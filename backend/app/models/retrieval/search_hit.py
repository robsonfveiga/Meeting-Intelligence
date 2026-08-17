from uuid import UUID

from pydantic import BaseModel


class SearchHit(BaseModel):
    """One result from a single strategy, before fusion.

    `score` is kept for display and debugging only. Fusion uses `rank`, because
    scores from different strategies are not comparable.
    """

    chunk_id: UUID
    score: float
    rank: int
