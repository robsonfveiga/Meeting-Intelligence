"""Graph state.

Two rules govern this file.

**Identifiers, never payloads.** Nodes write their real output to Postgres and
put identifiers in the state. No transcript text, no chunk bodies, and above all
no embedding vectors. State is checkpointed to the database after every node, so
a payload-carrying state means writing thousands of floats into a checkpoint
blob on every step, and a "resume" that re-does work already saved. Keeping the
state small is what makes resume genuinely resume.

**Every field declares replace or accumulate.** LangGraph replaces by default.
Fields that gather contributions from several nodes need an explicit reducer.
Getting this wrong on `stats` is silent: you keep only the last node's numbers
and do not notice until you go looking for the cost breakdown.
"""

import operator
from typing import Annotated, TypedDict
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import Stage, TranscriptFormat


class SourceReference(BaseModel):
    """The uploaded file. Where it is, not what it says."""

    filename: str
    content_type: str | None = None
    size_bytes: int = 0
    storage_path: str


class StageStats(BaseModel):
    """One node's measurements. The cost and latency story is assembled from these."""

    duration_ms: int = 0
    items_in: int = 0
    items_out: int = 0
    tokens: int = 0
    cost_usd: float = 0.0


class StageError(BaseModel):
    stage: str
    message: str
    recoverable: bool = False


def merge_stats(left: dict[str, StageStats], right: dict[str, StageStats]) -> dict[str, StageStats]:
    """Merge by stage name. Without this, each node would erase the previous one's numbers."""
    return {**left, **right}


class IngestionState(TypedDict, total=False):
    job_id: str
    source: SourceReference
    stage: Stage
    detected_format: TranscriptFormat | None
    meeting_id: UUID | None
    turn_count: int
    embedded_count: int
    # Replaced, not accumulated — unlike `chunk_ids` below. The extraction node
    # clears a meeting's facts before writing, so a re-drive produces a complete
    # new set rather than more of the old one, and a state that appended would
    # disagree with the database it describes.
    fact_ids: list[UUID]
    # Facts the extractor cited turns for that it was never shown. Non-zero is a
    # grounding failure worth surfacing on the job, the ingest-side counterpart
    # of `AnswerTrace.dropped_markers`.
    dropped_fact_count: int

    # --- accumulated across nodes ---
    chunk_ids: Annotated[list[UUID], operator.add]
    errors: Annotated[list[StageError], operator.add]
    stats: Annotated[dict[str, StageStats], merge_stats]


def new_ingestion_state(job_id: str, source: SourceReference) -> IngestionState:
    return IngestionState(
        job_id=job_id,
        source=source,
        stage=Stage.RECEIVED,
        detected_format=None,
        meeting_id=None,
        turn_count=0,
        embedded_count=0,
        dropped_fact_count=0,
        chunk_ids=[],
        fact_ids=[],
        errors=[],
        stats={},
    )


class JobStatus(BaseModel):
    """A read-only view of ingestion state, assembled from the checkpoint."""

    job_id: str
    stage: Stage
    filename: str
    detected_format: TranscriptFormat | None = None
    meeting_id: UUID | None = None
    turn_count: int = 0
    chunk_count: int = 0
    fact_count: int = 0
    errors: list[StageError] = Field(default_factory=list)
    stats: dict[str, StageStats] = Field(default_factory=dict)

    @property
    def total_duration_ms(self) -> int:
        return sum(s.duration_ms for s in self.stats.values())
