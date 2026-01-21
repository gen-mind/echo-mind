"""
Tests for user management endpoints.
"""

import pytest
from fastapi.testclient import TestClient


def test_get_current_user_profile(client: TestClient):
    """Test getting current user profile."""
    response = client.get("/api/v1/users/me")
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "email" in data


def test_update_current_user_profile(client: TestClient):
    """Test updating current user profile."""
    response = client.put(
        "/api/v1/users/me",
        json={"first_name": "Updated", "last_name": "Name"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["first_name"] == "Updated"
    assert data["last_name"] == "Name"
