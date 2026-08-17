"""Answer vocabulary.

`AnswerTrace` is a first-class part of the response rather than a debug extra.
It is what the "how was this answer built" panel renders, and shipping it on
every answer means the interface never has to ask a second time — the same
argument that put speaker and title inside `Citation`.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.retrieval import ScoredChunk
from app.models.transcript import TimeRange


class AnswerCitation(BaseModel):
    """A verified reference. Exists only if the chunk behind it was in context."""

    marker: int
    chunk_id: UUID
    meeting_id: UUID
    meeting_title: str
    speakers: list[str]
    time: TimeRange
    quote: str


class AnswerTrace(BaseModel):
    """What the system did, in the response the caller already has."""

    search_query: str
    rewritten: bool = False
    attempts: int = 1
    hits_considered: int = 0
    sufficient: bool = True
    # Markers the model emitted that pointed at excerpts we never supplied. A
    # non-zero count is a grounding failure worth surfacing, not hiding.
    dropped_markers: list[int] = Field(default_factory=list)
    timings_ms: dict[str, int] = Field(default_factory=dict)
    tokens: int = 0
    cost_usd: float = 0.0


class Answer(BaseModel):
    question: str
    text: str
    citations: list[AnswerCitation] = Field(default_factory=list)
    # True when retrieval found nothing usable and no model was called at all.
    refused: bool = False
    excerpts: list[ScoredChunk] = Field(default_factory=list)
    trace: AnswerTrace
