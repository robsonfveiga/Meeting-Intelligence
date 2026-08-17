from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.api.schemas.health import HealthResponse, ReadyResponse
from app.config import get_settings
from app.db.engine import get_engine
from app.observability.log import get_logger

router = APIRouter()
log = get_logger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness. Deliberately checks nothing — it answers "is the process up".

    Kept separate from readiness so an orchestrator restarts a wedged process
    without also restarting one that is merely waiting on the database.
    """
    return HealthResponse(status="ok", service=get_settings().app_name)


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    """Readiness: can this instance actually serve traffic?"""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            revision = result.scalar_one_or_none()
    except Exception as exc:
        log.warning("ready.failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        ) from exc

    return ReadyResponse(status="ready", database="ok", migrations=revision or "none")
