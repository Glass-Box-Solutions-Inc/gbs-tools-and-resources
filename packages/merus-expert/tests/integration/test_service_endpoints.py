"""
Integration tests for merus-expert service endpoints.

Tests field validation, error responses, and health check.
No live MerusCase API calls — dependencies are overridden via FastAPI's
dependency_overrides mechanism, which is cleaner than patching lru_cache
singletons and avoids import-order side effects.

Run with: pytest tests/integration/ -v -m "not live"

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

import os
import pytest
from unittest.mock import AsyncMock

# Set required env vars before any service module is imported.
# These values are used by service/auth.py and service/dependencies.py
# at import time via os.environ.get().
os.environ.setdefault("MERUS_API_KEY", "test-api-key-for-testing")
os.environ.setdefault("MERUSCASE_ACCESS_TOKEN", "test-token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")


@pytest.fixture(scope="module")
def test_client():
    """
    FastAPI TestClient with all agent dependencies replaced by mocks.

    Uses FastAPI's built-in dependency_overrides so no monkey-patching of
    lru_cache singletons is needed.  Module scope avoids re-creating the
    client for every test, which would trigger the lifespan handler repeatedly.
    """
    from fastapi.testclient import TestClient
    from service.main import app
    from service.dependencies import get_merus_agent, get_claude_agent

    mock_merus = AsyncMock()
    mock_claude = AsyncMock()

    app.dependency_overrides[get_merus_agent] = lambda: mock_merus
    app.dependency_overrides[get_claude_agent] = lambda: mock_claude

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    # Clean up overrides after the module is done so other test modules are
    # not affected if the app object is shared.
    app.dependency_overrides.clear()


class TestHealthCheck:
    def test_health_returns_200(self, test_client):
        """GET /health should return 200 without any auth header."""
        response = test_client.get("/health")
        assert response.status_code == 200

    def test_health_response_structure(self, test_client):
        """Health response should carry status, timestamp, service, and version fields."""
        response = test_client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "merus-expert"
        assert "timestamp" in data
        assert "version" in data


class TestAuthentication:
    def test_cases_requires_api_key(self, test_client):
        """GET /api/cases/search without X-API-Key header should return 401."""
        response = test_client.get("/api/cases/search?query=Smith")
        assert response.status_code == 401

    def test_invalid_api_key_returns_401(self, test_client):
        """GET /api/cases/search with a wrong API key should return 401."""
        response = test_client.get(
            "/api/cases/search?query=Smith",
            headers={"X-API-Key": "definitely-wrong-key"},
        )
        assert response.status_code == 401


class TestFieldValidation:
    def test_bill_time_missing_required_fields_returns_422(self, test_client):
        """POST /api/billing/time with only case_search (no hours, no description) → 422."""
        response = test_client.post(
            "/api/billing/time",
            json={"case_search": "Smith"},
            headers={"X-API-Key": "test-api-key-for-testing"},
        )
        assert response.status_code == 422

    def test_bill_time_negative_hours_returns_422(self, test_client):
        """POST /api/billing/time with hours <= 0 should fail Pydantic gt=0 validation."""
        response = test_client.post(
            "/api/billing/time",
            json={"case_search": "Smith", "hours": -1.0, "description": "Test"},
            headers={"X-API-Key": "test-api-key-for-testing"},
        )
        assert response.status_code == 422

    def test_add_cost_zero_amount_returns_422(self, test_client):
        """POST /api/billing/cost with amount=0 should fail Pydantic gt=0 validation."""
        response = test_client.post(
            "/api/billing/cost",
            json={"case_search": "Smith", "amount": 0, "description": "Test"},
            headers={"X-API-Key": "test-api-key-for-testing"},
        )
        assert response.status_code == 422

    def test_bulk_billing_empty_entries_returns_422(self, test_client):
        """POST /api/billing/time/bulk with entries=[] should fail min_length=1 validation."""
        response = test_client.post(
            "/api/billing/time/bulk",
            json={"entries": []},
            headers={"X-API-Key": "test-api-key-for-testing"},
        )
        assert response.status_code == 422

    def test_add_cost_negative_amount_returns_422(self, test_client):
        """POST /api/billing/cost with a negative amount should fail gt=0 validation."""
        response = test_client.post(
            "/api/billing/cost",
            json={"case_search": "Smith", "amount": -50.00, "description": "Test"},
            headers={"X-API-Key": "test-api-key-for-testing"},
        )
        assert response.status_code == 422


class TestDocsAvailable:
    def test_openapi_docs_accessible(self, test_client):
        """FastAPI /docs (Swagger UI) should be accessible without auth."""
        response = test_client.get("/docs")
        assert response.status_code == 200

    def test_openapi_json_accessible(self, test_client):
        """GET /openapi.json should return a valid OpenAPI schema with the /health path."""
        response = test_client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "paths" in data
        assert "/health" in data["paths"]
