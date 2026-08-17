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
