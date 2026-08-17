"""Durability: does a failed run actually resume where it stopped?

This is the load-bearing claim behind running ingestion as a checkpointed graph.
If it does not hold, the architecture is paying the cost of a graph for nothing,
and the state design is wrong. Worth testing rather than assuming.

A purpose-built graph is used instead of the real ingestion graph so the failure
can be injected at an exact node without reaching into a compiled object.
"""

import operator
from typing import Annotated, TypedDict
from uuid import uuid4

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from app.config import get_settings

pytestmark = pytest.mark.integration


class _State(TypedDict, total=False):
    trail: Annotated[list[str], operator.add]


async def test_resume_skips_already_completed_nodes():
    calls: list[str] = []
    fail_once = {"pending": True}

    async def cheap(state: _State) -> dict:
        calls.append("cheap")
        return {"trail": ["cheap"]}

    async def expensive(state: _State) -> dict:
        """Stands in for embedding: slow, costly, and the likely failure point."""
        calls.append("expensive")
        if fail_once["pending"]:
            fail_once["pending"] = False
            raise RuntimeError("provider timed out")
        return {"trail": ["expensive"]}

    async def finalise(state: _State) -> dict:
        calls.append("finalise")
        return {"trail": ["finalise"]}

    builder = StateGraph(_State)
    builder.add_node("cheap", cheap)
    builder.add_node("expensive", expensive)
    builder.add_node("finalise", finalise)
    builder.add_edge(START, "cheap")
    builder.add_edge("cheap", "expensive")
    builder.add_edge("expensive", "finalise")
    builder.add_edge("finalise", END)

    async with AsyncPostgresSaver.from_conn_string(get_settings().database_url) as saver:
        await saver.setup()
        graph = builder.compile(checkpointer=saver)
        # Fresh thread per run: checkpoints outlive the test process, so a fixed
        # identifier would accumulate state from previous runs.
        config = {"configurable": {"thread_id": f"resume-test-{uuid4()}"}}

        with pytest.raises(RuntimeError):
            await graph.ainvoke({"trail": []}, config=config)

        assert calls == ["cheap", "expensive"]

        # Passing None means "carry on from the checkpoint" rather than "start over".
        result = await graph.ainvoke(None, config=config)

    # `cheap` ran exactly once: its result was restored, not recomputed. That is
    # the whole point — a failed embedding step must not re-parse and re-chunk.
    assert calls == ["cheap", "expensive", "expensive", "finalise"]
    assert result["trail"] == ["cheap", "expensive", "finalise"]
