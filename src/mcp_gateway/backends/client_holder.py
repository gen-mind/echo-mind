"""
Shared mutable client holder for MCP Gateway backends.

Provides a single reference object that backends hold, allowing the gateway
to swap out reconnected clients without backends holding stale references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from echomind_lib.db.qdrant import QdrantDB

    from mcp_gateway.backends.embedder_client import EmbedderClient
    from mcp_gateway.backends.nats_backend import NatsBackend


@dataclass
class ClientHolder:
    """
    Mutable container for shared backend clients.

    The gateway updates these fields when clients reconnect.
    Backends read from this holder on every call, ensuring they
    always use the latest connected client instance.

    Attributes:
        qdrant: Qdrant vector database client, or None if not connected.
        embedder: Embedder gRPC client, or None if not connected.
        session_factory: Async SQLAlchemy session factory, or None if DB is down.
        nats: NATS backend for publishing, or None if not connected.
    """

    qdrant: QdrantDB | None = field(default=None)
    embedder: EmbedderClient | None = field(default=None)
    session_factory: async_sessionmaker[AsyncSession] | None = field(default=None)
    nats: NatsBackend | None = field(default=None)
