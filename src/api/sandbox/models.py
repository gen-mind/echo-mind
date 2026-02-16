"""
Pydantic models for sandbox state management.

These are runtime models used by SandboxManager, not proto-generated models.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class SandboxState(str, enum.Enum):
    """Sandbox container lifecycle states.

    State machine transitions:
        WARM -> ASSIGNED -> ACTIVE -> DRAINING -> DESTROYED
        WARM -> DESTROYED (idle timeout)
        ASSIGNED -> DESTROYED (assignment failure)
        ACTIVE -> DRAINING -> DESTROYED (release/timeout)
    """

    WARM = "warm"
    ASSIGNED = "assigned"
    ACTIVE = "active"
    DRAINING = "draining"
    DESTROYED = "destroyed"

    @staticmethod
    def valid_transitions() -> dict[SandboxState, set[SandboxState]]:
        """Return valid state transitions.

        Returns:
            Mapping of current state to set of valid next states.
        """
        return {
            SandboxState.WARM: {SandboxState.ASSIGNED, SandboxState.DESTROYED},
            SandboxState.ASSIGNED: {SandboxState.ACTIVE, SandboxState.DESTROYED},
            SandboxState.ACTIVE: {SandboxState.DRAINING, SandboxState.DESTROYED},
            SandboxState.DRAINING: {SandboxState.DESTROYED},
            SandboxState.DESTROYED: set(),
        }

    def can_transition_to(self, target: SandboxState) -> bool:
        """Check if transition to target state is valid.

        Args:
            target: The desired next state.

        Returns:
            True if the transition is allowed.
        """
        return target in self.valid_transitions().get(self, set())


class ContainerInfo(BaseModel):
    """Information about a Docker container."""

    container_id: str = Field(..., description="Docker container ID")
    name: str = Field(..., description="Container name")
    status: str = Field(..., description="Docker container status")
    labels: dict[str, str] = Field(default_factory=dict, description="Container labels")


class SandboxAssignment(BaseModel):
    """Represents a sandbox container assignment to a session."""

    session_id: str = Field(..., description="Unique session identifier")
    user_id: int = Field(..., description="User who owns this session")
    chat_session_id: int | None = Field(None, description="Associated chat session")
    container_id: str = Field(..., description="Docker container ID")
    container_name: str = Field(..., description="Docker container name")
    state: SandboxState = Field(..., description="Current lifecycle state")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the assignment was created",
    )
    assigned_at: datetime | None = Field(None, description="When assigned to session")
    activated_at: datetime | None = Field(None, description="When health check passed")
    agent_config: dict[str, str] = Field(
        default_factory=dict, description="Agent configuration"
    )
    message_count: int = Field(0, description="Messages processed")
    tool_calls_count: int = Field(0, description="Tool calls made")
    total_tokens: int = Field(0, description="Total tokens consumed")


class WarmContainer(BaseModel):
    """A pre-created container in the warm pool."""

    container_id: str = Field(..., description="Docker container ID")
    container_name: str = Field(..., description="Docker container name")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the container was created",
    )
