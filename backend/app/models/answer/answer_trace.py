from pydantic import BaseModel, Field


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
