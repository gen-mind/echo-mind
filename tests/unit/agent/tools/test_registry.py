"""
Unit tests for ToolsRegistry.

Tests cover initialization, registration, retrieval, and filtering.
Target: 100% code coverage
"""

from unittest.mock import MagicMock, patch

import pytest

from agent_framework import FunctionTool

from src.agent.tools.registry import ToolsRegistry


class TestRegistryInit:
    """Tests for ToolsRegistry initialization."""

    @patch("src.agent.tools.registry.create_bash_tool")
    @patch("src.agent.tools.registry.create_read_tool")
    @patch("src.agent.tools.registry.create_write_tool")
    @patch("src.agent.tools.registry.create_grep_tool")
    @patch("src.agent.tools.registry.create_glob_tool")
    @patch("src.agent.tools.registry.create_git_log_tool")
    @patch("src.agent.tools.registry.create_git_diff_tool")
    @patch("src.agent.tools.registry.create_git_status_tool")
    @patch("src.agent.tools.registry.create_git_add_tool")
    @patch("src.agent.tools.registry.create_git_commit_tool")
    def test_registers_core_tools(
        self,
        mock_git_commit,
        mock_git_add,
        mock_git_status,
        mock_git_diff,
        mock_git_log,
        mock_glob,
        mock_grep,
        mock_write,
        mock_read,
        mock_bash,
    ):
        """Test that __init__ registers all 10 core tools."""
        registry = ToolsRegistry()
        assert registry.count() == 10

    @patch("src.agent.tools.registry.create_bash_tool")
    @patch("src.agent.tools.registry.create_read_tool")
    @patch("src.agent.tools.registry.create_write_tool")
    @patch("src.agent.tools.registry.create_grep_tool")
    @patch("src.agent.tools.registry.create_glob_tool")
    @patch("src.agent.tools.registry.create_git_log_tool")
    @patch("src.agent.tools.registry.create_git_diff_tool")
    @patch("src.agent.tools.registry.create_git_status_tool")
    @patch("src.agent.tools.registry.create_git_add_tool")
    @patch("src.agent.tools.registry.create_git_commit_tool")
    def test_expected_tool_names(
        self,
        mock_git_commit,
        mock_git_add,
        mock_git_status,
        mock_git_diff,
        mock_git_log,
        mock_glob,
        mock_grep,
        mock_write,
        mock_read,
        mock_bash,
    ):
        """Test that all expected tool names are registered."""
        registry = ToolsRegistry()
        expected = [
            "bash", "git_add", "git_commit", "git_diff", "git_log",
            "git_status", "glob", "grep", "read", "write",
        ]
        assert registry.list_names() == expected


class TestRegistryRegister:
    """Tests for register method."""

    def _make_empty_registry(self):
        """Create registry with no core tools."""
        with patch.object(ToolsRegistry, "_register_core_tools"):
            return ToolsRegistry()

    def test_register_new_tool(self):
        """Test registering a new tool wraps it as FunctionTool."""
        registry = self._make_empty_registry()

        def my_tool(x: str) -> str:
            """A test tool."""
            return x

        registry.register("my_tool", my_tool)

        result = registry.get("my_tool")
        assert isinstance(result, FunctionTool)
        assert registry.count() == 1

    def test_register_pre_wrapped_function_tool(self):
        """Test registering a pre-wrapped FunctionTool passes through."""
        registry = self._make_empty_registry()

        # Create a real FunctionTool by wrapping first
        def raw_tool(x: str = "") -> str:
            """A raw tool."""
            return x

        from agent_framework import tool as agent_tool
        wrapped = agent_tool(raw_tool, name="pre_wrapped")

        registry.register("pre_wrapped", wrapped)
        result = registry.get("pre_wrapped")

        # Should be the same FunctionTool instance, not double-wrapped
        assert result is wrapped
        assert isinstance(result, FunctionTool)

    def test_register_duplicate_raises(self):
        """Test that registering duplicate name raises ValueError."""
        registry = self._make_empty_registry()

        def dup_tool(x: str = "") -> str:
            """Duplicate tool."""
            return x

        registry.register("dup", dup_tool)

        with pytest.raises(ValueError, match="already registered"):
            registry.register("dup", dup_tool)


class TestRegistryGet:
    """Tests for get method."""

    def _make_registry(self, tools: dict):
        """Create registry with specific tools."""
        with patch.object(ToolsRegistry, "_register_core_tools"):
            registry = ToolsRegistry()
        for name, fn in tools.items():
            registry.register(name, fn)
        return registry

    def test_get_existing_tool(self):
        """Test getting an existing tool returns a FunctionTool."""
        def read_tool(path: str) -> str:
            """Read a file."""
            return path

        registry = self._make_registry({"read": read_tool})
        result = registry.get("read")
        assert isinstance(result, FunctionTool)

    def test_get_nonexistent_tool_returns_none(self):
        """Test getting non-existent tool returns None."""
        registry = self._make_registry({})
        assert registry.get("nonexistent") is None


class TestRegistryGetAll:
    """Tests for get_all method."""

    def test_get_all_returns_all_tools(self):
        """Test get_all returns list of all FunctionTool objects."""
        with patch.object(ToolsRegistry, "_register_core_tools"):
            registry = ToolsRegistry()

        def tool_a(x: str) -> str:
            """Tool A."""
            return x

        def tool_b(x: str) -> str:
            """Tool B."""
            return x

        registry.register("a", tool_a)
        registry.register("b", tool_b)

        result = registry.get_all()
        assert len(result) == 2
        assert all(isinstance(t, FunctionTool) for t in result)

    def test_get_all_empty_registry(self):
        """Test get_all on empty registry returns empty list."""
        with patch.object(ToolsRegistry, "_register_core_tools"):
            registry = ToolsRegistry()
        assert registry.get_all() == []


class TestRegistryGetFiltered:
    """Tests for get_filtered method with wildcard patterns."""

    @pytest.fixture
    def registry(self):
        """Create registry with test tools."""
        with patch.object(ToolsRegistry, "_register_core_tools"):
            reg = ToolsRegistry()

        def _make_tool(tool_name: str) -> callable:
            def tool_fn(x: str = "") -> str:
                f"""Tool {tool_name}."""
                return x
            tool_fn.__name__ = tool_name
            tool_fn.__doc__ = f"Tool {tool_name}."
            return tool_fn

        for name in ["read", "write", "grep", "glob", "bash",
                      "git_log", "git_diff", "git_status", "git_add", "git_commit"]:
            reg.register(name, _make_tool(name))
        return reg

    def test_no_filters_returns_all(self, registry):
        """Test no allow/deny returns all tools."""
        result = registry.get_filtered()
        assert len(result) == 10

    def test_none_filters_returns_all(self, registry):
        """Test allow=None, deny=None returns all tools."""
        result = registry.get_filtered(allow=None, deny=None)
        assert len(result) == 10

    def test_allow_wildcard(self, registry):
        """Test allow with wildcard pattern."""
        result = registry.get_filtered(allow=["git_*"])
        assert len(result) == 5

    def test_allow_exact(self, registry):
        """Test allow with exact name."""
        result = registry.get_filtered(allow=["bash"])
        assert len(result) == 1

    def test_allow_multiple_patterns(self, registry):
        """Test allow with multiple patterns."""
        result = registry.get_filtered(allow=["read", "write"])
        assert len(result) == 2

    def test_deny_wildcard(self, registry):
        """Test deny with wildcard pattern."""
        result = registry.get_filtered(deny=["git_*"])
        assert len(result) == 5  # read, write, grep, glob, bash

    def test_deny_exact(self, registry):
        """Test deny with exact name."""
        result = registry.get_filtered(deny=["bash"])
        assert len(result) == 9

    def test_deny_overrides_allow(self, registry):
        """Test that deny takes precedence over allow."""
        result = registry.get_filtered(allow=["git_*"], deny=["git_commit"])
        assert len(result) == 4  # git_log, git_diff, git_status, git_add

    def test_allow_and_deny_combined(self, registry):
        """Test combined allow and deny patterns."""
        result = registry.get_filtered(allow=["git_*", "bash"], deny=["git_add", "git_commit"])
        assert len(result) == 4  # git_log, git_diff, git_status, bash

    def test_empty_allow_list_returns_all(self, registry):
        """Test that empty allow list (falsy) returns all tools."""
        result = registry.get_filtered(allow=[])
        assert len(result) == 10

    def test_empty_deny_list_denies_nothing(self, registry):
        """Test that empty deny list denies nothing."""
        result = registry.get_filtered(deny=[])
        assert len(result) == 10

    def test_allow_no_match_returns_empty(self, registry):
        """Test allow pattern matching nothing returns empty."""
        result = registry.get_filtered(allow=["nonexistent_*"])
        assert len(result) == 0

    def test_deny_all_returns_empty(self, registry):
        """Test deny pattern matching everything returns empty."""
        result = registry.get_filtered(deny=["*"])
        assert len(result) == 0

    def test_preserves_insertion_order(self, registry):
        """Test that result preserves tool insertion order."""
        result = registry.get_filtered(allow=["read", "write", "bash"])
        assert len(result) == 3
        assert all(isinstance(t, FunctionTool) for t in result)


class TestRegistryListNames:
    """Tests for list_names method."""

    def test_list_names_sorted(self):
        """Test list_names returns sorted names."""
        with patch.object(ToolsRegistry, "_register_core_tools"):
            registry = ToolsRegistry()

        def make_fn(n: str) -> callable:
            def fn(x: str = "") -> str:
                f"""Tool {n}."""
                return x
            fn.__name__ = n
            fn.__doc__ = f"Tool {n}."
            return fn

        registry.register("zebra", make_fn("zebra"))
        registry.register("alpha", make_fn("alpha"))
        registry.register("middle", make_fn("middle"))

        assert registry.list_names() == ["alpha", "middle", "zebra"]

    def test_list_names_empty(self):
        """Test list_names on empty registry."""
        with patch.object(ToolsRegistry, "_register_core_tools"):
            registry = ToolsRegistry()
        assert registry.list_names() == []


class TestRegistryCount:
    """Tests for count method."""

    def test_count_empty(self):
        """Test count on empty registry."""
        with patch.object(ToolsRegistry, "_register_core_tools"):
            registry = ToolsRegistry()
        assert registry.count() == 0

    def test_count_after_registration(self):
        """Test count after adding tools."""
        with patch.object(ToolsRegistry, "_register_core_tools"):
            registry = ToolsRegistry()

        def tool_a(x: str = "") -> str:
            """Tool A."""
            return x

        def tool_b(x: str = "") -> str:
            """Tool B."""
            return x

        registry.register("a", tool_a)
        registry.register("b", tool_b)
        assert registry.count() == 2
