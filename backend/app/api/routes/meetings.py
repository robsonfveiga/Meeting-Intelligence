"""Meeting upload and listing.

Thin on purpose: validate, hand off, shape the response. No domain logic here.
"""

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile, status

from app.api.routes.facts import list_facts
from app.api.schemas.facts import FactResponse
from app.api.schemas.jobs import UploadAccepted
from app.config import get_settings
from app.db import meetings as meetings_db
from app.db.engine import transaction
from app.graphs.ingest import new_job_id
from app.models.enums import FactKind
from app.models.state import SourceReference, new_ingestion_state
from app.models.transcript import Meeting
from app.observability.log import get_logger

router = APIRouter()
log = get_logger(__name__)


async def _run_ingestion(request_app, job_id: str, state) -> None:
    """Drive the graph after the response has gone out.

    In-process on purpose for now, and a known limitation: a restart mid-run
    leaves the job stranded until something re-drives it. Productionising this
    means a real worker consuming a queue. The checkpoint means no work is lost
    either way, which is the point.
    """
    graph = request_app.state.ingestion_graph
    config = {"configurable": {"thread_id": job_id}}
    try:
        await graph.ainvoke(state, config=config)
    except Exception:
        log.exception("ingest.failed", job_id=job_id)


@router.post("", response_model=UploadAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_meeting(
    request: Request,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File()],
) -> UploadAccepted:
    settings = get_settings()

    payload = await file.read()
    if not payload:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")
    if len(payload) > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"file exceeds {settings.max_upload_bytes} bytes",
        )

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    original = Path(file.filename or "transcript.txt").name
    stored_at = upload_dir / f"{uuid.uuid4()}_{original}"
    stored_at.write_bytes(payload)

    job_id = new_job_id()
    state = new_ingestion_state(
        job_id,
        SourceReference(
            filename=original,
            content_type=file.content_type,
            size_bytes=len(payload),
            storage_path=str(stored_at),
        ),
    )

    log.info("ingest.accepted", job_id=job_id, filename=original, size_bytes=len(payload))
    background.add_task(_run_ingestion, request.app, job_id, state)

    return UploadAccepted(job_id=job_id, filename=original, status_url=f"/jobs/{job_id}")


@router.get("", response_model=list[Meeting])
async def list_meetings() -> list[Meeting]:
    """Returns the domain model directly — the wire shape does not differ from it."""
    async with transaction() as conn:
        return await meetings_db.list_all(conn)


@router.get("/{meeting_id}/facts", response_model=list[FactResponse])
async def meeting_facts(meeting_id: uuid.UUID, kind: FactKind | None = None) -> list[FactResponse]:
    """One meeting's decisions, commitments and open threads.

    A sub-resource rather than a filter on `/facts`, because that is what it is:
    the natural read after opening a meeting, and the shape a detail view asks
    for without having to construct a query.
    """
    return await list_facts(meeting_ids=[meeting_id], kind=kind)
