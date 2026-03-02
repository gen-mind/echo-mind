"""
Session Manager — low-level JSONL file I/O for conversation persistence.

Handles creating session files, appending messages, and loading history.
Each session is stored as a single `.jsonl` file with a header line
followed by message entries.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import SessionHeader, SessionMessageEntry

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Low-level JSONL session file manager.

    Each session key maps to a single `.jsonl` file. The first line
    is a SessionHeader; subsequent lines are SessionMessageEntry records.

    Attributes:
        sessions_dir: Root directory for session JSONL files.
    """

    def __init__(self, sessions_dir: str = "data/sessions") -> None:
        """
        Initialize session manager and create directory if needed.

        Args:
            sessions_dir: Root directory for storing session files.
        """
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        logger.info("📂 Session manager initialized: %s", self.sessions_dir)

    def create_session(
        self,
        session_key: str,
        agent_id: str,
        cwd: str = ".",
    ) -> str:
        """
        Create a new JSONL session file with a header line.

        Args:
            session_key: Routing session key for isolation.
            agent_id: Agent that owns this session.
            cwd: Working directory context.

        Returns:
            Generated session ID (e.g. "session_abc123def456").

        Raises:
            OSError: If file cannot be written.
        """
        session_id = self._generate_session_id()
        session_file = self._get_session_file(session_key)

        header = SessionHeader.create(
            session_id=session_id,
            cwd=cwd,
            agent_id=agent_id,
            session_key=session_key,
        )

        self._append_entry(session_file, header.to_dict())
        logger.info(
            "✨ Created session %s for agent '%s' (key=%s)",
            session_id,
            agent_id,
            session_key,
        )
        return session_id

    def append_message(
        self,
        session_key: str,
        role: str,
        content: str,
        parent_id: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Append a message entry to the session JSONL file.

        Args:
            session_key: Session key identifying the file.
            role: Message role (user/assistant/system/tool).
            content: Message text content.
            parent_id: ID of the preceding message.
            tool_calls: Optional tool call data.

        Returns:
            Generated message ID (e.g. "msg_abc123def456").

        Raises:
            FileNotFoundError: If session file does not exist.
            OSError: If file cannot be written.
        """
        session_file = self._get_session_file(session_key)
        if not session_file.exists():
            raise FileNotFoundError(
                f"Session file not found for key '{session_key}': {session_file}"
            )

        message_id = self._generate_message_id()

        entry = SessionMessageEntry.create(
            message_id=message_id,
            role=role,
            content=content,
            parent_id=parent_id,
            tool_calls=tool_calls,
        )

        self._append_entry(session_file, entry.to_dict())
        logger.debug(
            "💬 Appended message %s (role=%s) to session key=%s",
            message_id,
            role,
            session_key,
        )
        return message_id

    def load_history(
        self,
        session_key: str,
        max_messages: int | None = None,
    ) -> list[SessionMessageEntry]:
        """
        Load message entries from a JSONL session file.

        Args:
            session_key: Session key identifying the file.
            max_messages: Maximum number of messages to return
                (newest N). None means unlimited.

        Returns:
            List of SessionMessageEntry in chronological order.
            Returns empty list if session file does not exist.
        """
        session_file = self._get_session_file(session_key)
        if not session_file.exists():
            return []

        messages: list[SessionMessageEntry] = []

        with open(session_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(
                        "⚠️ Skipping malformed JSON on line %d in %s",
                        line_num,
                        session_file,
                    )
                    continue

                if data.get("type") != "message":
                    continue

                try:
                    entry = SessionMessageEntry.from_dict(data)
                    messages.append(entry)
                except (KeyError, ValueError) as e:
                    logger.warning(
                        "⚠️ Skipping invalid message on line %d in %s: %s",
                        line_num,
                        session_file,
                        e,
                    )

        if max_messages is not None and len(messages) > max_messages:
            messages = messages[-max_messages:]

        logger.debug(
            "📖 Loaded %d messages from session key=%s",
            len(messages),
            session_key,
        )
        return messages

    def load_header(self, session_key: str) -> SessionHeader | None:
        """
        Load the session header from the first line of the JSONL file.

        Args:
            session_key: Session key identifying the file.

        Returns:
            SessionHeader if file exists and header is valid, None otherwise.
        """
        session_file = self._get_session_file(session_key)
        if not session_file.exists():
            return None

        with open(session_file, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()

        if not first_line:
            return None

        try:
            data = json.loads(first_line)
            return SessionHeader.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(
                "⚠️ Failed to parse session header in %s: %s",
                session_file,
                e,
            )
            return None

    def session_exists(self, session_key: str) -> bool:
        """
        Check if a JSONL session file exists for the given key.

        Args:
            session_key: Session key identifying the file.

        Returns:
            True if the session file exists.
        """
        return self._get_session_file(session_key).exists()

    def _append_entry(self, session_file: Path, entry: dict[str, Any]) -> None:
        """
        Append a JSON entry as a single line to the session file.

        Args:
            session_file: Path to the JSONL file.
            entry: Dictionary to serialize as JSON.

        Raises:
            OSError: If file cannot be written.
        """
        json_line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        with self._write_lock:
            with open(session_file, "a", encoding="utf-8") as f:
                f.write(json_line + "\n")

    def _get_session_file(self, session_key: str) -> Path:
        """
        Convert session key to a filesystem-safe filename.

        Replaces ':' and '/' with '_' and appends '.jsonl'.

        Args:
            session_key: Routing session key.

        Returns:
            Path to the JSONL session file.
        """
        safe_name = session_key.replace(":", "_").replace("/", "_")
        return self.sessions_dir / f"{safe_name}.jsonl"

    def _generate_session_id(self) -> str:
        """
        Generate a unique session identifier.

        Returns:
            Session ID in format "session_{12 hex chars}".
        """
        return f"session_{uuid4().hex[:12]}"

    def _generate_message_id(self) -> str:
        """
        Generate a unique message identifier.

        Returns:
            Message ID in format "msg_{12 hex chars}".
        """
        return f"msg_{uuid4().hex[:12]}"
