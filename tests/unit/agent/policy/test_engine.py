"""
Unit tests for ToolPolicyEngine.

Tests cover all 9 layers (Layer 7 skipped) of the cascading tool filter:
profile presets, provider profiles, global policy, global+provider,
agent policy, agent+provider, sandbox, and subagent restrictions.
Target: 100% code coverage.
"""

import pytest
from unittest.mock import MagicMock

from agent_framework import FunctionTool

from src.agent.config.schema import (
    AgentConfig,
    MoltbotConfig,
    RoutingConfig,
    SandboxConfig,
    ToolPolicy,
)
from src.agent.policy.engine import PolicyContext, ToolPolicyEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def make_config(
    global_profile: str | None = None,
    global_allow: list[str] | None = None,
    global_deny: list[str] | None = None,
    global_by_provider: dict[str, ToolPolicy] | None = None,
    agent_profile: str | None = None,
    agent_allow: list[str] | None = None,
    agent_deny: list[str] | None = None,
    agent_by_provider: dict[str, ToolPolicy] | None = None,
    sandbox_enabled: bool = False,
    sandbox_denied: list[str] | None = None,
) -> tuple[MoltbotConfig, AgentConfig]:
    """
    Build a (MoltbotConfig, AgentConfig) pair for testing.

    Args:
        global_profile: Profile name for global tool policy.
        global_allow: Global allow patterns.
        global_deny: Global deny patterns.
        global_by_provider: Global per-provider overrides.
        agent_profile: Profile name for agent tool policy.
        agent_allow: Agent allow patterns.
        agent_deny: Agent deny patterns.
        agent_by_provider: Agent per-provider overrides.
        sandbox_enabled: Whether sandbox is enabled.
        sandbox_denied: Tools denied by sandbox.

    Returns:
        Tuple of (MoltbotConfig, AgentConfig).
    """
    has_agent_policy = any([
        agent_profile, agent_allow, agent_deny, agent_by_provider,
    ])
    agent = AgentConfig(
        id="test-agent",
        name="Test",
        model="gpt-4o-mini",
        tools=ToolPolicy(
            profile=agent_profile,
            allow=agent_allow or [],
            deny=agent_deny or [],
            by_provider=agent_by_provider or {},
        ) if has_agent_policy else None,
    )
    global_config = MoltbotConfig(
        agents=[agent],
        routing=RoutingConfig(defaults={"agentId": "test-agent"}),
        tools=ToolPolicy(
            profile=global_profile,
            allow=global_allow or [],
            deny=global_deny or [],
            by_provider=global_by_provider or {},
        ),
        sandbox=SandboxConfig(
            enabled=sandbox_enabled,
            denied_tools=sandbox_denied or [],
        ),
    )
    return global_config, agent


# Standard tool set used across most tests
ALL_TOOLS = [
    make_tool(n)
    for n in [
        "read", "write", "grep", "glob", "bash",
        "git_log", "git_diff", "git_status", "git_add", "git_commit",
    ]
]


def tool_names(tools: list[FunctionTool]) -> set[str]:
    """
    Extract names from a list of tools.

    Args:
        tools: Tool list.

    Returns:
        Set of tool names.
    """
    return {t.name for t in tools}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPolicyContext:
    """Tests for PolicyContext dataclass."""

    def test_defaults(self) -> None:
        """Test PolicyContext default values."""
        ctx = PolicyContext()
        assert ctx.provider == "local"
        assert ctx.parent_agent_id is None

    def test_custom_values(self) -> None:
        """Test PolicyContext with custom values."""
        ctx = PolicyContext(provider="openai", parent_agent_id="parent-1")
        assert ctx.provider == "openai"
        assert ctx.parent_agent_id == "parent-1"


class TestToolPolicyEngineNoPolicy:
    """Tests for engine with no explicit policy (all defaults)."""

    def test_no_policy_passes_all_tools(self) -> None:
        """Test that with no policy all tools pass through."""
        gc, agent = make_config()
        engine = ToolPolicyEngine(gc, agent)
        filtered = engine.filter_tools(list(ALL_TOOLS))
        assert tool_names(filtered) == tool_names(ALL_TOOLS)


class TestToolPolicyEngineProfileLayer:
    """Tests for Layer 1: Profile presets."""

    def test_profile_minimal(self) -> None:
        """Test minimal profile keeps only read-only tools."""
        gc, agent = make_config(global_profile="minimal")
        engine = ToolPolicyEngine(gc, agent)
        filtered = engine.filter_tools(list(ALL_TOOLS))
        assert tool_names(filtered) == {
            "read", "grep", "glob", "git_log", "git_diff", "git_status",
        }

    def test_profile_coding(self) -> None:
        """Test coding profile keeps dev tools."""
        gc, agent = make_config(global_profile="coding")
        engine = ToolPolicyEngine(gc, agent)
        filtered = engine.filter_tools(list(ALL_TOOLS))
        assert tool_names(filtered) == {
            "read", "write", "grep", "glob", "bash",
            "git_log", "git_diff", "git_status", "git_add", "git_commit",
        }

    def test_profile_messaging(self) -> None:
        """Test messaging profile removes all tools."""
        gc, agent = make_config(global_profile="messaging")
        engine = ToolPolicyEngine(gc, agent)
        filtered = engine.filter_tools(list(ALL_TOOLS))
        assert filtered == []

    def test_agent_profile_overrides_global(self) -> None:
        """Test that agent profile overrides global profile."""
        gc, agent = make_config(
            global_profile="coding",
            agent_profile="minimal",
        )
        engine = ToolPolicyEngine(gc, agent)
        filtered = engine.filter_tools(list(ALL_TOOLS))
        assert tool_names(filtered) == {
            "read", "grep", "glob", "git_log", "git_diff", "git_status",
        }


class TestToolPolicyEngineProviderProfileLayer:
    """Tests for Layer 2: Provider profile from global byProvider."""

    def test_provider_profile_applied(self) -> None:
        """Test provider profile from global by_provider narrows tools."""
        gc, agent = make_config(
            global_by_provider={
                "openai": ToolPolicy(profile="minimal"),
            },
        )
        engine = ToolPolicyEngine(gc, agent)
        ctx = PolicyContext(provider="openai")
        filtered = engine.filter_tools(list(ALL_TOOLS), ctx)
        assert tool_names(filtered) == {
            "read", "grep", "glob", "git_log", "git_diff", "git_status",
        }


class TestToolPolicyEngineGlobalLayer:
    """Tests for Layer 3: Global allow/deny."""

    def test_global_allow_narrows(self) -> None:
        """Test global allow keeps only matching tools."""
        gc, agent = make_config(global_allow=["read", "write"])
        engine = ToolPolicyEngine(gc, agent)
        filtered = engine.filter_tools(list(ALL_TOOLS))
        assert tool_names(filtered) == {"read", "write"}

    def test_global_deny_removes(self) -> None:
        """Test global deny removes matching tools."""
        gc, agent = make_config(global_deny=["write"])
        engine = ToolPolicyEngine(gc, agent)
        filtered = engine.filter_tools(list(ALL_TOOLS))
        expected = tool_names(ALL_TOOLS) - {"write"}
        assert tool_names(filtered) == expected


class TestToolPolicyEngineGlobalProviderLayer:
    """Tests for Layer 4: Global + Provider allow/deny."""

    def test_global_provider_deny_removes(self) -> None:
        """Test global by_provider deny removes additional tools."""
        gc, agent = make_config(
            global_by_provider={
                "openai": ToolPolicy(deny=["bash"]),
            },
        )
        engine = ToolPolicyEngine(gc, agent)
        ctx = PolicyContext(provider="openai")
        filtered = engine.filter_tools(list(ALL_TOOLS), ctx)
        expected = tool_names(ALL_TOOLS) - {"bash"}
        assert tool_names(filtered) == expected


class TestToolPolicyEngineAgentLayer:
    """Tests for Layer 5: Agent allow/deny."""

    def test_agent_allow_narrows(self) -> None:
        """Test agent allow further narrows the tool set."""
        gc, agent = make_config(agent_allow=["read", "grep"])
        engine = ToolPolicyEngine(gc, agent)
        filtered = engine.filter_tools(list(ALL_TOOLS))
        assert tool_names(filtered) == {"read", "grep"}


class TestToolPolicyEngineAgentProviderLayer:
    """Tests for Layer 6: Agent + Provider allow/deny."""

    def test_agent_provider_deny_narrows(self) -> None:
        """Test agent by_provider deny further narrows the tool set."""
        gc, agent = make_config(
            agent_allow=["read", "grep", "glob"],
            agent_by_provider={
                "openai": ToolPolicy(deny=["glob"]),
            },
        )
        engine = ToolPolicyEngine(gc, agent)
        ctx = PolicyContext(provider="openai")
        filtered = engine.filter_tools(list(ALL_TOOLS), ctx)
        assert tool_names(filtered) == {"read", "grep"}


class TestToolPolicyEngineSandboxLayer:
    """Tests for Layer 8: Sandbox restrictions."""

    def test_sandbox_enabled_removes_denied(self) -> None:
        """Test sandbox removes denied tools when enabled."""
        gc, agent = make_config(
            sandbox_enabled=True,
            sandbox_denied=["bash", "write"],
        )
        engine = ToolPolicyEngine(gc, agent)
        filtered = engine.filter_tools(list(ALL_TOOLS))
        expected = tool_names(ALL_TOOLS) - {"bash", "write"}
        assert tool_names(filtered) == expected

    def test_sandbox_disabled_no_effect(self) -> None:
        """Test sandbox has no effect when disabled."""
        gc, agent = make_config(
            sandbox_enabled=False,
            sandbox_denied=["bash", "write"],
        )
        engine = ToolPolicyEngine(gc, agent)
        filtered = engine.filter_tools(list(ALL_TOOLS))
        assert tool_names(filtered) == tool_names(ALL_TOOLS)


class TestToolPolicyEngineSubagentLayer:
    """Tests for Layer 9: Subagent restrictions."""

    def test_subagent_removes_write_tools(self) -> None:
        """Test subagent context removes write/bash/git_add/git_commit."""
        gc, agent = make_config()
        engine = ToolPolicyEngine(gc, agent)
        ctx = PolicyContext(provider="openai", parent_agent_id="parent-1")
        filtered = engine.filter_tools(list(ALL_TOOLS), ctx)
        expected = tool_names(ALL_TOOLS) - {
            "write", "bash", "git_add", "git_commit",
        }
        assert tool_names(filtered) == expected

    def test_subagent_empty_deny_list_passes_all(self) -> None:
        """Test subagent with empty denied list passes all tools through."""
        agent = AgentConfig(
            id="test-agent", name="Test", model="gpt-4o-mini",
        )
        gc = MoltbotConfig(
            agents=[agent],
            routing=RoutingConfig(defaults={"agentId": "test-agent"}),
            tools=ToolPolicy(),
            sandbox=SandboxConfig(subagent_denied_tools=[]),
        )
        engine = ToolPolicyEngine(gc, agent)
        ctx = PolicyContext(provider="openai", parent_agent_id="parent-1")
        filtered = engine.filter_tools(list(ALL_TOOLS), ctx)
        assert tool_names(filtered) == tool_names(ALL_TOOLS)


class TestToolPolicyEngineCascading:
    """Tests for cascading multiple layers together."""

    def test_cascading_layers_narrow_progressively(self) -> None:
        """Test multiple layers applied in order, each narrowing."""
        gc, agent = make_config(
            global_profile="full",         # Layer 1: allow all
            global_deny=["git_commit"],    # Layer 3: remove git_commit
            agent_deny=["bash"],           # Layer 5: remove bash
            sandbox_enabled=True,
            sandbox_denied=["write"],      # Layer 8: remove write
        )
        engine = ToolPolicyEngine(gc, agent)
        filtered = engine.filter_tools(list(ALL_TOOLS))
        expected = tool_names(ALL_TOOLS) - {"git_commit", "bash", "write"}
        assert tool_names(filtered) == expected

    def test_deny_always_wins_over_allow(self) -> None:
        """Test deny takes precedence when both allow and deny match a tool."""
        gc, agent = make_config(
            global_allow=["read", "write"],
            global_deny=["write"],
        )
        engine = ToolPolicyEngine(gc, agent)
        filtered = engine.filter_tools(list(ALL_TOOLS))
        assert tool_names(filtered) == {"read"}

    def test_empty_allow_means_allow_all(self) -> None:
        """Test that empty allow list means everything passes allow filter."""
        gc, agent = make_config(global_allow=[])
        engine = ToolPolicyEngine(gc, agent)
        filtered = engine.filter_tools(list(ALL_TOOLS))
        assert tool_names(filtered) == tool_names(ALL_TOOLS)


class TestToolPolicyEngineContextDefaults:
    """Tests for PolicyContext default behavior."""

    def test_none_context_uses_detected_provider(self) -> None:
        """Test that context=None creates default context with detected provider."""
        gc, agent = make_config()
        engine = ToolPolicyEngine(gc, agent)
        # gpt-4o-mini -> openai
        assert engine.provider == "openai"
        # filter_tools with None context should still work
        filtered = engine.filter_tools(list(ALL_TOOLS), context=None)
        assert tool_names(filtered) == tool_names(ALL_TOOLS)

    def test_provider_auto_detected_from_model(self) -> None:
        """Test that provider is auto-detected from agent model."""
        agent = AgentConfig(
            id="claude-agent", name="Claude", model="claude-3-sonnet",
        )
        gc = MoltbotConfig(
            agents=[agent],
            routing=RoutingConfig(defaults={"agentId": "claude-agent"}),
            tools=ToolPolicy(),
            sandbox=SandboxConfig(),
        )
        engine = ToolPolicyEngine(gc, agent)
        assert engine.provider == "anthropic"
