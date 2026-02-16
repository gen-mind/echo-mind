"""
Unit tests for SessionManager JSONL I/O.

Tests cover session creation, message appending, history loading,
file sanitization, and error handling.
"""

import json
from pathlib import Path

import pytest

from agent.sessions.manager import SessionManager
from agent.sessions.models import SessionHeader, SessionMessageEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def manager(tmp_path: Path) -> SessionManager:
    """Create a SessionManager using a temporary directory."""
    return SessionManager(sessions_dir=str(tmp_path))


@pytest.fixture()
def session_key() -> str:
    """Standard session key for tests."""
    return "agent:assistant:discord:main"


# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------


class TestCreateSession:
    """Tests for SessionManager.create_session."""

    def test_creates_file(self, manager: SessionManager, session_key: str) -> None:
        """create_session creates a JSONL file on disk."""
        manager.create_session(session_key, agent_id="assistant")
        session_file = manager._get_session_file(session_key)
        assert session_file.exists()

    def test_returns_session_id(self, manager: SessionManager, session_key: str) -> None:
        """create_session returns a session_xxx ID."""
        sid = manager.create_session(session_key, agent_id="assistant")
        assert sid.startswith("session_")
        assert len(sid) == len("session_") + 12

    def test_writes_valid_header(self, manager: SessionManager, session_key: str) -> None:
        """First line of file is a valid SessionHeader."""
        manager.create_session(session_key, agent_id="assistant", cwd="/home")
        header = manager.load_header(session_key)
        assert header is not None
        assert header.type == "session"
        assert header.version == 3
        assert header.agent_id == "assistant"
        assert header.cwd == "/home"
        assert header.session_key == session_key

    def test_unique_session_ids(self, manager: SessionManager) -> None:
        """Each call generates a unique session ID."""
        id1 = manager.create_session("key1", agent_id="a")
        id2 = manager.create_session("key2", agent_id="a")
        assert id1 != id2


# ---------------------------------------------------------------------------
# append_message
# ---------------------------------------------------------------------------


class TestAppendMessage:
    """Tests for SessionManager.append_message."""

    def test_appends_message(self, manager: SessionManager, session_key: str) -> None:
        """append_message adds a message line to the JSONL file."""
        manager.create_session(session_key, agent_id="assistant")
        msg_id = manager.append_message(session_key, role="user", content="Hello")
        assert msg_id.startswith("msg_")

        messages = manager.load_history(session_key)
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content == "Hello"

    def test_parent_id_chain(self, manager: SessionManager, session_key: str) -> None:
        """Messages can form a parent chain."""
        manager.create_session(session_key, agent_id="assistant")
        m1 = manager.append_message(session_key, role="user", content="Q1")
        m2 = manager.append_message(session_key, role="assistant", content="A1", parent_id=m1)

        messages = manager.load_history(session_key)
        assert messages[0].parent_id is None
        assert messages[1].parent_id == m1

    def test_with_tool_calls(self, manager: SessionManager, session_key: str) -> None:
        """Messages with tool_calls are persisted correctly."""
        manager.create_session(session_key, agent_id="assistant")
        calls = [{"name": "bash", "args": {"cmd": "ls"}}]
        manager.append_message(
            session_key, role="assistant", content="Running...", tool_calls=calls
        )

        messages = manager.load_history(session_key)
        assert messages[0].tool_calls == calls

    def test_no_file_raises(self, manager: SessionManager) -> None:
        """append_message raises FileNotFoundError if session doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Session file not found"):
            manager.append_message("nonexistent", role="user", content="Hi")

    def test_unique_message_ids(self, manager: SessionManager, session_key: str) -> None:
        """Each message gets a unique ID."""
        manager.create_session(session_key, agent_id="assistant")
        m1 = manager.append_message(session_key, role="user", content="a")
        m2 = manager.append_message(session_key, role="user", content="b")
        assert m1 != m2


# ---------------------------------------------------------------------------
# load_history
# ---------------------------------------------------------------------------


class TestLoadHistory:
    """Tests for SessionManager.load_history."""

    def test_empty_when_no_file(self, manager: SessionManager) -> None:
        """load_history returns empty list when session doesn't exist."""
        messages = manager.load_history("nonexistent")
        assert messages == []

    def test_skips_header(self, manager: SessionManager, session_key: str) -> None:
        """load_history skips the header line, returns only messages."""
        manager.create_session(session_key, agent_id="assistant")
        assert manager.load_history(session_key) == []

    def test_chronological_order(self, manager: SessionManager, session_key: str) -> None:
        """Messages are returned in chronological order."""
        manager.create_session(session_key, agent_id="assistant")
        manager.append_message(session_key, role="user", content="first")
        manager.append_message(session_key, role="assistant", content="second")
        manager.append_message(session_key, role="user", content="third")

        messages = manager.load_history(session_key)
        assert len(messages) == 3
        assert [m.content for m in messages] == ["first", "second", "third"]

    def test_max_messages_newest(self, manager: SessionManager, session_key: str) -> None:
        """max_messages returns the newest N messages."""
        manager.create_session(session_key, agent_id="assistant")
        for i in range(5):
            manager.append_message(session_key, role="user", content=f"msg{i}")

        messages = manager.load_history(session_key, max_messages=2)
        assert len(messages) == 2
        assert messages[0].content == "msg3"
        assert messages[1].content == "msg4"

    def test_max_messages_larger_than_total(
        self, manager: SessionManager, session_key: str
    ) -> None:
        """max_messages larger than total returns all messages."""
        manager.create_session(session_key, agent_id="assistant")
        manager.append_message(session_key, role="user", content="only")

        messages = manager.load_history(session_key, max_messages=100)
        assert len(messages) == 1

    def test_skips_malformed_json(
        self, manager: SessionManager, session_key: str
    ) -> None:
        """Malformed JSON lines are skipped with a warning."""
        manager.create_session(session_key, agent_id="assistant")
        manager.append_message(session_key, role="user", content="good")

        # Manually append a malformed line
        session_file = manager._get_session_file(session_key)
        with open(session_file, "a", encoding="utf-8") as f:
            f.write("not valid json\n")

        manager.append_message(session_key, role="assistant", content="also good")

        messages = manager.load_history(session_key)
        assert len(messages) == 2
        assert messages[0].content == "good"
        assert messages[1].content == "also good"

    def test_skips_invalid_message_entry(
        self, manager: SessionManager, session_key: str
    ) -> None:
        """Valid JSON but invalid message entries are skipped."""
        manager.create_session(session_key, agent_id="assistant")

        # Append a line with type=message but missing required fields
        session_file = manager._get_session_file(session_key)
        with open(session_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "message", "id": ""}) + "\n")

        messages = manager.load_history(session_key)
        assert messages == []


# ---------------------------------------------------------------------------
# load_header
# ---------------------------------------------------------------------------


class TestLoadHeader:
    """Tests for SessionManager.load_header."""

    def test_returns_none_no_file(self, manager: SessionManager) -> None:
        """load_header returns None if file doesn't exist."""
        assert manager.load_header("nonexistent") is None

    def test_returns_none_empty_file(self, manager: SessionManager) -> None:
        """load_header returns None for empty file."""
        session_file = manager._get_session_file("empty_key")
        session_file.touch()
        assert manager.load_header("empty_key") is None

    def test_returns_header(self, manager: SessionManager, session_key: str) -> None:
        """load_header returns the session header."""
        sid = manager.create_session(session_key, agent_id="coder")
        header = manager.load_header(session_key)
        assert header is not None
        assert header.id == sid
        assert header.agent_id == "coder"

    def test_returns_none_corrupt_header(self, manager: SessionManager) -> None:
        """load_header returns None when header JSON is corrupt."""
        session_file = manager._get_session_file("corrupt_key")
        with open(session_file, "w", encoding="utf-8") as f:
            f.write("not valid json\n")
        assert manager.load_header("corrupt_key") is None

    def test_returns_none_invalid_header_fields(self, manager: SessionManager) -> None:
        """load_header returns None when header has invalid fields."""
        import json

        session_file = manager._get_session_file("bad_fields")
        with open(session_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "wrong", "version": 3, "id": "x"}) + "\n")
        assert manager.load_header("bad_fields") is None


# ---------------------------------------------------------------------------
# load_history — empty line handling
# ---------------------------------------------------------------------------


class TestLoadHistoryEmptyLines:
    """Tests for empty line handling in load_history."""

    def test_skips_empty_lines(self, manager: SessionManager, session_key: str) -> None:
        """Empty lines in JSONL file are skipped gracefully."""
        manager.create_session(session_key, agent_id="assistant")
        manager.append_message(session_key, role="user", content="before")

        # Manually insert empty lines
        session_file = manager._get_session_file(session_key)
        with open(session_file, "a", encoding="utf-8") as f:
            f.write("\n\n")

        manager.append_message(session_key, role="assistant", content="after")

        messages = manager.load_history(session_key)
        assert len(messages) == 2
        assert messages[0].content == "before"
        assert messages[1].content == "after"


# ---------------------------------------------------------------------------
# session_exists
# ---------------------------------------------------------------------------


class TestSessionExists:
    """Tests for SessionManager.session_exists."""

    def test_false_when_missing(self, manager: SessionManager) -> None:
        """session_exists returns False for nonexistent session."""
        assert manager.session_exists("nope") is False

    def test_true_when_exists(self, manager: SessionManager, session_key: str) -> None:
        """session_exists returns True after creation."""
        manager.create_session(session_key, agent_id="assistant")
        assert manager.session_exists(session_key) is True


# ---------------------------------------------------------------------------
# _get_session_file
# ---------------------------------------------------------------------------


class TestGetSessionFile:
    """Tests for SessionManager._get_session_file."""

    def test_sanitizes_colons(self, manager: SessionManager) -> None:
        """Colons in session key are replaced with underscores."""
        path = manager._get_session_file("agent:assistant:discord:main")
        assert path.name == "agent_assistant_discord_main.jsonl"

    def test_sanitizes_slashes(self, manager: SessionManager) -> None:
        """Slashes in session key are replaced with underscores."""
        path = manager._get_session_file("agent/assistant/test")
        assert path.name == "agent_assistant_test.jsonl"

    def test_mixed_separators(self, manager: SessionManager) -> None:
        """Mixed colons and slashes are all replaced."""
        path = manager._get_session_file("a:b/c:d")
        assert path.name == "a_b_c_d.jsonl"


# ---------------------------------------------------------------------------
# Session isolation
# ---------------------------------------------------------------------------


class TestSessionIsolation:
    """Tests for cross-session isolation."""

    def test_separate_sessions(self, manager: SessionManager) -> None:
        """Messages in different sessions don't cross-contaminate."""
        manager.create_session("key_a", agent_id="a")
        manager.create_session("key_b", agent_id="b")

        manager.append_message("key_a", role="user", content="message for A")
        manager.append_message("key_b", role="user", content="message for B")

        msgs_a = manager.load_history("key_a")
        msgs_b = manager.load_history("key_b")

        assert len(msgs_a) == 1
        assert msgs_a[0].content == "message for A"
        assert len(msgs_b) == 1
        assert msgs_b[0].content == "message for B"


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------


class TestIdGeneration:
    """Tests for ID generation helpers."""

    def test_session_id_format(self, manager: SessionManager) -> None:
        """Session IDs follow session_{12 hex} format."""
        sid = manager._generate_session_id()
        assert sid.startswith("session_")
        hex_part = sid[len("session_"):]
        assert len(hex_part) == 12
        int(hex_part, 16)  # validates hex

    def test_message_id_format(self, manager: SessionManager) -> None:
        """Message IDs follow msg_{12 hex} format."""
        mid = manager._generate_message_id()
        assert mid.startswith("msg_")
        hex_part = mid[len("msg_"):]
        assert len(hex_part) == 12
        int(hex_part, 16)  # validates hex
