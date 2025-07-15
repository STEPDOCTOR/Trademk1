"""Redis caching service for performance optimization."""
import json
import pickle
from datetime import timedelta
from typing import Any, Optional, Union, List, Dict
from functools import wraps
import hashlib

import redis.asyncio as redis
from fastapi import Request
from pydantic import BaseModel

from app.config.settings import get_settings


class CacheService:
    """Redis caching service with async support."""
    
    def __init__(self):
        settings = get_settings()
        self.redis_url = settings.REDIS_URL
        self._client: Optional[redis.Redis] = None
        
    async def connect(self):
        """Connect to Redis."""
        if not self._client:
            self._client = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=False  # We'll handle encoding/decoding
            )
            
    async def disconnect(self):
        """Disconnect from Redis."""
        if self._client:
            await self._client.close()
            self._client = None
            
    @property
    def client(self) -> redis.Redis:
        """Get Redis client."""
        if not self._client:
            raise RuntimeError("Cache service not connected")
        return self._client
        
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        value = await self.client.get(key)
        if value:
            try:
                # Try JSON first
                return json.loads(value)
            except:
                try:
                    # Fall back to pickle
                    return pickle.loads(value)
                except:
                    # Return as string
                    return value.decode('utf-8') if isinstance(value, bytes) else value
        return None
        
    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[Union[int, timedelta]] = None
    ):
        """Set value in cache with optional expiration."""
        # Serialize value
        if isinstance(value, (dict, list)) or hasattr(value, 'dict'):
            if hasattr(value, 'dict'):
                serialized = json.dumps(value.dict())
            else:
                serialized = json.dumps(value)
        elif isinstance(value, str):
            serialized = value
        else:
            serialized = pickle.dumps(value)
            
        # Set with expiration
        if expire:
            if isinstance(expire, timedelta):
                expire = int(expire.total_seconds())
            await self.client.setex(key, expire, serialized)
        else:
            await self.client.set(key, serialized)
            
    async def delete(self, key: str):
        """Delete key from cache."""
        await self.client.delete(key)
        
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        return bool(await self.client.exists(key))
        
    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple values from cache."""
        if not keys:
            return {}
            
        values = await self.client.mget(keys)
        result = {}
        
        for key, value in zip(keys, values):
            if value:
                try:
                    result[key] = json.loads(value)
                except:
                    try:
                        result[key] = pickle.loads(value)
                    except:
                        result[key] = value.decode('utf-8') if isinstance(value, bytes) else value
                        
        return result
        
    async def set_many(
        self,
        mapping: Dict[str, Any],
        expire: Optional[Union[int, timedelta]] = None
    ):
        """Set multiple values in cache."""
        if not mapping:
            return
            
        # Serialize values
        serialized = {}
        for key, value in mapping.items():
            if isinstance(value, (dict, list)) or hasattr(value, 'dict'):
                if hasattr(value, 'dict'):
                    serialized[key] = json.dumps(value.dict())
                else:
                    serialized[key] = json.dumps(value)
            elif isinstance(value, str):
                serialized[key] = value
            else:
                serialized[key] = pickle.dumps(value)
                
        # Set all at once
        await self.client.mset(serialized)
        
        # Set expiration if needed
        if expire:
            if isinstance(expire, timedelta):
                expire = int(expire.total_seconds())
            for key in mapping.keys():
                await self.client.expire(key, expire)
                
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment a counter."""
        return await self.client.incr(key, amount)
        
    async def decrement(self, key: str, amount: int = 1) -> int:
        """Decrement a counter."""
        return await self.client.decr(key, amount)
        
    async def expire(self, key: str, seconds: int):
        """Set expiration on a key."""
        await self.client.expire(key, seconds)
        
    async def ttl(self, key: str) -> int:
        """Get time to live for a key."""
        return await self.client.ttl(key)
        
    async def flush_pattern(self, pattern: str):
        """Delete all keys matching a pattern."""
        cursor = 0
        while True:
            cursor, keys = await self.client.scan(cursor, match=pattern, count=100)
            if keys:
                await self.client.delete(*keys)
            if cursor == 0:
                break
                
    async def flush_all(self):
        """Flush entire cache (use with caution)."""
        await self.client.flushdb()
        
    # Cache key generators
    @staticmethod
    def make_key(*args, prefix: str = "cache") -> str:
        """Generate cache key from arguments."""
        key_parts = [prefix]
        for arg in args:
            if isinstance(arg, (dict, list)):
                key_parts.append(hashlib.md5(json.dumps(arg, sort_keys=True).encode()).hexdigest()[:8])
            else:
                key_parts.append(str(arg))
        return ":".join(key_parts)
        
    @staticmethod
    def make_user_key(user_id: str, *args) -> str:
        """Generate user-specific cache key."""
        return CacheService.make_key(user_id, *args, prefix="user")
        
    @staticmethod
    def make_market_key(symbol: str, *args) -> str:
        """Generate market data cache key."""
        return CacheService.make_key(symbol, *args, prefix="market")
        
    @staticmethod
    def make_strategy_key(strategy_id: str, *args) -> str:
        """Generate strategy cache key."""
        return CacheService.make_key(strategy_id, *args, prefix="strategy")


# Global cache instance
cache_service = CacheService()


def cache_result(
    expire: Union[int, timedelta] = 300,  # 5 minutes default
    key_prefix: str = "api",
    key_func: Optional[callable] = None
):
    """Decorator to cache function results."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Build key from function name and arguments
                key_parts = [key_prefix, func.__name__]
                
                # Add positional arguments
                for arg in args:
                    if isinstance(arg, Request):
                        continue  # Skip request objects
                    elif isinstance(arg, BaseModel):
                        key_parts.append(hashlib.md5(arg.json().encode()).hexdigest()[:8])
                    elif isinstance(arg, (dict, list)):
                        key_parts.append(hashlib.md5(json.dumps(arg, sort_keys=True).encode()).hexdigest()[:8])
                    else:
                        key_parts.append(str(arg))
                        
                # Add keyword arguments
                if kwargs:
                    sorted_kwargs = sorted(kwargs.items())
                    kwargs_str = json.dumps(dict(sorted_kwargs), sort_keys=True)
                    key_parts.append(hashlib.md5(kwargs_str.encode()).hexdigest()[:8])
                    
                cache_key = ":".join(key_parts)
                
            # Try to get from cache
            cached_value = await cache_service.get(cache_key)
            if cached_value is not None:
                return cached_value
                
            # Call function and cache result
            result = await func(*args, **kwargs)
            await cache_service.set(cache_key, result, expire)
            
            return result
            
        return wrapper
    return decorator


def invalidate_cache(pattern: str):
    """Decorator to invalidate cache entries matching a pattern after function execution."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            await cache_service.flush_pattern(pattern)
            return result
        return wrapper
    return decorator