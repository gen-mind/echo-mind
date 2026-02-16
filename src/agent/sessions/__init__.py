"""
Session management for agent conversation persistence.

Provides JSONL-based session storage with Microsoft Agent Framework integration.
"""

from .manager import SessionManager
from .models import SessionHeader, SessionMessageEntry
from .provider import JSONLHistoryProvider

__all__ = [
    "JSONLHistoryProvider",
    "SessionHeader",
    "SessionManager",
    "SessionMessageEntry",
]
