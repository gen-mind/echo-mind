"""
Base provider interface for external data sources.

All connector providers must implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator

from connector.logic.checkpoint import ConnectorCheckpoint
from connector.logic.permissions import ExternalAccess


@dataclass
class FileMetadata:
    """
    Metadata for a file from an external source.

    Contains information needed for change detection and download.
    """

    source_id: str
    name: str
    mime_type: str
    size: int | None = None
    content_hash: str | None = None  # md5 for GDrive, cTag for OneDrive
    modified_at: datetime | None = None
    created_at: datetime | None = None
    web_url: str | None = None
    parent_id: str | None = None

    # Provider-specific metadata
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class FileChange:
    """
    Represents a detected change to a file.

    Used by change detection to signal what needs to be processed.
    """

    source_id: str
    action: str  # "create", "update", "delete"
    file: FileMetadata | None = None  # None for deletes


@dataclass
class DownloadedFile:
    """
    A file downloaded from an external source.

    Contains the file content and all metadata needed for processing.
    """

    source_id: str
    name: str
    content: bytes
    mime_type: str
    content_hash: str | None
    modified_at: datetime | None
    external_access: ExternalAccess

    # For parent-child relationships
    parent_id: str | None = None

    # Original URL from provider
    original_url: str | None = None


@dataclass
class DeletedFile:
    """Represents a file that was deleted from the source."""

    source_id: str


class BaseProvider(ABC):
    """
    Abstract base class for connector providers.

    Each provider (Google Drive, OneDrive) implements this interface
    to handle authentication, change detection, and file download.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Return the provider name for logging and identification.

        Returns:
            Provider name (e.g., 'google_drive', 'onedrive').
        """
        ...

    @abstractmethod
    async def authenticate(self, config: dict[str, Any]) -> None:
        """
        Authenticate with the external service.

        Args:
            config: Provider-specific configuration from connector.config.

        Raises:
            AuthenticationError: If authentication fails.
        """
        ...

    @abstractmethod
    async def check_connection(self) -> bool:
        """
        Verify the connection is still valid.

        Returns:
            True if connected and authenticated, False otherwise.
        """
        ...

    @abstractmethod
    def get_changes(
        self,
        config: dict[str, Any],
        checkpoint: ConnectorCheckpoint,
    ) -> AsyncIterator[FileChange]:
        """
        Detect changes since last sync.

        Uses provider's change/delta API to efficiently find changed files
        without downloading content.

        Args:
            config: Provider-specific configuration.
            checkpoint: Current checkpoint state.

        Yields:
            FileChange objects for each detected change.
        """
        ...

    @abstractmethod
    async def download_file(
        self,
        file: FileMetadata,
        config: dict[str, Any],
    ) -> DownloadedFile:
        """
        Download a file from the external source.

        For Google Workspace files, exports as PDF.

        Args:
            file: File metadata from change detection.
            config: Provider-specific configuration.

        Returns:
            DownloadedFile with content and metadata.

        Raises:
            DownloadError: If download fails.
            ExportError: If Google Workspace export fails.
            FileTooLargeError: If file exceeds size limit.
        """
        ...

    @abstractmethod
    async def get_file_permissions(
        self,
        file: FileMetadata,
        config: dict[str, Any],
    ) -> ExternalAccess:
        """
        Fetch permissions for a file.

        Called on every document sync to keep permissions current.

        Args:
            file: File metadata.
            config: Provider-specific configuration.

        Returns:
            ExternalAccess with permission information.

        Raises:
            PermissionError: If permission fetch fails.
        """
        ...

    @abstractmethod
    def sync(
        self,
        config: dict[str, Any],
        checkpoint: ConnectorCheckpoint,
    ) -> AsyncIterator[DownloadedFile | DeletedFile]:
        """
        Perform a full or incremental sync.

        This is the main entry point for syncing. It:
        1. Detects changes via API metadata
        2. Downloads only changed files
        3. Fetches permissions for each file
        4. Updates checkpoint for resumption

        Args:
            config: Provider-specific configuration.
            checkpoint: Current checkpoint state (will be mutated).

        Yields:
            DownloadedFile or DeletedFile for each change.
        """
        ...

    @abstractmethod
    def create_checkpoint(self) -> ConnectorCheckpoint:
        """
        Create a new checkpoint for this provider.

        Returns:
            Fresh checkpoint instance of the appropriate type.
        """
        ...

    async def close(self) -> None:
        """
        Clean up provider resources.

        Override if the provider needs cleanup (e.g., closing HTTP sessions).
        """
        pass

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<{self.__class__.__name__}>"
