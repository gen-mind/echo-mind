"""
Qdrant vector database client.

Provides async operations for vector storage and similarity search.
"""

from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    SearchParams,
    VectorParams,
)


class QdrantDB:
    """
    Async Qdrant client for vector operations.
    
    Usage:
        qdrant = QdrantDB(host="localhost", port=6333)
        await qdrant.init()
        
        # Upsert vectors
        await qdrant.upsert("collection", vectors, payloads, ids)
        
        # Search
        results = await qdrant.search("collection", query_vector, limit=10)
        
        await qdrant.close()
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        grpc_port: int = 6334,
        prefer_grpc: bool = True,
        api_key: str | None = None,
    ):
        """
        Initialize Qdrant client.
        
        Args:
            host: Qdrant server host
            port: Qdrant REST API port
            grpc_port: Qdrant gRPC port
            prefer_grpc: Use gRPC for better performance
            api_key: Optional API key for authentication
        """
        self._client = AsyncQdrantClient(
            host=host,
            port=port,
            grpc_port=grpc_port,
            prefer_grpc=prefer_grpc,
            api_key=api_key,
        )
    
    async def init(self) -> None:
        """Initialize connection (verify connectivity)."""
        await self._client.get_collections()
    
    async def close(self) -> None:
        """Close the client connection."""
        await self._client.close()
    
    async def create_collection(
        self,
        collection_name: str,
        vector_size: int,
        distance: Distance = Distance.COSINE,
    ) -> bool:
        """
        Create a new collection if it doesn't exist.
        
        Args:
            collection_name: Name of the collection
            vector_size: Dimension of vectors
            distance: Distance metric (COSINE, EUCLID, DOT)
        
        Returns:
            True if created, False if already exists
        """
        collections = await self._client.get_collections()
        existing = [c.name for c in collections.collections]
        
        if collection_name in existing:
            return False
        
        await self._client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=distance),
        )
        return True
    
    async def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection."""
        return await self._client.delete_collection(collection_name)
    
    async def upsert(
        self,
        collection_name: str,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        ids: list[str | int],
    ) -> None:
        """
        Upsert vectors with payloads.
        
        Args:
            collection_name: Target collection
            vectors: List of embedding vectors
            payloads: List of metadata dicts
            ids: List of point IDs
        """
        points = [
            PointStruct(id=id_, vector=vector, payload=payload)
            for id_, vector, payload in zip(ids, vectors, payloads)
        ]
        await self._client.upsert(collection_name=collection_name, points=points)
    
    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float | None = None,
        filter_: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for similar vectors.
        
        Args:
            collection_name: Collection to search
            query_vector: Query embedding
            limit: Max results
            score_threshold: Minimum similarity score
            filter_: Qdrant filter conditions
        
        Returns:
            List of results with id, score, and payload
        """
        results = await self._client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            query_filter=filter_,
            search_params=SearchParams(hnsw_ef=128, exact=False),
        )
        
        return [
            {
                "id": r.id,
                "score": r.score,
                "payload": r.payload,
            }
            for r in results
        ]
    
    async def delete_by_filter(
        self,
        collection_name: str,
        filter_: dict[str, Any],
    ) -> None:
        """Delete points matching a filter."""
        await self._client.delete(
            collection_name=collection_name,
            points_selector=filter_,
        )
    
    async def get_collection_info(self, collection_name: str) -> dict[str, Any]:
        """Get collection statistics."""
        info = await self._client.get_collection(collection_name)
        return {
            "name": collection_name,
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "status": info.status.value,
        }


_qdrant_client: QdrantDB | None = None


def get_qdrant() -> QdrantDB:
    """Get the global Qdrant client instance."""
    if _qdrant_client is None:
        raise RuntimeError("Qdrant client not initialized. Call init_qdrant() first.")
    return _qdrant_client


async def init_qdrant(
    host: str = "localhost",
    port: int = 6333,
    api_key: str | None = None,
) -> QdrantDB:
    """Initialize the global Qdrant client."""
    global _qdrant_client
    _qdrant_client = QdrantDB(host=host, port=port, api_key=api_key)
    await _qdrant_client.init()
    return _qdrant_client


async def close_qdrant() -> None:
    """Close the global Qdrant client."""
    global _qdrant_client
    if _qdrant_client is not None:
        await _qdrant_client.close()
        _qdrant_client = None
