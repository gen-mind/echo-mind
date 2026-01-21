"""Tests for connector management endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_list_connectors(client: TestClient):
    """Test listing connectors returns paginated response."""
    response = client.get("/api/v1/connectors")
    assert response.status_code == 200
    data = response.json()
    assert "connectors" in data


def test_create_connector(client: TestClient):
    """Test creating a new connector."""
    response = client.post(
        "/api/v1/connectors",
        json={
            "name": "Test Connector",
            "type": "web",
            "config": {"url": "https://example.com"},
            "refresh_freq_minutes": 60,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Connector"
    assert "id" in data


def test_get_connector_not_found(client: TestClient):
    """Test getting non-existent connector returns 404."""
    response = client.get("/api/v1/connectors/99999")
    assert response.status_code == 404


def test_update_connector(client: TestClient):
    """Test updating a connector."""
    # First create a connector
    create_response = client.post(
        "/api/v1/connectors",
        json={
            "name": "Original Connector",
            "type": "web",
            "config": {"url": "https://example.com"},
        },
    )
    assert create_response.status_code == 201
    connector_id = create_response.json()["id"]

    # Update it
    update_response = client.put(
        f"/api/v1/connectors/{connector_id}",
        json={"name": "Updated Connector"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Updated Connector"


def test_delete_connector(client: TestClient):
    """Test deleting a connector (soft delete)."""
    # First create a connector
    create_response = client.post(
        "/api/v1/connectors",
        json={
            "name": "To Delete",
            "type": "web",
            "config": {"url": "https://example.com"},
        },
    )
    assert create_response.status_code == 201
    connector_id = create_response.json()["id"]

    # Delete it
    delete_response = client.delete(f"/api/v1/connectors/{connector_id}")
    assert delete_response.status_code == 204

    # Verify it's gone
    get_response = client.get(f"/api/v1/connectors/{connector_id}")
    assert get_response.status_code == 404


def test_trigger_sync(client: TestClient):
    """Test triggering a connector sync."""
    # First create a connector
    create_response = client.post(
        "/api/v1/connectors",
        json={
            "name": "Sync Test",
            "type": "web",
            "config": {"url": "https://example.com"},
        },
    )
    assert create_response.status_code == 201
    connector_id = create_response.json()["id"]

    # Trigger sync
    sync_response = client.post(f"/api/v1/connectors/{connector_id}/sync")
    assert sync_response.status_code == 200
    data = sync_response.json()
    assert "success" in data
    assert "message" in data


def test_get_connector_status(client: TestClient):
    """Test getting connector status."""
    # First create a connector
    create_response = client.post(
        "/api/v1/connectors",
        json={
            "name": "Status Test",
            "type": "web",
            "config": {"url": "https://example.com"},
        },
    )
    assert create_response.status_code == 201
    connector_id = create_response.json()["id"]

    # Get status
    status_response = client.get(f"/api/v1/connectors/{connector_id}/status")
    assert status_response.status_code == 200
    data = status_response.json()
    assert "status" in data
    assert "docs_analyzed" in data
