"""
Data models for agent routing.

Defines the core value objects used throughout the routing system:
RoutePeer, RouteContext, and ResolvedRoute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.config.schema import AgentConfig

_VALID_PEER_KINDS = frozenset({"dm", "group", "channel"})


@dataclass(frozen=True)
class RoutePeer:
    """
    Identifies a conversation peer (user, group, or channel).

    Attributes:
        kind: Peer type — "dm", "group", or "channel".
        id: Unique peer identifier within the platform.

    Raises:
        ValueError: If kind is not one of dm/group/channel or id is empty.
    """

    kind: str
    id: str

    def __post_init__(self) -> None:
        """
        Validate peer fields.

        Raises:
            ValueError: If kind is invalid or id is empty.
        """
        if self.kind not in _VALID_PEER_KINDS:
            raise ValueError(
                f"Invalid peer kind '{self.kind}'. "
                f"Must be one of: {', '.join(sorted(_VALID_PEER_KINDS))}"
            )
        if not self.id or not self.id.strip():
            raise ValueError("Peer id cannot be empty")


@dataclass
class RouteContext:
    """
    Incoming message context used for agent routing decisions.

    Attributes:
        channel: Platform name — "discord", "telegram", "slack", "test_client".
        account_id: Bot account identifier (for multi-account setups).
        peer: Conversation peer (user/group/channel).
        guild_id: Discord guild (server) identifier.
        team_id: Slack workspace identifier.
        message: Raw message text (used for intent classification).
    """

    channel: str
    account_id: str | None = None
    peer: RoutePeer | None = None
    guild_id: str | None = None
    team_id: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        """
        Validate route context.

        Raises:
            ValueError: If channel is empty.
        """
        if not self.channel or not self.channel.strip():
            raise ValueError("Channel cannot be empty")


@dataclass(frozen=True)
class ResolvedRoute:
    """
    Result of agent routing — the selected agent and session key.

    Attributes:
        agent_id: Selected agent identifier.
        matched_by: How the route was resolved — one of:
            "binding.peer", "binding.guild", "binding.team",
            "binding.account", "binding.channel", "intent", "default".
        session_key: Session isolation key for conversation state.
        agent_config: Resolved AgentConfig (None if not found).
    """

    agent_id: str
    matched_by: str
    session_key: str
    agent_config: "AgentConfig | None" = field(default=None)

    def __post_init__(self) -> None:
        """
        Validate resolved route.

        Raises:
            ValueError: If agent_id or session_key is empty.
        """
        if not self.agent_id:
            raise ValueError("agent_id cannot be empty")
        if not self.session_key:
            raise ValueError("session_key cannot be empty")
