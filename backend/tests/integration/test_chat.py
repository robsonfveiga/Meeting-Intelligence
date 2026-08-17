"""Grounded answers, end to end.

The model is stubbed. These tests cover the wiring around generation — the
corrective retry loop, citation verification, refusal when nothing is retrieved,
and the streamed event order — none of which should depend on what a model
happens to say on a given day. Answer *quality* is a separate question, measured
against the golden set rather than asserted here.
"""

import json
from pathlib import Path

import pytest

from app.clients.llm import CompletionResult

VTT = (Path(__file__).parent.parent / "fixtures" / "teams_retro.vtt").read_bytes()

pytestmark = pytest.mark.integration


@pytest.fixture
async def ingested(client):
    import asyncio

    response = await client.post(
        "/meetings", files={"file": ("2026-03-18-retro.vtt", VTT, "text/vtt")}
    )
    job_id = response.json()["job_id"]
    for _ in range(300):
        job = (await client.get(f"/jobs/{job_id}")).json()
        if job["stage"] in {"done", "failed"}:
            break
        await asyncio.sleep(0.1)
    assert job["stage"] == "done"
    return job


@pytest.fixture
def stub_model(monkeypatch):
    """Replace both model calls with something deterministic.

    Returns a recorder so a test can assert on how many times each was called —
    which is how the retry loop is observed without depending on a real grader.
    """
    calls: dict[str, list] = {"complete": [], "stream": []}
    scripted: dict[str, str] = {"answer": "The rollback took four hours. [1]", "grade": ""}

    async def fake_complete(messages, *, model=None, max_tokens=None):
        system = messages[0]["content"]
        kind = "grade" if "SUFFICIENT" in system else "rewrite" if "rewrite" in system else "answer"
        calls["complete"].append(kind)
        text = scripted.get(kind, "rewritten query")
        return CompletionResult(text=text, tokens=10, cost_usd=0.0)

    async def fake_stream(messages, *, model=None, max_tokens=None):
        calls["stream"].append("answer")
        for word in scripted["answer"].split(" "):
            yield word + " "
        yield CompletionResult(text=scripted["answer"], tokens=10, cost_usd=0.0)

    monkeypatch.setattr("app.graphs.query.complete", fake_complete)
    monkeypatch.setattr("app.graphs.query.stream_completion", fake_stream)
    monkeypatch.setattr("app.clients.llm.completions_available", lambda: True)
    monkeypatch.setattr("app.api.routes.chat.completions_available", lambda: True)
    return calls, scripted


async def _ask(client, question: str, **kwargs) -> dict:
    response = await client.post("/chat", json={"question": question, **kwargs})
    assert response.status_code == 200, response.text
    return response.json()


class TestAnswering:
    async def test_returns_a_grounded_answer_with_citations(self, client, ingested, stub_model):
        body = await _ask(client, "how long did the rollback take?")

        assert "four hours" in body["text"]
        assert len(body["citations"]) == 1
        assert body["citations"][0]["marker"] == 1

    async def test_citations_carry_what_the_evidence_panel_needs(
        self, client, ingested, stub_model
    ):
        citation = (await _ask(client, "rollback"))["citations"][0]

        assert citation["meeting_title"]
        assert citation["speakers"]
        assert citation["quote"]
        assert "start_ms" in citation["time"]

    async def test_excerpts_are_returned_alongside_the_answer(self, client, ingested, stub_model):
        """A reader can judge thin evidence only if the evidence is shown."""
        body = await _ask(client, "rollback")
        assert body["excerpts"]

    async def test_trace_reports_how_the_answer_was_built(self, client, ingested, stub_model):
        trace = (await _ask(client, "rollback"))["trace"]

        assert trace["hits_considered"] > 0
        assert set(trace["timings_ms"]) >= {"retrieve", "grade", "answer"}
        assert trace["tokens"] > 0

    async def test_rejects_an_empty_question(self, client):
        assert (await client.post("/chat", json={"question": ""})).status_code == 422


class TestCitationVerification:
    async def test_markers_pointing_at_nothing_are_removed(self, client, ingested, stub_model):
        """The guardrail: a model cannot cite evidence it was never given."""
        _, scripted = stub_model
        scripted["answer"] = "Real claim [1] and invented claim [99]."

        body = await _ask(client, "rollback")

        assert "[99]" not in body["text"]
        assert "[1]" in body["text"]
        assert body["trace"]["dropped_markers"] == [99]
        assert [c["marker"] for c in body["citations"]] == [1]

    async def test_an_uncited_answer_produces_no_citations(self, client, ingested, stub_model):
        _, scripted = stub_model
        scripted["answer"] = "An answer with no citations at all."

        body = await _ask(client, "rollback")
        assert body["citations"] == []


class TestCorrectiveLoop:
    async def test_a_poor_grade_triggers_one_rewrite_and_retry(self, client, ingested, stub_model):
        calls, scripted = stub_model
        scripted["grade"] = "INSUFFICIENT"

        body = await _ask(client, "something the grader dislikes")

        assert "rewrite" in calls["complete"]
        assert body["trace"]["rewritten"] is True
        assert body["trace"]["attempts"] == 2

    async def test_the_loop_is_bounded(self, client, ingested, stub_model):
        """A permanently unhappy grader must not loop forever."""
        calls, scripted = stub_model
        scripted["grade"] = "INSUFFICIENT"

        body = await _ask(client, "never satisfying")

        assert body["trace"]["attempts"] == 2
        assert calls["complete"].count("rewrite") == 1

    async def test_a_good_grade_skips_the_rewrite(self, client, ingested, stub_model):
        calls, _ = stub_model
        await _ask(client, "how long did the rollback take?")
        assert "rewrite" not in calls["complete"]

    async def test_a_broken_grader_does_not_fail_the_request(
        self, client, ingested, monkeypatch, stub_model
    ):
        """Grading is an optimisation, so its failure must not lose the answer."""

        async def exploding(messages, *, model=None, max_tokens=None):
            if "SUFFICIENT" in messages[0]["content"]:
                raise RuntimeError("grader is down")
            return CompletionResult(text="Answer anyway. [1]", tokens=5, cost_usd=0.0)

        monkeypatch.setattr("app.graphs.query.complete", exploding)
        body = await _ask(client, "rollback")

        assert "Answer anyway" in body["text"]


class TestRefusal:
    async def test_no_corpus_means_no_model_call_at_all(self, client, stub_model):
        """A guardrail and a cost saving: no evidence, nothing to ground."""
        calls, _ = stub_model
        body = await _ask(client, "anything at all")

        assert body["refused"] is True
        assert body["citations"] == []
        assert calls["complete"] == []
        assert calls["stream"] == []


class TestStreaming:
    async def test_event_order_puts_evidence_before_tokens(self, client, ingested, stub_model):
        """The evidence panel renders while the answer is still being written."""
        async with client.stream("POST", "/chat/stream", json={"question": "rollback"}) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            names = [
                line[7:] async for line in response.aiter_lines() if line.startswith("event: ")
            ]

        assert names[0] == "excerpts"
        assert names[-1] == "done"
        assert names.count("token") > 1

    async def test_the_final_event_carries_verified_citations(self, client, ingested, stub_model):
        payloads: list[tuple[str, str]] = []
        name = ""
        async with client.stream("POST", "/chat/stream", json={"question": "rollback"}) as response:
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: "):
                    payloads.append((name, line[6:]))

        done = next(json.loads(data) for n, data in payloads if n == "done")
        assert done["citations"]
        assert "trace" in done
