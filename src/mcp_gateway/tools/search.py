"""
Search tools for MCP Gateway.

Registers MCP tool definitions for semantic document search, collection
listing, and document chunk retrieval via FastMCP decorators.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from mcp_gateway.backends.search_backend import SearchBackend

logger = logging.getLogger("echomind-mcp-gateway")


def register_search_tools(mcp: FastMCP, backend: SearchBackend) -> None:
    """
    Register search-related MCP tools on the FastMCP server.

    Defines tools for document search, collection management, and
    chunk retrieval. Each tool delegates to the SearchBackend.

    Args:
        mcp: FastMCP server instance to register tools on.
        backend: SearchBackend providing vector search operations.
    """

    @mcp.tool()
    async def search_documents(
        collection: str,
        query: str,
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for documents using semantic similarity.

        Embeds the query and searches the specified Qdrant collection
        for similar document chunks.

        Args:
            collection: Name of the Qdrant collection to search.
            query: Natural language search query.
            limit: Maximum number of results to return (default: 10).
            score_threshold: Minimum similarity score (0-1). None means no threshold.

        Returns:
            List of matching document chunks with scores and metadata.
        """
        logger.info(f"🔍 search_documents: collection='{collection}', query='{query[:50]}...'")
        return await backend.search_documents(
            collection_name=collection,
            query=query,
            limit=limit,
            score_threshold=score_threshold,
        )

    @mcp.tool()
    async def list_collections() -> list[dict[str, Any]]:
        """
        List all available document collections.

        Returns:
            List of collection names and metadata.
        """
        logger.info("📋 list_collections")
        return await backend.list_collections()

    @mcp.tool()
    async def get_collection_info(collection: str) -> dict[str, Any]:
        """
        Get detailed information about a collection.

        Args:
            collection: Name of the collection.

        Returns:
            Collection statistics including vector count and status.
        """
        logger.info(f"ℹ️ get_collection_info: collection='{collection}'")
        return await backend.get_collection_info(collection)

    @mcp.tool()
    async def get_document_chunks(
        collection: str,
        document_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get all chunks for a specific document.

        Args:
            collection: Name of the collection containing the document.
            document_id: ID of the document to retrieve chunks for.
            limit: Maximum number of chunks to return (default: 100).

        Returns:
            List of document chunks with their payloads.
        """
        logger.info(f"📄 get_document_chunks: collection='{collection}', doc='{document_id}'")
        return await backend.get_document_chunks(
            collection_name=collection,
            document_id=document_id,
            limit=limit,
        )
