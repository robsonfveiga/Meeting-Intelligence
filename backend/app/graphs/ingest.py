"""The ingestion graph.

Ingestion is the expensive, slow, failure-prone half of this system: many
embedding calls and, later, a model pass per meeting. Running it as a
checkpointed graph means a failure at the embedding step resumes from the
embedding step instead of re-parsing and re-chunking everything.

It also removes infrastructure rather than adding it. The checkpointer is the
job store — `thread_id` is the job identifier, and the status endpoint reads
graph state — so there is no task queue, no Redis, and no jobs table.

**Nodes are thin.** Each one reads state, calls a pure function from `core/`,
writes to Postgres, and returns identifiers. The logic worth testing lives in
`core/` where it needs no infrastructure to exercise. A node that grows big
enough to need its own tests is a signal that logic belongs in `core/`, not that
`core/` should become nodes.
"""

from typing import Any
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph

from app.clients.llm import (
    CompletionUnavailable,
    EmbeddingUnavailable,
    complete_structured,
    completions_available,
    embed_texts,
    embeddings_available,
)
from app.config import get_settings
from app.core.chunking import build_context_header, chunk_turns
from app.core.extraction import (
    FACT_SCHEMA,
    build_windows,
    deduplicate,
    parse_facts,
    to_facts,
    verify_evidence,
)
from app.core.parsing import (
    has_speaker_attribution,
    looks_like_webvtt,
    parse_webvtt,
    title_and_date,
)
from app.core.prompts import build_extraction_messages
from app.db import chunks as chunks_db
from app.db import facts as facts_db
from app.db import meetings as meetings_db
from app.db import turns as turns_db
from app.db.engine import transaction
from app.models.fact.fact import Fact
from app.models.ingestion.ingestion_state import IngestionState
from app.models.ingestion.source_reference import SourceReference
from app.models.ingestion.stage import Stage
from app.models.ingestion.stage_error import StageError
from app.models.ingestion.stage_stats import StageStats
from app.models.transcript.meeting import Meeting
from app.models.transcript.transcript_format import TranscriptFormat
from app.models.transcript.turn import Turn
from app.observability.log import get_logger
from app.observability.stages import timed

log = get_logger(__name__)

_SAMPLE_BYTES = 4096

_NOT_WEBVTT = (
    "This does not look like a WebVTT transcript. In Teams, use "
    "Download → .vtt on the meeting transcript. Zoom, Whisper and most "
    "transcription tools can export WebVTT too."
)


def _read(path: str, limit: int | None = None) -> str:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read(limit) if limit else handle.read()


def _meeting_id(state: IngestionState) -> UUID:
    """Narrow the optional field, and state the invariant it depends on.

    `meeting_id` is None until the parser writes the meeting, so it is optional
    in the state type. Every node downstream of parsing requires it. Rather than
    casting the type away, fail loudly — a None here means the graph was wired
    wrong, which is worth a clear error rather than a confusing one later.
    """
    meeting_id = state.get("meeting_id")
    if meeting_id is None:
        raise RuntimeError("meeting_id is not set: a node ran before parsing")
    return meeting_id


def _source(state: IngestionState) -> SourceReference:
    """Take the source however it arrived.

    The state is a TypedDict, which annotates but does not coerce: the upload
    route puts a real `SourceReference` in, while anything driving the graph from
    JSON — LangGraph Studio, a replayed checkpoint, the platform API — puts the
    dict it deserialised. Both are legitimate entry points, so the node accepts
    either rather than the caller having to know which one it is.
    """
    source = state["source"]
    return source if isinstance(source, SourceReference) else SourceReference.model_validate(source)


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------


@timed("validate")
async def validate_node(state: IngestionState) -> dict[str, Any]:
    """Reject non-WebVTT before reading the whole file.

    Separate from parsing so the job reports *why* it failed: a wrong format and
    an empty transcript are different problems for whoever uploaded it.
    """
    source = _source(state)
    if not looks_like_webvtt(_read(source.storage_path, _SAMPLE_BYTES)):
        log.warning("ingest.rejected", job_id=state["job_id"], filename=source.filename)
        return {
            "stage": Stage.FAILED,
            "errors": [StageError(stage="validate", message=_NOT_WEBVTT)],
        }

    return {"detected_format": TranscriptFormat.WEBVTT, "stage": Stage.VALIDATED}


@timed("parse")
async def parse_node(state: IngestionState) -> dict[str, Any]:
    """Parse the file and write the meeting and its turns in one transaction.

    Parsing and persistence are one node rather than two because the turns
    cannot travel between them: state carries identifiers, not payloads, and
    turns have nowhere to live until the meeting row exists. Merging them also
    makes the write atomic — there is no state where a meeting exists with no
    content.
    """
    source = _source(state)
    transcript = parse_webvtt(_read(source.storage_path))

    if not transcript.turns:
        return {
            "stage": Stage.FAILED,
            "errors": [StageError(stage="parse", message="valid WebVTT, but it has no cues")],
        }

    warnings: list[StageError] = []
    if not has_speaker_attribution(transcript):
        warnings.append(
            StageError(
                stage="parse",
                message="no speaker names found; the Teams tenant may have speaker "
                "attribution disabled, so citations will not name anyone",
                recoverable=True,
            )
        )

    title, occurred_at = title_and_date(source.filename)
    meeting = Meeting(
        title=title,
        source_filename=source.filename,
        source_format=TranscriptFormat.WEBVTT,
        occurred_at=occurred_at,
        duration_ms=transcript.duration_ms,
        participants=transcript.participants,
    )
    rows = [
        Turn(
            meeting_id=meeting.id,
            index=turn.index,
            speaker=turn.speaker,
            time=turn.time,
            text=turn.text,
        )
        for turn in transcript.turns
    ]

    async with transaction() as conn:
        await meetings_db.insert(conn, meeting)
        await turns_db.add_many(conn, rows)

    log.info(
        "ingest.parsed",
        job_id=state["job_id"],
        turns=len(rows),
        participants=len(meeting.participants),
    )
    return {
        "meeting_id": meeting.id,
        "turn_count": len(rows),
        "stage": Stage.PARSED,
        "errors": warnings,
        "stats": {"parse": StageStats(items_out=len(rows))},
    }


def route_if_failed(state: IngestionState) -> str:
    """A terminal failure skips to the end rather than embedding nothing."""
    return "finalise" if state.get("stage") == Stage.FAILED else "continue"


@timed("chunk")
async def chunk_node(state: IngestionState) -> dict[str, Any]:
    meeting_id = _meeting_id(state)
    settings = get_settings()

    async with transaction() as conn:
        turns = await turns_db.list_by_meeting(conn, meeting_id)
        built = chunk_turns(
            turns,
            target_chars=settings.chunk_target_chars,
            max_chars=settings.chunk_max_chars,
            overlap_turns=settings.chunk_overlap_turns,
        )
        chunk_ids = await chunks_db.add_many(conn, built)

    log.info("ingest.chunked", job_id=state["job_id"], chunks=len(chunk_ids))
    return {
        "chunk_ids": chunk_ids,
        "stage": Stage.CHUNKED,
        "stats": {
            "chunk": StageStats(items_in=state.get("turn_count", 0), items_out=len(chunk_ids))
        },
    }


@timed("contextualise")
async def contextualise_node(state: IngestionState) -> dict[str, Any]:
    """Prefix each chunk with where it sits in the meeting, before embedding."""
    meeting_id = _meeting_id(state)

    async with transaction() as conn:
        meeting = await meetings_db.get(conn, meeting_id)
        stored = await chunks_db.list_by_meeting(conn, meeting_id)
        if meeting is None or not stored:
            return {"stage": Stage.CONTEXTUALISED}

        headers = {
            chunk.id: build_context_header(meeting.title, chunk, meeting.duration_ms or 0)
            for chunk in stored
        }
        await chunks_db.set_context_headers(conn, headers)

    return {
        "stage": Stage.CONTEXTUALISED,
        "stats": {"contextualise": StageStats(items_out=len(headers))},
    }


@timed("embed")
async def embed_node(state: IngestionState) -> dict[str, Any]:
    """Embed only what is not embedded yet.

    Reading the unembedded rows rather than the state's chunk list is what makes
    a retry cheap: work already paid for is not paid for again.
    """
    meeting_id = _meeting_id(state)

    if not embeddings_available():
        log.warning("embed.skipped", job_id=state["job_id"], reason="no api key")
        return {
            "stage": Stage.EMBEDDED,
            "errors": [
                StageError(
                    stage="embed",
                    message="OPENAI_API_KEY not set; chunks stored without vectors, "
                    "keyword search still works",
                    recoverable=True,
                )
            ],
        }

    async with transaction() as conn:
        pending = await chunks_db.list_unembedded(conn, meeting_id)

    if not pending:
        async with transaction() as conn:
            already = await chunks_db.count_embedded(conn, meeting_id)
        return {"stage": Stage.EMBEDDED, "embedded_count": already}

    try:
        result = await embed_texts([chunk.embedding_input for chunk in pending])
    except EmbeddingUnavailable as exc:
        return {
            "stage": Stage.EMBEDDED,
            "errors": [StageError(stage="embed", message=str(exc), recoverable=True)],
        }

    async with transaction() as conn:
        written = await chunks_db.set_embeddings(
            conn, dict(zip([c.id for c in pending], result.vectors, strict=True))
        )
        total = await chunks_db.count_embedded(conn, meeting_id)

    return {
        "stage": Stage.EMBEDDED,
        "embedded_count": total,
        "stats": {
            "embed": StageStats(
                items_in=len(pending),
                items_out=written,
                tokens=result.tokens,
                cost_usd=result.cost_usd,
            )
        },
    }


def _skipped(message: str) -> dict[str, Any]:
    """Extraction did not run, and the job says why rather than looking complete."""
    return {
        "stage": Stage.EXTRACTED,
        "errors": [StageError(stage="extract_facts", message=message, recoverable=True)],
    }


@timed("extract_facts")
async def extract_facts_node(state: IngestionState) -> dict[str, Any]:
    """Decisions, commitments and open threads, each tied to the turns it came from.

    One structured call per window, sequentially. Concurrency across windows
    would shorten a long meeting's ingest, but it also multiplies the rate limit
    a bulk upload hits, and nothing downstream is waiting on this — a background
    job that takes a minute longer is not a user-visible cost.
    """
    settings = get_settings()

    if not settings.extraction_enabled:
        return {"stage": Stage.EXTRACTED}

    if not completions_available():
        log.warning("extract.skipped", job_id=state["job_id"], reason="no api key")
        return _skipped(
            "OPENAI_API_KEY not set; decisions, commitments and open threads were "
            "not extracted. Search and retrieval are unaffected."
        )

    meeting_id = _meeting_id(state)
    async with transaction() as conn:
        turns = await turns_db.list_by_meeting(conn, meeting_id)

    windows = build_windows(turns, max_chars=settings.extraction_window_chars)
    if not windows:
        return {"stage": Stage.EXTRACTED}

    extracted: list[Fact] = []
    tokens = 0
    cost = 0.0
    dropped = 0

    for window in windows:
        try:
            result = await complete_structured(
                build_extraction_messages(window),
                schema=FACT_SCHEMA,
                schema_name="meeting_facts",
                model=settings.extraction_model or settings.llm_utility_model,
            )
        except CompletionUnavailable as exc:
            return _skipped(str(exc))

        tokens += result.tokens
        cost += result.cost_usd

        kept, rejected = verify_evidence(parse_facts(result.data), window)
        dropped += len(rejected)
        if rejected:
            log.warning(
                "extract.evidence_rejected",
                job_id=state["job_id"],
                count=len(rejected),
                first_window_turn=window[0].index,
            )

        capped = kept[: settings.extraction_max_facts_per_window]
        if len(kept) > len(capped):
            log.warning(
                "extract.window_capped",
                job_id=state["job_id"],
                returned=len(kept),
                kept=len(capped),
            )

        extracted.extend(to_facts(capped, meeting_id=meeting_id, window=window))

    merged = deduplicate(extracted)

    async with transaction() as conn:
        await facts_db.delete_for_meeting(conn, meeting_id)
        fact_ids = await facts_db.add_many(conn, merged)

    log.info(
        "ingest.extracted",
        job_id=state["job_id"],
        windows=len(windows),
        facts=len(fact_ids),
        dropped=dropped,
    )
    return {
        "stage": Stage.EXTRACTED,
        "fact_ids": fact_ids,
        "dropped_fact_count": dropped,
        "stats": {
            "extract_facts": StageStats(
                items_in=len(windows),
                items_out=len(fact_ids),
                tokens=tokens,
                cost_usd=cost,
            )
        },
    }


@timed("finalise")
async def finalise_node(state: IngestionState) -> dict[str, Any]:
    if state.get("stage") == Stage.FAILED:
        log.warning("ingest.failed", job_id=state["job_id"], errors=len(state.get("errors", [])))
        return {"stage": Stage.FAILED}

    log.info(
        "ingest.completed",
        job_id=state["job_id"],
        meeting_id=str(state.get("meeting_id")),
        turns=state.get("turn_count", 0),
        chunks=len(state.get("chunk_ids", [])),
        embedded=state.get("embedded_count", 0),
    )
    return {"stage": Stage.DONE}


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------


def build_ingestion_graph(checkpointer) -> Any:
    builder = StateGraph(IngestionState)

    builder.add_node("validate", validate_node)
    builder.add_node("parse", parse_node)
    builder.add_node("chunk", chunk_node)
    builder.add_node("contextualise", contextualise_node)
    builder.add_node("embed", embed_node)
    builder.add_node("extract_facts", extract_facts_node)
    builder.add_node("finalise", finalise_node)

    builder.add_edge(START, "validate")
    # Both gates share one predicate: a failed stage short-circuits to the end.
    builder.add_conditional_edges(
        "validate", route_if_failed, {"continue": "parse", "finalise": "finalise"}
    )
    builder.add_conditional_edges(
        "parse", route_if_failed, {"continue": "chunk", "finalise": "finalise"}
    )

    builder.add_edge("chunk", "contextualise")
    builder.add_edge("contextualise", "embed")
    builder.add_edge("embed", "extract_facts")
    builder.add_edge("extract_facts", "finalise")
    builder.add_edge("finalise", END)

    return builder.compile(checkpointer=checkpointer)


def new_job_id() -> str:
    return str(uuid4())


def studio_graph() -> Any:
    """Entry point for LangGraph Studio, which needs to build the graph itself.

    Compiled **without** a checkpointer, unlike the application's. Studio runs its
    own persistence layer and attaches it to whatever it loads; handing it ours
    would give the run two competing stores and defeat the thread inspection that
    is the reason to open Studio at all.

    Everything else is the real graph — the same nodes writing to the same
    database, so a run started here leaves real meetings behind.
    """
    return build_ingestion_graph(None)
