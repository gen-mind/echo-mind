"""
Integration tests for the 8-layer tool policy system.

These tests verify the policy engine integrates correctly with
the agent wrapper and config parser, using real config files.

Run with: PYTHONPATH=src python -m pytest tests/integration/agent/test_policy_integration.py -v
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.agent import AgentFactory, BasicAgentWrapper
from agent.config.parser import ConfigParser
from agent.config.schema import (
    AgentConfig,
    MoltbotConfig,
    RoutingConfig,
    SandboxConfig,
    ToolPolicy,
)
from agent.policy.engine import PolicyContext, ToolPolicyEngine


@pytest.fixture(scope="module")
def config_path() -> str:
    """Path to agent config YAML."""
    path = Path(__file__).resolve().parents[3] / "config" / "agents" / "config.yaml"
    assert path.exists(), f"Config not found: {path}"
    return str(path)


@pytest.fixture(scope="module")
def moltbot_config(config_path: str) -> MoltbotConfig:
    """Load full MoltbotConfig from YAML."""
    return ConfigParser(config_path).load()


class TestConfigLoadsPolicy:
    """Test that config.yaml loads tool policies correctly."""

    def test_global_tool_policy_loaded(self, moltbot_config: MoltbotConfig) -> None:
        """Global tool policy should have profile, allow, deny."""
        tools = moltbot_config.tools
        assert tools.profile == "full"
        assert "*" in tools.allow
        assert "system_*" in tools.deny
        assert "admin_*" in tools.deny

    def test_global_by_provider_loaded(self, moltbot_config: MoltbotConfig) -> None:
        """Global byProvider should have anthropic deny."""
        anthropic = moltbot_config.tools.by_provider.get("anthropic")
        assert anthropic is not None
        assert "sessions_spawn" in anthropic.deny

    def test_assistant_agent_has_full_profile(self, moltbot_config: MoltbotConfig) -> None:
        """Assistant agent should have full profile."""
        assistant = moltbot_config.get_agent("assistant")
        assert assistant is not None
        assert assistant.tools is not None
        assert assistant.tools.profile == "full"

    def test_coder_agent_has_coding_profile(self, moltbot_config: MoltbotConfig) -> None:
        """Coder agent should have coding profile with specific allows."""
        coder = moltbot_config.get_agent("coder")
        assert coder is not None
        assert coder.tools is not None
        assert coder.tools.profile == "coding"
        assert "read*" in coder.tools.allow
        assert "git_*" in coder.tools.allow

    def test_researcher_agent_has_minimal_profile(self, moltbot_config: MoltbotConfig) -> None:
        """Researcher agent should have minimal profile (read-only)."""
        researcher = moltbot_config.get_agent("researcher")
        assert researcher is not None
        assert researcher.tools is not None
        assert researcher.tools.profile == "minimal"

    def test_three_agents_defined(self, moltbot_config: MoltbotConfig) -> None:
        """Config should define 3 agents."""
        assert len(moltbot_config.agents) == 3
        ids = {a.id for a in moltbot_config.agents}
        assert ids == {"assistant", "coder", "researcher"}


class TestPolicyEngineWithRealConfig:
    """Test ToolPolicyEngine with real config.yaml values."""

    def test_researcher_gets_read_only_tools(self, moltbot_config: MoltbotConfig) -> None:
        """Researcher (minimal profile) should only get read-only tools."""
        researcher = moltbot_config.get_agent("researcher")
        engine = ToolPolicyEngine(moltbot_config, researcher)

        # Create mock tools matching our 10 core tools
        tool_names = [
            "read", "write", "grep", "glob", "bash",
            "git_log", "git_diff", "git_status", "git_add", "git_commit",
        ]
        tools = []
        for name in tool_names:
            t = MagicMock()
            t.name = name
            tools.append(t)

        filtered = engine.filter_tools(tools)
        filtered_names = {t.name for t in filtered}

        # Minimal profile allows: read, grep, glob, git_log, git_diff, git_status
        assert "read" in filtered_names
        assert "grep" in filtered_names
        assert "glob" in filtered_names
        assert "git_log" in filtered_names
        assert "git_diff" in filtered_names
        assert "git_status" in filtered_names

        # These should be denied
        assert "write" not in filtered_names
        assert "bash" not in filtered_names
        assert "git_add" not in filtered_names
        assert "git_commit" not in filtered_names

    def test_coder_gets_coding_tools(self, moltbot_config: MoltbotConfig) -> None:
        """Coder (coding profile + explicit allow) should get dev tools."""
        coder = moltbot_config.get_agent("coder")
        engine = ToolPolicyEngine(moltbot_config, coder)

        tool_names = [
            "read", "write", "grep", "glob", "bash",
            "git_log", "git_diff", "git_status", "git_add", "git_commit",
        ]
        tools = []
        for name in tool_names:
            t = MagicMock()
            t.name = name
            tools.append(t)

        filtered = engine.filter_tools(tools)
        filtered_names = {t.name for t in filtered}

        # Coder allows: read*, write*, grep*, glob*, bash, git_*
        assert "read" in filtered_names
        assert "write" in filtered_names
        assert "bash" in filtered_names
        assert "git_commit" in filtered_names

    def test_assistant_gets_all_tools(self, moltbot_config: MoltbotConfig) -> None:
        """Assistant (full profile) should get all tools."""
        assistant = moltbot_config.get_agent("assistant")
        engine = ToolPolicyEngine(moltbot_config, assistant)

        tool_names = [
            "read", "write", "grep", "glob", "bash",
            "git_log", "git_diff", "git_status", "git_add", "git_commit",
        ]
        tools = []
        for name in tool_names:
            t = MagicMock()
            t.name = name
            tools.append(t)

        filtered = engine.filter_tools(tools)
        assert len(filtered) == 10

    def test_sandbox_denies_tools_when_enabled(self) -> None:
        """Sandbox layer should deny tools when enabled."""
        agent = AgentConfig(id="test", name="Test", model="gpt-4o-mini")
        config = MoltbotConfig(
            agents=[agent],
            routing=RoutingConfig(defaults={"agentId": "test"}),
            tools=ToolPolicy(),
            sandbox=SandboxConfig(enabled=True, denied_tools=["bash", "write"]),
        )
        engine = ToolPolicyEngine(config, agent)

        tools = []
        for name in ["read", "write", "bash", "grep"]:
            t = MagicMock()
            t.name = name
            tools.append(t)

        filtered = engine.filter_tools(tools)
        filtered_names = {t.name for t in filtered}
        assert "bash" not in filtered_names
        assert "write" not in filtered_names
        assert "read" in filtered_names
        assert "grep" in filtered_names

    def test_subagent_gets_restricted_tools(self, moltbot_config: MoltbotConfig) -> None:
        """Subagent context should restrict write/execute tools."""
        assistant = moltbot_config.get_agent("assistant")
        engine = ToolPolicyEngine(moltbot_config, assistant)

        tool_names = [
            "read", "write", "grep", "glob", "bash",
            "git_log", "git_diff", "git_status", "git_add", "git_commit",
        ]
        tools = []
        for name in tool_names:
            t = MagicMock()
            t.name = name
            tools.append(t)

        # Run as subagent
        ctx = PolicyContext(provider="openai", parent_agent_id="parent-agent")
        filtered = engine.filter_tools(tools, ctx)
        filtered_names = {t.name for t in filtered}

        # Subagent denies: write, bash, git_add, git_commit
        assert "write" not in filtered_names
        assert "bash" not in filtered_names
        assert "git_add" not in filtered_names
        assert "git_commit" not in filtered_names

        # Read-only tools should survive
        assert "read" in filtered_names
        assert "grep" in filtered_names
        assert "glob" in filtered_names


class TestAgentFactoryWithPolicy:
    """Test AgentFactory creates agents with policy middleware."""

    @patch("agent.agent.OpenAIChatClient")
    @patch("agent.agent.Agent")
    def test_factory_passes_global_config(
        self, mock_agent_cls, mock_client_cls, moltbot_config: MoltbotConfig
    ) -> None:
        """Factory should pass global_config to BasicAgentWrapper."""
        mock_client_cls.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock()

        factory = AgentFactory(
            api_key="test-key",
            global_config=moltbot_config,
        )
        assistant = moltbot_config.get_agent("assistant")
        wrapper = factory.create_agent(assistant)

        assert wrapper._policy_engine is not None
        assert wrapper.global_config is moltbot_config

    @patch("agent.agent.OpenAIChatClient")
    @patch("agent.agent.Agent")
    def test_factory_no_policy_without_global_config(
        self, mock_agent_cls, mock_client_cls
    ) -> None:
        """Factory without global_config should create agent without policy."""
        mock_client_cls.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock()

        factory = AgentFactory(api_key="test-key")
        agent_config = AgentConfig(
            id="test", name="Test", model="gpt-4o-mini"
        )
        wrapper = factory.create_agent(agent_config)

        assert wrapper._policy_engine is None

    @patch("agent.agent.OpenAIChatClient")
    @patch("agent.agent.Agent")
    def test_middleware_injected_into_agent(
        self, mock_agent_cls, mock_client_cls, moltbot_config: MoltbotConfig
    ) -> None:
        """Agent should be created with middleware when global_config provided."""
        mock_client_cls.return_value = MagicMock()
        mock_agent_cls.return_value = MagicMock()

        factory = AgentFactory(
            api_key="test-key",
            global_config=moltbot_config,
        )
        assistant = moltbot_config.get_agent("assistant")
        factory.create_agent(assistant)

        # Agent() should have been called with middleware kwarg
        call_kwargs = mock_agent_cls.call_args[1]
        assert "middleware" in call_kwargs
        assert len(call_kwargs["middleware"]) == 1
