from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.models.transcript.time_range import TimeRange


class Turn(BaseModel):
    """One uninterrupted stretch of speech by one speaker.

    The atom of a transcript. Chunking groups these; it never splits one.
    """

    id: UUID = Field(default_factory=uuid4)
    meeting_id: UUID
    index: int
    speaker: str
    time: TimeRange
    text: str
