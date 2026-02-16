"""
EchoMind MCP Gateway Service Entry Point.

Exposes EchoMind capabilities (search, connectors, API proxy, skills) as
MCP tools over streamable HTTP transport using FastMCP.

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
    MCP_GATEWAY_EMBEDDER_MODEL: Embedder model name (documentation/future use)
    MCP_GATEWAY_DATABASE_URL: PostgreSQL async URL
    MCP_GATEWAY_NATS_URL: NATS server URL
    MCP_GATEWAY_NATS_USER: NATS username (optional)
    MCP_GATEWAY_NATS_PASSWORD: NATS password (optional)
    MCP_GATEWAY_SKILLS_DIR: Skills directory path (default: /app/config/skills)
    MCP_GATEWAY_LOG_LEVEL: Logging level (default: INFO)
"""

import asyncio
import logging
import signal
import threading
import urllib.parse

from fastmcp import FastMCP
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from echomind_lib.db.qdrant import QdrantDB
from echomind_lib.helpers.readiness_probe import HealthServer

from mcp_gateway.backends.api_key_manager import ApiKeyManager
from mcp_gateway.backends.api_proxy_backend import ApiProxyBackend
from mcp_gateway.backends.client_holder import ClientHolder
from mcp_gateway.backends.connector_backend import ConnectorBackend
from mcp_gateway.backends.embedder_client import EmbedderClient
from mcp_gateway.backends.nats_backend import NatsBackend
from mcp_gateway.backends.search_backend import SearchBackend
from mcp_gateway.config import get_settings
from mcp_gateway.middleware.audit_logger import AuditLoggingMiddleware
from mcp_gateway.middleware.error_handler import ErrorHandlingMiddleware
from mcp_gateway.skills.executor import SkillExecutor
from mcp_gateway.skills.registry import SkillRegistry
from mcp_gateway.tools.api_proxy import register_api_proxy_tools
from mcp_gateway.tools.connectors import register_connector_tools
from mcp_gateway.tools.search import register_search_tools
from mcp_gateway.tools.skills import register_skills_tools

logger = logging.getLogger("echomind-mcp-gateway")


def _mask_db_url(url: str) -> str:
    """
    Mask credentials in a database URL for safe logging.

    Extracts only host, port, and database name from the URL.

    Args:
        url: Full database connection URL.

    Returns:
        Masked string showing only host:port/dbname.
    """
    if not url:
        return "<not configured>"
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or "unknown"
        port = parsed.port or "5432"
        dbname = parsed.path.lstrip("/") or "unknown"
        return f"{host}:{port}/{dbname}"
    except Exception:
        return "<invalid url>"


class MCPGateway:
    """
    Main MCP Gateway application.

    Manages lifecycle of FastMCP server, Qdrant, Embedder, PostgreSQL,
    and NATS connections. Implements graceful degradation: retries failed
    connections in background. Tools check readiness before executing.
    """

    def __init__(self) -> None:
        """Initialize MCP Gateway."""
        self._settings = get_settings()

        # Configure logging from settings
        logging.basicConfig(
            level=self._settings.log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            force=True,
        )

        self._health_server: HealthServer | None = None
        self._qdrant_connected = False
        self._embedder_connected = False
        self._db_connected = False
        self._nats_connected = False
        self._retry_tasks: list[asyncio.Task] = []
        self._mcp_task: asyncio.Task | None = None
        self._db_engine = None

        # Shared mutable client holder — backends read from this on every call
        self._clients = ClientHolder()

    def _is_ready(self) -> bool:
        """Check if all required connections are established."""
        return (
            self._qdrant_connected
            and self._embedder_connected
            and self._db_connected
            and self._nats_connected
        )

    def _update_readiness(self) -> None:
        """Update health server readiness based on connection state."""
        if self._health_server:
            self._health_server.set_ready(self._is_ready())

    async def start(self) -> None:
        """
        Start the MCP Gateway service.

        Initializes:
        - Health check server (always starts first)
        - PostgreSQL connection (retries on failure)
        - NATS connection (retries on failure)
        - Qdrant connection (retries on failure)
        - Embedder gRPC connection (retries on failure)
        - Skill registry and executor
        - API key manager
        - FastMCP server with registered tools and audit middleware
        """
        db_url = self._settings.database_url.get_secret_value()
        nats_password = (
            self._settings.nats_password.get_secret_value()
            if self._settings.nats_password
            else None
        )
        qdrant_api_key = (
            self._settings.qdrant_api_key.get_secret_value()
            if self._settings.qdrant_api_key
            else None
        )

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
        logger.info(f"   🐘 Database: {_mask_db_url(db_url)}")
        logger.info(f"   📡 NATS: {self._settings.nats_url}")
        logger.info(f"   📂 Skills dir: {self._settings.skills_dir}")
        logger.info(f"   🔤 Embedder model: {self._settings.embedder_model}")

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

        # Initialize PostgreSQL
        logger.info("🛠️ Connecting to PostgreSQL...")
        try:
            self._db_engine = create_async_engine(
                db_url,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
            )
            # Verify connectivity
            async with self._db_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            self._clients.session_factory = async_sessionmaker(
                bind=self._db_engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False,
            )
            self._db_connected = True
            logger.info("🐘 PostgreSQL connected")
        except Exception as e:
            logger.warning(f"⚠️ PostgreSQL connection failed: {e}")
            logger.info("🔄 Will retry PostgreSQL connection in background...")
            self._retry_tasks.append(
                asyncio.create_task(self._retry_db_connection())
            )

        # Initialize NATS
        logger.info("🛠️ Connecting to NATS...")
        try:
            self._clients.nats = NatsBackend(
                url=self._settings.nats_url,
                user=self._settings.nats_user,
                password=nats_password,
            )
            await self._clients.nats.connect()
            self._nats_connected = True
            logger.info("📡 NATS connected")
        except Exception as e:
            logger.warning(f"⚠️ NATS connection failed: {e}")
            logger.info("🔄 Will retry NATS connection in background...")
            self._retry_tasks.append(
                asyncio.create_task(self._retry_nats_connection())
            )

        # Initialize Qdrant
        logger.info("🛠️ Connecting to Qdrant...")
        try:
            self._clients.qdrant = QdrantDB(
                host=self._settings.qdrant_host,
                port=self._settings.qdrant_port,
                api_key=qdrant_api_key,
            )
            await self._clients.qdrant.init()
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
            self._clients.embedder = EmbedderClient(
                host=self._settings.embedder_host,
                port=self._settings.embedder_port,
                timeout=self._settings.embedder_timeout,
                model_name=self._settings.embedder_model,
            )
            healthy = await self._clients.embedder.health_check()
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

        # Create API key manager
        api_key_manager = ApiKeyManager()

        # Create backends with shared client holder
        search_backend = SearchBackend(clients=self._clients)
        connector_backend = ConnectorBackend(clients=self._clients)
        api_proxy_backend = ApiProxyBackend(api_key_manager)

        # Create FastMCP server with error handling + audit middleware
        mcp = FastMCP("echomind-mcp-gateway")
        mcp.add_middleware(ErrorHandlingMiddleware())
        mcp.add_middleware(AuditLoggingMiddleware())

        # Register all tools
        register_search_tools(mcp, search_backend, readiness_check=self._is_ready)
        register_skills_tools(mcp, skill_registry, skill_executor)
        register_connector_tools(mcp, connector_backend)
        register_api_proxy_tools(mcp, api_proxy_backend)

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

        if self._is_ready():
            logger.info("🚀 MCP Gateway ready")
        else:
            logger.warning(
                "⚠️ MCP Gateway started with degraded connectivity, retrying..."
            )

    async def _retry_db_connection(self) -> None:
        """Background task to retry PostgreSQL connection every 30 seconds."""
        db_url = self._settings.database_url.get_secret_value()
        while not self._db_connected:
            await asyncio.sleep(30)
            try:
                # Dispose old engine before creating a new one
                if self._db_engine:
                    await self._db_engine.dispose()

                self._db_engine = create_async_engine(
                    db_url,
                    pool_size=5,
                    max_overflow=10,
                    pool_pre_ping=True,
                )
                async with self._db_engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                self._clients.session_factory = async_sessionmaker(
                    bind=self._db_engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                    autocommit=False,
                    autoflush=False,
                )
                self._db_connected = True
                logger.info("🐘 PostgreSQL reconnected")
                self._update_readiness()
            except Exception as e:
                logger.warning(f"⚠️ PostgreSQL reconnection attempt failed: {e}")

    async def _retry_nats_connection(self) -> None:
        """Background task to retry NATS connection every 30 seconds."""
        nats_password = (
            self._settings.nats_password.get_secret_value()
            if self._settings.nats_password
            else None
        )
        while not self._nats_connected:
            await asyncio.sleep(30)
            try:
                self._clients.nats = NatsBackend(
                    url=self._settings.nats_url,
                    user=self._settings.nats_user,
                    password=nats_password,
                )
                await self._clients.nats.connect()
                self._nats_connected = True
                logger.info("📡 NATS reconnected")
                self._update_readiness()
            except Exception as e:
                logger.warning(f"⚠️ NATS reconnection attempt failed: {e}")

    async def _retry_qdrant_connection(self) -> None:
        """Background task to retry Qdrant connection every 30 seconds."""
        qdrant_api_key = (
            self._settings.qdrant_api_key.get_secret_value()
            if self._settings.qdrant_api_key
            else None
        )
        while not self._qdrant_connected:
            await asyncio.sleep(30)
            try:
                self._clients.qdrant = QdrantDB(
                    host=self._settings.qdrant_host,
                    port=self._settings.qdrant_port,
                    api_key=qdrant_api_key,
                )
                await self._clients.qdrant.init()
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
                self._clients.embedder = EmbedderClient(
                    host=self._settings.embedder_host,
                    port=self._settings.embedder_port,
                    timeout=self._settings.embedder_timeout,
                    model_name=self._settings.embedder_model,
                )
                healthy = await self._clients.embedder.health_check()
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

        # Mark as not ready
        if self._health_server:
            self._health_server.set_ready(False)

        # Cancel retry tasks and await them
        for task in self._retry_tasks:
            task.cancel()
        if self._retry_tasks:
            await asyncio.gather(*self._retry_tasks, return_exceptions=True)

        # Stop MCP server
        if self._mcp_task:
            self._mcp_task.cancel()
            try:
                await self._mcp_task
            except asyncio.CancelledError:
                pass
            logger.info("🌐 MCP server stopped")

        # Close NATS
        if self._clients.nats:
            await self._clients.nats.close()
            logger.info("📡 NATS disconnected")

        # Close database
        if self._db_engine:
            await self._db_engine.dispose()
            logger.info("🐘 PostgreSQL disconnected")

        # Close Qdrant
        if self._clients.qdrant:
            await self._clients.qdrant.close()
            logger.info("🗄️ Qdrant disconnected")

        # Close Embedder
        if self._clients.embedder:
            await self._clients.embedder.close()
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

    except asyncio.CancelledError:
        logger.info("🛑 Received cancellation")
    finally:
        await gateway.stop()


if __name__ == "__main__":
    asyncio.run(main())
