"""Unit tests for mcp_gateway.backends.search_backend."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_gateway.backends.client_holder import ClientHolder
from mcp_gateway.backends.search_backend import SearchBackend


@pytest.fixture
def mock_qdrant() -> MagicMock:
    """Create a mock QdrantDB instance."""
    qdrant = MagicMock()
    qdrant.search = AsyncMock()
    qdrant.get_collection_info = AsyncMock()
    qdrant._client = MagicMock()
    qdrant._client.get_collections = AsyncMock()
    qdrant._client.scroll = AsyncMock()
    return qdrant


@pytest.fixture
def mock_embedder() -> AsyncMock:
    """Create a mock EmbedderClient instance."""
    embedder = AsyncMock()
    embedder.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    return embedder


@pytest.fixture
def client_holder(mock_qdrant: MagicMock, mock_embedder: AsyncMock) -> ClientHolder:
    """Create a ClientHolder with mocked dependencies."""
    holder = ClientHolder()
    holder.qdrant = mock_qdrant
    holder.embedder = mock_embedder
    return holder


@pytest.fixture
def backend(client_holder: ClientHolder) -> SearchBackend:
    """Create a SearchBackend with mocked dependencies."""
    return SearchBackend(clients=client_holder)


class TestSearchBackendInit:
    """Tests for SearchBackend initialization."""

    def test_stores_qdrant_reference(
        self, mock_qdrant: MagicMock, mock_embedder: AsyncMock
    ) -> None:
        """Verify qdrant client is stored via client holder."""
        holder = ClientHolder()
        holder.qdrant = mock_qdrant
        holder.embedder = mock_embedder
        backend = SearchBackend(clients=holder)
        assert backend._clients.qdrant is mock_qdrant

    def test_stores_embedder_reference(
        self, mock_qdrant: MagicMock, mock_embedder: AsyncMock
    ) -> None:
        """Verify embedder client is stored via client holder."""
        holder = ClientHolder()
        holder.qdrant = mock_qdrant
        holder.embedder = mock_embedder
        backend = SearchBackend(clients=holder)
        assert backend._clients.embedder is mock_embedder

    @pytest.mark.asyncio
    async def test_search_raises_when_not_connected(self) -> None:
        """Raises RuntimeError when qdrant and embedder are None."""
        holder = ClientHolder()
        backend = SearchBackend(clients=holder)
        with pytest.raises(RuntimeError, match="Qdrant and Embedder must be connected"):
            await backend.search_documents(collection_name="col", query="q")


class TestSearchDocuments:
    """Tests for SearchBackend.search_documents."""

    @pytest.mark.asyncio
    async def test_embeds_query_and_searches(
        self, backend: SearchBackend, mock_embedder: AsyncMock, mock_qdrant: MagicMock
    ) -> None:
        """Verify query is embedded then used for search."""
        mock_qdrant.search.return_value = [
            {"id": "1", "score": 0.95, "payload": {"text": "hello"}}
        ]

        results = await backend.search_documents(
            collection_name="test_col", query="test query"
        )

        mock_embedder.embed_query.assert_awaited_once_with("test query")
        mock_qdrant.search.assert_awaited_once_with(
            collection_name="test_col",
            query_vector=[0.1, 0.2, 0.3],
            limit=10,
            score_threshold=None,
        )
        assert len(results) == 1
        assert results[0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_passes_custom_limit(
        self, backend: SearchBackend, mock_qdrant: MagicMock
    ) -> None:
        """Verify custom limit is forwarded to qdrant."""
        mock_qdrant.search.return_value = []

        await backend.search_documents(
            collection_name="col", query="q", limit=5
        )

        call_kwargs = mock_qdrant.search.call_args.kwargs
        assert call_kwargs["limit"] == 5

    @pytest.mark.asyncio
    async def test_passes_score_threshold(
        self, backend: SearchBackend, mock_qdrant: MagicMock
    ) -> None:
        """Verify score_threshold is forwarded to qdrant."""
        mock_qdrant.search.return_value = []

        await backend.search_documents(
            collection_name="col", query="q", score_threshold=0.8
        )

        call_kwargs = mock_qdrant.search.call_args.kwargs
        assert call_kwargs["score_threshold"] == 0.8

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_results(
        self, backend: SearchBackend, mock_qdrant: MagicMock
    ) -> None:
        """Verify empty list returned when no matches."""
        mock_qdrant.search.return_value = []

        results = await backend.search_documents(
            collection_name="col", query="q"
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_propagates_embedder_error(
        self, backend: SearchBackend, mock_embedder: AsyncMock
    ) -> None:
        """Verify embedder errors propagate to caller."""
        mock_embedder.embed_query.side_effect = ConnectionError("unavailable")

        with pytest.raises(ConnectionError, match="unavailable"):
            await backend.search_documents(
                collection_name="col", query="q"
            )


class TestListCollections:
    """Tests for SearchBackend.list_collections."""

    @pytest.mark.asyncio
    async def test_returns_collection_names(
        self, backend: SearchBackend, mock_qdrant: MagicMock
    ) -> None:
        """Verify collections are returned as name dicts."""
        col1 = MagicMock()
        col1.name = "collection_a"
        col2 = MagicMock()
        col2.name = "collection_b"

        collections_response = MagicMock()
        collections_response.collections = [col1, col2]
        mock_qdrant._client.get_collections.return_value = collections_response

        results = await backend.list_collections()

        assert results == [{"name": "collection_a"}, {"name": "collection_b"}]

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_collections(
        self, backend: SearchBackend, mock_qdrant: MagicMock
    ) -> None:
        """Verify empty list when no collections exist."""
        collections_response = MagicMock()
        collections_response.collections = []
        mock_qdrant._client.get_collections.return_value = collections_response

        results = await backend.list_collections()

        assert results == []


class TestGetCollectionInfo:
    """Tests for SearchBackend.get_collection_info."""

    @pytest.mark.asyncio
    async def test_delegates_to_qdrant(
        self, backend: SearchBackend, mock_qdrant: MagicMock
    ) -> None:
        """Verify call is delegated to qdrant client."""
        expected_info = {
            "name": "test_col",
            "vectors_count": 100,
            "points_count": 100,
            "status": "green",
        }
        mock_qdrant.get_collection_info.return_value = expected_info

        result = await backend.get_collection_info("test_col")

        mock_qdrant.get_collection_info.assert_awaited_once_with("test_col")
        assert result == expected_info


class TestGetDocumentChunks:
    """Tests for SearchBackend.get_document_chunks."""

    @pytest.mark.asyncio
    async def test_returns_formatted_chunks(
        self, backend: SearchBackend, mock_qdrant: MagicMock
    ) -> None:
        """Verify chunks are formatted with id and payload."""
        point1 = MagicMock()
        point1.id = "abc-123"
        point1.payload = {"text": "chunk 1", "document_id": "doc1"}
        point2 = MagicMock()
        point2.id = "abc-456"
        point2.payload = {"text": "chunk 2", "document_id": "doc1"}

        mock_qdrant._client.scroll.return_value = ([point1, point2], None)

        results = await backend.get_document_chunks(
            collection_name="col", document_id="doc1"
        )

        assert len(results) == 2
        assert results[0] == {"id": "abc-123", "payload": point1.payload}
        assert results[1] == {"id": "abc-456", "payload": point2.payload}

    @pytest.mark.asyncio
    async def test_uses_document_id_filter(
        self, backend: SearchBackend, mock_qdrant: MagicMock
    ) -> None:
        """Verify scroll uses document_id filter."""
        mock_qdrant._client.scroll.return_value = ([], None)

        await backend.get_document_chunks(
            collection_name="col", document_id="doc42"
        )

        call_kwargs = mock_qdrant._client.scroll.call_args.kwargs
        assert call_kwargs["collection_name"] == "col"
        assert call_kwargs["with_payload"] is True
        assert call_kwargs["with_vectors"] is False

        # Verify the filter contains the document_id condition
        scroll_filter = call_kwargs["scroll_filter"]
        assert len(scroll_filter.must) == 1
        condition = scroll_filter.must[0]
        assert condition.key == "document_id"
        assert condition.match.value == "doc42"

    @pytest.mark.asyncio
    async def test_passes_custom_limit(
        self, backend: SearchBackend, mock_qdrant: MagicMock
    ) -> None:
        """Verify custom limit is passed to scroll."""
        mock_qdrant._client.scroll.return_value = ([], None)

        await backend.get_document_chunks(
            collection_name="col", document_id="doc1", limit=50
        )

        call_kwargs = mock_qdrant._client.scroll.call_args.kwargs
        assert call_kwargs["limit"] == 50

    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_document(
        self, backend: SearchBackend, mock_qdrant: MagicMock
    ) -> None:
        """Verify empty list for non-existent document."""
        mock_qdrant._client.scroll.return_value = ([], None)

        results = await backend.get_document_chunks(
            collection_name="col", document_id="nonexistent"
        )

        assert results == []
