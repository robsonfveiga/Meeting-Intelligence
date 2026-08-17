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

    if not snapshot or not snapshot.values:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown job")

    values = snapshot.values
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
