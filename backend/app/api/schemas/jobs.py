from uuid import UUID

from pydantic import BaseModel, Field

from app.models.ingestion.stage import Stage
from app.models.ingestion.stage_error import StageError
from app.models.ingestion.stage_stats import StageStats
from app.models.transcript.transcript_format import TranscriptFormat


class UploadAccepted(BaseModel):
    job_id: str
    filename: str
    status_url: str


class JobResponse(BaseModel):
    """A flattened read of the ingestion state.

    Differs from `IngestionState` in ways the wire needs: chunk identifiers
    collapse to a count, and the per-stage durations are summed. Worth its own
    shape rather than exposing the state object, which is an internal contract
    that will keep changing as nodes are filled in.
    """

    job_id: str
    stage: Stage
    filename: str
    detected_format: TranscriptFormat | None = None
    meeting_id: UUID | None = None
    turn_count: int = 0
    chunk_count: int = 0
    fact_count: int = 0
    # Facts the extractor could not point at real turns for. Surfaced rather than
    # hidden: it is the one number that says whether extraction was grounded.
    dropped_fact_count: int = 0
    total_duration_ms: int = 0
    stats: dict[str, StageStats] = Field(default_factory=dict)
    errors: list[StageError] = Field(default_factory=list)
