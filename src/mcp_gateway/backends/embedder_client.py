"""
Embedder gRPC client for the MCP Gateway service.

Handles text embedding via async gRPC calls to the Embedder service.
Used by SearchBackend for query vectorization during retrieval.
"""

import logging

import grpc

from echomind_lib.models.internal.embedding_pb2 import EmbedRequest
from echomind_lib.models.internal.embedding_pb2_grpc import EmbedServiceStub

logger = logging.getLogger("echomind-mcp-gateway")


class EmbedderClient:
    """
    Async gRPC client for Embedder service.

    Provides query embedding for semantic search within the MCP Gateway.

    Attributes:
        _host: Embedder service hostname.
        _port: Embedder gRPC port.
        _timeout: gRPC call timeout in seconds.
        _model_name: Embedder model name (for logging/documentation).
    """

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 30.0,
        model_name: str = "",
    ) -> None:
        """
        Initialize Embedder client.

        Args:
            host: Embedder service hostname.
            port: Embedder gRPC port.
            timeout: gRPC call timeout in seconds.
            model_name: Embedder model name (for logging; model selection
                is server-side via EMBEDDER_MODEL_NAME env var).
        """
        self._host = host
        self._port = port
        self._timeout = timeout
        self._model_name = model_name
        self._channel: grpc.aio.Channel | None = None
        self._stub: EmbedServiceStub | None = None

    async def _ensure_connected(self) -> None:
        """
        Ensure gRPC channel is connected.

        Creates channel and stub if not already connected.
        """
        if self._channel is None:
            target = f"{self._host}:{self._port}"
            self._channel = grpc.aio.insecure_channel(
                target,
                options=[
                    ("grpc.max_send_message_length", 10 * 1024 * 1024),
                    ("grpc.max_receive_message_length", 10 * 1024 * 1024),
                    ("grpc.keepalive_time_ms", 30000),
                    ("grpc.keepalive_timeout_ms", 10000),
                ],
            )
            self._stub = EmbedServiceStub(self._channel)
            logger.info(
                "🔗 Connected to Embedder at %s:%d (model: %s)",
                self._host,
                self._port,
                self._model_name or "server-default",
            )

    async def embed_query(self, query: str) -> list[float]:
        """
        Embed a search query text into a vector.

        Args:
            query: The search query text to embed.

        Returns:
            Embedding vector as a list of floats.

        Raises:
            ConnectionError: If the Embedder service is unavailable or
                returns an empty response.
        """
        await self._ensure_connected()

        try:
            request = EmbedRequest(texts=[query])
            response = await self._stub.Embed(
                request,
                timeout=self._timeout,
            )

            if not response.embeddings:
                logger.error("❌ Embedder returned empty response")
                raise ConnectionError("Embedder returned empty response")

            vector = list(response.embeddings[0].vector)
            logger.debug(f"🎯 Embedded query ({len(vector)} dims)")
            return vector

        except grpc.aio.AioRpcError as e:
            logger.error(f"❌ Embedder gRPC error: {e.details()}")
            # Force channel recreation on next call
            self._channel = None
            self._stub = None
            raise ConnectionError(f"Embedder unavailable: {e.details()}") from e

    async def close(self) -> None:
        """Close the gRPC channel and release resources."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
            logger.info("🔗 Embedder client closed")

    async def health_check(self) -> bool:
        """
        Check if the Embedder service is healthy by performing a real embed call.

        Returns:
            True if an embed call succeeds, False otherwise.
        """
        try:
            await self._ensure_connected()
            request = EmbedRequest(texts=["health"])
            response = await self._stub.Embed(request, timeout=5.0)
            return bool(response.embeddings)
        except Exception:
            self._channel = None
            self._stub = None
            return False
