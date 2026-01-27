"""Unit tests for OneDrive provider."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from connector.logic.checkpoint import SharePointCheckpoint
from connector.logic.exceptions import (
    AuthenticationError,
    DownloadError,
    FileTooLargeError,
    RateLimitError,
)
from connector.logic.providers.onedrive import OneDriveProvider


class TestOneDriveProvider:
    """Tests for OneDriveProvider."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def provider(self, mock_client: AsyncMock) -> OneDriveProvider:
        """Create a provider with mock client."""
        return OneDriveProvider(http_client=mock_client)

    def test_provider_name(self, provider: OneDriveProvider) -> None:
        """Test provider name is onedrive."""
        assert provider.provider_name == "onedrive"

    def test_create_checkpoint(self, provider: OneDriveProvider) -> None:
        """Test creating a new checkpoint."""
        checkpoint = provider.create_checkpoint()

        assert isinstance(checkpoint, SharePointCheckpoint)
        assert checkpoint.delta_link is None


class TestOneDriveAuthentication:
    """Tests for OneDrive authentication."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def provider(self, mock_client: AsyncMock) -> OneDriveProvider:
        """Create a provider with mock client."""
        return OneDriveProvider(http_client=mock_client)

    @pytest.mark.asyncio
    async def test_authenticate_with_access_token(
        self, provider: OneDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test authentication with access token."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response

        config = {"access_token": "valid_token"}

        await provider.authenticate(config)

        assert provider._access_token == "valid_token"

    @pytest.mark.asyncio
    async def test_authenticate_with_app_credentials(
        self, provider: OneDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test authentication with app credentials."""
        # Mock token response
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "app_token",
            "expires_in": 3600,
        }
        mock_client.post.return_value = token_response

        # Mock connection check
        check_response = MagicMock()
        check_response.status_code = 200
        mock_client.get.return_value = check_response

        config = {
            "client_id": "client123",
            "client_secret": "secret456",
            "tenant_id": "tenant789",
        }

        await provider.authenticate(config)

        assert provider._access_token == "app_token"

    @pytest.mark.asyncio
    async def test_authenticate_missing_credentials(
        self, provider: OneDriveProvider
    ) -> None:
        """Test authentication fails without credentials."""
        config = {}

        with pytest.raises(AuthenticationError) as exc_info:
            await provider.authenticate(config)

        assert "Missing access_token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_check_connection_success(
        self, provider: OneDriveProvider, mock_client: AsyncMock
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
        self, provider: OneDriveProvider
    ) -> None:
        """Test connection check fails without token."""
        result = await provider.check_connection()

        assert result is False


class TestOneDriveDownload:
    """Tests for OneDrive file download."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def provider(self, mock_client: AsyncMock) -> OneDriveProvider:
        """Create a provider with mock client and token."""
        p = OneDriveProvider(http_client=mock_client, max_file_size=1024)
        p._access_token = "valid_token"
        return p

    @pytest.mark.asyncio
    async def test_download_file_success(
        self, provider: OneDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test downloading a file."""
        from connector.logic.providers.base import FileMetadata

        # Mock download response
        download_response = MagicMock()
        download_response.status_code = 200
        download_response.content = b"file content"

        # Mock permissions response
        perm_response = MagicMock()
        perm_response.status_code = 200
        perm_response.json.return_value = {"value": []}

        mock_client.get.side_effect = [download_response, perm_response]

        file = FileMetadata(
            source_id="item123",
            name="document.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size=100,
            content_hash="ctag123",
            extra={"drive_id": "drive123"},
        )

        result = await provider.download_file(file, {})

        assert result.content == b"file content"
        assert result.name == "document.docx"
        assert result.content_hash == "ctag123"

    @pytest.mark.asyncio
    async def test_download_file_too_large_check(
        self, provider: OneDriveProvider
    ) -> None:
        """Test file size check before download."""
        from connector.logic.providers.base import FileMetadata

        file = FileMetadata(
            source_id="item123",
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
        self, provider: OneDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test handling rate limit response."""
        from connector.logic.providers.base import FileMetadata

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}
        mock_client.get.return_value = mock_response

        file = FileMetadata(
            source_id="item123",
            name="doc.pdf",
            mime_type="application/pdf",
            size=100,
        )

        with pytest.raises(RateLimitError) as exc_info:
            await provider.download_file(file, {})

        assert exc_info.value.retry_after == 60


class TestOneDriveChanges:
    """Tests for OneDrive change detection."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def provider(self, mock_client: AsyncMock) -> OneDriveProvider:
        """Create a provider with mock client."""
        p = OneDriveProvider(http_client=mock_client)
        p._access_token = "valid_token"
        return p

    @pytest.mark.asyncio
    async def test_get_changes_initial_sync(
        self, provider: OneDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test initial sync uses delta endpoint."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {
                    "id": "item1",
                    "name": "doc.pdf",
                    "file": {"mimeType": "application/pdf"},
                    "cTag": "ctag123",
                }
            ],
            "@odata.deltaLink": "https://graph.microsoft.com/delta?token=abc",
        }
        mock_client.get.return_value = mock_response

        checkpoint = SharePointCheckpoint()
        changes = [c async for c in provider.get_changes({}, checkpoint)]

        assert len(changes) == 1
        assert changes[0].source_id == "item1"
        assert checkpoint.delta_link == "https://graph.microsoft.com/delta?token=abc"

    @pytest.mark.asyncio
    async def test_get_changes_incremental(
        self, provider: OneDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test incremental sync uses delta link."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {
                    "id": "item1",
                    "name": "updated.pdf",
                    "file": {"mimeType": "application/pdf"},
                    "cTag": "ctag456",
                }
            ],
            "@odata.deltaLink": "https://graph.microsoft.com/delta?token=new",
        }
        mock_client.get.return_value = mock_response

        checkpoint = SharePointCheckpoint(
            delta_link="https://graph.microsoft.com/delta?token=old"
        )

        changes = [c async for c in provider.get_changes({}, checkpoint)]

        assert len(changes) == 1
        assert changes[0].action == "update"
        assert checkpoint.delta_link == "https://graph.microsoft.com/delta?token=new"

    @pytest.mark.asyncio
    async def test_get_changes_deleted_item(
        self, provider: OneDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test detecting deleted items."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {
                    "id": "item1",
                    "deleted": {"state": "deleted"},
                }
            ],
            "@odata.deltaLink": "https://graph.microsoft.com/delta?token=abc",
        }
        mock_client.get.return_value = mock_response

        checkpoint = SharePointCheckpoint()
        changes = [c async for c in provider.get_changes({}, checkpoint)]

        assert len(changes) == 1
        assert changes[0].action == "delete"
        assert changes[0].file is None

    @pytest.mark.asyncio
    async def test_get_changes_skips_folders(
        self, provider: OneDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test folders are skipped."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {
                    "id": "folder1",
                    "name": "Documents",
                    "folder": {"childCount": 5},
                }
            ],
            "@odata.deltaLink": "https://graph.microsoft.com/delta?token=abc",
        }
        mock_client.get.return_value = mock_response

        checkpoint = SharePointCheckpoint()
        changes = [c async for c in provider.get_changes({}, checkpoint)]

        assert len(changes) == 0


class TestOneDrivePermissions:
    """Tests for OneDrive permission fetching."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.fixture
    def provider(self, mock_client: AsyncMock) -> OneDriveProvider:
        """Create a provider with mock client."""
        p = OneDriveProvider(http_client=mock_client)
        p._access_token = "valid_token"
        return p

    @pytest.mark.asyncio
    async def test_fetch_user_permissions(
        self, provider: OneDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test fetching user permissions."""
        from connector.logic.providers.base import FileMetadata

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {
                    "grantedToV2": {
                        "user": {"email": "user1@example.com"}
                    }
                },
                {
                    "grantedTo": {
                        "user": {"email": "user2@example.com"}
                    }
                },
            ]
        }
        mock_client.get.return_value = mock_response

        file = FileMetadata(
            source_id="item123",
            name="doc.pdf",
            mime_type="application/pdf",
            extra={},
        )

        access = await provider.get_file_permissions(file, {})

        assert "user1@example.com" in access.external_user_emails
        assert "user2@example.com" in access.external_user_emails
        assert access.is_public is False

    @pytest.mark.asyncio
    async def test_fetch_group_permissions(
        self, provider: OneDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test fetching group permissions."""
        from connector.logic.providers.base import FileMetadata

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {
                    "grantedToV2": {
                        "group": {"id": "group-123"}
                    }
                },
            ]
        }
        mock_client.get.return_value = mock_response

        file = FileMetadata(
            source_id="item123",
            name="doc.pdf",
            mime_type="application/pdf",
            extra={},
        )

        access = await provider.get_file_permissions(file, {})

        assert "group-123" in access.external_user_group_ids

    @pytest.mark.asyncio
    async def test_fetch_public_permissions(
        self, provider: OneDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test detecting anonymous share links."""
        from connector.logic.providers.base import FileMetadata

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {
                    "link": {"scope": "anonymous"}
                },
            ]
        }
        mock_client.get.return_value = mock_response

        file = FileMetadata(
            source_id="item123",
            name="public.pdf",
            mime_type="application/pdf",
            extra={},
        )

        access = await provider.get_file_permissions(file, {})

        assert access.is_public is True

    @pytest.mark.asyncio
    async def test_permissions_error_returns_empty(
        self, provider: OneDriveProvider, mock_client: AsyncMock
    ) -> None:
        """Test permission fetch error returns empty access."""
        from connector.logic.providers.base import FileMetadata

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_client.get.return_value = mock_response

        file = FileMetadata(
            source_id="item123",
            name="private.pdf",
            mime_type="application/pdf",
            extra={},
        )

        access = await provider.get_file_permissions(file, {})

        assert access.external_user_emails == frozenset()
        assert access.is_public is False
