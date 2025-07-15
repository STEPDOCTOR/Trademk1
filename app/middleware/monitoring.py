"""Request monitoring middleware for logging and metrics collection."""

import asyncio
import time
import uuid
from typing import Optional, Dict, Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.monitoring.logger import get_performance_logger, get_security_logger
from app.monitoring.metrics import metrics_collector, timer


class RequestMonitoringMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive request monitoring."""
    
    def __init__(self, app, enable_detailed_logging: bool = True):
        super().__init__(app)
        self.enable_detailed_logging = enable_detailed_logging
        self.performance_logger = get_performance_logger()
        self.security_logger = get_security_logger()
        
    async def dispatch(self, request: Request, call_next):
        """Monitor request and response."""
        # Generate request ID for correlation
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Get client information
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "")
        user_id = getattr(request.state, "user_id", None)
        
        # Start timing
        start_time = time.time()
        
        # Increment request counter
        metrics_collector.counter(
            "http.requests.total",
            tags={
                "method": request.method,
                "path": self._normalize_path(request.url.path),
                "user_type": "authenticated" if user_id else "anonymous"
            }
        )
        
        # Track concurrent requests
        metrics_collector.gauge("http.requests.active", 1)
        
        try:
            # Process request with timing
            with timer("http.request.duration", tags={
                "method": request.method,
                "path": self._normalize_path(request.url.path)
            }):
                response = await call_next(request)
                
            # Calculate duration
            duration = time.time() - start_time
            
            # Log performance metrics
            self.performance_logger.log_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration=duration,
                user_id=user_id,
                request_id=request_id,
                ip_address=client_ip,
                user_agent=user_agent,
                content_length=response.headers.get("content-length"),
                response_size=response.headers.get("content-length")
            )
            
            # Record metrics
            metrics_collector.counter(
                "http.responses.total",
                tags={
                    "method": request.method,
                    "path": self._normalize_path(request.url.path),
                    "status_code": str(response.status_code),
                    "status_class": f"{response.status_code // 100}xx"
                }
            )
            
            metrics_collector.histogram(
                "http.request.size_bytes",
                self._get_request_size(request),
                tags={"method": request.method}
            )
            
            if "content-length" in response.headers:
                metrics_collector.histogram(
                    "http.response.size_bytes",
                    int(response.headers["content-length"]),
                    tags={"status_code": str(response.status_code)}
                )
            
            # Add correlation headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration:.3f}"
            
            # Log security events for suspicious activity
            if duration > 10.0:  # Very slow request
                self.security_logger.log_security_violation(
                    violation_type="slow_request",
                    ip_address=client_ip,
                    details=f"Request took {duration:.2f}s: {request.method} {request.url.path}",
                    severity="low"
                )
                
            if response.status_code >= 400:
                # Log failed requests
                metrics_collector.counter(
                    "http.errors.total",
                    tags={
                        "status_code": str(response.status_code),
                        "method": request.method,
                        "path": self._normalize_path(request.url.path)
                    }
                )
                
                if response.status_code == 401:
                    self.security_logger.log_authentication_attempt(
                        email="unknown",
                        success=False,
                        ip_address=client_ip,
                        user_agent=user_agent
                    )
                    
            return response
            
        except Exception as e:
            # Calculate duration for failed requests
            duration = time.time() - start_time
            
            # Log the error
            self.performance_logger.log_request(
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration=duration,
                user_id=user_id,
                request_id=request_id,
                ip_address=client_ip,
                user_agent=user_agent,
                error=str(e)
            )
            
            # Record error metrics
            metrics_collector.counter(
                "http.errors.total",
                tags={
                    "status_code": "500",
                    "method": request.method,
                    "path": self._normalize_path(request.url.path),
                    "error_type": type(e).__name__
                }
            )
            
            # Re-raise the exception
            raise
            
        finally:
            # Decrement active requests
            metrics_collector.gauge("http.requests.active", -1)
            
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
        
    def _get_request_size(self, request: Request) -> int:
        """Get request size in bytes."""
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                return int(content_length)
            except ValueError:
                pass
        return 0
        
    def _normalize_path(self, path: str) -> str:
        """Normalize path for metrics (remove dynamic parts)."""
        # Replace UUIDs and IDs with placeholders to reduce cardinality
        import re
        
        # Replace UUIDs
        path = re.sub(
            r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '/{uuid}',
            path,
            flags=re.IGNORECASE
        )
        
        # Replace numeric IDs
        path = re.sub(r'/\d+', '/{id}', path)
        
        # Replace long strings that might be tokens
        path = re.sub(r'/[a-zA-Z0-9_-]{20,}', '/{token}', path)
        
        return path


class DatabaseMonitoringMiddleware:
    """Middleware for monitoring database operations."""
    
    def __init__(self):
        self.performance_logger = get_performance_logger()
        
    def register_with_engine(self, engine):
        """Register SQLAlchemy event listeners."""
        from sqlalchemy import event
        
        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            context._query_start_time = time.time()
            context._query_statement = statement
            
        @event.listens_for(engine.sync_engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            duration = time.time() - context._query_start_time
            
            # Log slow queries
            self.performance_logger.log_database_query(
                query=statement,
                duration=duration,
                rows_affected=cursor.rowcount if hasattr(cursor, 'rowcount') else None
            )
            
            # Record metrics
            metrics_collector.timing("database.query.duration", duration)
            metrics_collector.counter("database.queries.total")
            
            if duration > 1.0:  # Slow query threshold
                metrics_collector.counter("database.queries.slow")
                
        @event.listens_for(engine.sync_engine.pool, "checkout")
        def connection_checkout(dbapi_conn, connection_record, connection_proxy):
            metrics_collector.counter("database.connections.checkout")
            metrics_collector.gauge("database.connections.active", 1)
            
        @event.listens_for(engine.sync_engine.pool, "checkin")
        def connection_checkin(dbapi_conn, connection_record):
            metrics_collector.gauge("database.connections.active", -1)
            
        @event.listens_for(engine.sync_engine.pool, "invalidate")
        def connection_invalidate(dbapi_conn, connection_record, exception):
            metrics_collector.counter("database.connections.errors")


class CacheMonitoringDecorator:
    """Decorator for monitoring cache operations."""
    
    def __init__(self, cache_service):
        self.cache_service = cache_service
        self.performance_logger = get_performance_logger()
        
    def _wrap_method(self, method_name: str, original_method):
        """Wrap a cache method with monitoring."""
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = await original_method(*args, **kwargs)
                duration = time.time() - start_time
                
                # Determine if it was a hit or miss
                hit = result is not None if method_name == "get" else True
                
                # Log cache operation
                self.performance_logger.log_cache_operation(
                    operation=method_name,
                    key=str(args[0]) if args else "unknown",
                    hit=hit,
                    duration=duration
                )
                
                # Record metrics
                metrics_collector.timing(
                    "cache.operation.duration",
                    duration,
                    tags={"operation": method_name}
                )
                
                metrics_collector.counter(
                    "cache.operations.total",
                    tags={
                        "operation": method_name,
                        "result": "hit" if hit else "miss"
                    }
                )
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                
                # Record error metrics
                metrics_collector.counter(
                    "cache.errors.total",
                    tags={"operation": method_name}
                )
                
                raise
                
        return wrapper
        
    def apply_monitoring(self):
        """Apply monitoring to cache service methods."""
        methods_to_monitor = ["get", "set", "delete", "exists", "get_many", "set_many"]
        
        for method_name in methods_to_monitor:
            if hasattr(self.cache_service, method_name):
                original_method = getattr(self.cache_service, method_name)
                wrapped_method = self._wrap_method(method_name, original_method)
                setattr(self.cache_service, method_name, wrapped_method)


# Health check endpoint with detailed metrics
async def get_detailed_health_metrics() -> Dict[str, Any]:
    """Get detailed health metrics for monitoring dashboards."""
    
    # Get all current metrics
    all_metrics = metrics_collector.get_all_metrics()
    
    # Organize metrics by category
    health_data = {
        "timestamp": time.time(),
        "status": "healthy",
        "metrics": {
            "http": {},
            "database": {},
            "cache": {},
            "system": {}
        }
    }
    
    for metric_key, summary in all_metrics.items():
        metric_name = summary.name
        
        if metric_name.startswith("http."):
            health_data["metrics"]["http"][metric_name] = {
                "count": summary.count,
                "avg": summary.avg_value,
                "last": summary.last_value,
                "last_updated": summary.last_updated.isoformat()
            }
        elif metric_name.startswith("database."):
            health_data["metrics"]["database"][metric_name] = {
                "count": summary.count,
                "avg": summary.avg_value,
                "last": summary.last_value,
                "last_updated": summary.last_updated.isoformat()
            }
        elif metric_name.startswith("cache."):
            health_data["metrics"]["cache"][metric_name] = {
                "count": summary.count,
                "avg": summary.avg_value,
                "last": summary.last_value,
                "last_updated": summary.last_updated.isoformat()
            }
        elif metric_name.startswith("system."):
            health_data["metrics"]["system"][metric_name] = {
                "count": summary.count,
                "avg": summary.avg_value,
                "last": summary.last_value,
                "last_updated": summary.last_updated.isoformat()
            }
    
    # Calculate overall health status
    error_rate = 0
    if "http.errors.total" in all_metrics and "http.requests.total" in all_metrics:
        errors = all_metrics["http.errors.total"].last_value
        requests = all_metrics["http.requests.total"].last_value
        if requests > 0:
            error_rate = errors / requests
            
    if error_rate > 0.1:  # 10% error rate
        health_data["status"] = "degraded"
    elif error_rate > 0.05:  # 5% error rate
        health_data["status"] = "warning"
        
    return health_data