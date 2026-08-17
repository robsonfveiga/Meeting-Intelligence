from pydantic import BaseModel


class SourceReference(BaseModel):
    """The uploaded file. Where it is, not what it says."""

    filename: str
    content_type: str | None = None
    size_bytes: int = 0
    storage_path: str
