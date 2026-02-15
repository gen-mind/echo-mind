"""
Configuration Schema for Agent System

This module defines the complete configuration schema using dataclasses.
All configuration is loaded from YAML files and validated at runtime.

Confidence: High - Schema matches Moltbot architecture exactly
"""

from dataclasses import dataclass, field
from typing import Any


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
    """

    id: str
    name: str
    model: str
    instructions: str | None = None
    tools: ToolPolicy | None = None
    dm_scope: str = "per-peer"  # main, per-peer, per-channel-peer

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
class RoutingConfig:
    """
    Complete routing configuration.

    Attributes:
        defaults: Default routing (e.g., {"agentId": "assistant"})
        bindings: List of routing rules
    """

    defaults: dict[str, str]
    bindings: list[RouteBindingConfig] = field(default_factory=list)

    def __post_init__(self) -> None:
        """
        Validate routing config after initialization.

        Raises:
            ValueError: If defaults is missing 'agentId' key.
        """
        if "agentId" not in self.defaults:
            raise ValueError("defaults must contain 'agentId' key")


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
    """

    enabled: bool = False
    safe_bins: list[str] = field(default_factory=list)
    path_prepend: str | None = None
    denied_tools: list[str] = field(default_factory=list)
    subagent_denied_tools: list[str] = field(
        default_factory=lambda: ["write", "bash", "git_add", "git_commit"]
    )


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
    """

    agents: list[AgentConfig]
    routing: RoutingConfig
    tools: ToolPolicy
    sandbox: SandboxConfig

    def __post_init__(self) -> None:
        """
        Validate complete config after initialization.

        Raises:
            ValueError: If agents list is empty, IDs are duplicated,
                or routing references invalid agent IDs.
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
