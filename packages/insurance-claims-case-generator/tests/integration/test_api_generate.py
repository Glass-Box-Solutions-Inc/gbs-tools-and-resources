"""
Integration tests for POST /api/v1/generate.

Uses httpx AsyncClient with ASGI transport — no real network.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from claims_generator.api.job_store import reset_job_store
from claims_generator.main import create_app


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    """Ensure a fresh job store for each test."""
    reset_job_store()
    yield
    reset_job_store()


@pytest_asyncio.fixture
async def client():
    """Async httpx client connected to the ASGI app."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
class TestGenerateEndpoint:
    """POST /api/v1/generate — synchronous single case."""

    async def test_generate_standard_claim_returns_200(self, client: AsyncClient) -> None:
        """Standard claim generation returns 200 with valid manifest."""
        resp = await client.post(
            "/api/v1/generate",
            json={"scenario": "standard_claim", "seed": 42},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario_slug"] == "standard_claim"
        assert data["seed"] == 42
        assert data["document_count"] >= 8
        assert len(data["document_events"]) == data["document_count"]
        assert len(data["stages_visited"]) > 0
        assert data["zip_size_bytes"] > 0

    async def test_generate_produces_non_empty_zip(self, client: AsyncClient) -> None:
        """zip_size_bytes must be > 1000 when PDFs are generated."""
        resp = await client.post(
            "/api/v1/generate",
            json={"scenario": "standard_claim", "seed": 7, "generate_pdfs": True},
        )
        assert resp.status_code == 200
        assert resp.json()["zip_size_bytes"] > 1000

    async def test_generate_no_pdfs_mode(self, client: AsyncClient) -> None:
        """generate_pdfs=False must return zip_size_bytes > 0 (just the manifest)."""
        resp = await client.post(
            "/api/v1/generate",
            json={"scenario": "standard_claim", "seed": 1, "generate_pdfs": False},
        )
        assert resp.status_code == 200
        # Even without PDFs the ZIP contains a manifest.json
        assert resp.json()["zip_size_bytes"] > 0

    async def test_generate_litigated_qme(self, client: AsyncClient) -> None:
        """Litigated QME scenario must produce ≥ 18 documents."""
        resp = await client.post(
            "/api/v1/generate",
            json={"scenario": "litigated_qme", "seed": 99},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_count"] >= 18, (
            f"litigated_qme expected ≥18 docs, got {data['document_count']}"
        )

    @pytest.mark.parametrize(
        "scenario",
        [
            "standard_claim",
            "cumulative_trauma",
            "litigated_qme",
            "denied_claim",
            "death_claim",
            "ptd_claim",
            "psychiatric_overlay",
            "multi_employer",
            "split_carrier",
            "complex_lien",
            "expedited_hearing",
            "qme_dispute_only",
            "sjdb_voucher",
        ],
    )
    async def test_all_13_scenarios_return_valid_case(
        self, client: AsyncClient, scenario: str
    ) -> None:
        """Every scenario must return a valid case with at least 8 document events."""
        resp = await client.post(
            "/api/v1/generate",
            json={"scenario": scenario, "seed": 1, "generate_pdfs": False},
        )
        assert resp.status_code == 200, f"{scenario} returned {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["scenario_slug"] == scenario
        assert data["document_count"] >= 8, (
            f"{scenario}: expected ≥8 docs, got {data['document_count']}"
        )

    async def test_generate_invalid_scenario_returns_422(self, client: AsyncClient) -> None:
        """Unknown scenario slug must return 422."""
        resp = await client.post(
            "/api/v1/generate",
            json={"scenario": "nonexistent_scenario", "seed": 1},
        )
        assert resp.status_code == 422

    async def test_generate_document_events_have_required_fields(self, client: AsyncClient) -> None:
        """Each document_event in the response must have required fields."""
        resp = await client.post(
            "/api/v1/generate",
            json={"scenario": "standard_claim", "seed": 5, "generate_pdfs": False},
        )
        assert resp.status_code == 200
        for event in resp.json()["document_events"]:
            assert "event_id" in event
            assert "document_type" in event
            assert "subtype_slug" in event
            assert "title" in event
            assert "event_date" in event
            assert "stage" in event

    async def test_generate_reproducible_with_same_seed(self, client: AsyncClient) -> None:
        """Same scenario + seed must produce the same document count."""
        r1 = await client.post(
            "/api/v1/generate",
            json={"scenario": "standard_claim", "seed": 42, "generate_pdfs": False},
        )
        r2 = await client.post(
            "/api/v1/generate",
            json={"scenario": "standard_claim", "seed": 42, "generate_pdfs": False},
        )
        assert r1.json()["document_count"] == r2.json()["document_count"]
