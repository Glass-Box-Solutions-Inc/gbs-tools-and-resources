"""
Tests for Spectacles Health API Endpoints
"""

import pytest
from unittest.mock import patch, MagicMock


class TestHealthEndpoints:
    """Test health check endpoints"""

    def test_health_check_basic(self, test_client):
        """Test basic health check returns healthy status"""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "spectacles"
        assert "timestamp" in data
        assert "environment" in data

    def test_health_check_detailed(self, test_client):
        """Test detailed health check returns component status"""
        response = test_client.get("/health/detailed")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert "checks" in data

        # Should have checks for each component
        checks = data["checks"]
        assert "database" in checks
        assert "slack" in checks
        assert "browserless" in checks
        assert "vlm" in checks
        assert "gcp" in checks

    def test_readiness_check(self, test_client):
        """Test readiness check for K8s/Cloud Run"""
        response = test_client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert "ready" in data
        # In test environment, should be ready
        assert data["ready"] is True

    def test_liveness_check(self, test_client):
        """Test liveness check returns alive"""
        response = test_client.get("/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["alive"] is True


class TestRootEndpoint:
    """Test root endpoint"""

    def test_root_returns_service_info(self, test_client):
        """Test root endpoint returns service information"""
        response = test_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "spectacles"
        assert data["version"] == "1.0.0"
        assert "description" in data
        assert data["health"] == "/health"
