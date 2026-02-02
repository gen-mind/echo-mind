"""Unit tests for Google Drive provider."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from connector.logic.checkpoint import DriveRetrievalStage, GoogleDriveCheckpoint
from connector.logic.exceptions import (
    AuthenticationError,
    DownloadError,
    ExportError,
    FileTooLargeError,
    RateLimitError,
)
from connector.logic.providers.google_drive import (
    GOOGLE_EXPORT_MIMES,
    GoogleDriveProvider,
    MAX_EXPORT_SIZE_BYTES,
)


class TestGoogleDriveProvider:
    """Tests for GoogleDriveProvider."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def provider(self, mock_client: AsyncMock) -> GoogleDriveProvider:
        """Create a provider with mock client."""
        return GoogleDriveProvider(http_client=mock_client)

    def test_provider_name(self, provider: GoogleDriveProvider) -> None:
        """Test provider name is google_drive."""
        assert provider.provider_name == "google_drive"

    def test_create_checkpoint(self, provider: GoogleDriveProvider) -> None:
        """Test creating a new checkpoint."""
        checkpoint = provider.create_checkpoint()

        assert isinstance(checkpoint, GoogleDriveCheckpoint)
        assert checkpoint.completion_stage == DriveRetrievalStage.START


class TestGoogleDriveAuthentication:
    """Tests for Google Drive authentication."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def provider(self, mock_client: AsyncMock) -> GoogleDriveProvider:
        """Create a provider with mock client."""
        return GoogleDriveProvider(http_client=mock_client)

    @pytest.mark.asyncio
    async def test_authenticate_with_access_token(
        self, provider: GoogleDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test authentication with access token."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response

        config = {"access_token": "valid_token"}

        await provider.authenticate(config)

        assert provider._access_token == "valid_token"

    @pytest.mark.asyncio
    async def test_authenticate_missing_credentials(
        self, provider: GoogleDriveProvider
    ) -> None:
        """Test authentication fails without credentials."""
        config = {}

        with pytest.raises(AuthenticationError) as exc_info:
            await provider.authenticate(config)

        assert "Missing access_token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authenticate_invalid_token(
        self, provider: GoogleDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test authentication fails with invalid token."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_client.get.return_value = mock_response

        config = {"access_token": "invalid_token"}

        with pytest.raises(AuthenticationError) as exc_info:
            await provider.authenticate(config)

        assert "Token validation failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_check_connection_success(
        self, provider: GoogleDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test connection check success."""
        provider._access_token = "valid_token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response

        result = await provider.check_connection()

        assert result is True

    @pytest.mark.asyncio
    async def test_check_connection_no_token(
        self, provider: GoogleDriveProvider
    ) -> None:
        """Test connection check fails without token."""
        result = await provider.check_connection()

        assert result is False


class TestGoogleDriveDownload:
    """Tests for Google Drive file download."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def provider(self, mock_client: AsyncMock) -> GoogleDriveProvider:
        """Create a provider with mock client and token."""
        p = GoogleDriveProvider(http_client=mock_client, max_file_size=1024)
        p._access_token = "valid_token"
        return p

    @pytest.mark.asyncio
    async def test_download_regular_file(
        self, provider: GoogleDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test downloading a regular file."""
        from connector.logic.providers.base import FileMetadata

        # Mock download response
        download_response = MagicMock()
        download_response.status_code = 200
        download_response.content = b"file content"

        # Mock permissions response
        perm_response = MagicMock()
        perm_response.status_code = 200
        perm_response.json.return_value = {"permissions": []}

        mock_client.get.side_effect = [download_response, perm_response]

        file = FileMetadata(
            source_id="file123",
            name="document.pdf",
            mime_type="application/pdf",
            size=100,
        )

        result = await provider.download_file(file, {})

        assert result.content == b"file content"
        assert result.name == "document.pdf"

    @pytest.mark.asyncio
    async def test_download_file_too_large_check(
        self, provider: GoogleDriveProvider
    ) -> None:
        """Test file size check before download."""
        from connector.logic.providers.base import FileMetadata

        file = FileMetadata(
            source_id="file123",
            name="large.zip",
            mime_type="application/zip",
            size=10000,  # Larger than max_file_size (1024)
        )

        with pytest.raises(FileTooLargeError) as exc_info:
            await provider.download_file(file, {})

        assert exc_info.value.size == 10000
        assert exc_info.value.limit == 1024

    @pytest.mark.asyncio
    async def test_download_rate_limited(
        self, provider: GoogleDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test handling rate limit response."""
        from connector.logic.providers.base import FileMetadata

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.get.return_value = mock_response

        file = FileMetadata(
            source_id="file123",
            name="doc.pdf",
            mime_type="application/pdf",
            size=100,
        )

        with pytest.raises(RateLimitError):
            await provider.download_file(file, {})


class TestGoogleWorkspaceExport:
    """Tests for Google Workspace file export."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def provider(self, mock_client: AsyncMock) -> GoogleDriveProvider:
        """Create a provider with mock client."""
        p = GoogleDriveProvider(http_client=mock_client)
        p._access_token = "valid_token"
        return p

    def test_google_export_mimes_defined(self) -> None:
        """Test Google export MIME types are defined."""
        assert "application/vnd.google-apps.document" in GOOGLE_EXPORT_MIMES
        assert "application/vnd.google-apps.spreadsheet" in GOOGLE_EXPORT_MIMES
        assert "application/vnd.google-apps.presentation" in GOOGLE_EXPORT_MIMES

    def test_all_exports_to_pdf(self) -> None:
        """Test all Workspace types export to PDF."""
        for export_mime in GOOGLE_EXPORT_MIMES.values():
            assert export_mime == "application/pdf"

    @pytest.mark.asyncio
    async def test_export_google_doc(
        self, provider: GoogleDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test exporting Google Doc as PDF."""
        from connector.logic.providers.base import FileMetadata

        # Mock export response
        export_response = MagicMock()
        export_response.status_code = 200
        export_response.content = b"%PDF-1.4 content"

        # Mock permissions response
        perm_response = MagicMock()
        perm_response.status_code = 200
        perm_response.json.return_value = {"permissions": []}

        mock_client.get.side_effect = [export_response, perm_response]

        file = FileMetadata(
            source_id="doc123",
            name="My Document",
            mime_type="application/vnd.google-apps.document",
        )

        result = await provider.download_file(file, {})

        assert result.content == b"%PDF-1.4 content"
        assert result.name == "My Document.pdf"
        assert result.mime_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_export_forbidden_error(
        self, provider: GoogleDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test export forbidden error (file too large)."""
        from connector.logic.providers.base import FileMetadata

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_client.get.return_value = mock_response

        file = FileMetadata(
            source_id="sheet123",
            name="Large Spreadsheet",
            mime_type="application/vnd.google-apps.spreadsheet",
        )

        with pytest.raises(ExportError) as exc_info:
            await provider.download_file(file, {})

        assert "10MB limit" in str(exc_info.value)


class TestGoogleDriveChanges:
    """Tests for Google Drive change detection."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def provider(self, mock_client: AsyncMock) -> GoogleDriveProvider:
        """Create a provider with mock client."""
        p = GoogleDriveProvider(http_client=mock_client)
        p._access_token = "valid_token"
        return p

    @pytest.mark.asyncio
    async def test_get_changes_initial_sync(
        self, provider: GoogleDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test initial sync gets start page token."""
        # Mock start page token response
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {"startPageToken": "token123"}

        # Mock list files response
        list_response = MagicMock()
        list_response.status_code = 200
        list_response.json.return_value = {
            "files": [
                {
                    "id": "file1",
                    "name": "doc.pdf",
                    "mimeType": "application/pdf",
                }
            ]
        }

        mock_client.get.side_effect = [token_response, list_response]

        checkpoint = GoogleDriveCheckpoint()
        changes = [c async for c in provider.get_changes({}, checkpoint)]

        assert len(changes) == 1
        assert changes[0].source_id == "file1"
        assert checkpoint.changes_start_page_token == "token123"

    @pytest.mark.asyncio
    async def test_get_changes_incremental(
        self, provider: GoogleDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test incremental sync uses changes API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "changes": [
                {
                    "fileId": "file1",
                    "file": {
                        "id": "file1",
                        "name": "updated.pdf",
                        "mimeType": "application/pdf",
                    },
                }
            ],
            "newStartPageToken": "newtoken",
        }
        mock_client.get.return_value = mock_response

        checkpoint = GoogleDriveCheckpoint(
            changes_start_page_token="oldtoken"
        )

        changes = [c async for c in provider.get_changes({}, checkpoint)]

        assert len(changes) == 1
        assert changes[0].action == "update"
        assert checkpoint.changes_start_page_token == "newtoken"

    @pytest.mark.asyncio
    async def test_get_changes_deleted_file(
        self, provider: GoogleDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test detecting deleted files."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "changes": [
                {
                    "fileId": "file1",
                    "removed": True,
                }
            ],
            "newStartPageToken": "token",
        }
        mock_client.get.return_value = mock_response

        checkpoint = GoogleDriveCheckpoint(
            changes_start_page_token="token"
        )

        changes = [c async for c in provider.get_changes({}, checkpoint)]

        assert len(changes) == 1
        assert changes[0].action == "delete"
        assert changes[0].file is None


class TestGoogleDrivePermissions:
    """Tests for Google Drive permission fetching."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def provider(self, mock_client: AsyncMock) -> GoogleDriveProvider:
        """Create a provider with mock client."""
        p = GoogleDriveProvider(http_client=mock_client)
        p._access_token = "valid_token"
        return p

    @pytest.mark.asyncio
    async def test_fetch_user_permissions(
        self, provider: GoogleDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test fetching user permissions."""
        from connector.logic.providers.base import FileMetadata

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "permissions": [
                {"type": "user", "emailAddress": "user1@example.com", "role": "reader"},
                {"type": "user", "emailAddress": "user2@example.com", "role": "writer"},
            ]
        }
        mock_client.get.return_value = mock_response

        file = FileMetadata(
            source_id="file123",
            name="doc.pdf",
            mime_type="application/pdf",
        )

        access = await provider.get_file_permissions(file, {})

        assert "user1@example.com" in access.external_user_emails
        assert "user2@example.com" in access.external_user_emails
        assert access.is_public is False

    @pytest.mark.asyncio
    async def test_fetch_public_permissions(
        self, provider: GoogleDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test detecting public permissions."""
        from connector.logic.providers.base import FileMetadata

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "permissions": [
                {"type": "anyone", "role": "reader"},
            ]
        }
        mock_client.get.return_value = mock_response

        file = FileMetadata(
            source_id="file123",
            name="public.pdf",
            mime_type="application/pdf",
        )

        access = await provider.get_file_permissions(file, {})

        assert access.is_public is True

    @pytest.mark.asyncio
    async def test_permissions_error_returns_empty(
        self, provider: GoogleDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test permission fetch error returns empty access."""
        from connector.logic.providers.base import FileMetadata

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_client.get.return_value = mock_response

        file = FileMetadata(
            source_id="file123",
            name="private.pdf",
            mime_type="application/pdf",
        )

        access = await provider.get_file_permissions(file, {})

        assert access.external_user_emails == frozenset()
        assert access.is_public is False


class TestGoogleDriveStreamToStorage:
    """Tests for Google Drive streaming to MinIO storage."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def mock_minio(self) -> AsyncMock:
        """Create a mock MinIO client."""
        minio = AsyncMock()
        minio.upload_file = AsyncMock(return_value="test-etag-123")
        return minio

    @pytest.fixture
    def provider(self, mock_client: AsyncMock) -> GoogleDriveProvider:
        """Create a provider with mock client."""
        p = GoogleDriveProvider(http_client=mock_client)
        p._access_token = "valid_token"
        return p

    @pytest.mark.asyncio
    async def test_stream_regular_file_to_storage(
        self,
        provider: GoogleDriveProvider,
        mock_client: AsyncMock,
        mock_minio: AsyncMock,
    ) -> None:
        """Test streaming a regular file directly to MinIO."""
        from connector.logic.providers.base import FileMetadata

        # Mock streaming response
        async def mock_aiter_bytes(chunk_size=8192):
            yield b"chunk1"
            yield b"chunk2"
            yield b"chunk3"

        mock_stream_response = MagicMock()
        mock_stream_response.status_code = 200
        mock_stream_response.aiter_bytes = mock_aiter_bytes
        mock_stream_response.__aenter__ = AsyncMock(return_value=mock_stream_response)
        mock_stream_response.__aexit__ = AsyncMock(return_value=None)

        mock_client.stream.return_value = mock_stream_response

        file = FileMetadata(
            source_id="file123",
            name="document.pdf",
            mime_type="application/pdf",
            size=1000,
            content_hash="abc123",
        )

        result = await provider.stream_to_storage(
            file=file,
            config={},
            minio_client=mock_minio,
            bucket="test-bucket",
            object_key="test/path/doc.pdf",
        )

        assert result.storage_path == "minio:test-bucket:test/path/doc.pdf"
        assert result.etag == "test-etag-123"
        assert result.size == len(b"chunk1chunk2chunk3")
        assert result.content_hash == "abc123"

        mock_minio.upload_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_workspace_file_exports_to_pdf(
        self,
        provider: GoogleDriveProvider,
        mock_client: AsyncMock,
        mock_minio: AsyncMock,
    ) -> None:
        """Test streaming a Google Workspace file exports to PDF first."""
        from connector.logic.providers.base import FileMetadata

        # Mock export response
        mock_export_response = MagicMock()
        mock_export_response.status_code = 200
        mock_export_response.content = b"%PDF-1.4 test content"
        mock_client.get.return_value = mock_export_response

        file = FileMetadata(
            source_id="doc123",
            name="My Document",
            mime_type="application/vnd.google-apps.document",
        )

        result = await provider.stream_to_storage(
            file=file,
            config={},
            minio_client=mock_minio,
            bucket="test-bucket",
            object_key="test/path/doc.pdf",
        )

        assert result.storage_path == "minio:test-bucket:test/path/doc.pdf"
        assert result.size == len(b"%PDF-1.4 test content")
        # Workspace files don't have content_hash
        assert result.content_hash is None

        # Verify upload was called with PDF content
        mock_minio.upload_file.assert_called_once()
        call_kwargs = mock_minio.upload_file.call_args[1]
        assert call_kwargs["content_type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_stream_handles_rate_limit(
        self,
        provider: GoogleDriveProvider,
        mock_client: AsyncMock,
        mock_minio: AsyncMock,
    ) -> None:
        """Test streaming handles rate limit errors."""
        from connector.logic.providers.base import FileMetadata

        # Mock rate limited response
        mock_stream_response = MagicMock()
        mock_stream_response.status_code = 429
        mock_stream_response.__aenter__ = AsyncMock(return_value=mock_stream_response)
        mock_stream_response.__aexit__ = AsyncMock(return_value=None)

        mock_client.stream.return_value = mock_stream_response

        file = FileMetadata(
            source_id="file123",
            name="document.pdf",
            mime_type="application/pdf",
        )

        with pytest.raises(RateLimitError):
            await provider.stream_to_storage(
                file=file,
                config={},
                minio_client=mock_minio,
                bucket="bucket",
                object_key="path/file.pdf",
            )

    @pytest.mark.asyncio
    async def test_stream_handles_download_error(
        self,
        provider: GoogleDriveProvider,
        mock_client: AsyncMock,
        mock_minio: AsyncMock,
    ) -> None:
        """Test streaming handles download errors."""
        from connector.logic.providers.base import FileMetadata

        # Mock error response
        mock_stream_response = MagicMock()
        mock_stream_response.status_code = 500
        mock_stream_response.__aenter__ = AsyncMock(return_value=mock_stream_response)
        mock_stream_response.__aexit__ = AsyncMock(return_value=None)

        mock_client.stream.return_value = mock_stream_response

        file = FileMetadata(
            source_id="file123",
            name="document.pdf",
            mime_type="application/pdf",
        )

        with pytest.raises(DownloadError):
            await provider.stream_to_storage(
                file=file,
                config={},
                minio_client=mock_minio,
                bucket="bucket",
                object_key="path/file.pdf",
            )
