"""
MCP (Model Context Protocol) server integration.

Provides MCPManager for connecting to external tool servers
and exposing their tools alongside native agent tools.
"""

from .manager import MCPManager

__all__ = ["MCPManager"]
