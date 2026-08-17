"""Conversation-aware chunking.

A fixed-size splitter is actively wrong for transcripts, in three ways:

1. **It splits mid-turn**, so a chunk begins halfway through someone's sentence
   and the speaker attribution is lost — which is most of what makes a citation
   useful.
2. **It ignores speakers**, when who said something is often the answer.
3. **It has no notion of time**, which is a first-class filter here.

So chunks are built from whole turns, never split, with a turn of overlap so a
question answered across a boundary is still retrievable. Size is measured in
characters rather than tokens: the target is far below the embedding model's
limit, so token-exact counting would add a dependency to buy precision that
does not change any decision.
"""

import re

from app.models.transcript.chunk import Chunk
from app.models.transcript.time_range import TimeRange
from app.models.transcript.turn import Turn

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _split_long_text(text: str, max_chars: int) -> list[str]:
    """Break a single oversized turn on sentence boundaries.

    Only reachable when one person talks without interruption for longer than a
    whole chunk — a demo or a status monologue. Rare, but a single turn larger
    than the embedding limit would otherwise fail the whole ingest.
    """
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(text):
        if current and len(current) + len(sentence) + 1 > max_chars:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)

    # A single sentence longer than the limit still has to be cut somewhere.
    final: list[str] = []
    for part in parts:
        while len(part) > max_chars:
            final.append(part[:max_chars])
            part = part[max_chars:]
        if part:
            final.append(part)
    return final


def _speakers_in(turns: list[Turn]) -> list[str]:
    seen: dict[str, None] = {}
    for turn in turns:
        seen.setdefault(turn.speaker, None)
    return list(seen)


def _render(turns: list[Turn]) -> str:
    """Speaker labels stay in the embedded text — they are part of the meaning."""
    return "\n".join(f"{turn.speaker}: {turn.text}" for turn in turns)


def chunk_turns(
    turns: list[Turn],
    *,
    # Defaults mirror `config.py` on purpose: the tests exercise these, so a
    # drifting default would mean the suite validates a size nobody runs.
    target_chars: int = 500,
    max_chars: int = 1000,
    overlap_turns: int = 1,
) -> list[Chunk]:
    """Group consecutive turns into overlapping, speaker-preserving windows."""
    if not turns:
        return []

    meeting_id = turns[0].meeting_id
    chunks: list[Chunk] = []
    window: list[Turn] = []
    size = 0

    def flush() -> None:
        nonlocal window, size
        if not window:
            return
        chunks.append(
            Chunk(
                meeting_id=meeting_id,
                index=len(chunks),
                start_turn_index=window[0].index,
                end_turn_index=window[-1].index,
                time=TimeRange(start_ms=window[0].time.start_ms, end_ms=window[-1].time.end_ms),
                speakers=_speakers_in(window),
                text=_render(window),
            )
        )
        # Carry the tail forward so a boundary does not orphan the answer.
        window = window[-overlap_turns:] if overlap_turns else []
        size = sum(len(t.text) for t in window)

    for turn in turns:
        rendered = len(turn.speaker) + len(turn.text) + 2

        if rendered > max_chars:
            flush()
            window, size = [], 0
            for piece in _split_long_text(turn.text, max_chars):
                part = turn.model_copy(update={"text": piece})
                chunks.append(
                    Chunk(
                        meeting_id=meeting_id,
                        index=len(chunks),
                        start_turn_index=turn.index,
                        end_turn_index=turn.index,
                        time=turn.time,
                        speakers=[turn.speaker],
                        text=_render([part]),
                    )
                )
            continue

        if window and size + rendered > target_chars:
            flush()

        window.append(turn)
        size += rendered

    flush()
    # flush() leaves the overlap tail behind; without this the final turns of a
    # meeting would only ever appear as overlap, never as a chunk of their own.
    if window and (not chunks or chunks[-1].end_turn_index < turns[-1].index):
        chunks.append(
            Chunk(
                meeting_id=meeting_id,
                index=len(chunks),
                start_turn_index=window[0].index,
                end_turn_index=window[-1].index,
                time=TimeRange(start_ms=window[0].time.start_ms, end_ms=window[-1].time.end_ms),
                speakers=_speakers_in(window),
                text=_render(window),
            )
        )

    return chunks


def build_context_header(
    meeting_title: str,
    chunk: Chunk,
    total_duration_ms: int,
) -> str:
    """A one-line description of where a chunk sits, prefixed before embedding.

    Deliberately derived from metadata rather than generated by a model. The
    published contextual-retrieval technique uses a model call per chunk, which
    resolves pronouns properly but costs a request per chunk on every ingest.
    Slice 2 adds retrieval measurement; buying that upgrade before it can be
    measured would be paying for an improvement nobody has demonstrated.
    """
    minutes = chunk.time.start_ms // 60_000
    position = ""
    if total_duration_ms > 0:
        fraction = chunk.time.start_ms / total_duration_ms
        position = ("opening of", "middle of", "later in")[min(int(fraction * 3), 2)]

    speakers = ", ".join(chunk.speakers)
    return f"From the {position} '{meeting_title}' at {minutes} min. Speaking: {speakers}."
