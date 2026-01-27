"""Unit tests for base provider."""

from datetime import datetime, timezone

import pytest

from connector.logic.permissions import ExternalAccess
from connector.logic.providers.base import (
    DeletedFile,
    DownloadedFile,
    FileChange,
    FileMetadata,
)


class TestFileMetadata:
    """Tests for FileMetadata dataclass."""

    def test_required_fields(self) -> None:
        """Test creating metadata with required fields."""
        metadata = FileMetadata(
            source_id="file123",
            name="document.pdf",
            mime_type="application/pdf",
        )

        assert metadata.source_id == "file123"
        assert metadata.name == "document.pdf"
        assert metadata.mime_type == "application/pdf"

    def test_optional_fields_default_none(self) -> None:
        """Test optional fields default to None."""
        metadata = FileMetadata(
            source_id="file123",
            name="doc.pdf",
            mime_type="application/pdf",
        )

        assert metadata.size is None
        assert metadata.content_hash is None
        assert metadata.modified_at is None
        assert metadata.web_url is None
        assert metadata.parent_id is None

    def test_extra_metadata(self) -> None:
        """Test extra metadata field."""
        metadata = FileMetadata(
            source_id="file123",
            name="doc.pdf",
            mime_type="application/pdf",
            extra={"drive_id": "drive123"},
        )

        assert metadata.extra["drive_id"] == "drive123"

    def test_all_fields(self) -> None:
        """Test creating metadata with all fields."""
        now = datetime.now(timezone.utc)
        metadata = FileMetadata(
            source_id="file123",
            name="document.pdf",
            mime_type="application/pdf",
            size=1024,
            content_hash="abc123",
            modified_at=now,
            created_at=now,
            web_url="https://example.com/file",
            parent_id="folder456",
        )

        assert metadata.size == 1024
        assert metadata.content_hash == "abc123"
        assert metadata.modified_at == now


class TestFileChange:
    """Tests for FileChange dataclass."""

    def test_create_action(self) -> None:
        """Test create action change."""
        file = FileMetadata(
            source_id="file123",
            name="new.pdf",
            mime_type="application/pdf",
        )
        change = FileChange(
            source_id="file123",
            action="create",
            file=file,
        )

        assert change.action == "create"
        assert change.file == file

    def test_update_action(self) -> None:
        """Test update action change."""
        file = FileMetadata(
            source_id="file123",
            name="updated.pdf",
            mime_type="application/pdf",
        )
        change = FileChange(
            source_id="file123",
            action="update",
            file=file,
        )

        assert change.action == "update"

    def test_delete_action(self) -> None:
        """Test delete action change."""
        change = FileChange(
            source_id="file123",
            action="delete",
            file=None,
        )

        assert change.action == "delete"
        assert change.file is None


class TestDownloadedFile:
    """Tests for DownloadedFile dataclass."""

    def test_required_fields(self) -> None:
        """Test creating downloaded file with required fields."""
        access = ExternalAccess.empty()
        downloaded = DownloadedFile(
            source_id="file123",
            name="document.pdf",
            content=b"PDF content",
            mime_type="application/pdf",
            content_hash="abc123",
            modified_at=None,
            external_access=access,
        )

        assert downloaded.source_id == "file123"
        assert downloaded.content == b"PDF content"
        assert downloaded.external_access == access

    def test_optional_fields(self) -> None:
        """Test optional fields."""
        access = ExternalAccess.empty()
        downloaded = DownloadedFile(
            source_id="file123",
            name="doc.pdf",
            content=b"content",
            mime_type="application/pdf",
            content_hash=None,
            modified_at=None,
            external_access=access,
            parent_id="folder456",
            original_url="https://drive.google.com/file",
        )

        assert downloaded.parent_id == "folder456"
        assert downloaded.original_url == "https://drive.google.com/file"


class TestDeletedFile:
    """Tests for DeletedFile dataclass."""

    def test_stores_source_id(self) -> None:
        """Test deleted file stores source ID."""
        deleted = DeletedFile(source_id="file123")

        assert deleted.source_id == "file123"
