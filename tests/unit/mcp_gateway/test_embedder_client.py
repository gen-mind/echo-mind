"""Unit tests for mcp_gateway.backends.embedder_client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_gateway.backends.embedder_client import EmbedderClient


class TestEmbedderClientInit:
    """Tests for EmbedderClient initialization."""

    def test_stores_connection_params(self) -> None:
        """Verify connection parameters are stored."""
        client = EmbedderClient(host="localhost", port=50051, timeout=10.0, model_name="test-model")
        assert client._host == "localhost"
        assert client._port == 50051
        assert client._timeout == 10.0
        assert client._model_name == "test-model"

    def test_starts_disconnected(self) -> None:
        """Verify client starts with no channel or stub."""
        client = EmbedderClient(host="localhost", port=50051)
        assert client._channel is None
        assert client._stub is None

    def test_default_timeout(self) -> None:
        """Verify default timeout is 30 seconds."""
        client = EmbedderClient(host="localhost", port=50051)
        assert client._timeout == 30.0

    def test_default_model_name(self) -> None:
        """Verify default model name is empty string."""
        client = EmbedderClient(host="localhost", port=50051)
        assert client._model_name == ""


class TestEmbedderClientEmbedQuery:
    """Tests for embed_query method."""

    @pytest.mark.asyncio
    @patch("mcp_gateway.backends.embedder_client.grpc.aio.insecure_channel")
    @patch("mcp_gateway.backends.embedder_client.EmbedServiceStub")
    async def test_embeds_query_successfully(self, mock_stub_cls: MagicMock, mock_channel_fn: MagicMock) -> None:
        """Verify successful embedding returns vector."""
        mock_channel = MagicMock()
        mock_channel_fn.return_value = mock_channel

        mock_embedding = MagicMock()
        mock_embedding.vector = [0.1, 0.2, 0.3]
        mock_response = MagicMock()
        mock_response.embeddings = [mock_embedding]

        mock_stub = MagicMock()
        mock_stub.Embed = AsyncMock(return_value=mock_response)
        mock_stub_cls.return_value = mock_stub

        client = EmbedderClient(host="localhost", port=50051)
        result = await client.embed_query("test query")

        assert result == [0.1, 0.2, 0.3]
        mock_stub.Embed.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("mcp_gateway.backends.embedder_client.grpc.aio.insecure_channel")
    @patch("mcp_gateway.backends.embedder_client.EmbedServiceStub")
    async def test_raises_on_empty_response(self, mock_stub_cls: MagicMock, mock_channel_fn: MagicMock) -> None:
        """Verify ConnectionError raised on empty embeddings response."""
        mock_channel_fn.return_value = MagicMock()
        mock_response = MagicMock()
        mock_response.embeddings = []
        mock_stub = MagicMock()
        mock_stub.Embed = AsyncMock(return_value=mock_response)
        mock_stub_cls.return_value = mock_stub

        client = EmbedderClient(host="localhost", port=50051)
        with pytest.raises(ConnectionError, match="empty response"):
            await client.embed_query("test")

    @pytest.mark.asyncio
    @patch("mcp_gateway.backends.embedder_client.grpc.aio.insecure_channel")
    @patch("mcp_gateway.backends.embedder_client.EmbedServiceStub")
    async def test_resets_channel_on_grpc_error(self, mock_stub_cls: MagicMock, mock_channel_fn: MagicMock) -> None:
        """Verify channel is reset on gRPC error for reconnection."""
        import grpc

        mock_channel_fn.return_value = MagicMock()
        mock_stub = MagicMock()
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="unavailable",
            debug_error_string=None,
        )
        mock_stub.Embed = AsyncMock(side_effect=error)
        mock_stub_cls.return_value = mock_stub

        client = EmbedderClient(host="localhost", port=50051)
        with pytest.raises(ConnectionError):
            await client.embed_query("test")

        assert client._channel is None
        assert client._stub is None


class TestEmbedderClientClose:
    """Tests for close method."""

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self) -> None:
        """Close is safe when not connected."""
        client = EmbedderClient(host="localhost", port=50051)
        await client.close()  # Should not raise

    @pytest.mark.asyncio
    @patch("mcp_gateway.backends.embedder_client.grpc.aio.insecure_channel")
    @patch("mcp_gateway.backends.embedder_client.EmbedServiceStub")
    async def test_close_releases_channel(self, mock_stub_cls: MagicMock, mock_channel_fn: MagicMock) -> None:
        """Close releases channel and stub."""
        mock_channel = AsyncMock()
        mock_channel_fn.return_value = mock_channel
        mock_stub_cls.return_value = MagicMock()

        client = EmbedderClient(host="localhost", port=50051)
        await client._ensure_connected()
        assert client._channel is not None

        await client.close()
        assert client._channel is None
        assert client._stub is None
        mock_channel.close.assert_awaited_once()


class TestEmbedderClientHealthCheck:
    """Tests for health_check method."""

    @pytest.mark.asyncio
    @patch("mcp_gateway.backends.embedder_client.grpc.aio.insecure_channel")
    @patch("mcp_gateway.backends.embedder_client.EmbedServiceStub")
    async def test_health_check_returns_true_when_healthy(self, mock_stub_cls: MagicMock, mock_channel_fn: MagicMock) -> None:
        """Verify health check returns True when embed succeeds."""
        mock_channel_fn.return_value = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.vector = [0.1]
        mock_response = MagicMock()
        mock_response.embeddings = [mock_embedding]
        mock_stub = MagicMock()
        mock_stub.Embed = AsyncMock(return_value=mock_response)
        mock_stub_cls.return_value = mock_stub

        client = EmbedderClient(host="localhost", port=50051)
        assert await client.health_check() is True

    @pytest.mark.asyncio
    @patch("mcp_gateway.backends.embedder_client.grpc.aio.insecure_channel")
    @patch("mcp_gateway.backends.embedder_client.EmbedServiceStub")
    async def test_health_check_returns_false_on_error(self, mock_stub_cls: MagicMock, mock_channel_fn: MagicMock) -> None:
        """Verify health check returns False and resets channel on error."""
        mock_channel_fn.return_value = MagicMock()
        mock_stub = MagicMock()
        mock_stub.Embed = AsyncMock(side_effect=Exception("down"))
        mock_stub_cls.return_value = mock_stub

        client = EmbedderClient(host="localhost", port=50051)
        assert await client.health_check() is False
        assert client._channel is None
