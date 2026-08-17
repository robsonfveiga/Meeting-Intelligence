from pydantic import BaseModel

from app.models.fact.fact_kind import FactKind


class ExtractedFact(BaseModel):
    """One claim as the model returned it, before anything is trusted.

    `start_turn_index` and `end_turn_index` are the whole guardrail. A fact that
    cannot point at a stretch of transcript is not admissible, and one that points
    outside the window it was extracted from is discarded — the same mechanical
    check `grounding.py` runs on citation markers.
    """

    kind: FactKind
    statement: str
    # Present on commitments, absent on the other kinds. Free text on purpose:
    # "end of the week" is what people say, and normalising it into a date would
    # mean inventing a precision the transcript does not contain.
    owner: str | None = None
    due: str | None = None
    start_turn_index: int
    end_turn_index: int

    @property
    def turn_span(self) -> int:
        return self.end_turn_index - self.start_turn_index
