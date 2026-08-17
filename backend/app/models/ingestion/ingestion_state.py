"""The checkpointed state, and the two functions that belong to it.

`merge_stats` is the reducer for the `stats` field and `new_ingestion_state` is
its constructor, so both live here rather than next door: a `TypedDict`'s reducer
is part of its definition. The rules the shape obeys are in this package's
`__init__.py`.
"""

import operator
from typing import Annotated, TypedDict
from uuid import UUID

from app.models.ingestion.source_reference import SourceReference
from app.models.ingestion.stage import Stage
from app.models.ingestion.stage_error import StageError
from app.models.ingestion.stage_stats import StageStats
from app.models.transcript.transcript_format import TranscriptFormat


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
