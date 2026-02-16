"""
NATS backend for MCP Gateway.

Thin wrapper around JetStreamPublisher providing connection lifecycle
management for the MCP gateway service, which manages its own NATS
connection independently from other services.
"""

import logging

from echomind_lib.db.nats_publisher import JetStreamPublisher

logger = logging.getLogger("echomind-mcp-gateway")


class NatsBackend:
    """
    NATS JetStream connection manager for the MCP Gateway.

    Wraps JetStreamPublisher to provide a clean lifecycle API
    (connect, publish, close) for use by MCP Gateway backends.

    Attributes:
        _publisher: Underlying JetStreamPublisher instance.
        _url: NATS server URL.
        _user: Optional NATS username.
        _password: Optional NATS password.
        _connected: Whether the connection is active.
    """

    def __init__(
        self,
        url: str,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        """
        Initialize NatsBackend.

        Args:
            url: NATS server URL (e.g. 'nats://localhost:4222').
            user: Optional NATS username for authentication.
            password: Optional NATS password for authentication.
        """
        self._url = url
        self._user = user
        self._password = password
        self._publisher = JetStreamPublisher(
            servers=[url],
            user=user,
            password=password,
        )
        self._connected = False

    async def connect(self) -> None:
        """
        Connect to NATS and initialize JetStream context.

        Raises:
            Exception: If connection to NATS fails.
        """
        await self._publisher.init()
        self._connected = True
        logger.info("📡 Connected to NATS at %s", self._url)

    async def publish(self, subject: str, payload: bytes) -> None:
        """
        Publish a message to a NATS subject.

        Args:
            subject: Target subject (e.g. 'connector.sync.teams').
            payload: Message payload as bytes.

        Raises:
            RuntimeError: If not connected to NATS.
        """
        if not self._connected:
            raise RuntimeError("NATS backend not connected. Call connect() first.")

        await self._publisher.publish(subject, payload)
        logger.debug("📤 Published %d bytes to '%s'", len(payload), subject)

    async def close(self) -> None:
        """Close the NATS connection and release resources."""
        if self._connected:
            await self._publisher.close()
            self._connected = False
            logger.info("🔌 Disconnected from NATS")

    @property
    def is_connected(self) -> bool:
        """
        Check if the NATS connection is active.

        Returns:
            True if connected, False otherwise.
        """
        return self._connected
