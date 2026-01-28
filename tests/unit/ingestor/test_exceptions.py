"""Unit tests for Ingestor Service domain exceptions."""

import pytest

from ingestor.logic.exceptions import (
    AudioExtractionError,
    ChunkingError,
    DatabaseError,
    DocxExtractionError,
    DocumentNotFoundError,
    EmbeddingError,
    ExtractionError,
    FileNotFoundInStorageError,
    GrpcError,
    HtmlExtractionError,
    ImageExtractionError,
    IngestorError,
    MinioError,
    NatsError,
    PDFExtractionError,
    PptxExtractionError,
    TextExtractionError,
    UnsupportedMimeTypeError,
    ValidationError,
    VideoExtractionError,
)


class TestIngestorError:
    """Tests for base IngestorError."""

    def test_message_attribute(self) -> None:
        """Test error stores message attribute."""
        error = IngestorError("test message")
        assert error.message == "test message"

    def test_str_representation(self) -> None:
        """Test error string representation."""
        error = IngestorError("test message")
        assert str(error) == "test message"

    def test_is_exception(self) -> None:
        """Test IngestorError is an Exception."""
        error = IngestorError("test")
        assert isinstance(error, Exception)


class TestValidationError:
    """Tests for ValidationError."""

    def test_without_field(self) -> None:
        """Test ValidationError without field name."""
        error = ValidationError("invalid input")
        assert "Validation error: invalid input" in error.message
        assert error.field is None

    def test_with_field(self) -> None:
        """Test ValidationError with field name."""
        error = ValidationError("must be positive", field="chunk_size")
        assert "chunk_size" in error.message
        assert error.field == "chunk_size"

    def test_inherits_from_ingestor_error(self) -> None:
        """Test ValidationError inherits from IngestorError."""
        error = ValidationError("test")
        assert isinstance(error, IngestorError)


class TestDocumentNotFoundError:
    """Tests for DocumentNotFoundError."""

    def test_stores_document_id(self) -> None:
        """Test error stores document_id attribute."""
        error = DocumentNotFoundError(123)
        assert error.document_id == 123

    def test_message_includes_id(self) -> None:
        """Test error message includes document ID."""
        error = DocumentNotFoundError(456)
        assert "456" in error.message
        assert "not found" in error.message.lower()


class TestFileNotFoundInStorageError:
    """Tests for FileNotFoundInStorageError."""

    def test_stores_path_and_bucket(self) -> None:
        """Test error stores file_path and bucket attributes."""
        error = FileNotFoundInStorageError("path/to/file.pdf", "documents")
        assert error.file_path == "path/to/file.pdf"
        assert error.bucket == "documents"

    def test_message_includes_path(self) -> None:
        """Test error message includes file path."""
        error = FileNotFoundInStorageError("test.pdf", "mybucket")
        assert "test.pdf" in error.message
        assert "mybucket" in error.message


class TestExtractionError:
    """Tests for ExtractionError."""

    def test_basic_error(self) -> None:
        """Test basic extraction error."""
        error = ExtractionError("pdf", "corrupt file")
        assert error.source_type == "pdf"
        assert error.reason == "corrupt file"
        assert error.document_id is None
        assert error.is_transient is True

    def test_with_document_id(self) -> None:
        """Test extraction error with document ID."""
        error = ExtractionError("docx", "parse failed", document_id=123)
        assert error.document_id == 123
        assert "123" in error.message

    def test_terminal_error(self) -> None:
        """Test non-transient extraction error."""
        error = ExtractionError("pdf", "invalid format", is_transient=False)
        assert error.is_transient is False


class TestSpecificExtractionErrors:
    """Tests for specific extraction error types."""

    def test_pdf_extraction_error(self) -> None:
        """Test PDFExtractionError."""
        error = PDFExtractionError("corrupt PDF", document_id=1)
        assert error.source_type == "PDF"
        assert error.document_id == 1

    def test_docx_extraction_error(self) -> None:
        """Test DocxExtractionError."""
        error = DocxExtractionError("invalid DOCX")
        assert error.source_type == "DOCX"

    def test_pptx_extraction_error(self) -> None:
        """Test PptxExtractionError."""
        error = PptxExtractionError("slides error")
        assert error.source_type == "PPTX"

    def test_html_extraction_error(self) -> None:
        """Test HtmlExtractionError."""
        error = HtmlExtractionError("malformed HTML")
        assert error.source_type == "HTML"

    def test_image_extraction_error(self) -> None:
        """Test ImageExtractionError."""
        error = ImageExtractionError("OCR failed")
        assert error.source_type == "image"

    def test_audio_extraction_error_always_transient(self) -> None:
        """Test AudioExtractionError is always transient."""
        error = AudioExtractionError("Riva unavailable")
        assert error.source_type == "audio"
        assert error.is_transient is True

    def test_video_extraction_error(self) -> None:
        """Test VideoExtractionError."""
        error = VideoExtractionError("frame extraction failed")
        assert error.source_type == "video"

    def test_text_extraction_error_default_terminal(self) -> None:
        """Test TextExtractionError is terminal by default."""
        error = TextExtractionError("encoding error")
        assert error.source_type == "text"
        assert error.is_transient is False


class TestChunkingError:
    """Tests for ChunkingError."""

    def test_basic_error(self) -> None:
        """Test basic chunking error."""
        error = ChunkingError("tokenizer failed")
        assert error.reason == "tokenizer failed"
        assert error.document_id is None
        assert error.is_transient is True

    def test_with_document_id(self) -> None:
        """Test chunking error with document ID."""
        error = ChunkingError("split failed", document_id=456)
        assert error.document_id == 456
        assert "456" in error.message

    def test_terminal_chunking_error(self) -> None:
        """Test non-transient chunking error."""
        error = ChunkingError("invalid content", is_transient=False)
        assert error.is_transient is False


class TestUnsupportedMimeTypeError:
    """Tests for UnsupportedMimeTypeError."""

    def test_stores_mime_type(self) -> None:
        """Test error stores mime_type attribute."""
        error = UnsupportedMimeTypeError("application/x-unknown")
        assert error.mime_type == "application/x-unknown"

    def test_message_includes_mime_type(self) -> None:
        """Test error message includes MIME type."""
        error = UnsupportedMimeTypeError("video/webm")
        assert "video/webm" in error.message


class TestEmbeddingError:
    """Tests for EmbeddingError."""

    def test_basic_error(self) -> None:
        """Test basic embedding error."""
        error = EmbeddingError("model unavailable")
        assert error.reason == "model unavailable"
        assert error.document_id is None
        assert error.chunk_index is None

    def test_with_document_and_chunk(self) -> None:
        """Test embedding error with document and chunk info."""
        error = EmbeddingError("timeout", document_id=123, chunk_index=5)
        assert error.document_id == 123
        assert error.chunk_index == 5
        assert "123" in error.message
        assert "5" in error.message


class TestMinioError:
    """Tests for MinioError."""

    def test_stores_operation_and_reason(self) -> None:
        """Test error stores operation and reason."""
        error = MinioError("download", "connection refused")
        assert error.operation == "download"
        assert error.reason == "connection refused"

    def test_message_format(self) -> None:
        """Test error message format."""
        error = MinioError("upload", "bucket not found")
        assert "upload" in error.message.lower()
        assert "bucket not found" in error.message


class TestDatabaseError:
    """Tests for DatabaseError."""

    def test_stores_operation_and_reason(self) -> None:
        """Test error stores operation and reason."""
        error = DatabaseError("insert", "constraint violation")
        assert error.operation == "insert"
        assert error.reason == "constraint violation"


class TestGrpcError:
    """Tests for GrpcError."""

    def test_basic_error(self) -> None:
        """Test basic gRPC error."""
        error = GrpcError("embedder", "connection failed")
        assert error.service == "embedder"
        assert error.reason == "connection failed"
        assert error.code is None

    def test_with_status_code(self) -> None:
        """Test gRPC error with status code."""
        error = GrpcError("embedder", "timeout", code="DEADLINE_EXCEEDED")
        assert error.code == "DEADLINE_EXCEEDED"
        assert "DEADLINE_EXCEEDED" in error.message


class TestNatsError:
    """Tests for NatsError."""

    def test_stores_operation_and_reason(self) -> None:
        """Test error stores operation and reason."""
        error = NatsError("subscribe", "stream not found")
        assert error.operation == "subscribe"
        assert error.reason == "stream not found"


class TestErrorHierarchy:
    """Tests for exception hierarchy."""

    def test_all_errors_inherit_from_ingestor_error(self) -> None:
        """Test all domain errors inherit from IngestorError."""
        errors = [
            ValidationError("test"),
            DocumentNotFoundError(1),
            FileNotFoundInStorageError("p", "b"),
            ExtractionError("t", "r"),
            PDFExtractionError("r"),
            DocxExtractionError("r"),
            PptxExtractionError("r"),
            HtmlExtractionError("r"),
            ImageExtractionError("r"),
            AudioExtractionError("r"),
            VideoExtractionError("r"),
            TextExtractionError("r"),
            ChunkingError("r"),
            UnsupportedMimeTypeError("t"),
            EmbeddingError("r"),
            MinioError("o", "r"),
            DatabaseError("o", "r"),
            GrpcError("s", "r"),
            NatsError("o", "r"),
        ]

        for error in errors:
            assert isinstance(error, IngestorError)
            assert isinstance(error, Exception)

    def test_extraction_errors_inherit_from_extraction_error(self) -> None:
        """Test specific extraction errors inherit from ExtractionError."""
        errors = [
            PDFExtractionError("r"),
            DocxExtractionError("r"),
            PptxExtractionError("r"),
            HtmlExtractionError("r"),
            ImageExtractionError("r"),
            AudioExtractionError("r"),
            VideoExtractionError("r"),
            TextExtractionError("r"),
        ]

        for error in errors:
            assert isinstance(error, ExtractionError)
