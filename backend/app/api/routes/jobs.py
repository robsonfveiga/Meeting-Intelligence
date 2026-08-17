from fastapi import APIRouter, HTTPException, Request, status

from app.api.schemas.jobs import JobResponse

router = APIRouter()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(request: Request, job_id: str) -> JobResponse:
    """Job status, read straight out of the graph checkpoint.

    No jobs table: the checkpointer already stores exactly this, keyed by
    thread identifier, and duplicating it would just be a second thing to
    keep in sync.
    """
    graph = request.app.state.ingestion_graph
    snapshot = await graph.aget_state({"configurable": {"thread_id": job_id}})
    values = snapshot.values if snapshot else {}

    # A snapshot is not all-or-nothing. The first poll after an upload can land
    # while the opening checkpoint is still being written, and a reader on another
    # connection then sees state with some channels populated and some not — non
    # empty, but without the two fields this response cannot be built from.
    #
    # So the guard asks whether the fields are there rather than whether the dict
    # is, because "truthy" and "usable" are not the same question. Reading `stage`
    # off a partial snapshot was a 500 in the opening milliseconds of every
    # ingest, which the client correctly reported as the API failing.
    #
    # 404 rather than a synthesised "received": the client already waits out a 404
    # in the first seconds precisely because a job is not readable the instant it
    # is accepted, and one more poll costs 400ms.
    if "stage" not in values or "source" not in values:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown job")
    stats = values.get("stats", {})
    return JobResponse(
        job_id=job_id,
        stage=values["stage"],
        filename=values["source"].filename,
        detected_format=values.get("detected_format"),
        meeting_id=values.get("meeting_id"),
        turn_count=values.get("turn_count", 0),
        chunk_count=len(values.get("chunk_ids", [])),
        fact_count=len(values.get("fact_ids", [])),
        dropped_fact_count=values.get("dropped_fact_count", 0),
        total_duration_ms=sum(s.duration_ms for s in stats.values()),
        stats=stats,
        errors=values.get("errors", []),
    )
