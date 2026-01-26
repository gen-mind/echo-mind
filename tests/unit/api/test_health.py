"""Unit tests for health check endpoints."""

from unittest import mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create a test client with minimal setup."""
        from api.routes.health import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_health_check_returns_ok(self, client: TestClient) -> None:
        """Test that /health returns status ok."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_check_method_not_allowed(self, client: TestClient) -> None:
        """Test that POST to /health is not allowed."""
        response = client.post("/health")

        assert response.status_code == 405

    @mock.patch("api.routes.health.get_readiness_probe")
    def test_readiness_check_healthy(
        self,
        mock_get_probe: mock.MagicMock,
        client: TestClient,
    ) -> None:
        """Test /ready when all dependencies are healthy."""
        mock_report = mock.MagicMock()
        mock_report.to_dict.return_value = {
            "healthy": True,
            "checks": {
                "database": {"healthy": True, "latency_ms": 5},
                "qdrant": {"healthy": True, "latency_ms": 10},
            },
        }

        mock_probe = mock.AsyncMock()
        mock_probe.check_health.return_value = mock_report
        mock_get_probe.return_value = mock_probe

        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is True
        assert "database" in data["checks"]
        assert "qdrant" in data["checks"]

    @mock.patch("api.routes.health.get_readiness_probe")
    def test_readiness_check_unhealthy(
        self,
        mock_get_probe: mock.MagicMock,
        client: TestClient,
    ) -> None:
        """Test /ready when a dependency is unhealthy."""
        mock_report = mock.MagicMock()
        mock_report.to_dict.return_value = {
            "healthy": False,
            "checks": {
                "database": {"healthy": True, "latency_ms": 5},
                "qdrant": {"healthy": False, "error": "Connection refused"},
            },
        }

        mock_probe = mock.AsyncMock()
        mock_probe.check_health.return_value = mock_report
        mock_get_probe.return_value = mock_probe

        response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is False
        assert data["checks"]["qdrant"]["healthy"] is False

    @mock.patch("api.routes.health.get_readiness_probe")
    def test_readiness_check_probe_exception(
        self,
        mock_get_probe: mock.MagicMock,
        client: TestClient,
    ) -> None:
        """Test /ready when probe raises exception."""
        mock_probe = mock.AsyncMock()
        mock_probe.check_health.side_effect = Exception("Probe failed")
        mock_get_probe.return_value = mock_probe

        response = client.get("/ready")

        assert response.status_code == 500
