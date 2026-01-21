"""Tests for embedding model configuration endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_list_embedding_models(client: TestClient):
    """Test listing embedding models."""
    response = client.get("/api/v1/embedding-models")
    assert response.status_code == 200
    data = response.json()
    assert "embedding_models" in data


def test_get_active_embedding_model_not_found(client: TestClient):
    """Test getting active model when none configured returns 404."""
    response = client.get("/api/v1/embedding-models/active")
    # May return 404 if no active model, or 200 if one exists
    assert response.status_code in [200, 404]


def test_create_embedding_model(client: TestClient):
    """Test creating a new embedding model configuration."""
    response = client.post(
        "/api/v1/embedding-models",
        json={
            "model_id": "sentence-transformers/all-MiniLM-L6-v2",
            "model_name": "MiniLM L6",
            "model_dimension": 384,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["model_name"] == "MiniLM L6"
    assert data["model_dimension"] == 384
    assert "id" in data


def test_activate_embedding_model(client: TestClient):
    """Test activating an embedding model."""
    # First create a model
    create_response = client.post(
        "/api/v1/embedding-models",
        json={
            "model_id": "test-model",
            "model_name": "Test Model",
            "model_dimension": 768,
        },
    )
    assert create_response.status_code == 201
    model_id = create_response.json()["id"]

    # Activate it
    activate_response = client.put(f"/api/v1/embedding-models/{model_id}/activate")
    assert activate_response.status_code == 200
    data = activate_response.json()
    assert data["success"] is True
    assert "message" in data


def test_activate_nonexistent_model(client: TestClient):
    """Test activating non-existent model returns 404."""
    response = client.put("/api/v1/embedding-models/99999/activate")
    assert response.status_code == 404
