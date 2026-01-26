"""Unit tests for EmbedServicer gRPC handler."""

from unittest import mock

import grpc
import pytest


class TestEmbedServicer:
    """Tests for EmbedServicer class."""

    @pytest.fixture
    def servicer(self):
        """Create a servicer instance for testing."""
        # Import here to avoid import errors if proto not generated
        import sys
        sys.path.insert(0, "/Users/gp/Developer/EchoMind/src")

        from embedder.main import EmbedServicer
        return EmbedServicer(default_model="test-model", batch_size=32)

    @pytest.fixture
    def mock_context(self):
        """Create a mock gRPC context."""
        context = mock.MagicMock(spec=grpc.ServicerContext)
        return context

    @mock.patch("embedder.main.SentenceEncoder")
    def test_embed_success(
        self,
        mock_encoder: mock.MagicMock,
        servicer,
        mock_context,
    ) -> None:
        """Test successful embedding request."""
        # Setup mock
        mock_encoder.encode.return_value = [[0.1, 0.2], [0.3, 0.4]]

        # Create request
        request = mock.MagicMock()
        request.texts = ["hello", "world"]

        # Call servicer
        response = servicer.Embed(request, mock_context)

        # Verify
        mock_encoder.encode.assert_called_once_with(
            texts=["hello", "world"],
            model_name="test-model",
            batch_size=32,
        )
        assert len(response.embeddings) == 2
        mock_context.abort.assert_not_called()

    @mock.patch("embedder.main.SentenceEncoder")
    def test_embed_empty_texts_aborts(
        self,
        mock_encoder: mock.MagicMock,
        servicer,
        mock_context,
    ) -> None:
        """Test that empty texts list aborts with INVALID_ARGUMENT."""
        request = mock.MagicMock()
        request.texts = []

        servicer.Embed(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.INVALID_ARGUMENT

    @mock.patch("embedder.main.SentenceEncoder")
    def test_embed_model_not_found(
        self,
        mock_encoder: mock.MagicMock,
        servicer,
        mock_context,
    ) -> None:
        """Test handling of ModelNotFoundError."""
        from embedder.logic.exceptions import ModelNotFoundError

        mock_encoder.encode.side_effect = ModelNotFoundError("test-model")

        request = mock.MagicMock()
        request.texts = ["hello"]

        servicer.Embed(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.NOT_FOUND

    @mock.patch("embedder.main.SentenceEncoder")
    def test_embed_encoder_error(
        self,
        mock_encoder: mock.MagicMock,
        servicer,
        mock_context,
    ) -> None:
        """Test handling of EncoderError."""
        from embedder.logic.exceptions import EncoderError

        mock_encoder.encode.side_effect = EncoderError("encoding failed", 1)

        request = mock.MagicMock()
        request.texts = ["hello"]

        servicer.Embed(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.INTERNAL

    @mock.patch("embedder.main.SentenceEncoder")
    def test_get_dimension_success(
        self,
        mock_encoder: mock.MagicMock,
        servicer,
        mock_context,
    ) -> None:
        """Test successful dimension request."""
        mock_encoder.get_dimension.return_value = 384

        request = mock.MagicMock()

        response = servicer.GetDimension(request, mock_context)

        assert response.dimension == 384
        assert response.model_id == "test-model"
        mock_context.abort.assert_not_called()

    @mock.patch("embedder.main.SentenceEncoder")
    def test_get_dimension_model_not_found(
        self,
        mock_encoder: mock.MagicMock,
        servicer,
        mock_context,
    ) -> None:
        """Test handling of ModelNotFoundError in GetDimension."""
        from embedder.logic.exceptions import ModelNotFoundError

        mock_encoder.get_dimension.side_effect = ModelNotFoundError("test-model")

        request = mock.MagicMock()

        servicer.GetDimension(request, mock_context)

        mock_context.abort.assert_called_once()
        call_args = mock_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.NOT_FOUND
