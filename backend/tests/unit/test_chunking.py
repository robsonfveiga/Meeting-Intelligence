"""Chunking behaviour.

The properties that matter are structural: turns are never split, speakers are
preserved, and consecutive chunks overlap. Those are what make a retrieved chunk
citable and stop an answer being orphaned across a boundary.
"""

from itertools import pairwise
from uuid import uuid4

from app.core.chunking import build_context_header, chunk_turns
from app.models.transcript.time_range import TimeRange
from app.models.transcript.turn import Turn

MEETING = uuid4()


def make_turns(count: int, words: int = 20, speakers: tuple[str, ...] = ("Alice", "Bob")):
    return [
        Turn(
            meeting_id=MEETING,
            index=i,
            speaker=speakers[i % len(speakers)],
            time=TimeRange(start_ms=i * 5000, end_ms=(i + 1) * 5000),
            text=" ".join([f"word{i}"] * words),
        )
        for i in range(count)
    ]


class TestStructure:
    def test_no_turns_produces_no_chunks(self):
        assert chunk_turns([]) == []

    def test_a_short_meeting_is_a_single_chunk(self):
        chunks = chunk_turns(make_turns(3, words=5))
        assert len(chunks) == 1
        assert chunks[0].start_turn_index == 0
        assert chunks[0].end_turn_index == 2

    def test_every_turn_appears_in_at_least_one_chunk(self):
        """The property that matters most — losing a turn loses an answer."""
        turns = make_turns(40)
        chunks = chunk_turns(turns)

        covered = set()
        for chunk in chunks:
            covered.update(range(chunk.start_turn_index, chunk.end_turn_index + 1))

        assert covered == {t.index for t in turns}

    def test_turns_are_never_split(self):
        turns = make_turns(30)
        for chunk in chunk_turns(turns):
            for index in range(chunk.start_turn_index, chunk.end_turn_index + 1):
                assert turns[index].text in chunk.text

    def test_chunk_indexes_are_contiguous_from_zero(self):
        chunks = chunk_turns(make_turns(40))
        assert [c.index for c in chunks] == list(range(len(chunks)))


class TestOverlap:
    def test_consecutive_chunks_share_a_turn(self):
        chunks = chunk_turns(make_turns(40), overlap_turns=1)
        assert len(chunks) > 1
        for earlier, later in pairwise(chunks):
            assert later.start_turn_index <= earlier.end_turn_index

    def test_overlap_can_be_turned_off(self):
        chunks = chunk_turns(make_turns(40), overlap_turns=0)
        for earlier, later in pairwise(chunks):
            assert later.start_turn_index == earlier.end_turn_index + 1


class TestMetadata:
    def test_speakers_are_recorded_distinctly(self):
        chunk = chunk_turns(make_turns(4, words=5))[0]
        assert sorted(chunk.speakers) == ["Alice", "Bob"]

    def test_time_range_spans_the_included_turns(self):
        chunks = chunk_turns(make_turns(4, words=5))
        assert chunks[0].time.start_ms == 0
        assert chunks[0].time.end_ms == 20_000

    def test_speaker_labels_stay_in_the_embedded_text(self):
        """Who said it is part of the meaning, not metadata to strip."""
        assert "Alice:" in chunk_turns(make_turns(2, words=5))[0].text


class TestOversizedTurns:
    def test_a_monologue_longer_than_a_chunk_is_split(self):
        long_turn = Turn(
            meeting_id=MEETING,
            index=0,
            speaker="Alice",
            time=TimeRange(start_ms=0, end_ms=600_000),
            text=". ".join(["This is a sentence that goes on"] * 200),
        )
        chunks = chunk_turns([long_turn], max_chars=500)

        assert len(chunks) > 1
        assert all(len(c.text) <= 700 for c in chunks)

    def test_a_single_unbroken_sentence_is_still_cut(self):
        """No sentence boundary to use, but the embedding limit is still real."""
        turn = Turn(
            meeting_id=MEETING,
            index=0,
            speaker="Alice",
            time=TimeRange(start_ms=0, end_ms=1000),
            text="x" * 5000,
        )
        chunks = chunk_turns([turn], max_chars=500)
        assert len(chunks) > 1


class TestContextHeader:
    def test_names_the_meeting_speakers_and_position(self):
        chunk = chunk_turns(make_turns(4, words=5))[0]
        header = build_context_header("Q3 planning", chunk, total_duration_ms=600_000)

        assert "Q3 planning" in header
        assert "Alice" in header

    def test_position_moves_through_the_meeting(self):
        turns = make_turns(60, words=30)
        chunks = chunk_turns(turns)
        duration = turns[-1].time.end_ms

        first = build_context_header("Retro", chunks[0], duration)
        last = build_context_header("Retro", chunks[-1], duration)
        assert first != last

    def test_zero_duration_does_not_divide_by_zero(self):
        chunk = chunk_turns(make_turns(2, words=5))[0]
        assert build_context_header("Untimed", chunk, total_duration_ms=0)

    def test_header_is_prepended_to_the_embedded_text(self):
        chunk = chunk_turns(make_turns(2, words=5))[0]
        chunk.context_header = "From the opening of 'Retro'."

        assert chunk.embedding_input.startswith("From the opening of 'Retro'.")
        assert chunk.text in chunk.embedding_input
