"""
EchoMind MCP Gateway Service Entry Point.

Exposes EchoMind capabilities (search, skills) as MCP tools over
streamable HTTP transport using FastMCP.

Usage:
    python main.py

Environment Variables:
    MCP_GATEWAY_ENABLED: Enable gateway (default: true)
    MCP_GATEWAY_HEALTH_PORT: Health check port (default: 8080)
    MCP_GATEWAY_MCP_PORT: MCP HTTP transport port (default: 8100)
    MCP_GATEWAY_QDRANT_HOST: Qdrant host (default: localhost)
    MCP_GATEWAY_QDRANT_PORT: Qdrant REST port (default: 6333)
    MCP_GATEWAY_EMBEDDER_HOST: Embedder gRPC host (default: localhost)
    MCP_GATEWAY_EMBEDDER_PORT: Embedder gRPC port (default: 50051)
    MCP_GATEWAY_SKILLS_DIR: Skills directory path (default: /app/config/skills)
    MCP_GATEWAY_LOG_LEVEL: Logging level (default: INFO)
"""

import asyncio
import logging
import os
import signal
import sys
import threading

from fastmcp import FastMCP

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from echomind_lib.db.qdrant import QdrantDB
from echomind_lib.helpers.readiness_probe import HealthServer

from mcp_gateway.backends.embedder_client import EmbedderClient
from mcp_gateway.backends.search_backend import SearchBackend
from mcp_gateway.config import get_settings
from mcp_gateway.skills.executor import SkillExecutor
from mcp_gateway.skills.registry import SkillRegistry
from mcp_gateway.tools.search import register_search_tools
from mcp_gateway.tools.skills import register_skills_tools

# Configure logging
logging.basicConfig(
    level=os.getenv("MCP_GATEWAY_LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("echomind-mcp-gateway")


class MCPGateway:
    """
    Main MCP Gateway application.

    Manages lifecycle of FastMCP server, Qdrant, and Embedder connections.
    Implements graceful degradation: retries failed connections in background.
    Tools check readiness before executing operations.
    """

    def __init__(self) -> None:
        """Initialize MCP Gateway."""
        self._settings = get_settings()
        self._health_server: HealthServer | None = None
        self._running = False
        self._qdrant_connected = False
        self._embedder_connected = False
        self._retry_tasks: list[asyncio.Task] = []
        self._mcp_task: asyncio.Task | None = None
        self._qdrant: QdrantDB | None = None
        self._embedder: EmbedderClient | None = None

    def _is_ready(self) -> bool:
        """Check if all required connections are established."""
        return self._qdrant_connected and self._embedder_connected

    def _update_readiness(self) -> None:
        """Update health server readiness based on connection state."""
        if self._health_server:
            self._health_server.set_ready(self._is_ready())

    async def start(self) -> None:
        """
        Start the MCP Gateway service.

        Initializes:
        - Health check server (always starts first)
        - Qdrant connection (retries on failure)
        - Embedder gRPC connection (retries on failure)
        - Skill registry and executor
        - FastMCP server with registered tools
        """
        logger.info("🚀 EchoMind MCP Gateway Service starting...")
        logger.info("📋 Configuration:")
        logger.info(f"   ⚙️ Enabled: {self._settings.enabled}")
        logger.info(f"   🔌 Health port: {self._settings.health_port}")
        logger.info(f"   🌐 MCP port: {self._settings.mcp_port}")
        logger.info(
            f"   🗄️ Qdrant: {self._settings.qdrant_host}:{self._settings.qdrant_port}"
        )
        logger.info(
            f"   🧠 Embedder: {self._settings.embedder_host}:{self._settings.embedder_port}"
        )
        logger.info(f"   📂 Skills dir: {self._settings.skills_dir}")

        if not self._settings.enabled:
            logger.warning("⚠️ MCP Gateway is disabled via configuration")
            return

        # Start health server first (Kubernetes needs it)
        self._health_server = HealthServer(port=self._settings.health_port)
        health_thread = threading.Thread(
            target=self._health_server.start, daemon=True
        )
        health_thread.start()
        logger.info(f"💓 Health server started on port {self._settings.health_port}")

        # Initialize Qdrant
        logger.info("🛠️ Connecting to Qdrant...")
        try:
            self._qdrant = QdrantDB(
                host=self._settings.qdrant_host,
                port=self._settings.qdrant_port,
                api_key=self._settings.qdrant_api_key,
            )
            await self._qdrant.init()
            self._qdrant_connected = True
            logger.info("🗄️ Qdrant connected")
        except Exception as e:
            logger.warning(f"⚠️ Qdrant connection failed: {e}")
            logger.info("🔄 Will retry Qdrant connection in background...")
            self._retry_tasks.append(
                asyncio.create_task(self._retry_qdrant_connection())
            )

        # Initialize Embedder client
        logger.info("🛠️ Connecting to Embedder...")
        try:
            self._embedder = EmbedderClient(
                host=self._settings.embedder_host,
                port=self._settings.embedder_port,
                timeout=self._settings.embedder_timeout,
            )
            healthy = await self._embedder.health_check()
            if healthy:
                self._embedder_connected = True
                logger.info("🧠 Embedder connected")
            else:
                raise ConnectionError("Embedder health check failed")
        except Exception as e:
            logger.warning(f"⚠️ Embedder connection failed: {e}")
            logger.info("🔄 Will retry Embedder connection in background...")
            self._retry_tasks.append(
                asyncio.create_task(self._retry_embedder_connection())
            )

        # Load skills registry
        skill_registry = SkillRegistry(skills_dir=self._settings.skills_dir)
        skill_registry.load()
        logger.info(
            f"📦 Skill registry loaded ({skill_registry.skill_count} skills)"
        )

        # Create skill executor
        skill_executor = SkillExecutor(
            default_timeout=self._settings.skill_execution_timeout,
            max_output_bytes=self._settings.skill_max_output_bytes,
        )

        # Create search backend
        search_backend = SearchBackend(
            qdrant=self._qdrant,
            embedder=self._embedder,
        )

        # Create FastMCP server and register tools
        mcp = FastMCP("echomind-mcp-gateway")

        register_search_tools(mcp, search_backend)
        register_skills_tools(mcp, skill_registry, skill_executor)

        logger.info("🔧 MCP tools registered")

        # Run MCP server as background task (async)
        self._mcp_task = asyncio.create_task(
            mcp.run_http_async(
                transport="streamable-http",
                host="0.0.0.0",
                port=self._settings.mcp_port,
            )
        )
        logger.info(f"🌐 MCP server started on port {self._settings.mcp_port}")

        # Update readiness
        self._update_readiness()
        self._running = True

        if self._is_ready():
            logger.info("🚀 MCP Gateway ready")
        else:
            logger.warning(
                "⚠️ MCP Gateway started with degraded connectivity, retrying..."
            )

    async def _retry_qdrant_connection(self) -> None:
        """Background task to retry Qdrant connection every 30 seconds."""
        while not self._qdrant_connected:
            await asyncio.sleep(30)
            try:
                self._qdrant = QdrantDB(
                    host=self._settings.qdrant_host,
                    port=self._settings.qdrant_port,
                    api_key=self._settings.qdrant_api_key,
                )
                await self._qdrant.init()
                self._qdrant_connected = True
                logger.info("🗄️ Qdrant reconnected")
                self._update_readiness()
            except Exception as e:
                logger.warning(f"⚠️ Qdrant reconnection attempt failed: {e}")

    async def _retry_embedder_connection(self) -> None:
        """Background task to retry Embedder connection every 30 seconds."""
        while not self._embedder_connected:
            await asyncio.sleep(30)
            try:
                self._embedder = EmbedderClient(
                    host=self._settings.embedder_host,
                    port=self._settings.embedder_port,
                    timeout=self._settings.embedder_timeout,
                )
                healthy = await self._embedder.health_check()
                if not healthy:
                    raise ConnectionError("Embedder health check failed")
                self._embedder_connected = True
                logger.info("🧠 Embedder reconnected")
                self._update_readiness()
            except Exception as e:
                logger.warning(
                    f"⚠️ Embedder reconnection attempt failed: {e}"
                )

    async def stop(self) -> None:
        """
        Stop the MCP Gateway service gracefully.

        Cancels retry tasks, stops MCP server, closes connections.
        """
        logger.info("🛑 MCP Gateway shutting down...")
        self._running = False

        # Mark as not ready
        if self._health_server:
            self._health_server.set_ready(False)

        # Cancel retry tasks
        for task in self._retry_tasks:
            task.cancel()

        # Stop MCP server
        if self._mcp_task:
            self._mcp_task.cancel()
            try:
                await self._mcp_task
            except asyncio.CancelledError:
                pass
            logger.info("🌐 MCP server stopped")

        # Close Qdrant
        if self._qdrant:
            await self._qdrant.close()
            logger.info("🗄️ Qdrant disconnected")

        # Close Embedder
        if self._embedder:
            await self._embedder.close()
            logger.info("🧠 Embedder disconnected")

        logger.info("👋 MCP Gateway stopped")


async def main() -> None:
    """Main entry point for the MCP Gateway service."""
    gateway = MCPGateway()

    # Setup signal handlers
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def signal_handler() -> None:
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await gateway.start()

        # Wait for stop signal
        await stop_event.wait()

    except KeyboardInterrupt:
        logger.info("🛑 Received keyboard interrupt")
    finally:
        await gateway.stop()


if __name__ == "__main__":
    asyncio.run(main())
