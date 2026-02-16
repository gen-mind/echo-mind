"""
Unit tests for JSONLHistoryProvider.

Tests cover message loading, saving, auto-creation, edge cases,
and roundtrip integration with SessionManager.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_framework import Message

from agent.sessions.manager import SessionManager
from agent.sessions.models import SessionMessageEntry
from agent.sessions.provider import JSONLHistoryProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def manager(tmp_path: Path) -> SessionManager:
    """Create a SessionManager using a temporary directory."""
    return SessionManager(sessions_dir=str(tmp_path))


@pytest.fixture()
def provider(manager: SessionManager) -> JSONLHistoryProvider:
    """Create a JSONLHistoryProvider with default settings."""
    return JSONLHistoryProvider("history", manager)


@pytest.fixture()
def session_key() -> str:
    """Standard session key for tests."""
    return "agent:assistant:test:main"


# ---------------------------------------------------------------------------
# get_messages
# ---------------------------------------------------------------------------


class TestGetMessages:
    """Tests for JSONLHistoryProvider.get_messages."""

    @pytest.mark.asyncio
    async def test_empty_history(
        self, provider: JSONLHistoryProvider, manager: SessionManager, session_key: str
    ) -> None:
        """get_messages returns [] for session with no messages."""
        manager.create_session(session_key, agent_id="assistant")
        messages = await provider.get_messages(session_key)
        assert messages == []

    @pytest.mark.asyncio
    async def test_loads_messages(
        self, provider: JSONLHistoryProvider, manager: SessionManager, session_key: str
    ) -> None:
        """get_messages converts SessionMessageEntry to framework Message."""
        manager.create_session(session_key, agent_id="assistant")
        manager.append_message(session_key, role="user", content="Hello")
        manager.append_message(session_key, role="assistant", content="Hi there")

        messages = await provider.get_messages(session_key)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].text == "Hello"
        assert messages[1].role == "assistant"
        assert messages[1].text == "Hi there"

    @pytest.mark.asyncio
    async def test_respects_max_messages(
        self, manager: SessionManager, session_key: str
    ) -> None:
        """get_messages respects max_messages setting."""
        provider = JSONLHistoryProvider("history", manager, max_messages=2)
        manager.create_session(session_key, agent_id="assistant")
        for i in range(5):
            manager.append_message(session_key, role="user", content=f"msg{i}")

        messages = await provider.get_messages(session_key)
        assert len(messages) == 2
        assert messages[0].text == "msg3"
        assert messages[1].text == "msg4"

    @pytest.mark.asyncio
    async def test_none_session_id(self, provider: JSONLHistoryProvider) -> None:
        """get_messages returns [] when session_id is None."""
        messages = await provider.get_messages(None)
        assert messages == []

    @pytest.mark.asyncio
    async def test_nonexistent_session(self, provider: JSONLHistoryProvider) -> None:
        """get_messages returns [] for nonexistent session."""
        messages = await provider.get_messages("nonexistent_key")
        assert messages == []


# ---------------------------------------------------------------------------
# save_messages
# ---------------------------------------------------------------------------


class TestSaveMessages:
    """Tests for JSONLHistoryProvider.save_messages."""

    @pytest.mark.asyncio
    async def test_saves_messages(
        self, provider: JSONLHistoryProvider, manager: SessionManager, session_key: str
    ) -> None:
        """save_messages appends messages to JSONL via manager."""
        manager.create_session(session_key, agent_id="assistant")

        msgs = [
            Message("user", text="Question"),
            Message("assistant", text="Answer"),
        ]
        await provider.save_messages(session_key, msgs)

        history = manager.load_history(session_key)
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[0].content == "Question"
        assert history[1].role == "assistant"
        assert history[1].content == "Answer"

    @pytest.mark.asyncio
    async def test_auto_creates_session(
        self, provider: JSONLHistoryProvider, manager: SessionManager, session_key: str
    ) -> None:
        """save_messages auto-creates session if it doesn't exist."""
        assert not manager.session_exists(session_key)

        msgs = [Message("user", text="First message")]
        await provider.save_messages(session_key, msgs)

        assert manager.session_exists(session_key)
        history = manager.load_history(session_key)
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_handles_none_text(
        self, provider: JSONLHistoryProvider, manager: SessionManager, session_key: str
    ) -> None:
        """save_messages handles Message with None text."""
        manager.create_session(session_key, agent_id="assistant")

        msgs = [Message("user")]  # text is None
        await provider.save_messages(session_key, msgs)

        history = manager.load_history(session_key)
        assert len(history) == 1
        assert history[0].content == ""

    @pytest.mark.asyncio
    async def test_none_session_id_skips(
        self, provider: JSONLHistoryProvider
    ) -> None:
        """save_messages silently skips when session_id is None."""
        msgs = [Message("user", text="Hello")]
        await provider.save_messages(None, msgs)
        # No error, no file created

    @pytest.mark.asyncio
    async def test_parent_id_chain(
        self, provider: JSONLHistoryProvider, manager: SessionManager, session_key: str
    ) -> None:
        """save_messages builds parent_id chain across messages."""
        manager.create_session(session_key, agent_id="assistant")

        msgs = [
            Message("user", text="Q1"),
            Message("assistant", text="A1"),
            Message("user", text="Q2"),
        ]
        await provider.save_messages(session_key, msgs)

        history = manager.load_history(session_key)
        assert len(history) == 3
        # First message has no parent
        assert history[0].parent_id is None
        # Each subsequent message references the previous
        assert history[1].parent_id is not None
        assert history[2].parent_id is not None
        assert history[1].parent_id != history[2].parent_id

    @pytest.mark.asyncio
    async def test_empty_messages_list(
        self, provider: JSONLHistoryProvider, manager: SessionManager, session_key: str
    ) -> None:
        """save_messages with empty list does nothing (but may auto-create session)."""
        await provider.save_messages(session_key, [])
        # Session was auto-created but no messages appended
        assert manager.session_exists(session_key)
        assert manager.load_history(session_key) == []


# ---------------------------------------------------------------------------
# Roundtrip integration
# ---------------------------------------------------------------------------


class TestRoundtrip:
    """Tests for load → save → load roundtrip."""

    @pytest.mark.asyncio
    async def test_save_then_load(
        self, provider: JSONLHistoryProvider, manager: SessionManager, session_key: str
    ) -> None:
        """Messages saved via provider can be loaded back."""
        msgs = [
            Message("user", text="What is Python?"),
            Message("assistant", text="A programming language."),
        ]
        await provider.save_messages(session_key, msgs)

        loaded = await provider.get_messages(session_key)
        assert len(loaded) == 2
        assert loaded[0].role == "user"
        assert loaded[0].text == "What is Python?"
        assert loaded[1].role == "assistant"
        assert loaded[1].text == "A programming language."

    @pytest.mark.asyncio
    async def test_incremental_saves(
        self, provider: JSONLHistoryProvider, manager: SessionManager, session_key: str
    ) -> None:
        """Multiple save calls accumulate messages."""
        manager.create_session(session_key, agent_id="assistant")

        await provider.save_messages(session_key, [Message("user", text="Hi")])
        await provider.save_messages(session_key, [Message("assistant", text="Hello!")])

        loaded = await provider.get_messages(session_key)
        assert len(loaded) == 2
        assert loaded[0].text == "Hi"
        assert loaded[1].text == "Hello!"


# ---------------------------------------------------------------------------
# Configuration flags
# ---------------------------------------------------------------------------


class TestConfiguration:
    """Tests for provider configuration flags."""

    def test_default_flags(self, manager: SessionManager) -> None:
        """Default configuration flags are correct."""
        provider = JSONLHistoryProvider("test", manager)
        assert provider.load_messages is True
        assert provider.store_inputs is True
        assert provider.store_outputs is True
        assert provider.max_messages is None

    def test_custom_flags(self, manager: SessionManager) -> None:
        """Custom flags are preserved."""
        provider = JSONLHistoryProvider(
            "test",
            manager,
            max_messages=50,
            load_messages=False,
            store_inputs=False,
            store_outputs=False,
        )
        assert provider.load_messages is False
        assert provider.store_inputs is False
        assert provider.store_outputs is False
        assert provider.max_messages == 50
