from uuid import UUID

from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    meeting_ids: list[UUID] = Field(default_factory=list)
    speaker: str | None = None
