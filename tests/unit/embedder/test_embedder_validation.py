"""
Unit tests for Embedder gRPC input validation.

Tests the string validation logic added to prevent processing
empty, whitespace-only, or too-short text strings.
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

import grpc
import pytest
from unittest.mock import MagicMock, patch

from echomind_lib.models.internal.embedding_pb2 import EmbedRequest
from embedder.main import EmbedServicer


class TestValidateTexts:
    """Tests for the _validate_texts helper method."""

    @pytest.fixture
    def servicer(self):
        """Create an EmbedServicer instance."""
        return EmbedServicer(default_model="test-model", batch_size=32)

    def test_empty_list_returns_error(self, servicer) -> None:
        """Test that empty list returns validation error."""
        result = servicer._validate_texts([])
        assert result == "texts cannot be empty"

    def test_empty_string_returns_error(self, servicer) -> None:
        """Test that empty string returns validation error with index."""
        valid = "This is a valid text that is definitely longer than fifty characters."
        result = servicer._validate_texts([valid, ""])
        assert result is not None
        assert "index 1 is empty" in result

    def test_whitespace_only_returns_error(self, servicer) -> None:
        """Test that whitespace-only string returns validation error."""
        valid = "This is a valid text that is definitely longer than fifty characters."
        result = servicer._validate_texts([valid, "   \n\t  "])
        assert result is not None
        assert "only whitespace" in result

    def test_too_short_returns_error(self, servicer) -> None:
        """Test that short text returns validation error."""
        result = servicer._validate_texts(["Too short"])
        assert result is not None
        assert "too short" in result
        assert "minimum 50" in result

    def test_valid_texts_returns_none(self, servicer) -> None:
        """Test that valid texts return None (no error)."""
        valid = "This is a valid text that is long enough to pass validation and be embedded."
        result = servicer._validate_texts([valid])
        assert result is None

    def test_strips_whitespace_for_length(self, servicer) -> None:
        """Test that whitespace is stripped before length check."""
        text = "    This text has exactly sixty characters of actual content!     "
        result = servicer._validate_texts([text])
        assert result is None

    def test_validation_order_empty_before_length(self, servicer) -> None:
        """Test empty check runs before length check."""
        result = servicer._validate_texts([""])
        assert result is not None
        assert "is empty" in result
        assert "too short" not in result

    def test_batch_fails_on_first_invalid(self, servicer) -> None:
        """Test that validation stops at first invalid text."""
        texts = [
            "This is the first valid text that is long enough to pass validation.",
            "Short",
            "This is the third valid text that is long enough to pass validation.",
        ]
        result = servicer._validate_texts(texts)
        assert result is not None
        assert "index 1" in result
        assert "too short" in result


class TestEmbedderValidation:
    """Tests for embedder input validation via gRPC servicer."""

    @pytest.fixture
    def servicer(self):
        """Create an EmbedServicer instance."""
        return EmbedServicer(default_model="test-model", batch_size=32)

    @pytest.fixture
    def mock_context(self):
        """Create a mock gRPC context."""
        return MagicMock(spec=grpc.ServicerContext)

    def test_embed_rejects_empty_list(self, servicer, mock_context) -> None:
        """Test that empty texts list sets INVALID_ARGUMENT status."""
        request = EmbedRequest(texts=[])

        servicer.Embed(request, mock_context)

        mock_context.set_code.assert_called_once_with(
            grpc.StatusCode.INVALID_ARGUMENT,
        )
        mock_context.set_details.assert_called_once_with(
            "texts cannot be empty",
        )

    def test_embed_rejects_empty_string(self, servicer, mock_context) -> None:
        """Test that list containing empty string sets INVALID_ARGUMENT."""
        valid_long_text = "This is a valid text that is definitely longer than fifty characters."
        request = EmbedRequest(texts=[valid_long_text, ""])

        servicer.Embed(request, mock_context)

        mock_context.set_code.assert_called_once_with(
            grpc.StatusCode.INVALID_ARGUMENT,
        )
        details = mock_context.set_details.call_args[0][0]
        assert "index 1 is empty" in details

    def test_embed_rejects_whitespace_only(self, servicer, mock_context) -> None:
        """Test that whitespace-only strings set INVALID_ARGUMENT."""
        valid_long_text = "This is a valid text that is definitely longer than fifty characters."
        request = EmbedRequest(texts=[valid_long_text, "   \n\t  "])

        servicer.Embed(request, mock_context)

        mock_context.set_code.assert_called_once_with(
            grpc.StatusCode.INVALID_ARGUMENT,
        )
        details = mock_context.set_details.call_args[0][0]
        assert "only whitespace" in details

    def test_embed_rejects_too_short_text(self, servicer, mock_context) -> None:
        """Test that texts below 50 characters set INVALID_ARGUMENT."""
        short_text = "Too short"
        request = EmbedRequest(texts=[short_text])

        servicer.Embed(request, mock_context)

        mock_context.set_code.assert_called_once_with(
            grpc.StatusCode.INVALID_ARGUMENT,
        )
        details = mock_context.set_details.call_args[0][0]
        assert "too short" in details
        assert "minimum 50" in details

    def test_embed_accepts_valid_texts(self, servicer, mock_context) -> None:
        """Test that valid texts are accepted without error status."""
        valid_text = "This is a valid text that is long enough to pass validation and be embedded properly."
        request = EmbedRequest(texts=[valid_text])

        with patch("embedder.main.SentenceEncoder.encode") as mock_encode:
            mock_encode.return_value = [[0.1] * 384]

            response = servicer.Embed(request, mock_context)

            mock_context.set_code.assert_not_called()
            assert len(response.embeddings) == 1

    def test_embed_validates_all_texts_in_batch(self, servicer, mock_context) -> None:
        """Test that all texts in a batch are validated."""
        texts = [
            "This is the first valid text that is long enough to pass validation.",
            "Short",
            "This is the third valid text that is long enough to pass validation.",
        ]
        request = EmbedRequest(texts=texts)

        servicer.Embed(request, mock_context)

        mock_context.set_code.assert_called_once_with(
            grpc.StatusCode.INVALID_ARGUMENT,
        )
        details = mock_context.set_details.call_args[0][0]
        assert "index 1" in details
        assert "too short" in details

    def test_embed_trims_whitespace_for_length_check(self, servicer, mock_context) -> None:
        """Test that leading/trailing whitespace is trimmed for length validation."""
        text_with_spaces = "    This text has exactly sixty characters of actual content!     "
        request = EmbedRequest(texts=[text_with_spaces])

        with patch("embedder.main.SentenceEncoder.encode") as mock_encode:
            mock_encode.return_value = [[0.1] * 384]

            response = servicer.Embed(request, mock_context)

            mock_context.set_code.assert_not_called()
            assert len(response.embeddings) == 1

    def test_embed_validation_order(self, servicer, mock_context) -> None:
        """Test that validation checks run in correct order."""
        request = EmbedRequest(texts=[""])

        servicer.Embed(request, mock_context)

        details = mock_context.set_details.call_args[0][0]
        assert "is empty" in details
        assert "too short" not in details
