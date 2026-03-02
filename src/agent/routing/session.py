"""
Session key builder for conversation isolation.

Builds deterministic session keys based on agent dm_scope setting,
ensuring conversations are properly isolated per the configured scope.

Session key patterns:
    - main: agent:{id}:{channel}:main
    - per-peer: agent:{id}:{channel}:{kind}:{peer_id}
    - per-channel-peer: agent:{id}:{channel}:{kind}:{peer_id}
    - per-account-channel-peer: agent:{id}:{channel}:{account}:{kind}:{peer_id}
"""

from __future__ import annotations

import logging

from .models import RoutePeer

logger = logging.getLogger(__name__)

_VALID_SCOPES = frozenset({
    "main",
    "per-peer",
    "per-channel-peer",
    "per-account-channel-peer",
})


class SessionKeyBuilder:
    """
    Builds session keys for conversation state isolation.

    The key format depends on the agent's ``dm_scope`` setting,
    which controls how granularly conversations are separated.
    """

    def build(
        self,
        agent_id: str,
        dm_scope: str,
        channel: str,
        peer: RoutePeer | None = None,
        account_id: str | None = None,
    ) -> str:
        """
        Build a session key based on agent scope configuration.

        Args:
            agent_id: Agent identifier.
            dm_scope: Scope setting — main, per-peer, per-channel-peer,
                or per-account-channel-peer.
            channel: Platform channel name.
            peer: Conversation peer (required for per-peer scopes).
            account_id: Bot account id (required for per-account-channel-peer).

        Returns:
            Deterministic session key string.

        Raises:
            ValueError: If dm_scope is not recognized.
        """
        scope = dm_scope.strip().lower()

        if scope not in _VALID_SCOPES:
            raise ValueError(
                f"Invalid dm_scope '{dm_scope}'. "
                f"Must be one of: {', '.join(sorted(_VALID_SCOPES))}"
            )

        agent_id = self._normalize(agent_id)
        channel = self._normalize(channel)

        if scope == "main":
            return f"agent:{agent_id}:{channel}:main"

        if scope in ("per-peer", "per-channel-peer"):
            if peer is None:
                logger.warning(
                    "⚠️ dm_scope=%s but no peer provided, falling back to main",
                    scope,
                )
                return f"agent:{agent_id}:{channel}:main"
            kind = self._normalize(peer.kind)
            peer_id = self._normalize(peer.id)
            return f"agent:{agent_id}:{channel}:{kind}:{peer_id}"

        # per-account-channel-peer
        if peer is None:
            logger.warning(
                "⚠️ dm_scope=per-account-channel-peer but no peer provided, "
                "falling back to main"
            )
            return f"agent:{agent_id}:{channel}:main"

        account = self._normalize(account_id) if account_id else "default"
        kind = self._normalize(peer.kind)
        peer_id = self._normalize(peer.id)
        return f"agent:{agent_id}:{channel}:{account}:{kind}:{peer_id}"

    @staticmethod
    def _normalize(value: str) -> str:
        """
        Normalize a string for key construction.

        Args:
            value: Raw string.

        Returns:
            Lowercased, stripped string.
        """
        return value.strip().lower()
