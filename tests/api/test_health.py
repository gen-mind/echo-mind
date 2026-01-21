"""
Tests for health check endpoints.
"""

import pytest
from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    """Test liveness probe returns 200."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_check(client: TestClient):
    """Test readiness probe returns health report."""
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    data = response.json()
    assert "healthy" in data
    assert "checks" in data
