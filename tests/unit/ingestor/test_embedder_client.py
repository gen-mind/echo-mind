"""Unit tests for EmbedderClient gRPC client."""

from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest

from ingestor.grpc.embedder_client import EmbedderClient
from ingestor.logic.exceptions import EmbeddingError, GrpcError


class TestEmbedderClient:
    """Tests for EmbedderClient class."""

    def setup_method(self) -> None:
        """Create client instance for each test."""
        self.client = EmbedderClient(
            host="localhost",
            port=50051,
            timeout=30.0,
        )

    async def asyncTearDown(self) -> None:
        """Close client after tests."""
        await self.client.close()

    # ==========================================
    # Initialization tests
    # ==========================================

    def test_init_stores_config(self) -> None:
        """Test client stores configuration."""
        assert self.client._host == "localhost"
        assert self.client._port == 50051
        assert self.client._timeout == 30.0

    def test_init_channel_is_none(self) -> None:
        """Test client starts without channel."""
        assert self.client._channel is None
        assert self.client._stub is None

    def test_init_dimension_is_none(self) -> None:
        """Test client starts without cached dimension."""
        assert self.client._dimension is None

    def test_init_custom_config(self) -> None:
        """Test client with custom configuration."""
        client = EmbedderClient(
            host="custom-embedder",
            port=9999,
            timeout=60.0,
        )

        assert client._host == "custom-embedder"
        assert client._port == 9999
        assert client._timeout == 60.0

    # ==========================================
    # Connection tests
    # ==========================================

    @pytest.mark.asyncio
    async def test_ensure_connected_creates_channel(self) -> None:
        """Test _ensure_connected creates gRPC channel."""
        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()

            await self.client._ensure_connected()

            mock_channel.assert_called_once()
            assert self.client._channel is not None

    @pytest.mark.asyncio
    async def test_ensure_connected_creates_stub(self) -> None:
        """Test _ensure_connected creates service stub."""
        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()

            await self.client._ensure_connected()

            assert self.client._stub is not None

    @pytest.mark.asyncio
    async def test_ensure_connected_uses_correct_target(self) -> None:
        """Test _ensure_connected uses correct target address."""
        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()

            await self.client._ensure_connected()

            target = mock_channel.call_args[0][0]
            assert target == "localhost:50051"

    @pytest.mark.asyncio
    async def test_ensure_connected_only_once(self) -> None:
        """Test _ensure_connected doesn't recreate channel."""
        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()

            await self.client._ensure_connected()
            await self.client._ensure_connected()

            # Should only be called once
            assert mock_channel.call_count == 1

    # ==========================================
    # get_dimension tests
    # ==========================================

    @pytest.mark.asyncio
    async def test_get_dimension_calls_grpc(self) -> None:
        """Test get_dimension makes gRPC call."""
        mock_stub = MagicMock()
        mock_response = MagicMock()
        mock_response.dimension = 1024
        mock_response.model_id = "test-model"
        mock_stub.GetDimension = AsyncMock(return_value=mock_response)

        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            with patch(
                "ingestor.grpc.embedder_client.EmbedServiceStub",
                return_value=mock_stub,
            ):
                result = await self.client.get_dimension()

                assert result == 1024
                mock_stub.GetDimension.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_dimension_caches_result(self) -> None:
        """Test get_dimension caches dimension."""
        mock_stub = MagicMock()
        mock_response = MagicMock()
        mock_response.dimension = 768
        mock_response.model_id = "test"
        mock_stub.GetDimension = AsyncMock(return_value=mock_response)

        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            with patch(
                "ingestor.grpc.embedder_client.EmbedServiceStub",
                return_value=mock_stub,
            ):
                result1 = await self.client.get_dimension()
                result2 = await self.client.get_dimension()

                assert result1 == result2 == 768
                # Should only call gRPC once due to caching
                assert mock_stub.GetDimension.call_count == 1

    @pytest.mark.asyncio
    async def test_get_dimension_raises_grpc_error(self) -> None:
        """Test get_dimension raises GrpcError on failure."""
        mock_stub = MagicMock()

        # Create a real exception that mimics AioRpcError behavior
        class MockAioRpcError(grpc.aio.AioRpcError):
            def __init__(self):
                pass  # Don't call parent __init__

            def code(self):
                return grpc.StatusCode.UNAVAILABLE

            def details(self):
                return "Service unavailable"

        mock_stub.GetDimension = AsyncMock(side_effect=MockAioRpcError())

        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            with patch(
                "ingestor.grpc.embedder_client.EmbedServiceStub",
                return_value=mock_stub,
            ):
                with pytest.raises(GrpcError) as exc_info:
                    await self.client.get_dimension()

                assert exc_info.value.service == "embedder"

    # ==========================================
    # embed_texts tests
    # ==========================================

    @pytest.mark.asyncio
    async def test_embed_texts_empty_list(self) -> None:
        """Test embed_texts returns empty for empty input."""
        result = await self.client.embed_texts([])

        assert result == []

    @pytest.mark.asyncio
    async def test_embed_texts_single_text(self) -> None:
        """Test embed_texts with single text."""
        mock_stub = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.vector = [0.1, 0.2, 0.3]
        mock_response = MagicMock()
        mock_response.embeddings = [mock_embedding]
        mock_stub.Embed = AsyncMock(return_value=mock_response)

        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            with patch(
                "ingestor.grpc.embedder_client.EmbedServiceStub",
                return_value=mock_stub,
            ):
                result = await self.client.embed_texts(["hello"])

                assert len(result) == 1
                assert result[0] == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_embed_texts_multiple_texts(self) -> None:
        """Test embed_texts with multiple texts."""
        mock_stub = MagicMock()
        mock_embeddings = [
            MagicMock(vector=[0.1, 0.2]),
            MagicMock(vector=[0.3, 0.4]),
            MagicMock(vector=[0.5, 0.6]),
        ]
        mock_response = MagicMock()
        mock_response.embeddings = mock_embeddings
        mock_stub.Embed = AsyncMock(return_value=mock_response)

        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            with patch(
                "ingestor.grpc.embedder_client.EmbedServiceStub",
                return_value=mock_stub,
            ):
                result = await self.client.embed_texts(["a", "b", "c"])

                assert len(result) == 3

    @pytest.mark.asyncio
    async def test_embed_texts_passes_document_id(self) -> None:
        """Test embed_texts logs document_id."""
        mock_stub = MagicMock()
        mock_response = MagicMock()
        mock_response.embeddings = []
        mock_stub.Embed = AsyncMock(return_value=mock_response)

        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            with patch(
                "ingestor.grpc.embedder_client.EmbedServiceStub",
                return_value=mock_stub,
            ):
                await self.client.embed_texts(["test"], document_id=123)

                # Should not raise
                mock_stub.Embed.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_texts_raises_grpc_error(self) -> None:
        """Test embed_texts raises GrpcError on gRPC failure."""
        mock_stub = MagicMock()

        # Create a real exception that mimics AioRpcError behavior
        class MockAioRpcError(grpc.aio.AioRpcError):
            def __init__(self):
                pass  # Don't call parent __init__

            def code(self):
                return grpc.StatusCode.DEADLINE_EXCEEDED

            def details(self):
                return "Timeout"

        mock_stub.Embed = AsyncMock(side_effect=MockAioRpcError())

        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            with patch(
                "ingestor.grpc.embedder_client.EmbedServiceStub",
                return_value=mock_stub,
            ):
                with pytest.raises(GrpcError) as exc_info:
                    await self.client.embed_texts(["test"])

                assert exc_info.value.service == "embedder"

    @pytest.mark.asyncio
    async def test_embed_texts_raises_embedding_error(self) -> None:
        """Test embed_texts raises EmbeddingError on other failures."""
        mock_stub = MagicMock()
        mock_stub.Embed = AsyncMock(side_effect=ValueError("unexpected"))

        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            with patch(
                "ingestor.grpc.embedder_client.EmbedServiceStub",
                return_value=mock_stub,
            ):
                with pytest.raises(EmbeddingError) as exc_info:
                    await self.client.embed_texts(["test"], document_id=456)

                assert exc_info.value.document_id == 456

    # ==========================================
    # embed_batch tests
    # ==========================================

    @pytest.mark.asyncio
    async def test_embed_batch_empty_list(self) -> None:
        """Test embed_batch returns empty for empty input."""
        result = await self.client.embed_batch([])

        assert result == []

    @pytest.mark.asyncio
    async def test_embed_batch_single_batch(self) -> None:
        """Test embed_batch with texts fitting in one batch."""
        mock_stub = MagicMock()
        mock_response = MagicMock()
        mock_response.embeddings = [
            MagicMock(vector=[0.1]),
            MagicMock(vector=[0.2]),
        ]
        mock_stub.Embed = AsyncMock(return_value=mock_response)

        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            with patch(
                "ingestor.grpc.embedder_client.EmbedServiceStub",
                return_value=mock_stub,
            ):
                result = await self.client.embed_batch(["a", "b"], batch_size=10)

                assert len(result) == 2
                # Only one batch call
                assert mock_stub.Embed.call_count == 1

    @pytest.mark.asyncio
    async def test_embed_batch_multiple_batches(self) -> None:
        """Test embed_batch splits into multiple batches."""
        mock_stub = MagicMock()

        # Return different responses for each batch
        responses = [
            MagicMock(embeddings=[MagicMock(vector=[0.1]), MagicMock(vector=[0.2])]),
            MagicMock(embeddings=[MagicMock(vector=[0.3])]),
        ]
        mock_stub.Embed = AsyncMock(side_effect=responses)

        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            with patch(
                "ingestor.grpc.embedder_client.EmbedServiceStub",
                return_value=mock_stub,
            ):
                result = await self.client.embed_batch(["a", "b", "c"], batch_size=2)

                assert len(result) == 3
                # Two batch calls
                assert mock_stub.Embed.call_count == 2

    @pytest.mark.asyncio
    async def test_embed_batch_default_batch_size(self) -> None:
        """Test embed_batch uses default batch size of 32."""
        # Just verify it doesn't raise with default batch_size
        with patch.object(self.client, "embed_texts", return_value=[]):
            await self.client.embed_batch(["test"])

    # ==========================================
    # close tests
    # ==========================================

    @pytest.mark.asyncio
    async def test_close_closes_channel(self) -> None:
        """Test close() closes the gRPC channel."""
        mock_channel = MagicMock()
        # Make close() return a proper coroutine to avoid unawaited warning
        mock_channel.close = AsyncMock(return_value=None)

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            await self.client._ensure_connected()
            await self.client.close()

            mock_channel.close.assert_called_once()
            assert self.client._channel is None
            assert self.client._stub is None

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self) -> None:
        """Test close() when no connection exists."""
        # Should not raise
        await self.client.close()

        assert self.client._channel is None

    # ==========================================
    # health_check tests
    # ==========================================

    @pytest.mark.asyncio
    async def test_health_check_healthy(self) -> None:
        """Test health_check returns healthy status."""
        mock_stub = MagicMock()
        mock_response = MagicMock()
        mock_response.dimension = 1024
        mock_response.model_id = "test"
        mock_stub.GetDimension = AsyncMock(return_value=mock_response)

        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            with patch(
                "ingestor.grpc.embedder_client.EmbedServiceStub",
                return_value=mock_stub,
            ):
                result = await self.client.health_check()

                assert result["status"] == "healthy"
                assert result["dimension"] == 1024
                assert result["host"] == "localhost"
                assert result["port"] == 50051

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self) -> None:
        """Test health_check returns unhealthy status on error."""
        mock_stub = MagicMock()
        mock_stub.GetDimension = AsyncMock(side_effect=Exception("connection failed"))

        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            with patch(
                "ingestor.grpc.embedder_client.EmbedServiceStub",
                return_value=mock_stub,
            ):
                result = await self.client.health_check()

                assert result["status"] == "unhealthy"
                assert "error" in result
                assert result["host"] == "localhost"
