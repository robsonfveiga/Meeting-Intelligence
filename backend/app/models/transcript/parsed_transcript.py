from pydantic import BaseModel

from app.models.transcript.parsed_turn import ParsedTurn


class ParsedTranscript(BaseModel):
    """A parser's whole output. Metadata is derived, never guessed."""

    turns: list[ParsedTurn]

    @property
    def participants(self) -> list[str]:
        """Distinct speakers, in the order they first spoke."""
        seen: dict[str, None] = {}
        for turn in self.turns:
            seen.setdefault(turn.speaker, None)
        return list(seen)

    @property
    def duration_ms(self) -> int:
        return max((t.time.end_ms for t in self.turns), default=0)
