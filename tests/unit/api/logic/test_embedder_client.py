"""Unit tests for EmbedderClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.logic.embedder_client import (
    EmbedderClient,
    close_embedder_client,
    get_embedder_client,
    init_embedder_client,
)
from api.logic.exceptions import ServiceUnavailableError


class TestEmbedderClientEmbedQuery:
    """Tests for EmbedderClient.embed_query()."""

    @pytest.fixture
    def client(self) -> EmbedderClient:
        """Create EmbedderClient instance."""
        return EmbedderClient(host="localhost", port=50051, timeout=30.0)

    @pytest.mark.asyncio
    async def test_embed_query_returns_vector(
        self,
        client: EmbedderClient,
    ) -> None:
        """Test embed_query returns embedding vector."""
        mock_stub = AsyncMock()

        # Mock embedding response
        mock_embedding = MagicMock()
        mock_embedding.vector = [0.1, 0.2, 0.3]

        mock_response = MagicMock()
        mock_response.embeddings = [mock_embedding]

        mock_stub.Embed.return_value = mock_response

        # Set up client with mocked stub
        client._channel = MagicMock()
        client._stub = mock_stub

        result = await client.embed_query("test query")

        assert result == [0.1, 0.2, 0.3]
        mock_stub.Embed.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_query_raises_on_empty_response(
        self,
        client: EmbedderClient,
    ) -> None:
        """Test embed_query raises when embedder returns empty response."""
        mock_stub = AsyncMock()

        mock_response = MagicMock()
        mock_response.embeddings = []

        mock_stub.Embed.return_value = mock_response

        client._channel = MagicMock()
        client._stub = mock_stub

        with pytest.raises(ServiceUnavailableError) as exc_info:
            await client.embed_query("test query")

        assert "Embedder" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_embed_query_raises_on_grpc_error(
        self,
        client: EmbedderClient,
    ) -> None:
        """Test embed_query raises ServiceUnavailableError on gRPC error."""
        import grpc

        mock_stub = AsyncMock()

        # Create mock gRPC error
        mock_error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.UNAVAILABLE,
            initial_metadata=None,
            trailing_metadata=None,
            details="Connection refused",
            debug_error_string=None,
        )
        mock_stub.Embed.side_effect = mock_error

        client._channel = MagicMock()
        client._stub = mock_stub

        with pytest.raises(ServiceUnavailableError) as exc_info:
            await client.embed_query("test query")

        assert "Embedder" in str(exc_info.value)


class TestEmbedderClientClose:
    """Tests for EmbedderClient.close()."""

    @pytest.mark.asyncio
    async def test_close_closes_channel(self) -> None:
        """Test close properly closes gRPC channel."""
        client = EmbedderClient(host="localhost", port=50051)
        mock_channel = AsyncMock()
        client._channel = mock_channel
        client._stub = MagicMock()

        await client.close()

        mock_channel.close.assert_called_once()
        assert client._channel is None
        assert client._stub is None

    @pytest.mark.asyncio
    async def test_close_safe_when_no_channel(self) -> None:
        """Test close is safe when no channel initialized."""
        client = EmbedderClient(host="localhost", port=50051)
        await client.close()  # Should not raise


class TestEmbedderClientHealthCheck:
    """Tests for EmbedderClient.health_check()."""

    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_connected(self) -> None:
        """Test health_check returns True when connected."""
        client = EmbedderClient(host="localhost", port=50051)
        client._channel = MagicMock()
        client._stub = MagicMock()

        result = await client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_error(self) -> None:
        """Test health_check returns False when connection fails."""
        client = EmbedderClient(host="localhost", port=50051)

        # Mock connection failure
        with patch.object(
            client, "_ensure_connected", side_effect=Exception("Connection failed")
        ):
            result = await client.health_check()

        assert result is False


class TestEmbedderClientGlobalInstance:
    """Tests for global embedder client functions."""

    @pytest.mark.asyncio
    async def test_init_and_get_client(self) -> None:
        """Test initializing and getting global client."""
        # Initialize
        client = await init_embedder_client(
            host="localhost",
            port=50051,
            timeout=30.0,
        )

        # Get should return same instance
        retrieved = get_embedder_client()
        assert retrieved is client

        # Cleanup
        await close_embedder_client()

    def test_get_client_raises_when_not_initialized(self) -> None:
        """Test get_embedder_client raises when not initialized."""
        # Ensure client is None
        import api.logic.embedder_client as module

        original = module._embedder_client
        module._embedder_client = None

        try:
            with pytest.raises(RuntimeError) as exc_info:
                get_embedder_client()

            assert "not initialized" in str(exc_info.value)
        finally:
            module._embedder_client = original
