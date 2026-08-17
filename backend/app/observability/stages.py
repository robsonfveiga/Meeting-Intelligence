"""Per-node measurement.

Wrapping a node in `@timed` records its duration into the state's `stats` map,
which the `stats` reducer merges rather than replaces. This exists in slice 0,
before there is anything slow to measure, because retrofitting instrumentation
is always worse than designing it in — and because the job status endpoint and
the "how was this answer built" panel both read from here later.
"""

import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from app.models.state import StageStats
from app.observability.log import get_logger

log = get_logger(__name__)

# Bound to the wrapped function's own type rather than a fixed alias: LangGraph
# matches `add_node` against the node's state type, and a widened signature here
# would erase it at every call site.
NodeFn = TypeVar("NodeFn", bound=Callable[..., Awaitable[dict[str, Any]]])


def timed(stage_name: str) -> Callable[[NodeFn], NodeFn]:
    def decorator(fn: NodeFn) -> NodeFn:
        @functools.wraps(fn)
        async def wrapper(state: Any) -> dict[str, Any]:
            started = time.perf_counter()
            update = await fn(state)
            duration_ms = int((time.perf_counter() - started) * 1000)

            existing = update.get("stats", {}).get(stage_name, StageStats())
            existing.duration_ms = duration_ms
            update["stats"] = {**update.get("stats", {}), stage_name: existing}

            log.info(
                "node.completed",
                node=stage_name,
                job_id=state.get("job_id"),
                duration_ms=duration_ms,
            )
            return update

        return cast(NodeFn, wrapper)

    return decorator
