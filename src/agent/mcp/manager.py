"""
MCP Manager — Lifecycle management for MCP server connections.

Creates, connects, and disconnects MCPTool instances from config.
Provides per-agent tool retrieval by server name references.

The framework's MCPTool classes handle the actual protocol:
- MCPStdioTool: stdio subprocess transport
- MCPStreamableHTTPTool: HTTP/SSE transport
- MCPWebsocketTool: WebSocket transport
"""

from __future__ import annotations

import logging
from typing import Any

from agent_framework import (
    MCPStdioTool,
    MCPStreamableHTTPTool,
    MCPWebsocketTool,
)

from ..config.schema import MCPServerConfig

logger = logging.getLogger(__name__)

# Type alias for any MCPTool variant
MCPTool = MCPStdioTool | MCPStreamableHTTPTool | MCPWebsocketTool

_VALID_TRANSPORTS = {"stdio", "http", "websocket"}


class MCPManager:
    """
    Manages MCP server connections and lifecycle.

    Creates MCPTool instances from config, connects them,
    and provides per-agent tool retrieval. Designed as an
    async context manager for clean startup/shutdown.

    Usage:
        async with MCPManager(configs) as manager:
            tools = manager.get_tools_for_agent(["filesystem", "github"])
            agent = Agent(tools=native_tools + tools)
    """

    def __init__(self, configs: list[MCPServerConfig]) -> None:
        """
        Initialize MCPManager with server configs.

        Args:
            configs: List of MCP server configurations.
        """
        self._configs: dict[str, MCPServerConfig] = {c.name: c for c in configs}
        self._tools: dict[str, MCPTool] = {}
        self._connected: set[str] = set()

    def _create_tool(self, config: MCPServerConfig) -> MCPTool:
        """
        Create an MCPTool instance from config (not yet connected).

        Args:
            config: MCP server configuration.

        Returns:
            MCPTool instance ready for connection.

        Raises:
            ValueError: If transport type is unknown.
        """
        if config.transport not in _VALID_TRANSPORTS:
            raise ValueError(
                f"Unknown MCP transport '{config.transport}' for server '{config.name}'"
            )

        if config.transport == "stdio":
            tool_class = MCPStdioTool
        elif config.transport == "http":
            tool_class = MCPStreamableHTTPTool
        else:
            tool_class = MCPWebsocketTool

        # Build kwargs based on transport type
        kwargs: dict[str, Any] = {"name": config.name}

        if config.transport == "stdio":
            kwargs["command"] = config.command
            kwargs["args"] = config.args
            if config.env:
                kwargs["env"] = config.env
        else:
            # http or websocket
            kwargs["url"] = config.url
            if config.headers:
                kwargs["headers"] = config.headers

        # Approval mode
        if config.tool_approvals:
            # Build MCPSpecificApproval dict
            always_require = [
                name for name, mode in config.tool_approvals.items()
                if mode == "always_require"
            ]
            never_require = [
                name for name, mode in config.tool_approvals.items()
                if mode == "never_require"
            ]
            specific: dict[str, list[str]] = {}
            if always_require:
                specific["always_require_approval"] = always_require
            if never_require:
                specific["never_require_approval"] = never_require
            kwargs["approval_mode"] = specific
        elif config.approval_mode:
            kwargs["approval_mode"] = config.approval_mode

        # Optional fields
        if config.allowed_tools is not None:
            kwargs["allowed_tools"] = config.allowed_tools
        if config.request_timeout is not None:
            kwargs["request_timeout"] = config.request_timeout

        return tool_class(**kwargs)

    async def connect_all(self) -> None:
        """
        Connect all configured MCP servers.

        Failures are logged but not raised — partial connectivity
        is acceptable. Agents will get warnings about unavailable servers.
        """
        for name, config in self._configs.items():
            try:
                tool = self._create_tool(config)
                await tool.__aenter__()
                self._tools[name] = tool
                self._connected.add(name)
                logger.info(f"🔌 MCP server '{name}' connected ({config.transport})")
            except Exception as e:
                logger.warning(
                    f"⚠️ MCP server '{name}' connection failed: {e}"
                )

        total = len(self._configs)
        logger.info(
            f"🔌 MCP connection summary: {self.connected_count}/{total} servers connected"
        )

    async def disconnect_all(self) -> None:
        """
        Disconnect all connected MCP servers.

        Errors during disconnect are logged but not raised.
        """
        for name in list(self._connected):
            try:
                tool = self._tools[name]
                await tool.__aexit__(None, None, None)
                logger.info(f"🔌 MCP server '{name}' disconnected")
            except Exception as e:
                logger.warning(
                    f"⚠️ MCP server '{name}' disconnect failed: {e}"
                )
            finally:
                self._connected.discard(name)

    async def __aenter__(self) -> MCPManager:
        """
        Enter async context — connects all servers.

        Returns:
            Self with connected servers.
        """
        await self.connect_all()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context — disconnects all servers."""
        await self.disconnect_all()

    def get_tools_for_agent(self, server_names: list[str]) -> list[MCPTool]:
        """
        Get connected MCPTool objects for the given server names.

        Skips unavailable servers with a warning log.

        Args:
            server_names: List of MCP server names the agent references.

        Returns:
            List of connected MCPTool instances.
        """
        tools: list[MCPTool] = []
        for name in server_names:
            if name in self._connected:
                tools.append(self._tools[name])
            else:
                logger.warning(
                    f"⚠️ MCP server '{name}' not connected, skipping"
                )
        return tools

    def is_connected(self, name: str) -> bool:
        """
        Check if a server is connected.

        Args:
            name: MCP server name.

        Returns:
            True if connected.
        """
        return name in self._connected

    @property
    def connected_count(self) -> int:
        """
        Get number of connected servers.

        Returns:
            Count of connected MCP servers.
        """
        return len(self._connected)
