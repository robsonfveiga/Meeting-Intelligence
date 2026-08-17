"""Meeting reads and writes.

A module, not a class. Modules are already namespaces in Python; there is no
state to hold, so grouping these behind a class would add a constructor and buy
nothing. The connection is passed in, which keeps the transaction boundary with
the caller.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import meetings
from app.models.transcript.meeting import Meeting
from app.models.transcript.transcript_format import TranscriptFormat


def _to_model(row) -> Meeting:
    return Meeting(
        id=row.id,
        title=row.title,
        source_filename=row.source_filename,
        source_format=TranscriptFormat(row.source_format),
        occurred_at=row.occurred_at,
        duration_ms=row.duration_ms,
        participants=list(row.participants or []),
        created_at=row.created_at,
    )


async def insert(conn: AsyncConnection, meeting: Meeting) -> UUID:
    await conn.execute(
        meetings.insert().values(
            id=meeting.id,
            title=meeting.title,
            source_filename=meeting.source_filename,
            source_format=meeting.source_format.value,
            occurred_at=meeting.occurred_at,
            duration_ms=meeting.duration_ms,
            participants=meeting.participants,
        )
    )
    return meeting.id


async def get(conn: AsyncConnection, meeting_id: UUID) -> Meeting | None:
    result = await conn.execute(select(meetings).where(meetings.c.id == meeting_id))
    row = result.one_or_none()
    return _to_model(row) if row else None


async def list_all(conn: AsyncConnection, limit: int = 100) -> list[Meeting]:
    result = await conn.execute(
        select(meetings).order_by(meetings.c.created_at.desc()).limit(limit)
    )
    return [_to_model(row) for row in result]


async def delete(conn: AsyncConnection, meeting_id: UUID) -> bool:
    """Remove a meeting and everything derived from it. False if it was not there.

    One statement, because the turns, chunks and facts all carry
    `ON DELETE CASCADE` back to this row — the database already knows that a
    chunk without its meeting is garbage, so deleting it here in Python would be
    restating a rule that is enforced a layer down. It also means the whole
    removal is one atomic step rather than four that can half-succeed.

    The `rowcount` is what separates "deleted" from "was never here", which is
    the difference between a 204 and a 404 for the caller.
    """
    result = await conn.execute(meetings.delete().where(meetings.c.id == meeting_id))
    return result.rowcount > 0
