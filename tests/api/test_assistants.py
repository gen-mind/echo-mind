"""Tests for assistant management endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_list_assistants(client: TestClient):
    """Test listing assistants returns paginated response."""
    response = client.get("/api/v1/assistants")
    assert response.status_code == 200
    data = response.json()
    assert "assistants" in data


def test_create_assistant(client: TestClient):
    """Test creating a new assistant."""
    response = client.post(
        "/api/v1/assistants",
        json={
            "name": "Test Assistant",
            "description": "A test assistant",
            "system_prompt": "You are a helpful assistant.",
            "task_prompt": "Answer questions.",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Assistant"
    assert "id" in data


def test_get_assistant_not_found(client: TestClient):
    """Test getting non-existent assistant returns 404."""
    response = client.get("/api/v1/assistants/99999")
    assert response.status_code == 404


def test_update_assistant(client: TestClient):
    """Test updating an assistant."""
    # First create an assistant
    create_response = client.post(
        "/api/v1/assistants",
        json={
            "name": "Original Name",
            "description": "Original description",
            "system_prompt": "System prompt",
            "task_prompt": "Task prompt",
        },
    )
    assert create_response.status_code == 201
    assistant_id = create_response.json()["id"]

    # Update it
    update_response = client.put(
        f"/api/v1/assistants/{assistant_id}",
        json={"name": "Updated Name"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Updated Name"


def test_delete_assistant(client: TestClient):
    """Test deleting an assistant (soft delete)."""
    # First create an assistant
    create_response = client.post(
        "/api/v1/assistants",
        json={
            "name": "To Delete",
            "description": "Will be deleted",
            "system_prompt": "System prompt",
            "task_prompt": "Task prompt",
        },
    )
    assert create_response.status_code == 201
    assistant_id = create_response.json()["id"]

    # Delete it
    delete_response = client.delete(f"/api/v1/assistants/{assistant_id}")
    assert delete_response.status_code == 204

    # Verify it's gone
    get_response = client.get(f"/api/v1/assistants/{assistant_id}")
    assert get_response.status_code == 404
