"""Citation verification.

The guardrail that decides whether a citation means anything, so it is tested
exhaustively — pure functions over strings, no model, no database.
"""

from uuid import UUID

from app.core.grounding import (
    build_citations,
    extract_markers,
    ground,
    is_unsupported,
    strip_invalid_markers,
)
from app.models.retrieval import ScoredChunk
from app.models.transcript import TimeRange


def hit(index: int) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=UUID(int=index),
        meeting_id=UUID(int=100 + index),
        meeting_title=f"meeting {index}",
        chunk_index=index,
        text=f"content of excerpt {index}",
        time=TimeRange(start_ms=index * 1000, end_ms=(index + 1) * 1000),
        speakers=[f"Speaker {index}"],
        score=1.0,
    )


HITS = [hit(1), hit(2), hit(3)]


class TestExtraction:
    def test_finds_markers_in_order(self):
        assert extract_markers("first [2] then [1] and [2] again") == [2, 1, 2]

    def test_no_markers_is_an_empty_list(self):
        assert extract_markers("an answer with no citations") == []

    def test_ignores_bracketed_text_that_is_not_a_number(self):
        assert extract_markers("[see also] and [note]") == []


class TestStripping:
    def test_valid_markers_survive(self):
        text, dropped = strip_invalid_markers("supported [1] and [3]", 3)
        assert text == "supported [1] and [3]"
        assert dropped == []

    def test_out_of_range_markers_are_removed(self):
        """The model cannot cite an excerpt it was never given."""
        text, dropped = strip_invalid_markers("real [1] invented [9]", 3)
        assert "[9]" not in text
        assert "[1]" in text
        assert dropped == [9]

    def test_zero_is_not_a_valid_marker(self):
        _, dropped = strip_invalid_markers("bad [0]", 3)
        assert dropped == [0]

    def test_removal_does_not_leave_a_space_before_punctuation(self):
        text, _ = strip_invalid_markers("a claim [9].", 3)
        assert text == "a claim."

    def test_removal_does_not_leave_a_double_space(self):
        text, _ = strip_invalid_markers("before [9] after", 3)
        assert text == "before after"

    def test_every_marker_dropped_when_nothing_was_supplied(self):
        text, dropped = strip_invalid_markers("cites [1] and [2]", 0)
        assert dropped == [1, 2]
        assert "[" not in text


class TestCitations:
    def test_built_only_for_markers_used(self):
        """An evidence panel listing everything retrieved teaches nothing."""
        citations = build_citations("only [2] is cited", HITS)
        assert [c.marker for c in citations] == [2]
        assert citations[0].chunk_id == HITS[1].chunk_id

    def test_ordered_by_first_appearance(self):
        citations = build_citations("[3] then [1] then [3]", HITS)
        assert [c.marker for c in citations] == [3, 1]

    def test_repeated_markers_appear_once(self):
        assert len(build_citations("[1] [1] [1]", HITS)) == 1

    def test_carries_what_the_evidence_panel_renders(self):
        citation = build_citations("[2]", HITS)[0]
        assert citation.meeting_title == "meeting 2"
        assert citation.speakers == ["Speaker 2"]
        assert citation.quote == "content of excerpt 2"

    def test_no_citations_without_markers(self):
        assert build_citations("no markers here", HITS) == []


class TestGround:
    def test_strips_then_builds_so_dropped_markers_cannot_leak(self):
        """Ordering matters: a citation must never be built from a removed marker."""
        text, citations, dropped = ground("real [1], invented [7]", HITS)

        assert dropped == [7]
        assert [c.marker for c in citations] == [1]
        assert "[7]" not in text

    def test_an_answer_with_no_evidence_available(self):
        text, citations, dropped = ground("I could not find that.", [])
        assert citations == []
        assert dropped == []
        assert text == "I could not find that."


class TestUnsupportedDetection:
    def test_a_long_uncited_answer_is_flagged(self):
        """With excerpts supplied, no citations means general knowledge or invention."""
        assert is_unsupported("x" * 250, HITS)

    def test_a_cited_answer_is_not_flagged(self):
        assert not is_unsupported("x" * 250 + " [1]", HITS)

    def test_a_short_answer_is_exempt(self):
        """A refusal legitimately cites nothing."""
        assert not is_unsupported("Not in the transcripts.", HITS)

    def test_nothing_to_support_when_no_excerpts_were_retrieved(self):
        assert not is_unsupported("x" * 250, [])
