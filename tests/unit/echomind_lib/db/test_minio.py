"""
Unit tests for MinIO client streaming functionality.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from echomind_lib.db.minio import MinIOClient, StreamUploadResult


class TestMinIOClientStreamUpload:
    """Tests for MinIO streaming upload functionality."""

    @pytest.fixture
    def mock_minio(self):
        """Create a mock Minio client."""
        minio = MagicMock()
        minio.put_object = AsyncMock()
        return minio

    @pytest.fixture
    def client(self, mock_minio):
        """Create MinIOClient with mocked underlying client."""
        client = MinIOClient(
            endpoint="localhost:9000",
            access_key="test",
            secret_key="test",
        )
        client._client = mock_minio
        return client

    @pytest.mark.asyncio
    async def test_stream_upload_collects_chunks(self, client, mock_minio):
        """Test that stream_upload collects all chunks before uploading."""
        # Setup mock response
        mock_result = MagicMock()
        mock_result.etag = "test-etag-123"
        mock_minio.put_object.return_value = mock_result

        # Create async generator
        async def gen_chunks():
            yield b"chunk1"
            yield b"chunk2"
            yield b"chunk3"

        result = await client.stream_upload(
            bucket_name="test-bucket",
            object_name="test/path/file.txt",
            data_stream=gen_chunks(),
            content_type="text/plain",
        )

        assert isinstance(result, StreamUploadResult)
        assert result.etag == "test-etag-123"
        assert result.size == len(b"chunk1chunk2chunk3")
        assert result.storage_path == "minio:test-bucket:test/path/file.txt"

        # Verify put_object was called with collected content
        mock_minio.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_upload_with_metadata(self, client, mock_minio):
        """Test that stream_upload passes metadata correctly."""
        mock_result = MagicMock()
        mock_result.etag = "test-etag"
        mock_minio.put_object.return_value = mock_result

        async def gen_chunks():
            yield b"test data"

        metadata = {"custom-key": "custom-value"}

        await client.stream_upload(
            bucket_name="bucket",
            object_name="file.txt",
            data_stream=gen_chunks(),
            metadata=metadata,
        )

        call_kwargs = mock_minio.put_object.call_args[1]
        assert call_kwargs["metadata"] == metadata

    @pytest.mark.asyncio
    async def test_stream_upload_empty_stream(self, client, mock_minio):
        """Test stream_upload with empty stream."""
        mock_result = MagicMock()
        mock_result.etag = "empty-etag"
        mock_minio.put_object.return_value = mock_result

        async def empty_gen():
            return
            yield  # Make it an async generator

        result = await client.stream_upload(
            bucket_name="bucket",
            object_name="empty.txt",
            data_stream=empty_gen(),
        )

        assert result.size == 0


class TestMinIOClientPresignedPutUrl:
    """Tests for pre-signed PUT URL generation."""

    @pytest.fixture
    def mock_minio(self):
        """Create a mock Minio client."""
        minio = MagicMock()
        minio.presigned_put_object = AsyncMock(
            return_value="https://minio.example.com/bucket/file?signature=abc"
        )
        return minio

    @pytest.fixture
    def client(self, mock_minio):
        """Create MinIOClient with mocked underlying client."""
        client = MinIOClient(
            endpoint="localhost:9000",
            access_key="test",
            secret_key="test",
        )
        client._client = mock_minio
        return client

    @pytest.mark.asyncio
    async def test_presigned_put_url_returns_url(self, client, mock_minio):
        """Test that presigned_put_url returns a valid URL."""
        result = await client.presigned_put_url(
            bucket_name="bucket",
            object_name="file.txt",
            expires=3600,
        )

        assert "https://" in result
        mock_minio.presigned_put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_presigned_put_url_custom_expiry(self, client, mock_minio):
        """Test that custom expiry is passed correctly."""
        await client.presigned_put_url(
            bucket_name="bucket",
            object_name="file.txt",
            expires=7200,
        )

        call_kwargs = mock_minio.presigned_put_object.call_args[1]
        # Check timedelta was passed
        assert "expires" in call_kwargs
