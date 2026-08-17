from pydantic import BaseModel


class TimeRange(BaseModel):
    """Offset from the start of the recording, in milliseconds.

    Milliseconds rather than a timedelta because that is what every transcript
    format gives us and what the user interface needs back for seeking.
    """

    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms
