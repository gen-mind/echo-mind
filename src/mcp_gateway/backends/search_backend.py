"""
Search backend combining Qdrant vector search with embedder.

Wraps QdrantDB and EmbedderClient to provide high-level search operations
for the MCP Gateway service.
"""

import logging
from typing import Any

from qdrant_client.models import FieldCondition, Filter, MatchValue

from mcp_gateway.backends.client_holder import ClientHolder

logger = logging.getLogger("echomind-mcp-gateway")


class SearchBackend:
    """
    Backend for vector search operations.

    Combines the Embedder service (for query vectorization) with Qdrant
    (for similarity search) to provide semantic document search.

    Uses a shared ClientHolder so reconnected clients are picked up
    automatically without stale references.

    Attributes:
        _clients: Shared mutable client holder.
    """

    def __init__(self, clients: ClientHolder) -> None:
        """
        Initialize SearchBackend.

        Args:
            clients: Shared client holder providing qdrant and embedder.
        """
        self._clients = clients

    async def search_documents(
        self,
        collection_name: str,
        query: str,
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search documents by embedding the query and searching Qdrant.

        Embeds the natural language query into a vector, then performs
        similarity search against the specified Qdrant collection.

        Args:
            collection_name: Name of the Qdrant collection to search.
            query: Natural language search query to embed and search.
            limit: Maximum number of results to return.
            score_threshold: Minimum similarity score filter (0-1).
                None means no threshold is applied.

        Returns:
            List of matching document chunks, each containing:
                - id: Point ID in Qdrant.
                - score: Similarity score.
                - payload: Document metadata and content.

        Raises:
            RuntimeError: If Qdrant or Embedder are not connected.
            ConnectionError: If the Embedder service is unavailable.
        """
        if self._clients.qdrant is None or self._clients.embedder is None:
            raise RuntimeError(
                "Qdrant and Embedder must be connected for search operations"
            )

        vector = await self._clients.embedder.embed_query(query)
        results = await self._clients.qdrant.search(
            collection_name=collection_name,
            query_vector=vector,
            limit=limit,
            score_threshold=score_threshold,
        )
        logger.info(f"🔍 Search returned {len(results)} results from '{collection_name}'")
        return results

    async def list_collections(self) -> list[dict[str, Any]]:
        """
        List all available Qdrant collections.

        Returns:
            List of dicts, each containing:
                - name: Collection name string.

        Raises:
            RuntimeError: If Qdrant is not connected.
        """
        if self._clients.qdrant is None:
            raise RuntimeError("Qdrant must be connected to list collections")

        collections = await self._clients.qdrant._client.get_collections()
        result: list[dict[str, Any]] = []
        for c in collections.collections:
            result.append({"name": c.name})
        logger.info(f"📋 Listed {len(result)} collections")
        return result

    async def get_collection_info(self, collection_name: str) -> dict[str, Any]:
        """
        Get detailed information about a specific collection.

        Args:
            collection_name: Name of the Qdrant collection.

        Returns:
            Dict containing collection statistics:
                - name: Collection name.
                - vectors_count: Total number of vectors.
                - points_count: Total number of points.
                - status: Collection status string.

        Raises:
            RuntimeError: If Qdrant is not connected.
        """
        if self._clients.qdrant is None:
            raise RuntimeError("Qdrant must be connected to get collection info")

        info = await self._clients.qdrant.get_collection_info(collection_name)
        logger.info(f"ℹ️ Retrieved info for collection '{collection_name}'")
        return info

    async def get_document_chunks(
        self,
        collection_name: str,
        document_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get all chunks for a specific document from Qdrant.

        Retrieves document chunks by filtering on the document_id field
        in the Qdrant collection payload.

        Args:
            collection_name: Name of the collection containing the document.
            document_id: ID of the document to retrieve chunks for.
            limit: Maximum number of chunks to return.

        Returns:
            List of document chunks, each containing:
                - id: Point ID as string.
                - payload: Chunk metadata and content.

        Raises:
            RuntimeError: If Qdrant is not connected.
        """
        if self._clients.qdrant is None:
            raise RuntimeError("Qdrant must be connected to get document chunks")

        results = await self._clients.qdrant._client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        points, _ = results
        chunks: list[dict[str, Any]] = [
            {"id": str(p.id), "payload": p.payload}
            for p in points
        ]
        logger.info(f"📄 Retrieved {len(chunks)} chunks for document '{document_id}'")
        return chunks
