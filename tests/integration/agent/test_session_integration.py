"""
Integration tests for session management.

Tests cover end-to-end flows: config loading → session creation →
message persistence → history retrieval → provider integration.
"""

from pathlib import Path

import pytest
import yaml

from agent.config.parser import ConfigParser
from agent.sessions.manager import SessionManager
from agent.sessions.models import SessionHeader, SessionMessageEntry
from agent.sessions.provider import JSONLHistoryProvider
from agent_framework import Message


# ---------------------------------------------------------------------------
# Config integration
# ---------------------------------------------------------------------------


class TestConfigIntegration:
    """Tests that session config loads from real config.yaml."""

    def test_config_has_session_section(self) -> None:
        """Real config.yaml includes session configuration."""
        parser = ConfigParser("config/agents/config.yaml")
        config = parser.load()
        assert config.session is not None
        assert config.session.sessions_dir == "data/sessions"

    def test_config_session_defaults(self) -> None:
        """Session config has correct defaults."""
        parser = ConfigParser("config/agents/config.yaml")
        config = parser.load()
        assert config.session.max_messages is None


# ---------------------------------------------------------------------------
# SessionManager end-to-end
# ---------------------------------------------------------------------------


class TestSessionManagerEndToEnd:
    """End-to-end tests for SessionManager JSONL I/O."""

    def test_full_lifecycle(self, tmp_path: Path) -> None:
        """Complete session lifecycle: create → append → load → verify."""
        manager = SessionManager(sessions_dir=str(tmp_path))
        key = "agent:assistant:test:dm:user1"

        # Create session
        session_id = manager.create_session(key, agent_id="assistant", cwd="/project")
        assert session_id.startswith("session_")
        assert manager.session_exists(key)

        # Append messages
        m1 = manager.append_message(key, role="user", content="Hello")
        m2 = manager.append_message(
            key, role="assistant", content="Hi!", parent_id=m1
        )
        m3 = manager.append_message(
            key,
            role="assistant",
            content="Let me check.",
            parent_id=m2,
            tool_calls=[{"name": "read_file", "args": {"path": "README.md"}}],
        )

        # Load and verify
        messages = manager.load_history(key)
        assert len(messages) == 3
        assert messages[0].role == "user"
        assert messages[0].content == "Hello"
        assert messages[1].parent_id == m1
        assert messages[2].tool_calls == [
            {"name": "read_file", "args": {"path": "README.md"}}
        ]

        # Verify header
        header = manager.load_header(key)
        assert header is not None
        assert header.id == session_id
        assert header.agent_id == "assistant"
        assert header.session_key == key

    def test_max_messages_truncation(self, tmp_path: Path) -> None:
        """max_messages returns only the newest N messages."""
        manager = SessionManager(sessions_dir=str(tmp_path))
        key = "agent:coder:test:main"

        manager.create_session(key, agent_id="coder")
        for i in range(10):
            manager.append_message(key, role="user", content=f"Message {i}")

        messages = manager.load_history(key, max_messages=3)
        assert len(messages) == 3
        assert messages[0].content == "Message 7"
        assert messages[1].content == "Message 8"
        assert messages[2].content == "Message 9"

    def test_session_isolation(self, tmp_path: Path) -> None:
        """Different session keys produce isolated conversations."""
        manager = SessionManager(sessions_dir=str(tmp_path))

        manager.create_session("key_a", agent_id="a")
        manager.create_session("key_b", agent_id="b")

        manager.append_message("key_a", role="user", content="A says hello")
        manager.append_message("key_b", role="user", content="B says hi")

        assert len(manager.load_history("key_a")) == 1
        assert manager.load_history("key_a")[0].content == "A says hello"
        assert len(manager.load_history("key_b")) == 1
        assert manager.load_history("key_b")[0].content == "B says hi"

    def test_file_naming_convention(self, tmp_path: Path) -> None:
        """Session key is sanitized to filesystem-safe filename."""
        manager = SessionManager(sessions_dir=str(tmp_path))
        key = "agent:assistant:discord:dm:user123"

        manager.create_session(key, agent_id="assistant")

        expected_file = tmp_path / "agent_assistant_discord_dm_user123.jsonl"
        assert expected_file.exists()


# ---------------------------------------------------------------------------
# JSONLHistoryProvider end-to-end
# ---------------------------------------------------------------------------


class TestProviderEndToEnd:
    """End-to-end tests for JSONLHistoryProvider framework integration."""

    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Messages saved via provider load back correctly."""
        manager = SessionManager(sessions_dir=str(tmp_path))
        provider = JSONLHistoryProvider("history", manager)
        key = "agent:assistant:test:dm:roundtrip"

        # Save messages (auto-creates session)
        msgs = [
            Message("user", text="What is Python?"),
            Message("assistant", text="A programming language."),
        ]
        await provider.save_messages(key, msgs)

        # Load messages
        loaded = await provider.get_messages(key)
        assert len(loaded) == 2
        assert loaded[0].role == "user"
        assert loaded[0].text == "What is Python?"
        assert loaded[1].role == "assistant"
        assert loaded[1].text == "A programming language."

    @pytest.mark.asyncio
    async def test_incremental_conversation(self, tmp_path: Path) -> None:
        """Multiple save calls accumulate messages correctly."""
        manager = SessionManager(sessions_dir=str(tmp_path))
        provider = JSONLHistoryProvider("history", manager)
        key = "agent:assistant:test:dm:incremental"

        # Turn 1
        await provider.save_messages(key, [Message("user", text="Q1")])
        await provider.save_messages(key, [Message("assistant", text="A1")])

        # Turn 2
        await provider.save_messages(key, [Message("user", text="Q2")])
        await provider.save_messages(key, [Message("assistant", text="A2")])

        loaded = await provider.get_messages(key)
        assert len(loaded) == 4
        assert [m.text for m in loaded] == ["Q1", "A1", "Q2", "A2"]

    @pytest.mark.asyncio
    async def test_max_messages_via_provider(self, tmp_path: Path) -> None:
        """Provider respects max_messages setting."""
        manager = SessionManager(sessions_dir=str(tmp_path))
        provider = JSONLHistoryProvider("history", manager, max_messages=2)
        key = "agent:assistant:test:dm:maxmsg"

        manager.create_session(key, agent_id="assistant")
        for i in range(5):
            manager.append_message(key, role="user", content=f"msg{i}")

        loaded = await provider.get_messages(key)
        assert len(loaded) == 2
        assert loaded[0].text == "msg3"
        assert loaded[1].text == "msg4"

    @pytest.mark.asyncio
    async def test_auto_create_session(self, tmp_path: Path) -> None:
        """Provider auto-creates session on first save."""
        manager = SessionManager(sessions_dir=str(tmp_path))
        provider = JSONLHistoryProvider("auto-agent", manager)
        key = "agent:auto-agent:test:main"

        assert not manager.session_exists(key)

        await provider.save_messages(key, [Message("user", text="First")])

        assert manager.session_exists(key)
        header = manager.load_header(key)
        assert header is not None
        assert header.agent_id == "auto-agent"


# ---------------------------------------------------------------------------
# JSONL file format validation
# ---------------------------------------------------------------------------


class TestJSONLFormat:
    """Tests that verify JSONL file format compliance."""

    def test_jsonl_format_valid(self, tmp_path: Path) -> None:
        """Each line in the JSONL file is valid JSON."""
        import json

        manager = SessionManager(sessions_dir=str(tmp_path))
        key = "agent:assistant:test:main"

        manager.create_session(key, agent_id="assistant")
        manager.append_message(key, role="user", content="Hello")
        manager.append_message(key, role="assistant", content="Hi")

        session_file = manager._get_session_file(key)
        with open(session_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        assert len(lines) == 3  # header + 2 messages

        # All lines are valid JSON
        for i, line in enumerate(lines):
            data = json.loads(line)  # will raise if invalid
            assert isinstance(data, dict)

        # First line is header
        header = json.loads(lines[0])
        assert header["type"] == "session"
        assert header["version"] == 3

        # Remaining lines are messages
        for line in lines[1:]:
            msg = json.loads(line)
            assert msg["type"] == "message"
            assert msg["role"] in ("user", "assistant", "system", "tool")
