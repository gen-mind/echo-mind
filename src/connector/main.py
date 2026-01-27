"""
EchoMind Connector Service Entry Point.

NATS subscriber that fetches files from external sources (Google Drive, OneDrive)
and uploads them to MinIO for processing.

Usage:
    python main.py

Environment Variables:
    CONNECTOR_ENABLED: Enable connector service (default: true)
    CONNECTOR_HEALTH_PORT: Health check port (default: 8080)
    CONNECTOR_DATABASE_URL: PostgreSQL connection URL
    CONNECTOR_NATS_URL: NATS server URL
    CONNECTOR_MINIO_ENDPOINT: MinIO endpoint
    CONNECTOR_LOG_LEVEL: Logging level (default: INFO)
"""

import asyncio
import logging
import os
import signal
import sys
import threading
from typing import Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from echomind_lib.db.connection import close_db, get_db_manager, init_db
from echomind_lib.db.minio import close_minio, get_minio, init_minio
from echomind_lib.db.nats_publisher import (
    close_nats_publisher,
    get_nats_publisher,
    init_nats_publisher,
)
from echomind_lib.db.nats_subscriber import (
    JetStreamSubscriber,
    close_nats_subscriber,
    init_nats_subscriber,
)
from echomind_lib.helpers.readiness_probe import HealthServer

from connector.config import get_settings
from connector.logic.connector_service import ConnectorService

# Configure logging
logging.basicConfig(
    level=os.getenv("CONNECTOR_LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("echomind-connector")


class ConnectorApp:
    """
    Main connector application.

    Manages lifecycle of NATS subscriber, database, and MinIO connections.
    """

    def __init__(self):
        """Initialize connector application."""
        self._settings = get_settings()
        self._subscriber: JetStreamSubscriber | None = None
        self._health_server: HealthServer | None = None
        self._running = False

    async def start(self) -> None:
        """
        Start the connector service.

        Initializes:
        - Database connection
        - MinIO client
        - NATS publisher and subscriber
        - Health check server
        """
        logger.info("🛠️ Starting EchoMind Connector Service...")
        logger.info("🛠️ Configuration:")
        logger.info("🛠️    Enabled: %s", self._settings.enabled)
        logger.info("🛠️    Health port: %d", self._settings.health_port)
        logger.info("🛠️    Database: %s", self._mask_url(self._settings.database_url))
        logger.info("🛠️    NATS: %s", self._settings.nats_url)
        logger.info("🛠️    MinIO: %s", self._settings.minio_endpoint)

        if not self._settings.enabled:
            logger.warning("⚠️ Connector is disabled via configuration")
            return

        # Initialize database
        logger.info("🔌 Connecting to database...")
        try:
            await init_db(
                self._settings.database_url,
                echo=self._settings.database_echo,
            )
            logger.info("✅ Database connected")
        except Exception as e:
            logger.error("❌ Database connection failed: %s", e)
            raise

        # Initialize MinIO
        logger.info("🔌 Connecting to MinIO...")
        try:
            await init_minio(
                endpoint=self._settings.minio_endpoint,
                access_key=self._settings.minio_access_key,
                secret_key=self._settings.minio_secret_key,
                secure=self._settings.minio_secure,
            )
            logger.info("✅ MinIO connected")
        except Exception as e:
            logger.error("❌ MinIO connection failed: %s", e)
            await close_db()
            raise

        # Initialize NATS publisher
        logger.info("🔌 Connecting to NATS (publisher)...")
        try:
            await init_nats_publisher(
                servers=[self._settings.nats_url],
                user=self._settings.nats_user,
                password=self._settings.nats_password,
            )
            logger.info("✅ NATS publisher connected")
        except Exception as e:
            logger.error("❌ NATS publisher connection failed: %s", e)
            close_minio()
            await close_db()
            raise

        # Initialize NATS subscriber
        logger.info("🔌 Connecting to NATS (subscriber)...")
        try:
            self._subscriber = await init_nats_subscriber(
                servers=[self._settings.nats_url],
                user=self._settings.nats_user,
                password=self._settings.nats_password,
            )
            logger.info("✅ NATS subscriber connected")
        except Exception as e:
            logger.error("❌ NATS subscriber connection failed: %s", e)
            await close_nats_publisher()
            close_minio()
            await close_db()
            raise

        # Start health server
        self._health_server = HealthServer(port=self._settings.health_port)
        health_thread = threading.Thread(target=self._health_server.start, daemon=True)
        health_thread.start()
        logger.info("✅ Health server started on port %d", self._settings.health_port)

        # Subscribe to NATS subjects
        await self._setup_subscriptions()

        # Mark as ready
        self._health_server.set_ready(True)
        self._running = True
        logger.info("✅ Connector ready")

    async def _setup_subscriptions(self) -> None:
        """Set up NATS subscriptions for connector sync events."""
        if not self._subscriber:
            return

        subjects = [
            "connector.sync.google_drive",
            "connector.sync.onedrive",
        ]

        for subject in subjects:
            await self._subscriber.subscribe(
                stream=self._settings.nats_stream_name,
                consumer=f"{self._settings.nats_consumer_name}-{subject.split('.')[-1]}",
                subject=subject,
                handler=self._handle_sync_message,
            )
            logger.info("✅ Subscribed to %s", subject)

    async def _handle_sync_message(self, msg: Any) -> None:
        """
        Handle incoming sync message from NATS.

        Args:
            msg: NATS message with ConnectorSyncRequest payload.
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # Parse message
            # Generated protobuf lacks type stubs
            from echomind_lib.models.internal.orchestrator_pb2 import (  # type: ignore[import-untyped]
                ConnectorSyncRequest,
            )

            request = ConnectorSyncRequest()
            request.ParseFromString(msg.data)

            connector_id = request.connector_id
            logger.info(
                "🔄 Received sync request for connector %d", connector_id
            )

            # Process sync
            db = get_db_manager()
            minio = get_minio()
            publisher = get_nats_publisher()

            async with db.session() as session:
                service = ConnectorService(
                    db_session=session,
                    minio_client=minio,
                    nats_publisher=publisher,
                    minio_bucket=self._settings.minio_bucket,
                )

                try:
                    docs_processed = await service.sync_connector(connector_id)
                    logger.info(
                        "✅ Sync completed for connector %d: %d documents",
                        connector_id,
                        docs_processed,
                    )
                    await msg.ack()
                finally:
                    await service.close()

        except Exception as e:
            logger.exception("❌ Sync message handling failed: %s", e)
            await msg.nak()

        finally:
            elapsed = asyncio.get_event_loop().time() - start_time
            logger.info("⏰ Message processing time: %.2fs", elapsed)

    async def stop(self) -> None:
        """
        Stop the connector service gracefully.

        Shuts down subscriber, closes database and MinIO connections.
        """
        logger.info("🔄 Connector shutting down...")
        self._running = False

        # Mark as not ready
        if self._health_server:
            self._health_server.set_ready(False)

        # Close NATS subscriber
        await close_nats_subscriber()
        logger.info("✅ NATS subscriber disconnected")

        # Close NATS publisher
        await close_nats_publisher()
        logger.info("✅ NATS publisher disconnected")

        # Close MinIO
        close_minio()
        logger.info("✅ MinIO disconnected")

        # Close database
        await close_db()
        logger.info("✅ Database disconnected")

        logger.info("✅ Connector stopped")

    def _mask_url(self, url: str) -> str:
        """Mask password in connection URL for logging."""
        if "@" in url and ":" in url.split("@")[0]:
            parts = url.split("@")
            user_pass = parts[0].split(":")
            if len(user_pass) > 2:
                return f"{user_pass[0]}:{user_pass[1]}:***@{parts[1]}"
        return url


async def main() -> None:
    """Main entry point."""
    app = ConnectorApp()

    # Setup signal handlers
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def signal_handler() -> None:
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await app.start()

        # Wait for stop signal
        await stop_event.wait()

    except KeyboardInterrupt:
        logger.info("⚠️ Received keyboard interrupt")
    except Exception as e:
        logger.exception("💀 Fatal error: %s", e)
        sys.exit(1)
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
