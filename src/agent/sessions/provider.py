"""
JSONL-backed history provider for Microsoft Agent Framework.

Integrates SessionManager with the framework's BaseHistoryProvider hooks
so that conversation history is automatically loaded/saved from JSONL files.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from agent_framework import BaseHistoryProvider, Message

from .manager import SessionManager

logger = logging.getLogger(__name__)


class JSONLHistoryProvider(BaseHistoryProvider):
    """
    JSONL-backed conversation history provider.

    Loads messages from JSONL before each agent run and saves new
    messages after each run, integrating with the framework's
    before_run/after_run lifecycle hooks.

    Attributes:
        session_manager: SessionManager instance for JSONL I/O.
        max_messages: Maximum messages to load (None = unlimited).
    """

    def __init__(
        self,
        source_id: str,
        session_manager: SessionManager,
        *,
        max_messages: int | None = None,
        load_messages: bool = True,
        store_inputs: bool = True,
        store_outputs: bool = True,
    ) -> None:
        """
        Initialize JSONL history provider.

        Args:
            source_id: Unique identifier for this provider instance.
            session_manager: SessionManager for JSONL file operations.
            max_messages: Maximum messages to load per session (None = all).
            load_messages: Whether to load messages before invocation.
            store_inputs: Whether to store input messages.
            store_outputs: Whether to store response messages.
        """
        super().__init__(
            source_id,
            load_messages=load_messages,
            store_inputs=store_inputs,
            store_outputs=store_outputs,
        )
        self.session_manager = session_manager
        self.max_messages = max_messages

    async def get_messages(
        self,
        session_id: str | None,
        **kwargs: Any,
    ) -> list[Message]:
        """
        Load messages from JSONL via SessionManager.

        Converts SessionMessageEntry objects to framework Message objects.

        Args:
            session_id: Session key identifying the JSONL file.
                Returns empty list if None.
            **kwargs: Additional arguments (ignored).

        Returns:
            List of framework Message objects in chronological order.
        """
        if session_id is None:
            return []

        entries = self.session_manager.load_history(
            session_id,
            max_messages=self.max_messages,
        )

        messages: list[Message] = []
        for entry in entries:
            msg = Message(entry.role, [entry.content or ""])
            messages.append(msg)

        logger.debug(
            "📖 Loaded %d messages for session '%s'",
            len(messages),
            session_id,
        )
        return messages

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        **kwargs: Any,
    ) -> None:
        """
        Save messages to JSONL via SessionManager.

        Auto-creates the session file if it doesn't exist yet.

        Args:
            session_id: Session key identifying the JSONL file.
                Skips silently if None.
            messages: Framework Message objects to persist.
            **kwargs: Additional arguments (ignored).
        """
        if session_id is None:
            return

        # Auto-create session if it doesn't exist
        if not self.session_manager.session_exists(session_id):
            self.session_manager.create_session(
                session_key=session_id,
                agent_id=self.source_id,
            )
            logger.info(
                "✨ Auto-created session for key '%s'",
                session_id,
            )

        last_id: str | None = None
        for msg in messages:
            text = msg.text or ""
            last_id = self.session_manager.append_message(
                session_key=session_id,
                role=msg.role,
                content=text,
                parent_id=last_id,
            )

        logger.debug(
            "💾 Saved %d messages to session '%s'",
            len(messages),
            session_id,
        )
