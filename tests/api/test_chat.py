"""Tests for chat session and message endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_list_chat_sessions(client: TestClient):
    """Test listing chat sessions."""
    response = client.get("/api/v1/chat/sessions")
    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data


def test_create_chat_session_assistant_not_found(client: TestClient):
    """Test creating session with non-existent assistant returns 404."""
    response = client.post(
        "/api/v1/chat/sessions",
        json={
            "assistant_id": 99999,
            "title": "Test Chat",
        },
    )
    assert response.status_code == 404


def test_get_chat_session_not_found(client: TestClient):
    """Test getting non-existent session returns 404."""
    response = client.get("/api/v1/chat/sessions/99999")
    assert response.status_code == 404


def test_delete_chat_session_not_found(client: TestClient):
    """Test deleting non-existent session returns 404."""
    response = client.delete("/api/v1/chat/sessions/99999")
    assert response.status_code == 404


def test_list_session_messages_not_found(client: TestClient):
    """Test listing messages for non-existent session returns 404."""
    response = client.get("/api/v1/chat/sessions/99999/messages")
    assert response.status_code == 404


def test_get_message_not_found(client: TestClient):
    """Test getting non-existent message returns 404."""
    response = client.get("/api/v1/chat/messages/99999")
    assert response.status_code == 404


def test_get_message_sources_not_found(client: TestClient):
    """Test getting sources for non-existent message returns 404."""
    response = client.get("/api/v1/chat/messages/99999/sources")
    assert response.status_code == 404


def test_submit_feedback_message_not_found(client: TestClient):
    """Test submitting feedback for non-existent message returns 404."""
    response = client.post(
        "/api/v1/chat/messages/99999/feedback",
        json={
            "is_positive": True,
            "feedback_text": "Great response!",
        },
    )
    assert response.status_code == 404
