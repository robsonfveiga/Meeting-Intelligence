from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.models.fact.fact_kind import FactKind
from app.models.transcript.time_range import TimeRange


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
