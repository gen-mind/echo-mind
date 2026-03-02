"""Unit tests for mcp_gateway.tools.search."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_gateway.tools.search import register_search_tools


@pytest.fixture
def mock_backend() -> AsyncMock:
    """Create a mock SearchBackend."""
    backend = AsyncMock()
    backend.search_documents = AsyncMock(return_value=[])
    backend.list_collections = AsyncMock(return_value=[])
    backend.get_collection_info = AsyncMock(return_value={})
    backend.get_document_chunks = AsyncMock(return_value=[])
    return backend


@pytest.fixture
def tool_functions(mock_backend: AsyncMock) -> dict[str, Any]:
    """
    Register search tools and capture the inner tool functions.

    Returns a dict mapping tool name to the async callable.
    """
    captured: dict[str, Any] = {}

    class FakeMCP:
        """Fake FastMCP that captures tool registrations."""

        def tool(self) -> Any:
            """Return decorator that captures the function."""
            def decorator(fn: Any) -> Any:
                captured[fn.__name__] = fn
                return fn
            return decorator

    fake_mcp = FakeMCP()
    register_search_tools(fake_mcp, mock_backend)  # type: ignore[arg-type]
    return captured


class TestRegisterSearchTools:
    """Tests for register_search_tools registration."""

    def test_registers_four_tools(self, tool_functions: dict[str, Any]) -> None:
        """Verify all four search tools are registered."""
        assert "search_documents" in tool_functions
        assert "list_collections" in tool_functions
        assert "get_collection_info" in tool_functions
        assert "get_document_chunks" in tool_functions

    def test_registers_exactly_four(self, tool_functions: dict[str, Any]) -> None:
        """Verify no extra tools are registered."""
        assert len(tool_functions) == 4


class TestSearchDocumentsTool:
    """Tests for the search_documents tool function."""

    @pytest.mark.asyncio
    async def test_delegates_to_backend(
        self, tool_functions: dict[str, Any], mock_backend: AsyncMock
    ) -> None:
        """Verify tool delegates to backend.search_documents."""
        mock_backend.search_documents.return_value = [
            {"id": "1", "score": 0.9, "payload": {"text": "result"}}
        ]

        result = await tool_functions["search_documents"](
            collection="test_col", query="hello world"
        )

        mock_backend.search_documents.assert_awaited_once_with(
            collection_name="test_col",
            query="hello world",
            limit=10,
            score_threshold=None,
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_passes_custom_parameters(
        self, tool_functions: dict[str, Any], mock_backend: AsyncMock
    ) -> None:
        """Verify custom limit and score_threshold are forwarded."""
        mock_backend.search_documents.return_value = []

        await tool_functions["search_documents"](
            collection="col", query="q", limit=5, score_threshold=0.7
        )

        mock_backend.search_documents.assert_awaited_once_with(
            collection_name="col",
            query="q",
            limit=5,
            score_threshold=0.7,
        )

    @pytest.mark.asyncio
    async def test_returns_backend_results(
        self, tool_functions: dict[str, Any], mock_backend: AsyncMock
    ) -> None:
        """Verify tool returns exactly what backend returns."""
        expected = [{"id": "a", "score": 0.95, "payload": {}}]
        mock_backend.search_documents.return_value = expected

        result = await tool_functions["search_documents"](
            collection="col", query="q"
        )

        assert result is expected


class TestListCollectionsTool:
    """Tests for the list_collections tool function."""

    @pytest.mark.asyncio
    async def test_delegates_to_backend(
        self, tool_functions: dict[str, Any], mock_backend: AsyncMock
    ) -> None:
        """Verify tool delegates to backend.list_collections."""
        mock_backend.list_collections.return_value = [{"name": "col1"}]

        result = await tool_functions["list_collections"]()

        mock_backend.list_collections.assert_awaited_once()
        assert result == [{"name": "col1"}]


class TestGetCollectionInfoTool:
    """Tests for the get_collection_info tool function."""

    @pytest.mark.asyncio
    async def test_delegates_to_backend(
        self, tool_functions: dict[str, Any], mock_backend: AsyncMock
    ) -> None:
        """Verify tool delegates to backend.get_collection_info."""
        expected = {"name": "col", "vectors_count": 42}
        mock_backend.get_collection_info.return_value = expected

        result = await tool_functions["get_collection_info"](collection="col")

        mock_backend.get_collection_info.assert_awaited_once_with("col")
        assert result == expected


class TestGetDocumentChunksTool:
    """Tests for the get_document_chunks tool function."""

    @pytest.mark.asyncio
    async def test_delegates_to_backend(
        self, tool_functions: dict[str, Any], mock_backend: AsyncMock
    ) -> None:
        """Verify tool delegates to backend.get_document_chunks."""
        expected = [{"id": "1", "payload": {"text": "chunk"}}]
        mock_backend.get_document_chunks.return_value = expected

        result = await tool_functions["get_document_chunks"](
            collection="col", document_id="doc1"
        )

        mock_backend.get_document_chunks.assert_awaited_once_with(
            collection_name="col",
            document_id="doc1",
            limit=100,
        )
        assert result == expected

    @pytest.mark.asyncio
    async def test_passes_custom_limit(
        self, tool_functions: dict[str, Any], mock_backend: AsyncMock
    ) -> None:
        """Verify custom limit is forwarded."""
        mock_backend.get_document_chunks.return_value = []

        await tool_functions["get_document_chunks"](
            collection="col", document_id="doc1", limit=25
        )

        mock_backend.get_document_chunks.assert_awaited_once_with(
            collection_name="col",
            document_id="doc1",
            limit=25,
        )


def _make_tool_functions(
    backend: AsyncMock,
    readiness_check: Any = None,
) -> dict[str, Any]:
    """Helper to register tools and capture the inner functions.

    Args:
        backend: Mock SearchBackend.
        readiness_check: Optional readiness callback.

    Returns:
        Dict mapping tool name to the async callable.
    """
    captured: dict[str, Any] = {}

    class FakeMCP:
        """Fake FastMCP that captures tool registrations."""

        def tool(self) -> Any:
            """Return decorator that captures the function."""
            def decorator(fn: Any) -> Any:
                captured[fn.__name__] = fn
                return fn
            return decorator

    register_search_tools(FakeMCP(), backend, readiness_check=readiness_check)  # type: ignore[arg-type]
    return captured


class TestSearchDocumentsValidation:
    """Tests for input validation in search_documents."""

    @pytest.mark.asyncio
    async def test_empty_query_raises_value_error(self, mock_backend: AsyncMock) -> None:
        """Empty query raises ValueError."""
        tools = _make_tool_functions(mock_backend)
        with pytest.raises(ValueError, match="(?i)empty"):
            await tools["search_documents"](collection="col", query="   ")

    @pytest.mark.asyncio
    async def test_limit_clamped_to_range(self, mock_backend: AsyncMock) -> None:
        """Limit is clamped to 1-1000 range."""
        tools = _make_tool_functions(mock_backend)
        mock_backend.search_documents.return_value = []
        # Over-limit
        await tools["search_documents"](collection="col", query="test", limit=5000)
        assert mock_backend.search_documents.call_args.kwargs["limit"] == 1000
        # Under-limit
        mock_backend.search_documents.reset_mock()
        mock_backend.search_documents.return_value = []
        await tools["search_documents"](collection="col", query="test", limit=-1)
        assert mock_backend.search_documents.call_args.kwargs["limit"] == 1

    @pytest.mark.asyncio
    async def test_invalid_score_threshold_raises_value_error(self, mock_backend: AsyncMock) -> None:
        """Invalid score_threshold raises ValueError."""
        tools = _make_tool_functions(mock_backend)
        with pytest.raises(ValueError, match="score_threshold"):
            await tools["search_documents"](collection="col", query="test", score_threshold=1.5)


class TestSearchToolsReadiness:
    """Tests for readiness check in search tools."""

    @pytest.mark.asyncio
    async def test_search_documents_not_ready(self, mock_backend: AsyncMock) -> None:
        """search_documents raises RuntimeError when not ready."""
        tools = _make_tool_functions(mock_backend, readiness_check=lambda: False)
        with pytest.raises(RuntimeError, match="(?i)not ready"):
            await tools["search_documents"](collection="col", query="test")

    @pytest.mark.asyncio
    async def test_list_collections_not_ready(self, mock_backend: AsyncMock) -> None:
        """list_collections raises RuntimeError when not ready."""
        tools = _make_tool_functions(mock_backend, readiness_check=lambda: False)
        with pytest.raises(RuntimeError, match="(?i)not ready"):
            await tools["list_collections"]()

    @pytest.mark.asyncio
    async def test_get_collection_info_not_ready(self, mock_backend: AsyncMock) -> None:
        """get_collection_info raises RuntimeError when not ready."""
        tools = _make_tool_functions(mock_backend, readiness_check=lambda: False)
        with pytest.raises(RuntimeError, match="(?i)not ready"):
            await tools["get_collection_info"](collection="col")

    @pytest.mark.asyncio
    async def test_get_document_chunks_not_ready(self, mock_backend: AsyncMock) -> None:
        """get_document_chunks raises RuntimeError when not ready."""
        tools = _make_tool_functions(mock_backend, readiness_check=lambda: False)
        with pytest.raises(RuntimeError, match="(?i)not ready"):
            await tools["get_document_chunks"](collection="col", document_id="doc1")
