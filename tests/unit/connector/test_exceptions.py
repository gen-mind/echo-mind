"""Unit tests for Connector Service exceptions."""

import pytest

from connector.logic.exceptions import (
    AuthenticationError,
    CheckpointError,
    ConnectorError,
    DatabaseError,
    DownloadError,
    ExportError,
    FileTooLargeError,
    MinioUploadError,
    PermissionError,
    ProviderError,
    ProviderNotFoundError,
    RateLimitError,
)


class TestConnectorError:
    """Tests for base ConnectorError."""

    def test_stores_message(self) -> None:
        """Test error stores message."""
        error = ConnectorError("Test error")

        assert error.message == "Test error"
        assert str(error) == "Test error"

    def test_is_exception(self) -> None:
        """Test error is an Exception."""
        error = ConnectorError("Test")

        assert isinstance(error, Exception)


class TestProviderError:
    """Tests for ProviderError."""

    def test_stores_provider(self) -> None:
        """Test error stores provider name."""
        error = ProviderError("google_drive", "Connection failed")

        assert error.provider == "google_drive"
        assert "[google_drive]" in str(error)

    def test_inherits_connector_error(self) -> None:
        """Test error inherits from ConnectorError."""
        error = ProviderError("onedrive", "Test")

        assert isinstance(error, ConnectorError)


class TestAuthenticationError:
    """Tests for AuthenticationError."""

    def test_stores_reason(self) -> None:
        """Test error stores reason."""
        error = AuthenticationError("google_drive", "Invalid token")

        assert error.provider == "google_drive"
        assert error.reason == "Invalid token"
        assert "Authentication failed" in str(error)

    def test_inherits_provider_error(self) -> None:
        """Test error inherits from ProviderError."""
        error = AuthenticationError("onedrive", "Expired")

        assert isinstance(error, ProviderError)


class TestDownloadError:
    """Tests for DownloadError."""

    def test_stores_file_id(self) -> None:
        """Test error stores file ID."""
        error = DownloadError("google_drive", "file123", "Network error")

        assert error.file_id == "file123"
        assert error.reason == "Network error"
        assert "file123" in str(error)

    def test_inherits_provider_error(self) -> None:
        """Test error inherits from ProviderError."""
        error = DownloadError("onedrive", "abc", "Error")

        assert isinstance(error, ProviderError)


class TestExportError:
    """Tests for ExportError."""

    def test_stores_mime_type(self) -> None:
        """Test error stores MIME type."""
        error = ExportError("google_drive", "file123", "application/pdf", "Too large")

        assert error.file_id == "file123"
        assert error.mime_type == "application/pdf"
        assert error.reason == "Too large"

    def test_message_format(self) -> None:
        """Test error message format."""
        error = ExportError("google_drive", "abc", "application/pdf", "Failed")

        assert "abc" in str(error)
        assert "application/pdf" in str(error)


class TestFileTooLargeError:
    """Tests for FileTooLargeError."""

    def test_stores_size_info(self) -> None:
        """Test error stores size information."""
        error = FileTooLargeError("google_drive", "file123", 200_000_000, 100_000_000)

        assert error.file_id == "file123"
        assert error.size == 200_000_000
        assert error.limit == 100_000_000

    def test_message_includes_sizes(self) -> None:
        """Test message includes size information."""
        error = FileTooLargeError("onedrive", "abc", 150, 100)

        assert "150" in str(error)
        assert "100" in str(error)


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_stores_retry_after(self) -> None:
        """Test error stores retry after value."""
        error = RateLimitError("google_drive", retry_after=60)

        assert error.retry_after == 60
        assert "60" in str(error)

    def test_retry_after_optional(self) -> None:
        """Test retry_after is optional."""
        error = RateLimitError("onedrive")

        assert error.retry_after is None
        assert "Rate limit exceeded" in str(error)


class TestCheckpointError:
    """Tests for CheckpointError."""

    def test_stores_connector_id(self) -> None:
        """Test error stores connector ID."""
        error = CheckpointError(123, "Invalid state")

        assert error.connector_id == 123
        assert error.reason == "Invalid state"
        assert "123" in str(error)

    def test_inherits_connector_error(self) -> None:
        """Test error inherits from ConnectorError."""
        error = CheckpointError(1, "Error")

        assert isinstance(error, ConnectorError)


class TestProviderNotFoundError:
    """Tests for ProviderNotFoundError."""

    def test_stores_provider_type(self) -> None:
        """Test error stores provider type."""
        error = ProviderNotFoundError("unknown_provider")

        assert error.provider_type == "unknown_provider"
        assert "unknown_provider" in str(error)


class TestPermissionError:
    """Tests for PermissionError."""

    def test_stores_file_id(self) -> None:
        """Test error stores file ID."""
        error = PermissionError("google_drive", "file123", "Access denied")

        assert error.file_id == "file123"
        assert error.reason == "Access denied"


class TestMinioUploadError:
    """Tests for MinioUploadError."""

    def test_stores_object_name(self) -> None:
        """Test error stores object name."""
        error = MinioUploadError("bucket/file.pdf", "Connection refused")

        assert error.object_name == "bucket/file.pdf"
        assert error.reason == "Connection refused"


class TestDatabaseError:
    """Tests for DatabaseError."""

    def test_stores_operation(self) -> None:
        """Test error stores operation name."""
        error = DatabaseError("insert", "Constraint violation")

        assert error.operation == "insert"
        assert error.reason == "Constraint violation"
        assert "insert" in str(error)
