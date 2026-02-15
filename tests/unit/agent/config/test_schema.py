"""
Unit tests for configuration schema.

Tests cover all data classes, validation logic, and error cases.
Target: 100% code coverage
"""

import pytest

from src.agent.config.schema import (
    AgentConfig,
    MoltbotConfig,
    RouteBindingConfig,
    RoutingConfig,
    SandboxConfig,
    ToolPolicy,
)


class TestToolPolicy:
    """Tests for ToolPolicy dataclass."""

    def test_valid_profiles(self):
        """Test that valid profiles are accepted."""
        for profile in ["minimal", "coding", "messaging", "full"]:
            policy = ToolPolicy(profile=profile)
            assert policy.profile == profile

    def test_invalid_profile_raises_error(self):
        """Test that invalid profile raises ValueError."""
        with pytest.raises(ValueError, match="Invalid profile"):
            ToolPolicy(profile="invalid")

    def test_default_values(self):
        """Test default values."""
        policy = ToolPolicy()
        assert policy.profile is None
        assert policy.allow == []
        assert policy.deny == []
        assert policy.by_provider == {}

    def test_nested_policies(self):
        """Test nested provider policies."""
        policy = ToolPolicy(
            profile="full",
            by_provider={
                "anthropic": ToolPolicy(deny=["sessions_spawn"]),
                "openai": ToolPolicy(allow=["*"]),
            },
        )
        assert "anthropic" in policy.by_provider
        assert policy.by_provider["anthropic"].deny == ["sessions_spawn"]


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""

    def test_minimal_config(self):
        """Test minimal valid config."""
        config = AgentConfig(
            id="test",
            name="Test Agent",
            model="gpt-4o-mini",
        )
        assert config.id == "test"
        assert config.name == "Test Agent"
        assert config.model == "gpt-4o-mini"
        assert config.dm_scope == "per-peer"  # default

    def test_all_fields(self):
        """Test all fields populated."""
        config = AgentConfig(
            id="test",
            name="Test Agent",
            model="gpt-4o-mini",
            instructions="You are helpful",
            tools=ToolPolicy(profile="full"),
            dm_scope="main",
        )
        assert config.instructions == "You are helpful"
        assert config.tools.profile == "full"
        assert config.dm_scope == "main"

    def test_valid_dm_scopes(self):
        """Test that valid dm_scope values are accepted."""
        for scope in ["main", "per-peer", "per-channel-peer", "per-account-channel-peer"]:
            config = AgentConfig(id="test", name="Test", model="gpt-4o-mini", dm_scope=scope)
            assert config.dm_scope == scope

    def test_invalid_dm_scope_raises_error(self):
        """Test that invalid dm_scope raises ValueError."""
        with pytest.raises(ValueError, match="Invalid dm_scope"):
            AgentConfig(id="test", name="Test", model="gpt-4o-mini", dm_scope="invalid")


class TestRouteBindingConfig:
    """Tests for RouteBindingConfig dataclass."""

    def test_valid_binding(self):
        """Test valid route binding."""
        binding = RouteBindingConfig(
            match={"channel": "test"},
            agent_id="assistant",
        )
        assert binding.match == {"channel": "test"}
        assert binding.agent_id == "assistant"

    def test_empty_agent_id_raises_error(self):
        """Test that empty agent_id raises ValueError."""
        with pytest.raises(ValueError, match="agent_id cannot be empty"):
            RouteBindingConfig(match={"channel": "test"}, agent_id="")


class TestRoutingConfig:
    """Tests for RoutingConfig dataclass."""

    def test_minimal_routing(self):
        """Test minimal routing config."""
        config = RoutingConfig(defaults={"agentId": "assistant"})
        assert config.defaults == {"agentId": "assistant"}
        assert config.bindings == []

    def test_with_bindings(self):
        """Test routing with bindings."""
        config = RoutingConfig(
            defaults={"agentId": "assistant"},
            bindings=[
                RouteBindingConfig(match={"channel": "test"}, agent_id="coder")
            ],
        )
        assert len(config.bindings) == 1
        assert config.bindings[0].agent_id == "coder"

    def test_missing_agentId_raises_error(self):
        """Test that missing agentId in defaults raises ValueError."""
        with pytest.raises(ValueError, match="defaults must contain 'agentId' key"):
            RoutingConfig(defaults={})


class TestSandboxConfig:
    """Tests for SandboxConfig dataclass."""

    def test_default_values(self):
        """Test default sandbox config."""
        config = SandboxConfig()
        assert config.enabled is False
        assert config.safe_bins == []
        assert config.path_prepend is None
        assert config.denied_tools == []

    def test_all_fields(self):
        """Test all sandbox fields."""
        config = SandboxConfig(
            enabled=True,
            safe_bins=["git", "ls"],
            path_prepend="/usr/bin",
            denied_tools=["exec"],
        )
        assert config.enabled is True
        assert config.safe_bins == ["git", "ls"]
        assert config.path_prepend == "/usr/bin"
        assert config.denied_tools == ["exec"]


class TestMoltbotConfig:
    """Tests for MoltbotConfig dataclass."""

    def test_minimal_config(self):
        """Test minimal valid config."""
        config = MoltbotConfig(
            agents=[
                AgentConfig(id="assistant", name="Assistant", model="gpt-4o-mini")
            ],
            routing=RoutingConfig(defaults={"agentId": "assistant"}),
            tools=ToolPolicy(),
            sandbox=SandboxConfig(),
        )
        assert len(config.agents) == 1
        assert config.routing.defaults["agentId"] == "assistant"

    def test_empty_agents_raises_error(self):
        """Test that empty agents list raises ValueError."""
        with pytest.raises(ValueError, match="At least one agent must be defined"):
            MoltbotConfig(
                agents=[],
                routing=RoutingConfig(defaults={"agentId": "assistant"}),
                tools=ToolPolicy(),
                sandbox=SandboxConfig(),
            )

    def test_duplicate_agent_ids_raises_error(self):
        """Test that duplicate agent IDs raise ValueError."""
        with pytest.raises(ValueError, match="Agent IDs must be unique"):
            MoltbotConfig(
                agents=[
                    AgentConfig(id="agent1", name="A1", model="gpt-4o-mini"),
                    AgentConfig(id="agent1", name="A2", model="gpt-4o-mini"),
                ],
                routing=RoutingConfig(defaults={"agentId": "agent1"}),
                tools=ToolPolicy(),
                sandbox=SandboxConfig(),
            )

    def test_invalid_agent_reference_raises_error(self):
        """Test that routing references to non-existent agents raise ValueError."""
        with pytest.raises(ValueError, match="Routing references invalid agent IDs"):
            MoltbotConfig(
                agents=[
                    AgentConfig(id="agent1", name="A1", model="gpt-4o-mini"),
                ],
                routing=RoutingConfig(
                    defaults={"agentId": "nonexistent"}  # Invalid reference
                ),
                tools=ToolPolicy(),
                sandbox=SandboxConfig(),
            )

    def test_get_agent_by_id(self):
        """Test get_agent method."""
        config = MoltbotConfig(
            agents=[
                AgentConfig(id="agent1", name="A1", model="gpt-4o-mini"),
                AgentConfig(id="agent2", name="A2", model="gpt-4o-mini"),
            ],
            routing=RoutingConfig(defaults={"agentId": "agent1"}),
            tools=ToolPolicy(),
            sandbox=SandboxConfig(),
        )

        agent = config.get_agent("agent1")
        assert agent is not None
        assert agent.id == "agent1"

        # Test non-existent agent
        assert config.get_agent("nonexistent") is None
