from uuid import UUID

from pydantic import BaseModel, Field


class FusedHit(BaseModel):
    """A chunk after fusion, with the rank each strategy gave it.

    `ranks` is what the "how was this found" panel reads: a chunk at rank 1 in
    keyword and 40 in vector tells a very different story from one that placed
    third in both.
    """

    chunk_id: UUID
    score: float
    ranks: dict[str, int] = Field(default_factory=dict)
