"""
Domain exceptions for the Connector Service.

These exceptions represent business logic errors that can occur
during connector operations.
"""


class ConnectorError(Exception):
    """Base exception for connector errors."""

    def __init__(self, message: str):
        """
        Initialize connector error.

        Args:
            message: Error description.
        """
        self.message = message
        super().__init__(message)


class ProviderError(ConnectorError):
    """Raised when a provider operation fails."""

    def __init__(self, provider: str, message: str):
        """
        Initialize provider error.

        Args:
            provider: Name of the provider (e.g., 'google_drive', 'onedrive').
            message: Error description.
        """
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class AuthenticationError(ProviderError):
    """Raised when authentication with a provider fails."""

    def __init__(self, provider: str, reason: str):
        """
        Initialize authentication error.

        Args:
            provider: Name of the provider.
            reason: Reason for authentication failure.
        """
        self.reason = reason
        super().__init__(provider, f"Authentication failed: {reason}")


class DownloadError(ProviderError):
    """Raised when file download fails."""

    def __init__(self, provider: str, file_id: str, reason: str):
        """
        Initialize download error.

        Args:
            provider: Name of the provider.
            file_id: ID of the file that failed to download.
            reason: Reason for download failure.
        """
        self.file_id = file_id
        self.reason = reason
        super().__init__(provider, f"Failed to download file {file_id}: {reason}")


class ExportError(ProviderError):
    """Raised when Google Workspace file export fails."""

    def __init__(self, provider: str, file_id: str, mime_type: str, reason: str):
        """
        Initialize export error.

        Args:
            provider: Name of the provider.
            file_id: ID of the file that failed to export.
            mime_type: Target MIME type for export.
            reason: Reason for export failure.
        """
        self.file_id = file_id
        self.mime_type = mime_type
        self.reason = reason
        super().__init__(
            provider, f"Failed to export file {file_id} as {mime_type}: {reason}"
        )


class CheckpointError(ConnectorError):
    """Raised when checkpoint operations fail."""

    def __init__(self, connector_id: int, reason: str):
        """
        Initialize checkpoint error.

        Args:
            connector_id: ID of the connector.
            reason: Reason for checkpoint failure.
        """
        self.connector_id = connector_id
        self.reason = reason
        super().__init__(f"Checkpoint error for connector {connector_id}: {reason}")


class ProviderNotFoundError(ConnectorError):
    """Raised when a provider type is not supported."""

    def __init__(self, provider_type: str):
        """
        Initialize provider not found error.

        Args:
            provider_type: The unsupported provider type.
        """
        self.provider_type = provider_type
        super().__init__(f"Unsupported provider type: {provider_type}")


class PermissionError(ProviderError):
    """Raised when permission fetching fails."""

    def __init__(self, provider: str, file_id: str, reason: str):
        """
        Initialize permission error.

        Args:
            provider: Name of the provider.
            file_id: ID of the file.
            reason: Reason for permission fetch failure.
        """
        self.file_id = file_id
        self.reason = reason
        super().__init__(provider, f"Failed to fetch permissions for {file_id}: {reason}")


class RateLimitError(ProviderError):
    """Raised when API rate limit is exceeded."""

    def __init__(self, provider: str, retry_after: int | None = None):
        """
        Initialize rate limit error.

        Args:
            provider: Name of the provider.
            retry_after: Seconds to wait before retrying (if provided by API).
        """
        self.retry_after = retry_after
        msg = "Rate limit exceeded"
        if retry_after:
            msg += f", retry after {retry_after}s"
        super().__init__(provider, msg)


class FileTooLargeError(ProviderError):
    """Raised when file exceeds size limit."""

    def __init__(self, provider: str, file_id: str, size: int, limit: int):
        """
        Initialize file too large error.

        Args:
            provider: Name of the provider.
            file_id: ID of the file.
            size: Actual file size in bytes.
            limit: Maximum allowed size in bytes.
        """
        self.file_id = file_id
        self.size = size
        self.limit = limit
        super().__init__(
            provider,
            f"File {file_id} size ({size} bytes) exceeds limit ({limit} bytes)",
        )


class MinioUploadError(ConnectorError):
    """Raised when MinIO upload fails."""

    def __init__(self, object_name: str, reason: str):
        """
        Initialize MinIO upload error.

        Args:
            object_name: Name of the object that failed to upload.
            reason: Reason for upload failure.
        """
        self.object_name = object_name
        self.reason = reason
        super().__init__(f"Failed to upload {object_name} to MinIO: {reason}")


class DatabaseError(ConnectorError):
    """Raised when database operations fail."""

    def __init__(self, operation: str, reason: str):
        """
        Initialize database error.

        Args:
            operation: The database operation that failed.
            reason: Reason for failure.
        """
        self.operation = operation
        self.reason = reason
        super().__init__(f"Database {operation} failed: {reason}")
