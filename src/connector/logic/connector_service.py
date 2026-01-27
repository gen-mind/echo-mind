"""
Connector Service business logic.

Orchestrates provider sync operations, MinIO uploads, and NATS publishing.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from echomind_lib.db.minio import MinIOClient
from echomind_lib.db.models import Connector, Document
from echomind_lib.db.nats_publisher import JetStreamPublisher

from connector.logic.checkpoint import (
    ConnectorCheckpoint,
    deserialize_checkpoint,
    serialize_checkpoint,
)
from connector.logic.exceptions import (
    DatabaseError,
    MinioUploadError,
    ProviderNotFoundError,
)
from connector.logic.providers.base import (
    BaseProvider,
    DeletedFile,
    DownloadedFile,
)
from connector.logic.providers.google_drive import GoogleDriveProvider
from connector.logic.providers.onedrive import OneDriveProvider

logger = logging.getLogger("echomind-connector.service")


# Provider registry
PROVIDERS: dict[str, type[BaseProvider]] = {
    "google_drive": GoogleDriveProvider,
    "onedrive": OneDriveProvider,
}


class ConnectorService:
    """
    Main connector service that handles sync operations.

    Coordinates between:
    - Database (connector config, document records)
    - Providers (Google Drive, OneDrive)
    - MinIO (file storage)
    - NATS (publishing document.process messages)
    """

    def __init__(
        self,
        db_session: AsyncSession,
        minio_client: MinIOClient,
        nats_publisher: JetStreamPublisher,
        minio_bucket: str = "documents",
    ):
        """
        Initialize connector service.

        Args:
            db_session: Async database session.
            minio_client: MinIO client for file storage.
            nats_publisher: NATS publisher for messages.
            minio_bucket: MinIO bucket name.
        """
        self._db = db_session
        self._minio = minio_client
        self._nats = nats_publisher
        self._bucket = minio_bucket
        self._providers: dict[str, BaseProvider] = {}

    async def get_provider(self, connector_type: str) -> BaseProvider:
        """
        Get or create a provider instance.

        Args:
            connector_type: Type of connector (e.g., 'google_drive').

        Returns:
            BaseProvider instance.

        Raises:
            ProviderNotFoundError: If provider type not supported.
        """
        if connector_type not in self._providers:
            if connector_type not in PROVIDERS:
                raise ProviderNotFoundError(connector_type)
            self._providers[connector_type] = PROVIDERS[connector_type]()
        return self._providers[connector_type]

    async def sync_connector(self, connector_id: int) -> int:
        """
        Sync a connector by ID.

        Main entry point for sync operations triggered by NATS messages.

        Args:
            connector_id: ID of the connector to sync.

        Returns:
            Number of documents processed.

        Raises:
            ConnectorError: If sync fails.
        """
        logger.info("🔄 Starting sync for connector %d", connector_id)

        # Load connector from database
        connector = await self._get_connector(connector_id)
        if not connector:
            raise DatabaseError(
                "get_connector",
                f"Connector {connector_id} not found",
            )

        # Update status to syncing
        await self._update_connector_status(connector, "syncing")

        try:
            # Get provider
            provider = await self.get_provider(connector.type)

            # Load checkpoint from state
            checkpoint = self._load_checkpoint(connector.state, connector.type)

            # Authenticate
            await provider.authenticate(connector.config)

            # Sync and process documents
            docs_processed = 0

            async for item in provider.sync(connector.config, checkpoint):
                if isinstance(item, DownloadedFile):
                    await self._process_downloaded_file(connector, item)
                    docs_processed += 1
                elif isinstance(item, DeletedFile):
                    await self._process_deleted_file(connector, item)

                # Save checkpoint periodically
                if docs_processed % 10 == 0:
                    await self._save_checkpoint(connector, checkpoint)

            # Save final checkpoint
            await self._save_checkpoint(connector, checkpoint)

            # Update connector stats
            connector.docs_analyzed = (connector.docs_analyzed or 0) + docs_processed
            connector.last_sync_at = datetime.now(timezone.utc)
            await self._db.commit()

            logger.info(
                "✅ Sync completed for connector %d: %d documents processed",
                connector_id,
                docs_processed,
            )
            return docs_processed

        except Exception as e:
            logger.exception("❌ Sync failed for connector %d", connector_id)
            await self._update_connector_status(
                connector, "error", str(e)
            )
            raise

    async def _get_connector(self, connector_id: int) -> Connector | None:
        """
        Load connector from database.

        Args:
            connector_id: Connector ID.

        Returns:
            Connector model or None if not found.
        """
        result = await self._db.execute(
            select(Connector).where(Connector.id == connector_id)
        )
        return result.scalar_one_or_none()

    async def _update_connector_status(
        self,
        connector: Connector,
        status: str,
        message: str | None = None,
    ) -> None:
        """
        Update connector status in database.

        Args:
            connector: Connector model.
            status: New status.
            message: Optional status message.
        """
        connector.status = status
        connector.status_message = message
        connector.last_update = datetime.now(timezone.utc)
        await self._db.commit()

    def _load_checkpoint(
        self,
        state: dict[str, Any],
        connector_type: str,
    ) -> ConnectorCheckpoint:
        """
        Load checkpoint from connector state.

        Args:
            state: Connector state JSON.
            connector_type: Type of connector.

        Returns:
            Checkpoint instance.
        """
        if "checkpoint" in state:
            try:
                return deserialize_checkpoint(state["checkpoint"])
            except Exception as e:
                logger.warning(
                    "⚠️ Failed to deserialize checkpoint, creating new: %s", e
                )

        # Create fresh checkpoint based on provider
        provider_class = PROVIDERS.get(connector_type)
        if provider_class:
            return provider_class().create_checkpoint()
        return ConnectorCheckpoint()

    async def _save_checkpoint(
        self,
        connector: Connector,
        checkpoint: ConnectorCheckpoint,
    ) -> None:
        """
        Save checkpoint to connector state.

        Args:
            connector: Connector model.
            checkpoint: Checkpoint to save.
        """
        if connector.state is None:
            connector.state = {}
        connector.state["checkpoint"] = serialize_checkpoint(checkpoint)
        await self._db.commit()

    async def _process_downloaded_file(
        self,
        connector: Connector,
        file: DownloadedFile,
    ) -> None:
        """
        Process a downloaded file.

        1. Upload to MinIO
        2. Create/update document record
        3. Publish to NATS

        Args:
            connector: Connector model.
            file: Downloaded file.
        """
        # Generate MinIO path
        object_name = self._generate_minio_path(connector, file)

        # Upload to MinIO
        try:
            await self._minio.upload_file(
                bucket_name=self._bucket,
                object_name=object_name,
                data=file.content,
                content_type=file.mime_type,
            )
            logger.info("✅ Uploaded %s to MinIO: %s", file.name, object_name)
        except Exception as e:
            raise MinioUploadError(object_name, str(e)) from e

        # Create or update document
        doc = await self._upsert_document(connector, file, object_name)

        # Publish to NATS
        await self._publish_document_process(doc)

    async def _process_deleted_file(
        self,
        connector: Connector,
        file: DeletedFile,
    ) -> None:
        """
        Process a deleted file.

        Marks document as deleted in database.

        Args:
            connector: Connector model.
            file: Deleted file info.
        """
        result = await self._db.execute(
            select(Document).where(
                Document.connector_id == connector.id,
                Document.source_id == file.source_id,
            )
        )
        doc = result.scalar_one_or_none()

        if doc:
            doc.status = "deleted"
            doc.last_update = datetime.now(timezone.utc)
            await self._db.commit()
            logger.info(
                "🔄 Marked document %d as deleted (source: %s)",
                doc.id,
                file.source_id,
            )

    def _generate_minio_path(
        self,
        connector: Connector,
        file: DownloadedFile,
    ) -> str:
        """
        Generate MinIO object path for a file.

        Format: {connector_id}/{source_id}/{uuid}_{filename}

        Args:
            connector: Connector model.
            file: Downloaded file.

        Returns:
            MinIO object path.
        """
        safe_name = file.name.replace("/", "_").replace("\\", "_")
        unique_id = uuid.uuid4().hex[:8]
        return f"{connector.id}/{file.source_id}/{unique_id}_{safe_name}"

    async def _upsert_document(
        self,
        connector: Connector,
        file: DownloadedFile,
        minio_url: str,
    ) -> Document:
        """
        Create or update document record.

        Args:
            connector: Connector model.
            file: Downloaded file.
            minio_url: MinIO object path.

        Returns:
            Document model.
        """
        # Check for existing document
        result = await self._db.execute(
            select(Document).where(
                Document.connector_id == connector.id,
                Document.source_id == file.source_id,
            )
        )
        doc = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if doc:
            # Update existing
            doc.url = minio_url
            doc.original_url = file.original_url
            doc.title = file.name
            doc.content_type = file.mime_type
            doc.signature = file.content_hash
            doc.status = "pending"
            doc.last_update = now
        else:
            # Create new
            doc = Document(
                connector_id=connector.id,
                source_id=file.source_id,
                url=minio_url,
                original_url=file.original_url,
                title=file.name,
                content_type=file.mime_type,
                signature=file.content_hash,
                status="pending",
                creation_date=now,
            )
            self._db.add(doc)

        await self._db.commit()
        await self._db.refresh(doc)

        logger.info(
            "✅ %s document %d for source %s",
            "Updated" if doc else "Created",
            doc.id,
            file.source_id,
        )
        return doc

    async def _publish_document_process(self, doc: Document) -> None:
        """
        Publish document.process message to NATS.

        Args:
            doc: Document model to process.
        """
        # Create protobuf message
        # Generated protobuf lacks type stubs
        from echomind_lib.models.internal.semantic_pb2 import DocumentProcessRequest  # type: ignore[import-untyped]

        message = DocumentProcessRequest(
            document_id=doc.id,
            connector_id=doc.connector_id,
            url=doc.url or "",
            content_type=doc.content_type or "",
        )

        await self._nats.publish(
            subject="document.process",
            payload=message.SerializeToString(),
        )

        logger.info("✅ Published document.process for document %d", doc.id)

    async def close(self) -> None:
        """
        Clean up resources.

        Closes all provider connections.
        """
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()
