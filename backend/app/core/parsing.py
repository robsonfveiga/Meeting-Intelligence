"""WebVTT transcript parsing.

**Scope: WebVTT only, deliberately.** It is what Microsoft Teams exports — both
from the meeting UI and as the Graph API default, where each utterance carries a
`<v Speaker Name>` voice tag. Because WebVTT is a W3C standard rather than a
Microsoft one, Zoom, Whisper, Otter and most transcription tooling emit it too,
so scoping to one format costs less coverage than it appears to.

Rejected: SubRip, JSON exports and plain text. All were implemented and worked;
they were removed because supporting one format completely is worth more here
than four formats adequately. The cost of adding one back is a parser plus a
branch — the canonical `Turn` shape below is what everything downstream depends
on, and it does not change.

Everything here is a pure function over strings. No database, no network, no
file input or output — which is what lets the fiddliest logic in the system be
tested exhaustively in milliseconds with nothing else running.

The important step is not the format handling but **merging cues into turns**.
WebVTT emits a cue every few seconds, so a single thought arrives as three
fragments. Embedding those directly produces chunks like "yeah, agreed" with
nothing to retrieve on. Consecutive cues from the same speaker are merged into
one turn, and a turn is never split again downstream.
"""

import re
from datetime import UTC, datetime

from app.models.transcript.parsed_transcript import ParsedTranscript
from app.models.transcript.parsed_turn import ParsedTurn
from app.models.transcript.time_range import TimeRange

UNKNOWN_SPEAKER = "Unknown"

_VTT_TIMESTAMP = re.compile(r"\d{1,2}:\d{2}:\d{2}\.\d{1,3}\s*-->")
_TIMESTAMP = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?")

# Teams writes "<v Alice Smith>text</v>". The closing tag is optional in the
# wild, so it is not required here.
_VOICE_TAG = re.compile(r"^\s*<v\s+([^>]+?)>\s*(.*?)\s*(?:</v>)?\s*$", re.DOTALL)
# Some tools write "Alice Smith: text" instead of a voice tag.
_PREFIX_SPEAKER = re.compile(r"^\s*([A-Z][\w .'\-]{0,40}?)\s*:\s+(.*)$", re.DOTALL)

_FILENAME_DATE = re.compile(r"^\s*(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})\s*[-_. ]*")


# --------------------------------------------------------------------------
# Validation and filename metadata
# --------------------------------------------------------------------------


def looks_like_webvtt(sample: str) -> bool:
    """Is this a WebVTT file?

    The header is required by the specification but occasionally stripped, so a
    VTT-style timestamp also counts. Deliberately discriminating against SubRip,
    which uses a comma before the milliseconds and so does not match — a
    rejection with a useful message beats a parse that silently yields nothing.
    """
    head = sample.lstrip("﻿").lstrip()
    return head.startswith("WEBVTT") or bool(_VTT_TIMESTAMP.search(head[:4000]))


def title_and_date(filename: str) -> tuple[str, datetime | None]:
    """Derive a readable title and, where present, the meeting date.

    Dated filenames are the norm for exported transcripts, and leaving the date
    in the title produces "2026 03 04 pricing review". Lifting it out gives a
    clean title *and* fills `occurred_at`, which date filtering needs and which
    nothing else populates.
    """
    stem = filename.rsplit(".", 1)[0]

    occurred_at: datetime | None = None
    match = _FILENAME_DATE.match(stem)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            occurred_at = datetime(year, month, day, tzinfo=UTC)
            stem = stem[match.end() :]
        except ValueError:
            occurred_at = None  # 2026-13-45 is not a date, so treat it as text

    title = " ".join(stem.replace("_", " ").replace("-", " ").split())
    return (title or filename), occurred_at


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def parse_timestamp(value: str) -> int:
    """`HH:MM:SS.mmm` or `MM:SS` to milliseconds."""
    match = _TIMESTAMP.search(value)
    if not match:
        return 0
    hours, minutes, seconds, fraction = match.groups()
    millis = int((fraction or "0").ljust(3, "0")[:3])
    return int(hours or 0) * 3_600_000 + int(minutes) * 60_000 + int(seconds) * 1000 + millis


def split_speaker(text: str) -> tuple[str | None, str]:
    """Pull a speaker label off the front of a cue, if there is one."""
    voice = _VOICE_TAG.match(text)
    if voice:
        return voice.group(1).strip(), voice.group(2).strip()

    prefix = _PREFIX_SPEAKER.match(text)
    if prefix:
        candidate = prefix.group(1).strip()
        if _looks_like_a_name(candidate):
            return candidate, prefix.group(2).strip()

    return None, text.strip()


def _looks_like_a_name(candidate: str) -> bool:
    """Distinguish "Tom Beckett:" from "The point is this:".

    A word count alone is not enough — "The point is this" is four words and
    starts with a capital. Requiring *every* word to be capitalised separates
    display names from sentence fragments. It gives up on lowercase particles
    like "van der Berg", which is an acceptable miss: Teams uses voice tags, and
    this path only serves tools that write "Name:" prefixes instead.
    """
    words = candidate.split()
    return 0 < len(words) <= 4 and all(word[:1].isupper() for word in words)


def _cue_blocks(content: str) -> list[list[str]]:
    """Split on blank lines. WebVTT is block-structured."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in content.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def merge_into_turns(segments: list[tuple[str, int, int, str]]) -> ParsedTranscript:
    """Collapse consecutive same-speaker segments into turns.

    Segments arrive as (speaker, start_ms, end_ms, text). Nobody spoke between
    two consecutive segments by definition, so consecutive segments from one
    speaker are one continuous turn regardless of the gap between them.
    """
    turns: list[ParsedTurn] = []

    for speaker, start_ms, end_ms, text in segments:
        cleaned = " ".join(text.split())
        if not cleaned:
            continue

        if turns and turns[-1].speaker == speaker:
            previous = turns[-1]
            previous.text = f"{previous.text} {cleaned}"
            previous.time = TimeRange(start_ms=previous.time.start_ms, end_ms=end_ms)
            continue

        turns.append(
            ParsedTurn(
                index=len(turns),
                speaker=speaker or UNKNOWN_SPEAKER,
                time=TimeRange(start_ms=start_ms, end_ms=end_ms),
                text=cleaned,
            )
        )

    return ParsedTranscript(turns=turns)


def parse_webvtt(content: str) -> ParsedTranscript:
    """WebVTT to turns.

    Anything in a cue block that is not the timing line or the payload —
    the `WEBVTT` header, `NOTE` comments, Teams' cue identifiers — is skipped by
    construction rather than pattern-matched, so identifier conventions across
    tools do not matter.
    """
    segments: list[tuple[str, int, int, str]] = []
    last_speaker = UNKNOWN_SPEAKER

    for block in _cue_blocks(content):
        timing_at = next((i for i, line in enumerate(block) if "-->" in line), None)
        if timing_at is None:
            continue

        start_raw, _, end_raw = block[timing_at].partition("-->")
        start_ms = parse_timestamp(start_raw)
        end_ms = parse_timestamp(end_raw)

        body = " ".join(block[timing_at + 1 :]).strip()
        if not body:
            continue

        speaker, text = split_speaker(body)
        if speaker:
            last_speaker = speaker
        # A cue with no label continues whoever was speaking.
        segments.append((speaker or last_speaker, start_ms, end_ms, text))

    return merge_into_turns(segments)


def has_speaker_attribution(transcript: ParsedTranscript) -> bool:
    """Did anyone get named?

    Teams tenants can disable speaker attribution, and the Graph API then serves
    a variant with no voice tags at all. The file parses perfectly and every turn
    is anonymous, which is worth telling the user rather than discovering later
    when citations name nobody.
    """
    return any(turn.speaker != UNKNOWN_SPEAKER for turn in transcript.turns)
