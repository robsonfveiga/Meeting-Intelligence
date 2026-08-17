"""Fusing two ranked lists into one.

Vector similarity and keyword relevance produce scores on **incomparable
scales**: cosine distance lives in [0, 2] and clusters tightly around the middle
for conversational text, while `ts_rank_cd` is unbounded and depends on document
length and term frequency. Normalising them into a shared scale means estimating
each distribution, which changes as the corpus grows.

Reciprocal Rank Fusion sidesteps that entirely by discarding the scores and
using only **rank order**:

    score(chunk) = Σ  weight / (k + rank)

`k` damps the influence of top positions so one strategy cannot dominate on a
single confident hit — 60 is the constant from the original paper, and the value
is not sensitive.

The whole module is pure functions over lists of identifiers. No database, no
embedding call. That is deliberate: this is the code most likely to hide a subtle
bug and the code that gets tuned most, so it has to be measurable in
milliseconds with handwritten inputs.
"""

from uuid import UUID

from app.models.retrieval import FusedHit, SearchHit

RRF_K = 60


def reciprocal_rank_fusion(
    rankings: dict[str, list[SearchHit]],
    *,
    k: int = RRF_K,
    weights: dict[str, float] | None = None,
) -> list[FusedHit]:
    """Merge ranked lists from several strategies into one ordering.

    `rankings` maps a strategy name to its results, best first. Each strategy
    contributes independently, so a chunk found by both rises above one found
    strongly by only one — which is the entire point of running both.
    """
    weights = weights or {}
    scores: dict[UUID, float] = {}
    positions: dict[UUID, dict[str, int]] = {}

    for strategy, hits in rankings.items():
        weight = weights.get(strategy, 1.0)
        for rank, hit in enumerate(hits, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + weight / (k + rank)
            positions.setdefault(hit.chunk_id, {})[strategy] = rank

    ordered = sorted(scores.items(), key=lambda item: (-item[1], str(item[0])))
    return [
        FusedHit(chunk_id=chunk_id, score=score, ranks=positions[chunk_id])
        for chunk_id, score in ordered
    ]


def neighbour_ids(hit_indexes: list[int], *, total: int, radius: int = 1) -> list[int]:
    """Chunk indexes adjacent to the hits, excluding the hits themselves.

    Small-to-big retrieval: chunks are deliberately small so their embeddings
    stay specific, which costs surrounding context. Widening at read time
    recovers the context without diluting what was indexed — the alternative,
    indexing larger chunks, was measured and made retrieval worse.
    """
    hits = set(hit_indexes)
    wanted: set[int] = set()
    for index in hit_indexes:
        for offset in range(-radius, radius + 1):
            neighbour = index + offset
            if 0 <= neighbour < total and neighbour not in hits:
                wanted.add(neighbour)
    return sorted(wanted)
