"""Unit tests for mcp_gateway.middleware.error_handler."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import mcp.types as mt
import pytest
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools.tool import ToolResult

from mcp_gateway.middleware.error_handler import ErrorHandlingMiddleware
from mcp_gateway.skills.exceptions import (
    SkillExecutionError,
    SkillNotFoundError,
    SkillTimeoutError,
)


def _make_context(tool_name: str = "test_tool") -> MiddlewareContext[mt.CallToolRequestParams]:
    """Create a mock MiddlewareContext for testing.

    Args:
        tool_name: Name of the tool being called.

    Returns:
        Mock MiddlewareContext with the tool name set.
    """
    ctx = MagicMock(spec=MiddlewareContext)
    ctx.message = MagicMock()
    ctx.message.name = tool_name
    return ctx


@pytest.fixture
def middleware() -> ErrorHandlingMiddleware:
    """Create an ErrorHandlingMiddleware instance."""
    return ErrorHandlingMiddleware()


class TestErrorHandlingMiddleware:
    """Tests for ErrorHandlingMiddleware.on_call_tool."""

    @pytest.mark.asyncio
    async def test_success_passes_through(self, middleware: ErrorHandlingMiddleware) -> None:
        """Verify successful tool calls pass through unchanged."""
        expected = ToolResult(content=[mt.TextContent(type="text", text="ok")])
        call_next = AsyncMock(return_value=expected)
        ctx = _make_context()

        result = await middleware.on_call_tool(ctx, call_next)

        call_next.assert_called_once_with(ctx)
        assert result is expected

    @pytest.mark.asyncio
    async def test_skill_not_found_returns_error(self, middleware: ErrorHandlingMiddleware) -> None:
        """Verify SkillNotFoundError is caught and returns friendly message."""
        call_next = AsyncMock(side_effect=SkillNotFoundError("weather-forecast"))
        ctx = _make_context("skills_execute")

        result = await middleware.on_call_tool(ctx, call_next)

        assert len(result.content) == 1
        text = result.content[0].text
        assert "Skill not found" in text
        assert "weather-forecast" in text

    @pytest.mark.asyncio
    async def test_skill_timeout_returns_error(self, middleware: ErrorHandlingMiddleware) -> None:
        """Verify SkillTimeoutError is caught and returns timeout message."""
        call_next = AsyncMock(side_effect=SkillTimeoutError("slow-skill timed out after 30s"))
        ctx = _make_context("skills_execute")

        result = await middleware.on_call_tool(ctx, call_next)

        assert len(result.content) == 1
        text = result.content[0].text
        assert "timed out" in text
        assert "slow-skill" in text

    @pytest.mark.asyncio
    async def test_skill_execution_error_returns_error(self, middleware: ErrorHandlingMiddleware) -> None:
        """Verify SkillExecutionError is caught and returns failure message."""
        call_next = AsyncMock(side_effect=SkillExecutionError("exit code 127"))
        ctx = _make_context("skills_execute")

        result = await middleware.on_call_tool(ctx, call_next)

        assert len(result.content) == 1
        text = result.content[0].text
        assert "execution failed" in text
        assert "exit code 127" in text

    @pytest.mark.asyncio
    async def test_generic_exception_returns_safe_message(self, middleware: ErrorHandlingMiddleware) -> None:
        """Verify unknown exceptions return generic message without leaking internals."""
        call_next = AsyncMock(side_effect=RuntimeError("connection refused to internal-db:5432"))
        ctx = _make_context("search_documents")

        result = await middleware.on_call_tool(ctx, call_next)

        assert len(result.content) == 1
        text = result.content[0].text
        assert "internal error" in text.lower()
        # Must NOT leak the internal error details
        assert "connection refused" not in text
        assert "internal-db" not in text

    @pytest.mark.asyncio
    async def test_does_not_catch_keyboard_interrupt(self, middleware: ErrorHandlingMiddleware) -> None:
        """Verify KeyboardInterrupt is not caught by the middleware."""
        call_next = AsyncMock(side_effect=KeyboardInterrupt())
        ctx = _make_context()

        with pytest.raises(KeyboardInterrupt):
            await middleware.on_call_tool(ctx, call_next)
