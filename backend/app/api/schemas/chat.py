from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    meeting_ids: list[UUID] = Field(default_factory=list)
    speaker: str | None = None
