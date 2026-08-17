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
from app.models.enums import TranscriptFormat
from app.models.transcript import Meeting


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
