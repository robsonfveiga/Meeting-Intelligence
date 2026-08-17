from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.models.enums import TranscriptFormat


class TimeRange(BaseModel):
    """Offset from the start of the recording, in milliseconds.

    Milliseconds rather than a timedelta because that is what every transcript
    format gives us and what the user interface needs back for seeking.
    """

    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


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


class ParsedTurn(BaseModel):
    """A turn before it belongs to anything.

    Separate from `Turn` because parsing happens before the meeting row exists,
    and a required `meeting_id` the parser cannot supply would be a lie.
    """

    index: int
    speaker: str
    time: TimeRange
    text: str


class ParsedTranscript(BaseModel):
    """A parser's whole output. Metadata is derived, never guessed."""

    turns: list[ParsedTurn]

    @property
    def participants(self) -> list[str]:
        """Distinct speakers, in the order they first spoke."""
        seen: dict[str, None] = {}
        for turn in self.turns:
            seen.setdefault(turn.speaker, None)
        return list(seen)

    @property
    def duration_ms(self) -> int:
        return max((t.time.end_ms for t in self.turns), default=0)


class Meeting(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    source_filename: str
    source_format: TranscriptFormat
    occurred_at: datetime | None = None
    duration_ms: int | None = None
    participants: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
