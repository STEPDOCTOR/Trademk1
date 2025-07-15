"""Response compression and optimization middleware."""

import gzip
import json
import time
from typing import Optional, Dict, Any, List
from io import BytesIO

from fastapi import Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.monitoring.metrics import metrics_collector


class CompressionMiddleware(BaseHTTPMiddleware):
    """Middleware for response compression and optimization."""
    
    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 500,
        compression_level: int = 6,
        exclude_media_types: Optional[List[str]] = None
    ):
        super().__init__(app)
        self.minimum_size = minimum_size
        self.compression_level = compression_level
        self.exclude_media_types = exclude_media_types or [
            "image/",
            "video/",
            "audio/",
            "application/zip",
            "application/gzip",
            "application/x-compressed"
        ]
        
    async def dispatch(self, request: Request, call_next):
        """Apply compression if appropriate."""
        # Check if client accepts gzip
        accept_encoding = request.headers.get("accept-encoding", "")
        supports_gzip = "gzip" in accept_encoding.lower()
        
        if not supports_gzip:
            return await call_next(request)
            
        # Get response
        response = await call_next(request)
        
        # Skip compression for certain conditions
        if self._should_skip_compression(response):
            return response
            
        # Apply compression
        return await self._compress_response(response)
        
    def _should_skip_compression(self, response: Response) -> bool:
        """Determine if compression should be skipped."""
        # Skip if already compressed
        if response.headers.get("content-encoding"):
            return True
            
        # Skip for certain status codes
        if response.status_code < 200 or response.status_code >= 300:
            return True
            
        # Skip for excluded media types
        content_type = response.headers.get("content-type", "")
        if any(excluded in content_type for excluded in self.exclude_media_types):
            return True
            
        # Skip if response is too small
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) < self.minimum_size:
            return True
            
        return False
        
    async def _compress_response(self, response: Response) -> Response:
        """Compress response body."""
        # Get response body
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
            
        # Skip if body is too small
        if len(body) < self.minimum_size:
            # Recreate response with original body
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )
            
        # Compress body
        start_time = time.time()
        compressed_body = gzip.compress(body, compresslevel=self.compression_level)
        compression_time = time.time() - start_time
        
        # Calculate compression ratio
        original_size = len(body)
        compressed_size = len(compressed_body)
        compression_ratio = compressed_size / original_size if original_size > 0 else 1.0
        
        # Record metrics
        metrics_collector.histogram("http.compression.ratio", compression_ratio)
        metrics_collector.histogram("http.compression.time", compression_time)
        metrics_collector.histogram("http.compression.original_size", original_size)
        metrics_collector.histogram("http.compression.compressed_size", compressed_size)
        metrics_collector.counter("http.responses.compressed")
        
        # Update headers
        headers = dict(response.headers)
        headers["content-encoding"] = "gzip"
        headers["content-length"] = str(compressed_size)
        headers["x-compression-ratio"] = f"{compression_ratio:.3f}"
        headers["x-original-size"] = str(original_size)
        
        # Return compressed response
        return Response(
            content=compressed_body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type
        )


class ResponseOptimizationMiddleware(BaseHTTPMiddleware):
    """Middleware for response optimization techniques."""
    
    def __init__(
        self,
        app: ASGIApp,
        enable_etag: bool = True,
        enable_caching_headers: bool = True,
        max_age: int = 300,  # 5 minutes default cache
    ):
        super().__init__(app)
        self.enable_etag = enable_etag
        self.enable_caching_headers = enable_caching_headers
        self.max_age = max_age
        
    async def dispatch(self, request: Request, call_next):
        """Optimize response."""
        # Check for conditional requests
        if_none_match = request.headers.get("if-none-match")
        if_modified_since = request.headers.get("if-modified-since")
        
        # Get response
        response = await call_next(request)
        
        # Apply optimizations
        response = self._add_caching_headers(request, response)
        response = await self._handle_etag(request, response, if_none_match)
        
        return response
        
    def _add_caching_headers(self, request: Request, response: Response) -> Response:
        """Add appropriate caching headers."""
        if not self.enable_caching_headers:
            return response
            
        # Skip caching for error responses
        if response.status_code >= 400:
            return response
            
        # Determine cache strategy based on endpoint
        path = request.url.path
        
        if self._is_static_endpoint(path):
            # Static data - longer cache
            response.headers["cache-control"] = f"public, max-age={self.max_age * 12}"  # 1 hour
        elif self._is_market_data_endpoint(path):
            # Market data - short cache
            response.headers["cache-control"] = "public, max-age=5"  # 5 seconds
        elif self._is_user_specific_endpoint(path):
            # User-specific data - private cache
            response.headers["cache-control"] = "private, max-age=60"  # 1 minute
        else:
            # Default caching
            response.headers["cache-control"] = f"public, max-age={self.max_age}"
            
        # Add vary header for content negotiation
        response.headers["vary"] = "Accept-Encoding, Authorization"
        
        return response
        
    async def _handle_etag(
        self,
        request: Request,
        response: Response,
        if_none_match: Optional[str]
    ) -> Response:
        """Handle ETag for conditional requests."""
        if not self.enable_etag or response.status_code != 200:
            return response
            
        # Get response body to generate ETag
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
            
        # Generate ETag based on content hash
        import hashlib
        etag = f'"{hashlib.md5(body).hexdigest()}"'
        
        # Check if client has cached version
        if if_none_match and if_none_match == etag:
            # Return 304 Not Modified
            return Response(
                status_code=304,
                headers={
                    "etag": etag,
                    "cache-control": response.headers.get("cache-control", ""),
                }
            )
            
        # Add ETag to response
        response.headers["etag"] = etag
        
        # Recreate response with ETag
        return Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type
        )
        
    def _is_static_endpoint(self, path: str) -> bool:
        """Check if endpoint serves static data."""
        static_patterns = [
            "/api/v1/market-data/symbols",
            "/docs",
            "/redoc",
            "/openapi.json"
        ]
        return any(pattern in path for pattern in static_patterns)
        
    def _is_market_data_endpoint(self, path: str) -> bool:
        """Check if endpoint serves market data."""
        market_patterns = [
            "/api/v1/market-data/ticks",
            "/api/v1/market-data/latest",
            "/api/v1/market-data/stream_status"
        ]
        return any(pattern in path for pattern in market_patterns)
        
    def _is_user_specific_endpoint(self, path: str) -> bool:
        """Check if endpoint serves user-specific data."""
        user_patterns = [
            "/api/v1/auth/me",
            "/api/v1/trading/orders",
            "/api/v1/trading/positions",
            "/api/v1/api-keys"
        ]
        return any(pattern in path for pattern in user_patterns)


class ContentOptimizationMiddleware(BaseHTTPMiddleware):
    """Middleware for content optimization (JSON minification, etc.)."""
    
    def __init__(
        self,
        app: ASGIApp,
        minify_json: bool = True,
        remove_null_fields: bool = True,
        enable_pagination_optimization: bool = True
    ):
        super().__init__(app)
        self.minify_json = minify_json
        self.remove_null_fields = remove_null_fields
        self.enable_pagination_optimization = enable_pagination_optimization
        
    async def dispatch(self, request: Request, call_next):
        """Optimize response content."""
        response = await call_next(request)
        
        # Only optimize JSON responses
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            return response
            
        # Get response body
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
            
        try:
            # Parse JSON
            data = json.loads(body.decode())
            
            # Apply optimizations
            if self.remove_null_fields:
                data = self._remove_null_fields(data)
                
            # Serialize with optimizations
            if self.minify_json:
                optimized_body = json.dumps(
                    data,
                    separators=(',', ':'),  # Compact separators
                    ensure_ascii=False
                ).encode()
            else:
                optimized_body = json.dumps(data).encode()
                
            # Calculate optimization savings
            original_size = len(body)
            optimized_size = len(optimized_body)
            savings = original_size - optimized_size
            
            if savings > 0:
                metrics_collector.histogram("http.optimization.savings_bytes", savings)
                metrics_collector.counter("http.responses.optimized")
                
            # Update content-length
            headers = dict(response.headers)
            headers["content-length"] = str(optimized_size)
            if savings > 0:
                headers["x-optimization-savings"] = str(savings)
                
            return Response(
                content=optimized_body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type
            )
            
        except (json.JSONDecodeError, UnicodeDecodeError):
            # If we can't parse/optimize, return original
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )
            
    def _remove_null_fields(self, data: Any) -> Any:
        """Recursively remove null/None fields from data."""
        if isinstance(data, dict):
            return {
                k: self._remove_null_fields(v)
                for k, v in data.items()
                if v is not None
            }
        elif isinstance(data, list):
            return [
                self._remove_null_fields(item)
                for item in data
                if item is not None
            ]
        else:
            return data


class ResponseSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to limit response sizes and implement streaming for large responses."""
    
    def __init__(
        self,
        app: ASGIApp,
        max_response_size: int = 10 * 1024 * 1024,  # 10MB
        enable_streaming_threshold: int = 1024 * 1024,  # 1MB
    ):
        super().__init__(app)
        self.max_response_size = max_response_size
        self.enable_streaming_threshold = enable_streaming_threshold
        
    async def dispatch(self, request: Request, call_next):
        """Check response size and apply streaming if needed."""
        response = await call_next(request)
        
        # Check content-length if available
        content_length = response.headers.get("content-length")
        if content_length:
            size = int(content_length)
            
            if size > self.max_response_size:
                # Response too large
                metrics_collector.counter("http.responses.too_large")
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "Response too large",
                        "message": f"Response size {size} exceeds limit {self.max_response_size}",
                        "suggestion": "Use pagination or filtering to reduce response size"
                    }
                )
                
            if size > self.enable_streaming_threshold:
                # Convert to streaming response for large content
                metrics_collector.counter("http.responses.streamed")
                response.headers["x-streaming"] = "true"
                
        return response