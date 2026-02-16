"""
Integration tests for agent routing.

Loads the real config.yaml and verifies route resolution,
session key format, and agent config lookup.
"""

from pathlib import Path

import pytest

from agent.config.parser import ConfigParser
from agent.routing.models import RouteContext, RoutePeer
from agent.routing.router import AgentRouter

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "agents" / "config.yaml"


@pytest.fixture
def router() -> AgentRouter:
    """
    Load real config and create router.

    Returns:
        AgentRouter with production config.
    """
    parser = ConfigParser(str(CONFIG_PATH))
    config = parser.load()
    return AgentRouter(config)


class TestRoutingIntegration:
    """Integration tests loading real config.yaml."""

    @pytest.mark.asyncio
    async def test_default_route(self, router: AgentRouter) -> None:
        """Unknown channel resolves to default agent."""
        result = await router.resolve(RouteContext(channel="unknown"))
        assert result.agent_id == "assistant"
        assert result.matched_by == "default"

    @pytest.mark.asyncio
    async def test_test_client_channel(self, router: AgentRouter) -> None:
        """test_client channel matches binding."""
        result = await router.resolve(RouteContext(channel="test_client"))
        assert result.agent_id == "assistant"
        assert result.matched_by == "binding.channel"

    @pytest.mark.asyncio
    async def test_research_channel(self, router: AgentRouter) -> None:
        """research channel routes to researcher agent."""
        result = await router.resolve(RouteContext(channel="research"))
        assert result.agent_id == "researcher"
        assert result.matched_by == "binding.channel"

    @pytest.mark.asyncio
    async def test_session_key_format(self, router: AgentRouter) -> None:
        """Session key has correct format with peer."""
        peer = RoutePeer(kind="dm", id="user123")
        result = await router.resolve(
            RouteContext(channel="discord", peer=peer)
        )
        assert result.session_key.startswith("agent:")
        assert "discord" in result.session_key
        assert "user123" in result.session_key

    @pytest.mark.asyncio
    async def test_session_key_no_peer(self, router: AgentRouter) -> None:
        """Session key falls back to main without peer."""
        result = await router.resolve(RouteContext(channel="discord"))
        assert result.session_key.endswith(":main")

    @pytest.mark.asyncio
    async def test_agent_config_resolved(self, router: AgentRouter) -> None:
        """Resolved route includes full agent config."""
        result = await router.resolve(RouteContext(channel="test_client"))
        assert result.agent_config is not None
        assert result.agent_config.id == "assistant"
        assert result.agent_config.model is not None

    @pytest.mark.asyncio
    async def test_researcher_config_resolved(
        self, router: AgentRouter
    ) -> None:
        """Research route resolves researcher agent config."""
        result = await router.resolve(RouteContext(channel="research"))
        assert result.agent_config is not None
        assert result.agent_config.id == "researcher"
        assert result.agent_config.tools is not None
        assert result.agent_config.tools.profile == "minimal"

    @pytest.mark.asyncio
    async def test_multiple_routes_independent(
        self, router: AgentRouter
    ) -> None:
        """Different contexts produce different routes."""
        r1 = await router.resolve(RouteContext(channel="test_client"))
        r2 = await router.resolve(RouteContext(channel="research"))

        assert r1.agent_id != r2.agent_id
        assert r1.session_key != r2.session_key

    @pytest.mark.asyncio
    async def test_case_insensitive_channel(
        self, router: AgentRouter
    ) -> None:
        """Channel matching is case-insensitive."""
        result = await router.resolve(RouteContext(channel="Test_Client"))
        assert result.agent_id == "assistant"
        assert result.matched_by == "binding.channel"

    @pytest.mark.asyncio
    async def test_session_key_deterministic(
        self, router: AgentRouter
    ) -> None:
        """Same context produces identical session keys."""
        peer = RoutePeer(kind="dm", id="user1")
        ctx = RouteContext(channel="discord", peer=peer)

        r1 = await router.resolve(ctx)
        r2 = await router.resolve(ctx)

        assert r1.session_key == r2.session_key
