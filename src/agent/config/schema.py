"""
Configuration Schema for Agent System

This module defines the complete configuration schema using dataclasses.
All configuration is loaded from YAML files and validated at runtime.

Confidence: High - Schema matches Moltbot architecture exactly
"""

from dataclasses import dataclass, field
from typing import Any

_VALID_MCP_TRANSPORTS = {"stdio", "http", "websocket"}
_VALID_MCP_APPROVAL_MODES = {"always_require", "never_require"}


@dataclass
class MCPServerConfig:
    """
    Configuration for an MCP (Model Context Protocol) server.

    Attributes:
        name: Unique identifier for the server.
        transport: Connection type ("stdio", "http", or "websocket").
        command: Executable for stdio transport.
        args: Command-line arguments for stdio transport.
        url: Endpoint URL for http/websocket transport.
        env: Environment variables passed to stdio process.
        headers: HTTP headers for http/websocket transport.
        allowed_tools: Whitelist of tool names (None = all tools exposed).
        approval_mode: Default approval for all tools from this server.
        tool_approvals: Per-tool approval overrides.
        request_timeout: Request timeout in seconds.
    """

    name: str
    transport: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    allowed_tools: list[str] | None = None
    approval_mode: str | None = None
    tool_approvals: dict[str, str] = field(default_factory=dict)
    request_timeout: int | None = None

    def __post_init__(self) -> None:
        """
        Validate MCP server config after initialization.

        Raises:
            ValueError: If name is empty, transport is invalid,
                or required fields for transport are missing.
        """
        if not self.name or not self.name.strip():
            raise ValueError("MCP server name cannot be empty")

        if self.transport not in _VALID_MCP_TRANSPORTS:
            raise ValueError(
                f"Invalid MCP transport '{self.transport}'. "
                f"Must be: {', '.join(sorted(_VALID_MCP_TRANSPORTS))}"
            )

        if self.transport == "stdio" and not self.command:
            raise ValueError(
                f"MCP server '{self.name}': stdio transport requires 'command'"
            )

        if self.transport in {"http", "websocket"} and not self.url:
            raise ValueError(
                f"MCP server '{self.name}': {self.transport} transport requires 'url'"
            )

        if self.approval_mode is not None and self.approval_mode not in _VALID_MCP_APPROVAL_MODES:
            raise ValueError(
                f"Invalid MCP approval_mode '{self.approval_mode}'. "
                f"Must be: {', '.join(sorted(_VALID_MCP_APPROVAL_MODES))}"
            )


@dataclass
class ToolPolicy:
    """
    Tool access policy with cascading filters.

    Attributes:
        profile: Named preset (minimal/coding/messaging/full)
        allow: List of allowed tool patterns (wildcards supported)
        deny: List of denied tool patterns (takes precedence)
        by_provider: Provider-specific overrides (anthropic, openai, etc.)
    """

    profile: str | None = None
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)
    by_provider: dict[str, "ToolPolicy"] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """
        Validate tool policy after initialization.

        Raises:
            ValueError: If profile is not a valid preset name.
        """
        if self.profile and self.profile not in {
            "minimal",
            "coding",
            "messaging",
            "full",
        }:
            raise ValueError(
                f"Invalid profile '{self.profile}'. "
                f"Must be: minimal, coding, messaging, or full"
            )


@dataclass
class AgentConfig:
    """
    Configuration for a single agent.

    Attributes:
        id: Unique agent identifier
        name: Human-readable agent name
        model: Model identifier (e.g., "gpt-4o-mini")
        instructions: System prompt for agent
        tools: Tool access policy (optional)
        dm_scope: Session isolation scope
        mcp_servers: List of MCP server names this agent uses
    """

    id: str
    name: str
    model: str
    instructions: str | None = None
    tools: ToolPolicy | None = None
    dm_scope: str = "per-peer"  # main, per-peer, per-channel-peer
    mcp_servers: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """
        Validate agent config after initialization.

        Raises:
            ValueError: If dm_scope is not a valid scope.
        """
        if self.dm_scope not in {
            "main",
            "per-peer",
            "per-channel-peer",
            "per-account-channel-peer",
        }:
            raise ValueError(
                f"Invalid dm_scope '{self.dm_scope}'. "
                f"Must be: main, per-peer, per-channel-peer, or per-account-channel-peer"
            )


@dataclass
class RouteBindingConfig:
    """
    Routing rule for agent selection.

    Attributes:
        match: Match criteria (channel, accountId, peer, guildId, teamId)
        agent_id: Target agent ID
    """

    match: dict[str, Any]
    agent_id: str

    def __post_init__(self) -> None:
        """
        Validate route binding after initialization.

        Raises:
            ValueError: If agent_id is empty.
        """
        if not self.agent_id:
            raise ValueError("agent_id cannot be empty")


@dataclass
class IntentFallbackConfig:
    """
    Configuration for LLM-based intent classification fallback.

    When no routing binding matches, the system can optionally use
    an LLM to classify the user's intent and select an agent.

    Attributes:
        enabled: Whether intent fallback is active.
        model: LLM model identifier for classification.
    """

    enabled: bool = False
    model: str = "gpt-4o-mini"

    def __post_init__(self) -> None:
        """
        Validate intent fallback config.

        Raises:
            ValueError: If model is empty when enabled.
        """
        if self.enabled and not self.model:
            raise ValueError(
                "Intent fallback model cannot be empty when enabled"
            )


@dataclass
class RoutingConfig:
    """
    Complete routing configuration.

    Attributes:
        defaults: Default routing (e.g., {"agentId": "assistant"})
        bindings: List of routing rules
        intent_fallback: Optional LLM intent classification config
    """

    defaults: dict[str, str]
    bindings: list[RouteBindingConfig] = field(default_factory=list)
    intent_fallback: IntentFallbackConfig = field(
        default_factory=IntentFallbackConfig
    )

    def __post_init__(self) -> None:
        """
        Validate routing config after initialization.

        Raises:
            ValueError: If defaults is missing 'agentId' key.
        """
        if "agentId" not in self.defaults:
            raise ValueError("defaults must contain 'agentId' key")


@dataclass
class ToolApprovalConfig:
    """
    Configuration for tool approval overrides.

    Allows config-level overrides of hardcoded approval defaults.
    For example, skip approval for ``write`` in a trusted agent,
    or require approval for a normally safe tool.

    Attributes:
        require_approval: Tool names/patterns that always require approval.
        skip_approval: Tool names/patterns that skip approval (overrides defaults).
    """

    require_approval: list[str] = field(default_factory=list)
    skip_approval: list[str] = field(default_factory=list)


@dataclass
class PathRestrictionConfig:
    """
    Configuration for path-based access restrictions.

    When enabled, tools that operate on file paths are checked
    against allowed/denied path lists via PathRestrictionMiddleware.

    Attributes:
        enabled: Whether path restrictions are active.
        allowed_paths: If set, paths must be under one of these directories.
        denied_paths: Paths under these directories are always blocked.
    """

    enabled: bool = False
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=list)


@dataclass
class SandboxConfig:
    """
    Sandbox configuration for tool execution.

    Attributes:
        enabled: Whether sandboxing is enabled
        safe_bins: Whitelist of allowed executables
        path_prepend: PATH prefix for sandboxed execution
        denied_tools: List of tools denied in sandbox
        subagent_denied_tools: Tools denied for sub-agents (configurable)
        path_restriction: Path-based access restriction config.
    """

    enabled: bool = False
    safe_bins: list[str] = field(default_factory=list)
    path_prepend: str | None = None
    denied_tools: list[str] = field(default_factory=list)
    subagent_denied_tools: list[str] = field(
        default_factory=lambda: ["write", "bash", "git_add", "git_commit"]
    )
    path_restriction: PathRestrictionConfig = field(
        default_factory=PathRestrictionConfig
    )


@dataclass
class SessionConfig:
    """
    Configuration for session persistence.

    Attributes:
        sessions_dir: Directory path for storing JSONL session files.
        max_messages: Maximum messages per session (None = unlimited).
    """

    sessions_dir: str = "data/sessions"
    max_messages: int | None = None

    def __post_init__(self) -> None:
        """
        Validate session config.

        Raises:
            ValueError: If sessions_dir is empty or max_messages is negative.
        """
        if not self.sessions_dir or not self.sessions_dir.strip():
            raise ValueError("sessions_dir cannot be empty")
        if self.max_messages is not None and self.max_messages < 0:
            raise ValueError("max_messages cannot be negative")


@dataclass
class MoltbotConfig:
    """
    Root configuration for entire agent system.

    This is the top-level configuration object loaded from YAML.
    It contains all agent definitions, routing rules, tool policies, and sandbox settings.

    Attributes:
        agents: List of configured agents
        routing: Routing configuration
        tools: Global tool policy
        sandbox: Sandbox configuration
        session: Session persistence configuration
        approval: Tool approval override configuration
        mcp_servers: Global MCP server definitions
    """

    agents: list[AgentConfig]
    routing: RoutingConfig
    tools: ToolPolicy
    sandbox: SandboxConfig
    session: SessionConfig = field(default_factory=SessionConfig)
    approval: ToolApprovalConfig = field(default_factory=ToolApprovalConfig)
    mcp_servers: list[MCPServerConfig] = field(default_factory=list)

    def __post_init__(self) -> None:
        """
        Validate complete config after initialization.

        Raises:
            ValueError: If agents list is empty, IDs are duplicated,
                routing references invalid agent IDs, MCP server names
                are duplicated, or agents reference nonexistent MCP servers.
        """
        if not self.agents:
            raise ValueError("At least one agent must be defined")

        # Validate all agent IDs are unique
        agent_ids = [agent.id for agent in self.agents]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("Agent IDs must be unique")

        # Validate routing references valid agents
        referenced_agents = {binding.agent_id for binding in self.routing.bindings}
        referenced_agents.add(self.routing.defaults["agentId"])

        valid_agent_ids = set(agent_ids)
        invalid_refs = referenced_agents - valid_agent_ids

        if invalid_refs:
            raise ValueError(
                f"Routing references invalid agent IDs: {invalid_refs}. "
                f"Valid IDs: {valid_agent_ids}"
            )

        # Validate MCP server names are unique
        mcp_names = [s.name for s in self.mcp_servers]
        if len(mcp_names) != len(set(mcp_names)):
            raise ValueError("MCP server names must be unique")

        # Validate agent MCP server references
        valid_mcp_names = set(mcp_names)
        for agent in self.agents:
            invalid_mcp_refs = set(agent.mcp_servers) - valid_mcp_names
            if invalid_mcp_refs:
                raise ValueError(
                    f"Agent '{agent.id}' references nonexistent MCP servers: "
                    f"{invalid_mcp_refs}. Valid servers: {valid_mcp_names}"
                )

    def get_agent(self, agent_id: str) -> AgentConfig | None:
        """
        Get agent configuration by ID.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent configuration or None if not found
        """
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        return None
