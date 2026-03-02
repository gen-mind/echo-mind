"""
Connector tools for MCP Gateway.

Registers MCP tool definitions for listing connectors, checking status,
searching connector-scoped documents, and triggering manual syncs.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from mcp_gateway.backends.connector_backend import ConnectorBackend

logger = logging.getLogger("echomind-mcp-gateway")


def register_connector_tools(
    mcp: FastMCP,
    connector_backend: ConnectorBackend,
) -> None:
    """
    Register connector-related MCP tools on the FastMCP server.

    Defines tools for listing user connectors, checking connector status,
    searching documents scoped to a connector, and triggering manual syncs.

    Args:
        mcp: FastMCP server instance to register tools on.
        connector_backend: ConnectorBackend providing connector operations.
    """

    @mcp.tool()
    async def connectors_list(user_id: int) -> list[dict[str, Any]]:
        """
        List all active data connectors for a user.

        Returns summary info for each connector including name, type,
        sync status, and document count.

        Args:
            user_id: ID of the user whose connectors to list.

        Returns:
            List of connector summaries with id, name, type, status,
            last_sync_at, and docs_analyzed.
        """
        # SECURITY: user_id is agent-supplied, not authenticated.
        # Phase 8 will extract user identity from JWT token in MCP session context.
        # Until then, this tool trusts the agent to supply the correct user_id.
        logger.info(f"📋 connectors_list: user_id={user_id}")
        return await connector_backend.list_connectors(user_id)

    @mcp.tool()
    async def connector_status(connector_id: int) -> dict[str, Any]:
        """
        Get detailed status of a specific connector.

        Returns full connector information including sanitized config,
        sync state, and scheduling details.

        Args:
            connector_id: ID of the connector to inspect.

        Returns:
            Connector details with id, name, type, status, status_message,
            state, config (sanitized), last_sync_at, docs_analyzed, scope,
            scope_id, and refresh_freq_minutes. Returns error dict if not found.
        """
        # SECURITY: connector_id is agent-supplied, not authenticated.
        # Phase 8 will extract user identity from JWT token in MCP session context.
        # Until then, this tool trusts the agent to supply the correct connector_id.
        logger.info(f"ℹ️ connector_status: connector_id={connector_id}")
        result = await connector_backend.get_connector_status(connector_id)
        if result is None:
            return {"error": f"Connector {connector_id} not found"}
        return result

    @mcp.tool()
    async def connector_search(
        connector_id: int,
        query: str,
        collection: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Search documents from a specific connector.

        Performs a vector similarity search filtered to only return
        documents belonging to the specified connector.

        Args:
            connector_id: ID of the connector to search within.
            query: Natural language search query.
            collection: Qdrant collection name to search.
            limit: Maximum number of results to return (default: 5).

        Returns:
            List of matching document chunks with id, score, and payload.
            On error, returns a list with a single dict containing an 'error' key.
        """
        # SECURITY: connector_id is agent-supplied, not authenticated.
        # Phase 8 will extract user identity from JWT token in MCP session context.
        # Until then, this tool trusts the agent to supply the correct connector_id.
        logger.info(
            f"🔍 connector_search: connector_id={connector_id}, "
            f"query='{query[:50]}', collection='{collection}', limit={limit}"
        )
        try:
            return await connector_backend.search_connector_documents(
                connector_id=connector_id,
                query=query,
                collection_name=collection,
                limit=limit,
            )
        except RuntimeError as e:
            logger.error(f"❌ connector_search failed: {e}")
            return [{"error": str(e)}]

    @mcp.tool()
    async def connector_sync(
        connector_id: int,
        user_id: int,
    ) -> dict[str, Any]:
        """
        Trigger a manual sync for a connector.

        Publishes a sync request to NATS, which the connector service
        will pick up and process. The user must own the connector.

        Args:
            connector_id: ID of the connector to sync.
            user_id: ID of the user requesting the sync (must be connector owner).

        Returns:
            Dict with connector_id, status, NATS subject, and chunking_session.
            On error, returns a dict with an 'error' key.
        """
        # SECURITY: user_id is agent-supplied, not authenticated.
        # Phase 8 will extract user identity from JWT token in MCP session context.
        # Until then, this tool trusts the agent to supply the correct user_id.
        logger.info(f"🔄 connector_sync: connector_id={connector_id}, user_id={user_id}")
        try:
            return await connector_backend.trigger_sync(
                connector_id=connector_id,
                user_id=user_id,
            )
        except (RuntimeError, ValueError) as e:
            logger.error(f"❌ connector_sync failed: {e}")
            return {"error": str(e)}
