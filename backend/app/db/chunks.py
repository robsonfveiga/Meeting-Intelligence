import re
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import chunks
from app.models.chunk import Chunk
from app.models.retrieval import SearchFilters, SearchHit
from app.models.transcript import TimeRange


def _to_model(row) -> Chunk:
    return Chunk(
        id=row.id,
        meeting_id=row.meeting_id,
        index=row.chunk_index,
        start_turn_index=row.start_turn_index,
        end_turn_index=row.end_turn_index,
        time=TimeRange(start_ms=row.start_ms, end_ms=row.end_ms),
        speakers=list(row.speakers or []),
        text=row.text,
        context_header=row.context_header,
    )


async def add_many(conn: AsyncConnection, items: list[Chunk]) -> list[UUID]:
    """Insert chunks without embeddings.

    The embedding column stays null until the embed node fills it, and that gap
    is exactly what makes a failed ingest resumable: chunking is not redone when
    the embedding provider times out.
    """
    if not items:
        return []
    await conn.execute(
        chunks.insert(),
        [
            {
                "id": chunk.id,
                "meeting_id": chunk.meeting_id,
                "chunk_index": chunk.index,
                "start_turn_index": chunk.start_turn_index,
                "end_turn_index": chunk.end_turn_index,
                "start_ms": chunk.time.start_ms,
                "end_ms": chunk.time.end_ms,
                "speakers": chunk.speakers,
                "text": chunk.text,
                "context_header": chunk.context_header,
            }
            for chunk in items
        ],
    )
    return [chunk.id for chunk in items]


async def list_by_meeting(conn: AsyncConnection, meeting_id: UUID) -> list[Chunk]:
    result = await conn.execute(
        select(chunks).where(chunks.c.meeting_id == meeting_id).order_by(chunks.c.chunk_index)
    )
    return [_to_model(row) for row in result]


async def list_unembedded(conn: AsyncConnection, meeting_id: UUID) -> list[Chunk]:
    """Only what still needs work, so a retry does not re-embed and re-pay."""
    result = await conn.execute(
        select(chunks)
        .where(chunks.c.meeting_id == meeting_id, chunks.c.embedding.is_(None))
        .order_by(chunks.c.chunk_index)
    )
    return [_to_model(row) for row in result]


async def set_context_headers(conn: AsyncConnection, headers: dict[UUID, str]) -> None:
    for chunk_id, header in headers.items():
        await conn.execute(
            update(chunks).where(chunks.c.id == chunk_id).values(context_header=header)
        )


async def set_embeddings(conn: AsyncConnection, vectors: dict[UUID, list[float]]) -> int:
    for chunk_id, vector in vectors.items():
        await conn.execute(update(chunks).where(chunks.c.id == chunk_id).values(embedding=vector))
    return len(vectors)


async def count_embedded(conn: AsyncConnection, meeting_id: UUID) -> int:
    result = await conn.execute(
        select(chunks.c.id).where(
            chunks.c.meeting_id == meeting_id, chunks.c.embedding.is_not(None)
        )
    )
    return len(result.all())


# --------------------------------------------------------------------------
# Retrieval primitives
#
# The database provides the two *primitives*; merging and re-ranking their
# results lives in `core/ranking.py` as pure functions. That split is what lets
# the ranking algorithm — the part most likely to hide a subtle bug and the part
# that gets tuned most — be tested and measured with no database running.
# --------------------------------------------------------------------------


def _apply_filters(statement, filters: SearchFilters | None):
    if not filters:
        return statement
    if filters.meeting_ids:
        statement = statement.where(chunks.c.meeting_id.in_(filters.meeting_ids))
    if filters.speaker:
        statement = statement.where(chunks.c.speakers.any(filters.speaker))
    return statement


async def search_by_vector(
    conn: AsyncConnection,
    embedding: list[float],
    *,
    limit: int = 20,
    filters: SearchFilters | None = None,
) -> list[SearchHit]:
    """Nearest chunks by cosine distance.

    Cosine rather than L2 because OpenAI embeddings are normalised, so the two
    rank identically and cosine is what the index was built for.
    """
    distance = chunks.c.embedding.cosine_distance(embedding)
    statement = (
        select(chunks.c.id, distance.label("distance"))
        .where(chunks.c.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )
    result = await conn.execute(_apply_filters(statement, filters))
    return [
        SearchHit(chunk_id=row.id, score=1.0 - row.distance, rank=rank)
        for rank, row in enumerate(result, start=1)
    ]


def _or_tsquery(query: str):
    """Build an OR-joined tsquery from the words in a question.

    Tokens are extracted with a word regex rather than passed through, so the
    string handed to `to_tsquery` can never contain its operators — no escaping
    to get wrong, and no syntax error from whatever a user typed. Postgres stems
    each token and drops stopwords under the 'english' configuration.
    """
    tokens = [t for t in re.findall(r"[\w']+", query.lower()) if len(t) > 1]
    if not tokens:
        return None
    return func.to_tsquery("english", " | ".join(tokens))


async def search_by_text(
    conn: AsyncConnection,
    query: str,
    *,
    limit: int = 20,
    filters: SearchFilters | None = None,
) -> list[SearchHit]:
    """Keyword search over the generated tsvector column.

    This is not a fallback. Meetings are dense with proper nouns and figures —
    "eleven thousand", "rollback tooling", a customer name — that embeddings
    blur together and exact matching finds immediately.

    Terms are joined with OR, not AND. `websearch_to_tsquery` and
    `plainto_tsquery` both require *every* term, which for a natural question
    like "how long did the rollback actually take" means a chunk must contain all
    six words — so it matched almost nothing. Measured: recall@10 was flat at
    0.27 with AND, and the flatness was the tell, since a ranking problem
    improves with depth and a filtering problem does not. Precision comes from
    `ts_rank_cd` ordering instead, which is how keyword search is normally built.
    """
    tsquery = _or_tsquery(query)
    if tsquery is None:
        return []
    rank = func.ts_rank_cd(chunks.c.text_search, tsquery)
    statement = (
        select(chunks.c.id, rank.label("rank"))
        .where(chunks.c.text_search.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(limit)
    )
    result = await conn.execute(_apply_filters(statement, filters))
    return [
        SearchHit(chunk_id=row.id, score=float(row.rank), rank=position)
        for position, row in enumerate(result, start=1)
    ]


async def get_many(conn: AsyncConnection, ids: list[UUID]) -> dict[UUID, Chunk]:
    """Hydrate fused hits in one round trip, keyed for ordering by the caller."""
    if not ids:
        return {}
    result = await conn.execute(select(chunks).where(chunks.c.id.in_(ids)))
    return {row.id: _to_model(row) for row in result}


async def get_by_indexes(
    conn: AsyncConnection, meeting_id: UUID, indexes: list[int]
) -> dict[int, Chunk]:
    """Fetch specific chunk positions — used for neighbour expansion."""
    if not indexes:
        return {}
    result = await conn.execute(
        select(chunks).where(chunks.c.meeting_id == meeting_id, chunks.c.chunk_index.in_(indexes))
    )
    return {row.chunk_index: _to_model(row) for row in result}


async def count_by_meeting(conn: AsyncConnection, meeting_id: UUID) -> int:
    result = await conn.execute(select(chunks.c.id).where(chunks.c.meeting_id == meeting_id))
    return len(result.all())
