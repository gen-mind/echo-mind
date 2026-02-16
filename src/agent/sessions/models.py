"""
Session data models for JSONL-based conversation persistence.

Defines the core value objects stored in session files:
SessionHeader (first line) and SessionMessageEntry (subsequent lines).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_VALID_ROLES = frozenset({"user", "assistant", "system", "tool"})

_SESSION_HEADER_TYPE = "session"
_SESSION_VERSION = 3
_MESSAGE_ENTRY_TYPE = "message"


@dataclass(frozen=True)
class SessionHeader:
    """
    First line of a JSONL session file — session metadata.

    Attributes:
        type: Entry type, always "session".
        version: Schema version (currently 3).
        id: Session UUID (e.g. "session_abc123def456").
        timestamp: ISO 8601 creation timestamp.
        cwd: Working directory when session was created.
        agent_id: Agent that owns this session.
        session_key: Routing session key for isolation.
    """

    type: str
    version: int
    id: str
    timestamp: str
    cwd: str
    agent_id: str
    session_key: str

    def __post_init__(self) -> None:
        """
        Validate session header fields.

        Raises:
            ValueError: If type is not "session", version is not 3,
                or id is empty.
        """
        if self.type != _SESSION_HEADER_TYPE:
            raise ValueError(
                f"Invalid type '{self.type}'. Must be '{_SESSION_HEADER_TYPE}'"
            )
        if self.version != _SESSION_VERSION:
            raise ValueError(
                f"Invalid version {self.version}. Must be {_SESSION_VERSION}"
            )
        if not self.id or not self.id.strip():
            raise ValueError("Session id cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize header to a dictionary suitable for JSON.

        Returns:
            Dictionary representation of the session header.
        """
        return {
            "type": self.type,
            "version": self.version,
            "id": self.id,
            "timestamp": self.timestamp,
            "cwd": self.cwd,
            "agentId": self.agent_id,
            "sessionKey": self.session_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionHeader:
        """
        Deserialize a dictionary into a SessionHeader.

        Args:
            data: Dictionary with session header fields.
                Uses camelCase keys (agentId, sessionKey).

        Returns:
            Validated SessionHeader instance.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If validation fails.
        """
        return cls(
            type=data["type"],
            version=data["version"],
            id=data["id"],
            timestamp=data["timestamp"],
            cwd=data["cwd"],
            agent_id=data["agentId"],
            session_key=data["sessionKey"],
        )

    @classmethod
    def create(
        cls,
        session_id: str,
        cwd: str,
        agent_id: str,
        session_key: str,
    ) -> SessionHeader:
        """
        Create a new SessionHeader with auto-generated timestamp.

        Args:
            session_id: Unique session identifier.
            cwd: Working directory.
            agent_id: Agent identifier.
            session_key: Routing session key.

        Returns:
            New SessionHeader with current UTC timestamp.
        """
        return cls(
            type=_SESSION_HEADER_TYPE,
            version=_SESSION_VERSION,
            id=session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            cwd=cwd,
            agent_id=agent_id,
            session_key=session_key,
        )


@dataclass(frozen=True)
class SessionMessageEntry:
    """
    A single message line in a JSONL session file.

    Attributes:
        type: Entry type, always "message".
        id: Message UUID (e.g. "msg_abc123def456").
        parent_id: Previous message ID (None for first message).
        timestamp: ISO 8601 timestamp.
        role: Message role — "user", "assistant", "system", or "tool".
        content: Message text content.
        tool_calls: Optional list of tool call dicts.
    """

    type: str
    id: str
    parent_id: str | None
    timestamp: str
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = field(default=None)

    def __post_init__(self) -> None:
        """
        Validate message entry fields.

        Raises:
            ValueError: If type is not "message", id is empty,
                or role is invalid.
        """
        if self.type != _MESSAGE_ENTRY_TYPE:
            raise ValueError(
                f"Invalid type '{self.type}'. Must be '{_MESSAGE_ENTRY_TYPE}'"
            )
        if not self.id or not self.id.strip():
            raise ValueError("Message id cannot be empty")
        if self.role not in _VALID_ROLES:
            raise ValueError(
                f"Invalid role '{self.role}'. "
                f"Must be one of: {', '.join(sorted(_VALID_ROLES))}"
            )

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize message entry to a dictionary suitable for JSON.

        Returns:
            Dictionary representation of the message entry.
            Omits tool_calls if None.
        """
        result: dict[str, Any] = {
            "type": self.type,
            "id": self.id,
            "parentId": self.parent_id,
            "timestamp": self.timestamp,
            "role": self.role,
            "content": self.content,
        }
        if self.tool_calls is not None:
            result["toolCalls"] = self.tool_calls
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMessageEntry:
        """
        Deserialize a dictionary into a SessionMessageEntry.

        Args:
            data: Dictionary with message entry fields.
                Uses camelCase keys (parentId, toolCalls).

        Returns:
            Validated SessionMessageEntry instance.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If validation fails.
        """
        return cls(
            type=data["type"],
            id=data["id"],
            parent_id=data.get("parentId"),
            timestamp=data["timestamp"],
            role=data["role"],
            content=data["content"],
            tool_calls=data.get("toolCalls"),
        )

    @classmethod
    def create(
        cls,
        message_id: str,
        role: str,
        content: str,
        parent_id: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> SessionMessageEntry:
        """
        Create a new SessionMessageEntry with auto-generated timestamp.

        Args:
            message_id: Unique message identifier.
            role: Message role (user/assistant/system/tool).
            content: Message text.
            parent_id: ID of the preceding message.
            tool_calls: Optional tool call data.

        Returns:
            New SessionMessageEntry with current UTC timestamp.
        """
        return cls(
            type=_MESSAGE_ENTRY_TYPE,
            id=message_id,
            parent_id=parent_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            role=role,
            content=content,
            tool_calls=tool_calls,
        )
