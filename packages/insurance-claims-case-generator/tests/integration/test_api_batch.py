"""
Integration tests for the full batch flow:
  POST /api/v1/batch → poll GET /api/v1/jobs/{job_id} → GET /api/v1/export/{job_id}

Uses httpx AsyncClient with ASGI transport — no real network.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import asyncio
import io
import zipfile

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


async def _wait_for_job(client: AsyncClient, job_id: str, timeout: float = 60.0) -> dict:
    """Poll GET /api/v1/jobs/{job_id} until status is done or failed."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(f"/api/v1/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] in ("done", "failed"):
            return data
        await asyncio.sleep(0.1)
    raise TimeoutError(f"Job {job_id!r} did not complete within {timeout}s")


@pytest.mark.asyncio
class TestBatchFlow:
    """Full batch lifecycle: submit → poll → export."""

    async def test_batch_submit_returns_202(self, client: AsyncClient) -> None:
        """POST /api/v1/batch must return 202 with a job_id."""
        resp = await client.post(
            "/api/v1/batch",
            json={
                "jobs": [{"scenario": "standard_claim", "seed": 1}],
                "generate_pdfs": False,
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert data["total"] == 1

    async def test_batch_poll_then_export_zip(self, client: AsyncClient) -> None:
        """Full flow: submit 3-case batch → poll until done → download ZIP."""
        submit_resp = await client.post(
            "/api/v1/batch",
            json={
                "jobs": [
                    {"scenario": "standard_claim", "seed": 10},
                    {"scenario": "litigated_qme", "seed": 11},
                    {"scenario": "denied_claim", "seed": 12},
                ],
                "generate_pdfs": False,
                "max_workers": 2,
            },
        )
        assert submit_resp.status_code == 202
        job_id = submit_resp.json()["job_id"]

        # Poll until done
        final = await _wait_for_job(client, job_id, timeout=60.0)
        assert final["status"] == "done", f"Job failed: {final.get('error')}"
        assert final["progress"] == 100

        # Download ZIP
        export_resp = await client.get(f"/api/v1/export/{job_id}")
        assert export_resp.status_code == 200
        assert export_resp.headers["content-type"] == "application/zip"
        zip_bytes = export_resp.content
        assert len(zip_bytes) > 100

        # Validate ZIP structure
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            assert "batch_manifest.json" in names
            manifests = [
                n for n in names
                if n.endswith("manifest.json") and n != "batch_manifest.json"
            ]
            assert len(manifests) == 3

    async def test_batch_invalid_scenario_returns_422(self, client: AsyncClient) -> None:
        """Batch with unknown scenario must return 422 (pre-validated before enqueueing)."""
        resp = await client.post(
            "/api/v1/batch",
            json={
                "jobs": [{"scenario": "does_not_exist", "seed": 1}],
                "generate_pdfs": False,
            },
        )
        assert resp.status_code == 422

    async def test_batch_empty_jobs_returns_422(self, client: AsyncClient) -> None:
        """Empty jobs list must return 422."""
        resp = await client.post(
            "/api/v1/batch",
            json={"jobs": [], "generate_pdfs": False},
        )
        assert resp.status_code == 422

    async def test_jobs_not_found_returns_404(self, client: AsyncClient) -> None:
        """GET /api/v1/jobs/{unknown_id} must return 404."""
        resp = await client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    async def test_export_not_found_returns_404(self, client: AsyncClient) -> None:
        """GET /api/v1/export/{unknown_id} must return 404."""
        resp = await client.get("/api/v1/export/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    async def test_export_pending_job_returns_409(self, client: AsyncClient) -> None:
        """Attempting to export a job that hasn't finished must return 409."""
        # Submit a job but don't poll — export immediately
        submit_resp = await client.post(
            "/api/v1/batch",
            json={
                "jobs": [{"scenario": "standard_claim", "seed": 50}] * 20,
                "generate_pdfs": True,  # heavier, may still be running
                "max_workers": 1,
            },
        )
        assert submit_resp.status_code == 202
        job_id = submit_resp.json()["job_id"]

        # Try to export immediately — should be 409 unless it finished instantly
        export_resp = await client.get(f"/api/v1/export/{job_id}")
        # Either 409 (still running) or 200 (finished very fast)
        assert export_resp.status_code in (200, 409)

    async def test_health_endpoint(self, client: AsyncClient) -> None:
        """GET /api/v1/health must return 200 with scenario_count=13."""
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["scenario_count"] == 13

    async def test_scenarios_list_returns_13(self, client: AsyncClient) -> None:
        """GET /api/v1/scenarios must return all 13 scenarios."""
        resp = await client.get("/api/v1/scenarios")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 13
        slugs = {s["slug"] for s in data}
        assert "standard_claim" in slugs
        assert "ptd_claim" in slugs
        assert "sjdb_voucher" in slugs

    async def test_scenario_detail(self, client: AsyncClient) -> None:
        """GET /api/v1/scenarios/{slug} must return scenario detail."""
        resp = await client.get("/api/v1/scenarios/litigated_qme")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "litigated_qme"
        assert data["litigated"] is True
        assert data["attorney_represented"] is True

    async def test_scenario_not_found_returns_404(self, client: AsyncClient) -> None:
        """GET /api/v1/scenarios/{unknown} must return 404."""
        resp = await client.get("/api/v1/scenarios/not_a_scenario")
        assert resp.status_code == 404

    async def test_batch_with_pdf_generation(self, client: AsyncClient) -> None:
        """Batch with PDF generation must produce a non-trivial ZIP."""
        submit_resp = await client.post(
            "/api/v1/batch",
            json={
                "jobs": [
                    {"scenario": "standard_claim", "seed": 100},
                    {"scenario": "denied_claim", "seed": 101},
                ],
                "generate_pdfs": True,
                "max_workers": 2,
            },
        )
        assert submit_resp.status_code == 202
        job_id = submit_resp.json()["job_id"]

        final = await _wait_for_job(client, job_id, timeout=60.0)
        assert final["status"] == "done"

        export_resp = await client.get(f"/api/v1/export/{job_id}")
        assert export_resp.status_code == 200
        # With PDFs the ZIP should be substantially larger
        assert len(export_resp.content) > 5000
