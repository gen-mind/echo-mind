"""Tests for SandboxManager NATS lifecycle event publishing."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from api.sandbox.config import SandboxSettings
from api.sandbox.manager import SandboxManager
from tests.unit.sandbox.conftest import MockSandboxBackend


def _make_mock_nats(connected: bool = True) -> MagicMock:
    """Create a mock NatsBackend.

    Args:
        connected: Whether the mock should report as connected.

    Returns:
        MagicMock with is_connected property and async publish.
    """
    mock = MagicMock()
    type(mock).is_connected = PropertyMock(return_value=connected)
    mock.publish = AsyncMock()
    return mock


class TestPublishLifecycleEvent:
    """Tests for _publish_lifecycle_event method."""

    @pytest.mark.asyncio
    async def test_publish_when_nats_none(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test that no error occurs when nats is None (degraded mode)."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        # Should not raise
        await manager._publish_lifecycle_event("assigned", "sess-1", "ctr-1", 1)

    @pytest.mark.asyncio
    async def test_publish_when_nats_disconnected(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test that publish is skipped when NATS is disconnected."""
        mock_nats = _make_mock_nats(connected=False)
        manager = SandboxManager(mock_backend, sandbox_settings, nats=mock_nats)
        await manager._publish_lifecycle_event("assigned", "sess-1", "ctr-1", 1)
        mock_nats.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_publish_sends_correct_subject_and_payload(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test that publish uses correct subject and JSON payload."""
        mock_nats = _make_mock_nats(connected=True)
        manager = SandboxManager(mock_backend, sandbox_settings, nats=mock_nats)

        await manager._publish_lifecycle_event("activated", "sess-42", "ctr-abc", 7)

        mock_nats.publish.assert_awaited_once()
        subject, payload = mock_nats.publish.call_args[0]
        assert subject == "sandbox.sess-42.control"

        data = json.loads(payload)
        assert data["event_type"] == "activated"
        assert data["session_id"] == "sess-42"
        assert data["container_id"] == "ctr-abc"
        assert data["user_id"] == 7
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_publish_error_is_swallowed(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test that publish errors are logged, not raised."""
        mock_nats = _make_mock_nats(connected=True)
        mock_nats.publish.side_effect = Exception("NATS down")
        manager = SandboxManager(mock_backend, sandbox_settings, nats=mock_nats)

        # Should not raise
        await manager._publish_lifecycle_event("destroyed", "sess-1", "ctr-1", 1)


class TestManagerNatsIntegration:
    """Tests that lifecycle methods trigger NATS publishing."""

    @pytest.mark.asyncio
    async def test_assign_publishes_assigned_event(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test that assign() publishes an 'assigned' lifecycle event."""
        mock_nats = _make_mock_nats(connected=True)
        manager = SandboxManager(mock_backend, sandbox_settings, nats=mock_nats)
        await manager.start()

        try:
            await manager.assign("sess-1", user_id=1)

            # Find the 'assigned' publish call
            calls = mock_nats.publish.call_args_list
            assigned_calls = [
                c for c in calls
                if b'"event_type": "assigned"' in c[0][1]
            ]
            assert len(assigned_calls) == 1
            subject = assigned_calls[0][0][0]
            assert subject == "sandbox.sess-1.control"
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_activate_publishes_activated_event(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test that activate() publishes an 'activated' lifecycle event."""
        mock_nats = _make_mock_nats(connected=True)
        manager = SandboxManager(mock_backend, sandbox_settings, nats=mock_nats)
        await manager.start()

        try:
            await manager.assign("sess-1", user_id=1)
            mock_nats.publish.reset_mock()

            await manager.activate("sess-1")

            calls = mock_nats.publish.call_args_list
            activated_calls = [
                c for c in calls
                if b'"event_type": "activated"' in c[0][1]
            ]
            assert len(activated_calls) == 1
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_release_publishes_draining_and_destroyed_events(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test that release() publishes 'draining' and 'destroyed' events."""
        mock_nats = _make_mock_nats(connected=True)
        manager = SandboxManager(mock_backend, sandbox_settings, nats=mock_nats)
        await manager.start()

        try:
            await manager.assign("sess-1", user_id=1)
            mock_nats.publish.reset_mock()

            await manager.release("sess-1")

            calls = mock_nats.publish.call_args_list
            event_types = []
            for c in calls:
                try:
                    data = json.loads(c[0][1])
                    event_types.append(data.get("event_type"))
                except (json.JSONDecodeError, IndexError):
                    pass

            assert "draining" in event_types
            assert "destroyed" in event_types
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_assign_works_without_nats(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test that assign() works when nats is None (degraded mode)."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            assignment = await manager.assign("sess-1", user_id=1)
            assert assignment.session_id == "sess-1"
        finally:
            await manager.stop()
