"""
Redis client for caching and session memory.

Provides async operations for key-value storage and pub/sub.
"""

from typing import Any

import redis.asyncio as redis


class RedisClient:
    """
    Async Redis client for caching and memory operations.
    
    Usage:
        cache = RedisClient(host="localhost", port=6379)
        await cache.init()
        
        await cache.set("key", "value", ttl=3600)
        value = await cache.get("key")
        
        await cache.close()
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        decode_responses: bool = True,
    ):
        """
        Initialize Redis client.
        
        Args:
            host: Redis server host
            port: Redis server port
            db: Database number
            password: Optional password
            decode_responses: Decode bytes to strings
        """
        self._pool = redis.ConnectionPool(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=decode_responses,
            max_connections=20,
        )
        self._client: redis.Redis | None = None
    
    async def init(self) -> None:
        """Initialize connection and verify connectivity."""
        self._client = redis.Redis(connection_pool=self._pool)
        await self._client.ping()
    
    async def close(self) -> None:
        """Close all connections."""
        if self._client:
            await self._client.aclose()
        await self._pool.aclose()
    
    @property
    def client(self) -> redis.Redis:
        """Get the Redis client."""
        if self._client is None:
            raise RuntimeError("Redis client not initialized")
        return self._client
    
    async def get(self, key: str) -> str | None:
        """Get a value by key."""
        return await self.client.get(key)
    
    async def set(
        self,
        key: str,
        value: str,
        ttl: int | None = None,
    ) -> bool:
        """
        Set a key-value pair.
        
        Args:
            key: Key name
            value: Value to store
            ttl: Time-to-live in seconds (None = no expiry)
        
        Returns:
            True if successful
        """
        if ttl:
            return await self.client.setex(key, ttl, value)
        return await self.client.set(key, value)
    
    async def delete(self, *keys: str) -> int:
        """Delete one or more keys. Returns count of deleted keys."""
        return await self.client.delete(*keys)
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        return await self.client.exists(key) > 0
    
    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration on a key."""
        return await self.client.expire(key, ttl)
    
    async def hget(self, name: str, key: str) -> str | None:
        """Get a hash field value."""
        return await self.client.hget(name, key)
    
    async def hset(self, name: str, key: str, value: str) -> int:
        """Set a hash field value."""
        return await self.client.hset(name, key, value)
    
    async def hgetall(self, name: str) -> dict[str, str]:
        """Get all fields in a hash."""
        return await self.client.hgetall(name)
    
    async def hdel(self, name: str, *keys: str) -> int:
        """Delete hash fields."""
        return await self.client.hdel(name, *keys)
    
    async def lpush(self, key: str, *values: str) -> int:
        """Push values to the left of a list."""
        return await self.client.lpush(key, *values)
    
    async def rpush(self, key: str, *values: str) -> int:
        """Push values to the right of a list."""
        return await self.client.rpush(key, *values)
    
    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        """Get a range of elements from a list."""
        return await self.client.lrange(key, start, end)
    
    async def ltrim(self, key: str, start: int, end: int) -> bool:
        """Trim a list to the specified range."""
        return await self.client.ltrim(key, start, end)
    
    async def publish(self, channel: str, message: str) -> int:
        """Publish a message to a channel."""
        return await self.client.publish(channel, message)
    
    async def incr(self, key: str) -> int:
        """Increment a key's value."""
        return await self.client.incr(key)
    
    async def decr(self, key: str) -> int:
        """Decrement a key's value."""
        return await self.client.decr(key)


_redis_client: RedisClient | None = None


def get_redis() -> RedisClient:
    """Get the global Redis client instance."""
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized. Call init_redis() first.")
    return _redis_client


async def init_redis(
    host: str = "localhost",
    port: int = 6379,
    password: str | None = None,
) -> RedisClient:
    """Initialize the global Redis client."""
    global _redis_client
    _redis_client = RedisClient(host=host, port=port, password=password)
    await _redis_client.init()
    return _redis_client


async def close_redis() -> None:
    """Close the global Redis client."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
