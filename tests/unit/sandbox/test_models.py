"""Tests for sandbox Pydantic models and state machine."""

from datetime import datetime, timezone

import pytest

from api.sandbox.models import (
    ContainerInfo,
    SandboxAssignment,
    SandboxState,
    WarmContainer,
)


class TestSandboxState:
    """Tests for SandboxState enum and transitions."""

    def test_all_states_exist(self) -> None:
        """Test all expected states are defined."""
        assert SandboxState.WARM == "warm"
        assert SandboxState.ASSIGNED == "assigned"
        assert SandboxState.ACTIVE == "active"
        assert SandboxState.DRAINING == "draining"
        assert SandboxState.DESTROYED == "destroyed"

    def test_valid_transitions_warm(self) -> None:
        """Test WARM can transition to ASSIGNED or DESTROYED."""
        assert SandboxState.WARM.can_transition_to(SandboxState.ASSIGNED)
        assert SandboxState.WARM.can_transition_to(SandboxState.DESTROYED)
        assert not SandboxState.WARM.can_transition_to(SandboxState.ACTIVE)
        assert not SandboxState.WARM.can_transition_to(SandboxState.DRAINING)

    def test_valid_transitions_assigned(self) -> None:
        """Test ASSIGNED can transition to ACTIVE or DESTROYED."""
        assert SandboxState.ASSIGNED.can_transition_to(SandboxState.ACTIVE)
        assert SandboxState.ASSIGNED.can_transition_to(SandboxState.DESTROYED)
        assert not SandboxState.ASSIGNED.can_transition_to(SandboxState.WARM)
        assert not SandboxState.ASSIGNED.can_transition_to(SandboxState.DRAINING)

    def test_valid_transitions_active(self) -> None:
        """Test ACTIVE can transition to DRAINING or DESTROYED."""
        assert SandboxState.ACTIVE.can_transition_to(SandboxState.DRAINING)
        assert SandboxState.ACTIVE.can_transition_to(SandboxState.DESTROYED)
        assert not SandboxState.ACTIVE.can_transition_to(SandboxState.WARM)
        assert not SandboxState.ACTIVE.can_transition_to(SandboxState.ASSIGNED)

    def test_valid_transitions_draining(self) -> None:
        """Test DRAINING can only transition to DESTROYED."""
        assert SandboxState.DRAINING.can_transition_to(SandboxState.DESTROYED)
        assert not SandboxState.DRAINING.can_transition_to(SandboxState.WARM)
        assert not SandboxState.DRAINING.can_transition_to(SandboxState.ACTIVE)

    def test_valid_transitions_destroyed(self) -> None:
        """Test DESTROYED is terminal (no transitions)."""
        assert not SandboxState.DESTROYED.can_transition_to(SandboxState.WARM)
        assert not SandboxState.DESTROYED.can_transition_to(SandboxState.ASSIGNED)
        assert not SandboxState.DESTROYED.can_transition_to(SandboxState.ACTIVE)
        assert not SandboxState.DESTROYED.can_transition_to(SandboxState.DRAINING)

    def test_self_transition_not_allowed(self) -> None:
        """Test no state can transition to itself."""
        for state in SandboxState:
            assert not state.can_transition_to(state)


class TestContainerInfo:
    """Tests for ContainerInfo model."""

    def test_basic_creation(self) -> None:
        """Test creating a ContainerInfo."""
        info = ContainerInfo(
            container_id="abc123",
            name="test-container",
            status="running",
        )
        assert info.container_id == "abc123"
        assert info.name == "test-container"
        assert info.status == "running"
        assert info.labels == {}

    def test_with_labels(self) -> None:
        """Test ContainerInfo with labels."""
        info = ContainerInfo(
            container_id="abc123",
            name="test",
            status="running",
            labels={"key": "value"},
        )
        assert info.labels == {"key": "value"}


class TestSandboxAssignment:
    """Tests for SandboxAssignment model."""

    def test_creation_with_defaults(self) -> None:
        """Test creating assignment with default values."""
        assignment = SandboxAssignment(
            session_id="sess-001",
            user_id=1,
            container_id="ctr-001",
            container_name="sandbox-001",
            state=SandboxState.ASSIGNED,
        )
        assert assignment.session_id == "sess-001"
        assert assignment.user_id == 1
        assert assignment.chat_session_id is None
        assert assignment.state == SandboxState.ASSIGNED
        assert assignment.message_count == 0
        assert assignment.tool_calls_count == 0
        assert assignment.total_tokens == 0
        assert assignment.created_at is not None
        assert assignment.assigned_at is None
        assert assignment.activated_at is None
        assert assignment.agent_config == {}

    def test_creation_with_all_fields(self) -> None:
        """Test creating assignment with all fields."""
        now = datetime.now(timezone.utc)
        assignment = SandboxAssignment(
            session_id="sess-002",
            user_id=2,
            chat_session_id=10,
            container_id="ctr-002",
            container_name="sandbox-002",
            state=SandboxState.ACTIVE,
            created_at=now,
            assigned_at=now,
            activated_at=now,
            agent_config={"model": "gpt-4"},
            message_count=5,
            tool_calls_count=3,
            total_tokens=1000,
        )
        assert assignment.chat_session_id == 10
        assert assignment.activated_at == now
        assert assignment.agent_config == {"model": "gpt-4"}
        assert assignment.message_count == 5


class TestWarmContainer:
    """Tests for WarmContainer model."""

    def test_creation(self) -> None:
        """Test creating a warm container."""
        warm = WarmContainer(
            container_id="warm-001",
            container_name="sandbox-warm-001",
        )
        assert warm.container_id == "warm-001"
        assert warm.container_name == "sandbox-warm-001"
        assert warm.created_at is not None

    def test_custom_created_at(self) -> None:
        """Test warm container with custom timestamp."""
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        warm = WarmContainer(
            container_id="warm-002",
            container_name="sandbox-warm-002",
            created_at=ts,
        )
        assert warm.created_at == ts
