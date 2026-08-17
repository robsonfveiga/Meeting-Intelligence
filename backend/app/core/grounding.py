"""Citation verification.

The guardrail that makes citations mean something. A model asked to cite `[3]`
will sometimes emit `[7]` when it was given four excerpts, or cite a plausible
number for a claim the excerpt does not support. The first is mechanically
detectable and this module detects it; the second is not, and saying so is more
useful than pretending otherwise.

What is enforced here:

- **Every marker must refer to an excerpt that was supplied.** Out-of-range
  markers are removed from the answer text rather than rendered, so the interface
  cannot show a citation pointing at nothing.
- **Citations are built from what survived**, not from what the model claimed.
  The returned list is derived from verified markers, so a citation can only
  exist if the chunk behind it was really in context.

What is *not* enforced: whether the cited excerpt actually supports the claim.
That is a semantic judgement needing another model call, and it belongs in an
evaluation harness rather than the request path — an unreliable check on the hot
path costs latency on every request and still misses cases.

Pure functions over strings and lists, so every case is testable without a model.
"""

import re

from app.models.answer import AnswerCitation
from app.models.retrieval import ScoredChunk

_MARKER = re.compile(r"\[(\d+)\]")
# Left behind when an invalid marker is removed mid-sentence.
_ORPHANED_SPACE = re.compile(r" +([.,;:!?])")
_DOUBLE_SPACE = re.compile(r"  +")


def extract_markers(text: str) -> list[int]:
    """Citation numbers in the order they appear, duplicates included."""
    return [int(match.group(1)) for match in _MARKER.finditer(text)]


def strip_invalid_markers(text: str, excerpt_count: int) -> tuple[str, list[int]]:
    """Remove markers that point at excerpts we never supplied.

    Returns the cleaned text and the markers that were dropped, because a
    non-empty dropped list is a quality signal worth surfacing rather than
    swallowing: it means the model referenced evidence that does not exist.
    """
    dropped: list[int] = []

    def replace(match: re.Match[str]) -> str:
        number = int(match.group(1))
        if 1 <= number <= excerpt_count:
            return match.group(0)
        dropped.append(number)
        return ""

    cleaned = _MARKER.sub(replace, text)
    cleaned = _ORPHANED_SPACE.sub(r"\1", cleaned)
    cleaned = _DOUBLE_SPACE.sub(" ", cleaned)
    return cleaned.strip(), dropped


def build_citations(text: str, hits: list[ScoredChunk]) -> list[AnswerCitation]:
    """Citations for the markers actually used, in first-appearance order.

    Excerpts the model did not cite are deliberately excluded: an evidence panel
    listing everything retrieved teaches the reader nothing about which parts the
    answer rests on.
    """
    seen: dict[int, None] = {}
    for marker in extract_markers(text):
        if 1 <= marker <= len(hits):
            seen.setdefault(marker, None)

    return [
        AnswerCitation(
            marker=marker,
            chunk_id=hits[marker - 1].chunk_id,
            meeting_id=hits[marker - 1].meeting_id,
            meeting_title=hits[marker - 1].meeting_title,
            speakers=hits[marker - 1].speakers,
            time=hits[marker - 1].time,
            quote=hits[marker - 1].text,
        )
        for marker in seen
    ]


def ground(text: str, hits: list[ScoredChunk]) -> tuple[str, list[AnswerCitation], list[int]]:
    """Verify an answer against the excerpts it was given.

    Order matters: strip first, then build citations from the cleaned text, so a
    dropped marker cannot leak into the citation list.
    """
    cleaned, dropped = strip_invalid_markers(text, len(hits))
    return cleaned, build_citations(cleaned, hits), dropped


def is_unsupported(text: str, hits: list[ScoredChunk]) -> bool:
    """Did a substantive answer arrive with no citations at all?

    With excerpts available, an uncited answer is either general knowledge or
    invention — both ungrounded. Short replies are exempt because a refusal
    legitimately cites nothing.
    """
    return bool(hits) and len(text) > 200 and not extract_markers(text)
