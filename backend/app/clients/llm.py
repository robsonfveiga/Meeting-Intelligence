"""The one place that talks to OpenAI.

Named for the capability, not the vendor: swapping providers rewrites the inside
of this file rather than reorganising the package. That is the whole of the
"swappable provider" story — no interface, no indirection, just a single obvious
place where every outbound model call lives.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings
from app.observability.log import get_logger

log = get_logger(__name__)

# text-embedding-3-small, dollars per million tokens. Used to turn the usage
# figures the API returns into a number the job endpoint can show.
_EMBEDDING_USD_PER_MTOK = 0.02

_client: AsyncOpenAI | None = None


class EmbeddingUnavailable(RuntimeError):
    """No API key configured. Recoverable — keyword search still works."""


@dataclass(slots=True)
class EmbeddingResult:
    vectors: list[list[float]]
    tokens: int
    cost_usd: float


def _get_client() -> AsyncOpenAI:
    global _client
    settings = get_settings()
    if not settings.openai_api_key:
        raise EmbeddingUnavailable("OPENAI_API_KEY is not set")
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


def embeddings_available() -> bool:
    return bool(get_settings().openai_api_key)


async def embed_texts(texts: list[str]) -> EmbeddingResult:
    """Embed in batches, reporting what it cost.

    Batched because one request per chunk would make ingesting a corpus a
    few-hundred-round-trip affair.
    """
    if not texts:
        return EmbeddingResult(vectors=[], tokens=0, cost_usd=0.0)

    settings = get_settings()
    client = _get_client()

    vectors: list[list[float]] = []
    tokens = 0
    batch_size = settings.embedding_batch_size

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
            dimensions=settings.embedding_dimensions,
        )
        # The API does not promise ordering, but does return an index per item.
        for item in sorted(response.data, key=lambda d: d.index):
            vectors.append(item.embedding)
        tokens += response.usage.total_tokens

    cost = tokens / 1_000_000 * _EMBEDDING_USD_PER_MTOK
    log.info("embed.completed", count=len(vectors), tokens=tokens, cost_usd=round(cost, 6))
    return EmbeddingResult(vectors=vectors, tokens=tokens, cost_usd=cost)


# --------------------------------------------------------------------------
# Completions
# --------------------------------------------------------------------------


class CompletionUnavailable(RuntimeError):
    """No API key configured. Not recoverable — there is no answer without one."""


@dataclass(slots=True)
class CompletionResult:
    text: str
    tokens: int
    cost_usd: float


def completions_available() -> bool:
    return bool(get_settings().openai_api_key)


def _price(prompt_tokens: int, completion_tokens: int) -> float:
    """Cost from configured rates.

    Rates default to zero and live in settings rather than being hardcoded.
    Published prices change and vary by model, and a stale constant compiled into
    the source reports a confident wrong number — worse than reporting none.
    Token counts come from the API and are always accurate.
    """
    settings = get_settings()
    return (
        prompt_tokens / 1_000_000 * settings.llm_input_usd_per_mtok
        + completion_tokens / 1_000_000 * settings.llm_output_usd_per_mtok
    )


def _request_kwargs(model: str | None, max_tokens: int | None) -> dict[str, Any]:
    """Only send parameters that were explicitly configured.

    Newer model families reject `temperature` outright and renamed the output
    limit, so sending defaults "just in case" is how a provider upgrade turns
    into a 400. Absent settings mean the provider's own defaults apply.
    """
    settings = get_settings()
    kwargs: dict[str, Any] = {"model": model or settings.llm_model}
    if settings.llm_temperature is not None:
        kwargs["temperature"] = settings.llm_temperature
    if max_tokens is not None:
        kwargs["max_completion_tokens"] = max_tokens
    return kwargs


async def complete(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
) -> CompletionResult:
    if not completions_available():
        raise CompletionUnavailable("OPENAI_API_KEY is not set")

    client = _get_client()
    # The SDK types messages as a union of per-role TypedDicts; a plain
    # list[dict[str, str]] is structurally identical but not assignable to it.
    response = await client.chat.completions.create(
        messages=messages,  # type: ignore[arg-type]
        **_request_kwargs(model, max_tokens),
    )

    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    cost = _price(prompt_tokens, completion_tokens)

    log.info(
        "completion.finished",
        model=model or get_settings().llm_model,
        tokens=prompt_tokens + completion_tokens,
        cost_usd=round(cost, 6),
    )
    return CompletionResult(
        text=response.choices[0].message.content or "",
        tokens=prompt_tokens + completion_tokens,
        cost_usd=cost,
    )


@dataclass(slots=True)
class StructuredResult:
    data: dict[str, Any]
    tokens: int
    cost_usd: float


async def complete_structured(
    messages: list[dict[str, str]],
    *,
    schema: dict[str, Any],
    schema_name: str,
    model: str | None = None,
    max_tokens: int | None = None,
) -> StructuredResult:
    """A completion constrained to a JSON schema.

    Strict schema mode rather than "reply with JSON" and a parser. Asking for
    JSON in the prose gets valid JSON almost always, and the residue is a
    parse-and-retry path that costs a request and still fails eventually.
    Constraining the shape at the provider moves that from a runtime risk to a
    contract — and the contract is versioned in one place, next to the caller
    that depends on it.

    A refusal returns empty data rather than raising: the caller treats "no facts
    here" as a legitimate outcome anyway, and an exception would fail an ingest
    over one unproductive window.
    """
    if not completions_available():
        raise CompletionUnavailable("OPENAI_API_KEY is not set")

    client = _get_client()
    # The schema is a plain dict rather than the SDK's TypedDict, so no overload
    # matches — same boundary looseness as the `messages` cast above.
    response = await client.chat.completions.create(  # type: ignore[call-overload]
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        },
        **_request_kwargs(model, max_tokens),
    )

    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    cost = _price(prompt_tokens, completion_tokens)

    message = response.choices[0].message
    data: dict[str, Any] = {}
    if getattr(message, "refusal", None):
        log.warning("completion.refused", schema=schema_name, refusal=message.refusal)
    elif message.content:
        try:
            parsed = json.loads(message.content)
        except json.JSONDecodeError:
            log.warning("completion.unparseable", schema=schema_name)
        else:
            if isinstance(parsed, dict):
                data = parsed

    log.info(
        "completion.structured",
        model=model or get_settings().llm_model,
        schema=schema_name,
        tokens=prompt_tokens + completion_tokens,
        cost_usd=round(cost, 6),
    )
    return StructuredResult(
        data=data,
        tokens=prompt_tokens + completion_tokens,
        cost_usd=cost,
    )


async def stream_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
) -> AsyncIterator[str | CompletionResult]:
    """Yield text deltas, then a final `CompletionResult` carrying usage.

    The mixed yield type is deliberate: usage totals only arrive after the last
    delta, and the caller needs both the tokens for the trace and the text as it
    arrives. A separate callback would hide the ordering that matters.
    """
    if not completions_available():
        raise CompletionUnavailable("OPENAI_API_KEY is not set")

    client = _get_client()
    stream = await client.chat.completions.create(  # type: ignore[call-overload]
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
        **_request_kwargs(model, max_tokens),
    )

    collected: list[str] = []
    prompt_tokens = completion_tokens = 0

    async for event in stream:
        if event.usage:
            prompt_tokens = event.usage.prompt_tokens
            completion_tokens = event.usage.completion_tokens
        for choice in event.choices:
            delta = choice.delta.content
            if delta:
                collected.append(delta)
                yield delta

    cost = _price(prompt_tokens, completion_tokens)
    log.info(
        "completion.streamed",
        model=model or get_settings().llm_model,
        tokens=prompt_tokens + completion_tokens,
        cost_usd=round(cost, 6),
    )
    yield CompletionResult(
        text="".join(collected),
        tokens=prompt_tokens + completion_tokens,
        cost_usd=cost,
    )
