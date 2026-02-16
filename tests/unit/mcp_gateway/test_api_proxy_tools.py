"""Unit tests for mcp_gateway.tools.api_proxy."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_gateway.backends.api_key_manager import ApiKeyManager
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
def mock_api_key_manager() -> MagicMock:
    """Create a mock ApiKeyManager with Google Search keys."""
    mgr = MagicMock(spec=ApiKeyManager)
    mgr.has_key.return_value = True
    mgr.get_key.side_effect = lambda s: {
        "google_search_api_key": "test-api-key",
        "google_search_cx": "test-cx",
    }.get(s, "")
    return mgr


@pytest.fixture
def tool_functions(mock_api_key_manager: MagicMock) -> dict[str, Any]:
    """Register API proxy tools and capture the inner tool functions."""
    fake_mcp = FakeMCP()
    register_api_proxy_tools(fake_mcp, mock_api_key_manager)  # type: ignore[arg-type]
    return fake_mcp.tools


class TestRegisterApiProxyTools:
    """Tests for tool registration."""

    def test_registers_four_tools(self, tool_functions: dict[str, Any]) -> None:
        """Verify all four API proxy tools are registered."""
        assert set(tool_functions.keys()) == {
            "web_search",
            "send_email",
            "calendar_create_event",
            "calendar_list_events",
        }


class TestWebSearch:
    """Tests for the web_search tool."""

    @pytest.mark.asyncio
    async def test_returns_error_when_api_key_missing(self) -> None:
        """Returns error dict when Google API key is not configured."""
        mgr = MagicMock(spec=ApiKeyManager)
        mgr.has_key.return_value = False
        fake_mcp = FakeMCP()
        register_api_proxy_tools(fake_mcp, mgr)  # type: ignore[arg-type]

        result = await fake_mcp.tools["web_search"](query="test", max_results=5)

        assert len(result) == 1
        assert "error" in result[0]

    @pytest.mark.asyncio
    async def test_returns_error_when_cx_missing(self) -> None:
        """Returns error dict when Google CX is not configured."""
        mgr = MagicMock(spec=ApiKeyManager)
        mgr.has_key.side_effect = lambda k: k == "google_search_api_key"
        fake_mcp = FakeMCP()
        register_api_proxy_tools(fake_mcp, mgr)  # type: ignore[arg-type]

        result = await fake_mcp.tools["web_search"](query="test")

        assert len(result) == 1
        assert "error" in result[0]

    @pytest.mark.asyncio
    async def test_successful_search(
        self, tool_functions: dict[str, Any]
    ) -> None:
        """Successful Google search returns formatted results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "title": "Result 1",
                    "link": "https://example.com",
                    "snippet": "A snippet",
                },
            ]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "mcp_gateway.tools.api_proxy.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await tool_functions["web_search"](
                query="test query", max_results=5
            )

        assert len(result) == 1
        assert result[0]["title"] == "Result 1"
        assert result[0]["link"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_results(
        self, tool_functions: dict[str, Any]
    ) -> None:
        """Returns empty list when Google returns no items."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "mcp_gateway.tools.api_proxy.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await tool_functions["web_search"](query="noresults")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_error_on_http_error(
        self, tool_functions: dict[str, Any]
    ) -> None:
        """Returns error when Google API returns non-200."""
        mock_response = MagicMock()
        mock_response.status_code = 429

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch(
            "mcp_gateway.tools.api_proxy.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await tool_functions["web_search"](query="test")

        assert len(result) == 1
        assert "error" in result[0]


class TestStubTools:
    """Tests for stub tools (email, calendar)."""

    @pytest.mark.asyncio
    async def test_send_email_returns_unavailable(
        self, tool_functions: dict[str, Any]
    ) -> None:
        """send_email returns unavailable status."""
        result = await tool_functions["send_email"](
            to="a@b.com", subject="Hi", body="Hello"
        )
        assert result["status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_calendar_create_event_returns_unavailable(
        self, tool_functions: dict[str, Any]
    ) -> None:
        """calendar_create_event returns unavailable status."""
        result = await tool_functions["calendar_create_event"](
            title="Meeting", start="2026-01-01T10:00", end="2026-01-01T11:00"
        )
        assert result["status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_calendar_list_events_returns_unavailable(
        self, tool_functions: dict[str, Any]
    ) -> None:
        """calendar_list_events returns unavailable status."""
        result = await tool_functions["calendar_list_events"](days_ahead=7)
        assert result["status"] == "unavailable"
