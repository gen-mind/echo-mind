"""Tests for LLM configuration endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_list_llms(client: TestClient):
    """Test listing LLMs returns paginated response."""
    response = client.get("/api/v1/llms")
    assert response.status_code == 200
    data = response.json()
    assert "llms" in data


def test_create_llm(client: TestClient):
    """Test creating a new LLM configuration."""
    response = client.post(
        "/api/v1/llms",
        json={
            "name": "Test LLM",
            "provider": "openai",
            "model_id": "gpt-4",
            "endpoint": "https://api.openai.com/v1",
            "max_tokens": 4096,
            "temperature": 0.7,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test LLM"
    assert "id" in data


def test_get_llm_not_found(client: TestClient):
    """Test getting non-existent LLM returns 404."""
    response = client.get("/api/v1/llms/99999")
    assert response.status_code == 404


def test_update_llm(client: TestClient):
    """Test updating an LLM configuration."""
    # First create an LLM
    create_response = client.post(
        "/api/v1/llms",
        json={
            "name": "Original LLM",
            "provider": "openai",
            "model_id": "gpt-4",
            "endpoint": "https://api.openai.com/v1",
        },
    )
    assert create_response.status_code == 201
    llm_id = create_response.json()["id"]

    # Update it
    update_response = client.put(
        f"/api/v1/llms/{llm_id}",
        json={"name": "Updated LLM", "temperature": 0.5},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Updated LLM"


def test_delete_llm(client: TestClient):
    """Test deleting an LLM (soft delete)."""
    # First create an LLM
    create_response = client.post(
        "/api/v1/llms",
        json={
            "name": "To Delete",
            "provider": "openai",
            "model_id": "gpt-4",
            "endpoint": "https://api.openai.com/v1",
        },
    )
    assert create_response.status_code == 201
    llm_id = create_response.json()["id"]

    # Delete it
    delete_response = client.delete(f"/api/v1/llms/{llm_id}")
    assert delete_response.status_code == 204

    # Verify it's gone
    get_response = client.get(f"/api/v1/llms/{llm_id}")
    assert get_response.status_code == 404


def test_test_llm_connection(client: TestClient):
    """Test LLM connection test endpoint."""
    # First create an LLM
    create_response = client.post(
        "/api/v1/llms",
        json={
            "name": "Connection Test",
            "provider": "openai",
            "model_id": "gpt-4",
            "endpoint": "https://api.openai.com/v1",
        },
    )
    assert create_response.status_code == 201
    llm_id = create_response.json()["id"]

    # Test connection
    test_response = client.post(f"/api/v1/llms/{llm_id}/test")
    assert test_response.status_code == 200
    data = test_response.json()
    assert "success" in data
    assert "message" in data
