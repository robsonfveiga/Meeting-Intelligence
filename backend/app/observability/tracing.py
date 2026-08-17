"""LangSmith tracing.

Opt-in and off by default. LangSmith is configured entirely through environment
variables, so this only translates our settings into the names it expects and
makes the choice visible in one place rather than implicit in a `.env` file.
"""

import os

from app.config import get_settings
from app.observability.log import get_logger

log = get_logger(__name__)


def configure_tracing() -> None:
    settings = get_settings()

    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        os.environ["LANGSMITH_TRACING"] = "false"
        log.info("tracing.disabled")
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    log.info("tracing.enabled", project=settings.langsmith_project)
