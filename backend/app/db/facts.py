"""Fact reads and writes.

A module of functions taking a connection, like `db/meetings.py` — the
transaction boundary stays with the caller, and there is no state worth a class.
"""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import facts
from app.models.enums import FactKind
from app.models.fact import Fact
from app.models.transcript import TimeRange


def _to_model(row) -> Fact:
    return Fact(
        id=row.id,
        meeting_id=row.meeting_id,
        kind=FactKind(row.kind),
        statement=row.statement,
        owner=row.owner,
        due=row.due_text,
        start_turn_index=row.start_turn_index,
        end_turn_index=row.end_turn_index,
        time=TimeRange(start_ms=row.start_ms, end_ms=row.end_ms),
        speakers=list(row.speakers or []),
        created_at=row.created_at,
    )


async def add_many(conn: AsyncConnection, items: list[Fact]) -> list[UUID]:
    if not items:
        return []
    await conn.execute(
        facts.insert(),
        [
            {
                "id": fact.id,
                "meeting_id": fact.meeting_id,
                "kind": fact.kind.value,
                "statement": fact.statement,
                "owner": fact.owner,
                "due_text": fact.due,
                "start_turn_index": fact.start_turn_index,
                "end_turn_index": fact.end_turn_index,
                "start_ms": fact.time.start_ms,
                "end_ms": fact.time.end_ms,
                "speakers": fact.speakers,
            }
            for fact in items
        ],
    )
    return [fact.id for fact in items]


async def delete_for_meeting(conn: AsyncConnection, meeting_id: UUID) -> int:
    """Clear a meeting's facts so extraction can be re-run.

    Stricter than the chunk node, which relies on the checkpointer never
    replaying a completed step. Extraction is the last and most provider-
    dependent node, so a partial failure and a re-drive is the ordinary case
    here rather than the exotic one, and a duplicated decision list is a visible
    product defect rather than a wasted request.
    """
    result = await conn.execute(delete(facts).where(facts.c.meeting_id == meeting_id))
    return result.rowcount or 0


async def search(
    conn: AsyncConnection,
    *,
    meeting_ids: list[UUID] | None = None,
    kind: FactKind | None = None,
    owner: str | None = None,
    limit: int = 200,
) -> list[Fact]:
    """Filtered listing, across meetings by default.

    Cross-meeting is the interesting case: "what did we commit to" is a question
    about a series, not about one hour. Scoping to a single meeting is the same
    query with one filter set.
    """
    statement = select(facts)

    if meeting_ids:
        statement = statement.where(facts.c.meeting_id.in_(meeting_ids))
    if kind is not None:
        statement = statement.where(facts.c.kind == kind.value)
    if owner:
        statement = statement.where(facts.c.owner.ilike(f"%{owner}%"))

    statement = statement.order_by(facts.c.created_at.desc(), facts.c.start_turn_index).limit(limit)

    result = await conn.execute(statement)
    return [_to_model(row) for row in result]
