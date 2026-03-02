"""Unit tests for mcp_gateway.tools.connectors."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_gateway.backends.connector_backend import ConnectorBackend
from mcp_gateway.tools.connectors import register_connector_tools


class FakeMCP:
    """Fake FastMCP that captures tool registrations."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self) -> Any:
        """Return decorator that captures the function."""

        def decorator(fn: Any) -> Any:
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.fixture
def mock_connector_backend() -> MagicMock:
    """Create a mock ConnectorBackend."""
    backend = MagicMock(spec=ConnectorBackend)
    backend.list_connectors = AsyncMock(return_value=[])
    backend.get_connector_status = AsyncMock(return_value=None)
    backend.search_connector_documents = AsyncMock(return_value=[])
    backend.trigger_sync = AsyncMock(return_value={})
    return backend



@pytest.fixture
def tool_functions(
    mock_connector_backend: MagicMock,
) -> dict[str, Any]:
    """Register connector tools and capture the inner tool functions."""
    fake_mcp = FakeMCP()
    register_connector_tools(
        fake_mcp, mock_connector_backend,  # type: ignore[arg-type]
    )
    return fake_mcp.tools


class TestRegisterConnectorTools:
    """Tests for tool registration."""

    def test_registers_four_tools(self, tool_functions: dict[str, Any]) -> None:
        """Verify all four connector tools are registered."""
        assert set(tool_functions.keys()) == {
            "connectors_list",
            "connector_status",
            "connector_search",
            "connector_sync",
        }


class TestConnectorsList:
    """Tests for the connectors_list tool."""

    @pytest.mark.asyncio
    async def test_delegates_to_backend(
        self,
        tool_functions: dict[str, Any],
        mock_connector_backend: MagicMock,
    ) -> None:
        """connectors_list delegates to ConnectorBackend."""
        mock_connector_backend.list_connectors.return_value = [
            {"id": 1, "name": "C1"}
        ]

        result = await tool_functions["connectors_list"](user_id=42)

        mock_connector_backend.list_connectors.assert_awaited_once_with(42)
        assert len(result) == 1
        assert result[0]["name"] == "C1"


class TestConnectorStatus:
    """Tests for the connector_status tool."""

    @pytest.mark.asyncio
    async def test_returns_status(
        self,
        tool_functions: dict[str, Any],
        mock_connector_backend: MagicMock,
    ) -> None:
        """connector_status returns backend result."""
        mock_connector_backend.get_connector_status.return_value = {
            "id": 1, "status": "active"
        }

        result = await tool_functions["connector_status"](connector_id=1)

        assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_returns_error_when_not_found(
        self,
        tool_functions: dict[str, Any],
        mock_connector_backend: MagicMock,
    ) -> None:
        """connector_status returns error dict when not found."""
        mock_connector_backend.get_connector_status.return_value = None

        result = await tool_functions["connector_status"](connector_id=999)

        assert "error" in result


class TestConnectorSearch:
    """Tests for the connector_search tool."""

    @pytest.mark.asyncio
    async def test_delegates_to_backend(
        self,
        tool_functions: dict[str, Any],
        mock_connector_backend: MagicMock,
    ) -> None:
        """connector_search delegates to ConnectorBackend."""
        mock_connector_backend.search_connector_documents.return_value = [
            {"id": "1", "score": 0.9}
        ]

        result = await tool_functions["connector_search"](
            connector_id=1, query="test", collection="col"
        )

        mock_connector_backend.search_connector_documents.assert_awaited_once()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_returns_error_on_runtime_error(
        self,
        tool_functions: dict[str, Any],
        mock_connector_backend: MagicMock,
    ) -> None:
        """connector_search returns error dict on RuntimeError."""
        mock_connector_backend.search_connector_documents.side_effect = (
            RuntimeError("not configured")
        )

        result = await tool_functions["connector_search"](
            connector_id=1, query="test", collection="col"
        )

        assert result[0]["error"] == "not configured"


class TestConnectorSync:
    """Tests for the connector_sync tool."""

    @pytest.mark.asyncio
    async def test_delegates_to_backend(
        self,
        tool_functions: dict[str, Any],
        mock_connector_backend: MagicMock,
    ) -> None:
        """connector_sync delegates to ConnectorBackend."""
        mock_connector_backend.trigger_sync.return_value = {
            "connector_id": 1, "status": "sync_requested"
        }

        result = await tool_functions["connector_sync"](
            connector_id=1, user_id=1
        )

        assert result["status"] == "sync_requested"

    @pytest.mark.asyncio
    async def test_returns_error_on_value_error(
        self,
        tool_functions: dict[str, Any],
        mock_connector_backend: MagicMock,
    ) -> None:
        """connector_sync returns error dict on ValueError."""
        mock_connector_backend.trigger_sync.side_effect = ValueError(
            "User does not own connector"
        )

        result = await tool_functions["connector_sync"](
            connector_id=1, user_id=99
        )

        assert "error" in result
