from pydantic import BaseModel

from app.models.transcript.time_range import TimeRange


class ParsedTurn(BaseModel):
    """A turn before it belongs to anything.

    Separate from `Turn` because parsing happens before the meeting row exists,
    and a required `meeting_id` the parser cannot supply would be a lie.
    """

    index: int
    speaker: str
    time: TimeRange
    text: str
