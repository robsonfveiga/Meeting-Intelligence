"""Tests for the state reducers.

These guard the failure mode flagged when the state was designed: a field that
should accumulate but replaces instead. `stats` is the dangerous one — losing
it is silent, and you only find out much later when the cost numbers are wrong.
"""

from app.models.enums import Stage
from app.models.state import (
    IngestionState,
    SourceReference,
    StageError,
    StageStats,
    merge_stats,
    new_ingestion_state,
)


def test_merge_stats_keeps_both_stages():
    left = {"parse": StageStats(duration_ms=10)}
    right = {"embed": StageStats(duration_ms=20)}

    merged = merge_stats(left, right)

    assert set(merged) == {"parse", "embed"}
    assert merged["parse"].duration_ms == 10
    assert merged["embed"].duration_ms == 20


def test_merge_stats_later_stage_wins_on_conflict():
    merged = merge_stats(
        {"embed": StageStats(duration_ms=10)},
        {"embed": StageStats(duration_ms=99)},
    )
    assert merged["embed"].duration_ms == 99


def test_annotated_fields_are_the_ones_that_accumulate():
    """The declaration itself is the contract, so assert on it directly."""
    hints = IngestionState.__annotations__
    accumulating = {"chunk_ids", "errors", "stats"}

    for field in accumulating:
        assert "Annotated" in str(hints[field]), f"{field} must declare a reducer"

    for field in ("stage", "meeting_id", "turn_count"):
        assert "Annotated" not in str(hints[field]), f"{field} should replace, not accumulate"


def test_new_state_starts_empty_and_received():
    state = new_ingestion_state(
        "job-1",
        SourceReference(filename="a.txt", size_bytes=1, storage_path="/tmp/a.txt"),
    )

    assert state["stage"] is Stage.RECEIVED
    assert state["chunk_ids"] == []
    assert state["errors"] == []
    assert state["stats"] == {}


def test_state_carries_no_payload_fields():
    """Identifiers, never payloads — the rule that keeps checkpoints small."""
    forbidden = {"chunks", "turns", "embeddings", "text", "transcript"}
    assert forbidden.isdisjoint(IngestionState.__annotations__)


def test_stage_error_defaults_to_unrecoverable():
    assert StageError(stage="embed", message="boom").recoverable is False
