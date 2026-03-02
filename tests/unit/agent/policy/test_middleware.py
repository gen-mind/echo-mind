"""
Unit tests for ToolPolicyMiddleware.

Tests cover the middleware's interaction with the policy engine, context
extraction from chat metadata, and edge cases like missing metadata.
Target: 100% code coverage.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent_framework import ChatContext, FunctionTool

from src.agent.policy.engine import PolicyContext, ToolPolicyEngine
from src.agent.policy.middleware import ToolPolicyMiddleware


def make_tool(name: str) -> FunctionTool:
    """
    Create a mock FunctionTool with the given name.

    Args:
        name: Tool name to assign.

    Returns:
        MagicMock with FunctionTool spec and .name set.
    """
    tool = MagicMock(spec=FunctionTool)
    tool.name = name
    return tool


class TestToolPolicyMiddleware:
    """Tests for ToolPolicyMiddleware."""

    @pytest.fixture
    def mock_engine(self) -> MagicMock:
        """Create a mock ToolPolicyEngine."""
        engine = MagicMock(spec=ToolPolicyEngine)
        engine.provider = "openai"
        return engine

    @pytest.fixture
    def middleware(self, mock_engine: MagicMock) -> ToolPolicyMiddleware:
        """Create a ToolPolicyMiddleware with mocked engine."""
        return ToolPolicyMiddleware(engine=mock_engine)

    @pytest.mark.asyncio
    async def test_process_filters_tools(
        self, middleware: ToolPolicyMiddleware, mock_engine: MagicMock,
    ) -> None:
        """Test that process() replaces tools with filtered list."""
        tool_read = make_tool("read")
        tool_write = make_tool("write")
        all_tools = [tool_read, tool_write]

        # Engine returns only read
        mock_engine.filter_tools.return_value = [tool_read]

        context = MagicMock(spec=ChatContext)
        context.options = {"tools": all_tools}
        context.metadata = None

        call_next = AsyncMock()

        await middleware.process(context, call_next)

        # Verify tools were replaced
        assert context.options["tools"] == [tool_read]
        mock_engine.filter_tools.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_calls_call_next(
        self, middleware: ToolPolicyMiddleware, mock_engine: MagicMock,
    ) -> None:
        """Test that process() awaits call_next."""
        mock_engine.filter_tools.return_value = []
        context = MagicMock(spec=ChatContext)
        context.options = {"tools": []}
        context.metadata = None

        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_extracts_parent_agent_id(
        self, middleware: ToolPolicyMiddleware, mock_engine: MagicMock,
    ) -> None:
        """Test that parent_agent_id is extracted from context.metadata."""
        mock_engine.filter_tools.return_value = []
        context = MagicMock(spec=ChatContext)
        context.options = {"tools": []}
        context.metadata = {"parent_agent_id": "parent-123"}

        call_next = AsyncMock()

        await middleware.process(context, call_next)

        # Check that filter_tools was called with correct PolicyContext
        call_args = mock_engine.filter_tools.call_args
        policy_ctx = call_args[0][1]  # Second positional arg
        assert isinstance(policy_ctx, PolicyContext)
        assert policy_ctx.parent_agent_id == "parent-123"
        assert policy_ctx.provider == "openai"

    @pytest.mark.asyncio
    async def test_process_handles_missing_metadata(
        self, middleware: ToolPolicyMiddleware, mock_engine: MagicMock,
    ) -> None:
        """Test that None metadata results in parent_agent_id=None."""
        mock_engine.filter_tools.return_value = []
        context = MagicMock(spec=ChatContext)
        context.options = {"tools": []}
        context.metadata = None

        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_args = mock_engine.filter_tools.call_args
        policy_ctx = call_args[0][1]
        assert policy_ctx.parent_agent_id is None

    @pytest.mark.asyncio
    async def test_process_handles_empty_tools(
        self, middleware: ToolPolicyMiddleware, mock_engine: MagicMock,
    ) -> None:
        """Test that missing 'tools' key in options defaults to empty list."""
        mock_engine.filter_tools.return_value = []
        context = MagicMock(spec=ChatContext)
        context.options = {}  # No "tools" key
        context.metadata = None

        call_next = AsyncMock()

        await middleware.process(context, call_next)

        # filter_tools called with empty list
        call_args = mock_engine.filter_tools.call_args
        assert call_args[0][0] == []
