"""
Sandbox Runner - Entry point for agent-sandbox Docker containers.

This module runs inside each sandbox container and:
1. Starts a health server on port 8080
2. Waits for session assignment (reads /tmp/sandbox.env)
3. Connects to NATS and subscribes to session-specific subjects
4. Runs the agent (BasicAgentWrapper) with MCP tools
5. Streams responses back via NATS

NATS subjects:
    sandbox.{session_id}.input   - Incoming user messages
    sandbox.{session_id}.output  - Final agent responses
    sandbox.{session_id}.stream  - Token-by-token streaming
    sandbox.{session_id}.control - Cancel/shutdown commands
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - %(message)s",
)
logger = logging.getLogger("echomind-sandbox-runner")


class SandboxRunner:
    """Main runner for sandbox containers.

    Manages the lifecycle of a sandbox: health checks, NATS subscription,
    agent execution, and graceful shutdown.
    """

    def __init__(self) -> None:
        """Initialize SandboxRunner."""
        self._running = False
        self._nats_client: object | None = None
        self._health_task: asyncio.Task[None] | None = None
        self._env_watch_task: asyncio.Task[None] | None = None
        self._session_id: str = ""
        self._user_id: str = ""

    async def start(self) -> None:
        """Start the sandbox runner.

        1. Start health server
        2. Watch for session assignment
        3. Connect to NATS when assigned
        4. Subscribe to session subjects
        """
        self._running = True
        logger.info("🚀 Sandbox runner starting")

        # Register signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        # Start health server
        self._health_task = asyncio.create_task(self._run_health_server())

        # Load initial settings
        settings = self._load_settings()

        if settings.get("mode") == "warm":
            logger.info("🔥 Container in warm mode, watching for assignment...")
            self._env_watch_task = asyncio.create_task(self._watch_for_assignment())
        else:
            # Already assigned (e.g., restart)
            self._session_id = settings.get("session_id", "")
            self._user_id = settings.get("user_id", "")
            if self._session_id:
                await self._activate(settings)

        # Keep running
        while self._running:
            await asyncio.sleep(1)

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        if not self._running:
            return

        logger.info("🛑 Shutting down sandbox runner")
        self._running = False

        if self._env_watch_task:
            self._env_watch_task.cancel()
        if self._health_task:
            self._health_task.cancel()

        # Close NATS
        if self._nats_client is not None:
            try:
                import nats

                if isinstance(self._nats_client, nats.aio.client.Client):
                    await self._nats_client.close()
            except Exception as e:
                logger.warning(f"⚠️ Error closing NATS: {e}")

        logger.info("👋 Sandbox runner stopped")

    def _load_settings(self) -> dict[str, str]:
        """Load settings from environment and /tmp/sandbox.env.

        Returns:
            Dict of setting key-value pairs.
        """
        settings: dict[str, str] = {}

        # Read from env file if it exists
        env_file = Path("/tmp/sandbox.env")
        if env_file.exists():
            for line in env_file.read_text().strip().splitlines():
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    key, _, value = line.partition("=")
                    settings[key.strip().lower().removeprefix("sandbox_")] = value.strip()

        # Override with actual env vars
        for key in ("SANDBOX_SESSION_ID", "SANDBOX_USER_ID", "SANDBOX_MODE",
                     "SANDBOX_NATS_URL", "SANDBOX_MCP_URL", "SANDBOX_LLM_ENDPOINT",
                     "SANDBOX_LLM_MODEL", "SANDBOX_LLM_API_KEY"):
            val = os.environ.get(key, "")
            if val:
                settings[key.lower().removeprefix("sandbox_")] = val

        return settings

    async def _watch_for_assignment(self) -> None:
        """Poll for /tmp/sandbox.env changes indicating assignment."""
        env_file = Path("/tmp/sandbox.env")
        last_mtime: float = 0

        while self._running:
            try:
                if env_file.exists():
                    current_mtime = env_file.stat().st_mtime
                    if current_mtime > last_mtime:
                        last_mtime = current_mtime
                        settings = self._load_settings()
                        session_id = settings.get("session_id", "")
                        if session_id and session_id != self._session_id:
                            self._session_id = session_id
                            self._user_id = settings.get("user_id", "")
                            logger.info(f"📌 Assignment detected: session={session_id}")
                            await self._activate(settings)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error watching for assignment: {e}")
                await asyncio.sleep(5)

    async def _activate(self, settings: dict[str, str]) -> None:
        """Activate the sandbox for a session.

        Args:
            settings: Configuration settings dict.
        """
        nats_url = settings.get("nats_url", "nats://nats:4222")
        session_id = self._session_id

        logger.info(f"🔌 Activating sandbox for session {session_id}")

        try:
            import nats as nats_lib

            self._nats_client = await nats_lib.connect(nats_url)
            logger.info(f"📡 Connected to NATS at {nats_url}")

            js = self._nats_client.jetstream()

            # Subscribe to input messages
            input_subject = f"sandbox.{session_id}.input"
            await js.subscribe(
                input_subject,
                cb=self._handle_input_message,
                durable=f"sandbox-{session_id}-input",
                stream="sandbox-stream",
            )
            logger.info(f"👂 Subscribed to {input_subject}")

            # Subscribe to control messages
            control_subject = f"sandbox.{session_id}.control"
            await js.subscribe(
                control_subject,
                cb=self._handle_control_message,
                durable=f"sandbox-{session_id}-control",
                stream="sandbox-stream",
            )
            logger.info(f"👂 Subscribed to {control_subject}")

            # Publish health ping
            await js.publish(
                f"sandbox.{session_id}.health",
                json.dumps({"status": "active", "session_id": session_id}).encode(),
            )

            logger.info(f"✅ Sandbox activated for session {session_id}")
        except Exception as e:
            logger.error(f"❌ Failed to activate sandbox: {e}")

    async def _handle_input_message(self, msg: object) -> None:
        """Handle incoming user message.

        Args:
            msg: NATS message with user input.
        """
        try:
            data = json.loads(msg.data.decode())  # type: ignore[union-attr]
            query = data.get("query", "")
            logger.info(f"📨 Received message: {query[:50]}...")

            # TODO: Run agent with MCP tools and stream response
            # For now, acknowledge the message
            response = {
                "session_id": self._session_id,
                "response": f"Echo from sandbox: {query}",
                "status": "complete",
            }

            # Publish response
            if self._nats_client:
                import nats as nats_lib

                if isinstance(self._nats_client, nats_lib.aio.client.Client):
                    js = self._nats_client.jetstream()
                    await js.publish(
                        f"sandbox.{self._session_id}.output",
                        json.dumps(response).encode(),
                    )

            await msg.ack()  # type: ignore[union-attr]
            logger.info("✅ Message processed and response published")
        except Exception as e:
            logger.error(f"❌ Error handling input message: {e}")
            try:
                await msg.nak()  # type: ignore[union-attr]
            except Exception:
                pass

    async def _handle_control_message(self, msg: object) -> None:
        """Handle control messages (cancel, shutdown).

        Args:
            msg: NATS message with control command.
        """
        try:
            data = json.loads(msg.data.decode())  # type: ignore[union-attr]
            command = data.get("command", "")
            logger.info(f"🎮 Control command: {command}")

            if command == "shutdown":
                await msg.ack()  # type: ignore[union-attr]
                await self.shutdown()
            elif command == "cancel":
                # TODO: Cancel current agent execution
                await msg.ack()  # type: ignore[union-attr]
                logger.info("🚫 Cancellation requested")
            else:
                logger.warning(f"⚠️ Unknown control command: {command}")
                await msg.ack()  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"❌ Error handling control message: {e}")

    async def _run_health_server(self) -> None:
        """Run a simple HTTP health check server on port 8080."""
        from aiohttp import web

        async def healthz(request: web.Request) -> web.Response:
            """Health check endpoint."""
            status = {
                "status": "ok",
                "session_id": self._session_id or None,
                "mode": "active" if self._session_id else "warm",
            }
            return web.json_response(status)

        app = web.Application()
        app.router.add_get("/healthz", healthz)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8080)

        try:
            await site.start()
            logger.info("🏥 Health server listening on :8080")
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()


async def main() -> None:
    """Entry point for the sandbox runner."""
    runner = SandboxRunner()
    await runner.start()


if __name__ == "__main__":
    asyncio.run(main())
