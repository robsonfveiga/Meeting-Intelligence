from uuid import UUID

from pydantic import BaseModel, Field

from app.models.transcript.time_range import TimeRange


class ScoredChunk(BaseModel):
    """A fused hit hydrated with enough content to be read or cited."""

    chunk_id: UUID
    meeting_id: UUID
    meeting_title: str
    chunk_index: int
    text: str
    time: TimeRange
    speakers: list[str]
    score: float
    ranks: dict[str, int] = Field(default_factory=dict)
    # Adjacent chunks, when neighbour expansion is on. Context for a generator,
    # not additional hits — never counted in retrieval metrics.
    context_before: str | None = None
    context_after: str | None = None
