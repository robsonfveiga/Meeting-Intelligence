"""The golden set: questions with known answers.

**Relevance is judged by content, not by chunk identifier.** Chunk identifiers
change on every re-ingest and shift whenever chunk size is tuned — which is
exactly the parameter this set exists to tune. So a hit counts as relevant when
it comes from the expected meeting *and* contains the expected phrase. That
judgement is stable across re-chunking, which is the whole point.

Written by hand against the seed corpus, and deliberately mixed:

- **semantic** — paraphrased questions sharing no vocabulary with the answer;
  dense retrieval should carry these
- **lexical** — exact figures and proper nouns; keyword should carry these, and
  they are the reason the system is hybrid rather than vector-only
- **cross-meeting** — the answer sits in a different meeting from where the
  topic started
- **aggregate** — questions no top-k retrieval can answer completely. Kept in
  and expected to score badly, because that failure is the argument for the
  structured extraction pass in slice 4. Removing them would flatter the numbers.
"""

from typing import Literal

from pydantic import BaseModel

Category = Literal["semantic", "lexical", "cross-meeting", "aggregate"]


class GoldenQuestion(BaseModel):
    question: str
    meeting: str
    phrase: str
    category: Category

    def is_relevant(self, meeting_title: str, text: str) -> bool:
        return meeting_title.lower() == self.meeting.lower() and self.phrase.lower() in text.lower()


GOLDEN_SET: list[GoldenQuestion] = [
    # ---- semantic: no shared vocabulary with the answer ----
    GoldenQuestion(
        question="how long did the rollback actually take?",
        meeting="migration retro",
        phrase="four hours",
        category="semantic",
    ),
    GoldenQuestion(
        question="why was raising prices considered risky?",
        meeting="pricing review",
        phrase="four points worse",
        category="semantic",
    ),
    GoldenQuestion(
        question="what went wrong with how the migration was tested?",
        meeting="migration retro",
        phrase="twentieth of the data",
        category="semantic",
    ),
    GoldenQuestion(
        question="was anyone unable to tell if the job was progressing?",
        meeting="migration retro",
        phrase="progressing or stuck",
        category="semantic",
    ),
    GoldenQuestion(
        question="did customers get told about the price hold?",
        meeting="sprint planning",
        phrase="told two customers",
        category="semantic",
    ),
    # ---- lexical: exact figures and names that embeddings blur ----
    GoldenQuestion(
        question="eleven thousand a year",
        meeting="exec sync",
        phrase="eleven thousand",
        category="lexical",
    ),
    GoldenQuestion(
        question="bug count thirty-one to nine",
        meeting="migration retro",
        phrase="thirty-one to nine",
        category="lexical",
    ),
    GoldenQuestion(
        question="fourteen points of migration cleanup",
        meeting="sprint planning",
        phrase="fourteen points",
        category="lexical",
    ),
    GoldenQuestion(
        question="rollback tooling",
        meeting="sprint planning",
        phrase="rollback tooling",
        category="lexical",
    ),
    # ---- cross-meeting: topic starts elsewhere, answer lives here ----
    GoldenQuestion(
        question="what did Priya commit to delivering?",
        meeting="pricing review",
        phrase="churn analysis",
        category="cross-meeting",
    ),
    GoldenQuestion(
        question="did the churn analysis ever actually go out?",
        meeting="exec sync",
        phrase="went out last Thursday",
        category="cross-meeting",
    ),
    GoldenQuestion(
        question="was the pricing decision reopened later?",
        meeting="exec sync",
        phrase="stays flat through launch",
        category="cross-meeting",
    ),
    GoldenQuestion(
        question="what happened to the annual tier accounts after the migration?",
        meeting="exec sync",
        phrase="damaged trust",
        category="cross-meeting",
    ),
    # ---- aggregate: retrieval cannot answer these completely, by design ----
    GoldenQuestion(
        question="what is everyone's outstanding action item?",
        meeting="exec sync",
        phrase="account-level churn split",
        category="aggregate",
    ),
    GoldenQuestion(
        question="list every decision made across all meetings",
        meeting="sprint planning",
        phrase="Decision: rollback tooling",
        category="aggregate",
    ),
]
