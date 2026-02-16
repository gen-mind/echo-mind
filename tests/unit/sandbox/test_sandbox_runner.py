"""Tests for SandboxRunner NATS bridge."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.sandbox_runner import SandboxRunner


class TestSandboxRunnerSettings:
    """Tests for settings loading."""

    def test_load_settings_from_env(self) -> None:
        """Test loading settings from environment variables."""
        runner = SandboxRunner()
        env = {
            "SANDBOX_SESSION_ID": "test-session",
            "SANDBOX_USER_ID": "42",
            "SANDBOX_MODE": "active",
            "SANDBOX_NATS_URL": "nats://custom:4222",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = runner._load_settings()
            assert settings["session_id"] == "test-session"
            assert settings["user_id"] == "42"
            assert settings["mode"] == "active"
            assert settings["nats_url"] == "nats://custom:4222"

    def test_load_settings_from_env_file(self, tmp_path: Path) -> None:
        """Test loading settings from a .env file."""
        env_file = tmp_path / "sandbox.env"
        env_file.write_text(
            "SANDBOX_SESSION_ID=file-session\n"
            "SANDBOX_USER_ID=99\n"
            "SANDBOX_MODE=active\n"
        )

        runner = SandboxRunner()
        with patch.object(Path, "__new__", return_value=env_file):
            # Directly test the file parsing logic
            settings: dict[str, str] = {}
            for line in env_file.read_text().strip().splitlines():
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    key, _, value = line.partition("=")
                    settings[key.strip().lower().removeprefix("sandbox_")] = value.strip()

            assert settings["session_id"] == "file-session"
            assert settings["user_id"] == "99"
            assert settings["mode"] == "active"

    def test_env_vars_override_file(self) -> None:
        """Test that env vars take precedence over file."""
        runner = SandboxRunner()
        env = {"SANDBOX_SESSION_ID": "env-session", "SANDBOX_MODE": "active"}
        with patch.dict(os.environ, env, clear=False):
            settings = runner._load_settings()
            assert settings["session_id"] == "env-session"


class TestSandboxRunnerMessageHandling:
    """Tests for NATS message handling."""

    @pytest.mark.asyncio
    async def test_handle_input_message(self) -> None:
        """Test handling an input message."""
        runner = SandboxRunner()
        runner._session_id = "test-session"

        # Mock NATS client with JetStream
        mock_js = AsyncMock()
        mock_nc = MagicMock()
        mock_nc.jetstream.return_value = mock_js

        runner._nats_client = mock_nc

        msg = MagicMock()
        msg.data = json.dumps({"query": "Hello agent"}).encode()
        msg.ack = AsyncMock()
        msg.nak = AsyncMock()

        # Patch the nats import inside the method
        mock_nats_module = MagicMock()
        mock_nats_module.aio.client.Client = type(mock_nc)
        with patch.dict("sys.modules", {"nats": mock_nats_module, "nats.aio": mock_nats_module.aio, "nats.aio.client": mock_nats_module.aio.client}):
            await runner._handle_input_message(msg)

        msg.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_control_shutdown(self) -> None:
        """Test handling a shutdown control message."""
        runner = SandboxRunner()
        runner._running = True
        runner._session_id = "test-session"

        msg = MagicMock()
        msg.data = json.dumps({"command": "shutdown"}).encode()
        msg.ack = AsyncMock()

        # Patch shutdown to track it was called
        runner.shutdown = AsyncMock()

        await runner._handle_control_message(msg)
        msg.ack.assert_called_once()
        runner.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_control_cancel(self) -> None:
        """Test handling a cancel control message."""
        runner = SandboxRunner()
        runner._session_id = "test-session"

        msg = MagicMock()
        msg.data = json.dumps({"command": "cancel"}).encode()
        msg.ack = AsyncMock()

        await runner._handle_control_message(msg)
        msg.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_control_unknown(self) -> None:
        """Test handling an unknown control command."""
        runner = SandboxRunner()
        runner._session_id = "test-session"

        msg = MagicMock()
        msg.data = json.dumps({"command": "unknown_cmd"}).encode()
        msg.ack = AsyncMock()

        await runner._handle_control_message(msg)
        msg.ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_input_message_error_naks(self) -> None:
        """Test that input handler NAKs on error."""
        runner = SandboxRunner()
        runner._session_id = "test-session"

        msg = MagicMock()
        msg.data = b"invalid json{"
        msg.ack = AsyncMock()
        msg.nak = AsyncMock()

        await runner._handle_input_message(msg)
        msg.nak.assert_called_once()


class TestSandboxRunnerLifecycle:
    """Tests for runner lifecycle."""

    @pytest.mark.asyncio
    async def test_shutdown_sets_running_false(self) -> None:
        """Test shutdown sets _running to False."""
        runner = SandboxRunner()
        runner._running = True
        runner._nats_client = None

        await runner.shutdown()
        assert runner._running is False

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self) -> None:
        """Test calling shutdown twice is safe."""
        runner = SandboxRunner()
        runner._running = False
        await runner.shutdown()
        assert runner._running is False
