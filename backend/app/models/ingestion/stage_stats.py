from pydantic import BaseModel


class StageStats(BaseModel):
    """One node's measurements. The cost and latency story is assembled from these."""

    duration_ms: int = 0
    items_in: int = 0
    items_out: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
