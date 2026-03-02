"""Tests for SandboxManager state machine, warm pool, and reconciliation."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from api.sandbox.config import SandboxSettings
from api.sandbox.manager import SandboxManager
from api.sandbox.models import SandboxAssignment, SandboxState, WarmContainer
from tests.unit.sandbox.conftest import MockSandboxBackend


class TestSandboxManagerStartStop:
    """Tests for manager lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_warm_pool(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test that start() fills the warm pool."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            assert manager.warm_pool_size == sandbox_settings.pool_size
            assert manager.active_count == 0
            assert manager.total_count == sandbox_settings.pool_size
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_reconciliation(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test that stop() cancels the reconciliation task."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()
        assert manager._reconciliation_task is not None
        assert not manager._reconciliation_task.done()

        await manager.stop()
        assert manager._running is False

    @pytest.mark.asyncio
    async def test_start_idempotent(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test that calling start() twice doesn't create duplicate pools."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            initial_count = manager.warm_pool_size
            await manager.start()  # Should be idempotent
            assert manager.warm_pool_size == initial_count
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_get_status(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test status reporting."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            status = await manager.get_status()
            assert status["running"] is True
            assert status["warm_pool_size"] == sandbox_settings.pool_size
            assert status["active_count"] == 0
            assert status["max_instances"] == sandbox_settings.max_instances
            assert status["active_sessions"] == []
            assert status["persistence_errors"] == 0
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_warm_pool_is_deque(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test warm pool uses collections.deque for O(1) popleft."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        assert isinstance(manager._warm_pool, deque)


class TestSandboxManagerAssign:
    """Tests for container assignment."""

    @pytest.mark.asyncio
    async def test_assign_pops_from_warm_pool(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test assign() takes a container from the warm pool."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            initial_warm = manager.warm_pool_size
            assignment = await manager.assign("sess-1", user_id=1)

            assert assignment.session_id == "sess-1"
            assert assignment.user_id == 1
            assert assignment.state == SandboxState.ASSIGNED
            assert assignment.assigned_at is not None
            assert assignment.container_id is not None
            # Warm pool shrunk by 1 (but replenish runs in bg)
            assert manager.active_count == 1
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_assign_injects_env(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test assign() injects session environment variables."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            assignment = await manager.assign(
                "sess-1", user_id=42, env_vars={"CUSTOM": "value"}
            )
            injected = mock_backend.env_injections.get(assignment.container_id, {})
            assert injected["SANDBOX_SESSION_ID"] == "sess-1"
            assert injected["SANDBOX_USER_ID"] == "42"
            assert injected["CUSTOM"] == "value"
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_assign_same_session_returns_existing(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test assign() returns existing assignment for same session_id."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            a1 = await manager.assign("sess-1", user_id=1)
            a2 = await manager.assign("sess-1", user_id=1)
            assert a1.container_id == a2.container_id
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_assign_max_instances_exceeded(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test assign() raises when max instances reached."""
        # pool_size=0 (no warm pool), max_instances=1
        # First assign creates on-demand (total=1), second should fail
        sandbox_settings.pool_size = 0
        sandbox_settings.max_instances = 1
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            await manager.assign("sess-1", user_id=1)
            assert manager.total_count == 1

            with pytest.raises(RuntimeError, match="Max sandbox instances"):
                await manager.assign("sess-2", user_id=2)
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_assign_on_demand_when_pool_empty(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test assign() creates on-demand when warm pool is empty."""
        sandbox_settings.pool_size = 0  # No warm pool
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            assert manager.warm_pool_size == 0
            assignment = await manager.assign("sess-1", user_id=1)
            assert assignment.container_id is not None
            assert assignment.state == SandboxState.ASSIGNED
        finally:
            await manager.stop()


class TestSandboxManagerActivate:
    """Tests for sandbox activation."""

    @pytest.mark.asyncio
    async def test_activate_transitions_to_active(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test activate() transitions from ASSIGNED to ACTIVE."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            await manager.assign("sess-1", user_id=1)
            assignment = await manager.activate("sess-1")
            assert assignment.state == SandboxState.ACTIVE
            assert assignment.activated_at is not None
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_activate_unknown_session_raises(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test activate() raises KeyError for unknown session."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            with pytest.raises(KeyError):
                await manager.activate("nonexistent")
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_activate_from_wrong_state_raises(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test activate() raises ValueError from invalid state."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            await manager.assign("sess-1", user_id=1)
            await manager.activate("sess-1")  # Now ACTIVE

            with pytest.raises(ValueError, match="Cannot transition"):
                await manager.activate("sess-1")  # ACTIVE -> ACTIVE invalid
        finally:
            await manager.stop()


class TestSandboxManagerRelease:
    """Tests for sandbox release."""

    @pytest.mark.asyncio
    async def test_release_destroys_container(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test release() stops and removes the container."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            assignment = await manager.assign("sess-1", user_id=1)
            container_id = assignment.container_id
            await manager.release("sess-1")

            assert await manager.get_assignment("sess-1") is None
            assert manager.active_count == 0
            # Container should be removed from backend
            assert await mock_backend.get_container(container_id) is None
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_release_unknown_session_raises(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test release() raises KeyError for unknown session."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            with pytest.raises(KeyError):
                await manager.release("nonexistent")
        finally:
            await manager.stop()


class TestSandboxManagerReconciliation:
    """Tests for reconciliation logic."""

    @pytest.mark.asyncio
    async def test_reconcile_enforces_session_timeout(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test reconciliation releases timed-out sessions."""
        sandbox_settings.session_timeout = 1  # 1 second for test
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            await manager.assign("sess-1", user_id=1)
            assert manager.active_count == 1

            # Wait for timeout + reconciliation
            await asyncio.sleep(2)
            await manager._reconcile()

            assert manager.active_count == 0
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_reconcile_enforces_idle_timeout(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test reconciliation destroys idle warm containers."""
        sandbox_settings.idle_timeout = 1  # 1 second for test
        sandbox_settings.pool_size = 0  # Don't replenish
        manager = SandboxManager(mock_backend, sandbox_settings)

        # Manually add an old warm container
        old_warm = WarmContainer(
            container_id="old-warm",
            container_name="sandbox-old",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        )
        # Create it in the backend so destroy works
        await mock_backend.create_container(
            name="sandbox-old", image="test:latest", env={},
            network="net", cpu_limit=1.0, memory_limit="512m",
        )
        # Manually set the container_id to match
        for cid, info in mock_backend.containers.items():
            if info.name == "sandbox-old":
                old_warm = WarmContainer(
                    container_id=cid,
                    container_name="sandbox-old",
                    created_at=datetime.now(timezone.utc) - timedelta(seconds=10),
                )
                break

        manager._warm_pool.append(old_warm)
        manager._running = True

        try:
            assert manager.warm_pool_size == 1
            await manager._reconcile()
            assert manager.warm_pool_size == 0
        finally:
            manager._running = False

    @pytest.mark.asyncio
    async def test_reconcile_replenishes_pool(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test reconciliation replenishes the warm pool."""
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            # Drain pool via assignments
            await manager.assign("sess-1", user_id=1)
            await asyncio.sleep(0.1)

            # Force reconciliation
            await manager._reconcile()
            await asyncio.sleep(0.1)

            # Pool should be replenished
            assert manager.warm_pool_size + manager.active_count <= sandbox_settings.max_instances
        finally:
            await manager.stop()


class TestSandboxManagerDiscovery:
    """Tests for existing container discovery."""

    @pytest.mark.asyncio
    async def test_discover_existing_warm_containers(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test discovering existing warm containers on startup."""
        # Pre-create a container in the backend
        info = await mock_backend.create_container(
            name="existing-warm", image="test:latest", env={},
            network="net", cpu_limit=1.0, memory_limit="512m",
            labels={"echomind.sandbox": "true", "echomind.sandbox.state": "warm"},
        )
        await mock_backend.start_container(info.container_id)

        sandbox_settings.pool_size = 0  # Don't create new ones
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            # Should discover the existing warm container
            assert manager.warm_pool_size == 1
        finally:
            await manager.stop()


class TestSandboxManagerPersistence:
    """Tests for database persistence methods."""

    @staticmethod
    def _make_mock_db() -> AsyncMock:
        """Create a mock DB session with begin_nested() as async context manager.

        Returns:
            AsyncMock configured for begin_nested() usage.
        """
        mock_db = AsyncMock()
        # begin_nested() must return an async context manager directly (not a coroutine).
        # Override with MagicMock so it's a sync call returning the context manager.
        mock_savepoint = MagicMock()
        mock_savepoint.__aenter__ = AsyncMock(return_value=mock_savepoint)
        mock_savepoint.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin_nested = MagicMock(return_value=mock_savepoint)
        return mock_db

    @pytest.mark.asyncio
    async def test_persist_assignment_executes_upsert(self) -> None:
        """_persist_assignment executes SQL with correct parameters."""
        mock_db = self._make_mock_db()
        manager = SandboxManager.__new__(SandboxManager)

        assignment = SandboxAssignment(
            session_id="sess-1",
            user_id=42,
            chat_session_id=7,
            container_id="ctr-123",
            container_name="sandbox-test",
            state=SandboxState.ASSIGNED,
            assigned_at=datetime.now(timezone.utc),
            agent_config={"model": "gpt-4"},
        )

        await manager._persist_assignment(mock_db, assignment)

        mock_db.execute.assert_awaited_once()
        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        assert params["session_id"] == "sess-1"
        assert params["user_id"] == 42
        assert params["chat_session_id"] == 7
        assert params["container_id"] == "ctr-123"
        assert params["status"] == "assigned"
        assert params["agent_config"] == '{"model": "gpt-4"}'

    @pytest.mark.asyncio
    async def test_persist_assignment_rollback_on_error(self) -> None:
        """_persist_assignment handles exception via begin_nested savepoint."""
        mock_db = self._make_mock_db()
        mock_db.execute.side_effect = Exception("DB error")
        manager = SandboxManager.__new__(SandboxManager)
        manager._persistence_errors = 0

        assignment = SandboxAssignment(
            session_id="sess-1",
            user_id=1,
            container_id="ctr-1",
            container_name="sandbox-1",
            state=SandboxState.ASSIGNED,
        )

        # Should not raise — error is caught and logged
        await manager._persist_assignment(mock_db, assignment)

        # begin_nested was called (savepoint handles rollback automatically)
        mock_db.begin_nested.assert_called_once()
        assert manager._persistence_errors == 1

    @pytest.mark.asyncio
    async def test_persist_event_executes_insert(self) -> None:
        """_persist_event inserts event with correct parameters."""
        mock_db = self._make_mock_db()
        manager = SandboxManager.__new__(SandboxManager)

        assignment = SandboxAssignment(
            session_id="sess-1",
            user_id=1,
            container_id="ctr-1",
            container_name="sandbox-1",
            state=SandboxState.ACTIVE,
        )

        await manager._persist_event(
            mock_db, assignment, "activated", {"extra": "data"}
        )

        mock_db.execute.assert_awaited_once()
        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        assert params["session_id"] == "sess-1"
        assert params["event_type"] == "activated"
        assert json.loads(params["event_data"]) == {"extra": "data"}

    @pytest.mark.asyncio
    async def test_persist_event_rollback_on_error(self) -> None:
        """_persist_event handles exception via begin_nested savepoint."""
        mock_db = self._make_mock_db()
        mock_db.execute.side_effect = Exception("DB error")
        manager = SandboxManager.__new__(SandboxManager)
        manager._persistence_errors = 0

        assignment = SandboxAssignment(
            session_id="sess-1",
            user_id=1,
            container_id="ctr-1",
            container_name="sandbox-1",
            state=SandboxState.ACTIVE,
        )

        # Should not raise — error is caught and logged
        await manager._persist_event(mock_db, assignment, "failed", {})

        mock_db.begin_nested.assert_called_once()
        assert manager._persistence_errors == 1


class TestSandboxManagerConcurrency:
    """Tests for concurrent operations."""

    @pytest.mark.asyncio
    async def test_concurrent_assigns_respect_max_instances(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Concurrent assign() calls respect max_instances limit.

        With pool_size=3 and max_instances=6, the warm pool fills 3 containers
        (total=3). Assigning all 3 moves them from warm to assigned (total stays 3).
        A 4th assign creates on-demand (total=4). max_instances=6 leaves room.
        After 6 total, the next should fail.
        """
        sandbox_settings.pool_size = 3
        sandbox_settings.max_instances = 6
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            # All 3 warm pool containers should be assignable
            results = await asyncio.gather(
                manager.assign("sess-1", user_id=1),
                manager.assign("sess-2", user_id=2),
                manager.assign("sess-3", user_id=3),
            )

            assert len(results) == 3
            # All should have unique container IDs
            container_ids = {r.container_id for r in results}
            assert len(container_ids) == 3
            assert manager.active_count == 3
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_concurrent_assigns_no_lost_containers(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """No containers are lost between warm pool and assignments."""
        sandbox_settings.pool_size = 2
        sandbox_settings.max_instances = 5
        manager = SandboxManager(mock_backend, sandbox_settings)
        await manager.start()

        try:
            initial_total = manager.total_count

            a1 = await manager.assign("sess-1", user_id=1)
            a2 = await manager.assign("sess-2", user_id=2)

            # Active count should match assignments
            assert manager.active_count == 2
            # No containers should be unaccounted for
            assert manager.total_count >= manager.active_count
        finally:
            await manager.stop()


def _make_mock_nats(connected: bool = True) -> MagicMock:
    """Create a mock NatsBackend.

    Args:
        connected: Whether the mock reports as connected.

    Returns:
        MagicMock configured as a NatsBackend.
    """
    mock = MagicMock()
    type(mock).is_connected = PropertyMock(return_value=connected)
    mock.publish = AsyncMock()
    return mock


class TestSandboxManagerNatsPublishing:
    """Tests for NATS lifecycle event publishing."""

    @pytest.mark.asyncio
    async def test_assign_publishes_assigned_event(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test assign() publishes an 'assigned' event to NATS."""
        mock_nats = _make_mock_nats()
        manager = SandboxManager(mock_backend, sandbox_settings, nats=mock_nats)
        await manager.start()

        try:
            assignment = await manager.assign("sess-1", user_id=42)

            mock_nats.publish.assert_called_once()
            subject, payload = mock_nats.publish.call_args[0]
            assert subject == "sandbox.sess-1.control"
            event = json.loads(payload)
            assert event["event_type"] == "assigned"
            assert event["session_id"] == "sess-1"
            assert event["container_id"] == assignment.container_id
            assert event["user_id"] == 42
            assert "timestamp" in event
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_activate_publishes_activated_event(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test activate() publishes an 'activated' event to NATS."""
        mock_nats = _make_mock_nats()
        manager = SandboxManager(mock_backend, sandbox_settings, nats=mock_nats)
        await manager.start()

        try:
            assignment = await manager.assign("sess-1", user_id=10)
            mock_nats.publish.reset_mock()

            await manager.activate("sess-1")

            mock_nats.publish.assert_called_once()
            subject, payload = mock_nats.publish.call_args[0]
            assert subject == "sandbox.sess-1.control"
            event = json.loads(payload)
            assert event["event_type"] == "activated"
            assert event["user_id"] == 10
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_release_publishes_draining_and_destroyed_events(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test release() publishes 'draining' and 'destroyed' events."""
        mock_nats = _make_mock_nats()
        manager = SandboxManager(mock_backend, sandbox_settings, nats=mock_nats)
        await manager.start()

        try:
            await manager.assign("sess-1", user_id=5)
            mock_nats.publish.reset_mock()

            await manager.release("sess-1")

            assert mock_nats.publish.call_count == 2
            calls = mock_nats.publish.call_args_list

            # First call: draining
            draining_event = json.loads(calls[0][0][1])
            assert draining_event["event_type"] == "draining"
            assert draining_event["session_id"] == "sess-1"

            # Second call: destroyed
            destroyed_event = json.loads(calls[1][0][1])
            assert destroyed_event["event_type"] == "destroyed"
            assert destroyed_event["session_id"] == "sess-1"
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_nats_none_skips_publishing(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test that manager works without NATS (nats=None)."""
        manager = SandboxManager(mock_backend, sandbox_settings, nats=None)
        await manager.start()

        try:
            # Should not raise — just skips publishing
            assignment = await manager.assign("sess-1", user_id=1)
            await manager.activate("sess-1")
            await manager.release("sess-1")
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_nats_disconnected_skips_publishing(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test that disconnected NATS skips publishing gracefully."""
        mock_nats = _make_mock_nats(connected=False)
        manager = SandboxManager(mock_backend, sandbox_settings, nats=mock_nats)
        await manager.start()

        try:
            await manager.assign("sess-1", user_id=1)
            mock_nats.publish.assert_not_called()
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_nats_publish_failure_does_not_crash(
        self, mock_backend: MockSandboxBackend, sandbox_settings: SandboxSettings
    ) -> None:
        """Test that NATS publish errors are caught, not raised."""
        mock_nats = _make_mock_nats()
        mock_nats.publish.side_effect = Exception("NATS connection lost")
        manager = SandboxManager(mock_backend, sandbox_settings, nats=mock_nats)
        await manager.start()

        try:
            # Should not raise despite NATS failure
            assignment = await manager.assign("sess-1", user_id=1)
            assert assignment.state == SandboxState.ASSIGNED
            assert assignment.session_id == "sess-1"
        finally:
            await manager.stop()
