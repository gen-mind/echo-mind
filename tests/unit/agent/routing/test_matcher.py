"""
Unit tests for BindingMatcher.

Tests cover channel, account, peer, guild, and team matching,
including wildcards, case-insensitivity, and full binding evaluation.
"""

import pytest

from agent.config.schema import RouteBindingConfig
from agent.routing.matcher import BindingMatcher
from agent.routing.models import RouteContext, RoutePeer


@pytest.fixture
def matcher() -> BindingMatcher:
    """Create a BindingMatcher instance."""
    return BindingMatcher()


# ---------------------------------------------------------------------------
# Channel Matching
# ---------------------------------------------------------------------------


class TestChannelMatching:
    """Tests for channel criteria matching."""

    def test_exact_match(self, matcher: BindingMatcher) -> None:
        """Exact channel name matches."""
        assert matcher.matches_channel({"channel": "discord"}, "discord")

    def test_case_insensitive(self, matcher: BindingMatcher) -> None:
        """Channel matching is case-insensitive."""
        assert matcher.matches_channel({"channel": "Discord"}, "discord")
        assert matcher.matches_channel({"channel": "discord"}, "DISCORD")

    def test_wildcard(self, matcher: BindingMatcher) -> None:
        """Wildcard '*' matches any channel."""
        assert matcher.matches_channel({"channel": "*"}, "discord")
        assert matcher.matches_channel({"channel": "*"}, "telegram")

    def test_no_match(self, matcher: BindingMatcher) -> None:
        """Different channel name does not match."""
        assert not matcher.matches_channel({"channel": "discord"}, "telegram")

    def test_whitespace_stripped(self, matcher: BindingMatcher) -> None:
        """Whitespace is stripped before comparison."""
        assert matcher.matches_channel({"channel": "  discord  "}, "discord")


# ---------------------------------------------------------------------------
# Account Matching
# ---------------------------------------------------------------------------


class TestAccountMatching:
    """Tests for account criteria matching."""

    def test_exact_match(self, matcher: BindingMatcher) -> None:
        """Exact account ID matches."""
        assert matcher.matches_account({"accountId": "bot1"}, "bot1")

    def test_wildcard(self, matcher: BindingMatcher) -> None:
        """Wildcard matches any account."""
        assert matcher.matches_account({"accountId": "*"}, "bot1")

    def test_none_account(self, matcher: BindingMatcher) -> None:
        """None account_id does not match a specific criteria."""
        assert not matcher.matches_account({"accountId": "bot1"}, None)

    def test_wildcard_with_none(self, matcher: BindingMatcher) -> None:
        """Wildcard matches even when account is None."""
        assert matcher.matches_account({"accountId": "*"}, None)

    def test_case_insensitive(self, matcher: BindingMatcher) -> None:
        """Account matching is case-insensitive."""
        assert matcher.matches_account({"accountId": "Bot1"}, "bot1")


# ---------------------------------------------------------------------------
# Peer Matching
# ---------------------------------------------------------------------------


class TestPeerMatching:
    """Tests for peer criteria matching."""

    def test_exact_match(self, matcher: BindingMatcher) -> None:
        """Exact peer kind and id match."""
        peer = RoutePeer(kind="dm", id="user123")
        assert matcher.matches_peer(
            {"peer": {"kind": "dm", "id": "user123"}}, peer
        )

    def test_wildcard_kind(self, matcher: BindingMatcher) -> None:
        """Wildcard kind matches any peer kind."""
        peer = RoutePeer(kind="group", id="g1")
        assert matcher.matches_peer({"peer": {"kind": "*", "id": "g1"}}, peer)

    def test_wildcard_id(self, matcher: BindingMatcher) -> None:
        """Wildcard id matches any peer id."""
        peer = RoutePeer(kind="dm", id="anyone")
        assert matcher.matches_peer(
            {"peer": {"kind": "dm", "id": "*"}}, peer
        )

    def test_none_peer(self, matcher: BindingMatcher) -> None:
        """None peer does not match."""
        assert not matcher.matches_peer(
            {"peer": {"kind": "dm", "id": "user1"}}, None
        )

    def test_invalid_peer_criteria(self, matcher: BindingMatcher) -> None:
        """Non-dict peer criteria does not match."""
        peer = RoutePeer(kind="dm", id="user1")
        assert not matcher.matches_peer({"peer": "invalid"}, peer)

    def test_kind_mismatch(self, matcher: BindingMatcher) -> None:
        """Wrong kind does not match."""
        peer = RoutePeer(kind="group", id="user1")
        assert not matcher.matches_peer(
            {"peer": {"kind": "dm", "id": "user1"}}, peer
        )

    def test_id_mismatch(self, matcher: BindingMatcher) -> None:
        """Wrong id does not match."""
        peer = RoutePeer(kind="dm", id="user2")
        assert not matcher.matches_peer(
            {"peer": {"kind": "dm", "id": "user1"}}, peer
        )


# ---------------------------------------------------------------------------
# Guild Matching
# ---------------------------------------------------------------------------


class TestGuildMatching:
    """Tests for guild criteria matching."""

    def test_exact_match(self, matcher: BindingMatcher) -> None:
        """Exact guild ID matches."""
        assert matcher.matches_guild({"guildId": "guild1"}, "guild1")

    def test_wildcard(self, matcher: BindingMatcher) -> None:
        """Wildcard matches any guild."""
        assert matcher.matches_guild({"guildId": "*"}, "guild1")

    def test_none_guild(self, matcher: BindingMatcher) -> None:
        """None guild_id does not match a specific criteria."""
        assert not matcher.matches_guild({"guildId": "guild1"}, None)

    def test_case_insensitive(self, matcher: BindingMatcher) -> None:
        """Guild matching is case-insensitive."""
        assert matcher.matches_guild({"guildId": "Guild1"}, "guild1")


# ---------------------------------------------------------------------------
# Team Matching
# ---------------------------------------------------------------------------


class TestTeamMatching:
    """Tests for team criteria matching."""

    def test_exact_match(self, matcher: BindingMatcher) -> None:
        """Exact team ID matches."""
        assert matcher.matches_team({"teamId": "team1"}, "team1")

    def test_wildcard(self, matcher: BindingMatcher) -> None:
        """Wildcard matches any team."""
        assert matcher.matches_team({"teamId": "*"}, "team1")

    def test_none_team(self, matcher: BindingMatcher) -> None:
        """None team_id does not match a specific criteria."""
        assert not matcher.matches_team({"teamId": "team1"}, None)


# ---------------------------------------------------------------------------
# Full Binding Match
# ---------------------------------------------------------------------------


class TestFullBindingMatch:
    """Tests for complete binding evaluation."""

    def test_channel_only_binding(self, matcher: BindingMatcher) -> None:
        """Binding with only channel matches when channel matches."""
        binding = RouteBindingConfig(
            match={"channel": "discord"}, agent_id="assistant"
        )
        ctx = RouteContext(channel="discord")
        assert matcher.matches(binding, ctx)

    def test_channel_mismatch(self, matcher: BindingMatcher) -> None:
        """Binding fails when channel doesn't match."""
        binding = RouteBindingConfig(
            match={"channel": "discord"}, agent_id="assistant"
        )
        ctx = RouteContext(channel="telegram")
        assert not matcher.matches(binding, ctx)

    def test_multi_criteria_all_match(self, matcher: BindingMatcher) -> None:
        """All criteria must match for binding to match."""
        binding = RouteBindingConfig(
            match={
                "channel": "discord",
                "guildId": "guild1",
                "peer": {"kind": "dm", "id": "user1"},
            },
            agent_id="assistant",
        )
        ctx = RouteContext(
            channel="discord",
            guild_id="guild1",
            peer=RoutePeer(kind="dm", id="user1"),
        )
        assert matcher.matches(binding, ctx)

    def test_multi_criteria_partial_fail(
        self, matcher: BindingMatcher
    ) -> None:
        """If one criterion fails, entire binding fails."""
        binding = RouteBindingConfig(
            match={
                "channel": "discord",
                "guildId": "wrong_guild",
            },
            agent_id="assistant",
        )
        ctx = RouteContext(channel="discord", guild_id="guild1")
        assert not matcher.matches(binding, ctx)

    def test_empty_match_dict(self, matcher: BindingMatcher) -> None:
        """Empty match dict never matches."""
        binding = RouteBindingConfig(match={}, agent_id="assistant")
        ctx = RouteContext(channel="discord")
        assert not matcher.matches(binding, ctx)


# ---------------------------------------------------------------------------
# Tier Classification
# ---------------------------------------------------------------------------


class TestTierClassification:
    """Tests for binding tier determination."""

    def test_peer_tier(self, matcher: BindingMatcher) -> None:
        """Binding with peer is tier 'peer'."""
        binding = RouteBindingConfig(
            match={"peer": {"kind": "dm", "id": "u1"}}, agent_id="a"
        )
        assert matcher.tier(binding) == "peer"

    def test_guild_tier(self, matcher: BindingMatcher) -> None:
        """Binding with guildId is tier 'guild'."""
        binding = RouteBindingConfig(
            match={"guildId": "g1"}, agent_id="a"
        )
        assert matcher.tier(binding) == "guild"

    def test_team_tier(self, matcher: BindingMatcher) -> None:
        """Binding with teamId is tier 'team'."""
        binding = RouteBindingConfig(
            match={"teamId": "t1"}, agent_id="a"
        )
        assert matcher.tier(binding) == "team"

    def test_account_tier(self, matcher: BindingMatcher) -> None:
        """Binding with accountId is tier 'account'."""
        binding = RouteBindingConfig(
            match={"accountId": "a1"}, agent_id="a"
        )
        assert matcher.tier(binding) == "account"

    def test_channel_tier(self, matcher: BindingMatcher) -> None:
        """Binding with only channel is tier 'channel'."""
        binding = RouteBindingConfig(
            match={"channel": "discord"}, agent_id="a"
        )
        assert matcher.tier(binding) == "channel"

    def test_peer_takes_priority(self, matcher: BindingMatcher) -> None:
        """When multiple criteria present, peer tier wins."""
        binding = RouteBindingConfig(
            match={
                "channel": "discord",
                "peer": {"kind": "dm", "id": "u1"},
                "guildId": "g1",
            },
            agent_id="a",
        )
        assert matcher.tier(binding) == "peer"

    def test_empty_match_none_tier(self, matcher: BindingMatcher) -> None:
        """Empty match dict has None tier."""
        binding = RouteBindingConfig(match={}, agent_id="a")
        assert matcher.tier(binding) is None

    def test_unknown_keys_none_tier(self, matcher: BindingMatcher) -> None:
        """Match dict with only unknown keys has None tier."""
        binding = RouteBindingConfig(
            match={"unknownKey": "value"}, agent_id="a"
        )
        assert matcher.tier(binding) is None


# ---------------------------------------------------------------------------
# Full Match — Specific Criteria Failures
# ---------------------------------------------------------------------------


class TestFullMatchCriteriaFailures:
    """Tests for specific criteria failing in full matches() call."""

    def test_account_mismatch_in_full_match(
        self, matcher: BindingMatcher
    ) -> None:
        """Binding fails when accountId doesn't match in full evaluation."""
        binding = RouteBindingConfig(
            match={"channel": "discord", "accountId": "bot1"},
            agent_id="assistant",
        )
        ctx = RouteContext(channel="discord", account_id="bot2")
        assert not matcher.matches(binding, ctx)

    def test_peer_mismatch_in_full_match(
        self, matcher: BindingMatcher
    ) -> None:
        """Binding fails when peer doesn't match in full evaluation."""
        binding = RouteBindingConfig(
            match={
                "channel": "discord",
                "peer": {"kind": "dm", "id": "user1"},
            },
            agent_id="assistant",
        )
        ctx = RouteContext(
            channel="discord",
            peer=RoutePeer(kind="dm", id="user2"),
        )
        assert not matcher.matches(binding, ctx)

    def test_team_mismatch_in_full_match(
        self, matcher: BindingMatcher
    ) -> None:
        """Binding fails when teamId doesn't match in full evaluation."""
        binding = RouteBindingConfig(
            match={"channel": "slack", "teamId": "team1"},
            agent_id="assistant",
        )
        ctx = RouteContext(channel="slack", team_id="team2")
        assert not matcher.matches(binding, ctx)
