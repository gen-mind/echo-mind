"""
Tools Registry for Agent System

Central registry for all available tools. Tools are registered by name
and can be retrieved individually or in bulk with wildcard pattern filtering.
"""

import fnmatch
import logging
from collections.abc import Callable
from typing import Any

from agent_framework import FunctionTool, tool as agent_tool

logger = logging.getLogger(__name__)

from .execution import create_bash_tool
from .filesystem import create_glob_tool, create_grep_tool, create_read_tool, create_write_tool
from .git import (
    create_git_add_tool,
    create_git_commit_tool,
    create_git_diff_tool,
    create_git_log_tool,
    create_git_status_tool,
)


class ToolsRegistry:
    """
    Registry of all available tools.

    Manages tool registration and retrieval. Tools are functions that
    can be called by agents during execution.

    Usage:
        registry = ToolsRegistry()
        all_tools = registry.get_all()
        read_tool = registry.get("read")
    """

    def __init__(self) -> None:
        """Initialize registry and register core tools."""
        self.tools: dict[str, FunctionTool | Callable[..., Any]] = {}
        self._register_core_tools()
        logger.info(f"🔧 ToolsRegistry initialized with {self.count()} tools")

    def _register_core_tools(self) -> None:
        """Register Phase 1 core tools (10 tools)."""
        # Filesystem tools (4 tools)
        self.register("read", create_read_tool())
        self.register("write", create_write_tool())
        self.register("grep", create_grep_tool())
        self.register("glob", create_glob_tool())

        # Execution tools (1 tool)
        self.register("bash", create_bash_tool())

        # Git tools (5 tools)
        self.register("git_log", create_git_log_tool())
        self.register("git_diff", create_git_diff_tool())
        self.register("git_status", create_git_status_tool())
        self.register("git_add", create_git_add_tool())
        self.register("git_commit", create_git_commit_tool())

    def register(self, name: str, tool_func: Callable[..., Any]) -> None:
        """
        Register a tool in the registry.

        Plain callables are automatically wrapped as FunctionTool via
        the agent_framework @tool decorator so they can be serialized
        to the OpenAI tool-calling API.

        Args:
            name: Unique tool name
            tool_func: Tool function (plain callable or FunctionTool)

        Raises:
            ValueError: If tool name already registered
        """
        if name in self.tools:
            raise ValueError(f"Tool '{name}' is already registered")

        # Wrap plain callables as FunctionTool for OpenAI compatibility
        if isinstance(tool_func, FunctionTool):
            self.tools[name] = tool_func
        else:
            self.tools[name] = agent_tool(tool_func, name=name)

    def get(self, name: str) -> FunctionTool | Callable[..., Any] | None:
        """
        Get tool by name.

        Args:
            name: Tool name

        Returns:
            Tool function or None if not found
        """
        return self.tools.get(name)

    def get_all(self) -> list[FunctionTool | Callable[..., Any]]:
        """
        Get all registered tools.

        Returns:
            List of all tool functions
        """
        return list(self.tools.values())

    def get_filtered(
        self,
        allow: list[str] | None = None,
        deny: list[str] | None = None,
    ) -> list[FunctionTool | Callable[..., Any]]:
        """
        Get filtered list of tools using allow/deny wildcard patterns.

        Allow patterns are applied first (if empty/None, all tools are allowed).
        Deny patterns override allow (deny takes precedence).
        Patterns support fnmatch wildcards: ``*``, ``?``, ``[seq]``.

        Args:
            allow: Wildcard patterns for tools to include (None = all).
            deny: Wildcard patterns for tools to exclude (takes precedence).

        Returns:
            List of matching tool functions.
        """
        all_names = list(self.tools.keys())

        # Step 1: Apply allow filter (empty = allow all)
        if allow:
            allowed = {
                name for name in all_names
                if any(fnmatch.fnmatch(name, pattern) for pattern in allow)
            }
        else:
            allowed = set(all_names)

        # Step 2: Apply deny filter (deny takes precedence)
        if deny:
            allowed = {
                name for name in allowed
                if not any(fnmatch.fnmatch(name, pattern) for pattern in deny)
            }

        result = [self.tools[name] for name in all_names if name in allowed]
        logger.info(
            f"📦 Filtered tools: {len(result)}/{len(all_names)} "
            f"(allow={allow}, deny={deny})"
        )
        return result

    def list_names(self) -> list[str]:
        """
        Get list of all registered tool names.

        Returns:
            Sorted list of tool names
        """
        return sorted(self.tools.keys())

    def count(self) -> int:
        """
        Get count of registered tools.

        Returns:
            Number of tools registered
        """
        return len(self.tools)
