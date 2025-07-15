"""Rate limiting middleware using Redis."""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass

from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.cache import cache_service

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_minute: int = 60
    requests_per_hour: int = 3600
    requests_per_day: int = 86400
    burst_limit: int = 10  # Number of requests allowed in burst
    burst_window: int = 1  # Burst window in seconds


@dataclass
class RateLimitResult:
    """Rate limit check result."""
    allowed: bool
    retry_after: Optional[int] = None
    remaining: Optional[int] = None
    reset_time: Optional[datetime] = None
    message: Optional[str] = None


class RateLimiter:
    """Redis-based rate limiter with sliding window algorithm."""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client or cache_service
        
    async def check_rate_limit(
        self,
        key: str,
        config: RateLimitConfig,
        user_id: Optional[str] = None
    ) -> RateLimitResult:
        """Check if request is within rate limits."""
        try:
            await self.redis_client.connect()
            
            current_time = int(time.time())
            
            # Check different time windows
            windows = [
                ("minute", 60, config.requests_per_minute),
                ("hour", 3600, config.requests_per_hour),
                ("day", 86400, config.requests_per_day),
            ]
            
            for window_name, window_seconds, limit in windows:
                result = await self._check_sliding_window(
                    f"{key}:{window_name}",
                    window_seconds,
                    limit,
                    current_time
                )
                
                if not result.allowed:
                    return result
                    
            # Check burst limit
            burst_result = await self._check_burst_limit(
                f"{key}:burst",
                config.burst_limit,
                config.burst_window,
                current_time
            )
            
            if not burst_result.allowed:
                return burst_result
                
            return RateLimitResult(allowed=True)
            
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # Fail open - allow request if Redis is down
            return RateLimitResult(allowed=True)
            
    async def _check_sliding_window(
        self,
        key: str,
        window_seconds: int,
        limit: int,
        current_time: int
    ) -> RateLimitResult:
        """Check rate limit using sliding window algorithm."""
        window_start = current_time - window_seconds
        
        # Remove old entries
        await self.redis_client.client.zremrangebyscore(key, 0, window_start)
        
        # Count current requests in window
        current_count = await self.redis_client.client.zcard(key)
        
        if current_count >= limit:
            # Get the oldest entry to calculate retry_after
            oldest_entries = await self.redis_client.client.zrange(key, 0, 0, withscores=True)
            if oldest_entries:
                oldest_time = oldest_entries[0][1]
                retry_after = int(oldest_time + window_seconds - current_time)
                return RateLimitResult(
                    allowed=False,
                    retry_after=max(retry_after, 1),
                    remaining=0,
                    message=f"Rate limit exceeded: {limit} requests per {window_seconds} seconds"
                )
            
        # Add current request
        await self.redis_client.client.zadd(key, {str(current_time): current_time})
        
        # Set expiration
        await self.redis_client.client.expire(key, window_seconds)
        
        remaining = limit - current_count - 1
        return RateLimitResult(
            allowed=True,
            remaining=max(remaining, 0)
        )
        
    async def _check_burst_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        current_time: int
    ) -> RateLimitResult:
        """Check burst rate limit."""
        window_start = current_time - window_seconds
        
        # Remove old entries
        await self.redis_client.client.zremrangebyscore(key, 0, window_start)
        
        # Count current requests in burst window
        current_count = await self.redis_client.client.zcard(key)
        
        if current_count >= limit:
            return RateLimitResult(
                allowed=False,
                retry_after=window_seconds,
                remaining=0,
                message=f"Burst limit exceeded: {limit} requests per {window_seconds} seconds"
            )
            
        # Add current request
        await self.redis_client.client.zadd(key, {str(current_time): current_time})
        
        # Set expiration
        await self.redis_client.client.expire(key, window_seconds)
        
        return RateLimitResult(allowed=True)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for API rate limiting."""
    
    def __init__(
        self,
        app,
        default_config: Optional[RateLimitConfig] = None,
        exempt_paths: Optional[list] = None
    ):
        super().__init__(app)
        self.rate_limiter = RateLimiter()
        self.default_config = default_config or RateLimitConfig()
        self.exempt_paths = exempt_paths or ["/docs", "/redoc", "/openapi.json", "/api/health"]
        
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        # Skip rate limiting for exempt paths
        if any(request.url.path.startswith(path) for path in self.exempt_paths):
            return await call_next(request)
            
        # Get rate limit configuration
        config = await self._get_rate_limit_config(request)
        
        # Generate rate limit key
        rate_limit_key = await self._generate_rate_limit_key(request)
        
        # Check rate limit
        result = await self.rate_limiter.check_rate_limit(
            rate_limit_key,
            config,
            user_id=getattr(request.state, "user_id", None)
        )
        
        if not result.allowed:
            # Log rate limit violation
            logger.warning(
                f"Rate limit exceeded for {rate_limit_key}: {result.message}"
            )
            
            # Return rate limit error
            headers = {}
            if result.retry_after:
                headers["Retry-After"] = str(result.retry_after)
                
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": result.message,
                    "retry_after": result.retry_after
                },
                headers=headers
            )
            
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        if result.remaining is not None:
            response.headers["X-RateLimit-Remaining"] = str(result.remaining)
            
        return response
        
    async def _get_rate_limit_config(self, request: Request) -> RateLimitConfig:
        """Get rate limit configuration for request."""
        # Check if user has custom rate limits (API key, user tier, etc.)
        user_id = getattr(request.state, "user_id", None)
        api_key_id = getattr(request.state, "api_key_id", None)
        
        if api_key_id:
            # Get API key specific limits from database/cache
            return await self._get_api_key_rate_limits(api_key_id)
        elif user_id:
            # Get user specific limits
            return await self._get_user_rate_limits(user_id)
        else:
            # Anonymous user limits (more restrictive)
            return RateLimitConfig(
                requests_per_minute=30,
                requests_per_hour=1800,
                requests_per_day=43200,
                burst_limit=5
            )
            
    async def _get_api_key_rate_limits(self, api_key_id: str) -> RateLimitConfig:
        """Get rate limits for API key."""
        # This would typically query the database
        # For now, return default config
        return self.default_config
        
    async def _get_user_rate_limits(self, user_id: str) -> RateLimitConfig:
        """Get rate limits for user."""
        # This would typically check user tier/subscription
        # For now, return default config
        return self.default_config
        
    async def _generate_rate_limit_key(self, request: Request) -> str:
        """Generate rate limit key for request."""
        # Priority order: API key > User ID > IP address
        api_key_id = getattr(request.state, "api_key_id", None)
        if api_key_id:
            return f"rate_limit:api_key:{api_key_id}"
            
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return f"rate_limit:user:{user_id}"
            
        # Fall back to IP address
        client_ip = self._get_client_ip(request)
        return f"rate_limit:ip:{client_ip}"
        
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address."""
        # Check for forwarded headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
            
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
            
        # Fall back to client host
        return request.client.host if request.client else "unknown"


# Decorator for endpoint-specific rate limiting
def rate_limit(
    requests_per_minute: int = 60,
    requests_per_hour: int = 3600,
    requests_per_day: int = 86400,
    burst_limit: int = 10
):
    """Decorator to apply specific rate limits to endpoints."""
    def decorator(func):
        func._rate_limit_config = RateLimitConfig(
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour,
            requests_per_day=requests_per_day,
            burst_limit=burst_limit
        )
        return func
    return decorator


# Rate limit categories for different API tiers
class RateLimitTiers:
    """Predefined rate limit tiers."""
    
    FREE = RateLimitConfig(
        requests_per_minute=30,
        requests_per_hour=1800,
        requests_per_day=43200,
        burst_limit=5
    )
    
    BASIC = RateLimitConfig(
        requests_per_minute=60,
        requests_per_hour=3600,
        requests_per_day=86400,
        burst_limit=10
    )
    
    PREMIUM = RateLimitConfig(
        requests_per_minute=120,
        requests_per_hour=7200,
        requests_per_day=172800,
        burst_limit=20
    )
    
    ENTERPRISE = RateLimitConfig(
        requests_per_minute=300,
        requests_per_hour=18000,
        requests_per_day=432000,
        burst_limit=50
    )