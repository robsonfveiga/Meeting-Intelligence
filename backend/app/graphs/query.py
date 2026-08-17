"""The query graph.

Slice 2 kept this as a plain function, on the grounds that embed → search →
fuse is a straight line and a graph would have been ceremony. Slice 3 changes
that: the path now branches on whether anything was retrieved, grades whether the
excerpts can answer the question, and loops back through a rewritten query when
they cannot. Conditional edges and a cycle — the shape LangGraph exists for.

**No checkpointer here, unlike ingestion.** A query is a few seconds of work
that is cheap to redo, so durability buys nothing and would cost a database write
per node on the latency-sensitive path. That is also why this state may carry
retrieved chunks directly: the identifiers-not-payloads rule exists because
ingestion state is serialised after every step, and this state never is.

Generation is deliberately *outside* the graph. Streaming tokens to a browser is
a straight line, and forcing it through graph event plumbing to gain nothing
would be the same mistake in the opposite direction. The graph prepares the
evidence; `answer` and `answer_stream` consume it.
"""

import asyncio
import operator
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.clients.llm import (
    CompletionResult,
    complete,
    embed_texts,
    embeddings_available,
    stream_completion,
)
from app.config import get_settings
from app.core.grounding import ground, is_unsupported
from app.core.prompts import (
    NO_EVIDENCE,
    build_answer_messages,
    build_grader_messages,
    build_rewrite_messages,
)
from app.core.ranking import neighbour_ids, reciprocal_rank_fusion
from app.db import chunks as chunks_db
from app.db import meetings as meetings_db
from app.db.engine import transaction
from app.models.answer import Answer, AnswerTrace
from app.models.retrieval import ScoredChunk, SearchFilters, SearchResult
from app.observability.log import get_logger

log = get_logger(__name__)

MIN_CANDIDATES = 20


def merge_timings(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    return {**left, **right}


class QueryState(TypedDict, total=False):
    question: str
    search_query: str
    filters: SearchFilters
    limit: int
    expand: bool

    attempts: int
    rewritten: bool
    hits: list[ScoredChunk]
    sufficient: bool
    refused: bool

    tokens: Annotated[int, operator.add]
    cost_usd: Annotated[float, operator.add]
    timings_ms: Annotated[dict[str, int], merge_timings]


# --------------------------------------------------------------------------
# Retrieval (unchanged from slice 2, now a node)
# --------------------------------------------------------------------------


async def _retrieve(
    query: str, *, limit: int, filters: SearchFilters | None, expand: bool
) -> tuple[list[ScoredChunk], dict[str, int], dict[str, int]]:
    settings = get_settings()
    timings: dict[str, int] = {}
    candidate_limit = max(limit * settings.retrieval_candidate_multiplier, MIN_CANDIDATES)

    started = time.perf_counter()
    vector_query: list[float] | None = None
    if embeddings_available():
        vector_query = (await embed_texts([query])).vectors[0]
    timings["embed"] = int((time.perf_counter() - started) * 1000)

    started = time.perf_counter()
    async with transaction() as conn:
        tasks = [chunks_db.search_by_text(conn, query, limit=candidate_limit, filters=filters)]
        if vector_query is not None:
            tasks.append(
                chunks_db.search_by_vector(
                    conn, vector_query, limit=candidate_limit, filters=filters
                )
            )
        gathered = await asyncio.gather(*tasks)
    timings["retrieve"] = int((time.perf_counter() - started) * 1000)

    rankings = {"keyword": gathered[0]}
    if len(gathered) > 1:
        rankings["vector"] = gathered[1]

    started = time.perf_counter()
    fused = reciprocal_rank_fusion(
        rankings,
        weights={
            "keyword": settings.retrieval_keyword_weight,
            "vector": settings.retrieval_vector_weight,
        },
    )[:limit]
    timings["fuse"] = int((time.perf_counter() - started) * 1000)

    hits = await _hydrate(fused, expand=expand)
    return hits, timings, {name: len(v) for name, v in rankings.items()}


async def _hydrate(fused: list[Any], *, expand: bool) -> list[ScoredChunk]:
    if not fused:
        return []

    async with transaction() as conn:
        by_id = await chunks_db.get_many(conn, [hit.chunk_id for hit in fused])
        meetings = {
            meeting_id: await meetings_db.get(conn, meeting_id)
            for meeting_id in {c.meeting_id for c in by_id.values()}
        }
        neighbours = await _fetch_neighbours(conn, fused, by_id) if expand else {}

    results: list[ScoredChunk] = []
    for hit in fused:
        chunk = by_id.get(hit.chunk_id)
        if chunk is None:
            continue  # deleted between search and hydrate
        meeting = meetings.get(chunk.meeting_id)
        results.append(
            ScoredChunk(
                chunk_id=chunk.id,
                meeting_id=chunk.meeting_id,
                meeting_title=meeting.title if meeting else "",
                chunk_index=chunk.index,
                text=chunk.text,
                time=chunk.time,
                speakers=chunk.speakers,
                score=hit.score,
                ranks=hit.ranks,
                context_before=neighbours.get((chunk.meeting_id, chunk.index - 1)),
                context_after=neighbours.get((chunk.meeting_id, chunk.index + 1)),
            )
        )
    return results


async def _fetch_neighbours(conn: Any, fused: list[Any], by_id: dict) -> dict[tuple, str]:
    """Small-to-big: widen the returned window without widening what was indexed."""
    found_text: dict[tuple, str] = {}
    by_meeting: dict = {}
    for hit in fused:
        chunk = by_id.get(hit.chunk_id)
        if chunk:
            by_meeting.setdefault(chunk.meeting_id, []).append(chunk.index)

    for meeting_id, indexes in by_meeting.items():
        total = await chunks_db.count_by_meeting(conn, meeting_id)
        found = await chunks_db.get_by_indexes(
            conn, meeting_id, neighbour_ids(indexes, total=total)
        )
        for index, chunk in found.items():
            found_text[(meeting_id, index)] = chunk.text
    return found_text


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------


async def retrieve_node(state: QueryState) -> dict[str, Any]:
    hits, timings, candidates = await _retrieve(
        state.get("search_query") or state["question"],
        limit=state.get("limit", get_settings().answer_excerpt_count),
        filters=state.get("filters"),
        expand=state.get("expand", True),
    )
    log.info(
        "query.retrieved",
        query=state.get("search_query"),
        hits=len(hits),
        candidates=candidates,
        attempt=state.get("attempts", 0) + 1,
    )
    return {
        "hits": hits,
        "attempts": state.get("attempts", 0) + 1,
        "timings_ms": timings,
    }


async def grade_node(state: QueryState) -> dict[str, Any]:
    """Are these excerpts enough to answer?

    A cheap model, because the judgement is coarse and it runs on every query.
    Its only job is to decide whether to spend a rewrite-and-retry, so a wrong
    answer costs one extra retrieval rather than a wrong result — which is why a
    small model is the right tool and a failure here defaults to proceeding.
    """
    started = time.perf_counter()
    try:
        result = await complete(
            build_grader_messages(state["question"], state["hits"]),
            model=get_settings().llm_utility_model,
        )
        sufficient = "INSUFFICIENT" not in result.text.upper()
        tokens, cost = result.tokens, result.cost_usd
    except Exception as exc:
        # Grading is an optimisation. If it breaks, answer with what we have
        # rather than failing the request.
        log.warning("query.grade_failed", error=str(exc))
        sufficient, tokens, cost = True, 0, 0.0

    log.info("query.graded", sufficient=sufficient, hits=len(state["hits"]))
    return {
        "sufficient": sufficient,
        "tokens": tokens,
        "cost_usd": cost,
        "timings_ms": {"grade": int((time.perf_counter() - started) * 1000)},
    }


async def rewrite_node(state: QueryState) -> dict[str, Any]:
    """Restate the question in the vocabulary people actually speak.

    "What is our position on pricing?" retrieves badly because nobody says
    "position on pricing" out loud; they say "hold the increase until after
    launch". This is the whole reason for the loop.
    """
    started = time.perf_counter()
    try:
        result = await complete(
            build_rewrite_messages(state["question"]),
            model=get_settings().llm_utility_model,
        )
        rewritten = result.text.strip().strip('"') or state["question"]
        tokens, cost = result.tokens, result.cost_usd
    except Exception as exc:
        log.warning("query.rewrite_failed", error=str(exc))
        rewritten, tokens, cost = state["question"], 0, 0.0

    log.info("query.rewritten", original=state["question"], rewritten=rewritten)
    return {
        "search_query": rewritten,
        "rewritten": True,
        "tokens": tokens,
        "cost_usd": cost,
        "timings_ms": {"rewrite": int((time.perf_counter() - started) * 1000)},
    }


async def refuse_node(state: QueryState) -> dict[str, Any]:
    """Nothing retrieved, so no model is called at all.

    A guardrail and a cost saving in one: with no evidence there is nothing to
    ground an answer in, and asking anyway invites exactly the confident
    fabrication the citations exist to prevent.
    """
    log.info("query.refused", question=state["question"], reason="no hits")
    return {"refused": True}


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------


def route_after_retrieve(state: QueryState) -> str:
    return "refuse" if not state.get("hits") else "grade"


def route_after_grade(state: QueryState) -> str:
    """Retry once on a bad grade, then answer with whatever we have.

    Answering imperfectly beats looping: the excerpts are shown alongside the
    answer, so a reader can see the evidence is thin.
    """
    if state.get("sufficient"):
        return "ready"
    if state.get("attempts", 1) >= get_settings().max_retrieval_attempts:
        return "ready"
    return "rewrite"


def build_query_graph() -> Any:
    builder = StateGraph(QueryState)

    builder.add_node("retrieve", retrieve_node)
    builder.add_node("grade", grade_node)
    builder.add_node("rewrite", rewrite_node)
    builder.add_node("refuse", refuse_node)

    builder.add_edge(START, "retrieve")
    builder.add_conditional_edges(
        "retrieve", route_after_retrieve, {"grade": "grade", "refuse": "refuse"}
    )
    builder.add_conditional_edges("grade", route_after_grade, {"rewrite": "rewrite", "ready": END})
    builder.add_edge("rewrite", "retrieve")  # the cycle
    builder.add_edge("refuse", END)

    return builder.compile()


_graph = None


def get_query_graph() -> Any:
    global _graph
    if _graph is None:
        _graph = build_query_graph()
    return _graph


# --------------------------------------------------------------------------
# Public surface
# --------------------------------------------------------------------------


async def search(
    query: str,
    *,
    limit: int = 8,
    filters: SearchFilters | None = None,
    expand: bool = False,
) -> SearchResult:
    """Retrieval alone, with no model in the loop. Used by /search and the evals."""
    hits, timings, candidates = await _retrieve(query, limit=limit, filters=filters, expand=expand)
    return SearchResult(
        query=query,
        hits=hits,
        strategy="hybrid" if "vector" in candidates else "keyword-only",
        candidates=candidates,
        timings_ms=timings,
    )


async def prepare(
    question: str, *, filters: SearchFilters | None = None, limit: int | None = None
) -> QueryState:
    """Run the graph: retrieve, grade, and rewrite-and-retry if needed."""
    settings = get_settings()
    initial: QueryState = {
        "question": question,
        "search_query": question,
        "filters": filters or SearchFilters(),
        "limit": limit or settings.answer_excerpt_count,
        "expand": True,
        "attempts": 0,
        "rewritten": False,
        "tokens": 0,
        "cost_usd": 0.0,
        "timings_ms": {},
    }
    return await get_query_graph().ainvoke(initial)


def _trace(state: QueryState, extra_timings: dict[str, int], dropped: list[int]) -> AnswerTrace:
    return AnswerTrace(
        search_query=state.get("search_query", state["question"]),
        rewritten=bool(state.get("rewritten")),
        attempts=state.get("attempts", 1),
        hits_considered=len(state.get("hits", [])),
        sufficient=bool(state.get("sufficient", False)),
        dropped_markers=dropped,
        timings_ms={**state.get("timings_ms", {}), **extra_timings},
        tokens=state.get("tokens", 0),
        cost_usd=state.get("cost_usd", 0.0),
    )


def refusal(state: QueryState) -> Answer:
    return Answer(
        question=state["question"],
        text=NO_EVIDENCE,
        refused=True,
        excerpts=[],
        trace=_trace(state, {}, []),
    )


async def answer(question: str, *, filters: SearchFilters | None = None) -> Answer:
    """Retrieve, generate, and verify every citation before returning."""
    state = await prepare(question, filters=filters)
    if state.get("refused"):
        return refusal(state)

    hits = state["hits"]
    started = time.perf_counter()
    result = await complete(
        build_answer_messages(question, hits),
        max_tokens=get_settings().llm_max_answer_tokens,
    )
    elapsed = int((time.perf_counter() - started) * 1000)

    text, citations, dropped = ground(result.text, hits)
    if dropped:
        log.warning("answer.dropped_markers", markers=dropped, question=question)
    if is_unsupported(text, hits):
        log.warning("answer.uncited", question=question)

    trace = _trace(state, {"answer": elapsed}, dropped)
    trace.tokens += result.tokens
    trace.cost_usd += result.cost_usd

    return Answer(question=question, text=text, citations=citations, excerpts=hits, trace=trace)


async def answer_stream(
    question: str, *, filters: SearchFilters | None = None
) -> AsyncIterator[tuple[str, Any]]:
    """Yield `(event, payload)` pairs for Server-Sent Events.

    Excerpts are emitted *before* the first token so the evidence panel renders
    while the answer is still being written — the retrieval is already done by
    then, and holding it back would waste the most useful second of the request.

    Citations arrive at the end because verification needs the finished text: a
    marker cannot be checked until it has been fully written.
    """
    state = await prepare(question, filters=filters)

    if state.get("refused"):
        final = refusal(state)
        yield "excerpts", []
        yield "token", final.text
        yield "done", final
        return

    hits = state["hits"]
    yield "excerpts", hits

    started = time.perf_counter()
    completion: CompletionResult | None = None
    async for piece in stream_completion(
        build_answer_messages(question, hits),
        max_tokens=get_settings().llm_max_answer_tokens,
    ):
        if isinstance(piece, CompletionResult):
            completion = piece
        else:
            yield "token", piece
    elapsed = int((time.perf_counter() - started) * 1000)

    raw = completion.text if completion else ""
    text, citations, dropped = ground(raw, hits)
    if dropped:
        log.warning("answer.dropped_markers", markers=dropped, question=question)

    trace = _trace(state, {"answer": elapsed}, dropped)
    if completion:
        trace.tokens += completion.tokens
        trace.cost_usd += completion.cost_usd

    yield (
        "done",
        Answer(question=question, text=text, citations=citations, excerpts=hits, trace=trace),
    )
