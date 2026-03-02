"""
Unit tests for ToolsRegistry approval_mode support.

Tests cover approval_mode parameter handling in registration
and correct assignment to all 30 registered tools.
"""

from unittest.mock import patch

import pytest

from agent_framework import FunctionTool

from src.agent.config.schema import ToolApprovalConfig
from src.agent.tools.registry import ToolsRegistry


class TestRegistryApprovalMode:
    """Tests for approval_mode parameter on register()."""

    def _make_empty_registry(self) -> ToolsRegistry:
        """Create registry with no core tools."""
        with patch.object(ToolsRegistry, "_register_core_tools"):
            return ToolsRegistry()

    def test_register_with_always_require(self) -> None:
        """Test registering a tool with always_require approval mode."""
        registry = self._make_empty_registry()

        def destructive_tool(path: str) -> str:
            """A destructive tool."""
            return path

        registry.register("destroy", destructive_tool, approval_mode="always_require")
        tool = registry.get("destroy")
        assert isinstance(tool, FunctionTool)
        assert tool.approval_mode == "always_require"

    def test_register_with_never_require(self) -> None:
        """Test registering a tool with never_require approval mode."""
        registry = self._make_empty_registry()

        def safe_tool(path: str) -> str:
            """A safe tool."""
            return path

        registry.register("safe", safe_tool, approval_mode="never_require")
        tool = registry.get("safe")
        assert isinstance(tool, FunctionTool)
        assert tool.approval_mode == "never_require"

    def test_register_with_no_approval_mode(self) -> None:
        """Test registering a tool with None approval_mode defaults to never_require."""
        registry = self._make_empty_registry()

        def basic_tool(x: str) -> str:
            """A basic tool."""
            return x

        registry.register("basic", basic_tool, approval_mode=None)
        tool = registry.get("basic")
        assert isinstance(tool, FunctionTool)
        # Framework defaults None to "never_require"
        assert tool.approval_mode == "never_require"

    def test_register_default_approval_mode(self) -> None:
        """Test that default approval_mode (not specified) defaults to never_require."""
        registry = self._make_empty_registry()

        def basic_tool(x: str) -> str:
            """A basic tool."""
            return x

        registry.register("basic", basic_tool)
        tool = registry.get("basic")
        assert isinstance(tool, FunctionTool)
        # Framework defaults to "never_require"
        assert tool.approval_mode == "never_require"


class TestRegistryToolCount:
    """Tests for correct tool count after Phase 5 expansion."""

    def test_registers_30_tools(self) -> None:
        """Test that __init__ registers all 30 tools."""
        registry = ToolsRegistry()
        assert registry.count() == 30

    def test_expected_tool_names(self) -> None:
        """Test that all 30 expected tool names are registered."""
        registry = ToolsRegistry()
        expected = sorted([
            # Filesystem (4)
            "read", "write", "grep", "glob",
            # Edit (1)
            "edit",
            # Directory (5)
            "list_dir", "tree", "mkdir", "move", "delete",
            # Execution (1)
            "bash",
            # Web (1)
            "http_request",
            # Core git (5)
            "git_log", "git_diff", "git_status", "git_add", "git_commit",
            # Extended git (8)
            "git_branch", "git_checkout", "git_stash", "git_push",
            "git_pull", "git_reset", "git_clone", "git_tag",
            # System (3)
            "env_get", "which", "find_replace",
            # Text (2)
            "diff", "patch",
        ])
        assert registry.list_names() == expected


class TestRegistryApprovalModes:
    """Tests for correct approval modes on registered tools."""

    @pytest.fixture
    def registry(self) -> ToolsRegistry:
        """Create a full registry."""
        return ToolsRegistry()

    def test_destructive_tools_require_approval(self, registry: ToolsRegistry) -> None:
        """Test that destructive tools have always_require approval."""
        destructive_tools = [
            "write", "edit", "move", "delete", "bash",
            "git_add", "git_commit", "git_checkout", "git_push",
            "git_pull", "git_reset", "find_replace", "patch",
        ]
        for name in destructive_tools:
            tool = registry.get(name)
            assert isinstance(tool, FunctionTool), f"Tool '{name}' not found"
            assert tool.approval_mode == "always_require", (
                f"Tool '{name}' should have always_require approval, "
                f"got {tool.approval_mode}"
            )

    def test_safe_tools_never_require_approval(self, registry: ToolsRegistry) -> None:
        """Test that safe tools have never_require approval."""
        safe_tools = [
            "read", "grep", "glob", "list_dir", "tree", "mkdir",
            "http_request", "git_log", "git_diff", "git_status",
            "git_branch", "git_stash", "git_clone", "git_tag",
            "env_get", "which", "diff",
        ]
        for name in safe_tools:
            tool = registry.get(name)
            assert isinstance(tool, FunctionTool), f"Tool '{name}' not found"
            assert tool.approval_mode == "never_require", (
                f"Tool '{name}' should have never_require approval, "
                f"got {tool.approval_mode}"
            )

    def test_all_tools_have_approval_mode_set(self, registry: ToolsRegistry) -> None:
        """Test that every registered tool has an explicit approval mode."""
        for name in registry.list_names():
            tool = registry.get(name)
            assert isinstance(tool, FunctionTool), f"Tool '{name}' not a FunctionTool"
            assert tool.approval_mode in ("always_require", "never_require"), (
                f"Tool '{name}' has unexpected approval_mode: {tool.approval_mode}"
            )


class TestApplyApprovalOverrides:
    """Tests for apply_approval_overrides method."""

    def _make_registry_with_tools(self) -> ToolsRegistry:
        """Create registry with test tools."""
        with patch.object(ToolsRegistry, "_register_core_tools"):
            registry = ToolsRegistry()

        def safe_tool(x: str) -> str:
            """Safe tool."""
            return x

        def danger_tool(x: str) -> str:
            """Dangerous tool."""
            return x

        registry.register("read", safe_tool, approval_mode="never_require")
        registry.register("write", danger_tool, approval_mode="always_require")
        registry.register("git_push", danger_tool, approval_mode="always_require")
        registry.register("git_log", safe_tool, approval_mode="never_require")
        return registry

    def test_empty_config_no_changes(self) -> None:
        """Test that empty config doesn't change any approval modes."""
        registry = self._make_registry_with_tools()
        config = ToolApprovalConfig()
        registry.apply_approval_overrides(config)

        assert registry.get("read").approval_mode == "never_require"
        assert registry.get("write").approval_mode == "always_require"

    def test_require_approval_overrides(self) -> None:
        """Test require_approval forces tools to always_require."""
        registry = self._make_registry_with_tools()
        config = ToolApprovalConfig(require_approval=["read"])
        registry.apply_approval_overrides(config)

        assert registry.get("read").approval_mode == "always_require"

    def test_skip_approval_overrides(self) -> None:
        """Test skip_approval forces tools to never_require."""
        registry = self._make_registry_with_tools()
        config = ToolApprovalConfig(skip_approval=["write"])
        registry.apply_approval_overrides(config)

        assert registry.get("write").approval_mode == "never_require"

    def test_require_takes_precedence_over_skip(self) -> None:
        """Test require_approval wins when both match."""
        registry = self._make_registry_with_tools()
        config = ToolApprovalConfig(
            require_approval=["read"],
            skip_approval=["read"],
        )
        registry.apply_approval_overrides(config)

        # require takes precedence
        assert registry.get("read").approval_mode == "always_require"

    def test_wildcard_patterns(self) -> None:
        """Test wildcard patterns in approval overrides."""
        registry = self._make_registry_with_tools()
        config = ToolApprovalConfig(skip_approval=["git_*"])
        registry.apply_approval_overrides(config)

        assert registry.get("git_push").approval_mode == "never_require"
        assert registry.get("git_log").approval_mode == "never_require"
        # Non-matching tools unchanged
        assert registry.get("write").approval_mode == "always_require"

    def test_no_match_leaves_unchanged(self) -> None:
        """Test that non-matching patterns leave tools unchanged."""
        registry = self._make_registry_with_tools()
        config = ToolApprovalConfig(require_approval=["nonexistent_*"])
        registry.apply_approval_overrides(config)

        assert registry.get("read").approval_mode == "never_require"
        assert registry.get("write").approval_mode == "always_require"
