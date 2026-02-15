"""
Tool Policy Engine — 9-layer cascading filter (Layer 7 skipped).

Applies layers in order, each narrowing the available tool set.
Deny ALWAYS takes precedence. Empty allow = allow all.
Tools can never be re-added once removed by a layer.
"""

import fnmatch
import logging
from dataclasses import dataclass, field

from agent_framework import FunctionTool

from ..config.schema import AgentConfig, MoltbotConfig, SandboxConfig, ToolPolicy
from .profiles import PROFILES
from .providers import detect_provider

logger = logging.getLogger(__name__)


@dataclass
class PolicyContext:
    """
    Runtime context for policy evaluation.

    Attributes:
        provider: Detected LLM provider name.
        parent_agent_id: ID of parent agent if this is a sub-agent.
    """

    provider: str = "local"
    parent_agent_id: str | None = None


class ToolPolicyEngine:
    """
    9-layer cascading tool policy filter (Layer 7 skipped).

    Layers:
        1. Profile (minimal/coding/messaging/full presets)
        2. Provider Profile (from global byProvider)
        3. Global Policy (config-wide allow/deny)
        4. Global + Provider (global byProvider allow/deny)
        5. Agent Policy (agent-specific allow/deny)
        6. Agent + Provider (agent byProvider allow/deny)
        7. Group/Channel (SKIPPED — not implemented)
        8. Sandbox (denied_tools enforcement)
        9. Subagent (restrict tools for spawned sub-agents)
    """

    def __init__(
        self,
        global_config: MoltbotConfig,
        agent_config: AgentConfig,
    ) -> None:
        """
        Initialize the policy engine.

        Args:
            global_config: Root configuration with global tool policy and sandbox.
            agent_config: Agent-specific configuration.
        """
        self.global_config = global_config
        self.agent_config = agent_config
        self.provider = detect_provider(agent_config.model)

        logger.info(
            f"🔒 ToolPolicyEngine initialized for agent '{agent_config.id}' "
            f"(provider={self.provider})"
        )

    def filter_tools(
        self,
        tools: list[FunctionTool],
        context: PolicyContext | None = None,
    ) -> list[FunctionTool]:
        """
        Apply all policy layers and return filtered tools.

        Args:
            tools: Full list of available tools.
            context: Runtime policy context (provider, parent agent, etc.).

        Returns:
            Filtered list of tools after all layers applied.
        """
        if context is None:
            context = PolicyContext(provider=self.provider)

        result = list(tools)
        initial_count = len(result)

        global_tools = self.global_config.tools
        agent_tools = self.agent_config.tools
        sandbox = self.global_config.sandbox

        # Layer 1: Profile preset
        profile_name = self._resolve_profile(global_tools, agent_tools)
        if profile_name and profile_name in PROFILES:
            profile = PROFILES[profile_name]
            result = self._apply_layer(
                result, profile.allow, profile.deny, "profile"
            )

        # Layer 2: Provider profile (global byProvider → profile)
        provider_policy = global_tools.by_provider.get(context.provider)
        if provider_policy and provider_policy.profile:
            pp = PROFILES.get(provider_policy.profile)
            if pp:
                result = self._apply_layer(
                    result, pp.allow, pp.deny, "provider-profile"
                )

        # Layer 3: Global policy
        result = self._apply_layer(
            result, global_tools.allow, global_tools.deny, "global"
        )

        # Layer 4: Global + Provider (global byProvider allow/deny)
        if provider_policy:
            result = self._apply_layer(
                result, provider_policy.allow, provider_policy.deny, "global+provider"
            )

        # Layer 5: Agent policy
        if agent_tools:
            result = self._apply_layer(
                result, agent_tools.allow, agent_tools.deny, "agent"
            )

        # Layer 6: Agent + Provider (agent byProvider allow/deny)
        if agent_tools:
            agent_provider_policy = agent_tools.by_provider.get(context.provider)
            if agent_provider_policy:
                result = self._apply_layer(
                    result,
                    agent_provider_policy.allow,
                    agent_provider_policy.deny,
                    "agent+provider",
                )

        # Layer 7: Group/Channel — SKIPPED (not implemented)

        # Layer 8: Sandbox
        result = self._apply_sandbox(result, sandbox)

        # Layer 9: Subagent restrictions
        if context.parent_agent_id:
            result = self._apply_subagent(result, context)

        logger.info(
            f"🔒 Policy filter: {initial_count} → {len(result)} tools "
            f"(agent={self.agent_config.id})"
        )
        return result

    def _resolve_profile(
        self,
        global_tools: ToolPolicy,
        agent_tools: ToolPolicy | None,
    ) -> str | None:
        """
        Resolve the effective profile name.

        Agent profile overrides global profile.

        Args:
            global_tools: Global tool policy.
            agent_tools: Agent-specific tool policy (may be None).

        Returns:
            Profile name or None.
        """
        if agent_tools and agent_tools.profile:
            return agent_tools.profile
        return global_tools.profile

    def _apply_layer(
        self,
        tools: list[FunctionTool],
        allow: list[str] | None,
        deny: list[str] | None,
        layer_name: str,
    ) -> list[FunctionTool]:
        """
        Apply a single layer of allow/deny filtering.

        Args:
            tools: Current tool list.
            allow: Wildcard patterns for tools to include (empty = allow all).
            deny: Wildcard patterns for tools to exclude (takes precedence).
            layer_name: Name of this layer (for logging).

        Returns:
            Filtered tool list.
        """
        before = len(tools)
        result = tools

        # Apply allow filter (empty = allow all)
        if allow:
            result = [
                t for t in result
                if any(fnmatch.fnmatch(t.name, pat) for pat in allow)
            ]

        # Apply deny filter (deny takes precedence)
        if deny:
            result = [
                t for t in result
                if not any(fnmatch.fnmatch(t.name, pat) for pat in deny)
            ]

        after = len(result)
        if before != after:
            logger.debug(
                f"  📋 Layer '{layer_name}': {before} → {after} tools "
                f"(allow={allow}, deny={deny})"
            )
        return result

    def _apply_sandbox(
        self,
        tools: list[FunctionTool],
        sandbox: SandboxConfig,
    ) -> list[FunctionTool]:
        """
        Apply sandbox restrictions.

        Args:
            tools: Current tool list.
            sandbox: Sandbox configuration.

        Returns:
            Filtered tool list with sandbox-denied tools removed.
        """
        if not sandbox.enabled or not sandbox.denied_tools:
            return tools

        before = len(tools)
        result = [
            t for t in tools
            if not any(
                fnmatch.fnmatch(t.name, pat) for pat in sandbox.denied_tools
            )
        ]
        after = len(result)
        if before != after:
            logger.debug(
                f"  🔒 Sandbox: {before} → {after} tools "
                f"(denied={sandbox.denied_tools})"
            )
        return result

    def _apply_subagent(
        self,
        tools: list[FunctionTool],
        context: PolicyContext,
    ) -> list[FunctionTool]:
        """
        Apply sub-agent restrictions.

        Uses configurable ``sandbox.subagent_denied_tools`` list.

        Args:
            tools: Current tool list.
            context: Policy context with parent agent info.

        Returns:
            Filtered tool list for sub-agent.
        """
        subagent_deny = self.global_config.sandbox.subagent_denied_tools
        if not subagent_deny:
            return tools

        before = len(tools)
        result = [
            t for t in tools
            if not any(fnmatch.fnmatch(t.name, pat) for pat in subagent_deny)
        ]
        after = len(result)
        if before != after:
            logger.debug(
                f"  👶 Subagent: {before} → {after} tools "
                f"(parent={context.parent_agent_id})"
            )
        return result
