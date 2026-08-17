from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.models.transcript.transcript_format import TranscriptFormat


class Meeting(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    source_filename: str
    source_format: TranscriptFormat
    occurred_at: datetime | None = None
    duration_ms: int | None = None
    participants: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
