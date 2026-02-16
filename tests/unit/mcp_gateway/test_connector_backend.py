"""Unit tests for mcp_gateway.backends.connector_backend."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mcp_gateway.backends.connector_backend import (
    ConnectorBackend,
    _sanitize_config,
)


class TestSanitizeConfig:
    """Tests for _sanitize_config utility."""

    def test_redacts_token_keys(self) -> None:
        """Keys containing 'token' are sanitized."""
        config = {"access_token": "abc", "refresh_token": "xyz", "host": "h"}
        result = _sanitize_config(config)
        assert result["access_token"] == "***"
        assert result["refresh_token"] == "***"
        assert result["host"] == "h"

    def test_redacts_secret_keys(self) -> None:
        """Keys containing 'secret' are sanitized."""
        config = {"client_secret": "sec"}
        result = _sanitize_config(config)
        assert result["client_secret"] == "***"

    def test_redacts_password_keys(self) -> None:
        """Keys containing 'password' are sanitized."""
        config = {"password": "pass123"}
        result = _sanitize_config(config)
        assert result["password"] == "***"

    def test_returns_empty_for_none(self) -> None:
        """None config returns empty dict."""
        assert _sanitize_config(None) == {}

    def test_returns_empty_for_empty(self) -> None:
        """Empty config returns empty dict."""
        assert _sanitize_config({}) == {}

    def test_preserves_safe_keys(self) -> None:
        """Non-sensitive keys are preserved."""
        config = {"url": "https://example.com", "scope": "read"}
        result = _sanitize_config(config)
        assert result == config


def _make_connector(**kwargs: Any) -> MagicMock:
    """Create a mock Connector ORM instance."""
    connector = MagicMock()
    connector.id = kwargs.get("id", 1)
    connector.name = kwargs.get("name", "Test Connector")
    connector.type = kwargs.get("type", "teams")
    connector.status = kwargs.get("status", "active")
    connector.status_message = kwargs.get("status_message", None)
    connector.state = kwargs.get("state", {})
    connector.config = kwargs.get("config", {})
    connector.last_sync_at = kwargs.get(
        "last_sync_at", datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    connector.docs_analyzed = kwargs.get("docs_analyzed", 42)
    connector.scope = kwargs.get("scope", "user")
    connector.scope_id = kwargs.get("scope_id", None)
    connector.refresh_freq_minutes = kwargs.get("refresh_freq_minutes", 60)
    connector.user_id = kwargs.get("user_id", 1)
    return connector


class TestListConnectors:
    """Tests for ConnectorBackend.list_connectors."""

    @pytest.mark.asyncio
    async def test_returns_connector_summaries(self) -> None:
        """Lists connectors with summary fields."""
        mock_session = AsyncMock(spec=AsyncSession)
        session_factory = MagicMock(spec=async_sessionmaker)
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__ = AsyncMock(return_value=mock_session)
        ctx_mgr.__aexit__ = AsyncMock(return_value=False)
        session_factory.return_value = ctx_mgr

        connectors = [_make_connector(id=1, name="C1"), _make_connector(id=2, name="C2")]

        with patch(
            "mcp_gateway.backends.connector_backend.connector_crud"
        ) as mock_crud:
            mock_crud.get_by_user = AsyncMock(return_value=connectors)

            backend = ConnectorBackend(session_factory=session_factory)
            result = await backend.list_connectors(user_id=1)

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["name"] == "C1"
        assert result[1]["id"] == 2

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_connectors(self) -> None:
        """Returns empty list when user has no connectors."""
        mock_session = AsyncMock(spec=AsyncSession)
        session_factory = MagicMock(spec=async_sessionmaker)
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__ = AsyncMock(return_value=mock_session)
        ctx_mgr.__aexit__ = AsyncMock(return_value=False)
        session_factory.return_value = ctx_mgr

        with patch(
            "mcp_gateway.backends.connector_backend.connector_crud"
        ) as mock_crud:
            mock_crud.get_by_user = AsyncMock(return_value=[])

            backend = ConnectorBackend(session_factory=session_factory)
            result = await backend.list_connectors(user_id=99)

        assert result == []


class TestGetConnectorStatus:
    """Tests for ConnectorBackend.get_connector_status."""

    @pytest.mark.asyncio
    async def test_returns_detailed_status(self) -> None:
        """Returns full connector details with sanitized config."""
        mock_session = AsyncMock(spec=AsyncSession)
        session_factory = MagicMock(spec=async_sessionmaker)
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__ = AsyncMock(return_value=mock_session)
        ctx_mgr.__aexit__ = AsyncMock(return_value=False)
        session_factory.return_value = ctx_mgr

        connector = _make_connector(
            config={"access_token": "secret", "url": "https://example.com"}
        )

        with patch(
            "mcp_gateway.backends.connector_backend.connector_crud"
        ) as mock_crud:
            mock_crud.get_by_id_active = AsyncMock(return_value=connector)

            backend = ConnectorBackend(session_factory=session_factory)
            result = await backend.get_connector_status(connector_id=1)

        assert result is not None
        assert result["config"]["access_token"] == "***"
        assert result["config"]["url"] == "https://example.com"
        assert result["docs_analyzed"] == 42

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self) -> None:
        """Returns None when connector not found."""
        mock_session = AsyncMock(spec=AsyncSession)
        session_factory = MagicMock(spec=async_sessionmaker)
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__ = AsyncMock(return_value=mock_session)
        ctx_mgr.__aexit__ = AsyncMock(return_value=False)
        session_factory.return_value = ctx_mgr

        with patch(
            "mcp_gateway.backends.connector_backend.connector_crud"
        ) as mock_crud:
            mock_crud.get_by_id_active = AsyncMock(return_value=None)

            backend = ConnectorBackend(session_factory=session_factory)
            result = await backend.get_connector_status(connector_id=999)

        assert result is None


class TestSearchConnectorDocuments:
    """Tests for ConnectorBackend.search_connector_documents."""

    @pytest.mark.asyncio
    async def test_raises_without_qdrant(self) -> None:
        """Raises RuntimeError when Qdrant is not configured."""
        session_factory = MagicMock(spec=async_sessionmaker)
        backend = ConnectorBackend(session_factory=session_factory)

        with pytest.raises(RuntimeError, match="Qdrant and Embedder"):
            await backend.search_connector_documents(
                connector_id=1, query="test", collection_name="col"
            )

    @pytest.mark.asyncio
    async def test_searches_with_connector_filter(self) -> None:
        """Embeds query and searches with connector_id filter."""
        mock_qdrant = MagicMock()
        mock_qdrant.search = AsyncMock(
            return_value=[{"id": "1", "score": 0.9, "payload": {}}]
        )
        mock_embedder = AsyncMock()
        mock_embedder.embed_query = AsyncMock(return_value=[0.1, 0.2])

        session_factory = MagicMock(spec=async_sessionmaker)
        backend = ConnectorBackend(
            session_factory=session_factory,
            qdrant=mock_qdrant,
            embedder=mock_embedder,
        )

        results = await backend.search_connector_documents(
            connector_id=5, query="test", collection_name="col"
        )

        mock_embedder.embed_query.assert_awaited_once_with("test")
        mock_qdrant.search.assert_awaited_once()
        assert len(results) == 1


class TestTriggerSync:
    """Tests for ConnectorBackend.trigger_sync."""

    @pytest.mark.asyncio
    async def test_raises_without_nats(self) -> None:
        """Raises RuntimeError when NATS is not configured."""
        session_factory = MagicMock(spec=async_sessionmaker)
        backend = ConnectorBackend(session_factory=session_factory)

        with pytest.raises(RuntimeError, match="NATS publisher"):
            await backend.trigger_sync(connector_id=1, user_id=1)

    @pytest.mark.asyncio
    async def test_raises_for_wrong_owner(self) -> None:
        """Raises ValueError when user doesn't own connector."""
        mock_session = AsyncMock(spec=AsyncSession)
        session_factory = MagicMock(spec=async_sessionmaker)
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__ = AsyncMock(return_value=mock_session)
        ctx_mgr.__aexit__ = AsyncMock(return_value=False)
        session_factory.return_value = ctx_mgr

        connector = _make_connector(user_id=1)
        mock_nats = AsyncMock()

        with patch(
            "mcp_gateway.backends.connector_backend.connector_crud"
        ) as mock_crud:
            mock_crud.get_by_id_active = AsyncMock(return_value=connector)

            backend = ConnectorBackend(
                session_factory=session_factory, nats_publisher=mock_nats
            )
            with pytest.raises(ValueError, match="does not own"):
                await backend.trigger_sync(connector_id=1, user_id=999)

    @pytest.mark.asyncio
    async def test_raises_for_missing_connector(self) -> None:
        """Raises ValueError when connector not found."""
        mock_session = AsyncMock(spec=AsyncSession)
        session_factory = MagicMock(spec=async_sessionmaker)
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__ = AsyncMock(return_value=mock_session)
        ctx_mgr.__aexit__ = AsyncMock(return_value=False)
        session_factory.return_value = ctx_mgr

        mock_nats = AsyncMock()

        with patch(
            "mcp_gateway.backends.connector_backend.connector_crud"
        ) as mock_crud:
            mock_crud.get_by_id_active = AsyncMock(return_value=None)

            backend = ConnectorBackend(
                session_factory=session_factory, nats_publisher=mock_nats
            )
            with pytest.raises(ValueError, match="not found"):
                await backend.trigger_sync(connector_id=999, user_id=1)

    @pytest.mark.asyncio
    async def test_publishes_to_nats(self) -> None:
        """trigger_sync publishes a serialized protobuf to NATS."""
        mock_session = AsyncMock(spec=AsyncSession)
        session_factory = MagicMock(spec=async_sessionmaker)
        ctx_mgr = AsyncMock()
        ctx_mgr.__aenter__ = AsyncMock(return_value=mock_session)
        ctx_mgr.__aexit__ = AsyncMock(return_value=False)
        session_factory.return_value = ctx_mgr

        connector = _make_connector(id=5, user_id=10, type="teams")
        mock_nats = AsyncMock()

        with patch(
            "mcp_gateway.backends.connector_backend.connector_crud"
        ) as mock_crud:
            mock_crud.get_by_id_active = AsyncMock(return_value=connector)

            backend = ConnectorBackend(
                session_factory=session_factory, nats_publisher=mock_nats
            )
            result = await backend.trigger_sync(connector_id=5, user_id=10)

        assert result["connector_id"] == 5
        assert result["status"] == "sync_requested"
        assert result["subject"] == "connector.sync.teams"
        assert "chunking_session" in result
        mock_nats.publish.assert_awaited_once()
