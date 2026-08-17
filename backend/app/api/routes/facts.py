"""Extracted decisions, commitments and open threads.

Deliberately not wired into the answer path. The retrieval index holds verbatim
transcript and nothing else, so a citation always resolves to something a person
actually said; mixing model-written statements into it would quietly weaken that
guarantee for a recall gain that this endpoint provides directly. Facts are a
browsable layer over the same evidence, not a second corpus.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.schemas.facts import FactResponse
from app.db import facts as facts_db
from app.db import meetings as meetings_db
from app.db.engine import transaction
from app.models.enums import FactKind
from app.models.fact import Fact

router = APIRouter()


async def list_facts(
    *,
    meeting_ids: list[UUID] | None = None,
    kind: FactKind | None = None,
    owner: str | None = None,
    limit: int = 200,
) -> list[FactResponse]:
    """Fetch facts and attach the meeting each one came from.

    Shared by both routes. The titles are resolved in one pass over the distinct
    meetings rather than a lookup per fact, so a cross-meeting listing stays two
    queries however long it gets.
    """
    async with transaction() as conn:
        found: list[Fact] = await facts_db.search(
            conn, meeting_ids=meeting_ids, kind=kind, owner=owner, limit=limit
        )
        titles = {
            meeting.id: meeting.title for meeting in await meetings_db.list_all(conn, limit=1000)
        }

    return [FactResponse.of(fact, titles.get(fact.meeting_id, "")) for fact in found]


@router.get("", response_model=list[FactResponse])
async def search_facts(
    kind: FactKind | None = None,
    owner: str | None = None,
    meeting_id: Annotated[list[UUID] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[FactResponse]:
    """Facts across the whole corpus.

    The cross-meeting view is the point. "What did we commit to" is a question
    about a series of meetings, and answering it from a list is both cheaper and
    more complete than answering it from retrieval.
    """
    return await list_facts(meeting_ids=meeting_id, kind=kind, owner=owner, limit=limit)
