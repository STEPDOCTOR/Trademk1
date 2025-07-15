"""Admin API endpoints for system monitoring and management."""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, AuthUser, require_superuser
from app.db.postgres import get_db, optimized_db, query_analyzer
from app.db.query_analyzer import IndexAdvisor
from app.services.cache import cache_service
from app.middleware.security import SecurityManager, SecurityConfig
from app.middleware.monitoring import get_detailed_health_metrics
from app.monitoring.metrics import metrics_collector

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# Response models
class ConnectionPoolStats(BaseModel):
    """Connection pool statistics."""
    pool_size: int
    active_connections: int
    idle_connections: int
    checked_in_connections: int
    overflow: int
    total: int
    connection_errors: int
    last_error: Optional[str]


class QueryPerformanceStats(BaseModel):
    """Query performance statistics."""
    query: str
    execution_count: int
    total_time: float
    avg_time: float
    min_time: float
    max_time: float
    slow_count: int
    last_executed: Optional[datetime]


class DatabaseStats(BaseModel):
    """Database statistics."""
    database_size: str
    active_connections: int
    max_connections: int
    cache_hit_ratio: float
    index_hit_ratio: float
    deadlocks: int
    slow_queries: int


class SystemHealth(BaseModel):
    """Overall system health."""
    status: str
    database: Dict[str, Any]
    cache: Dict[str, Any]
    connection_pool: ConnectionPoolStats
    timestamp: datetime


class IndexSuggestion(BaseModel):
    """Index suggestion."""
    table: str
    reason: str
    impact: str
    seq_scans: int
    tuples_read: int
    write_activity: int


class SecurityStats(BaseModel):
    """Security statistics."""
    blocked_ips_count: int
    allowed_ips_count: int
    temporarily_banned_count: int
    blocked_networks_count: int
    blocked_ips: List[str]
    allowed_ips: List[str]
    temporarily_banned: List[str]


class IPManagementRequest(BaseModel):
    """IP management request."""
    ip: str
    reason: Optional[str] = "Manual action"
    permanent: bool = False


@router.get("/health", response_model=SystemHealth)
async def get_system_health(
    current_user: AuthUser = Depends(require_superuser),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive system health status."""
    # Database health
    db_healthy = await optimized_db.health_check()
    
    # Connection pool stats
    pool_stats = await optimized_db.get_connection_stats()
    
    # Cache health
    cache_healthy = True
    cache_stats = {}
    try:
        await cache_service.connect()
        # Test cache operation
        test_key = "health_check_test"
        await cache_service.set(test_key, "ok", expire=1)
        cache_result = await cache_service.get(test_key)
        cache_healthy = cache_result == "ok"
        await cache_service.delete(test_key)
        
        # Get cache info
        cache_stats = {
            "connected": True,
            "test_passed": cache_healthy
        }
    except Exception as e:
        cache_healthy = False
        cache_stats = {
            "connected": False,
            "error": str(e)
        }
    
    # Overall status
    overall_status = "healthy" if db_healthy and cache_healthy else "unhealthy"
    
    return SystemHealth(
        status=overall_status,
        database={
            "healthy": db_healthy,
            "connection_pool_active": pool_stats.get("active_connections", 0),
            "connection_pool_total": pool_stats.get("total", 0)
        },
        cache={
            "healthy": cache_healthy,
            **cache_stats
        },
        connection_pool=ConnectionPoolStats(**pool_stats),
        timestamp=datetime.utcnow()
    )


@router.get("/database/stats", response_model=DatabaseStats)
async def get_database_stats(
    current_user: AuthUser = Depends(require_superuser),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed database statistics."""
    # Database size
    size_query = text("""
        SELECT pg_size_pretty(pg_database_size(current_database())) as db_size
    """)
    size_result = await db.execute(size_query)
    db_size = size_result.scalar()
    
    # Connection statistics
    conn_query = text("""
        SELECT 
            count(*) as active_connections,
            setting::int as max_connections
        FROM pg_stat_activity, pg_settings 
        WHERE pg_settings.name = 'max_connections'
        GROUP BY setting
    """)
    conn_result = await db.execute(conn_query)
    conn_stats = conn_result.fetchone()
    
    # Cache hit ratio
    cache_query = text("""
        SELECT 
            round(100.0 * sum(blks_hit) / (sum(blks_hit) + sum(blks_read)), 2) as cache_hit_ratio
        FROM pg_stat_database
        WHERE datname = current_database()
    """)
    cache_result = await db.execute(cache_query)
    cache_hit_ratio = cache_result.scalar() or 0.0
    
    # Index hit ratio
    index_query = text("""
        SELECT 
            round(100.0 * sum(idx_blks_hit) / (sum(idx_blks_hit) + sum(idx_blks_read)), 2) as index_hit_ratio
        FROM pg_statio_user_indexes
    """)
    index_result = await db.execute(index_query)
    index_hit_ratio = index_result.scalar() or 0.0
    
    # Deadlock count
    deadlock_query = text("""
        SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()
    """)
    deadlock_result = await db.execute(deadlock_query)
    deadlocks = deadlock_result.scalar() or 0
    
    # Slow query count from analyzer
    slow_queries = sum(
        1 for stats in query_analyzer.query_stats.values() 
        if stats.slow_count > 0
    )
    
    return DatabaseStats(
        database_size=db_size,
        active_connections=conn_stats.active_connections if conn_stats else 0,
        max_connections=conn_stats.max_connections if conn_stats else 0,
        cache_hit_ratio=cache_hit_ratio,
        index_hit_ratio=index_hit_ratio,
        deadlocks=deadlocks,
        slow_queries=slow_queries
    )


@router.get("/database/slow-queries", response_model=List[QueryPerformanceStats])
async def get_slow_queries(
    limit: int = 10,
    current_user: AuthUser = Depends(require_superuser)
):
    """Get slow queries from performance analyzer."""
    slow_queries = query_analyzer.get_slow_queries(limit=limit)
    
    return [
        QueryPerformanceStats(
            query=stats.query,
            execution_count=stats.execution_count,
            total_time=stats.total_time,
            avg_time=stats.avg_time,
            min_time=stats.min_time if stats.min_time != float('inf') else 0.0,
            max_time=stats.max_time,
            slow_count=stats.slow_count,
            last_executed=stats.last_executed
        )
        for stats in slow_queries
    ]


@router.get("/database/frequent-queries", response_model=List[QueryPerformanceStats])
async def get_frequent_queries(
    limit: int = 10,
    current_user: AuthUser = Depends(require_superuser)
):
    """Get frequently executed queries."""
    frequent_queries = query_analyzer.get_frequent_queries(limit=limit)
    
    return [
        QueryPerformanceStats(
            query=stats.query,
            execution_count=stats.execution_count,
            total_time=stats.total_time,
            avg_time=stats.avg_time,
            min_time=stats.min_time if stats.min_time != float('inf') else 0.0,
            max_time=stats.max_time,
            slow_count=stats.slow_count,
            last_executed=stats.last_executed
        )
        for stats in frequent_queries
    ]


@router.get("/database/index-suggestions", response_model=List[IndexSuggestion])
async def get_index_suggestions(
    min_occurrences: int = 5,
    current_user: AuthUser = Depends(require_superuser),
    db: AsyncSession = Depends(get_db)
):
    """Get suggestions for missing indexes."""
    advisor = IndexAdvisor()
    suggestions = await advisor.suggest_missing_indexes(db, min_occurrences)
    
    return [
        IndexSuggestion(
            table=suggestion["table"],
            reason=suggestion["reason"],
            impact=suggestion["impact"],
            seq_scans=suggestion["seq_scans"],
            tuples_read=suggestion["tuples_read"],
            write_activity=suggestion["write_activity"]
        )
        for suggestion in suggestions
    ]


@router.get("/database/table-info/{table_name}")
async def get_table_info(
    table_name: str,
    schema: str = "public",
    current_user: AuthUser = Depends(require_superuser),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed information about a table."""
    advisor = IndexAdvisor()
    table_info = await advisor.analyze_table_indexes(db, table_name, schema)
    return table_info


@router.post("/cache/clear")
async def clear_cache(
    pattern: Optional[str] = None,
    current_user: AuthUser = Depends(require_superuser)
):
    """Clear cache entries."""
    try:
        await cache_service.connect()
        
        if pattern:
            await cache_service.flush_pattern(pattern)
            message = f"Cache entries matching '{pattern}' cleared"
        else:
            await cache_service.flush_all()
            message = "All cache entries cleared"
            
        return {"message": message}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cache: {str(e)}"
        )


@router.get("/connection-pool/stats", response_model=ConnectionPoolStats)
async def get_connection_pool_stats(
    current_user: AuthUser = Depends(require_superuser)
):
    """Get connection pool statistics."""
    stats = await optimized_db.get_connection_stats()
    return ConnectionPoolStats(**stats)


@router.post("/query-analyzer/reset")
async def reset_query_analyzer(
    current_user: AuthUser = Depends(require_superuser)
):
    """Reset query analyzer statistics."""
    query_analyzer.query_stats.clear()
    return {"message": "Query analyzer statistics reset"}


@router.get("/database/explain/{table_name}")
async def explain_table_queries(
    table_name: str,
    current_user: AuthUser = Depends(require_superuser),
    db: AsyncSession = Depends(get_db)
):
    """Show EXPLAIN ANALYZE for common queries on a table."""
    # This is a simplified example - in practice, you'd want to 
    # capture and explain actual queries from your application
    
    sample_queries = [
        f"SELECT * FROM {table_name} LIMIT 100",
        f"SELECT COUNT(*) FROM {table_name}",
    ]
    
    results = []
    for query_sql in sample_queries:
        try:
            explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query_sql}"
            result = await db.execute(text(explain_query))
            explain_data = result.scalar()
            results.append({
                "query": query_sql,
                "plan": explain_data[0] if explain_data else None
            })
        except Exception as e:
            results.append({
                "query": query_sql,
                "error": str(e)
            })
    
    return {"table": table_name, "analyses": results}


# Security management endpoints
security_manager = SecurityManager(SecurityConfig())


@router.get("/security/stats", response_model=SecurityStats)
async def get_security_stats(
    current_user: AuthUser = Depends(require_superuser)
):
    """Get security statistics."""
    stats = await security_manager.get_security_stats()
    return SecurityStats(**stats)


@router.post("/security/block-ip")
async def block_ip(
    request_data: IPManagementRequest,
    current_user: AuthUser = Depends(require_superuser)
):
    """Block an IP address."""
    await security_manager.block_ip(
        request_data.ip,
        permanent=request_data.permanent,
        reason=request_data.reason
    )
    
    action = "permanently" if request_data.permanent else "temporarily"
    return {
        "message": f"IP {request_data.ip} {action} blocked",
        "reason": request_data.reason
    }


@router.post("/security/unblock-ip")
async def unblock_ip(
    ip: str,
    current_user: AuthUser = Depends(require_superuser)
):
    """Unblock an IP address."""
    await security_manager.unblock_ip(ip)
    return {"message": f"IP {ip} unblocked"}


@router.post("/security/allow-ip")
async def allow_ip(
    ip: str,
    current_user: AuthUser = Depends(require_superuser)
):
    """Add IP to allow list."""
    security_manager.allow_ip(ip)
    return {"message": f"IP {ip} added to allow list"}


@router.delete("/security/allow-ip/{ip}")
async def remove_allowed_ip(
    ip: str,
    current_user: AuthUser = Depends(require_superuser)
):
    """Remove IP from allow list."""
    security_manager.remove_allowed_ip(ip)
    return {"message": f"IP {ip} removed from allow list"}


@router.get("/rate-limits/stats")
async def get_rate_limit_stats(
    current_user: AuthUser = Depends(require_superuser)
):
    """Get rate limiting statistics."""
    try:
        await cache_service.connect()
        
        # Get rate limit keys
        rate_limit_keys = []
        cursor = 0
        while True:
            cursor, keys = await cache_service.client.scan(
                cursor, match="rate_limit:*", count=100
            )
            rate_limit_keys.extend(keys)
            if cursor == 0:
                break
        
        # Aggregate stats by type
        stats = {
            "total_tracked_entities": len(rate_limit_keys),
            "by_type": {
                "ip": len([k for k in rate_limit_keys if ":ip:" in k]),
                "user": len([k for k in rate_limit_keys if ":user:" in k]),
                "api_key": len([k for k in rate_limit_keys if ":api_key:" in k])
            },
            "sample_keys": rate_limit_keys[:10]  # Show first 10 for debugging
        }
        
        return stats
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get rate limit stats: {str(e)}"
        )


@router.post("/rate-limits/clear")
async def clear_rate_limits(
    pattern: Optional[str] = None,
    current_user: AuthUser = Depends(require_superuser)
):
    """Clear rate limit entries."""
    try:
        await cache_service.connect()
        
        if pattern:
            # Clear specific pattern
            await cache_service.flush_pattern(f"rate_limit:{pattern}")
            message = f"Rate limit entries matching 'rate_limit:{pattern}' cleared"
        else:
            # Clear all rate limits
            await cache_service.flush_pattern("rate_limit:*")
            message = "All rate limit entries cleared"
            
        return {"message": message}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear rate limits: {str(e)}"
        )


# Monitoring and metrics endpoints
@router.get("/metrics/detailed")
async def get_detailed_metrics(
    current_user: AuthUser = Depends(require_superuser)
):
    """Get detailed application metrics."""
    return await get_detailed_health_metrics()


@router.get("/metrics/summary")
async def get_metrics_summary(
    current_user: AuthUser = Depends(require_superuser)
):
    """Get metrics summary."""
    all_metrics = metrics_collector.get_all_metrics()
    
    summary = {
        "total_metrics": len(all_metrics),
        "categories": {
            "http": len([m for m in all_metrics if m.startswith("http.")]),
            "database": len([m for m in all_metrics if m.startswith("database.")]),
            "cache": len([m for m in all_metrics if m.startswith("cache.")]),
            "system": len([m for m in all_metrics if m.startswith("system.")]),
        },
        "recent_metrics": [
            {
                "name": name,
                "last_value": summary.last_value,
                "count": summary.count,
                "avg": summary.avg_value,
                "last_updated": summary.last_updated
            }
            for name, summary in list(all_metrics.items())[:20]
        ]
    }
    
    return summary


@router.get("/metrics/{metric_name}")
async def get_metric_details(
    metric_name: str,
    current_user: AuthUser = Depends(require_superuser)
):
    """Get details for a specific metric."""
    summary = metrics_collector.get_metric_summary(metric_name)
    
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metric {metric_name} not found"
        )
    
    # Get percentiles if it's a histogram metric
    percentiles = {}
    if "duration" in metric_name or "size" in metric_name:
        percentiles = metrics_collector.get_histogram_percentiles(metric_name)
    
    return {
        "summary": {
            "name": summary.name,
            "count": summary.count,
            "sum": summary.sum_value,
            "min": summary.min_value,
            "max": summary.max_value,
            "avg": summary.avg_value,
            "last": summary.last_value,
            "last_updated": summary.last_updated
        },
        "percentiles": percentiles
    }


@router.post("/metrics/reset")
async def reset_metrics(
    metric_name: Optional[str] = None,
    current_user: AuthUser = Depends(require_superuser)
):
    """Reset metrics (all or specific metric)."""
    if metric_name:
        metrics_collector.reset_metric(metric_name)
        return {"message": f"Metric {metric_name} reset"}
    else:
        metrics_collector.reset_all_metrics()
        return {"message": "All metrics reset"}