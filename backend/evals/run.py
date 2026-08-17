"""Measure retrieval, with no model judging anything.

Every metric here is deterministic: same corpus and same questions give the same
numbers, and a change in the score means a change in the system rather than a
change of mood in a grader. That matters because these numbers are what tuning
decisions get made on.

Deliberately no LLM-as-judge. Judging *answers* needs one; judging *retrieval*
does not, and introducing model variance into the one signal that should be
stable would be a bad trade.

    make eval

Reports recall@k and mean reciprocal rank for each strategy separately and
fused, so "hybrid is better" is a measurement rather than a claim.
"""

import asyncio
from dataclasses import dataclass, field

from app.clients.llm import embed_texts, embeddings_available
from app.config import get_settings
from app.core.ranking import reciprocal_rank_fusion
from app.db import chunks as chunks_db
from app.db import meetings as meetings_db
from app.db.engine import dispose_engine, transaction
from app.models.retrieval import SearchHit
from evals.golden import GOLDEN_SET, GoldenQuestion

CANDIDATES = 20
CUTOFFS = (1, 3, 5, 10)


@dataclass
class Outcome:
    question: GoldenQuestion
    first_relevant_rank: int | None


@dataclass
class Report:
    strategy: str
    outcomes: list[Outcome] = field(default_factory=list)

    def recall_at(self, k: int) -> float:
        found = sum(
            1
            for o in self.outcomes
            if o.first_relevant_rank is not None and o.first_relevant_rank <= k
        )
        return found / len(self.outcomes) if self.outcomes else 0.0

    @property
    def mrr(self) -> float:
        """Mean reciprocal rank — rewards putting the answer first, not just in the list."""
        total = sum(1 / o.first_relevant_rank for o in self.outcomes if o.first_relevant_rank)
        return total / len(self.outcomes) if self.outcomes else 0.0


async def _rank_of_first_relevant(
    hits: list[SearchHit], question: GoldenQuestion, lookup: dict
) -> int | None:
    for position, hit in enumerate(hits, start=1):
        chunk, title = lookup.get(hit.chunk_id, (None, ""))
        if chunk and question.is_relevant(title, chunk.text):
            return position
    return None


async def main() -> None:
    async with transaction() as conn:
        meetings = {m.id: m.title for m in await meetings_db.list_all(conn)}
        if not meetings:
            print("No meetings ingested. Run `make seed` first.")
            return

    reports = {name: Report(name) for name in ("keyword", "vector", "hybrid")}
    has_vectors = embeddings_available()

    for question in GOLDEN_SET:
        vector_query = (await embed_texts([question.question])).vectors[0] if has_vectors else None

        async with transaction() as conn:
            keyword = await chunks_db.search_by_text(conn, question.question, limit=CANDIDATES)
            vector = (
                await chunks_db.search_by_vector(conn, vector_query, limit=CANDIDATES)
                if vector_query is not None
                else []
            )
            ids = {h.chunk_id for h in keyword} | {h.chunk_id for h in vector}
            chunks = await chunks_db.get_many(conn, list(ids))

        lookup = {cid: (c, meetings.get(c.meeting_id, "")) for cid, c in chunks.items()}

        rankings = {"keyword": keyword}
        if vector:
            rankings["vector"] = vector
        # Use the configured weights, so the reported hybrid row is the system
        # that actually ships rather than an unweighted variant of it.
        fused = reciprocal_rank_fusion(
            rankings,
            weights={
                "keyword": get_settings().retrieval_keyword_weight,
                "vector": get_settings().retrieval_vector_weight,
            },
        )
        fused_hits = [
            SearchHit(chunk_id=f.chunk_id, score=f.score, rank=i) for i, f in enumerate(fused, 1)
        ]

        for name, hits in (("keyword", keyword), ("vector", vector), ("hybrid", fused_hits)):
            reports[name].outcomes.append(
                Outcome(question, await _rank_of_first_relevant(hits, question, lookup))
            )

    _print(reports, has_vectors)
    await dispose_engine()


def _print(reports: dict[str, Report], has_vectors: bool) -> None:
    if not has_vectors:
        print("\n!! OPENAI_API_KEY is not set — vector and hybrid rows are keyword only.\n")

    header = "strategy   " + "".join(f"  recall@{k:<3}" for k in CUTOFFS) + "     MRR"
    print(f"\n{header}")
    print("-" * len(header))
    for name in ("keyword", "vector", "hybrid"):
        report = reports[name]
        cells = "".join(f"  {report.recall_at(k):>9.2f}" for k in CUTOFFS)
        print(f"{name:<11}{cells}  {report.mrr:>6.2f}")

    print("\nby category (hybrid, recall@5)")
    print("-" * 34)
    hybrid = reports["hybrid"]
    categories = sorted({o.question.category for o in hybrid.outcomes})
    for category in categories:
        subset = [o for o in hybrid.outcomes if o.question.category == category]
        hit = sum(1 for o in subset if o.first_relevant_rank and o.first_relevant_rank <= 5)
        print(f"{category:<16} {hit}/{len(subset)}")

    missed = [o for o in hybrid.outcomes if o.first_relevant_rank is None]
    if missed:
        print(f"\nnot found at all ({len(missed)}):")
        for outcome in missed:
            print(f"  [{outcome.question.category}] {outcome.question.question}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
