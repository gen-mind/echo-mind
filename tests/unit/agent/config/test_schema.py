"""
Unit tests for configuration schema.

Tests cover all data classes, validation logic, and error cases.
Target: 100% code coverage
"""

import pytest

from src.agent.config.schema import (
    AgentConfig,
    IntentFallbackConfig,
    MCPServerConfig,
    MoltbotConfig,
    PathRestrictionConfig,
    RouteBindingConfig,
    RoutingConfig,
    SandboxConfig,
    ToolApprovalConfig,
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


class TestIntentFallbackConfig:
    """Tests for IntentFallbackConfig dataclass."""

    def test_default_values(self):
        """Test default intent fallback config."""
        config = IntentFallbackConfig()
        assert config.enabled is False
        assert config.model == "gpt-4o-mini"

    def test_enabled_with_model(self):
        """Test enabled intent fallback with custom model."""
        config = IntentFallbackConfig(enabled=True, model="claude-3-haiku")
        assert config.enabled is True
        assert config.model == "claude-3-haiku"

    def test_enabled_empty_model_raises(self):
        """Test that enabled with empty model raises ValueError."""
        with pytest.raises(ValueError, match="model cannot be empty"):
            IntentFallbackConfig(enabled=True, model="")

    def test_disabled_empty_model_ok(self):
        """Test that disabled with empty model is allowed."""
        config = IntentFallbackConfig(enabled=False, model="")
        assert config.enabled is False


class TestRoutingConfig:
    """Tests for RoutingConfig dataclass."""

    def test_minimal_routing(self):
        """Test minimal routing config."""
        config = RoutingConfig(defaults={"agentId": "assistant"})
        assert config.defaults == {"agentId": "assistant"}
        assert config.bindings == []
        assert config.intent_fallback.enabled is False

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


class TestToolApprovalConfig:
    """Tests for ToolApprovalConfig dataclass."""

    def test_default_values(self):
        """Test default approval config."""
        config = ToolApprovalConfig()
        assert config.require_approval == []
        assert config.skip_approval == []

    def test_with_patterns(self):
        """Test approval config with patterns."""
        config = ToolApprovalConfig(
            require_approval=["write", "bash", "git_*"],
            skip_approval=["read", "grep"],
        )
        assert config.require_approval == ["write", "bash", "git_*"]
        assert config.skip_approval == ["read", "grep"]


class TestPathRestrictionConfig:
    """Tests for PathRestrictionConfig dataclass."""

    def test_default_values(self):
        """Test default path restriction config."""
        config = PathRestrictionConfig()
        assert config.enabled is False
        assert config.allowed_paths == []
        assert config.denied_paths == []

    def test_enabled_with_paths(self):
        """Test path restriction with paths configured."""
        config = PathRestrictionConfig(
            enabled=True,
            allowed_paths=["/project", "/tmp"],
            denied_paths=["/etc", "/root", "~/.ssh"],
        )
        assert config.enabled is True
        assert config.allowed_paths == ["/project", "/tmp"]
        assert config.denied_paths == ["/etc", "/root", "~/.ssh"]


class TestSandboxConfig:
    """Tests for SandboxConfig dataclass."""

    def test_default_values(self):
        """Test default sandbox config."""
        config = SandboxConfig()
        assert config.enabled is False
        assert config.safe_bins == []
        assert config.path_prepend is None
        assert config.denied_tools == []
        assert isinstance(config.path_restriction, PathRestrictionConfig)
        assert config.path_restriction.enabled is False

    def test_all_fields(self):
        """Test all sandbox fields."""
        config = SandboxConfig(
            enabled=True,
            safe_bins=["git", "ls"],
            path_prepend="/usr/bin",
            denied_tools=["exec"],
            path_restriction=PathRestrictionConfig(
                enabled=True,
                allowed_paths=["/project"],
                denied_paths=["/etc"],
            ),
        )
        assert config.enabled is True
        assert config.safe_bins == ["git", "ls"]
        assert config.path_prepend == "/usr/bin"
        assert config.denied_tools == ["exec"]
        assert config.path_restriction.enabled is True
        assert config.path_restriction.allowed_paths == ["/project"]


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
        # Defaults
        assert isinstance(config.approval, ToolApprovalConfig)
        assert config.approval.require_approval == []
        assert config.approval.skip_approval == []

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

    def test_mcp_server_duplicate_names_raises(self):
        """Test that duplicate MCP server names raise ValueError."""
        with pytest.raises(ValueError, match="MCP server names must be unique"):
            MoltbotConfig(
                agents=[
                    AgentConfig(id="a1", name="A1", model="gpt-4o-mini"),
                ],
                routing=RoutingConfig(defaults={"agentId": "a1"}),
                tools=ToolPolicy(),
                sandbox=SandboxConfig(),
                mcp_servers=[
                    MCPServerConfig(name="fs", transport="stdio", command="echo"),
                    MCPServerConfig(name="fs", transport="http", url="https://x"),
                ],
            )

    def test_agent_references_nonexistent_mcp_server(self):
        """Test that agent referencing nonexistent MCP server raises ValueError."""
        with pytest.raises(ValueError, match="references nonexistent MCP servers"):
            MoltbotConfig(
                agents=[
                    AgentConfig(
                        id="a1", name="A1", model="gpt-4o-mini",
                        mcp_servers=["doesnt_exist"],
                    ),
                ],
                routing=RoutingConfig(defaults={"agentId": "a1"}),
                tools=ToolPolicy(),
                sandbox=SandboxConfig(),
                mcp_servers=[
                    MCPServerConfig(name="fs", transport="stdio", command="echo"),
                ],
            )

    def test_valid_mcp_server_references(self):
        """Test that valid MCP server references pass validation."""
        config = MoltbotConfig(
            agents=[
                AgentConfig(
                    id="a1", name="A1", model="gpt-4o-mini",
                    mcp_servers=["fs", "github"],
                ),
                AgentConfig(id="a2", name="A2", model="gpt-4o-mini"),
            ],
            routing=RoutingConfig(defaults={"agentId": "a1"}),
            tools=ToolPolicy(),
            sandbox=SandboxConfig(),
            mcp_servers=[
                MCPServerConfig(name="fs", transport="stdio", command="echo"),
                MCPServerConfig(name="github", transport="http", url="https://x"),
            ],
        )
        assert len(config.mcp_servers) == 2


class TestMCPServerConfig:
    """Tests for MCPServerConfig dataclass."""

    def test_valid_stdio_config(self):
        """Test valid stdio transport config."""
        config = MCPServerConfig(
            name="filesystem",
            transport="stdio",
            command="npx",
            args=["-y", "server-filesystem", "/tmp"],
            env={"NODE_ENV": "production"},
        )
        assert config.name == "filesystem"
        assert config.transport == "stdio"
        assert config.command == "npx"
        assert config.args == ["-y", "server-filesystem", "/tmp"]
        assert config.env == {"NODE_ENV": "production"}

    def test_valid_http_config(self):
        """Test valid http transport config."""
        config = MCPServerConfig(
            name="github",
            transport="http",
            url="https://mcp.example.com/github",
            headers={"Authorization": "Bearer token123"},
        )
        assert config.name == "github"
        assert config.transport == "http"
        assert config.url == "https://mcp.example.com/github"
        assert config.headers == {"Authorization": "Bearer token123"}

    def test_valid_websocket_config(self):
        """Test valid websocket transport config."""
        config = MCPServerConfig(
            name="ws-server",
            transport="websocket",
            url="wss://mcp.example.com/ws",
        )
        assert config.transport == "websocket"
        assert config.url == "wss://mcp.example.com/ws"

    def test_empty_name_raises(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            MCPServerConfig(name="", transport="stdio", command="echo")

    def test_whitespace_name_raises(self):
        """Test that whitespace-only name raises ValueError."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            MCPServerConfig(name="   ", transport="stdio", command="echo")

    def test_invalid_transport_raises(self):
        """Test that invalid transport raises ValueError."""
        with pytest.raises(ValueError, match="Invalid MCP transport"):
            MCPServerConfig(name="bad", transport="grpc", command="echo")

    def test_stdio_without_command_raises(self):
        """Test that stdio transport without command raises ValueError."""
        with pytest.raises(ValueError, match="stdio transport requires 'command'"):
            MCPServerConfig(name="bad", transport="stdio")

    def test_http_without_url_raises(self):
        """Test that http transport without url raises ValueError."""
        with pytest.raises(ValueError, match="http transport requires 'url'"):
            MCPServerConfig(name="bad", transport="http")

    def test_websocket_without_url_raises(self):
        """Test that websocket transport without url raises ValueError."""
        with pytest.raises(ValueError, match="websocket transport requires 'url'"):
            MCPServerConfig(name="bad", transport="websocket")

    def test_invalid_approval_mode_raises(self):
        """Test that invalid approval_mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid MCP approval_mode"):
            MCPServerConfig(
                name="bad", transport="stdio", command="echo",
                approval_mode="auto",
            )

    def test_valid_approval_modes(self):
        """Test that valid approval modes are accepted."""
        for mode in ["always_require", "never_require"]:
            config = MCPServerConfig(
                name="test", transport="stdio", command="echo",
                approval_mode=mode,
            )
            assert config.approval_mode == mode

    def test_none_approval_mode_ok(self):
        """Test that None approval_mode is accepted."""
        config = MCPServerConfig(name="test", transport="stdio", command="echo")
        assert config.approval_mode is None

    def test_default_values(self):
        """Test default values for optional fields."""
        config = MCPServerConfig(name="test", transport="stdio", command="echo")
        assert config.args == []
        assert config.url is None
        assert config.env == {}
        assert config.headers == {}
        assert config.allowed_tools is None
        assert config.tool_approvals == {}
        assert config.request_timeout is None

    def test_with_allowed_tools_and_tool_approvals(self):
        """Test config with allowed_tools and per-tool approvals."""
        config = MCPServerConfig(
            name="test",
            transport="stdio",
            command="echo",
            allowed_tools=["read_file", "list_dir"],
            tool_approvals={"delete_file": "always_require"},
            request_timeout=30,
        )
        assert config.allowed_tools == ["read_file", "list_dir"]
        assert config.tool_approvals == {"delete_file": "always_require"}
        assert config.request_timeout == 30
