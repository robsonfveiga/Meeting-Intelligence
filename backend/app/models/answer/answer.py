from pydantic import BaseModel, Field

from app.models.answer.answer_citation import AnswerCitation
from app.models.answer.answer_trace import AnswerTrace
from app.models.retrieval.scored_chunk import ScoredChunk


class Answer(BaseModel):
    question: str
    text: str
    citations: list[AnswerCitation] = Field(default_factory=list)
    # True when retrieval found nothing usable and no model was called at all.
    refused: bool = False
    excerpts: list[ScoredChunk] = Field(default_factory=list)
    trace: AnswerTrace
