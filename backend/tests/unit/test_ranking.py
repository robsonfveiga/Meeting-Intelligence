"""Fusion behaviour.

Pure functions over lists of identifiers, so these run with no database, no
embedding call and no corpus. That is what makes it practical to test the
ranking algorithm exhaustively — it is the code most likely to hide a subtle
bug and the code that gets tuned most.
"""

from uuid import UUID, uuid4

from app.core.ranking import RRF_K, neighbour_ids, reciprocal_rank_fusion
from app.models.retrieval import SearchHit

A, B, C, D = (UUID(int=i) for i in range(1, 5))


def ranked(*chunk_ids: UUID) -> list[SearchHit]:
    return [
        SearchHit(chunk_id=cid, score=1.0 / rank, rank=rank)
        for rank, cid in enumerate(chunk_ids, start=1)
    ]


class TestFusion:
    def test_no_rankings_produces_nothing(self):
        assert reciprocal_rank_fusion({}) == []

    def test_a_single_ranking_passes_through_in_order(self):
        fused = reciprocal_rank_fusion({"vector": ranked(A, B, C)})
        assert [f.chunk_id for f in fused] == [A, B, C]

    def test_agreement_beats_a_single_strong_hit(self):
        """The entire reason for running two strategies.

        C is second in both lists; A is first in one and absent from the other.
        Two moderate votes should outrank one confident one.
        """
        fused = reciprocal_rank_fusion({"vector": ranked(A, C), "keyword": ranked(B, C)})
        assert fused[0].chunk_id == C

    def test_scores_are_ignored_only_ranks_count(self):
        """Vector distance and ts_rank are on incomparable scales, so RRF drops them."""
        modest = [SearchHit(chunk_id=A, score=0.01, rank=1)]
        huge = [SearchHit(chunk_id=B, score=999.0, rank=1)]

        fused = reciprocal_rank_fusion({"x": modest, "y": huge})
        assert fused[0].score == fused[1].score

    def test_records_which_strategy_ranked_what(self):
        """Feeds the "how was this found" panel: rank 1 and 40 tells a story."""
        fused = reciprocal_rank_fusion({"vector": ranked(A, B), "keyword": ranked(B, A)})
        by_id = {f.chunk_id: f.ranks for f in fused}

        assert by_id[A] == {"vector": 1, "keyword": 2}
        assert by_id[B] == {"vector": 2, "keyword": 1}

    def test_a_chunk_found_by_one_strategy_still_appears(self):
        fused = reciprocal_rank_fusion({"vector": ranked(A), "keyword": ranked(B)})
        assert {f.chunk_id for f in fused} == {A, B}

    def test_score_matches_the_formula(self):
        fused = reciprocal_rank_fusion({"vector": ranked(A, B)})
        assert fused[0].score == 1 / (RRF_K + 1)
        assert fused[1].score == 1 / (RRF_K + 2)

    def test_ordering_is_deterministic_when_scores_tie(self):
        """Same inputs must give the same output, or evaluation numbers drift."""
        rankings = {"vector": ranked(A, B), "keyword": ranked(B, A)}
        first = [f.chunk_id for f in reciprocal_rank_fusion(rankings)]
        assert first == [f.chunk_id for f in reciprocal_rank_fusion(rankings)]


class TestWeights:
    def test_zero_weight_removes_a_strategy_from_the_outcome(self):
        fused = reciprocal_rank_fusion(
            {"vector": ranked(A), "keyword": ranked(B)},
            weights={"keyword": 0.0, "vector": 1.0},
        )
        assert fused[0].chunk_id == A
        assert fused[1].score == 0.0

    def test_a_heavier_strategy_wins_a_disagreement(self):
        fused = reciprocal_rank_fusion(
            {"vector": ranked(A), "keyword": ranked(B)},
            weights={"keyword": 2.0, "vector": 1.0},
        )
        assert fused[0].chunk_id == B

    def test_unlisted_strategies_default_to_full_weight(self):
        fused = reciprocal_rank_fusion({"vector": ranked(A)}, weights={"keyword": 0.5})
        assert fused[0].score == 1 / (RRF_K + 1)


class TestNeighbourExpansion:
    def test_returns_the_chunks_either_side(self):
        assert neighbour_ids([5], total=10) == [4, 6]

    def test_never_returns_the_hits_themselves(self):
        """The window adds context; it must not duplicate what was already returned."""
        assert neighbour_ids([4, 5], total=10) == [3, 6]

    def test_clamps_at_the_start_and_end_of_a_meeting(self):
        assert neighbour_ids([0], total=3) == [1]
        assert neighbour_ids([2], total=3) == [1]

    def test_a_single_chunk_meeting_has_no_neighbours(self):
        assert neighbour_ids([0], total=1) == []

    def test_radius_widens_the_window(self):
        assert neighbour_ids([5], total=10, radius=2) == [3, 4, 6, 7]

    def test_overlapping_windows_are_not_duplicated(self):
        assert neighbour_ids([2, 4], total=10) == [1, 3, 5]


def test_fusion_handles_a_realistic_volume():
    """Twenty candidates per strategy is the production default."""
    left = ranked(*(uuid4() for _ in range(20)))
    right = ranked(*(uuid4() for _ in range(20)))

    fused = reciprocal_rank_fusion({"vector": left, "keyword": right})
    assert len(fused) == 40
    assert fused == sorted(fused, key=lambda f: -f.score)
