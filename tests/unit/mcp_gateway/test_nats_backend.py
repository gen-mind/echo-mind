"""Unit tests for mcp_gateway.backends.nats_backend."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_gateway.backends.nats_backend import NatsBackend


class TestNatsBackendInit:
    """Tests for NatsBackend initialization."""

    @patch("mcp_gateway.backends.nats_backend.JetStreamPublisher")
    def test_creates_publisher(self, mock_publisher_cls: MagicMock) -> None:
        """NatsBackend creates a JetStreamPublisher on init."""
        NatsBackend(url="nats://localhost:4222", user="u", password="p")
        mock_publisher_cls.assert_called_once_with(
            servers=["nats://localhost:4222"],
            user="u",
            password="p",
        )

    @patch("mcp_gateway.backends.nats_backend.JetStreamPublisher")
    def test_starts_disconnected(self, mock_publisher_cls: MagicMock) -> None:
        """NatsBackend starts in disconnected state."""
        backend = NatsBackend(url="nats://localhost:4222")
        assert backend.is_connected is False


class TestNatsBackendConnect:
    """Tests for NatsBackend.connect."""

    @pytest.mark.asyncio
    @patch("mcp_gateway.backends.nats_backend.JetStreamPublisher")
    async def test_connect_initializes_publisher(
        self, mock_publisher_cls: MagicMock
    ) -> None:
        """connect calls publisher.init() and sets connected flag."""
        mock_publisher = AsyncMock()
        mock_publisher_cls.return_value = mock_publisher

        backend = NatsBackend(url="nats://localhost:4222")
        await backend.connect()

        mock_publisher.init.assert_awaited_once()
        assert backend.is_connected is True

    @pytest.mark.asyncio
    @patch("mcp_gateway.backends.nats_backend.JetStreamPublisher")
    async def test_connect_failure_propagates(
        self, mock_publisher_cls: MagicMock
    ) -> None:
        """connect propagates exceptions from publisher.init()."""
        mock_publisher = AsyncMock()
        mock_publisher.init.side_effect = ConnectionRefusedError("refused")
        mock_publisher_cls.return_value = mock_publisher

        backend = NatsBackend(url="nats://localhost:4222")
        with pytest.raises(ConnectionRefusedError):
            await backend.connect()

        assert backend.is_connected is False


class TestNatsBackendPublish:
    """Tests for NatsBackend.publish."""

    @pytest.mark.asyncio
    @patch("mcp_gateway.backends.nats_backend.JetStreamPublisher")
    async def test_publish_delegates(self, mock_publisher_cls: MagicMock) -> None:
        """publish delegates to publisher.publish."""
        mock_publisher = AsyncMock()
        mock_publisher_cls.return_value = mock_publisher

        backend = NatsBackend(url="nats://localhost:4222")
        await backend.connect()
        await backend.publish("subject.test", b"payload")

        mock_publisher.publish.assert_awaited_once_with("subject.test", b"payload")

    @pytest.mark.asyncio
    @patch("mcp_gateway.backends.nats_backend.JetStreamPublisher")
    async def test_publish_raises_when_disconnected(
        self, mock_publisher_cls: MagicMock
    ) -> None:
        """publish raises RuntimeError when not connected."""
        mock_publisher_cls.return_value = AsyncMock()

        backend = NatsBackend(url="nats://localhost:4222")
        with pytest.raises(RuntimeError, match="not connected"):
            await backend.publish("subject", b"data")


class TestNatsBackendClose:
    """Tests for NatsBackend.close."""

    @pytest.mark.asyncio
    @patch("mcp_gateway.backends.nats_backend.JetStreamPublisher")
    async def test_close_delegates(self, mock_publisher_cls: MagicMock) -> None:
        """close delegates to publisher.close and resets connected flag."""
        mock_publisher = AsyncMock()
        mock_publisher_cls.return_value = mock_publisher

        backend = NatsBackend(url="nats://localhost:4222")
        await backend.connect()
        assert backend.is_connected is True

        await backend.close()
        mock_publisher.close.assert_awaited_once()
        assert backend.is_connected is False

    @pytest.mark.asyncio
    @patch("mcp_gateway.backends.nats_backend.JetStreamPublisher")
    async def test_close_when_not_connected_is_noop(
        self, mock_publisher_cls: MagicMock
    ) -> None:
        """close when already disconnected does nothing."""
        mock_publisher = AsyncMock()
        mock_publisher_cls.return_value = mock_publisher

        backend = NatsBackend(url="nats://localhost:4222")
        await backend.close()

        mock_publisher.close.assert_not_awaited()


class TestNatsBackendIsConnected:
    """Tests for NatsBackend.is_connected property."""

    @patch("mcp_gateway.backends.nats_backend.JetStreamPublisher")
    def test_is_connected_reflects_state(self, mock_publisher_cls: MagicMock) -> None:
        """is_connected reflects internal connection state."""
        backend = NatsBackend(url="nats://localhost:4222")
        assert backend.is_connected is False
        backend._connected = True
        assert backend.is_connected is True
