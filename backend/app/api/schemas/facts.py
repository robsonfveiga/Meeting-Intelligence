"""Fact wire shapes.

A schema rather than returning `Fact` directly, because the wire shape genuinely
differs: the interesting view is cross-meeting — every open commitment in the
series, not one hour's worth — and a list of statements without their meeting is
unreadable. So `meeting_title` is denormalised onto the response, the same
argument that put it on `ScoredChunk` and `AnswerCitation`.

The title is joined once per request rather than once per row, so this costs one
extra query regardless of how many facts come back.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import FactKind
from app.models.fact import Fact
from app.models.transcript import TimeRange


class FactResponse(BaseModel):
    id: UUID
    meeting_id: UUID
    meeting_title: str
    kind: FactKind
    statement: str
    owner: str | None = None
    due: str | None = None
    # The evidence, in the two forms an interface needs: turn indices to fetch
    # the exact lines, and milliseconds to seek a recording.
    start_turn_index: int
    end_turn_index: int
    time: TimeRange
    speakers: list[str] = Field(default_factory=list)
    created_at: datetime | None = None

    @classmethod
    def of(cls, fact: Fact, meeting_title: str) -> "FactResponse":
        return cls(meeting_title=meeting_title, **fact.model_dump())
