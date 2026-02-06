"""Unit tests for Ingestor Service configuration."""

import os
from unittest.mock import patch

import pytest

from ingestor.config import IngestorSettings, get_settings, reset_settings


class TestIngestorSettings:
    """Tests for IngestorSettings."""

    def setup_method(self) -> None:
        """Reset settings before each test."""
        reset_settings()

    def teardown_method(self) -> None:
        """Reset settings after each test."""
        reset_settings()

    def test_default_values(self) -> None:
        """Test default configuration values."""
        settings = IngestorSettings()

        assert settings.enabled is True
        assert settings.health_port == 8080
        assert settings.database_echo is False
        assert settings.chunk_size == 512
        assert settings.chunk_overlap == 50
        assert settings.max_retries == 3
        assert settings.retry_base_delay == 1.0
        assert settings.log_level == "INFO"

    def test_database_url_default(self) -> None:
        """Test default database URL."""
        settings = IngestorSettings()

        assert "postgresql+asyncpg" in settings.database_url
        assert "echomind" in settings.database_url

    def test_nats_defaults(self) -> None:
        """Test NATS default configuration."""
        settings = IngestorSettings()

        assert settings.nats_url == "nats://localhost:4222"
        assert settings.nats_stream_name == "ECHOMIND"
        assert settings.nats_consumer_name == "ingestor-consumer"
        assert settings.nats_user is None
        assert settings.nats_password is None

    def test_minio_defaults(self) -> None:
        """Test MinIO default configuration."""
        settings = IngestorSettings()

        assert settings.minio_endpoint == "localhost:9000"
        assert settings.minio_access_key == "minioadmin"
        assert settings.minio_secret_key == "minioadmin"
        assert settings.minio_secure is False
        assert settings.minio_bucket == "echomind-documents"

    def test_qdrant_defaults(self) -> None:
        """Test Qdrant default configuration."""
        settings = IngestorSettings()

        assert settings.qdrant_host == "localhost"
        assert settings.qdrant_port == 6333
        assert settings.qdrant_api_key is None

    def test_embedder_defaults(self) -> None:
        """Test Embedder gRPC default configuration."""
        settings = IngestorSettings()

        assert settings.embedder_host == "echomind-embedder"
        assert settings.embedder_port == 50051
        assert settings.embedder_timeout == 30.0

    def test_extraction_defaults(self) -> None:
        """Test nv-ingest extraction default configuration."""
        settings = IngestorSettings()

        assert settings.extract_method == "pdfium"
        assert settings.chunk_size == 512
        assert settings.chunk_overlap == 50
        assert settings.tokenizer == "meta-llama/Llama-3.2-1B"

    def test_optional_nims_disabled_by_default(self) -> None:
        """Test optional NIMs are disabled by default."""
        settings = IngestorSettings()

        assert settings.yolox_enabled is False
        assert settings.riva_enabled is False

    def test_env_prefix(self) -> None:
        """Test environment variable prefix."""
        with patch.dict(os.environ, {"INGESTOR_ENABLED": "false"}):
            settings = IngestorSettings()
            assert settings.enabled is False

    def test_custom_chunk_settings(self) -> None:
        """Test custom chunk settings from environment."""
        with patch.dict(
            os.environ,
            {
                "INGESTOR_CHUNK_SIZE": "1024",
                "INGESTOR_CHUNK_OVERLAP": "100",
            },
        ):
            settings = IngestorSettings()
            assert settings.chunk_size == 1024
            assert settings.chunk_overlap == 100

    def test_custom_embedder_settings(self) -> None:
        """Test custom embedder settings from environment."""
        with patch.dict(
            os.environ,
            {
                "INGESTOR_EMBEDDER_HOST": "custom-embedder",
                "INGESTOR_EMBEDDER_PORT": "9999",
                "INGESTOR_EMBEDDER_TIMEOUT": "60.0",
            },
        ):
            settings = IngestorSettings()
            assert settings.embedder_host == "custom-embedder"
            assert settings.embedder_port == 9999
            assert settings.embedder_timeout == 60.0

    def test_log_level_validation_valid(self) -> None:
        """Test log level validation accepts valid levels."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            with patch.dict(os.environ, {"INGESTOR_LOG_LEVEL": level}):
                settings = IngestorSettings()
                assert settings.log_level == level

    def test_log_level_validation_case_insensitive(self) -> None:
        """Test log level validation is case insensitive."""
        with patch.dict(os.environ, {"INGESTOR_LOG_LEVEL": "debug"}):
            settings = IngestorSettings()
            assert settings.log_level == "DEBUG"

    def test_log_level_validation_invalid(self) -> None:
        """Test log level validation rejects invalid levels."""
        with patch.dict(os.environ, {"INGESTOR_LOG_LEVEL": "INVALID"}):
            with pytest.raises(ValueError, match="Invalid log level"):
                IngestorSettings()

    def test_extract_method_validation_valid(self) -> None:
        """Test extract method validation accepts valid methods."""
        for method in ["pdfium", "pdfium_hybrid", "nemotron_parse"]:
            with patch.dict(os.environ, {"INGESTOR_EXTRACT_METHOD": method}):
                settings = IngestorSettings()
                assert settings.extract_method == method

    def test_extract_method_validation_invalid(self) -> None:
        """Test extract method validation rejects invalid methods."""
        with patch.dict(os.environ, {"INGESTOR_EXTRACT_METHOD": "invalid"}):
            with pytest.raises(ValueError, match="Invalid extract method"):
                IngestorSettings()

    def test_chunk_size_constraints(self) -> None:
        """Test chunk size constraints."""
        # Test minimum (gt=0)
        with patch.dict(os.environ, {"INGESTOR_CHUNK_SIZE": "0"}):
            with pytest.raises(ValueError):
                IngestorSettings()

        # Test maximum (le=8192)
        with patch.dict(os.environ, {"INGESTOR_CHUNK_SIZE": "9000"}):
            with pytest.raises(ValueError):
                IngestorSettings()

    def test_chunk_overlap_constraint(self) -> None:
        """Test chunk overlap minimum constraint."""
        with patch.dict(os.environ, {"INGESTOR_CHUNK_OVERLAP": "-1"}):
            with pytest.raises(ValueError):
                IngestorSettings()


class TestGetSettings:
    """Tests for get_settings function."""

    def setup_method(self) -> None:
        """Reset settings before each test."""
        reset_settings()

    def teardown_method(self) -> None:
        """Reset settings after each test."""
        reset_settings()

    def test_returns_settings(self) -> None:
        """Test get_settings returns IngestorSettings instance."""
        settings = get_settings()

        assert isinstance(settings, IngestorSettings)

    def test_caches_settings(self) -> None:
        """Test settings are cached after first call."""
        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2

    def test_reset_clears_cache(self) -> None:
        """Test reset_settings clears the cache."""
        settings1 = get_settings()
        reset_settings()
        settings2 = get_settings()

        assert settings1 is not settings2
