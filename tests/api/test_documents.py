"""Tests for document management endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_list_documents(client: TestClient):
    """Test listing documents returns paginated response."""
    response = client.get("/api/v1/documents")
    assert response.status_code == 200
    data = response.json()
    assert "documents" in data


def test_list_documents_with_connector_filter(client: TestClient):
    """Test listing documents filtered by connector."""
    response = client.get("/api/v1/documents?connector_id=1")
    assert response.status_code == 200
    data = response.json()
    assert "documents" in data


def test_get_document_not_found(client: TestClient):
    """Test getting non-existent document returns 404."""
    response = client.get("/api/v1/documents/99999")
    assert response.status_code == 404


def test_search_documents(client: TestClient):
    """Test searching documents."""
    response = client.get("/api/v1/documents/search?query=test")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data


def test_delete_document_not_found(client: TestClient):
    """Test deleting non-existent document returns 404."""
    response = client.delete("/api/v1/documents/99999")
    assert response.status_code == 404
