from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.models.transcript import TimeRange


class Chunk(BaseModel):
    """A window of consecutive turns, embedded and retrieved as one unit.

    Carries the speakers and the time range so a retrieved chunk can be cited
    without a second lookup, and so retrieval can filter on either.
    """

    id: UUID = Field(default_factory=uuid4)
    meeting_id: UUID
    index: int
    start_turn_index: int
    end_turn_index: int
    time: TimeRange
    speakers: list[str] = Field(default_factory=list)
    text: str
    context_header: str | None = None

    @property
    def embedding_input(self) -> str:
        """What actually gets embedded.

        The header is a one-line description of where this sits in the meeting,
        generated at ingest. Transcript chunks are full of pronouns whose
        referent lives in an earlier turn; prefixing that context is what stops
        "let's do that" from being an unretrievable chunk.
        """
        if self.context_header:
            return f"{self.context_header}\n\n{self.text}"
        return self.text
