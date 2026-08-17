"""Extraction, without a provider.

Everything worth asserting about extraction is a shape property — a window that
loses a turn, a fact pointing at a turn that was never sent, the same decision
stored twice. All of it reproduces from a list of turns, so none of it needs a
model call.
"""

from uuid import uuid4

from app.core.extraction import (
    build_windows,
    deduplicate,
    parse_facts,
    to_facts,
    verify_evidence,
)
from app.models.fact.extracted_fact import ExtractedFact
from app.models.fact.fact import Fact
from app.models.fact.fact_kind import FactKind
from app.models.transcript.time_range import TimeRange
from app.models.transcript.turn import Turn

MEETING = uuid4()


def turn(index: int, speaker: str = "Priya Raman", text: str = "Some words.") -> Turn:
    return Turn(
        meeting_id=MEETING,
        index=index,
        speaker=speaker,
        time=TimeRange(start_ms=index * 1000, end_ms=(index + 1) * 1000),
        text=text,
    )


def extracted(
    kind: FactKind = FactKind.DECISION,
    statement: str = "Pricing was held until after launch.",
    start: int = 0,
    end: int = 1,
    **rest: str | None,
) -> ExtractedFact:
    return ExtractedFact(
        kind=kind,
        statement=statement,
        start_turn_index=start,
        end_turn_index=end,
        **rest,  # type: ignore[arg-type]
    )


class TestWindows:
    def test_no_turns_means_no_calls(self):
        assert build_windows([], max_chars=100) == []

    def test_a_short_meeting_is_one_window(self):
        windows = build_windows([turn(i) for i in range(3)], max_chars=6000)
        assert len(windows) == 1
        assert [t.index for t in windows[0]] == [0, 1, 2]

    def test_every_turn_appears_exactly_once(self):
        """Disjoint, unlike retrieval chunks: overlap would manufacture duplicates."""
        turns = [turn(i, text="x" * 90) for i in range(20)]
        windows = build_windows(turns, max_chars=300)

        seen = [t.index for window in windows for t in window]
        assert seen == list(range(20))

    def test_a_turn_is_never_split_even_when_it_exceeds_the_budget(self):
        """Losing half a monologue is worse than one oversized request."""
        turns = [turn(0, text="x" * 50), turn(1, text="y" * 5000)]
        windows = build_windows(turns, max_chars=200)

        assert [len(window) for window in windows] == [1, 1]
        assert len(windows[1][0].text) == 5000


class TestEvidenceVerification:
    def test_a_reference_inside_the_window_survives(self):
        window = [turn(0), turn(1), turn(2)]
        kept, rejected = verify_evidence([extracted(start=1, end=2)], window)

        assert len(kept) == 1
        assert rejected == []

    def test_a_reference_outside_the_window_is_rejected(self):
        """The whole guardrail: the model cannot cite turns it was never shown."""
        window = [turn(0), turn(1)]
        kept, rejected = verify_evidence([extracted(start=0, end=9)], window)

        assert kept == []
        assert len(rejected) == 1

    def test_an_inverted_range_is_rejected(self):
        window = [turn(0), turn(1), turn(2)]
        kept, _ = verify_evidence([extracted(start=2, end=0)], window)
        assert kept == []

    def test_a_gap_in_the_window_is_not_citable(self):
        """Windows are contiguous, so a reference spanning one is a hallucinated range."""
        window = [turn(0), turn(5)]
        kept, rejected = verify_evidence([extracted(start=0, end=3)], window)

        assert kept == []
        assert len(rejected) == 1

    def test_rejections_are_returned_rather_than_dropped(self):
        window = [turn(0)]
        _, rejected = verify_evidence(
            [extracted(start=0, end=0), extracted(start=7, end=8)], window
        )
        assert [f.start_turn_index for f in rejected] == [7]


class TestHydration:
    def test_speakers_and_times_come_from_the_turns_not_the_model(self):
        window = [turn(0, "Priya Raman"), turn(1, "Tom Beckett"), turn(2, "Priya Raman")]
        facts = to_facts([extracted(start=0, end=2)], meeting_id=MEETING, window=window)

        assert facts[0].speakers == ["Priya Raman", "Tom Beckett"]
        assert facts[0].time.start_ms == 0
        assert facts[0].time.end_ms == 3000

    def test_owner_and_due_survive_on_a_commitment(self):
        window = [turn(0), turn(1)]
        facts = to_facts(
            [extracted(kind=FactKind.COMMITMENT, owner="Tom Beckett", due="Friday")],
            meeting_id=MEETING,
            window=window,
        )

        assert facts[0].owner == "Tom Beckett"
        assert facts[0].due == "Friday"

    def test_owner_is_cleared_on_kinds_that_cannot_have_one(self):
        """Otherwise a decision arrives with an assignee because every field got filled."""
        window = [turn(0), turn(1)]
        facts = to_facts(
            [extracted(kind=FactKind.DECISION, owner="Tom Beckett", due="Friday")],
            meeting_id=MEETING,
            window=window,
        )

        assert facts[0].owner is None
        assert facts[0].due is None


class TestParsing:
    def test_a_well_formed_payload_parses(self):
        payload = {
            "facts": [
                {
                    "kind": "commitment",
                    "statement": "Tom will draft the migration plan.",
                    "owner": "Tom Beckett",
                    "due": None,
                    "start_turn_index": 4,
                    "end_turn_index": 4,
                }
            ]
        }
        assert parse_facts(payload)[0].kind is FactKind.COMMITMENT

    def test_an_empty_payload_is_a_valid_answer(self):
        assert parse_facts({"facts": []}) == []
        assert parse_facts({}) == []

    def test_one_malformed_entry_does_not_lose_the_others(self):
        payload = {
            "facts": [
                {
                    "kind": "not_a_kind",
                    "statement": "x",
                    "start_turn_index": 0,
                    "end_turn_index": 0,
                },
                {"kind": "decision", "statement": "y", "start_turn_index": 1, "end_turn_index": 1},
            ]
        }
        parsed = parse_facts(payload)
        assert [f.statement for f in parsed] == ["y"]


def fact(statement: str, start: int, end: int, kind: FactKind = FactKind.DECISION) -> Fact:
    return Fact(
        meeting_id=MEETING,
        kind=kind,
        statement=statement,
        start_turn_index=start,
        end_turn_index=end,
        time=TimeRange(start_ms=start * 1000, end_ms=end * 1000),
        speakers=["Priya Raman"],
    )


class TestDeduplication:
    def test_the_same_decision_restated_collapses_to_one(self):
        merged = deduplicate(
            [
                fact("Pricing is held until launch.", 2, 8),
                fact("Pricing is held until launch.", 40, 41),
            ]
        )
        assert len(merged) == 1

    def test_the_tightest_evidence_wins(self):
        """Two turns is where the decision was made; six is where it was recapped."""
        merged = deduplicate([fact("Pricing is held.", 2, 8), fact("Pricing is held.", 40, 41)])
        assert (merged[0].start_turn_index, merged[0].end_turn_index) == (40, 41)

    def test_punctuation_and_case_do_not_make_two_facts(self):
        merged = deduplicate([fact("Pricing is held.", 1, 2), fact("pricing is held", 5, 6)])
        assert len(merged) == 1

    def test_the_same_wording_under_two_kinds_stays_separate(self):
        merged = deduplicate(
            [
                fact("Ship the migration.", 1, 2, FactKind.DECISION),
                fact("Ship the migration.", 1, 2, FactKind.COMMITMENT),
            ]
        )
        assert len(merged) == 2

    def test_output_reads_in_transcript_order(self):
        merged = deduplicate([fact("b", 9, 9), fact("a", 1, 1)])
        assert [f.statement for f in merged] == ["a", "b"]
