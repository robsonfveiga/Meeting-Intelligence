"""Structured extraction: the parts that do not call a model.

Everything here is pure, for the same reason `prompts.py` and `grounding.py` are:
the interesting failures in extraction are shape failures — a fact pointing at a
turn that was never sent, two windows producing the same commitment twice, a
window that quietly drops the last turn of a meeting — and none of them need a
provider to reproduce.

The through-line is the one slice 3 established for citations. **A fact is
admissible only if the evidence behind it verifies.** The model returns turn
indices; those indices are checked against the turns actually supplied, and
anything outside the window is discarded and counted. That check is mechanical,
so it always holds.

What it does *not* establish is that the statement is a fair reading of those
turns. That is a semantic judgement, it needs a second model, and it belongs in
an evaluation harness rather than the ingest path. Verified evidence is not
verified meaning, and the README says so rather than letting one imply the other.
"""

import re
from typing import Any
from uuid import UUID

from app.models.fact.extracted_fact import ExtractedFact
from app.models.fact.fact import Fact
from app.models.fact.fact_kind import FactKind
from app.models.transcript.time_range import TimeRange
from app.models.transcript.turn import Turn

# The provider contract. Hand-written rather than generated from the pydantic
# model because strict JSON-schema mode is fussy in ways pydantic's output is
# not: every property must appear in `required`, optional means a null union,
# and `additionalProperties` must be explicitly false. Deriving it would mean a
# translation layer whose bugs surface as provider 400s at ingest time.
FACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": [kind.value for kind in FactKind]},
                    "statement": {"type": "string"},
                    "owner": {"type": ["string", "null"]},
                    "due": {"type": ["string", "null"]},
                    "start_turn_index": {"type": "integer"},
                    "end_turn_index": {"type": "integer"},
                },
                "required": [
                    "kind",
                    "statement",
                    "owner",
                    "due",
                    "start_turn_index",
                    "end_turn_index",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}

_PUNCTUATION = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")


def build_windows(turns: list[Turn], *, max_chars: int) -> list[list[Turn]]:
    """Group turns into the units extraction reads, one model call each.

    Not `chunk_turns`. Retrieval chunks are small on purpose and overlap by a
    turn, and both properties are wrong here: a decision stated in one turn and
    qualified four turns later needs to arrive in the same call, and overlap
    would manufacture duplicates for the deduplicator to clean up again. The
    windows are large, contiguous and disjoint.

    A turn is never split, so a single turn longer than the budget becomes an
    oversized window of one rather than a truncated one. Losing the second half
    of a monologue is a worse failure than one large request.
    """
    if not turns:
        return []

    windows: list[list[Turn]] = []
    current: list[Turn] = []
    size = 0

    for turn in turns:
        cost = len(turn.speaker) + len(turn.text) + 2
        if current and size + cost > max_chars:
            windows.append(current)
            current, size = [], 0
        current.append(turn)
        size += cost

    if current:
        windows.append(current)
    return windows


def parse_facts(payload: dict[str, Any]) -> list[ExtractedFact]:
    """Read the provider's response, skipping entries that will not parse.

    Strict schema mode should make this total, and in practice it does. The
    tolerance is here because a provider-side schema regression should cost the
    facts it corrupted, not the whole ingest — the same reasoning that lets a
    missing API key degrade rather than fail.
    """
    facts: list[ExtractedFact] = []
    for entry in payload.get("facts") or []:
        if not isinstance(entry, dict):
            continue
        try:
            facts.append(ExtractedFact.model_validate(entry))
        except ValueError:
            continue
    return facts


def verify_evidence(
    candidates: list[ExtractedFact], window: list[Turn]
) -> tuple[list[ExtractedFact], list[ExtractedFact]]:
    """Split candidates into those whose evidence exists and those whose does not.

    Rejections are returned rather than silently dropped: a non-empty list means
    the model referenced turns it was never shown, which is the extraction
    equivalent of `AnswerTrace.dropped_markers` — a grounding signal worth
    counting on the job rather than swallowing.
    """
    available = {turn.index for turn in window}
    kept: list[ExtractedFact] = []
    rejected: list[ExtractedFact] = []

    for candidate in candidates:
        valid = (
            candidate.start_turn_index <= candidate.end_turn_index
            and candidate.start_turn_index in available
            and candidate.end_turn_index in available
        )
        (kept if valid else rejected).append(candidate)

    return kept, rejected


def to_facts(
    candidates: list[ExtractedFact], *, meeting_id: UUID, window: list[Turn]
) -> list[Fact]:
    """Resolve verified turn references into speakers and timestamps.

    Attribution comes from the turns, never from the model. Whatever an extractor
    claims about who said something, the name on a stored fact is the name on the
    transcript line it cites.

    Assumes the candidates have already passed `verify_evidence`; an unverified
    reference would raise here, which is the right failure for a broken call
    order but the wrong one for a bad model response.
    """
    by_index = {turn.index: turn for turn in window}
    facts: list[Fact] = []

    for candidate in candidates:
        covered = [
            by_index[i]
            for i in range(candidate.start_turn_index, candidate.end_turn_index + 1)
            if i in by_index
        ]
        if not covered:
            continue

        seen: dict[str, None] = {}
        for turn in covered:
            seen.setdefault(turn.speaker, None)

        facts.append(
            Fact(
                meeting_id=meeting_id,
                kind=candidate.kind,
                statement=candidate.statement.strip(),
                # Owner and due only mean anything on a commitment. Clearing them
                # elsewhere stops a decision arriving with a spurious assignee
                # because the model filled every field it was given.
                owner=candidate.owner if candidate.kind is FactKind.COMMITMENT else None,
                due=candidate.due if candidate.kind is FactKind.COMMITMENT else None,
                start_turn_index=candidate.start_turn_index,
                end_turn_index=candidate.end_turn_index,
                time=TimeRange(
                    start_ms=covered[0].time.start_ms,
                    end_ms=covered[-1].time.end_ms,
                ),
                speakers=list(seen),
            )
        )

    return facts


def _normalise(statement: str) -> str:
    return _WHITESPACE.sub(" ", _PUNCTUATION.sub("", statement.lower())).strip()


def deduplicate(facts: list[Fact]) -> list[Fact]:
    """Collapse the same claim extracted twice, keeping the tightest evidence.

    Windows are disjoint, so this is not cleaning up an overlap artefact — it is
    handling the thing meetings actually do, which is restate a decision at the
    end of the hour after making it in the middle. Two entries for one decision
    is noise in a decision list; the one that cites the fewest turns is the one
    that points at where it was actually made.
    """
    best: dict[tuple[FactKind, str], Fact] = {}

    for fact in facts:
        key = (fact.kind, _normalise(fact.statement))
        incumbent = best.get(key)
        if incumbent is None or fact.turn_span < incumbent.turn_span:
            best[key] = fact

    return sorted(best.values(), key=lambda f: (f.start_turn_index, f.kind.value))
