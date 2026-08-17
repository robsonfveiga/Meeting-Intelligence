from uuid import UUID

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=8, ge=1, le=50)
    meeting_ids: list[UUID] = Field(default_factory=list)
    speaker: str | None = None
    # Attaches adjacent chunks as context. Off by default so retrieval metrics
    # measure the hit itself rather than the window around it.
    expand: bool = False
