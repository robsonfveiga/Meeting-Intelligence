"""Grounded answers, streamed and not.

Two endpoints over one implementation. The streaming one is what an interface
uses; the plain one exists because it is far easier to test, script and evaluate
against — and a system you can only observe through a token stream is a system
that is hard to check.
"""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.schemas.chat import ChatRequest
from app.clients.llm import CompletionUnavailable, completions_available
from app.graphs.query import answer, answer_stream
from app.models.answer.answer import Answer
from app.models.retrieval.search_filters import SearchFilters
from app.observability.log import get_logger

router = APIRouter()
log = get_logger(__name__)

_NO_KEY = (
    "OPENAI_API_KEY is not set, so answers cannot be generated. "
    "Retrieval still works — try POST /search."
)


def _filters(request: ChatRequest) -> SearchFilters:
    return SearchFilters(meeting_ids=request.meeting_ids, speaker=request.speaker)


@router.post("", response_model=Answer)
async def chat(request: ChatRequest) -> Answer:
    if not completions_available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _NO_KEY)
    try:
        return await answer(request.question, filters=_filters(request))
    except CompletionUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def _event(name: str, payload: object) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, default=str)}\n\n"


@router.post("/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Server-Sent Events rather than a WebSocket.

    The traffic is one-directional — the question arrives in this request body,
    and everything after is server to client. A WebSocket would add a protocol
    upgrade, reconnection handling and sticky-session concerns to buy a direction
    that is never used.
    """
    if not completions_available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _NO_KEY)

    async def events() -> AsyncIterator[str]:
        try:
            async for name, payload in answer_stream(request.question, filters=_filters(request)):
                if name == "excerpts":
                    yield _event("excerpts", [hit.model_dump() for hit in payload])
                elif name == "token":
                    yield _event("token", {"text": payload})
                else:
                    yield _event(
                        "done",
                        {
                            "citations": [c.model_dump() for c in payload.citations],
                            "trace": payload.trace.model_dump(),
                            "refused": payload.refused,
                        },
                    )
        except Exception as exc:
            # The response has already begun, so an error cannot become a status
            # code. It has to be an event the client can render.
            log.exception("chat.stream_failed", question=request.question)
            yield _event("error", {"message": str(exc)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
