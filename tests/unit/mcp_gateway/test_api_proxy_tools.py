"""Unit tests for mcp_gateway.tools.api_proxy."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_gateway.backends.api_proxy_backend import ApiProxyBackend
from mcp_gateway.tools.api_proxy import register_api_proxy_tools


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
def mock_backend() -> MagicMock:
    """Create a mock ApiProxyBackend."""
    return MagicMock(spec=ApiProxyBackend)


@pytest.fixture
def tool_functions(mock_backend: MagicMock) -> dict[str, Any]:
    """Register API proxy tools and capture the inner tool functions."""
    fake_mcp = FakeMCP()
    register_api_proxy_tools(fake_mcp, mock_backend)  # type: ignore[arg-type]
    return fake_mcp.tools


class TestRegisterApiProxyTools:
    """Tests for tool registration."""

    def test_registers_web_search_tool(self, tool_functions: dict[str, Any]) -> None:
        """Verify web_search tool is registered."""
        assert "web_search" in tool_functions


class TestWebSearchTool:
    """Tests for the web_search tool adapter."""

    @pytest.mark.asyncio
    async def test_delegates_to_backend(self, mock_backend: MagicMock) -> None:
        """web_search tool delegates to ApiProxyBackend.web_search."""
        expected = [{"title": "Result", "link": "https://example.com", "snippet": "A snippet"}]
        mock_backend.web_search = AsyncMock(return_value=expected)

        fake_mcp = FakeMCP()
        register_api_proxy_tools(fake_mcp, mock_backend)  # type: ignore[arg-type]

        result = await fake_mcp.tools["web_search"](query="test query", max_results=3)

        assert result == expected
        mock_backend.web_search.assert_awaited_once_with("test query", 3)

    @pytest.mark.asyncio
    async def test_passes_default_max_results(self, mock_backend: MagicMock) -> None:
        """web_search tool passes default max_results to backend."""
        mock_backend.web_search = AsyncMock(return_value=[])

        fake_mcp = FakeMCP()
        register_api_proxy_tools(fake_mcp, mock_backend)  # type: ignore[arg-type]

        await fake_mcp.tools["web_search"](query="test")

        mock_backend.web_search.assert_awaited_once_with("test", 5)
