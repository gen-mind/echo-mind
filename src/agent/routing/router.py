"""
Agent Router — 5-tier routing with intent fallback.

Implements the complete agent selection pipeline:
1. Filter bindings by channel + account
2. Try 5-tier matching (peer > guild > team > account > channel)
3. If no match and intent classifier enabled → classify
4. Fall back to default agent
5. Build session key and return ResolvedRoute
"""

from __future__ import annotations

import logging

from agent.config.schema import MoltbotConfig

from .intent import IntentClassifier
from .matcher import BindingMatcher
from .models import ResolvedRoute, RouteContext
from .session import SessionKeyBuilder

logger = logging.getLogger(__name__)

# Tier priority order (highest first)
_TIER_ORDER = ["peer", "guild", "team", "account", "channel"]


class AgentRouter:
    """
    Selects the appropriate agent for an incoming message.

    Uses a 5-tier binding hierarchy with optional LLM-based intent
    fallback when no binding matches.

    Attributes:
        config: Complete agent system configuration.
        matcher: Binding matcher instance.
        session_builder: Session key builder instance.
        intent_classifier: Optional LLM intent classifier.
    """

    def __init__(
        self,
        config: MoltbotConfig,
        intent_classifier: IntentClassifier | None = None,
    ) -> None:
        """
        Initialize the agent router.

        Args:
            config: Complete agent system configuration.
            intent_classifier: Optional LLM-based intent classifier
                for fallback when no binding matches.
        """
        self.config = config
        self.matcher = BindingMatcher()
        self.session_builder = SessionKeyBuilder()
        self.intent_classifier = intent_classifier

    async def resolve(self, context: RouteContext) -> ResolvedRoute:
        """
        Resolve the best agent for the given context.

        Matching follows the 5-tier hierarchy:
        peer > guild > team > account > channel.
        If no binding matches, tries intent classification (if enabled),
        then falls back to the default agent.

        Args:
            context: Incoming message context.

        Returns:
            Resolved route with agent ID, match reason, and session key.
        """
        # 1. Try 5-tier binding match
        matched = self._match_bindings(context)
        if matched is not None:
            agent_id, tier = matched
            return self._build_route(
                agent_id=agent_id,
                matched_by=f"binding.{tier}",
                context=context,
            )

        # 2. Try intent classification fallback
        if self.intent_classifier and context.message:
            intent_result = await self._classify_intent(context)
            if intent_result is not None:
                return self._build_route(
                    agent_id=intent_result,
                    matched_by="intent",
                    context=context,
                )

        # 3. Fall back to default
        default_agent_id = self.config.routing.defaults["agentId"]
        logger.info(
            "📌 Using default agent '%s' for channel=%s",
            default_agent_id,
            context.channel,
        )
        return self._build_route(
            agent_id=default_agent_id,
            matched_by="default",
            context=context,
        )

    def _match_bindings(
        self, context: RouteContext
    ) -> tuple[str, str] | None:
        """
        Try to match bindings in 5-tier priority order.

        Iterates through tiers (peer > guild > team > account > channel)
        and returns the first matching binding's agent_id and tier.

        Args:
            context: Incoming message context.

        Returns:
            Tuple of (agent_id, tier) or None if no match.
        """
        # Group matching bindings by tier
        matches_by_tier: dict[str, str] = {}

        for binding in self.config.routing.bindings:
            if not self.matcher.matches(binding, context):
                continue

            tier = self.matcher.tier(binding)
            if tier is None:
                continue

            # First match per tier wins
            if tier not in matches_by_tier:
                matches_by_tier[tier] = binding.agent_id
                logger.debug(
                    "🔍 Binding match: tier=%s, agent=%s",
                    tier,
                    binding.agent_id,
                )

        # Return highest priority tier match
        for tier in _TIER_ORDER:
            if tier in matches_by_tier:
                agent_id = matches_by_tier[tier]
                logger.info(
                    "🎯 Route matched: tier=%s, agent=%s, channel=%s",
                    tier,
                    agent_id,
                    context.channel,
                )
                return agent_id, tier

        return None

    async def _classify_intent(self, context: RouteContext) -> str | None:
        """
        Use intent classifier to find the best agent.

        Args:
            context: Route context with message text.

        Returns:
            Agent ID or None if classification fails.
        """
        if not self.intent_classifier:
            return None

        result = await self.intent_classifier.classify(
            message=context.message or "",
            agents=self.config.agents,
        )

        if result:
            logger.info(
                "🧠 Intent fallback matched agent '%s' for message",
                result,
            )

        return result

    def _build_route(
        self,
        agent_id: str,
        matched_by: str,
        context: RouteContext,
    ) -> ResolvedRoute:
        """
        Build a ResolvedRoute with session key.

        Args:
            agent_id: Selected agent identifier.
            matched_by: How the route was resolved.
            context: Original route context.

        Returns:
            Complete ResolvedRoute with session key and agent config.
        """
        agent_config = self.config.get_agent(agent_id)
        dm_scope = agent_config.dm_scope if agent_config else "per-peer"

        session_key = self.session_builder.build(
            agent_id=agent_id,
            dm_scope=dm_scope,
            channel=context.channel,
            peer=context.peer,
            account_id=context.account_id,
        )

        return ResolvedRoute(
            agent_id=agent_id,
            matched_by=matched_by,
            session_key=session_key,
            agent_config=agent_config,
        )
