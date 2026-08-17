from uuid import UUID

from pydantic import BaseModel

from app.models.transcript.time_range import TimeRange


class AnswerCitation(BaseModel):
    """A verified reference. Exists only if the chunk behind it was in context.

    Carries the meeting title and speakers directly, so the evidence panel
    renders without a request per citation.
    """

    marker: int
    chunk_id: UUID
    meeting_id: UUID
    meeting_title: str
    speakers: list[str]
    time: TimeRange
    quote: str
