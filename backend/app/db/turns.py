from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import turns
from app.models.transcript import TimeRange, Turn


def _to_model(row) -> Turn:
    return Turn(
        id=row.id,
        meeting_id=row.meeting_id,
        index=row.turn_index,
        speaker=row.speaker,
        time=TimeRange(start_ms=row.start_ms, end_ms=row.end_ms),
        text=row.text,
    )


async def add_many(conn: AsyncConnection, items: list[Turn]) -> int:
    """One statement, not one per turn.

    A meeting is hundreds of turns; inserting them in a loop would make ingest
    visibly slow for no reason.
    """
    if not items:
        return 0
    await conn.execute(
        turns.insert(),
        [
            {
                "id": turn.id,
                "meeting_id": turn.meeting_id,
                "turn_index": turn.index,
                "speaker": turn.speaker,
                "start_ms": turn.time.start_ms,
                "end_ms": turn.time.end_ms,
                "text": turn.text,
            }
            for turn in items
        ],
    )
    return len(items)


async def list_by_meeting(conn: AsyncConnection, meeting_id: UUID) -> list[Turn]:
    result = await conn.execute(
        select(turns).where(turns.c.meeting_id == meeting_id).order_by(turns.c.turn_index)
    )
    return [_to_model(row) for row in result]
