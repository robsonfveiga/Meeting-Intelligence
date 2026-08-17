from pydantic import BaseModel


class StageError(BaseModel):
    stage: str
    message: str
    recoverable: bool = False
