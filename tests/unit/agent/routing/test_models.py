"""
Unit tests for routing data models.

Tests cover RoutePeer, RouteContext, and ResolvedRoute construction,
validation, and immutability.
"""

import pytest

from agent.routing.models import ResolvedRoute, RouteContext, RoutePeer


# ---------------------------------------------------------------------------
# RoutePeer
# ---------------------------------------------------------------------------


class TestRoutePeer:
    """Tests for RoutePeer dataclass."""

    def test_create_dm_peer(self) -> None:
        """RoutePeer with kind=dm is valid."""
        peer = RoutePeer(kind="dm", id="user123")
        assert peer.kind == "dm"
        assert peer.id == "user123"

    def test_create_group_peer(self) -> None:
        """RoutePeer with kind=group is valid."""
        peer = RoutePeer(kind="group", id="group456")
        assert peer.kind == "group"
        assert peer.id == "group456"

    def test_create_channel_peer(self) -> None:
        """RoutePeer with kind=channel is valid."""
        peer = RoutePeer(kind="channel", id="ch789")
        assert peer.kind == "channel"

    def test_frozen_immutability(self) -> None:
        """RoutePeer is frozen — attributes cannot be reassigned."""
        peer = RoutePeer(kind="dm", id="user123")
        with pytest.raises(AttributeError):
            peer.kind = "group"  # type: ignore[misc]

    def test_invalid_kind_raises(self) -> None:
        """Invalid peer kind raises ValueError."""
        with pytest.raises(ValueError, match="Invalid peer kind"):
            RoutePeer(kind="unknown", id="abc")

    def test_empty_id_raises(self) -> None:
        """Empty peer id raises ValueError."""
        with pytest.raises(ValueError, match="Peer id cannot be empty"):
            RoutePeer(kind="dm", id="")

    def test_whitespace_id_raises(self) -> None:
        """Whitespace-only peer id raises ValueError."""
        with pytest.raises(ValueError, match="Peer id cannot be empty"):
            RoutePeer(kind="dm", id="   ")

    def test_equality(self) -> None:
        """Two RoutePeers with same values are equal."""
        p1 = RoutePeer(kind="dm", id="user1")
        p2 = RoutePeer(kind="dm", id="user1")
        assert p1 == p2

    def test_hashable(self) -> None:
        """RoutePeer can be used in sets (frozen=True)."""
        p1 = RoutePeer(kind="dm", id="user1")
        p2 = RoutePeer(kind="dm", id="user1")
        assert {p1, p2} == {p1}


# ---------------------------------------------------------------------------
# RouteContext
# ---------------------------------------------------------------------------


class TestRouteContext:
    """Tests for RouteContext dataclass."""

    def test_minimal_context(self) -> None:
        """RouteContext with only channel is valid."""
        ctx = RouteContext(channel="discord")
        assert ctx.channel == "discord"
        assert ctx.account_id is None
        assert ctx.peer is None
        assert ctx.guild_id is None
        assert ctx.team_id is None
        assert ctx.message is None

    def test_full_context(self) -> None:
        """RouteContext with all fields populated."""
        peer = RoutePeer(kind="dm", id="user1")
        ctx = RouteContext(
            channel="discord",
            account_id="bot1",
            peer=peer,
            guild_id="guild1",
            team_id="team1",
            message="hello",
        )
        assert ctx.channel == "discord"
        assert ctx.account_id == "bot1"
        assert ctx.peer == peer
        assert ctx.guild_id == "guild1"
        assert ctx.team_id == "team1"
        assert ctx.message == "hello"

    def test_empty_channel_raises(self) -> None:
        """Empty channel raises ValueError."""
        with pytest.raises(ValueError, match="Channel cannot be empty"):
            RouteContext(channel="")

    def test_whitespace_channel_raises(self) -> None:
        """Whitespace-only channel raises ValueError."""
        with pytest.raises(ValueError, match="Channel cannot be empty"):
            RouteContext(channel="  ")


# ---------------------------------------------------------------------------
# ResolvedRoute
# ---------------------------------------------------------------------------


class TestResolvedRoute:
    """Tests for ResolvedRoute dataclass."""

    def test_create_resolved_route(self) -> None:
        """ResolvedRoute with required fields is valid."""
        route = ResolvedRoute(
            agent_id="assistant",
            matched_by="default",
            session_key="agent:assistant:discord:main",
        )
        assert route.agent_id == "assistant"
        assert route.matched_by == "default"
        assert route.session_key == "agent:assistant:discord:main"
        assert route.agent_config is None

    def test_agent_config_optional(self) -> None:
        """ResolvedRoute works with and without agent_config."""
        route = ResolvedRoute(
            agent_id="coder",
            matched_by="binding.peer",
            session_key="agent:coder:slack:dm:u1",
        )
        assert route.agent_config is None

    def test_empty_agent_id_raises(self) -> None:
        """Empty agent_id raises ValueError."""
        with pytest.raises(ValueError, match="agent_id cannot be empty"):
            ResolvedRoute(
                agent_id="",
                matched_by="default",
                session_key="key",
            )

    def test_empty_session_key_raises(self) -> None:
        """Empty session_key raises ValueError."""
        with pytest.raises(ValueError, match="session_key cannot be empty"):
            ResolvedRoute(
                agent_id="assistant",
                matched_by="default",
                session_key="",
            )

    def test_frozen_immutability(self) -> None:
        """ResolvedRoute is frozen — attributes cannot be reassigned."""
        route = ResolvedRoute(
            agent_id="assistant",
            matched_by="default",
            session_key="key:1",
        )
        with pytest.raises(AttributeError):
            route.agent_id = "other"  # type: ignore[misc]
