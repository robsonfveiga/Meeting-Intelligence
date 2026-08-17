"""Search end to end.

Deliberately no assertions on *which* chunk ranks first — that is what the
evaluation harness measures, against a golden set, with numbers. These tests
cover behaviour the harness cannot: filters applying, expansion attaching
context, degradation without an API key, and the response carrying what the
interface needs.
"""

from pathlib import Path

import pytest

# A real file rather than a literal: transcript lines are longer than the code
# line limit, and a fixture you can open in a player is easier to reason about.
# Long enough to produce several chunks at the configured 500-character target —
# neighbour expansion has nothing to attach in a single-chunk meeting.
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


async def _search(client, query: str, **kwargs) -> dict:
    response = await client.post("/search", json={"query": query, **kwargs})
    assert response.status_code == 200
    return response.json()


class TestSearch:
    async def test_finds_content_by_meaning(self, client, ingested):
        body = await _search(client, "how long did the rollback take?")
        assert body["hits"]
        assert any("four hours" in hit["text"] for hit in body["hits"])

    async def test_finds_an_exact_figure(self, client, ingested):
        """Keyword's job — embeddings blur numbers together."""
        body = await _search(client, "eleven thousand")
        assert any("eleven thousand" in hit["text"] for hit in body["hits"])

    async def test_respects_the_limit(self, client, ingested):
        body = await _search(client, "rollback", limit=2)
        assert len(body["hits"]) <= 2

    async def test_a_query_matching_nothing_returns_empty_not_an_error(self, client, ingested):
        body = await _search(client, "zzzzz quantum badgers zzzzz")
        assert isinstance(body["hits"], list)

    async def test_rejects_an_empty_query(self, client):
        assert (await client.post("/search", json={"query": ""})).status_code == 422


class TestResponseShape:
    async def test_hits_carry_what_a_citation_needs(self, client, ingested):
        """Designed against the evidence panel so it never needs a second request."""
        hit = (await _search(client, "rollback"))["hits"][0]

        assert hit["meeting_title"]
        assert hit["speakers"]
        assert "start_ms" in hit["time"]
        assert hit["chunk_id"] and hit["meeting_id"]

    async def test_reports_per_strategy_ranks_and_timings(self, client, ingested):
        """The "how was this found" panel reads from the same payload."""
        body = await _search(client, "rollback tooling")

        assert set(body["timings_ms"]) >= {"embed", "retrieve", "fuse"}
        assert body["candidates"]
        assert any(hit["ranks"] for hit in body["hits"])

    async def test_strategy_is_reported(self, client, ingested):
        assert (await _search(client, "rollback"))["strategy"] in {"hybrid", "keyword-only"}


class TestFilters:
    async def test_filtering_to_a_meeting_excludes_everything_else(self, client, ingested):
        meeting_id = ingested["meeting_id"]
        body = await _search(client, "rollback", meeting_ids=[meeting_id])
        assert all(hit["meeting_id"] == meeting_id for hit in body["hits"])

    async def test_an_unknown_meeting_filter_returns_nothing(self, client, ingested):
        body = await _search(
            client, "rollback", meeting_ids=["00000000-0000-0000-0000-000000000000"]
        )
        assert body["hits"] == []

    async def test_filtering_by_speaker(self, client, ingested):
        body = await _search(client, "rollback", speaker="Priya Raman")
        assert all("Priya Raman" in hit["speakers"] for hit in body["hits"])


class TestNeighbourExpansion:
    async def test_off_by_default_so_metrics_measure_the_hit(self, client, ingested):
        hit = (await _search(client, "rollback"))["hits"][0]
        assert hit["context_before"] is None
        assert hit["context_after"] is None

    async def test_attaches_adjacent_chunks_when_asked(self, client, ingested):
        """limit=1 on purpose: with limit >= chunk count every chunk is a hit,
        and a hit is never its own context, so there would be nothing to attach."""
        body = await _search(client, "rollback", expand=True, limit=1)
        hit = body["hits"][0]
        assert hit["context_before"] or hit["context_after"]

    async def test_context_is_not_counted_as_a_hit(self, client, ingested):
        """Widening the window must not inflate the result count."""
        plain = await _search(client, "rollback", limit=1)
        expanded = await _search(client, "rollback", expand=True, limit=1)
        assert len(plain["hits"]) == len(expanded["hits"]) == 1


class TestDegradation:
    async def test_works_without_an_api_key_via_keyword_alone(self, client, ingested):
        from app.config import get_settings

        if get_settings().openai_api_key:
            pytest.skip("a key is configured, so the hybrid path is used")

        body = await _search(client, "rollback four hours")
        assert body["strategy"] == "keyword-only"
        assert body["hits"]
