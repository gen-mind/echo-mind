"""
Unit tests for SessionKeyBuilder.

Tests cover all 4 dm_scope patterns, missing peer/account fallbacks,
and string normalization.
"""

import pytest

from agent.routing.models import RoutePeer
from agent.routing.session import SessionKeyBuilder


@pytest.fixture
def builder() -> SessionKeyBuilder:
    """Create a SessionKeyBuilder instance."""
    return SessionKeyBuilder()


# ---------------------------------------------------------------------------
# Main Scope
# ---------------------------------------------------------------------------


class TestMainScope:
    """Tests for dm_scope='main'."""

    def test_main_scope(self, builder: SessionKeyBuilder) -> None:
        """Main scope produces agent:{id}:{channel}:main."""
        key = builder.build(
            agent_id="assistant",
            dm_scope="main",
            channel="discord",
        )
        assert key == "agent:assistant:discord:main"

    def test_main_scope_ignores_peer(self, builder: SessionKeyBuilder) -> None:
        """Main scope ignores peer even when provided."""
        peer = RoutePeer(kind="dm", id="user1")
        key = builder.build(
            agent_id="assistant",
            dm_scope="main",
            channel="discord",
            peer=peer,
        )
        assert key == "agent:assistant:discord:main"


# ---------------------------------------------------------------------------
# Per-Peer Scope
# ---------------------------------------------------------------------------


class TestPerPeerScope:
    """Tests for dm_scope='per-peer'."""

    def test_per_peer(self, builder: SessionKeyBuilder) -> None:
        """Per-peer scope includes peer kind and id."""
        peer = RoutePeer(kind="dm", id="user123")
        key = builder.build(
            agent_id="assistant",
            dm_scope="per-peer",
            channel="telegram",
            peer=peer,
        )
        assert key == "agent:assistant:telegram:dm:user123"

    def test_per_peer_no_peer_fallback(
        self, builder: SessionKeyBuilder
    ) -> None:
        """Per-peer scope falls back to main when no peer."""
        key = builder.build(
            agent_id="assistant",
            dm_scope="per-peer",
            channel="discord",
        )
        assert key == "agent:assistant:discord:main"

    def test_per_peer_group(self, builder: SessionKeyBuilder) -> None:
        """Per-peer scope works with group peer."""
        peer = RoutePeer(kind="group", id="grp456")
        key = builder.build(
            agent_id="coder",
            dm_scope="per-peer",
            channel="slack",
            peer=peer,
        )
        assert key == "agent:coder:slack:group:grp456"


# ---------------------------------------------------------------------------
# Per-Channel-Peer Scope
# ---------------------------------------------------------------------------


class TestPerChannelPeerScope:
    """Tests for dm_scope='per-channel-peer'."""

    def test_per_channel_peer(self, builder: SessionKeyBuilder) -> None:
        """Per-channel-peer scope includes channel peer kind and id."""
        peer = RoutePeer(kind="channel", id="ch987")
        key = builder.build(
            agent_id="support",
            dm_scope="per-channel-peer",
            channel="discord",
            peer=peer,
        )
        assert key == "agent:support:discord:channel:ch987"

    def test_per_channel_peer_no_peer_fallback(
        self, builder: SessionKeyBuilder
    ) -> None:
        """Per-channel-peer falls back to main when no peer."""
        key = builder.build(
            agent_id="support",
            dm_scope="per-channel-peer",
            channel="discord",
        )
        assert key == "agent:support:discord:main"


# ---------------------------------------------------------------------------
# Per-Account-Channel-Peer Scope
# ---------------------------------------------------------------------------


class TestPerAccountChannelPeerScope:
    """Tests for dm_scope='per-account-channel-peer'."""

    def test_full_scope(self, builder: SessionKeyBuilder) -> None:
        """Full scope includes account, peer kind, and id."""
        peer = RoutePeer(kind="dm", id="user456")
        key = builder.build(
            agent_id="bot",
            dm_scope="per-account-channel-peer",
            channel="telegram",
            peer=peer,
            account_id="bot1",
        )
        assert key == "agent:bot:telegram:bot1:dm:user456"

    def test_no_account_uses_default(
        self, builder: SessionKeyBuilder
    ) -> None:
        """Missing account falls back to 'default'."""
        peer = RoutePeer(kind="dm", id="user456")
        key = builder.build(
            agent_id="bot",
            dm_scope="per-account-channel-peer",
            channel="telegram",
            peer=peer,
        )
        assert key == "agent:bot:telegram:default:dm:user456"

    def test_no_peer_fallback(self, builder: SessionKeyBuilder) -> None:
        """Missing peer falls back to main."""
        key = builder.build(
            agent_id="bot",
            dm_scope="per-account-channel-peer",
            channel="telegram",
            account_id="bot1",
        )
        assert key == "agent:bot:telegram:main"


# ---------------------------------------------------------------------------
# Normalization & Validation
# ---------------------------------------------------------------------------


class TestNormalization:
    """Tests for string normalization and validation."""

    def test_case_normalized(self, builder: SessionKeyBuilder) -> None:
        """All parts are lowercased."""
        peer = RoutePeer(kind="dm", id="User1")
        key = builder.build(
            agent_id="Assistant",
            dm_scope="per-peer",
            channel="Discord",
            peer=peer,
        )
        assert key == "agent:assistant:discord:dm:user1"

    def test_whitespace_stripped(self, builder: SessionKeyBuilder) -> None:
        """Whitespace is stripped from all parts."""
        key = builder.build(
            agent_id="  assistant  ",
            dm_scope="  main  ",
            channel="  discord  ",
        )
        assert key == "agent:assistant:discord:main"

    def test_invalid_scope_raises(self, builder: SessionKeyBuilder) -> None:
        """Invalid dm_scope raises ValueError."""
        with pytest.raises(ValueError, match="Invalid dm_scope"):
            builder.build(
                agent_id="assistant",
                dm_scope="invalid",
                channel="discord",
            )
