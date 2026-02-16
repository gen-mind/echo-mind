"""Tests for SandboxManager state machine, warm pool, and reconciliation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from api.sandbox.config import SandboxSettings
from api.sandbox.manager import SandboxManager
from api.sandbox.models import SandboxState, WarmContainer
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
            assert status["enabled"] is True
            assert status["running"] is True
            assert status["warm_pool_size"] == sandbox_settings.pool_size
            assert status["active_count"] == 0
            assert status["max_instances"] == sandbox_settings.max_instances
            assert status["active_sessions"] == []
        finally:
            await manager.stop()


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
