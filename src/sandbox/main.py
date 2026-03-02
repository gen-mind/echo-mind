"""
EchoMind Sandbox Agent -- Entry Point.

Ephemeral single-session agent process running inside a Docker container.
Connects to NATS for message routing and runs a Semantic Kernel agent
with MCP-provided tools.

Usage:
    python -m sandbox.main

Environment Variables:
    SANDBOX_NATS_URL: NATS server URL (default: nats://nats:4222)
    SANDBOX_MCP_URL: MCP gateway HTTP URL (default: http://mcp-server:8080)
    SANDBOX_SESSION_ID: Unique session identifier (required when active)
    SANDBOX_USER_ID: Owner user ID (required when active)
    SANDBOX_MODE: Container mode -- 'warm' or 'active' (default: warm)
    SANDBOX_LOG_LEVEL: Logging level (default: INFO)
    SANDBOX_HEALTH_PORT: Health probe HTTP port (default: 8080)
    SANDBOX_HEARTBEAT_INTERVAL: Seconds between heartbeats (default: 15)
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import threading
from datetime import datetime, timezone

import nats
from nats.aio.client import Client as NATSClient
from nats.aio.msg import Msg

from echomind_lib.helpers.readiness_probe import HealthServer
from sandbox.agent_runner import AgentRunner, QueryContext
from sandbox.config import SandboxSettings

logger = logging.getLogger("echomind-sandbox")


class SandboxAgent:
    """
    Single-session agent running inside an ephemeral Docker container.

    Lifecycle:
    1. Start health server (always first, for Docker HEALTHCHECK)
    2. Connect to NATS (with resilience retry)
    3. If mode=='warm': wait for ASSIGNED signal on control subject
    4. If mode=='active': immediately subscribe to input messages
    5. Run heartbeat loop
    6. Process messages until shutdown signal

    Attributes:
        settings: Sandbox configuration from environment variables.
    """

    def __init__(self, settings: SandboxSettings | None = None) -> None:
        """
        Initialize sandbox agent.

        Args:
            settings: Sandbox configuration. Auto-loads from env if None.
        """
        self.settings = settings or SandboxSettings()
        self._nc: NATSClient | None = None
        self._js: nats.js.JetStreamContext | None = None
        self._running = True
        self._ready = False
        self._health_server: HealthServer | None = None
        self._agent_runner: AgentRunner | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._retry_tasks: list[asyncio.Task[None]] = []
        self._subscriptions: list[nats.aio.subscription.Subscription] = []
        self._shutdown_event = asyncio.Event()

        # Connection state tracking (resilience pattern)
        self._nats_connected = False

    def _is_ready(self) -> bool:
        """Check if the sandbox is ready to process messages.

        Returns:
            True if NATS is connected and agent is initialized.
        """
        return self._nats_connected and self._ready

    def _update_readiness(self) -> None:
        """Update health server readiness based on connection state."""
        if self._health_server:
            self._health_server.set_ready(self._is_ready())

    async def start(self) -> None:
        """
        Start the sandbox agent.

        Initializes health server, connects to NATS, subscribes to
        session subjects, and enters the main processing loop.
        """
        # Configure logging
        logging.basicConfig(
            level=self.settings.log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            force=True,
        )

        logger.info("🚀 EchoMind Sandbox Agent starting...")
        logger.info("📋 Configuration:")
        logger.info(f"   📡 NATS: {self.settings.nats_url}")
        logger.info(f"   🌐 MCP: {self.settings.mcp_url}")
        logger.info(f"   🔑 Session: {self.settings.session_id or '<warm pool>'}")
        logger.info(f"   👤 User: {self.settings.user_id or '<unassigned>'}")
        logger.info(f"   🔧 Mode: {self.settings.mode}")
        logger.info(f"   💓 Health port: {self.settings.health_port}")

        # 1. Start health server (always first for Docker HEALTHCHECK)
        self._health_server = HealthServer(port=self.settings.health_port)
        health_thread = threading.Thread(
            target=self._health_server.start, daemon=True
        )
        health_thread.start()
        logger.info(f"💓 Health server started on port {self.settings.health_port}")

        # 2. Connect to NATS (with resilience pattern)
        logger.info("🛠️ Connecting to NATS...")
        try:
            await self._connect_nats()
            self._nats_connected = True
            logger.info("📡 NATS connected")
        except Exception as e:
            logger.warning(f"⚠️ NATS connection failed: {e}")
            logger.info("🔄 Will retry NATS connection in background...")
            self._retry_tasks.append(
                asyncio.create_task(self._retry_nats_connection())
            )

        # 3. Enter appropriate mode
        if self.settings.mode == "active" and self._nats_connected:
            await self._activate()
        elif self.settings.mode == "warm" and self._nats_connected:
            await self._enter_warm_mode()
        elif not self._nats_connected:
            logger.warning("⚠️ Sandbox started without NATS -- waiting for reconnect")

        self._update_readiness()

        if self._is_ready():
            logger.info("🚀 Sandbox agent ready")
        else:
            logger.warning("⚠️ Sandbox agent started with degraded connectivity")

    async def _connect_nats(self) -> None:
        """
        Establish NATS connection and JetStream context.

        Raises:
            Exception: If NATS connection fails.
        """
        self._nc = await nats.connect(
            servers=[self.settings.nats_url],
            connect_timeout=5,
            max_reconnect_attempts=-1,  # Unlimited: long-lived container, rely on readiness probe
            reconnect_time_wait=2,
        )
        self._js = self._nc.jetstream()

    async def _retry_nats_connection(self) -> None:
        """Background task to retry NATS connection every 30 seconds."""
        while not self._nats_connected:
            await asyncio.sleep(30)
            try:
                await self._connect_nats()
                self._nats_connected = True
                logger.info("📡 NATS reconnected")

                # Enter appropriate mode after reconnect
                if self.settings.mode == "active":
                    await self._activate()
                else:
                    await self._enter_warm_mode()

                self._update_readiness()
            except Exception as e:
                logger.warning(f"⚠️ NATS reconnection attempt failed: {e}")

    async def _enter_warm_mode(self) -> None:
        """
        Enter warm pool mode -- wait for assignment via control subject.

        Subscribes to a generic control subject for warm containers.
        When an ASSIGN message arrives, transitions to active mode.
        """
        if not self._nc:
            return

        logger.info("🔥 Entering warm pool mode -- waiting for assignment...")

        # Subscribe to control subject for assignment signal
        # Warm containers use a wildcard or generic subject until assigned
        # Queue group ensures only ONE warm container processes each assignment message
        sub = await self._nc.subscribe(
            "sandbox.warm.control",
            queue="sandbox-warm-pool",
            cb=self._handle_warm_control,
        )
        self._subscriptions.append(sub)

        # Mark as ready (warm containers are ready to be assigned)
        self._ready = True
        self._update_readiness()

    async def _handle_warm_control(self, msg: Msg) -> None:
        """
        Handle control messages in warm mode.

        Expects an ASSIGN message with session_id, user_id, and configuration.

        Args:
            msg: NATS message with assignment payload.
        """
        try:
            data = json.loads(msg.data)
            msg_type = data.get("type", "")

            if msg_type == "assign":
                # Update settings with session-specific values
                self.settings.session_id = data["session_id"]
                self.settings.user_id = data["user_id"]
                self.settings.mode = "active"

                # Update optional config from assignment
                if "llm_provider" in data:
                    self.settings.llm_provider = data["llm_provider"]
                if "llm_model" in data:
                    self.settings.llm_model = data["llm_model"]
                if "llm_api_key" in data:
                    self.settings.llm_api_key = data["llm_api_key"]
                if "llm_endpoint" in data:
                    self.settings.llm_endpoint = data["llm_endpoint"]
                if "agent_instructions" in data:
                    self.settings.agent_instructions = data["agent_instructions"]

                logger.info(
                    "📦 Received assignment: session=%s, user=%d",
                    self.settings.session_id,
                    self.settings.user_id,
                )

                # Unsubscribe from warm control and activate
                for sub in self._subscriptions:
                    await sub.unsubscribe()
                self._subscriptions.clear()

                await self._activate()

            elif msg_type == "shutdown":
                logger.info("🛑 Warm container received shutdown signal")
                self._running = False
                self._shutdown_event.set()

        except Exception as e:
            logger.exception("❌ Failed to handle warm control message: %s", e)

    async def _activate(self) -> None:
        """
        Activate the sandbox for a specific session.

        Initializes the agent runner, subscribes to session-specific
        NATS subjects, starts the heartbeat loop, and publishes a
        ready signal.
        """
        if not self._nc:
            logger.error("❌ Cannot activate: NATS not connected")
            return

        session_id = self.settings.session_id
        if not session_id:
            logger.error("❌ Cannot activate: no session_id configured")
            return

        logger.info("⚡ Activating sandbox for session %s", session_id)

        # Initialize agent runner
        self._agent_runner = AgentRunner(self.settings, self._nc)
        await self._agent_runner.initialize()

        # Subscribe to session-specific subjects
        input_sub = await self._nc.subscribe(
            f"sandbox.{session_id}.input",
            cb=self._handle_input,
        )
        self._subscriptions.append(input_sub)

        control_sub = await self._nc.subscribe(
            f"sandbox.{session_id}.control",
            cb=self._handle_control,
        )
        self._subscriptions.append(control_sub)

        # Start heartbeat loop
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Publish ready signal
        await self._nc.publish(
            f"sandbox.{session_id}.health",
            json.dumps({
                "type": "ready",
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }).encode("utf-8"),
        )

        self._ready = True
        self._update_readiness()
        logger.info("🚀 Sandbox activated for session %s", session_id)

    async def _handle_input(self, msg: Msg) -> None:
        """
        Handle incoming user messages on the input subject.

        Dispatches to the agent runner for query processing.

        Args:
            msg: NATS message with user query payload.
        """
        if not self._running or not self._agent_runner:
            return

        try:
            data = json.loads(msg.data)
            msg_type = data.get("type", "query")

            if msg_type == "query":
                context = QueryContext(
                    query=data.get("query", ""),
                    conversation_history=data.get("conversation_history", []),
                    sources=data.get("sources", []),
                    metadata=data.get("metadata", {}),
                )
                await self._agent_runner.process_query(context)

            else:
                logger.warning("⚠️ Unknown input message type: %s", msg_type)

        except json.JSONDecodeError as e:
            logger.error("❌ Invalid JSON in input message: %s", e)
        except Exception as e:
            logger.exception("❌ Failed to process input message: %s", e)

    async def _handle_control(self, msg: Msg) -> None:
        """
        Handle control messages (cancel, shutdown, config updates).

        Args:
            msg: NATS message with control payload.
        """
        try:
            data = json.loads(msg.data)
            msg_type = data.get("type", "")

            if msg_type == "shutdown":
                logger.info("🛑 Received shutdown command")
                self._running = False
                self._shutdown_event.set()

            elif msg_type == "cancel":
                logger.info("🚫 Received cancel command -- cancelling current query")
                # TODO: Phase 5 -- Implement query cancellation via agent runner

            elif msg_type == "config_update":
                logger.info("🔧 Received config update")
                # TODO: Phase 5 -- Hot-reload agent configuration

            else:
                logger.warning("⚠️ Unknown control message type: %s", msg_type)

        except json.JSONDecodeError as e:
            logger.error("❌ Invalid JSON in control message: %s", e)
        except Exception as e:
            logger.exception("❌ Failed to handle control message: %s", e)

    async def _heartbeat_loop(self) -> None:
        """
        Publish periodic heartbeat to the health subject.

        Runs every ``heartbeat_interval`` seconds until shutdown.
        Includes session metrics and status.
        """
        session_id = self.settings.session_id
        subject = f"sandbox.{session_id}.health"

        while self._running:
            try:
                await asyncio.sleep(self.settings.heartbeat_interval)

                if not self._nc or self._nc.is_closed:
                    logger.warning("⚠️ Skipping heartbeat: NATS disconnected")
                    continue

                metrics = (
                    self._agent_runner.metrics.to_dict()
                    if self._agent_runner
                    else {}
                )
                payload = json.dumps({
                    "type": "heartbeat",
                    "session_id": session_id,
                    "status": "active" if self._running else "draining",
                    "metrics": metrics,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }).encode("utf-8")

                await self._nc.publish(subject, payload)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("⚠️ Heartbeat publish failed: %s", e)

    async def run(self) -> None:
        """
        Main event loop -- keeps the sandbox alive until shutdown.

        Blocks until ``_running`` is set to False by a shutdown signal
        or control message, using an asyncio.Event for efficient waiting
        instead of polling.
        """
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        """
        Graceful shutdown.

        1. Mark as not ready
        2. Cancel heartbeat and retry tasks
        3. Publish destroy event
        4. Shut down agent runner
        5. Unsubscribe and disconnect from NATS
        """
        logger.info("🛑 Sandbox agent shutting down...")
        self._running = False
        self._shutdown_event.set()

        # Mark as not ready
        if self._health_server:
            self._health_server.set_ready(False)

        # Cancel heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            logger.info("💓 Heartbeat stopped")

        # Cancel retry tasks
        for task in self._retry_tasks:
            task.cancel()
        if self._retry_tasks:
            await asyncio.gather(*self._retry_tasks, return_exceptions=True)

        # Publish destroy event
        if self._nc and not self._nc.is_closed and self.settings.session_id:
            try:
                payload = json.dumps({
                    "type": "destroyed",
                    "session_id": self.settings.session_id,
                    "metrics": (
                        self._agent_runner.metrics.to_dict()
                        if self._agent_runner
                        else {}
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }).encode("utf-8")
                await self._nc.publish(
                    f"sandbox.{self.settings.session_id}.health",
                    payload,
                )
                logger.info("📤 Published destroy event")
            except Exception as e:
                logger.warning("⚠️ Failed to publish destroy event: %s", e)

        # Shut down agent runner
        if self._agent_runner:
            await self._agent_runner.shutdown()

        # Unsubscribe all
        for sub in self._subscriptions:
            try:
                await sub.unsubscribe()
            except Exception:
                pass
        self._subscriptions.clear()

        # Disconnect NATS
        if self._nc and not self._nc.is_closed:
            await self._nc.drain()
            await self._nc.close()
            logger.info("📡 NATS disconnected")

        # Stop health server
        if self._health_server:
            self._health_server.stop()
            logger.info("💓 Health server stopped")

        logger.info("👋 Sandbox agent stopped")


async def main() -> None:
    """Main entry point for the sandbox agent process."""
    agent = SandboxAgent()

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def signal_handler() -> None:
        """Handle SIGTERM/SIGINT for graceful shutdown."""
        logger.info("🛑 Received shutdown signal")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await agent.start()

        # Wait for either the run loop to end or a shutdown signal
        run_task = asyncio.create_task(agent.run())
        stop_task = asyncio.create_task(stop_event.wait())

        done, pending = await asyncio.wait(
            [run_task, stop_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except asyncio.CancelledError:
        logger.info("🛑 Received cancellation")
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
