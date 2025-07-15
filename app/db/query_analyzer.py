"""Query performance analyzer for PostgreSQL optimization."""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects import postgresql

logger = logging.getLogger(__name__)


@dataclass
class QueryStats:
    """Statistics for a single query."""
    query: str
    execution_count: int = 0
    total_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    avg_time: float = 0.0
    last_executed: Optional[datetime] = None
    slow_count: int = 0  # Count of executions over threshold
    
    def add_execution(self, execution_time: float, slow_threshold: float = 1.0):
        """Add an execution to the statistics."""
        self.execution_count += 1
        self.total_time += execution_time
        self.min_time = min(self.min_time, execution_time)
        self.max_time = max(self.max_time, execution_time)
        self.avg_time = self.total_time / self.execution_count
        self.last_executed = datetime.utcnow()
        
        if execution_time > slow_threshold:
            self.slow_count += 1


@dataclass
class ExplainAnalysis:
    """EXPLAIN ANALYZE results."""
    query: str
    plan: Dict[str, Any]
    execution_time: float
    planning_time: float
    total_cost: float
    rows_estimated: int
    rows_actual: int
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class QueryPerformanceAnalyzer:
    """Analyze query performance and provide optimization suggestions."""
    
    def __init__(self, slow_query_threshold: float = 1.0):
        self.slow_query_threshold = slow_query_threshold
        self.query_stats: Dict[str, QueryStats] = {}
        self._monitoring = False
        
    def start_monitoring(self):
        """Start query monitoring."""
        self._monitoring = True
        logger.info(f"Query monitoring started (threshold={self.slow_query_threshold}s)")
        
    def stop_monitoring(self):
        """Stop query monitoring."""
        self._monitoring = False
        logger.info("Query monitoring stopped")
        
    def log_query_execution(self, query: str, execution_time: float):
        """Log a query execution."""
        if not self._monitoring:
            return
            
        # Normalize query for grouping
        normalized = self._normalize_query(query)
        
        if normalized not in self.query_stats:
            self.query_stats[normalized] = QueryStats(query=normalized)
            
        self.query_stats[normalized].add_execution(execution_time, self.slow_query_threshold)
        
        # Log slow queries
        if execution_time > self.slow_query_threshold:
            logger.warning(
                f"Slow query detected ({execution_time:.2f}s): {query[:100]}..."
            )
            
    def _normalize_query(self, query: str) -> str:
        """Normalize query for statistical grouping."""
        # Remove whitespace variations
        normalized = " ".join(query.split())
        
        # Remove specific values (basic normalization)
        # In production, use a proper SQL parser
        import re
        # Replace numbers with ?
        normalized = re.sub(r'\b\d+\b', '?', normalized)
        # Replace quoted strings with ?
        normalized = re.sub(r"'[^']*'", '?', normalized)
        
        return normalized[:200]  # Limit length for storage
        
    def get_slow_queries(self, limit: int = 10) -> List[QueryStats]:
        """Get the slowest queries."""
        sorted_queries = sorted(
            self.query_stats.values(),
            key=lambda x: x.max_time,
            reverse=True
        )
        return sorted_queries[:limit]
        
    def get_frequent_queries(self, limit: int = 10) -> List[QueryStats]:
        """Get the most frequently executed queries."""
        sorted_queries = sorted(
            self.query_stats.values(),
            key=lambda x: x.execution_count,
            reverse=True
        )
        return sorted_queries[:limit]
        
    async def explain_analyze_query(
        self,
        session: AsyncSession,
        query: sa.Select,
        params: Optional[Dict[str, Any]] = None
    ) -> ExplainAnalysis:
        """Run EXPLAIN ANALYZE on a query and analyze results."""
        # Compile query to SQL
        compiled = query.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True}
        )
        sql = str(compiled)
        
        # Run EXPLAIN ANALYZE
        explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"
        
        start_time = time.time()
        result = await session.execute(sa.text(explain_query))
        execution_time = time.time() - start_time
        
        # Parse results
        explain_data = result.scalar()
        plan = explain_data[0] if explain_data else {}
        
        # Extract key metrics
        analysis = ExplainAnalysis(
            query=sql,
            plan=plan,
            execution_time=execution_time * 1000,  # Convert to ms
            planning_time=plan.get("Planning Time", 0),
            total_cost=plan.get("Plan", {}).get("Total Cost", 0),
            rows_estimated=plan.get("Plan", {}).get("Plan Rows", 0),
            rows_actual=plan.get("Plan", {}).get("Actual Rows", 0)
        )
        
        # Analyze for issues
        self._analyze_plan(analysis)
        
        return analysis
        
    def _analyze_plan(self, analysis: ExplainAnalysis):
        """Analyze query plan for potential issues."""
        plan = analysis.plan.get("Plan", {})
        
        # Check for sequential scans on large tables
        if self._has_seq_scan(plan):
            analysis.issues.append("Sequential scan detected")
            analysis.suggestions.append("Consider adding an index")
            
        # Check for poor row estimation
        if analysis.rows_estimated > 0 and analysis.rows_actual > 0:
            estimation_error = abs(analysis.rows_estimated - analysis.rows_actual) / analysis.rows_estimated
            if estimation_error > 0.5:
                analysis.issues.append(f"Poor row estimation (estimated: {analysis.rows_estimated}, actual: {analysis.rows_actual})")
                analysis.suggestions.append("Update table statistics with ANALYZE")
                
        # Check for expensive sorts
        if self._has_expensive_sort(plan):
            analysis.issues.append("Expensive sort operation detected")
            analysis.suggestions.append("Consider adding an index to avoid sorting")
            
        # Check for nested loops with high cost
        if self._has_expensive_nested_loop(plan):
            analysis.issues.append("Expensive nested loop detected")
            analysis.suggestions.append("Consider using a different join strategy")
            
    def _has_seq_scan(self, plan: Dict[str, Any]) -> bool:
        """Check if plan has sequential scan."""
        if plan.get("Node Type") == "Seq Scan":
            # Only flag if it's on a reasonably large table
            if plan.get("Actual Rows", 0) > 1000:
                return True
                
        # Recursively check child plans
        for child in plan.get("Plans", []):
            if self._has_seq_scan(child):
                return True
                
        return False
        
    def _has_expensive_sort(self, plan: Dict[str, Any]) -> bool:
        """Check if plan has expensive sort."""
        if plan.get("Node Type") == "Sort":
            if plan.get("Actual Rows", 0) > 10000:
                return True
                
        for child in plan.get("Plans", []):
            if self._has_expensive_sort(child):
                return True
                
        return False
        
    def _has_expensive_nested_loop(self, plan: Dict[str, Any]) -> bool:
        """Check if plan has expensive nested loop."""
        if plan.get("Node Type") == "Nested Loop":
            total_cost = plan.get("Total Cost", 0)
            if total_cost > 10000:
                return True
                
        for child in plan.get("Plans", []):
            if self._has_expensive_nested_loop(child):
                return True
                
        return False


class IndexAdvisor:
    """Suggest indexes based on query patterns."""
    
    def __init__(self):
        self.missing_index_queries: List[Dict[str, Any]] = []
        
    async def analyze_table_indexes(
        self,
        session: AsyncSession,
        table_name: str,
        schema: str = "public"
    ) -> Dict[str, Any]:
        """Analyze indexes for a table."""
        # Get existing indexes
        indexes_query = sa.text("""
            SELECT 
                indexname,
                indexdef,
                tablename,
                schemaname
            FROM pg_indexes
            WHERE schemaname = :schema
            AND tablename = :table
        """)
        
        result = await session.execute(
            indexes_query,
            {"schema": schema, "table": table_name}
        )
        existing_indexes = result.fetchall()
        
        # Get table size
        size_query = sa.text("""
            SELECT 
                pg_size_pretty(pg_total_relation_size(:full_table)) as total_size,
                pg_size_pretty(pg_relation_size(:full_table)) as table_size,
                pg_size_pretty(pg_indexes_size(:full_table)) as indexes_size
        """)
        
        full_table = f"{schema}.{table_name}"
        size_result = await session.execute(
            size_query,
            {"full_table": full_table}
        )
        size_info = size_result.fetchone()
        
        # Get index usage statistics
        usage_query = sa.text("""
            SELECT 
                schemaname,
                tablename,
                indexname,
                idx_scan,
                idx_tup_read,
                idx_tup_fetch
            FROM pg_stat_user_indexes
            WHERE schemaname = :schema
            AND tablename = :table
            ORDER BY idx_scan DESC
        """)
        
        usage_result = await session.execute(
            usage_query,
            {"schema": schema, "table": table_name}
        )
        usage_stats = usage_result.fetchall()
        
        return {
            "table": table_name,
            "schema": schema,
            "size": {
                "total": size_info.total_size if size_info else "N/A",
                "table": size_info.table_size if size_info else "N/A",
                "indexes": size_info.indexes_size if size_info else "N/A"
            },
            "indexes": [
                {
                    "name": idx.indexname,
                    "definition": idx.indexdef
                }
                for idx in existing_indexes
            ],
            "usage": [
                {
                    "index": stat.indexname,
                    "scans": stat.idx_scan,
                    "tuples_read": stat.idx_tup_read,
                    "tuples_fetched": stat.idx_tup_fetch
                }
                for stat in usage_stats
            ]
        }
        
    async def suggest_missing_indexes(
        self,
        session: AsyncSession,
        min_occurrences: int = 5
    ) -> List[Dict[str, Any]]:
        """Suggest missing indexes based on query patterns."""
        # Query to find missing indexes from pg_stat_user_tables
        missing_indexes_query = sa.text("""
            SELECT 
                schemaname,
                tablename,
                seq_scan,
                seq_tup_read,
                idx_scan,
                n_tup_ins + n_tup_upd + n_tup_del as write_activity
            FROM pg_stat_user_tables
            WHERE seq_scan > :min_scans
            AND seq_scan > idx_scan
            ORDER BY seq_tup_read DESC
            LIMIT 20
        """)
        
        result = await session.execute(
            missing_indexes_query,
            {"min_scans": min_occurrences}
        )
        
        suggestions = []
        for row in result:
            if row.seq_tup_read > 10000:  # Only suggest for tables with significant reads
                suggestions.append({
                    "table": f"{row.schemaname}.{row.tablename}",
                    "reason": f"High sequential scans ({row.seq_scan}) vs index scans ({row.idx_scan})",
                    "impact": "high" if row.seq_tup_read > 100000 else "medium",
                    "seq_scans": row.seq_scan,
                    "tuples_read": row.seq_tup_read,
                    "write_activity": row.write_activity
                })
                
        return suggestions


# Global query analyzer instance
query_analyzer = QueryPerformanceAnalyzer()


# Middleware for automatic query monitoring
class QueryMonitoringMiddleware:
    """SQLAlchemy event listener for query monitoring."""
    
    def __init__(self, analyzer: QueryPerformanceAnalyzer):
        self.analyzer = analyzer
        
    def register(self, engine):
        """Register event listeners."""
        from sqlalchemy import event
        
        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            context._query_start_time = time.time()
            
        @event.listens_for(engine.sync_engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            execution_time = time.time() - context._query_start_time
            self.analyzer.log_query_execution(statement, execution_time)