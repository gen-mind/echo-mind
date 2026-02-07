"""Unit tests for Google OAuth2 endpoints."""

import time
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.google_oauth import (
    _cleanup_expired_states,
    _google_oauth_states,
    _STATE_TTL_SECONDS,
    router,
)


@pytest.fixture
def _mock_user() -> MagicMock:
    """Create a mock authenticated user with id=1."""
    user = MagicMock()
    user.id = 1
    user.email = "test@example.com"
    return user


@pytest.fixture
def _mock_db() -> MagicMock:
    """Create a mock async DB session."""
    db = MagicMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def client(_mock_user: MagicMock, _mock_db: MagicMock) -> TestClient:
    """Create a test client with the Google OAuth router and mocked deps."""
    from api.dependencies import get_current_user, get_db_session

    app = FastAPI()
    app.include_router(router, prefix="/google")

    async def override_user() -> MagicMock:
        return _mock_user

    async def override_db() -> AsyncGenerator[MagicMock, None]:
        yield _mock_db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db_session] = override_db

    return TestClient(app)


class TestGoogleAuthUrl:
    """Tests for GET /auth/url endpoint."""

    def test_generates_url_with_all_scopes(self, client: TestClient) -> None:
        """Test URL generation includes all scopes."""
        with patch("api.routes.google_oauth.get_settings") as mock_settings:
            settings = MagicMock()
            settings.google_client_id = "test-client-id"
            settings.google_client_secret = "test-secret"
            settings.google_redirect_uri = "https://example.com/callback"
            mock_settings.return_value = settings

            response = client.get("/google/auth/url")

        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert "accounts.google.com" in data["url"]
        assert "test-client-id" in data["url"]
        assert "offline" in data["url"]

    def test_returns_501_when_not_configured(self, client: TestClient) -> None:
        """Test 501 when Google OAuth is not configured."""
        with patch("api.routes.google_oauth.get_settings") as mock_settings:
            settings = MagicMock()
            settings.google_client_id = None
            settings.google_redirect_uri = None
            mock_settings.return_value = settings

            response = client.get("/google/auth/url")

        assert response.status_code == 501

    def test_state_stored_in_memory(self, client: TestClient) -> None:
        """Test that state is stored in memory for CSRF validation."""
        _google_oauth_states.clear()

        with patch("api.routes.google_oauth.get_settings") as mock_settings:
            settings = MagicMock()
            settings.google_client_id = "test-client-id"
            settings.google_client_secret = "test-secret"
            settings.google_redirect_uri = "https://example.com/callback"
            mock_settings.return_value = settings

            client.get("/google/auth/url")

        assert len(_google_oauth_states) == 1
        state_key = next(iter(_google_oauth_states))
        user_id, created_at = _google_oauth_states[state_key]
        assert user_id == 1
        assert isinstance(created_at, float)

        _google_oauth_states.clear()


class TestGoogleAuthCallback:
    """Tests for GET /auth/callback endpoint."""

    def test_callback_with_error_redirects(self, client: TestClient) -> None:
        """Test callback with error parameter redirects to frontend."""
        with patch("api.routes.google_oauth.get_settings") as mock_settings:
            settings = MagicMock()
            settings.oauth_frontend_url = "https://app.example.com"
            mock_settings.return_value = settings

            response = client.get(
                "/google/auth/callback",
                params={"error": "access_denied"},
                follow_redirects=False,
            )

        assert response.status_code == 302
        assert "error=access_denied" in response.headers["location"]

    def test_callback_invalid_state_returns_400(self, client: TestClient) -> None:
        """Test callback with invalid state returns 400."""
        response = client.get(
            "/google/auth/callback",
            params={"code": "auth_code", "state": "invalid_state"},
        )

        assert response.status_code == 400

    def test_callback_missing_state_returns_400(self, client: TestClient) -> None:
        """Test callback without state returns 400."""
        response = client.get(
            "/google/auth/callback",
            params={"code": "auth_code"},
        )

        assert response.status_code == 400

    def test_callback_missing_code_returns_400(self, client: TestClient) -> None:
        """Test callback without code returns 400."""
        _google_oauth_states["test_state"] = (1, time.monotonic())

        response = client.get(
            "/google/auth/callback",
            params={"state": "test_state"},
        )

        assert response.status_code == 400
        _google_oauth_states.clear()

    def test_callback_success_creates_credentials(
        self, client: TestClient, _mock_db: MagicMock
    ) -> None:
        """Test successful callback creates credentials and redirects."""
        _google_oauth_states["valid_state"] = (1, time.monotonic())

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        _mock_db.execute = AsyncMock(return_value=mock_result)

        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/gmail.readonly",
        }

        with (
            patch("api.routes.google_oauth.get_settings") as mock_settings,
            patch("api.routes.google_oauth.httpx.AsyncClient") as mock_client_cls,
        ):
            settings = MagicMock()
            settings.google_client_id = "test-client-id"
            settings.google_client_secret = "test-secret"
            settings.google_redirect_uri = "https://example.com/callback"
            settings.oauth_frontend_url = "https://app.example.com"
            mock_settings.return_value = settings

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_token_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            response = client.get(
                "/google/auth/callback",
                params={"code": "auth_code", "state": "valid_state"},
                follow_redirects=False,
            )

        assert response.status_code == 302
        assert "/connectors/google/setup" in response.headers["location"]
        assert "valid_state" not in _google_oauth_states
        assert _mock_db.add.called

        _google_oauth_states.clear()

    def test_callback_token_exchange_failure_returns_401(
        self, client: TestClient
    ) -> None:
        """Test callback returns 401 when token exchange fails."""
        _google_oauth_states["fail_state"] = (1, time.monotonic())

        mock_token_response = MagicMock()
        mock_token_response.status_code = 400
        mock_token_response.text = "invalid_grant"

        with (
            patch("api.routes.google_oauth.get_settings") as mock_settings,
            patch("api.routes.google_oauth.httpx.AsyncClient") as mock_client_cls,
        ):
            settings = MagicMock()
            settings.google_client_id = "test-client-id"
            settings.google_client_secret = "test-secret"
            settings.google_redirect_uri = "https://example.com/callback"
            mock_settings.return_value = settings

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_token_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            response = client.get(
                "/google/auth/callback",
                params={"code": "bad_code", "state": "fail_state"},
            )

        assert response.status_code == 401
        _google_oauth_states.clear()

    def test_callback_no_refresh_token_returns_401(
        self, client: TestClient
    ) -> None:
        """Test callback returns 401 when no refresh token received."""
        _google_oauth_states["no_refresh_state"] = (1, time.monotonic())

        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {
            "access_token": "test_access_token",
            "expires_in": 3600,
        }

        with (
            patch("api.routes.google_oauth.get_settings") as mock_settings,
            patch("api.routes.google_oauth.httpx.AsyncClient") as mock_client_cls,
        ):
            settings = MagicMock()
            settings.google_client_id = "test-client-id"
            settings.google_client_secret = "test-secret"
            settings.google_redirect_uri = "https://example.com/callback"
            mock_settings.return_value = settings

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_token_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            response = client.get(
                "/google/auth/callback",
                params={"code": "auth_code", "state": "no_refresh_state"},
            )

        assert response.status_code == 401
        assert "refresh token" in response.json()["detail"].lower()
        _google_oauth_states.clear()


class TestGoogleAuthStatus:
    """Tests for GET /auth/status endpoint."""

    def test_status_not_connected(
        self, client: TestClient, _mock_db: MagicMock
    ) -> None:
        """Test status when user has no Google credentials."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        _mock_db.execute = AsyncMock(return_value=mock_result)

        response = client.get("/google/auth/status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["granted_scopes"] == []

    def test_status_connected(
        self, client: TestClient, _mock_db: MagicMock
    ) -> None:
        """Test status when user has Google credentials."""
        mock_credential = MagicMock()
        mock_credential.granted_scopes = [
            "https://www.googleapis.com/auth/gmail.readonly"
        ]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_credential
        _mock_db.execute = AsyncMock(return_value=mock_result)

        response = client.get("/google/auth/status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert len(data["granted_scopes"]) == 1


class TestGoogleAuthRevoke:
    """Tests for DELETE /auth endpoint."""

    def test_revoke_no_credentials_returns_404(
        self, client: TestClient, _mock_db: MagicMock
    ) -> None:
        """Test revoke when user has no credentials."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        _mock_db.execute = AsyncMock(return_value=mock_result)

        response = client.delete("/google/auth")

        assert response.status_code == 404

    def test_revoke_success(
        self, client: TestClient, _mock_db: MagicMock
    ) -> None:
        """Test successful revoke deletes credentials."""
        mock_credential = MagicMock()
        mock_credential.access_token = "test_token"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_credential
        _mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("api.routes.google_oauth.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = MagicMock(status_code=200)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            response = client.delete("/google/auth")

        assert response.status_code == 204
        _mock_db.delete.assert_called_once_with(mock_credential)
        _mock_db.commit.assert_called()


class TestCleanupExpiredStates:
    """Tests for TTL-based state cleanup."""

    def test_cleanup_removes_expired_states(self) -> None:
        """Test expired states are removed."""
        _google_oauth_states.clear()

        _google_oauth_states["expired"] = (
            1,
            time.monotonic() - _STATE_TTL_SECONDS - 10,
        )
        _google_oauth_states["valid"] = (2, time.monotonic())

        _cleanup_expired_states()

        assert "expired" not in _google_oauth_states
        assert "valid" in _google_oauth_states

        _google_oauth_states.clear()

    def test_cleanup_noop_when_empty(self) -> None:
        """Test cleanup does nothing on empty dict."""
        _google_oauth_states.clear()

        _cleanup_expired_states()

        assert len(_google_oauth_states) == 0

    def test_cleanup_keeps_valid_states(self) -> None:
        """Test cleanup preserves non-expired states."""
        _google_oauth_states.clear()

        _google_oauth_states["fresh1"] = (1, time.monotonic())
        _google_oauth_states["fresh2"] = (2, time.monotonic())

        _cleanup_expired_states()

        assert len(_google_oauth_states) == 2

        _google_oauth_states.clear()
