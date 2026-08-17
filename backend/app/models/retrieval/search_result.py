from pydantic import BaseModel, Field

from app.models.retrieval.scored_chunk import ScoredChunk


class SearchResult(BaseModel):
    query: str
    hits: list[ScoredChunk]
    strategy: str
    candidates: dict[str, int] = Field(default_factory=dict)
    timings_ms: dict[str, int] = Field(default_factory=dict)
