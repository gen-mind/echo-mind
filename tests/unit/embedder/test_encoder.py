"""Unit tests for SentenceEncoder."""

from unittest import mock

import pytest

from embedder.logic.encoder import NVIDIA_EMBED_MODELS, SentenceEncoder
from embedder.logic.exceptions import EncodingError, ModelNotFoundError


class TestSentenceEncoder:
    """Tests for SentenceEncoder class."""

    def setup_method(self) -> None:
        """Reset encoder state before each test."""
        SentenceEncoder.clear_cache()
        SentenceEncoder._device = None
        SentenceEncoder._cache_limit = 1

    def test_set_cache_limit(self) -> None:
        """Test setting cache limit."""
        SentenceEncoder.set_cache_limit(5)
        assert SentenceEncoder._cache_limit == 5

    def test_set_cache_limit_minimum(self) -> None:
        """Test that cache limit has minimum of 1."""
        SentenceEncoder.set_cache_limit(0)
        assert SentenceEncoder._cache_limit == 1

        SentenceEncoder.set_cache_limit(-5)
        assert SentenceEncoder._cache_limit == 1

    def test_set_device(self) -> None:
        """Test setting device."""
        SentenceEncoder.set_device("cpu")
        assert SentenceEncoder._device == "cpu"

    def test_clear_cache(self) -> None:
        """Test clearing model cache."""
        SentenceEncoder._model_cache["test-model"] = mock.MagicMock()
        assert len(SentenceEncoder._model_cache) == 1

        SentenceEncoder.clear_cache()
        assert len(SentenceEncoder._model_cache) == 0

    def test_get_cached_models_empty(self) -> None:
        """Test getting cached models when empty."""
        models = SentenceEncoder.get_cached_models()
        assert models == []

    def test_get_cached_models(self) -> None:
        """Test getting list of cached models."""
        SentenceEncoder._model_cache["model-a"] = mock.MagicMock()
        SentenceEncoder._model_cache["model-b"] = mock.MagicMock()

        models = SentenceEncoder.get_cached_models()
        assert "model-a" in models
        assert "model-b" in models

    def test_encode_empty_list(self) -> None:
        """Test encoding empty list returns empty list."""
        result = SentenceEncoder.encode(
            texts=[],
            model_name="any-model",
        )
        assert result == []

    @mock.patch("embedder.logic.encoder.SentenceTransformer")
    def test_encode_success(self, mock_transformer_class: mock.MagicMock) -> None:
        """Test successful encoding."""
        import numpy as np

        mock_model = mock.MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        mock_model.get_sentence_embedding_dimension.return_value = 3
        mock_transformer_class.return_value = mock_model

        SentenceEncoder.set_device("cpu")

        result = SentenceEncoder.encode(
            texts=["hello", "world"],
            model_name="test-model",
            batch_size=32,
        )

        assert len(result) == 2
        assert result[0] == pytest.approx([0.1, 0.2, 0.3])
        assert result[1] == pytest.approx([0.4, 0.5, 0.6])

        mock_model.encode.assert_called_once_with(
            ["hello", "world"],
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    @mock.patch("embedder.logic.encoder.SentenceTransformer")
    def test_get_dimension(self, mock_transformer_class: mock.MagicMock) -> None:
        """Test getting model dimension."""
        mock_model = mock.MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_transformer_class.return_value = mock_model

        SentenceEncoder.set_device("cpu")

        dim = SentenceEncoder.get_dimension("test-model")
        assert dim == 384

    @mock.patch("embedder.logic.encoder.SentenceTransformer")
    def test_model_caching(self, mock_transformer_class: mock.MagicMock) -> None:
        """Test that models are cached."""
        mock_model = mock.MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_transformer_class.return_value = mock_model

        SentenceEncoder.set_device("cpu")

        SentenceEncoder.get_dimension("test-model")
        assert mock_transformer_class.call_count == 1

        SentenceEncoder.get_dimension("test-model")
        assert mock_transformer_class.call_count == 1  # Still 1, used cache

    @mock.patch("embedder.logic.encoder.SentenceTransformer")
    def test_cache_eviction(self, mock_transformer_class: mock.MagicMock) -> None:
        """Test that oldest model is evicted when cache is full."""
        mock_model = mock.MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_transformer_class.return_value = mock_model

        SentenceEncoder.set_device("cpu")
        SentenceEncoder.set_cache_limit(1)

        SentenceEncoder.get_dimension("model-a")
        assert "model-a" in SentenceEncoder.get_cached_models()

        SentenceEncoder.get_dimension("model-b")
        assert "model-b" in SentenceEncoder.get_cached_models()
        assert "model-a" not in SentenceEncoder.get_cached_models()

    @mock.patch("embedder.logic.encoder.SentenceTransformer")
    def test_model_not_found_error(self, mock_transformer_class: mock.MagicMock) -> None:
        """Test ModelNotFoundError is raised when model fails to load."""
        mock_transformer_class.side_effect = Exception("Model not found")
        SentenceEncoder.set_device("cpu")

        with pytest.raises(ModelNotFoundError) as exc_info:
            SentenceEncoder.get_dimension("nonexistent-model")

        assert exc_info.value.model_name == "nonexistent-model"

    @mock.patch("embedder.logic.encoder.SentenceTransformer")
    def test_encoding_error(self, mock_transformer_class: mock.MagicMock) -> None:
        """Test EncodingError is raised when encoding fails."""
        mock_model = mock.MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_model.encode.side_effect = Exception("Encoding failed")
        mock_transformer_class.return_value = mock_model

        SentenceEncoder.set_device("cpu")

        with pytest.raises(EncodingError) as exc_info:
            SentenceEncoder.encode(texts=["test"], model_name="test-model")

        assert exc_info.value.texts_count == 1


class TestExceptions:
    """Tests for encoder exceptions."""

    def test_model_not_found_error_message(self) -> None:
        """Test ModelNotFoundError message format."""
        error = ModelNotFoundError("my-model")
        assert error.model_name == "my-model"
        assert "my-model" in str(error)

    def test_encoding_error_message(self) -> None:
        """Test EncodingError message format."""
        error = EncodingError("failed to encode", 5)
        assert error.texts_count == 5
        assert "5 texts" in str(error)
        assert "failed to encode" in str(error)


class TestNvidiaModelSupport:
    """Tests for NVIDIA embedding model support."""

    def setup_method(self) -> None:
        """Reset encoder state before each test."""
        SentenceEncoder.clear_cache()
        SentenceEncoder._device = None
        SentenceEncoder._cache_limit = 1

    def test_is_nvidia_model_true(self) -> None:
        """Test NVIDIA model detection."""
        for model_name in NVIDIA_EMBED_MODELS:
            assert SentenceEncoder._is_nvidia_model(model_name) is True

    def test_is_nvidia_model_false(self) -> None:
        """Test non-NVIDIA model detection."""
        assert SentenceEncoder._is_nvidia_model("sentence-transformers/all-MiniLM-L6-v2") is False
        assert SentenceEncoder._is_nvidia_model("intfloat/e5-large-v2") is False

    @mock.patch("embedder.logic.encoder.SentenceTransformer")
    def test_nvidia_model_loads_with_trust_remote_code(
        self, mock_transformer_class: mock.MagicMock
    ) -> None:
        """Test that NVIDIA models are loaded with trust_remote_code=True."""
        import torch

        mock_model = mock.MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 2048
        mock_transformer_class.return_value = mock_model

        SentenceEncoder.set_device("cpu")
        SentenceEncoder.get_dimension("nvidia/llama-nemotron-embed-1b-v2")

        mock_transformer_class.assert_called_once_with(
            "nvidia/llama-nemotron-embed-1b-v2",
            device="cpu",
            trust_remote_code=True,
            model_kwargs={"torch_dtype": torch.bfloat16},
        )

    @mock.patch("embedder.logic.encoder.SentenceTransformer")
    def test_nvidia_model_uses_encode_document(
        self, mock_transformer_class: mock.MagicMock
    ) -> None:
        """Test that NVIDIA models use encode_document method."""
        import numpy as np

        mock_model = mock.MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 2048
        mock_model.encode_document.return_value = np.array([[0.1, 0.2, 0.3]])
        mock_transformer_class.return_value = mock_model

        SentenceEncoder.set_device("cpu")
        result = SentenceEncoder.encode_document(
            texts=["hello"],
            model_name="nvidia/llama-nemotron-embed-1b-v2",
        )

        mock_model.encode_document.assert_called_once_with(["hello"])
        assert len(result) == 1

    @mock.patch("embedder.logic.encoder.SentenceTransformer")
    def test_nvidia_model_uses_encode_query(
        self, mock_transformer_class: mock.MagicMock
    ) -> None:
        """Test that NVIDIA models use encode_query method."""
        import numpy as np

        mock_model = mock.MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 2048
        mock_model.encode_query.return_value = np.array([[0.1, 0.2, 0.3]])
        mock_transformer_class.return_value = mock_model

        SentenceEncoder.set_device("cpu")
        result = SentenceEncoder.encode_query(
            texts=["hello"],
            model_name="nvidia/llama-nemotron-embed-1b-v2",
        )

        mock_model.encode_query.assert_called_once_with(["hello"])
        assert len(result) == 1

    @mock.patch("embedder.logic.encoder.SentenceTransformer")
    def test_standard_model_loads_without_trust_remote_code(
        self, mock_transformer_class: mock.MagicMock
    ) -> None:
        """Test that standard models are loaded without trust_remote_code."""
        mock_model = mock.MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_transformer_class.return_value = mock_model

        SentenceEncoder.set_device("cpu")
        SentenceEncoder.get_dimension("sentence-transformers/all-MiniLM-L6-v2")

        mock_transformer_class.assert_called_once_with(
            "sentence-transformers/all-MiniLM-L6-v2",
            device="cpu",
        )
