"""
Binding matcher for agent routing.

Evaluates RouteBindingConfig match criteria against a RouteContext
to determine if a binding applies. Supports wildcard matching,
case-insensitive comparison, and partial match criteria.
"""

from __future__ import annotations

from typing import Any

from agent.config.schema import RouteBindingConfig

from .models import RouteContext, RoutePeer


class BindingMatcher:
    """
    Evaluates routing bindings against message context.

    Each binding has a ``match`` dict with optional keys:
    ``channel``, ``accountId``, ``peer`` (dict with kind/id),
    ``guildId``, ``teamId``. All specified criteria must match
    for the binding to apply. Wildcard ``"*"`` matches any value.
    """

    def matches(self, binding: RouteBindingConfig, context: RouteContext) -> bool:
        """
        Check if a binding matches the given context.

        All criteria present in the binding must match. Missing criteria
        are considered matched (don't-care).

        Args:
            binding: Route binding with match criteria.
            context: Incoming message context.

        Returns:
            True if all specified criteria match.
        """
        match = binding.match

        if not match:
            return False

        if "channel" in match and not self.matches_channel(match, context.channel):
            return False

        if "accountId" in match and not self.matches_account(
            match, context.account_id
        ):
            return False

        if "peer" in match and not self.matches_peer(match, context.peer):
            return False

        if "guildId" in match and not self.matches_guild(match, context.guild_id):
            return False

        if "teamId" in match and not self.matches_team(match, context.team_id):
            return False

        return True

    def matches_channel(self, match: dict[str, Any], channel: str) -> bool:
        """
        Check if the channel criteria matches.

        Args:
            match: Match criteria dict.
            channel: Platform channel name.

        Returns:
            True if channel matches or criteria is wildcard.
        """
        criteria = self._normalize(match.get("channel", ""))
        if criteria == "*":
            return True
        return criteria == self._normalize(channel)

    def matches_account(
        self, match: dict[str, Any], account_id: str | None
    ) -> bool:
        """
        Check if the account criteria matches.

        Args:
            match: Match criteria dict.
            account_id: Bot account identifier (may be None).

        Returns:
            True if account matches or criteria is wildcard.
        """
        criteria = self._normalize(match.get("accountId", ""))
        if criteria == "*":
            return True
        if account_id is None:
            return False
        return criteria == self._normalize(account_id)

    def matches_peer(
        self, match: dict[str, Any], peer: RoutePeer | None
    ) -> bool:
        """
        Check if the peer criteria matches.

        Peer criteria is a dict with ``kind`` and ``id`` keys.

        Args:
            match: Match criteria dict containing ``peer`` sub-dict.
            peer: Conversation peer (may be None).

        Returns:
            True if peer kind and id match.
        """
        peer_criteria = match.get("peer")
        if not isinstance(peer_criteria, dict):
            return False

        if peer is None:
            return False

        criteria_kind = self._normalize(peer_criteria.get("kind", ""))
        criteria_id = self._normalize(peer_criteria.get("id", ""))

        if criteria_kind != "*" and criteria_kind != self._normalize(peer.kind):
            return False

        if criteria_id != "*" and criteria_id != self._normalize(peer.id):
            return False

        return True

    def matches_guild(
        self, match: dict[str, Any], guild_id: str | None
    ) -> bool:
        """
        Check if the guild criteria matches.

        Args:
            match: Match criteria dict.
            guild_id: Discord guild identifier (may be None).

        Returns:
            True if guild matches or criteria is wildcard.
        """
        criteria = self._normalize(match.get("guildId", ""))
        if criteria == "*":
            return True
        if guild_id is None:
            return False
        return criteria == self._normalize(guild_id)

    def matches_team(
        self, match: dict[str, Any], team_id: str | None
    ) -> bool:
        """
        Check if the team criteria matches.

        Args:
            match: Match criteria dict.
            team_id: Slack workspace identifier (may be None).

        Returns:
            True if team matches or criteria is wildcard.
        """
        criteria = self._normalize(match.get("teamId", ""))
        if criteria == "*":
            return True
        if team_id is None:
            return False
        return criteria == self._normalize(team_id)

    @staticmethod
    def _normalize(value: str) -> str:
        """
        Normalize a string for comparison.

        Args:
            value: Raw string value.

        Returns:
            Lowercased, stripped string.
        """
        return value.strip().lower()

    def tier(self, binding: RouteBindingConfig) -> str | None:
        """
        Determine the highest-priority tier a binding targets.

        Priority order: peer > guild > team > account > channel.

        Args:
            binding: Route binding to classify.

        Returns:
            Tier name (e.g., "peer", "guild") or None if empty match.
        """
        match = binding.match
        if not match:
            return None

        if "peer" in match:
            return "peer"
        if "guildId" in match:
            return "guild"
        if "teamId" in match:
            return "team"
        if "accountId" in match:
            return "account"
        if "channel" in match:
            return "channel"

        return None
