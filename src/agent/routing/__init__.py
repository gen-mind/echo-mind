"""
Routing & Agent Selection for Agent System.

Implements a 5-tier agent routing system that selects the correct agent
based on incoming message context. Includes session key building for
conversation isolation and optional LLM-based intent fallback.

Tiers (highest to lowest priority):
    1. Peer — specific user/group/channel match
    2. Guild — Discord guild match
    3. Team — Slack workspace match
    4. Account — bot account match
    5. Channel — platform channel match
    6. Default — fallback agent from config
"""

from .intent import IntentClassifier
from .matcher import BindingMatcher
from .models import ResolvedRoute, RouteContext, RoutePeer
from .router import AgentRouter
from .session import SessionKeyBuilder

__all__ = [
    "AgentRouter",
    "BindingMatcher",
    "IntentClassifier",
    "ResolvedRoute",
    "RouteContext",
    "RoutePeer",
    "SessionKeyBuilder",
]
