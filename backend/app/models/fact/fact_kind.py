from enum import StrEnum


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
