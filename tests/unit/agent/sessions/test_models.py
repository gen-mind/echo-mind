"""
Unit tests for session data models.

Tests cover SessionHeader, SessionMessageEntry, and SessionConfig
construction, validation, serialization, and immutability.
"""

import pytest

from agent.config.schema import SessionConfig
from agent.sessions.models import SessionHeader, SessionMessageEntry


# ---------------------------------------------------------------------------
# SessionHeader
# ---------------------------------------------------------------------------


class TestSessionHeader:
    """Tests for SessionHeader dataclass."""

    def test_create_valid_header(self) -> None:
        """SessionHeader with valid fields is accepted."""
        header = SessionHeader(
            type="session",
            version=3,
            id="session_abc123",
            timestamp="2026-02-16T10:00:00+00:00",
            cwd="/home/user/project",
            agent_id="assistant",
            session_key="agent:assistant:discord:main",
        )
        assert header.type == "session"
        assert header.version == 3
        assert header.id == "session_abc123"
        assert header.agent_id == "assistant"

    def test_frozen_immutability(self) -> None:
        """SessionHeader is frozen — attributes cannot be reassigned."""
        header = SessionHeader(
            type="session",
            version=3,
            id="session_abc123",
            timestamp="2026-02-16T10:00:00+00:00",
            cwd="/home/user",
            agent_id="assistant",
            session_key="key",
        )
        with pytest.raises(AttributeError):
            header.id = "other"  # type: ignore[misc]

    def test_invalid_type_raises(self) -> None:
        """Invalid type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid type"):
            SessionHeader(
                type="invalid",
                version=3,
                id="session_abc",
                timestamp="2026-02-16T10:00:00+00:00",
                cwd="/home",
                agent_id="assistant",
                session_key="key",
            )

    def test_invalid_version_raises(self) -> None:
        """Invalid version raises ValueError."""
        with pytest.raises(ValueError, match="Invalid version"):
            SessionHeader(
                type="session",
                version=1,
                id="session_abc",
                timestamp="2026-02-16T10:00:00+00:00",
                cwd="/home",
                agent_id="assistant",
                session_key="key",
            )

    def test_empty_id_raises(self) -> None:
        """Empty id raises ValueError."""
        with pytest.raises(ValueError, match="Session id cannot be empty"):
            SessionHeader(
                type="session",
                version=3,
                id="",
                timestamp="2026-02-16T10:00:00+00:00",
                cwd="/home",
                agent_id="assistant",
                session_key="key",
            )

    def test_whitespace_id_raises(self) -> None:
        """Whitespace-only id raises ValueError."""
        with pytest.raises(ValueError, match="Session id cannot be empty"):
            SessionHeader(
                type="session",
                version=3,
                id="   ",
                timestamp="2026-02-16T10:00:00+00:00",
                cwd="/home",
                agent_id="assistant",
                session_key="key",
            )

    def test_to_dict(self) -> None:
        """to_dict produces camelCase keys."""
        header = SessionHeader(
            type="session",
            version=3,
            id="session_abc",
            timestamp="2026-02-16T10:00:00+00:00",
            cwd="/home",
            agent_id="assistant",
            session_key="key:1",
        )
        d = header.to_dict()
        assert d == {
            "type": "session",
            "version": 3,
            "id": "session_abc",
            "timestamp": "2026-02-16T10:00:00+00:00",
            "cwd": "/home",
            "agentId": "assistant",
            "sessionKey": "key:1",
        }

    def test_from_dict(self) -> None:
        """from_dict parses camelCase keys into snake_case fields."""
        data = {
            "type": "session",
            "version": 3,
            "id": "session_xyz",
            "timestamp": "2026-02-16T12:00:00+00:00",
            "cwd": "/tmp",
            "agentId": "coder",
            "sessionKey": "agent:coder:slack:dm:u1",
        }
        header = SessionHeader.from_dict(data)
        assert header.id == "session_xyz"
        assert header.agent_id == "coder"
        assert header.session_key == "agent:coder:slack:dm:u1"

    def test_roundtrip(self) -> None:
        """to_dict -> from_dict roundtrip preserves all fields."""
        original = SessionHeader(
            type="session",
            version=3,
            id="session_rt",
            timestamp="2026-02-16T10:00:00+00:00",
            cwd="/project",
            agent_id="researcher",
            session_key="agent:researcher:test:main",
        )
        restored = SessionHeader.from_dict(original.to_dict())
        assert original == restored

    def test_create_factory(self) -> None:
        """create() auto-generates timestamp and sets type/version."""
        header = SessionHeader.create(
            session_id="session_new",
            cwd="/work",
            agent_id="assistant",
            session_key="key:new",
        )
        assert header.type == "session"
        assert header.version == 3
        assert header.id == "session_new"
        assert header.timestamp  # non-empty ISO timestamp

    def test_equality(self) -> None:
        """Two SessionHeaders with same values are equal."""
        kwargs = dict(
            type="session",
            version=3,
            id="session_eq",
            timestamp="2026-02-16T10:00:00+00:00",
            cwd="/home",
            agent_id="assistant",
            session_key="key",
        )
        assert SessionHeader(**kwargs) == SessionHeader(**kwargs)

    def test_hashable(self) -> None:
        """SessionHeader can be used in sets (frozen=True)."""
        kwargs = dict(
            type="session",
            version=3,
            id="session_h",
            timestamp="2026-02-16T10:00:00+00:00",
            cwd="/home",
            agent_id="assistant",
            session_key="key",
        )
        h1 = SessionHeader(**kwargs)
        h2 = SessionHeader(**kwargs)
        assert {h1, h2} == {h1}


# ---------------------------------------------------------------------------
# SessionMessageEntry
# ---------------------------------------------------------------------------


class TestSessionMessageEntry:
    """Tests for SessionMessageEntry dataclass."""

    def test_create_valid_message(self) -> None:
        """SessionMessageEntry with valid fields is accepted."""
        entry = SessionMessageEntry(
            type="message",
            id="msg_abc123",
            parent_id=None,
            timestamp="2026-02-16T10:00:00+00:00",
            role="user",
            content="Hello",
        )
        assert entry.type == "message"
        assert entry.id == "msg_abc123"
        assert entry.parent_id is None
        assert entry.role == "user"
        assert entry.content == "Hello"
        assert entry.tool_calls is None

    def test_with_tool_calls(self) -> None:
        """SessionMessageEntry with tool_calls is accepted."""
        calls = [{"name": "read_file", "args": {"path": "/tmp/f.txt"}}]
        entry = SessionMessageEntry(
            type="message",
            id="msg_tc",
            parent_id="msg_prev",
            timestamp="2026-02-16T10:00:00+00:00",
            role="assistant",
            content="Let me read that file.",
            tool_calls=calls,
        )
        assert entry.tool_calls == calls
        assert entry.parent_id == "msg_prev"

    def test_all_valid_roles(self) -> None:
        """All valid roles are accepted."""
        for role in ("user", "assistant", "system", "tool"):
            entry = SessionMessageEntry(
                type="message",
                id=f"msg_{role}",
                parent_id=None,
                timestamp="2026-02-16T10:00:00+00:00",
                role=role,
                content="test",
            )
            assert entry.role == role

    def test_frozen_immutability(self) -> None:
        """SessionMessageEntry is frozen — attributes cannot be reassigned."""
        entry = SessionMessageEntry(
            type="message",
            id="msg_frz",
            parent_id=None,
            timestamp="2026-02-16T10:00:00+00:00",
            role="user",
            content="hi",
        )
        with pytest.raises(AttributeError):
            entry.content = "bye"  # type: ignore[misc]

    def test_invalid_type_raises(self) -> None:
        """Invalid type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid type"):
            SessionMessageEntry(
                type="event",
                id="msg_bad",
                parent_id=None,
                timestamp="2026-02-16T10:00:00+00:00",
                role="user",
                content="test",
            )

    def test_empty_id_raises(self) -> None:
        """Empty id raises ValueError."""
        with pytest.raises(ValueError, match="Message id cannot be empty"):
            SessionMessageEntry(
                type="message",
                id="",
                parent_id=None,
                timestamp="2026-02-16T10:00:00+00:00",
                role="user",
                content="test",
            )

    def test_invalid_role_raises(self) -> None:
        """Invalid role raises ValueError."""
        with pytest.raises(ValueError, match="Invalid role"):
            SessionMessageEntry(
                type="message",
                id="msg_bad",
                parent_id=None,
                timestamp="2026-02-16T10:00:00+00:00",
                role="admin",
                content="test",
            )

    def test_to_dict_without_tool_calls(self) -> None:
        """to_dict omits toolCalls when None."""
        entry = SessionMessageEntry(
            type="message",
            id="msg_d1",
            parent_id="msg_d0",
            timestamp="2026-02-16T10:00:00+00:00",
            role="user",
            content="Hi there",
        )
        d = entry.to_dict()
        assert d == {
            "type": "message",
            "id": "msg_d1",
            "parentId": "msg_d0",
            "timestamp": "2026-02-16T10:00:00+00:00",
            "role": "user",
            "content": "Hi there",
        }
        assert "toolCalls" not in d

    def test_to_dict_with_tool_calls(self) -> None:
        """to_dict includes toolCalls when present."""
        calls = [{"name": "bash", "args": {"cmd": "ls"}}]
        entry = SessionMessageEntry(
            type="message",
            id="msg_d2",
            parent_id=None,
            timestamp="2026-02-16T10:00:00+00:00",
            role="assistant",
            content="Running command.",
            tool_calls=calls,
        )
        d = entry.to_dict()
        assert d["toolCalls"] == calls

    def test_from_dict(self) -> None:
        """from_dict parses camelCase keys."""
        data = {
            "type": "message",
            "id": "msg_fd",
            "parentId": "msg_prev",
            "timestamp": "2026-02-16T10:00:00+00:00",
            "role": "assistant",
            "content": "Sure!",
            "toolCalls": [{"name": "grep"}],
        }
        entry = SessionMessageEntry.from_dict(data)
        assert entry.id == "msg_fd"
        assert entry.parent_id == "msg_prev"
        assert entry.tool_calls == [{"name": "grep"}]

    def test_from_dict_missing_optional(self) -> None:
        """from_dict handles missing parentId and toolCalls."""
        data = {
            "type": "message",
            "id": "msg_min",
            "timestamp": "2026-02-16T10:00:00+00:00",
            "role": "user",
            "content": "hello",
        }
        entry = SessionMessageEntry.from_dict(data)
        assert entry.parent_id is None
        assert entry.tool_calls is None

    def test_roundtrip(self) -> None:
        """to_dict -> from_dict roundtrip preserves all fields."""
        original = SessionMessageEntry(
            type="message",
            id="msg_rt",
            parent_id="msg_p",
            timestamp="2026-02-16T10:00:00+00:00",
            role="tool",
            content="result: 42",
            tool_calls=[{"name": "calc", "result": "42"}],
        )
        restored = SessionMessageEntry.from_dict(original.to_dict())
        assert original == restored

    def test_create_factory(self) -> None:
        """create() auto-generates timestamp and sets type."""
        entry = SessionMessageEntry.create(
            message_id="msg_new",
            role="user",
            content="What is 2+2?",
            parent_id="msg_prev",
        )
        assert entry.type == "message"
        assert entry.id == "msg_new"
        assert entry.role == "user"
        assert entry.parent_id == "msg_prev"
        assert entry.timestamp  # non-empty


# ---------------------------------------------------------------------------
# SessionConfig
# ---------------------------------------------------------------------------


class TestSessionConfig:
    """Tests for SessionConfig dataclass."""

    def test_default_values(self) -> None:
        """SessionConfig defaults are correct."""
        config = SessionConfig()
        assert config.sessions_dir == "data/sessions"
        assert config.max_messages is None

    def test_custom_values(self) -> None:
        """SessionConfig accepts custom values."""
        config = SessionConfig(sessions_dir="/tmp/sessions", max_messages=100)
        assert config.sessions_dir == "/tmp/sessions"
        assert config.max_messages == 100

    def test_zero_max_messages(self) -> None:
        """SessionConfig accepts zero max_messages."""
        config = SessionConfig(max_messages=0)
        assert config.max_messages == 0

    def test_empty_sessions_dir_raises(self) -> None:
        """Empty sessions_dir raises ValueError."""
        with pytest.raises(ValueError, match="sessions_dir cannot be empty"):
            SessionConfig(sessions_dir="")

    def test_whitespace_sessions_dir_raises(self) -> None:
        """Whitespace-only sessions_dir raises ValueError."""
        with pytest.raises(ValueError, match="sessions_dir cannot be empty"):
            SessionConfig(sessions_dir="   ")

    def test_negative_max_messages_raises(self) -> None:
        """Negative max_messages raises ValueError."""
        with pytest.raises(ValueError, match="max_messages cannot be negative"):
            SessionConfig(max_messages=-1)
