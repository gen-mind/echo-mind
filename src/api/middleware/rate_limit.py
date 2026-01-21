"""
Rate limiting middleware.

Provides request rate limiting using Redis for distributed rate limiting.
"""

import time
from typing import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from echomind_lib.db.redis import get_redis


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using sliding window algorithm.
    
    Uses Redis for distributed rate limiting across multiple instances.
    """
    
    def __init__(
        self,
        app,
        requests_per_minute: int = 100,
        key_prefix: str = "ratelimit:",
    ):
        """
        Initialize rate limiter.
        
        Args:
            app: FastAPI application
            requests_per_minute: Max requests per minute per user
            key_prefix: Redis key prefix
        """
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.key_prefix = key_prefix
        self.window_seconds = 60
    
    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Process request with rate limiting."""
        # Skip rate limiting for health endpoints
        if request.url.path in ("/api/v1/health", "/api/v1/ready"):
            return await call_next(request)
        
        # Get client identifier (user ID from token or IP)
        client_id = self._get_client_id(request)
        
        try:
            redis = get_redis()
            
            # Check rate limit
            allowed, remaining, reset_at = await self._check_rate_limit(
                redis, client_id
            )
            
            if not allowed:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": "Too many requests. Please try again later.",
                            "details": None,
                        }
                    },
                    headers={
                        "X-RateLimit-Limit": str(self.requests_per_minute),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_at),
                        "Retry-After": str(reset_at - int(time.time())),
                    },
                )
            
            # Process request
            response = await call_next(request)
            
            # Add rate limit headers
            response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset_at)
            
            return response
            
        except RuntimeError:
            # Redis not initialized, skip rate limiting
            return await call_next(request)
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        # Try to get user ID from request state (set by auth middleware)
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return f"user:{user_id}"
        
        # Fall back to IP address
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        
        return f"ip:{ip}"
    
    async def _check_rate_limit(
        self,
        redis,
        client_id: str,
    ) -> tuple[bool, int, int]:
        """
        Check if request is within rate limit.
        
        Returns:
            Tuple of (allowed, remaining, reset_timestamp)
        """
        now = int(time.time())
        window_start = now - self.window_seconds
        key = f"{self.key_prefix}{client_id}"
        
        # Remove old entries and count current window
        await redis.client.zremrangebyscore(key, 0, window_start)
        current_count = await redis.client.zcard(key)
        
        reset_at = now + self.window_seconds
        
        if current_count >= self.requests_per_minute:
            return False, 0, reset_at
        
        # Add current request
        await redis.client.zadd(key, {str(now): now})
        await redis.client.expire(key, self.window_seconds)
        
        remaining = self.requests_per_minute - current_count - 1
        
        return True, remaining, reset_at


class WebSocketRateLimiter:
    """
    Rate limiter for WebSocket messages.
    
    Usage:
        limiter = WebSocketRateLimiter(messages_per_minute=30)
        
        if not await limiter.check(user_id):
            # Rate limited
    """
    
    def __init__(
        self,
        messages_per_minute: int = 30,
        key_prefix: str = "ws_ratelimit:",
    ):
        """
        Initialize WebSocket rate limiter.
        
        Args:
            messages_per_minute: Max messages per minute per user
            key_prefix: Redis key prefix
        """
        self.messages_per_minute = messages_per_minute
        self.key_prefix = key_prefix
        self.window_seconds = 60
    
    async def check(self, user_id: int) -> bool:
        """
        Check if user can send a message.
        
        Returns:
            True if allowed, False if rate limited
        """
        try:
            redis = get_redis()
            
            now = int(time.time())
            window_start = now - self.window_seconds
            key = f"{self.key_prefix}{user_id}"
            
            # Remove old entries and count current window
            await redis.client.zremrangebyscore(key, 0, window_start)
            current_count = await redis.client.zcard(key)
            
            if current_count >= self.messages_per_minute:
                return False
            
            # Add current message
            await redis.client.zadd(key, {str(now): now})
            await redis.client.expire(key, self.window_seconds)
            
            return True
            
        except RuntimeError:
            # Redis not initialized, allow request
            return True
    
    async def get_remaining(self, user_id: int) -> int:
        """Get remaining messages for user."""
        try:
            redis = get_redis()
            
            now = int(time.time())
            window_start = now - self.window_seconds
            key = f"{self.key_prefix}{user_id}"
            
            await redis.client.zremrangebyscore(key, 0, window_start)
            current_count = await redis.client.zcard(key)
            
            return max(0, self.messages_per_minute - current_count)
            
        except RuntimeError:
            return self.messages_per_minute
