"""Unit tests for Ingestor error handling middleware."""

import pytest

from ingestor.logic.exceptions import (
    AudioExtractionError,
    ChunkingError,
    DatabaseError,
    DocumentNotFoundError,
    EmbeddingError,
    ExtractionError,
    FileNotFoundInStorageError,
    GrpcError,
    IngestorError,
    MinioError,
    NatsError,
    UnsupportedMimeTypeError,
    ValidationError,
)
from ingestor.middleware.error_handler import handle_ingestor_error


class TestHandleIngestorError:
    """Tests for handle_ingestor_error function."""

    # ==========================================
    # Terminal errors (should NOT retry)
    # ==========================================

    @pytest.mark.asyncio
    async def test_validation_error_no_retry(self) -> None:
        """Test ValidationError is terminal (no retry)."""
        error = ValidationError("invalid input", field="document_id")

        result = await handle_ingestor_error(error)

        assert result["should_retry"] is False
        assert result["error_type"] == "ValidationError"
        assert "field" in result["details"]
        assert result["details"]["field"] == "document_id"

    @pytest.mark.asyncio
    async def test_document_not_found_error_no_retry(self) -> None:
        """Test DocumentNotFoundError is terminal (no retry)."""
        error = DocumentNotFoundError(123)

        result = await handle_ingestor_error(error)

        assert result["should_retry"] is False
        assert result["error_type"] == "DocumentNotFoundError"
        assert result["details"]["document_id"] == 123

    @pytest.mark.asyncio
    async def test_unsupported_mime_type_error_no_retry(self) -> None:
        """Test UnsupportedMimeTypeError is terminal (no retry)."""
        error = UnsupportedMimeTypeError("application/x-unknown")

        result = await handle_ingestor_error(error)

        assert result["should_retry"] is False
        assert result["error_type"] == "UnsupportedMimeTypeError"
        assert result["details"]["mime_type"] == "application/x-unknown"

    # ==========================================
    # Transient errors (should retry)
    # ==========================================

    @pytest.mark.asyncio
    async def test_file_not_found_error_should_retry(self) -> None:
        """Test FileNotFoundInStorageError is transient (retry after 5s)."""
        error = FileNotFoundInStorageError("path/to/file.pdf", "documents")

        result = await handle_ingestor_error(error)

        assert result["should_retry"] is True
        assert result["retry_after"] == 5.0
        assert result["details"]["file_path"] == "path/to/file.pdf"
        assert result["details"]["bucket"] == "documents"

    @pytest.mark.asyncio
    async def test_transient_extraction_error_should_retry(self) -> None:
        """Test transient ExtractionError should retry."""
        error = ExtractionError(
            source_type="pdf",
            reason="NIM unavailable",
            document_id=123,
            is_transient=True,
        )

        result = await handle_ingestor_error(error)

        assert result["should_retry"] is True
        assert result["retry_after"] == 10.0
        assert result["details"]["source_type"] == "pdf"
        assert result["details"]["document_id"] == 123

    @pytest.mark.asyncio
    async def test_terminal_extraction_error_no_retry(self) -> None:
        """Test terminal ExtractionError should NOT retry."""
        error = ExtractionError(
            source_type="pdf",
            reason="corrupt file",
            is_transient=False,
        )

        result = await handle_ingestor_error(error)

        assert result["should_retry"] is False
        assert result["details"]["source_type"] == "pdf"

    @pytest.mark.asyncio
    async def test_audio_extraction_error_should_retry(self) -> None:
        """Test AudioExtractionError should retry (Riva NIM transient)."""
        error = AudioExtractionError("Riva unavailable")

        result = await handle_ingestor_error(error)

        assert result["should_retry"] is True
        assert result["retry_after"] == 30.0  # Longer delay for NIM

    @pytest.mark.asyncio
    async def test_transient_chunking_error_should_retry(self) -> None:
        """Test transient ChunkingError should retry."""
        error = ChunkingError("tokenizer download failed", is_transient=True)

        result = await handle_ingestor_error(error)

        assert result["should_retry"] is True
        assert result["retry_after"] == 5.0

    @pytest.mark.asyncio
    async def test_terminal_chunking_error_no_retry(self) -> None:
        """Test terminal ChunkingError should NOT retry."""
        error = ChunkingError("invalid content", is_transient=False)

        result = await handle_ingestor_error(error)

        assert result["should_retry"] is False

    @pytest.mark.asyncio
    async def test_embedding_error_should_retry(self) -> None:
        """Test EmbeddingError should retry (service may be overloaded)."""
        error = EmbeddingError("timeout", document_id=456, chunk_index=10)

        result = await handle_ingestor_error(error)

        assert result["should_retry"] is True
        assert result["retry_after"] == 10.0
        assert result["details"]["document_id"] == 456
        assert result["details"]["chunk_index"] == 10

    @pytest.mark.asyncio
    async def test_minio_error_should_retry(self) -> None:
        """Test MinioError should retry (transient network issue)."""
        error = MinioError("download", "connection refused")

        result = await handle_ingestor_error(error)

        assert result["should_retry"] is True
        assert result["retry_after"] == 5.0
        assert result["details"]["operation"] == "download"

    @pytest.mark.asyncio
    async def test_database_error_should_retry(self) -> None:
        """Test DatabaseError should retry (connection issue)."""
        error = DatabaseError("select", "connection pool exhausted")

        result = await handle_ingestor_error(error)

        assert result["should_retry"] is True
        assert result["retry_after"] == 5.0
        assert result["details"]["operation"] == "select"

    @pytest.mark.asyncio
    async def test_grpc_error_should_retry(self) -> None:
        """Test GrpcError should retry (service unavailable)."""
        error = GrpcError("embedder", "connection refused", code="UNAVAILABLE")

        result = await handle_ingestor_error(error)

        assert result["should_retry"] is True
        assert result["retry_after"] == 10.0
        assert result["details"]["service"] == "embedder"
        assert result["details"]["code"] == "UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_nats_error_should_retry(self) -> None:
        """Test NatsError should retry (connection issue)."""
        error = NatsError("ack", "connection lost")

        result = await handle_ingestor_error(error)

        assert result["should_retry"] is True
        assert result["retry_after"] == 5.0
        assert result["details"]["operation"] == "ack"

    # ==========================================
    # Error info structure tests
    # ==========================================

    @pytest.mark.asyncio
    async def test_error_info_has_required_fields(self) -> None:
        """Test error info contains all required fields."""
        error = ValidationError("test")

        result = await handle_ingestor_error(error)

        assert "error_type" in result
        assert "message" in result
        assert "should_retry" in result
        assert "retry_after" in result
        assert "details" in result

    @pytest.mark.asyncio
    async def test_error_info_message_from_exception(self) -> None:
        """Test error info message comes from exception."""
        error = IngestorError("custom error message")

        result = await handle_ingestor_error(error)

        assert result["message"] == "custom error message"

    @pytest.mark.asyncio
    async def test_error_type_is_class_name(self) -> None:
        """Test error_type is exception class name."""
        errors = [
            (ValidationError("test"), "ValidationError"),
            (DocumentNotFoundError(1), "DocumentNotFoundError"),
            (MinioError("op", "reason"), "MinioError"),
            (GrpcError("svc", "reason"), "GrpcError"),
        ]

        for error, expected_type in errors:
            result = await handle_ingestor_error(error)
            assert result["error_type"] == expected_type

    @pytest.mark.asyncio
    async def test_details_is_dict(self) -> None:
        """Test details is always a dictionary."""
        error = ValidationError("test")

        result = await handle_ingestor_error(error)

        assert isinstance(result["details"], dict)

    # ==========================================
    # Unknown error handling
    # ==========================================

    @pytest.mark.asyncio
    async def test_unknown_ingestor_error_defaults_to_retry(self) -> None:
        """Test unknown IngestorError subclass defaults to retry."""
        # Create a custom error that's not explicitly handled
        class CustomIngestorError(IngestorError):
            pass

        error = CustomIngestorError("unknown error")

        result = await handle_ingestor_error(error)

        # Should default to retry for safety
        assert result["should_retry"] is True
        assert result["retry_after"] == 30.0

    # ==========================================
    # Retry delay tests
    # ==========================================

    @pytest.mark.asyncio
    async def test_retry_delays_are_appropriate(self) -> None:
        """Test retry delays are appropriate for error types."""
        # Short delays (5s) for quick transients
        short_delay_errors = [
            FileNotFoundInStorageError("p", "b"),
            MinioError("op", "r"),
            DatabaseError("op", "r"),
            NatsError("op", "r"),
        ]
        for error in short_delay_errors:
            result = await handle_ingestor_error(error)
            assert result["retry_after"] == 5.0

        # Medium delays (10s) for service overload
        medium_delay_errors = [
            GrpcError("svc", "r"),
            EmbeddingError("r"),
        ]
        for error in medium_delay_errors:
            result = await handle_ingestor_error(error)
            assert result["retry_after"] == 10.0

        # Long delays (30s) for NIM availability
        long_delay_errors = [
            AudioExtractionError("r"),
        ]
        for error in long_delay_errors:
            result = await handle_ingestor_error(error)
            assert result["retry_after"] == 30.0

    @pytest.mark.asyncio
    async def test_terminal_errors_have_no_retry_delay(self) -> None:
        """Test terminal errors have None retry_after."""
        terminal_errors = [
            ValidationError("test"),
            DocumentNotFoundError(1),
            UnsupportedMimeTypeError("type"),
        ]

        for error in terminal_errors:
            result = await handle_ingestor_error(error)
            assert result["retry_after"] is None


class TestErrorHandlerIntegration:
    """Integration tests for error handler with NATS semantics."""

    @pytest.mark.asyncio
    async def test_terminal_errors_should_term_message(self) -> None:
        """Test terminal errors result in message termination (no redeliver)."""
        terminal_errors = [
            ValidationError("invalid input"),
            DocumentNotFoundError(999),
            UnsupportedMimeTypeError("unknown/type"),
            ExtractionError("pdf", "corrupt", is_transient=False),
            ChunkingError("invalid content", is_transient=False),
        ]

        for error in terminal_errors:
            result = await handle_ingestor_error(error)
            # NATS should call msg.term() for these
            assert result["should_retry"] is False

    @pytest.mark.asyncio
    async def test_transient_errors_should_nak_message(self) -> None:
        """Test transient errors result in message NAK (redeliver)."""
        transient_errors = [
            FileNotFoundInStorageError("path", "bucket"),
            ExtractionError("pdf", "NIM down", is_transient=True),
            AudioExtractionError("Riva down"),
            ChunkingError("tokenizer error", is_transient=True),
            EmbeddingError("timeout"),
            MinioError("download", "network"),
            DatabaseError("query", "pool"),
            GrpcError("embedder", "unavailable"),
            NatsError("ack", "lost"),
        ]

        for error in transient_errors:
            result = await handle_ingestor_error(error)
            # NATS should call msg.nak() for these
            assert result["should_retry"] is True
