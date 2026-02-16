"""
SandboxManager - State machine for sandbox container lifecycle.

Manages a warm pool of pre-created containers, assigns them to sessions,
and reconciles state on a timer. Persists state to PostgreSQL.

NOTE: This currently lives in the API service. In a future phase, it should
be decoupled to its own dedicated service for independent scaling.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from api.sandbox.backend import SandboxBackend
from api.sandbox.config import SandboxSettings
from api.sandbox.models import (
    ContainerInfo,
    SandboxAssignment,
    SandboxState,
    WarmContainer,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("echomind-sandbox")

# Label used to identify managed sandbox containers
_SANDBOX_LABEL = "echomind.sandbox"
_SANDBOX_LABEL_VALUE = "true"


class SandboxManager:
    """Manages sandbox container lifecycle with a warm pool.

    State machine:
        WARM -> ASSIGNED -> ACTIVE -> DRAINING -> DESTROYED

    The manager maintains a pool of warm containers and assigns them
    to chat sessions on demand. A background reconciliation loop
    enforces timeouts and replenishes the pool.
    """

    def __init__(
        self,
        backend: SandboxBackend,
        settings: SandboxSettings,
    ) -> None:
        """Initialize SandboxManager.

        Args:
            backend: Container backend (Docker, K8s, etc.).
            settings: Sandbox configuration.
        """
        self._backend = backend
        self._settings = settings

        # In-memory state
        self._warm_pool: list[WarmContainer] = []
        self._assignments: dict[str, SandboxAssignment] = {}  # session_id -> assignment
        self._lock = asyncio.Lock()
        self._reconciliation_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def warm_pool_size(self) -> int:
        """Current number of warm containers."""
        return len(self._warm_pool)

    @property
    def active_count(self) -> int:
        """Number of assigned/active containers."""
        return len(self._assignments)

    @property
    def total_count(self) -> int:
        """Total managed containers (warm + assigned/active)."""
        return self.warm_pool_size + self.active_count

    async def start(self) -> None:
        """Start the manager: replenish warm pool and start reconciliation.

        Raises:
            RuntimeError: If already running.
        """
        if self._running:
            logger.warning("⚠️ SandboxManager already running")
            return

        self._running = True
        logger.info(
            f"🚀 SandboxManager starting (pool_size={self._settings.pool_size}, "
            f"max_instances={self._settings.max_instances})"
        )

        # Discover existing managed containers
        await self._discover_existing_containers()

        # Fill the warm pool
        await self._replenish_pool()

        # Start reconciliation loop
        self._reconciliation_task = asyncio.create_task(
            self._reconciliation_loop()
        )
        logger.info("✅ SandboxManager started")

    async def stop(self) -> None:
        """Stop the manager and clean up.

        Cancels the reconciliation loop. Does NOT destroy containers —
        they will be discovered on next start.
        """
        self._running = False
        if self._reconciliation_task:
            self._reconciliation_task.cancel()
            try:
                await self._reconciliation_task
            except asyncio.CancelledError:
                pass
            self._reconciliation_task = None
        logger.info("🛑 SandboxManager stopped")

    async def assign(
        self,
        session_id: str,
        user_id: int,
        chat_session_id: int | None = None,
        env_vars: dict[str, str] | None = None,
        agent_config: dict[str, str] | None = None,
        db: AsyncSession | None = None,
    ) -> SandboxAssignment:
        """Assign a warm container to a session.

        Pops a container from the warm pool, injects session-specific
        environment variables, and transitions to ASSIGNED state.

        Args:
            session_id: Unique session identifier.
            user_id: User who owns this session.
            chat_session_id: Optional associated chat session.
            env_vars: Session-specific environment variables to inject.
            agent_config: Agent configuration dict.
            db: Optional database session for persistence.

        Returns:
            SandboxAssignment with container details.

        Raises:
            RuntimeError: If no warm containers available or max instances reached.
        """
        async with self._lock:
            if session_id in self._assignments:
                return self._assignments[session_id]

            if self.total_count >= self._settings.max_instances:
                raise RuntimeError(
                    f"Max sandbox instances reached ({self._settings.max_instances})"
                )

            if not self._warm_pool:
                # Try to create one on demand
                logger.warning("⚠️ Warm pool empty, creating container on demand")
                warm = await self._create_warm_container()
                if warm is None:
                    raise RuntimeError("No warm containers available and on-demand creation failed")
            else:
                warm = self._warm_pool.pop(0)

        # Inject session environment (outside lock to avoid holding it during I/O)
        session_env = {
            "SANDBOX_SESSION_ID": session_id,
            "SANDBOX_USER_ID": str(user_id),
        }
        if env_vars:
            session_env.update(env_vars)

        try:
            await self._backend.inject_env(warm.container_id, session_env)
        except RuntimeError:
            logger.error(f"❌ Failed to inject env into container {warm.container_id[:12]}")
            # Try to clean up the container
            await self._destroy_container(warm.container_id)
            raise

        now = datetime.now(timezone.utc)
        assignment = SandboxAssignment(
            session_id=session_id,
            user_id=user_id,
            chat_session_id=chat_session_id,
            container_id=warm.container_id,
            container_name=warm.container_name,
            state=SandboxState.ASSIGNED,
            created_at=warm.created_at,
            assigned_at=now,
            agent_config=agent_config or {},
        )

        async with self._lock:
            self._assignments[session_id] = assignment

        if db:
            await self._persist_assignment(db, assignment)
            await self._persist_event(
                db, assignment, "assigned", {"user_id": user_id}
            )

        logger.info(
            f"📌 Assigned container {warm.container_id[:12]} to session {session_id}"
        )

        # Replenish pool in background
        asyncio.create_task(self._replenish_pool())

        return assignment

    async def activate(
        self,
        session_id: str,
        db: AsyncSession | None = None,
    ) -> SandboxAssignment:
        """Transition sandbox from ASSIGNED to ACTIVE.

        Called when the sandbox container's health check passes.

        Args:
            session_id: Session identifier.
            db: Optional database session for persistence.

        Returns:
            Updated SandboxAssignment.

        Raises:
            KeyError: If session_id not found.
            ValueError: If invalid state transition.
        """
        async with self._lock:
            assignment = self._assignments.get(session_id)
            if assignment is None:
                raise KeyError(f"Session {session_id} not found")

            if not assignment.state.can_transition_to(SandboxState.ACTIVE):
                raise ValueError(
                    f"Cannot transition from {assignment.state} to ACTIVE"
                )

            assignment.state = SandboxState.ACTIVE
            assignment.activated_at = datetime.now(timezone.utc)

        if db:
            await self._persist_assignment(db, assignment)
            await self._persist_event(db, assignment, "activated", {})

        logger.info(f"✅ Activated sandbox for session {session_id}")
        return assignment

    async def release(
        self,
        session_id: str,
        db: AsyncSession | None = None,
    ) -> None:
        """Release a sandbox: DRAINING -> DESTROYED.

        Stops and removes the container, then replenishes the pool.

        Args:
            session_id: Session identifier.
            db: Optional database session for persistence.

        Raises:
            KeyError: If session_id not found.
        """
        async with self._lock:
            assignment = self._assignments.get(session_id)
            if assignment is None:
                raise KeyError(f"Session {session_id} not found")

            assignment.state = SandboxState.DRAINING

        if db:
            await self._persist_event(db, assignment, "draining", {})

        logger.info(f"🔄 Draining sandbox for session {session_id}")

        # Stop and remove container
        await self._destroy_container(assignment.container_id)

        async with self._lock:
            assignment.state = SandboxState.DESTROYED
            del self._assignments[session_id]

        if db:
            await self._persist_assignment(db, assignment)
            await self._persist_event(db, assignment, "destroyed", {})

        logger.info(f"🗑️ Destroyed sandbox for session {session_id}")

        # Replenish pool in background
        asyncio.create_task(self._replenish_pool())

    async def get_assignment(self, session_id: str) -> SandboxAssignment | None:
        """Get the assignment for a session.

        Args:
            session_id: Session identifier.

        Returns:
            SandboxAssignment if found, None otherwise.
        """
        return self._assignments.get(session_id)

    async def get_status(self) -> dict[str, Any]:
        """Get current manager status.

        Returns:
            Dict with pool stats, active sessions, etc.
        """
        return {
            "enabled": self._settings.enabled,
            "running": self._running,
            "warm_pool_size": self.warm_pool_size,
            "active_count": self.active_count,
            "total_count": self.total_count,
            "max_instances": self._settings.max_instances,
            "target_pool_size": self._settings.pool_size,
            "active_sessions": list(self._assignments.keys()),
        }

    # ── Internal Methods ──────────────────────────────────────────

    async def _create_warm_container(self) -> WarmContainer | None:
        """Create a single warm container.

        Returns:
            WarmContainer if created, None on failure.
        """
        name = f"sandbox-{uuid.uuid4().hex[:12]}"
        base_env = {
            "SANDBOX_NATS_URL": self._settings.nats_url,
            "SANDBOX_MCP_URL": self._settings.mcp_url,
            "SANDBOX_MODE": "warm",
        }

        try:
            info = await self._backend.create_container(
                name=name,
                image=self._settings.image,
                env=base_env,
                network=self._settings.network,
                cpu_limit=self._settings.cpu_limit,
                memory_limit=self._settings.memory_limit,
                labels={
                    _SANDBOX_LABEL: _SANDBOX_LABEL_VALUE,
                    "echomind.sandbox.state": SandboxState.WARM.value,
                },
            )
            await self._backend.start_container(info.container_id)

            warm = WarmContainer(
                container_id=info.container_id,
                container_name=info.name,
            )
            logger.info(f"🔥 Created warm container {name} ({info.container_id[:12]})")
            return warm
        except Exception as e:
            logger.error(f"❌ Failed to create warm container: {e}")
            return None

    async def _replenish_pool(self) -> None:
        """Fill the warm pool up to the configured pool_size."""
        async with self._lock:
            deficit = self._settings.pool_size - self.warm_pool_size
            headroom = self._settings.max_instances - self.total_count

        containers_to_create = min(deficit, headroom)
        if containers_to_create <= 0:
            return

        logger.info(f"🔄 Replenishing warm pool: creating {containers_to_create} containers")

        for _ in range(containers_to_create):
            warm = await self._create_warm_container()
            if warm:
                async with self._lock:
                    self._warm_pool.append(warm)

    async def _destroy_container(self, container_id: str) -> None:
        """Stop and remove a container, handling errors gracefully.

        Args:
            container_id: Docker container ID.
        """
        try:
            await self._backend.stop_container(container_id, timeout=5)
        except Exception as e:
            logger.warning(f"⚠️ Error stopping container {container_id[:12]}: {e}")

        try:
            await self._backend.remove_container(container_id, force=True)
        except Exception as e:
            logger.warning(f"⚠️ Error removing container {container_id[:12]}: {e}")

    async def _discover_existing_containers(self) -> None:
        """Discover and reconcile existing sandbox containers on startup.

        Finds containers with the echomind.sandbox label and reconstructs
        the warm pool / assignments from their state.
        """
        try:
            containers = await self._backend.list_containers(
                labels={_SANDBOX_LABEL: _SANDBOX_LABEL_VALUE}
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to discover existing containers: {e}")
            return

        for container in containers:
            state = container.labels.get("echomind.sandbox.state", "")
            if state == SandboxState.WARM.value and container.status == "running":
                self._warm_pool.append(
                    WarmContainer(
                        container_id=container.container_id,
                        container_name=container.name,
                    )
                )
            elif container.status in ("exited", "dead", "removing"):
                # Clean up stale containers
                await self._destroy_container(container.container_id)

        if self._warm_pool:
            logger.info(f"♻️ Discovered {len(self._warm_pool)} existing warm containers")

    async def _reconciliation_loop(self) -> None:
        """Background loop that enforces timeouts and replenishes the pool.

        Runs every reconciliation_interval seconds until stopped.
        """
        while self._running:
            try:
                await asyncio.sleep(self._settings.reconciliation_interval)
                await self._reconcile()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Reconciliation error: {e}")

    async def _reconcile(self) -> None:
        """Run a single reconciliation pass.

        - Enforce session_timeout on active sessions
        - Enforce idle_timeout on warm containers
        - Replenish warm pool
        """
        now = datetime.now(timezone.utc)

        # Enforce session timeout
        sessions_to_release: list[str] = []
        async with self._lock:
            for session_id, assignment in self._assignments.items():
                if assignment.state in (SandboxState.ASSIGNED, SandboxState.ACTIVE):
                    elapsed = (now - assignment.created_at).total_seconds()
                    if elapsed > self._settings.session_timeout:
                        sessions_to_release.append(session_id)
                        logger.warning(
                            f"⏰ Session {session_id} exceeded timeout "
                            f"({elapsed:.0f}s > {self._settings.session_timeout}s)"
                        )

        for session_id in sessions_to_release:
            try:
                await self.release(session_id)
            except Exception as e:
                logger.error(f"❌ Failed to release timed-out session {session_id}: {e}")

        # Enforce idle timeout on warm containers
        expired_warm: list[WarmContainer] = []
        async with self._lock:
            remaining: list[WarmContainer] = []
            for warm in self._warm_pool:
                idle_seconds = (now - warm.created_at).total_seconds()
                if idle_seconds > self._settings.idle_timeout:
                    expired_warm.append(warm)
                else:
                    remaining.append(warm)
            self._warm_pool = remaining

        for warm in expired_warm:
            logger.info(f"⏰ Destroying idle warm container {warm.container_id[:12]}")
            await self._destroy_container(warm.container_id)

        # Replenish pool
        await self._replenish_pool()

    # ── Persistence ───────────────────────────────────────────────

    async def _persist_assignment(
        self, db: AsyncSession, assignment: SandboxAssignment
    ) -> None:
        """Persist sandbox assignment to database.

        Args:
            db: Database session.
            assignment: Assignment to persist.
        """
        from sqlalchemy import text

        now = datetime.now(timezone.utc)

        try:
            await db.execute(
                text("""
                    INSERT INTO sandbox_sessions (
                        session_id, user_id, chat_session_id,
                        container_id, container_name, status,
                        assigned_at, activated_at, destroyed_at,
                        agent_config, message_count, tool_calls_count,
                        total_tokens, created_at, updated_at
                    ) VALUES (
                        :session_id, :user_id, :chat_session_id,
                        :container_id, :container_name, :status,
                        :assigned_at, :activated_at, :destroyed_at,
                        :agent_config::jsonb, :message_count, :tool_calls_count,
                        :total_tokens, :created_at, :updated_at
                    )
                    ON CONFLICT (session_id) DO UPDATE SET
                        status = :status,
                        assigned_at = :assigned_at,
                        activated_at = :activated_at,
                        destroyed_at = CASE
                            WHEN :status = 'destroyed' THEN :updated_at
                            ELSE sandbox_sessions.destroyed_at
                        END,
                        message_count = :message_count,
                        tool_calls_count = :tool_calls_count,
                        total_tokens = :total_tokens,
                        updated_at = :updated_at
                """),
                {
                    "session_id": assignment.session_id,
                    "user_id": assignment.user_id,
                    "chat_session_id": assignment.chat_session_id,
                    "container_id": assignment.container_id,
                    "container_name": assignment.container_name,
                    "status": assignment.state.value,
                    "assigned_at": assignment.assigned_at,
                    "activated_at": assignment.activated_at,
                    "destroyed_at": None,
                    "agent_config": "{}",
                    "message_count": assignment.message_count,
                    "tool_calls_count": assignment.tool_calls_count,
                    "total_tokens": assignment.total_tokens,
                    "created_at": assignment.created_at,
                    "updated_at": now,
                },
            )
            await db.commit()
        except Exception as e:
            logger.error(f"❌ Failed to persist assignment {assignment.session_id}: {e}")
            await db.rollback()

    async def _persist_event(
        self,
        db: AsyncSession,
        assignment: SandboxAssignment,
        event_type: str,
        event_data: dict[str, Any],
    ) -> None:
        """Persist a sandbox lifecycle event.

        Args:
            db: Database session.
            assignment: Related assignment.
            event_type: Event type string.
            event_data: Event payload.
        """
        from sqlalchemy import text
        import json

        try:
            await db.execute(
                text("""
                    INSERT INTO sandbox_events (
                        sandbox_session_id, event_type, event_data
                    )
                    SELECT id, :event_type, :event_data::jsonb
                    FROM sandbox_sessions
                    WHERE session_id = :session_id
                """),
                {
                    "session_id": assignment.session_id,
                    "event_type": event_type,
                    "event_data": json.dumps(event_data),
                },
            )
            await db.commit()
        except Exception as e:
            logger.error(
                f"❌ Failed to persist event {event_type} for {assignment.session_id}: {e}"
            )
            await db.rollback()
