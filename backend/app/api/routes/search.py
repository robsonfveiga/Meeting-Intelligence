from fastapi import APIRouter

from app.api.schemas.search import SearchRequest
from app.graphs.query import search
from app.models.retrieval import SearchFilters, SearchResult

router = APIRouter()


@router.post("", response_model=SearchResult)
async def search_chunks(request: SearchRequest) -> SearchResult:
    """Retrieval on its own, with no model in the loop.

    Exposed as its own endpoint rather than hidden inside chat because retrieval
    quality is the thing that decides whether answers are any good, and it can
    only be tuned and measured when it is separable from generation.

    The response carries per-strategy ranks and per-stage timings so the "how
    was this found" panel reads from the same payload the caller already has.
    """
    return await search(
        request.query,
        limit=request.limit,
        filters=SearchFilters(meeting_ids=request.meeting_ids, speaker=request.speaker),
        expand=request.expand,
    )
