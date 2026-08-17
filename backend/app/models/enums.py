from enum import StrEnum


class TranscriptFormat(StrEnum):
    """Formats accepted at ingest.

    One member, on purpose. WebVTT is what Teams exports and what most
    transcription tooling emits; supporting it completely is worth more than
    supporting several formats adequately. The enum stays rather than being
    replaced with a hardcoded string so the stored `source_format` keeps meaning
    when a second format is added.
    """

    WEBVTT = "webvtt"


class FactKind(StrEnum):
    """What extraction pulls out of a meeting.

    Three kinds, distinguished by what they commit someone to. A DECISION settles
    a question. A COMMITMENT names a person who will do something. An OPEN_THREAD
    is a question raised and left unanswered — the one that makes a meeting series
    legible, because it is what the next meeting is supposed to close.

    Deliberately not a general "topic" or "summary" kind: those cannot be verified
    against a specific stretch of transcript, and unverifiable output is what this
    system is built to avoid.
    """

    DECISION = "decision"
    COMMITMENT = "commitment"
    OPEN_THREAD = "open_thread"


class Stage(StrEnum):
    """Where an ingestion job has reached.

    Ordered as the pipeline runs. FAILED is terminal and can be entered from
    anywhere.
    """

    RECEIVED = "received"
    VALIDATED = "validated"
    PARSED = "parsed"
    CHUNKED = "chunked"
    CONTEXTUALISED = "contextualised"
    EMBEDDED = "embedded"
    EXTRACTED = "extracted"
    DONE = "done"
    FAILED = "failed"
