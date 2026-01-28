"""
Connector business logic service.

Handles connector CRUD operations and NATS sync message publishing.
"""

import logging
import uuid
from datetime import datetime, timezone

from google.protobuf import struct_pb2
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.logic.exceptions import NotFoundError, ValidationError
from echomind_lib.db.models import Connector as ConnectorORM
from echomind_lib.db.models import Document as DocumentORM
from echomind_lib.db.nats_publisher import JetStreamPublisher
from echomind_lib.models.internal.orchestrator_pb2 import ConnectorSyncRequest
from echomind_lib.models.public import connector_pb2

logger = logging.getLogger(__name__)


class ConnectorService:
    """Service for connector-related business logic."""

    def __init__(
        self,
        db: AsyncSession,
        nats_publisher: JetStreamPublisher | None = None,
    ):
        """
        Initialize connector service.

        Args:
            db: Database session.
            nats_publisher: Optional NATS publisher for sync messages.
        """
        self.db = db
        self.nats = nats_publisher

    async def get_connector(self, connector_id: int, user_id: int) -> ConnectorORM:
        """
        Get a connector by ID for a specific user.

        Args:
            connector_id: The connector ID.
            user_id: The user ID (for ownership check).

        Returns:
            ConnectorORM: The connector.

        Raises:
            NotFoundError: If connector not found.
        """
        result = await self.db.execute(
            select(ConnectorORM)
            .where(ConnectorORM.id == connector_id)
            .where(ConnectorORM.user_id == user_id)
            .where(ConnectorORM.deleted_date.is_(None))
        )
        connector = result.scalar_one_or_none()

        if not connector:
            raise NotFoundError("Connector", connector_id)

        return connector

    async def create_connector(
        self,
        name: str,
        connector_type: str,
        user_id: int,
        config: dict | None = None,
        refresh_freq_minutes: int | None = None,
        scope: str | None = None,
        scope_id: str | None = None,
        trigger_sync: bool = True,
    ) -> ConnectorORM:
        """
        Create a new connector and optionally trigger initial sync.

        Args:
            name: Connector name.
            connector_type: Type (google_drive, onedrive, etc.).
            user_id: Owner user ID.
            config: Connector configuration.
            refresh_freq_minutes: Sync frequency.
            scope: Connector scope (user, group, org).
            scope_id: Scope ID for group scope.
            trigger_sync: Whether to publish NATS sync message.

        Returns:
            ConnectorORM: The created connector.
        """
        connector = ConnectorORM(
            name=name,
            type=connector_type,
            config=config or {},
            state={},
            refresh_freq_minutes=refresh_freq_minutes,
            user_id=user_id,
            scope=scope,
            scope_id=scope_id or "",
            status="pending",
            user_id_last_update=user_id,
        )

        self.db.add(connector)
        await self.db.flush()
        await self.db.refresh(connector)

        logger.info(
            "✅ Created connector %d (%s) for user %d",
            connector.id,
            connector.type,
            user_id,
        )

        # Trigger initial sync if requested
        if trigger_sync and self.nats:
            await self._publish_sync_message(connector)

        return connector

    async def update_connector(
        self,
        connector_id: int,
        user_id: int,
        name: str | None = None,
        config: dict | None = None,
        refresh_freq_minutes: int | None = None,
        scope: str | None = None,
        scope_id: str | None = None,
    ) -> ConnectorORM:
        """
        Update a connector.

        Args:
            connector_id: The connector ID.
            user_id: The user ID (for ownership check).
            name: New name.
            config: New configuration.
            refresh_freq_minutes: New sync frequency.
            scope: New scope.
            scope_id: New scope ID.

        Returns:
            ConnectorORM: The updated connector.

        Raises:
            NotFoundError: If connector not found.
        """
        connector = await self.get_connector(connector_id, user_id)

        if name:
            connector.name = name
        if config:
            connector.config = config
        if refresh_freq_minutes is not None:
            connector.refresh_freq_minutes = refresh_freq_minutes
        if scope:
            connector.scope = scope
        if scope_id is not None:
            connector.scope_id = scope_id

        connector.user_id_last_update = user_id

        logger.info("✅ Updated connector %d", connector_id)

        return connector

    async def delete_connector(
        self,
        connector_id: int,
        user_id: int,
    ) -> None:
        """
        Soft delete a connector.

        Args:
            connector_id: The connector ID.
            user_id: The user ID (for ownership check).

        Raises:
            NotFoundError: If connector not found.
        """
        connector = await self.get_connector(connector_id, user_id)

        connector.deleted_date = datetime.now(timezone.utc)
        connector.user_id_last_update = user_id

        logger.info("🗑️ Deleted connector %d", connector_id)

    async def trigger_sync(
        self,
        connector_id: int,
        user_id: int,
    ) -> tuple[bool, str]:
        """
        Trigger a manual sync for a connector.

        Args:
            connector_id: The connector ID.
            user_id: The user ID (for ownership check).

        Returns:
            Tuple of (success, message).

        Raises:
            NotFoundError: If connector not found.
        """
        connector = await self.get_connector(connector_id, user_id)

        if connector.status == "syncing":
            return False, "Sync already in progress"

        if not self.nats:
            logger.warning("⚠️ NATS publisher not available, cannot trigger sync")
            return False, "NATS not available"

        # Update status to pending
        connector.status = "pending"
        connector.user_id_last_update = user_id

        # Publish sync message
        await self._publish_sync_message(connector)

        return True, "Sync triggered"

    async def get_connector_status(
        self,
        connector_id: int,
        user_id: int,
    ) -> dict:
        """
        Get detailed status for a connector.

        Args:
            connector_id: The connector ID.
            user_id: The user ID (for ownership check).

        Returns:
            Dict with status information.

        Raises:
            NotFoundError: If connector not found.
        """
        connector = await self.get_connector(connector_id, user_id)

        # Count pending documents
        pending_result = await self.db.execute(
            select(func.count(DocumentORM.id))
            .where(DocumentORM.connector_id == connector_id)
            .where(DocumentORM.status == "pending")
        )
        docs_pending = pending_result.scalar() or 0

        return {
            "status": connector.status,
            "status_message": connector.status_message,
            "last_sync_at": connector.last_sync_at,
            "docs_analyzed": connector.docs_analyzed,
            "docs_pending": docs_pending,
        }

    async def _publish_sync_message(self, connector: ConnectorORM) -> None:
        """
        Publish a sync message to NATS.

        Args:
            connector: The connector to sync.
        """
        if not self.nats:
            logger.warning("⚠️ NATS publisher not available")
            return

        # Generate chunking session ID
        chunking_session = str(uuid.uuid4())

        # Build protobuf message
        request = ConnectorSyncRequest()
        request.connector_id = connector.id
        request.user_id = connector.user_id
        request.chunking_session = chunking_session

        # Set connector type enum (proto enum names are prefixed with CONNECTOR_TYPE_)
        type_name = f"CONNECTOR_TYPE_{connector.type.upper()}" if connector.type else "CONNECTOR_TYPE_UNSPECIFIED"
        type_value = getattr(
            connector_pb2.ConnectorType,
            type_name,
            connector_pb2.ConnectorType.CONNECTOR_TYPE_UNSPECIFIED,
        )
        request.type = type_value

        # Set scope enum (proto enum names are prefixed with CONNECTOR_SCOPE_)
        scope_name = f"CONNECTOR_SCOPE_{connector.scope.upper()}" if connector.scope else "CONNECTOR_SCOPE_USER"
        scope_value = getattr(
            connector_pb2.ConnectorScope,
            scope_name,
            connector_pb2.ConnectorScope.CONNECTOR_SCOPE_USER,
        )
        request.scope = scope_value

        if connector.scope_id:
            request.scope_id = connector.scope_id

        # Convert config dict to protobuf Struct
        if connector.config:
            config_struct = struct_pb2.Struct()
            config_struct.update(connector.config)
            request.config.CopyFrom(config_struct)

        # Convert state dict to protobuf Struct
        if connector.state:
            state_struct = struct_pb2.Struct()
            state_struct.update(connector.state)
            request.state.CopyFrom(state_struct)

        # Determine NATS subject based on connector type
        subject = f"connector.sync.{connector.type}"

        # Publish message
        await self.nats.publish(subject, request.SerializeToString())

        logger.info(
            "📤 Published sync message for connector %d to %s (session: %s)",
            connector.id,
            subject,
            chunking_session,
        )