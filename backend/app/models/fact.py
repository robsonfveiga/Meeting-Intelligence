"""Extracted-fact vocabulary.

Two models rather than one, for the same reason `ParsedTurn` and `Turn` are
separate: the model that reads a transcript can supply a statement and the turns
it came from, but it cannot supply a meeting identifier, a time range or a
speaker list. A single model with those fields required would be a lie about what
the extractor produces; a single model with them optional would push the question
"is this hydrated yet?" into every caller.

So `ExtractedFact` is what comes back from the provider — a claim plus the turn
indices it rests on — and `Fact` is what is stored, after those indices have been
checked against the turns we actually supplied and resolved into real speakers
and timestamps.
"""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.models.enums import FactKind
from app.models.transcript import TimeRange


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


class Fact(BaseModel):
    """A verified fact, with the evidence behind it resolved.

    `speakers` and `time` are derived from the turns the fact cites, never from
    the model — so the attribution on a decision is as reliable as the transcript
    itself, whatever the extractor claimed.
    """

    id: UUID = Field(default_factory=uuid4)
    meeting_id: UUID
    kind: FactKind
    statement: str
    owner: str | None = None
    due: str | None = None
    start_turn_index: int
    end_turn_index: int
    time: TimeRange
    speakers: list[str] = Field(default_factory=list)
    created_at: datetime | None = None

    @property
    def turn_span(self) -> int:
        return self.end_turn_index - self.start_turn_index
