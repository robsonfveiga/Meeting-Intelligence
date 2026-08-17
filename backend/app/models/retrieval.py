"""Retrieval and citation vocabulary.

`Citation` is the shape the user interface reads to render the evidence panel,
so it is denormalised on purpose — adding fields later means reshaping responses
the frontend already depends on.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.transcript import TimeRange


class SearchHit(BaseModel):
    """One result from a single strategy, before fusion.

    `score` is kept for display and debugging only. Fusion uses `rank`, because
    scores from different strategies are not comparable.
    """

    chunk_id: UUID
    score: float
    rank: int


class FusedHit(BaseModel):
    """A chunk after fusion, with the rank each strategy gave it.

    `ranks` is what the "how was this found" panel reads: a chunk at rank 1 in
    keyword and 40 in vector tells a very different story from one that placed
    third in both.
    """

    chunk_id: UUID
    score: float
    ranks: dict[str, int] = Field(default_factory=dict)


class SearchFilters(BaseModel):
    meeting_ids: list[UUID] = Field(default_factory=list)
    speaker: str | None = None


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


class SearchResult(BaseModel):
    query: str
    hits: list[ScoredChunk]
    strategy: str
    candidates: dict[str, int] = Field(default_factory=dict)
    timings_ms: dict[str, int] = Field(default_factory=dict)


class Citation(BaseModel):
    """A reference attached to a generated answer (slice 3).

    Carries the meeting title and speakers directly so the evidence panel
    renders without a request per citation.
    """

    chunk_id: UUID
    meeting_id: UUID
    meeting_title: str
    speakers: list[str]
    time: TimeRange
    quote: str
