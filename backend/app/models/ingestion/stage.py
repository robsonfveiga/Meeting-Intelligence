from enum import StrEnum


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
