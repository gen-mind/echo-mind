"""Unit tests for EmbedServicer gRPC handler."""

from unittest import mock

import grpc
import pytest


class TestEmbedServicer:
    """Tests for EmbedServicer class."""

    @pytest.fixture
    def servicer(self):
        """Create a servicer instance for testing."""
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
        mock_encoder.encode.return_value = [[0.1, 0.2], [0.3, 0.4]]

        request = mock.MagicMock()
        request.texts = [
            "This is a sufficiently long test sentence for the embedding model to process correctly.",
            "Another realistic sentence that exceeds the minimum text length for embeddings validation.",
        ]

        response = servicer.Embed(request, mock_context)

        mock_encoder.encode.assert_called_once_with(
            texts=[
                "This is a sufficiently long test sentence for the embedding model to process correctly.",
                "Another realistic sentence that exceeds the minimum text length for embeddings validation.",
            ],
            model_name="test-model",
            batch_size=32,
        )
        assert len(response.embeddings) == 2
        mock_context.set_code.assert_not_called()

    @mock.patch("embedder.main.SentenceEncoder")
    def test_embed_empty_texts_sets_invalid_argument(
        self,
        mock_encoder: mock.MagicMock,
        servicer,
        mock_context,
    ) -> None:
        """Test that empty texts list sets INVALID_ARGUMENT status."""
        request = mock.MagicMock()
        request.texts = []

        servicer.Embed(request, mock_context)

        mock_context.set_code.assert_called_once_with(
            grpc.StatusCode.INVALID_ARGUMENT,
        )

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
        request.texts = ["This is a sufficiently long test sentence for the embedding model to process correctly."]

        servicer.Embed(request, mock_context)

        mock_context.set_code.assert_called_once_with(
            grpc.StatusCode.NOT_FOUND,
        )

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
        request.texts = ["This is a sufficiently long test sentence for the embedding model to process correctly."]

        servicer.Embed(request, mock_context)

        mock_context.set_code.assert_called_once_with(
            grpc.StatusCode.INTERNAL,
        )

    @mock.patch("embedder.main.SentenceEncoder")
    def test_embed_unexpected_error(
        self,
        mock_encoder: mock.MagicMock,
        servicer,
        mock_context,
    ) -> None:
        """Test handling of unexpected exceptions."""
        mock_encoder.encode.side_effect = RuntimeError("something broke")

        request = mock.MagicMock()
        request.texts = ["This is a sufficiently long test sentence for the embedding model to process correctly."]

        servicer.Embed(request, mock_context)

        mock_context.set_code.assert_called_once_with(
            grpc.StatusCode.INTERNAL,
        )
        details = mock_context.set_details.call_args[0][0]
        assert "something broke" in details

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
        mock_context.set_code.assert_not_called()

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

        mock_context.set_code.assert_called_once_with(
            grpc.StatusCode.NOT_FOUND,
        )

    @mock.patch("embedder.main.SentenceEncoder")
    def test_get_dimension_unexpected_error(
        self,
        mock_encoder: mock.MagicMock,
        servicer,
        mock_context,
    ) -> None:
        """Test handling of unexpected errors in GetDimension."""
        mock_encoder.get_dimension.side_effect = RuntimeError("model broke")

        request = mock.MagicMock()

        servicer.GetDimension(request, mock_context)

        mock_context.set_code.assert_called_once_with(
            grpc.StatusCode.INTERNAL,
        )
        details = mock_context.set_details.call_args[0][0]
        assert "model broke" in details
