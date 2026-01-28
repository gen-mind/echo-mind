"""
Ingestor Service business logic.

Orchestrates document ingestion without protocol concerns.
Coordinates extraction, chunking, embedding, and storage.
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from echomind_lib.db.minio import MinIOClient
from echomind_lib.db.models import Document
from echomind_lib.db.qdrant import QdrantDB

from ingestor.config import IngestorSettings
from ingestor.grpc.embedder_client import EmbedderClient
from ingestor.logic.document_processor import DocumentProcessor
from ingestor.logic.exceptions import (
    DatabaseError,
    DocumentNotFoundError,
    FileNotFoundInStorageError,
    MinioError,
)

logger = logging.getLogger("echomind-ingestor.service")


class IngestorService:
    """
    Main Ingestor service handling document ingestion.

    Coordinates between:
    - Database (document records, status updates)
    - MinIO (file storage)
    - DocumentProcessor (extraction + chunking)
    - EmbedderClient (gRPC to Embedder service)
    - QdrantDB (vector storage)

    Attributes:
        db: Async database session.
        minio: MinIO client for file operations.
        qdrant: Qdrant client for vector storage.
        settings: Ingestor service settings.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        minio_client: MinIOClient,
        qdrant_client: QdrantDB,
        settings: IngestorSettings,
    ) -> None:
        """
        Initialize Ingestor service.

        Args:
            db_session: Async database session.
            minio_client: MinIO client for file storage.
            qdrant_client: Qdrant client for vector storage.
            settings: Service configuration.
        """
        self._db = db_session
        self._minio = minio_client
        self._qdrant = qdrant_client
        self._settings = settings
        self._processor = DocumentProcessor(settings)
        self._embedder = EmbedderClient(
            host=settings.embedder_host,
            port=settings.embedder_port,
            timeout=settings.embedder_timeout,
        )

    async def process_document(
        self,
        document_id: int,
        connector_id: int,
        user_id: int,
        minio_path: str,
        chunking_session: str,
        scope: str,
        scope_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Process a document for ingestion.

        Full pipeline: download → extract → chunk → embed → store → update status.

        Args:
            document_id: Document ID in database.
            connector_id: Connector that owns this document.
            user_id: User who owns the connector.
            minio_path: Path to file in MinIO bucket.
            chunking_session: UUID for this processing session.
            scope: Document scope (user, group, org).
            scope_id: Optional scope identifier.

        Returns:
            Dictionary with processing results:
            - document_id: Processed document ID
            - chunk_count: Number of chunks created
            - collection_name: Qdrant collection used

        Raises:
            DocumentNotFoundError: If document not in database.
            FileNotFoundInStorageError: If file not in MinIO.
            ExtractionError: If content extraction fails.
            ChunkingError: If chunking fails.
            EmbeddingError: If embedding generation fails.
        """
        logger.info(
            "🔄 Processing document %d (path: %s, session: %s)",
            document_id,
            minio_path,
            chunking_session,
        )

        # Load document from database
        document = await self._get_document(document_id)
        if not document:
            raise DocumentNotFoundError(document_id)

        # Update status to processing
        await self._update_status(document_id, "processing")

        try:
            # Download file from MinIO
            logger.info("📥 Downloading from MinIO: %s", minio_path)
            file_bytes = await self._download_file(minio_path)

            # Get file metadata
            file_name = minio_path.split("/")[-1]
            mime_type = document.content_type or "application/octet-stream"

            # Extract and chunk content
            logger.info("📄 Extracting and chunking: %s (%s)", file_name, mime_type)
            chunks, structured_images = await self._processor.process(
                file_bytes=file_bytes,
                document_id=document_id,
                file_name=file_name,
                mime_type=mime_type,
            )

            if not chunks and not structured_images:
                logger.warning(
                    "⚠️ No content extracted from document %d",
                    document_id,
                )
                await self._update_status(
                    document_id,
                    "completed",
                    chunk_count=0,
                )
                return {
                    "document_id": document_id,
                    "chunk_count": 0,
                    "collection_name": None,
                }

            # Build collection name based on scope
            collection_name = self._build_collection_name(
                user_id=user_id,
                scope=scope,
                scope_id=scope_id,
            )

            # Ensure collection exists
            dimension = await self._embedder.get_dimension()
            await self._ensure_collection(collection_name, dimension)

            # Embed and store text chunks
            total_stored = 0
            if chunks:
                logger.info("🧠 Embedding %d text chunks", len(chunks))
                stored = await self._embed_and_store(
                    texts=chunks,
                    document_id=document_id,
                    collection_name=collection_name,
                    chunking_session=chunking_session,
                    content_type="text",
                )
                total_stored += stored

            # Handle structured images (tables/charts)
            if structured_images and self._settings.yolox_enabled:
                logger.info(
                    "🖼️ %d structured images extracted (multimodal embedding not implemented)",
                    len(structured_images),
                )
                # TODO: Implement multimodal embedding when embedder supports it

            # Update document status
            await self._update_status(
                document_id,
                "completed",
                chunk_count=total_stored,
                chunking_session=chunking_session,
            )

            logger.info(
                "✅ Document %d processed: %d chunks in %s",
                document_id,
                total_stored,
                collection_name,
            )

            return {
                "document_id": document_id,
                "chunk_count": total_stored,
                "collection_name": collection_name,
            }

        except Exception as e:
            logger.exception(
                "❌ Processing failed for document %d",
                document_id,
            )
            await self._update_status(
                document_id,
                "error",
                error_message=str(e)[:500],
            )
            raise

    async def _get_document(self, document_id: int) -> Document | None:
        """
        Load document from database.

        Args:
            document_id: Document ID to load.

        Returns:
            Document model or None if not found.

        Raises:
            DatabaseError: If query fails.
        """
        try:
            result = await self._db.execute(
                select(Document).where(Document.id == document_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            raise DatabaseError("select", str(e)) from e

    async def _update_status(
        self,
        document_id: int,
        status: str,
        chunk_count: int | None = None,
        error_message: str | None = None,
        chunking_session: str | None = None,
    ) -> None:
        """
        Update document status in database.

        Args:
            document_id: Document ID to update.
            status: New status (pending, processing, completed, error).
            chunk_count: Optional chunk count for completed status.
            error_message: Optional error message for error status.
            chunking_session: Optional chunking session UUID.

        Raises:
            DatabaseError: If update fails.
        """
        try:
            values: dict[str, Any] = {
                "status": status,
                "last_update": datetime.now(timezone.utc),
            }

            if chunk_count is not None:
                values["chunk_count"] = chunk_count

            if error_message:
                values["status_message"] = error_message

            if chunking_session:
                values["chunking_session"] = chunking_session

            await self._db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(**values)
            )
            await self._db.flush()

        except Exception as e:
            raise DatabaseError("update", str(e)) from e

    async def _download_file(self, file_path: str) -> bytes:
        """
        Download file from MinIO.

        Args:
            file_path: Path to file in MinIO bucket.

        Returns:
            File contents as bytes.

        Raises:
            FileNotFoundInStorageError: If file doesn't exist.
            MinioError: If download fails.
        """
        try:
            data = await self._minio.download_file(
                bucket_name=self._settings.minio_bucket,
                object_name=file_path,
            )
            if data is None:
                raise FileNotFoundInStorageError(file_path, self._settings.minio_bucket)
            return data
        except FileNotFoundInStorageError:
            raise
        except Exception as e:
            if "NoSuchKey" in str(e) or "not found" in str(e).lower():
                raise FileNotFoundInStorageError(
                    file_path,
                    self._settings.minio_bucket,
                )
            raise MinioError("download", str(e)) from e

    def _build_collection_name(
        self,
        user_id: int,
        scope: str,
        scope_id: str | None,
    ) -> str:
        """
        Build Qdrant collection name based on scope.

        Args:
            user_id: User ID.
            scope: Document scope (user, group, org).
            scope_id: Optional scope identifier.

        Returns:
            Collection name string.
        """
        if scope == "user":
            return f"user_{user_id}"
        elif scope == "group" and scope_id:
            return f"group_{scope_id}"
        elif scope == "org" and scope_id:
            return f"org_{scope_id}"
        else:
            return f"user_{user_id}"

    async def _ensure_collection(
        self,
        collection_name: str,
        dimension: int,
    ) -> None:
        """
        Ensure Qdrant collection exists.

        Args:
            collection_name: Collection name.
            dimension: Vector dimension.
        """
        try:
            created = await self._qdrant.create_collection(
                collection_name=collection_name,
                vector_size=dimension,
            )
            if created:
                logger.info(
                    "📦 Created collection: %s (dim=%d)",
                    collection_name,
                    dimension,
                )
        except Exception as e:
            # Collection may already exist
            logger.debug(
                "Collection %s already exists or creation failed: %s",
                collection_name,
                e,
            )

    async def _embed_and_store(
        self,
        texts: list[str],
        document_id: int,
        collection_name: str,
        chunking_session: str,
        content_type: str = "text",
    ) -> int:
        """
        Embed texts and store in Qdrant.

        Args:
            texts: List of text chunks.
            document_id: Document ID for metadata.
            collection_name: Target collection.
            chunking_session: Processing session UUID.
            content_type: Content type (text, image).

        Returns:
            Number of vectors stored.

        Raises:
            EmbeddingError: If embedding fails.
        """
        if not texts:
            return 0

        # Get embeddings in batches
        vectors = await self._embedder.embed_batch(
            texts=texts,
            batch_size=32,
            document_id=document_id,
        )

        if len(vectors) != len(texts):
            logger.warning(
                "⚠️ Vector count mismatch: %d texts, %d vectors",
                len(texts),
                len(vectors),
            )

        # Build point IDs and payloads
        ids: list[str] = []
        payloads: list[dict[str, Any]] = []

        for idx, text in enumerate(texts):
            # Deterministic ID based on document + chunk index
            point_id = self._generate_point_id(document_id, idx, chunking_session)
            ids.append(point_id)

            payloads.append({
                "document_id": document_id,
                "chunk_index": idx,
                "chunking_session": chunking_session,
                "content_type": content_type,
                "text": text[:1000],  # Store truncated text for preview
            })

        # Upsert to Qdrant
        await self._qdrant.upsert(
            collection_name=collection_name,
            vectors=vectors,
            payloads=payloads,
            ids=ids,
        )

        logger.info(
            "💾 Stored %d vectors in %s",
            len(vectors),
            collection_name,
        )

        return len(vectors)

    def _generate_point_id(
        self,
        document_id: int,
        chunk_index: int,
        session: str,
    ) -> str:
        """
        Generate deterministic point ID for upsert.

        Args:
            document_id: Document ID.
            chunk_index: Chunk index.
            session: Chunking session UUID.

        Returns:
            UUID string for point ID.
        """
        # Create deterministic UUID from document + index
        content = f"{document_id}:{chunk_index}:{session}"
        hash_bytes = hashlib.sha256(content.encode()).digest()[:16]
        return str(uuid.UUID(bytes=hash_bytes))

    async def delete_document_vectors(
        self,
        document_id: int,
        collection_name: str,
    ) -> None:
        """
        Delete all vectors for a document.

        Args:
            document_id: Document ID.
            collection_name: Target collection.
        """
        try:
            await self._qdrant.delete_by_filter(
                collection_name=collection_name,
                filter_={
                    "must": [
                        {"key": "document_id", "match": {"value": document_id}}
                    ]
                },
            )
            logger.info(
                "🗑️ Deleted vectors for document %d from %s",
                document_id,
                collection_name,
            )
        except Exception as e:
            logger.warning(
                "⚠️ Failed to delete vectors for document %d: %s",
                document_id,
                e,
            )

    async def close(self) -> None:
        """
        Cleanup service resources.

        Closes gRPC channel to Embedder.
        """
        await self._embedder.close()
