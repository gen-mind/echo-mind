"""
Unit tests for tool middleware.

Tests cover PathRestrictionMiddleware with allowed/denied path validation.
All tests use mocked FunctionInvocationContext — no real tool execution.
Target: 100% code coverage
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from agent_framework import FunctionInvocationContext, FunctionTool

from src.agent.tools.middleware import PathRestrictionMiddleware


# ---------------------------------------------------------------------------
# Test argument models
# ---------------------------------------------------------------------------


class PathArgs(BaseModel):
    """Test model with a single path field."""
    path: str = ""


class NoPathArgs(BaseModel):
    """Test model with no path-like fields."""
    pattern: str = ""
    max_results: int = 100


class MultiPathArgs(BaseModel):
    """Test model with source and destination fields."""
    source: str = ""
    destination: str = ""


class OptionalPathArgs(BaseModel):
    """Test model with optional path field."""
    file_path: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(args: BaseModel) -> FunctionInvocationContext:
    """
    Create a FunctionInvocationContext with mocked function.

    Args:
        args: Pydantic model for function arguments.

    Returns:
        FunctionInvocationContext with the given arguments.
    """
    mock_function = MagicMock(spec=FunctionTool)
    mock_function.name = "test_tool"
    return FunctionInvocationContext(
        function=mock_function,
        arguments=args,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPathRestrictionMiddleware:
    """Tests for PathRestrictionMiddleware."""

    @pytest.mark.asyncio
    async def test_no_restrictions_allows_all(self) -> None:
        """Test middleware with no restrictions allows all paths."""
        middleware = PathRestrictionMiddleware()
        context = _make_context(PathArgs(path="/any/path/file.txt"))
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_called_once()
        assert context.result is None

    @pytest.mark.asyncio
    async def test_allowed_path_passes(self) -> None:
        """Test path under allowed directory passes."""
        middleware = PathRestrictionMiddleware(allowed_paths=["/allowed"])
        context = _make_context(PathArgs(path="/allowed/subdir/file.txt"))
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_called_once()
        assert context.result is None

    @pytest.mark.asyncio
    async def test_allowed_path_blocks_outside(self) -> None:
        """Test path outside allowed directory is blocked."""
        middleware = PathRestrictionMiddleware(allowed_paths=["/allowed"])
        context = _make_context(PathArgs(path="/forbidden/file.txt"))
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_not_called()
        assert "❌" in context.result
        assert "not allowed" in context.result

    @pytest.mark.asyncio
    async def test_denied_path_blocks(self) -> None:
        """Test path under denied directory is blocked."""
        middleware = PathRestrictionMiddleware(denied_paths=["/secret"])
        context = _make_context(PathArgs(path="/secret/credentials.json"))
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_not_called()
        assert "❌" in context.result
        assert "not allowed" in context.result

    @pytest.mark.asyncio
    async def test_denied_takes_precedence_over_allowed(self) -> None:
        """Test denied paths take precedence over allowed paths."""
        middleware = PathRestrictionMiddleware(
            allowed_paths=["/project"],
            denied_paths=["/project/secrets"],
        )
        context = _make_context(PathArgs(path="/project/secrets/key.pem"))
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_not_called()
        assert "❌" in context.result

    @pytest.mark.asyncio
    async def test_multiple_allowed_paths(self) -> None:
        """Test path matching any of multiple allowed directories passes."""
        middleware = PathRestrictionMiddleware(
            allowed_paths=["/project/src", "/project/tests"],
        )
        context = _make_context(PathArgs(path="/project/tests/test_main.py"))
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_denied_paths(self) -> None:
        """Test path matching any denied directory is blocked."""
        middleware = PathRestrictionMiddleware(
            denied_paths=["/etc", "/var/log"],
        )
        context = _make_context(PathArgs(path="/var/log/syslog"))
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_not_called()
        assert "❌" in context.result

    @pytest.mark.asyncio
    async def test_no_path_args_passes(self) -> None:
        """Test tool with no path-like arguments passes through."""
        middleware = PathRestrictionMiddleware(
            allowed_paths=["/allowed"],
            denied_paths=["/denied"],
        )
        context = _make_context(NoPathArgs(pattern="*.py", max_results=50))
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_none_path_value_passes(self) -> None:
        """Test None path value is skipped (not validated)."""
        middleware = PathRestrictionMiddleware(allowed_paths=["/allowed"])
        context = _make_context(OptionalPathArgs(file_path=None))
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolves_relative_paths(self) -> None:
        """Test relative paths are resolved to absolute before checking."""
        middleware = PathRestrictionMiddleware(denied_paths=["/etc"])
        # This relative path won't resolve to /etc, so it should pass
        context = _make_context(PathArgs(path="./local/file.txt"))
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolves_home_directory(self) -> None:
        """Test ~ in paths is expanded before checking."""
        middleware = PathRestrictionMiddleware(denied_paths=["/etc"])
        # ~/file.txt expands to home dir, not /etc
        context = _make_context(PathArgs(path="~/file.txt"))
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_source_destination_both_checked(self) -> None:
        """Test both source and destination fields are validated."""
        middleware = PathRestrictionMiddleware(denied_paths=["/secret"])
        # Source is OK, but destination is denied
        context = _make_context(
            MultiPathArgs(source="/project/file.txt", destination="/secret/copy.txt"),
        )
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_not_called()
        assert "❌" in context.result

    @pytest.mark.asyncio
    async def test_blocked_sets_error_result(self) -> None:
        """Test blocked path sets descriptive error on context.result."""
        middleware = PathRestrictionMiddleware(denied_paths=["/blocked"])
        context = _make_context(PathArgs(path="/blocked/file.txt"))
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        assert context.result is not None
        assert "❌ Error:" in context.result
        assert "/blocked/file.txt" in context.result
        assert "path restrictions" in context.result

    @pytest.mark.asyncio
    async def test_allowed_calls_next(self) -> None:
        """Test allowed path proceeds to call_next."""
        middleware = PathRestrictionMiddleware(
            allowed_paths=["/workspace"],
        )
        context = _make_context(PathArgs(path="/workspace/src/main.py"))
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_awaited_once()
        assert context.result is None

    @pytest.mark.asyncio
    async def test_denied_does_not_call_next(self) -> None:
        """Test denied path does NOT call call_next."""
        middleware = PathRestrictionMiddleware(denied_paths=["/private"])
        context = _make_context(PathArgs(path="/private/data.db"))
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_not_called()
