"""
Unit tests for AgentRouter.

Tests cover 5-tier priority matching, default fallback, intent fallback,
session key construction, and agent config resolution.
"""

from unittest.mock import AsyncMock

import pytest

from agent.config.schema import (
    AgentConfig,
    MoltbotConfig,
    RouteBindingConfig,
    RoutingConfig,
    SandboxConfig,
    ToolPolicy,
)
from agent.routing.models import RouteContext, RoutePeer
from agent.routing.router import AgentRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(
    agent_id: str, dm_scope: str = "per-peer"
) -> AgentConfig:
    """
    Create a minimal AgentConfig for testing.

    Args:
        agent_id: Agent identifier.
        dm_scope: Session scope setting.

    Returns:
        AgentConfig instance.
    """
    return AgentConfig(
        id=agent_id,
        name=agent_id.title(),
        model="gpt-4o-mini",
        instructions=f"You are {agent_id}",
        dm_scope=dm_scope,
    )


def _make_config(
    agents: list[AgentConfig] | None = None,
    bindings: list[RouteBindingConfig] | None = None,
    default_agent: str = "assistant",
) -> MoltbotConfig:
    """
    Build a MoltbotConfig for testing.

    Args:
        agents: Agent list (defaults to [assistant, coder, researcher]).
        bindings: Route bindings (defaults to empty).
        default_agent: Default agent ID.

    Returns:
        MoltbotConfig instance.
    """
    if agents is None:
        agents = [
            _make_agent("assistant"),
            _make_agent("coder"),
            _make_agent("researcher"),
        ]

    return MoltbotConfig(
        agents=agents,
        routing=RoutingConfig(
            defaults={"agentId": default_agent},
            bindings=bindings or [],
        ),
        tools=ToolPolicy(),
        sandbox=SandboxConfig(),
    )


# ---------------------------------------------------------------------------
# Default Fallback
# ---------------------------------------------------------------------------


class TestDefaultFallback:
    """Tests for default agent fallback."""

    @pytest.mark.asyncio
    async def test_no_bindings_uses_default(self) -> None:
        """With no bindings, default agent is selected."""
        config = _make_config()
        router = AgentRouter(config)

        result = await router.resolve(RouteContext(channel="discord"))

        assert result.agent_id == "assistant"
        assert result.matched_by == "default"

    @pytest.mark.asyncio
    async def test_no_matching_binding_uses_default(self) -> None:
        """When no binding matches, default is used."""
        config = _make_config(
            bindings=[
                RouteBindingConfig(
                    match={"channel": "telegram"}, agent_id="coder"
                ),
            ]
        )
        router = AgentRouter(config)

        result = await router.resolve(RouteContext(channel="discord"))

        assert result.agent_id == "assistant"
        assert result.matched_by == "default"


# ---------------------------------------------------------------------------
# Channel Tier
# ---------------------------------------------------------------------------


class TestChannelTier:
    """Tests for channel-tier binding matching."""

    @pytest.mark.asyncio
    async def test_channel_match(self) -> None:
        """Channel binding matches and returns correct agent."""
        config = _make_config(
            bindings=[
                RouteBindingConfig(
                    match={"channel": "discord"}, agent_id="coder"
                ),
            ]
        )
        router = AgentRouter(config)

        result = await router.resolve(RouteContext(channel="discord"))

        assert result.agent_id == "coder"
        assert result.matched_by == "binding.channel"


# ---------------------------------------------------------------------------
# Peer Tier (Highest Priority)
# ---------------------------------------------------------------------------


class TestPeerTier:
    """Tests for peer-tier binding matching."""

    @pytest.mark.asyncio
    async def test_peer_match(self) -> None:
        """Peer binding matches with correct peer."""
        config = _make_config(
            bindings=[
                RouteBindingConfig(
                    match={"peer": {"kind": "dm", "id": "vip1"}},
                    agent_id="researcher",
                ),
            ]
        )
        router = AgentRouter(config)

        result = await router.resolve(
            RouteContext(
                channel="discord",
                peer=RoutePeer(kind="dm", id="vip1"),
            )
        )

        assert result.agent_id == "researcher"
        assert result.matched_by == "binding.peer"

    @pytest.mark.asyncio
    async def test_peer_takes_priority_over_channel(self) -> None:
        """Peer tier wins over channel tier."""
        config = _make_config(
            bindings=[
                RouteBindingConfig(
                    match={"channel": "discord"}, agent_id="coder"
                ),
                RouteBindingConfig(
                    match={"peer": {"kind": "dm", "id": "vip1"}},
                    agent_id="researcher",
                ),
            ]
        )
        router = AgentRouter(config)

        result = await router.resolve(
            RouteContext(
                channel="discord",
                peer=RoutePeer(kind="dm", id="vip1"),
            )
        )

        assert result.agent_id == "researcher"
        assert result.matched_by == "binding.peer"


# ---------------------------------------------------------------------------
# Guild Tier
# ---------------------------------------------------------------------------


class TestGuildTier:
    """Tests for guild-tier binding matching."""

    @pytest.mark.asyncio
    async def test_guild_match(self) -> None:
        """Guild binding matches."""
        config = _make_config(
            bindings=[
                RouteBindingConfig(
                    match={"guildId": "guild1", "channel": "discord"},
                    agent_id="coder",
                ),
            ]
        )
        router = AgentRouter(config)

        result = await router.resolve(
            RouteContext(channel="discord", guild_id="guild1")
        )

        assert result.agent_id == "coder"
        assert result.matched_by == "binding.guild"

    @pytest.mark.asyncio
    async def test_guild_takes_priority_over_team(self) -> None:
        """Guild tier wins over team tier."""
        config = _make_config(
            bindings=[
                RouteBindingConfig(
                    match={"teamId": "team1"}, agent_id="researcher"
                ),
                RouteBindingConfig(
                    match={"guildId": "guild1"}, agent_id="coder"
                ),
            ]
        )
        router = AgentRouter(config)

        result = await router.resolve(
            RouteContext(
                channel="discord",
                guild_id="guild1",
                team_id="team1",
            )
        )

        assert result.agent_id == "coder"
        assert result.matched_by == "binding.guild"


# ---------------------------------------------------------------------------
# Team Tier
# ---------------------------------------------------------------------------


class TestTeamTier:
    """Tests for team-tier binding matching."""

    @pytest.mark.asyncio
    async def test_team_match(self) -> None:
        """Team binding matches."""
        config = _make_config(
            bindings=[
                RouteBindingConfig(
                    match={"teamId": "workspace1"}, agent_id="coder"
                ),
            ]
        )
        router = AgentRouter(config)

        result = await router.resolve(
            RouteContext(channel="slack", team_id="workspace1")
        )

        assert result.agent_id == "coder"
        assert result.matched_by == "binding.team"


# ---------------------------------------------------------------------------
# Account Tier
# ---------------------------------------------------------------------------


class TestAccountTier:
    """Tests for account-tier binding matching."""

    @pytest.mark.asyncio
    async def test_account_match(self) -> None:
        """Account binding matches."""
        config = _make_config(
            bindings=[
                RouteBindingConfig(
                    match={"accountId": "bot1"}, agent_id="coder"
                ),
            ]
        )
        router = AgentRouter(config)

        result = await router.resolve(
            RouteContext(channel="telegram", account_id="bot1")
        )

        assert result.agent_id == "coder"
        assert result.matched_by == "binding.account"

    @pytest.mark.asyncio
    async def test_account_priority_over_channel(self) -> None:
        """Account tier wins over channel tier."""
        config = _make_config(
            bindings=[
                RouteBindingConfig(
                    match={"channel": "telegram"}, agent_id="researcher"
                ),
                RouteBindingConfig(
                    match={"accountId": "bot1"}, agent_id="coder"
                ),
            ]
        )
        router = AgentRouter(config)

        result = await router.resolve(
            RouteContext(channel="telegram", account_id="bot1")
        )

        assert result.agent_id == "coder"
        assert result.matched_by == "binding.account"


# ---------------------------------------------------------------------------
# 5-Tier Full Priority
# ---------------------------------------------------------------------------


class TestFullPriority:
    """Tests for complete 5-tier priority ordering."""

    @pytest.mark.asyncio
    async def test_all_tiers_peer_wins(self) -> None:
        """When all tiers match, peer tier wins."""
        config = _make_config(
            bindings=[
                RouteBindingConfig(
                    match={"channel": "discord"}, agent_id="assistant"
                ),
                RouteBindingConfig(
                    match={"accountId": "bot1"}, agent_id="assistant"
                ),
                RouteBindingConfig(
                    match={"teamId": "t1"}, agent_id="assistant"
                ),
                RouteBindingConfig(
                    match={"guildId": "g1"}, agent_id="assistant"
                ),
                RouteBindingConfig(
                    match={"peer": {"kind": "dm", "id": "u1"}},
                    agent_id="coder",
                ),
            ]
        )
        router = AgentRouter(config)

        result = await router.resolve(
            RouteContext(
                channel="discord",
                account_id="bot1",
                team_id="t1",
                guild_id="g1",
                peer=RoutePeer(kind="dm", id="u1"),
            )
        )

        assert result.agent_id == "coder"
        assert result.matched_by == "binding.peer"


# ---------------------------------------------------------------------------
# Intent Fallback
# ---------------------------------------------------------------------------


class TestIntentFallback:
    """Tests for LLM intent classification fallback."""

    @pytest.mark.asyncio
    async def test_intent_fallback_used(self) -> None:
        """Intent classifier is used when no binding matches."""
        config = _make_config()
        mock_classifier = AsyncMock()
        mock_classifier.classify = AsyncMock(return_value="coder")

        router = AgentRouter(config, intent_classifier=mock_classifier)

        result = await router.resolve(
            RouteContext(channel="discord", message="Write some Python")
        )

        assert result.agent_id == "coder"
        assert result.matched_by == "intent"
        mock_classifier.classify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_intent_fallback_returns_none_uses_default(self) -> None:
        """When intent returns None, default is used."""
        config = _make_config()
        mock_classifier = AsyncMock()
        mock_classifier.classify = AsyncMock(return_value=None)

        router = AgentRouter(config, intent_classifier=mock_classifier)

        result = await router.resolve(
            RouteContext(channel="discord", message="hello")
        )

        assert result.agent_id == "assistant"
        assert result.matched_by == "default"

    @pytest.mark.asyncio
    async def test_intent_not_used_when_binding_matches(self) -> None:
        """Intent classifier is skipped when a binding matches."""
        config = _make_config(
            bindings=[
                RouteBindingConfig(
                    match={"channel": "discord"}, agent_id="coder"
                ),
            ]
        )
        mock_classifier = AsyncMock()
        mock_classifier.classify = AsyncMock(return_value="researcher")

        router = AgentRouter(config, intent_classifier=mock_classifier)

        result = await router.resolve(
            RouteContext(channel="discord", message="hello")
        )

        assert result.agent_id == "coder"
        assert result.matched_by == "binding.channel"
        mock_classifier.classify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_intent_not_used_without_message(self) -> None:
        """Intent classifier is skipped when no message text."""
        config = _make_config()
        mock_classifier = AsyncMock()
        mock_classifier.classify = AsyncMock(return_value="coder")

        router = AgentRouter(config, intent_classifier=mock_classifier)

        result = await router.resolve(RouteContext(channel="discord"))

        assert result.agent_id == "assistant"
        assert result.matched_by == "default"
        mock_classifier.classify.assert_not_awaited()


# ---------------------------------------------------------------------------
# Session Key
# ---------------------------------------------------------------------------


class TestSessionKey:
    """Tests for session key in resolved route."""

    @pytest.mark.asyncio
    async def test_session_key_default_per_peer(self) -> None:
        """Default per-peer scope builds correct session key."""
        config = _make_config()
        router = AgentRouter(config)

        peer = RoutePeer(kind="dm", id="user1")
        result = await router.resolve(
            RouteContext(channel="discord", peer=peer)
        )

        assert result.session_key == "agent:assistant:discord:dm:user1"

    @pytest.mark.asyncio
    async def test_session_key_main_scope(self) -> None:
        """Main scope agent builds main session key."""
        agents = [_make_agent("assistant", dm_scope="main")]
        config = _make_config(agents=agents)
        router = AgentRouter(config)

        result = await router.resolve(RouteContext(channel="discord"))

        assert result.session_key == "agent:assistant:discord:main"

    @pytest.mark.asyncio
    async def test_session_key_no_peer_fallback(self) -> None:
        """Without peer, per-peer scope falls back to main."""
        config = _make_config()
        router = AgentRouter(config)

        result = await router.resolve(RouteContext(channel="discord"))

        assert result.session_key == "agent:assistant:discord:main"


# ---------------------------------------------------------------------------
# Agent Config Resolution
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases in routing logic."""

    @pytest.mark.asyncio
    async def test_classify_intent_without_classifier(self) -> None:
        """_classify_intent returns None when no classifier configured."""
        config = _make_config()
        router = AgentRouter(config)  # No intent_classifier
        result = await router._classify_intent(RouteContext(channel="discord"))
        assert result is None

    @pytest.mark.asyncio
    async def test_binding_with_unknown_keys_skipped(self) -> None:
        """Binding with unrecognized match keys (tier=None) is skipped."""
        config = _make_config(
            bindings=[
                RouteBindingConfig(
                    match={"unknownKey": "value"}, agent_id="coder"
                ),
            ]
        )
        router = AgentRouter(config)

        result = await router.resolve(RouteContext(channel="discord"))

        # Should fall through to default since tier is None
        assert result.agent_id == "assistant"
        assert result.matched_by == "default"


class TestAgentConfigResolution:
    """Tests for agent_config in resolved route."""

    @pytest.mark.asyncio
    async def test_agent_config_resolved(self) -> None:
        """Resolved route includes agent_config."""
        config = _make_config()
        router = AgentRouter(config)

        result = await router.resolve(RouteContext(channel="discord"))

        assert result.agent_config is not None
        assert result.agent_config.id == "assistant"
        assert result.agent_config.name == "Assistant"

    @pytest.mark.asyncio
    async def test_agent_config_from_binding(self) -> None:
        """Binding match also resolves agent_config."""
        config = _make_config(
            bindings=[
                RouteBindingConfig(
                    match={"channel": "discord"}, agent_id="coder"
                ),
            ]
        )
        router = AgentRouter(config)

        result = await router.resolve(RouteContext(channel="discord"))

        assert result.agent_config is not None
        assert result.agent_config.id == "coder"
