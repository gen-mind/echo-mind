"""
Unit tests for MCPManager.

Tests cover tool creation, connection lifecycle, per-agent retrieval,
approval modes, and error handling.
Target: 100% code coverage
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.agent.config.schema import MCPServerConfig
from src.agent.mcp.manager import MCPManager


def _make_config(
    name: str = "test-server",
    transport: str = "stdio",
    command: str = "echo",
    url: str | None = None,
    **kwargs,
) -> MCPServerConfig:
    """Helper to create MCPServerConfig for tests."""
    if transport == "stdio":
        return MCPServerConfig(
            name=name, transport=transport, command=command, **kwargs
        )
    else:
        return MCPServerConfig(
            name=name, transport=transport, url=url or "https://mcp.test/api", **kwargs
        )


class TestCreateTool:
    """Tests for MCPManager._create_tool."""

    @patch("src.agent.mcp.manager.MCPStdioTool")
    def test_create_stdio_tool(self, mock_class):
        """Test creating a stdio MCPTool."""
        config = _make_config(
            name="fs", transport="stdio", command="npx",
            args=["-y", "server-fs", "/tmp"],
            env={"NODE_ENV": "production"},
        )
        manager = MCPManager([config])
        manager._create_tool(config)

        mock_class.assert_called_once_with(
            name="fs",
            command="npx",
            args=["-y", "server-fs", "/tmp"],
            env={"NODE_ENV": "production"},
        )

    @patch("src.agent.mcp.manager.MCPStreamableHTTPTool")
    def test_create_http_tool(self, mock_class):
        """Test creating an HTTP MCPTool."""
        config = _make_config(
            name="github", transport="http",
            url="https://mcp.test/github",
            headers={"Authorization": "Bearer tok123"},
        )
        manager = MCPManager([config])
        manager._create_tool(config)

        mock_class.assert_called_once_with(
            name="github",
            url="https://mcp.test/github",
            headers={"Authorization": "Bearer tok123"},
        )

    @patch("src.agent.mcp.manager.MCPWebsocketTool")
    def test_create_websocket_tool(self, mock_class):
        """Test creating a WebSocket MCPTool."""
        config = _make_config(
            name="ws", transport="websocket",
            url="wss://mcp.test/ws",
        )
        manager = MCPManager([config])
        manager._create_tool(config)

        mock_class.assert_called_once_with(
            name="ws",
            url="wss://mcp.test/ws",
        )

    def test_unknown_transport_raises(self):
        """Test that unknown transport raises ValueError."""
        # Bypass MCPServerConfig validation to test manager logic
        config = MagicMock(spec=MCPServerConfig)
        config.name = "bad"
        config.transport = "grpc"

        manager = MCPManager([])
        with pytest.raises(ValueError, match="Unknown MCP transport 'grpc'"):
            manager._create_tool(config)

    @patch("src.agent.mcp.manager.MCPStdioTool")
    def test_approval_mode_string(self, mock_class):
        """Test that approval_mode string is passed through."""
        config = _make_config(approval_mode="always_require")
        manager = MCPManager([config])
        manager._create_tool(config)

        call_kwargs = mock_class.call_args.kwargs
        assert call_kwargs["approval_mode"] == "always_require"

    @patch("src.agent.mcp.manager.MCPStdioTool")
    def test_approval_mode_with_per_tool_overrides(self, mock_class):
        """Test that tool_approvals builds MCPSpecificApproval dict."""
        config = _make_config(
            tool_approvals={
                "delete_file": "always_require",
                "list_files": "never_require",
                "read_file": "never_require",
            },
        )
        manager = MCPManager([config])
        manager._create_tool(config)

        call_kwargs = mock_class.call_args.kwargs
        approval = call_kwargs["approval_mode"]
        assert approval["always_require_approval"] == ["delete_file"]
        assert sorted(approval["never_require_approval"]) == ["list_files", "read_file"]

    @patch("src.agent.mcp.manager.MCPStdioTool")
    def test_allowed_tools_forwarded(self, mock_class):
        """Test that allowed_tools is forwarded to tool constructor."""
        config = _make_config(allowed_tools=["read_file", "list_dir"])
        manager = MCPManager([config])
        manager._create_tool(config)

        call_kwargs = mock_class.call_args.kwargs
        assert call_kwargs["allowed_tools"] == ["read_file", "list_dir"]

    @patch("src.agent.mcp.manager.MCPStdioTool")
    def test_request_timeout_forwarded(self, mock_class):
        """Test that request_timeout is forwarded to tool constructor."""
        config = _make_config(request_timeout=30)
        manager = MCPManager([config])
        manager._create_tool(config)

        call_kwargs = mock_class.call_args.kwargs
        assert call_kwargs["request_timeout"] == 30

    @patch("src.agent.mcp.manager.MCPStdioTool")
    def test_no_optional_fields_omitted(self, mock_class):
        """Test that optional fields are omitted when not set."""
        config = _make_config()
        manager = MCPManager([config])
        manager._create_tool(config)

        call_kwargs = mock_class.call_args.kwargs
        assert "allowed_tools" not in call_kwargs
        assert "request_timeout" not in call_kwargs
        assert "env" not in call_kwargs
        assert "approval_mode" not in call_kwargs

    @patch("src.agent.mcp.manager.MCPStreamableHTTPTool")
    def test_http_no_headers_omitted(self, mock_class):
        """Test that empty headers dict is not passed."""
        config = _make_config(name="h", transport="http", url="https://test.com")
        manager = MCPManager([config])
        manager._create_tool(config)

        call_kwargs = mock_class.call_args.kwargs
        assert "headers" not in call_kwargs


class TestConnectAll:
    """Tests for MCPManager.connect_all."""

    @pytest.mark.asyncio
    async def test_connect_all_success(self):
        """Test successful connection of all servers."""
        config = _make_config(name="s1")
        manager = MCPManager([config])

        mock_tool = AsyncMock()
        with patch.object(manager, "_create_tool", return_value=mock_tool):
            await manager.connect_all()

        mock_tool.__aenter__.assert_called_once()
        assert manager.is_connected("s1")
        assert manager.connected_count == 1

    @pytest.mark.asyncio
    async def test_connect_all_partial_failure(self):
        """Test that one failure doesn't block others."""
        c1 = _make_config(name="ok")
        c2 = _make_config(name="fail")
        manager = MCPManager([c1, c2])

        mock_ok = AsyncMock()
        mock_fail = AsyncMock()
        mock_fail.__aenter__.side_effect = ConnectionError("refused")

        call_count = 0

        def create_side_effect(config):
            nonlocal call_count
            call_count += 1
            return mock_ok if config.name == "ok" else mock_fail

        with patch.object(manager, "_create_tool", side_effect=create_side_effect):
            await manager.connect_all()

        assert manager.is_connected("ok")
        assert not manager.is_connected("fail")
        assert manager.connected_count == 1


class TestDisconnectAll:
    """Tests for MCPManager.disconnect_all."""

    @pytest.mark.asyncio
    async def test_disconnect_all_success(self):
        """Test clean disconnection of all servers."""
        config = _make_config(name="s1")
        manager = MCPManager([config])

        mock_tool = AsyncMock()
        with patch.object(manager, "_create_tool", return_value=mock_tool):
            await manager.connect_all()

        assert manager.connected_count == 1
        await manager.disconnect_all()

        mock_tool.__aexit__.assert_called_once_with(None, None, None)
        assert manager.connected_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_handles_errors(self):
        """Test that disconnect errors are logged, not raised."""
        config = _make_config(name="s1")
        manager = MCPManager([config])

        mock_tool = AsyncMock()
        mock_tool.__aexit__.side_effect = RuntimeError("cleanup failed")
        with patch.object(manager, "_create_tool", return_value=mock_tool):
            await manager.connect_all()

        # Should not raise
        await manager.disconnect_all()
        assert manager.connected_count == 0


class TestAsyncContextManager:
    """Tests for MCPManager as async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_connects_and_disconnects(self):
        """Test that __aenter__/__aexit__ call connect/disconnect."""
        config = _make_config(name="ctx")
        mock_tool = AsyncMock()

        with patch("src.agent.mcp.manager.MCPStdioTool", return_value=mock_tool):
            async with MCPManager([config]) as manager:
                assert manager.is_connected("ctx")
                assert manager.connected_count == 1

        # After exit, tool disconnected
        mock_tool.__aexit__.assert_called_once()


class TestGetToolsForAgent:
    """Tests for MCPManager.get_tools_for_agent."""

    @pytest.mark.asyncio
    async def test_returns_connected_tools(self):
        """Test retrieving tools for connected servers."""
        c1 = _make_config(name="s1")
        c2 = _make_config(name="s2")
        manager = MCPManager([c1, c2])

        mock_t1 = AsyncMock()
        mock_t2 = AsyncMock()

        def create_side_effect(config):
            return mock_t1 if config.name == "s1" else mock_t2

        with patch.object(manager, "_create_tool", side_effect=create_side_effect):
            await manager.connect_all()

        tools = manager.get_tools_for_agent(["s1", "s2"])
        assert len(tools) == 2
        assert mock_t1 in tools
        assert mock_t2 in tools

    @pytest.mark.asyncio
    async def test_skips_unconnected_with_warning(self):
        """Test that unconnected servers are skipped with warning."""
        c1 = _make_config(name="connected")
        manager = MCPManager([c1])

        mock_tool = AsyncMock()
        with patch.object(manager, "_create_tool", return_value=mock_tool):
            await manager.connect_all()

        tools = manager.get_tools_for_agent(["connected", "not_connected"])
        assert len(tools) == 1

    def test_empty_list_returns_empty(self):
        """Test that empty server names returns empty list."""
        manager = MCPManager([])
        assert manager.get_tools_for_agent([]) == []


class TestProperties:
    """Tests for MCPManager properties."""

    def test_initial_state(self):
        """Test initial state with no connections."""
        config = _make_config()
        manager = MCPManager([config])
        assert manager.connected_count == 0
        assert not manager.is_connected("test-server")

    @pytest.mark.asyncio
    async def test_is_connected_after_connect(self):
        """Test is_connected returns True after successful connection."""
        config = _make_config(name="srv")
        manager = MCPManager([config])

        mock_tool = AsyncMock()
        with patch.object(manager, "_create_tool", return_value=mock_tool):
            await manager.connect_all()

        assert manager.is_connected("srv")
        assert not manager.is_connected("other")
