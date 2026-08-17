"""Extraction end to end, against a real database and a stubbed provider.

The provider is stubbed rather than called. What is worth testing here is the
node's contract — evidence verified against the turns actually sent, attribution
taken from the transcript rather than the model, a re-drive replacing rather than
duplicating — and all of that is about handling a response, not obtaining one.
A live call would make the assertions depend on what a model felt like returning.

Extraction quality is a different question, it needs a hand-written expected set
per meeting, and it belongs in the evaluation harness.
"""

import asyncio

import pytest

from app.clients.llm import StructuredResult

pytestmark = pytest.mark.integration

TEAMS = b"""WEBVTT

7c1f0a44-3b21-4d59-9f0e-11a2b3c4d5e6/1-0
00:00:01.000 --> 00:00:06.000
<v Priya Raman>We're holding the price change until after launch.</v>

7c1f0a44-3b21-4d59-9f0e-11a2b3c4d5e6/2-0
00:00:06.000 --> 00:00:11.000
<v Tom Beckett>I'll write it up before Friday.</v>
"""

# One valid decision, one valid commitment, and one fact citing a turn that was
# never sent — the case the guardrail exists for.
RESPONSE = {
    "facts": [
        {
            "kind": "decision",
            "statement": "The price change is held until after launch.",
            "owner": None,
            "due": None,
            "start_turn_index": 0,
            "end_turn_index": 0,
        },
        {
            "kind": "commitment",
            "statement": "Tom will write up the pricing decision.",
            "owner": "Tom Beckett",
            "due": "Friday",
            "start_turn_index": 1,
            "end_turn_index": 1,
        },
        {
            "kind": "decision",
            "statement": "A decision drawn from a turn that does not exist.",
            "owner": None,
            "due": None,
            "start_turn_index": 40,
            "end_turn_index": 41,
        },
    ]
}


@pytest.fixture
def extracting(monkeypatch):
    """Turn extraction on, with a provider that returns a fixed payload."""
    from app.config import get_settings
    from app.graphs import ingest

    async def fake_complete_structured(messages, **kwargs) -> StructuredResult:
        return StructuredResult(data=RESPONSE, tokens=1234, cost_usd=0.0)

    monkeypatch.setattr(get_settings(), "extraction_enabled", True)
    monkeypatch.setattr(ingest, "completions_available", lambda: True)
    monkeypatch.setattr(ingest, "complete_structured", fake_complete_structured)


async def _wait(client, job_id: str, timeout: float = 30.0) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    last: dict = {}
    while asyncio.get_event_loop().time() < deadline:
        response = await client.get(f"/jobs/{job_id}")
        if response.status_code == 200:
            last = response.json()
            if last["stage"] in {"done", "failed"}:
                return last
        await asyncio.sleep(0.1)
    return last


async def _ingest(client, name: str = "2026-03-04-pricing.vtt", payload: bytes = TEAMS) -> dict:
    response = await client.post("/meetings", files={"file": (name, payload, "text/vtt")})
    assert response.status_code == 202
    return await _wait(client, response.json()["job_id"])


class TestExtraction:
    async def test_verified_facts_are_stored_and_unverifiable_ones_are_not(
        self, client, extracting
    ):
        job = await _ingest(client)

        assert job["stage"] == "done"
        assert job["fact_count"] == 2
        assert job["dropped_fact_count"] == 1

    async def test_the_dropped_count_is_reported_rather_than_hidden(self, client, extracting):
        """A model citing evidence it was never shown is a signal, not an internal detail."""
        job = await _ingest(client)
        assert job["stats"]["extract_facts"]["items_out"] == 2

    async def test_attribution_comes_from_the_transcript(self, client, extracting):
        job = await _ingest(client)
        facts = (await client.get(f"/meetings/{job['meeting_id']}/facts")).json()

        decision = next(f for f in facts if f["kind"] == "decision")
        assert decision["speakers"] == ["Priya Raman"]
        assert decision["time"]["start_ms"] == 1000
        assert decision["meeting_title"] == "pricing"

    async def test_owner_and_due_survive_on_a_commitment(self, client, extracting):
        job = await _ingest(client)
        facts = (await client.get(f"/meetings/{job['meeting_id']}/facts")).json()

        commitment = next(f for f in facts if f["kind"] == "commitment")
        assert commitment["owner"] == "Tom Beckett"
        assert commitment["due"] == "Friday"

    async def test_re_running_replaces_rather_than_duplicates(self, client, extracting):
        """The node is re-drivable: a partial failure must not double the decision list."""
        from app.graphs.ingest import extract_facts_node

        job = await _ingest(client)
        state = {"job_id": job["job_id"], "meeting_id": job["meeting_id"]}

        update = await extract_facts_node(state)
        assert len(update["fact_ids"]) == 2

        facts = (await client.get(f"/meetings/{job['meeting_id']}/facts")).json()
        assert len(facts) == 2


class TestListing:
    async def test_facts_are_filterable_by_kind(self, client, extracting):
        await _ingest(client)

        commitments = (await client.get("/facts", params={"kind": "commitment"})).json()
        assert len(commitments) == 1
        assert commitments[0]["kind"] == "commitment"

    async def test_the_cross_meeting_view_carries_the_meeting_each_fact_came_from(
        self, client, extracting
    ):
        """A list of statements without their meeting is unreadable."""
        await _ingest(client, "2026-03-11-sprint.vtt")
        await _ingest(client, "2026-03-18-retro.vtt")

        listing = (await client.get("/facts")).json()
        assert len(listing) == 4
        assert {f["meeting_title"] for f in listing} == {"sprint", "retro"}

    async def test_owner_filter_matches_partially(self, client, extracting):
        await _ingest(client)
        assert len((await client.get("/facts", params={"owner": "Tom"})).json()) == 1

    async def test_an_unknown_meeting_returns_an_empty_list(self, client):
        response = await client.get("/meetings/00000000-0000-0000-0000-000000000000/facts")
        assert response.status_code == 200
        assert response.json() == []


class TestDegradation:
    async def test_no_api_key_leaves_a_recoverable_warning_not_a_failure(self, client, monkeypatch):
        """Search and retrieval do not depend on extraction, so it degrades alone."""
        from app.config import get_settings
        from app.graphs import ingest

        monkeypatch.setattr(get_settings(), "extraction_enabled", True)
        monkeypatch.setattr(ingest, "completions_available", lambda: False)

        job = await _ingest(client)

        assert job["stage"] == "done"
        assert job["fact_count"] == 0
        assert any(e["stage"] == "extract_facts" and e["recoverable"] for e in job["errors"])

    async def test_extraction_off_costs_nothing_and_says_nothing(self, client):
        """The default in this suite: no call, no warning, no facts."""
        job = await _ingest(client)

        assert job["stage"] == "done"
        assert job["fact_count"] == 0
        assert not any(e["stage"] == "extract_facts" for e in job["errors"])
