"""
Connector backend for MCP Gateway.

Wraps echomind_lib ConnectorCRUD to provide connector data and actions
to MCP tools. Uses a shared ClientHolder so reconnected clients are
picked up automatically without stale references.
"""

import logging
import uuid
from datetime import timezone
from typing import Any

from google.protobuf import struct_pb2
from qdrant_client.models import FieldCondition, Filter, MatchValue

from echomind_lib.db.crud.connector import connector_crud
from echomind_lib.db.models import Connector
from echomind_lib.models.internal.orchestrator_pb2 import ConnectorSyncRequest
from echomind_lib.models.public import connector_pb2

from mcp_gateway.backends.client_holder import ClientHolder

logger = logging.getLogger("echomind-mcp-gateway")

# Keys that must be stripped from connector config before returning
_SENSITIVE_KEY_PATTERNS = frozenset({"token", "secret", "password"})


def _sanitize_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """
    Remove sensitive fields from connector config.

    Strips exact keys (access_token, refresh_token, client_secret) and
    any key whose lowercase form contains 'token', 'secret', or 'password'.

    Args:
        config: Raw connector config dict, or None.

    Returns:
        Sanitized config dict with sensitive values replaced by '***'.
    """
    if not config:
        return {}

    sanitized: dict[str, Any] = {}
    for key, value in config.items():
        key_lower = key.lower()
        if any(pattern in key_lower for pattern in _SENSITIVE_KEY_PATTERNS):
            sanitized[key] = "***"
        else:
            sanitized[key] = value
    return sanitized


def _connector_to_summary(connector: Connector) -> dict[str, Any]:
    """
    Convert a Connector ORM instance to a summary dict.

    Args:
        connector: Connector ORM model.

    Returns:
        Dict with id, name, type, status, last_sync_at, docs_analyzed.
    """
    last_sync = connector.last_sync_at
    if last_sync and last_sync.tzinfo is None:
        last_sync = last_sync.replace(tzinfo=timezone.utc)

    return {
        "id": connector.id,
        "name": connector.name,
        "type": connector.type,
        "status": connector.status,
        "last_sync_at": last_sync.isoformat() if last_sync else None,
        "docs_analyzed": connector.docs_analyzed,
    }


class ConnectorBackend:
    """
    Backend for connector operations in the MCP Gateway.

    Provides read access to connectors, document search scoped to a
    connector, and manual sync triggering via NATS.

    Uses a shared ClientHolder so reconnected clients are picked up
    automatically without stale references.

    Attributes:
        _clients: Shared mutable client holder.
    """

    def __init__(self, clients: ClientHolder) -> None:
        """
        Initialize ConnectorBackend.

        Args:
            clients: Shared client holder providing session_factory,
                nats, qdrant, and embedder references.
        """
        self._clients = clients

    async def list_connectors(self, user_id: int) -> list[dict[str, Any]]:
        """
        List active connectors for a user.

        Args:
            user_id: Owner user ID.

        Returns:
            List of connector summary dicts with id, name, type,
            status, last_sync_at, and docs_analyzed.

        Raises:
            RuntimeError: If database session factory is not available.
        """
        if self._clients.session_factory is None:
            raise RuntimeError("Database not connected")

        async with self._clients.session_factory() as session:
            connectors = await connector_crud.get_by_user(session, user_id)
            result = [_connector_to_summary(c) for c in connectors]

        logger.info(f"📋 Listed {len(result)} connectors for user {user_id}")
        return result

    async def get_connector_status(self, connector_id: int) -> dict[str, Any] | None:
        """
        Get detailed connector status including sanitized config.

        Args:
            connector_id: Connector ID to look up.

        Returns:
            Dict with id, name, type, status, status_message, state,
            config (sanitized), last_sync_at, docs_analyzed, scope,
            scope_id, and refresh_freq_minutes. None if not found.

        Raises:
            RuntimeError: If database session factory is not available.
        """
        if self._clients.session_factory is None:
            raise RuntimeError("Database not connected")

        async with self._clients.session_factory() as session:
            connector = await connector_crud.get_by_id_active(session, connector_id)
            if connector is None:
                logger.warning(f"⚠️ Connector {connector_id} not found")
                return None

            last_sync = connector.last_sync_at
            if last_sync and last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)

            result: dict[str, Any] = {
                "id": connector.id,
                "name": connector.name,
                "type": connector.type,
                "status": connector.status,
                "status_message": connector.status_message,
                "state": connector.state or {},
                "config": _sanitize_config(connector.config),
                "last_sync_at": last_sync.isoformat() if last_sync else None,
                "docs_analyzed": connector.docs_analyzed,
                "scope": connector.scope,
                "scope_id": connector.scope_id,
                "refresh_freq_minutes": connector.refresh_freq_minutes,
            }

        logger.info(f"ℹ️ Retrieved status for connector {connector_id}")
        return result

    async def search_connector_documents(
        self,
        connector_id: int,
        query: str,
        collection_name: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Search documents from a specific connector using vector similarity.

        Embeds the query, then searches Qdrant with a connector_id filter
        to return only documents belonging to the specified connector.

        Args:
            connector_id: Connector ID to filter documents by.
            query: Natural language search query.
            collection_name: Qdrant collection to search.
            limit: Maximum number of results to return.

        Returns:
            List of matching document chunks, each containing:
                - id: Point ID in Qdrant.
                - score: Similarity score.
                - payload: Document metadata and content.

        Raises:
            RuntimeError: If Qdrant or Embedder are not configured.
        """
        if self._clients.qdrant is None or self._clients.embedder is None:
            raise RuntimeError(
                "Qdrant and Embedder must be configured for document search"
            )

        vector = await self._clients.embedder.embed_query(query)
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="connector_id",
                    match=MatchValue(value=connector_id),
                )
            ]
        )
        results = await self._clients.qdrant.search(
            collection_name=collection_name,
            query_vector=vector,
            limit=limit,
            filter_=query_filter,
        )
        logger.info(f"🔍 Connector {connector_id} search returned {len(results)} results for query '{query[:50]}'")
        return results

    async def trigger_sync(
        self,
        connector_id: int,
        user_id: int,
    ) -> dict[str, Any]:
        """
        Trigger a manual sync by publishing a ConnectorSyncRequest to NATS.

        Looks up the connector, validates ownership, builds the protobuf
        sync message, and publishes it to the appropriate NATS subject.

        Args:
            connector_id: Connector ID to sync.
            user_id: User ID requesting the sync (must be connector owner).

        Returns:
            Dict with connector_id, status ('sync_requested'), subject,
            and chunking_session UUID.

        Raises:
            RuntimeError: If NATS publisher or database is not configured.
            ValueError: If connector not found or user doesn't own it.
        """
        if self._clients.nats is None:
            raise RuntimeError("NATS publisher must be configured for sync operations")
        if self._clients.session_factory is None:
            raise RuntimeError("Database not connected")

        async with self._clients.session_factory() as session:
            connector = await connector_crud.get_by_id_active(session, connector_id)
            if connector is None:
                raise ValueError(f"Connector {connector_id} not found")
            if connector.user_id != user_id:
                raise ValueError(
                    f"User {user_id} does not own connector {connector_id}"
                )

            # Build protobuf sync request (matching api/logic/connector_service.py)
            chunking_session = str(uuid.uuid4())

            request = ConnectorSyncRequest()
            request.connector_id = connector.id
            request.user_id = connector.user_id
            request.chunking_session = chunking_session

            # Set connector type enum
            type_name = (
                f"CONNECTOR_TYPE_{connector.type.upper()}"
                if connector.type
                else "CONNECTOR_TYPE_UNSPECIFIED"
            )
            type_value = getattr(
                connector_pb2.ConnectorType,
                type_name,
                connector_pb2.ConnectorType.CONNECTOR_TYPE_UNSPECIFIED,
            )
            request.type = type_value

            # Set scope enum
            scope_name = (
                f"CONNECTOR_SCOPE_{connector.scope.upper()}"
                if connector.scope
                else "CONNECTOR_SCOPE_USER"
            )
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

            # Publish to NATS
            subject = f"connector.sync.{connector.type}"
            await self._clients.nats.publish(subject, request.SerializeToString())

        logger.info(f"📤 Triggered sync for connector {connector_id} to {subject} (session: {chunking_session})")
        return {
            "connector_id": connector_id,
            "status": "sync_requested",
            "subject": subject,
            "chunking_session": chunking_session,
        }
