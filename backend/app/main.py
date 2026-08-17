"""Application factory and lifespan.

The checkpointer connection pool and the compiled graph are built once at
startup and held on `app.state`, because compiling per request would rebuild
the graph on every upload.
"""

from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.api.routes import router
from app.config import get_settings
from app.db.engine import dispose_engine
from app.graphs.ingest import build_ingestion_graph
from app.observability.log import configure_logging, get_logger
from app.observability.middleware import RequestContextMiddleware
from app.observability.tracing import configure_tracing

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging()
    configure_tracing()

    async with AsyncExitStack() as stack:
        checkpointer = await stack.enter_async_context(
            AsyncPostgresSaver.from_conn_string(settings.database_url)
        )
        await checkpointer.setup()

        app.state.ingestion_graph = build_ingestion_graph(checkpointer)
        log.info("startup.complete", environment=settings.environment)

        yield

        await dispose_engine()
        log.info("shutdown.complete")


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title="Meeting Intelligence",
        description="Ask questions across a collection of meeting transcripts.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    app.include_router(router)
    log.info("app.created", environment=settings.environment)
    return app


app = create_app()
