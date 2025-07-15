"""Application metrics collection and monitoring."""

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from threading import Lock

from app.services.cache import cache_service


@dataclass
class MetricPoint:
    """Single metric data point."""
    timestamp: datetime
    value: float
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSummary:
    """Metric summary statistics."""
    name: str
    count: int
    sum_value: float
    min_value: float
    max_value: float
    avg_value: float
    last_value: float
    last_updated: datetime


class MetricsCollector:
    """In-memory metrics collector with Redis persistence."""
    
    def __init__(self, max_points_per_metric: int = 1000):
        self.max_points_per_metric = max_points_per_metric
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_points_per_metric))
        self.counters: Dict[str, float] = defaultdict(float)
        self.gauges: Dict[str, float] = defaultdict(float)
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        self.lock = Lock()
        
    def counter(self, name: str, value: float = 1, tags: Optional[Dict[str, str]] = None):
        """Increment a counter metric."""
        tags = tags or {}
        metric_key = self._make_key(name, tags)
        
        with self.lock:
            self.counters[metric_key] += value
            self.metrics[metric_key].append(MetricPoint(
                timestamp=datetime.utcnow(),
                value=self.counters[metric_key],
                tags=tags
            ))
            
    def gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Set a gauge metric value."""
        tags = tags or {}
        metric_key = self._make_key(name, tags)
        
        with self.lock:
            self.gauges[metric_key] = value
            self.metrics[metric_key].append(MetricPoint(
                timestamp=datetime.utcnow(),
                value=value,
                tags=tags
            ))
            
    def histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Add value to histogram metric."""
        tags = tags or {}
        metric_key = self._make_key(name, tags)
        
        with self.lock:
            self.histograms[metric_key].append(value)
            # Keep only recent values (last 1000)
            if len(self.histograms[metric_key]) > 1000:
                self.histograms[metric_key] = self.histograms[metric_key][-1000:]
                
            self.metrics[metric_key].append(MetricPoint(
                timestamp=datetime.utcnow(),
                value=value,
                tags=tags
            ))
            
    def timing(self, name: str, duration: float, tags: Optional[Dict[str, str]] = None):
        """Record timing metric (alias for histogram)."""
        self.histogram(name, duration, tags)
        
    def get_metric_summary(self, name: str, tags: Optional[Dict[str, str]] = None) -> Optional[MetricSummary]:
        """Get summary statistics for a metric."""
        tags = tags or {}
        metric_key = self._make_key(name, tags)
        
        with self.lock:
            points = list(self.metrics[metric_key])
            
        if not points:
            return None
            
        values = [p.value for p in points]
        return MetricSummary(
            name=name,
            count=len(values),
            sum_value=sum(values),
            min_value=min(values),
            max_value=max(values),
            avg_value=sum(values) / len(values),
            last_value=values[-1],
            last_updated=points[-1].timestamp
        )
        
    def get_histogram_percentiles(
        self, 
        name: str, 
        percentiles: List[float] = [50.0, 90.0, 95.0, 99.0],
        tags: Optional[Dict[str, str]] = None
    ) -> Dict[float, float]:
        """Get percentile values for histogram metric."""
        tags = tags or {}
        metric_key = self._make_key(name, tags)
        
        with self.lock:
            values = self.histograms[metric_key].copy()
            
        if not values:
            return {}
            
        values.sort()
        result = {}
        
        for p in percentiles:
            if p < 0 or p > 100:
                continue
            index = int((p / 100.0) * (len(values) - 1))
            result[p] = values[index]
            
        return result
        
    def get_all_metrics(self) -> Dict[str, MetricSummary]:
        """Get summaries for all metrics."""
        results = {}
        
        with self.lock:
            metric_keys = list(self.metrics.keys())
            
        for key in metric_keys:
            name, tags = self._parse_key(key)
            summary = self.get_metric_summary(name, tags)
            if summary:
                results[key] = summary
                
        return results
        
    def reset_metric(self, name: str, tags: Optional[Dict[str, str]] = None):
        """Reset a specific metric."""
        tags = tags or {}
        metric_key = self._make_key(name, tags)
        
        with self.lock:
            if metric_key in self.metrics:
                self.metrics[metric_key].clear()
            if metric_key in self.counters:
                self.counters[metric_key] = 0
            if metric_key in self.gauges:
                del self.gauges[metric_key]
            if metric_key in self.histograms:
                self.histograms[metric_key].clear()
                
    def reset_all_metrics(self):
        """Reset all metrics."""
        with self.lock:
            self.metrics.clear()
            self.counters.clear()
            self.gauges.clear()
            self.histograms.clear()
            
    async def persist_to_redis(self):
        """Persist metrics to Redis for persistence across restarts."""
        try:
            await cache_service.connect()
            
            # Persist counter values
            if self.counters:
                counter_data = {f"metrics:counter:{k}": v for k, v in self.counters.items()}
                await cache_service.set_many(counter_data, expire=timedelta(hours=24))
                
            # Persist gauge values
            if self.gauges:
                gauge_data = {f"metrics:gauge:{k}": v for k, v in self.gauges.items()}
                await cache_service.set_many(gauge_data, expire=timedelta(hours=24))
                
        except Exception as e:
            # Don't fail the application if metrics persistence fails
            pass
            
    async def restore_from_redis(self):
        """Restore persisted metrics from Redis."""
        try:
            await cache_service.connect()
            
            # Restore counters
            counter_keys = []
            cursor = 0
            while True:
                cursor, keys = await cache_service.client.scan(
                    cursor, match="metrics:counter:*", count=100
                )
                counter_keys.extend(keys)
                if cursor == 0:
                    break
                    
            if counter_keys:
                counter_data = await cache_service.get_many(counter_keys)
                for key, value in counter_data.items():
                    metric_key = key.replace("metrics:counter:", "")
                    self.counters[metric_key] = float(value)
                    
            # Restore gauges
            gauge_keys = []
            cursor = 0
            while True:
                cursor, keys = await cache_service.client.scan(
                    cursor, match="metrics:gauge:*", count=100
                )
                gauge_keys.extend(keys)
                if cursor == 0:
                    break
                    
            if gauge_keys:
                gauge_data = await cache_service.get_many(gauge_keys)
                for key, value in gauge_data.items():
                    metric_key = key.replace("metrics:gauge:", "")
                    self.gauges[metric_key] = float(value)
                    
        except Exception as e:
            # Don't fail the application if metrics restoration fails
            pass
            
    def _make_key(self, name: str, tags: Dict[str, str]) -> str:
        """Generate metric key from name and tags."""
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}[{tag_str}]"
        
    def _parse_key(self, key: str) -> tuple:
        """Parse metric key back to name and tags."""
        if "[" not in key:
            return key, {}
            
        name, tag_part = key.split("[", 1)
        tag_part = tag_part.rstrip("]")
        
        tags = {}
        if tag_part:
            for tag in tag_part.split(","):
                if "=" in tag:
                    k, v = tag.split("=", 1)
                    tags[k] = v
                    
        return name, tags


class PerformanceTimer:
    """Context manager for timing operations."""
    
    def __init__(self, metrics_collector: MetricsCollector, metric_name: str, tags: Optional[Dict[str, str]] = None):
        self.metrics_collector = metrics_collector
        self.metric_name = metric_name
        self.tags = tags or {}
        self.start_time = None
        
    def __enter__(self):
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time
            self.metrics_collector.timing(self.metric_name, duration, self.tags)


class SystemMetricsCollector:
    """Collect system-wide metrics."""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self._monitoring = False
        self._task = None
        
    async def start_monitoring(self, interval: int = 60):
        """Start collecting system metrics."""
        self._monitoring = True
        self._task = asyncio.create_task(self._collect_loop(interval))
        
    async def stop_monitoring(self):
        """Stop collecting system metrics."""
        self._monitoring = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
                
    async def _collect_loop(self, interval: int):
        """Main collection loop."""
        while self._monitoring:
            try:
                await self._collect_system_metrics()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error but continue monitoring
                await asyncio.sleep(interval)
                
    async def _collect_system_metrics(self):
        """Collect various system metrics."""
        import psutil
        
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        self.metrics_collector.gauge("system.cpu.percent", cpu_percent)
        
        # Memory metrics
        memory = psutil.virtual_memory()
        self.metrics_collector.gauge("system.memory.percent", memory.percent)
        self.metrics_collector.gauge("system.memory.used_bytes", memory.used)
        self.metrics_collector.gauge("system.memory.available_bytes", memory.available)
        
        # Disk metrics
        disk = psutil.disk_usage('/')
        self.metrics_collector.gauge("system.disk.percent", disk.percent)
        self.metrics_collector.gauge("system.disk.used_bytes", disk.used)
        self.metrics_collector.gauge("system.disk.free_bytes", disk.free)
        
        # Network metrics (if available)
        try:
            network = psutil.net_io_counters()
            self.metrics_collector.counter("system.network.bytes_sent", network.bytes_sent)
            self.metrics_collector.counter("system.network.bytes_recv", network.bytes_recv)
            self.metrics_collector.counter("system.network.packets_sent", network.packets_sent)
            self.metrics_collector.counter("system.network.packets_recv", network.packets_recv)
        except Exception:
            pass


# Global metrics collector instance
metrics_collector = MetricsCollector()


# Convenience functions
def counter(name: str, value: float = 1, tags: Optional[Dict[str, str]] = None):
    """Increment a counter metric."""
    metrics_collector.counter(name, value, tags)


def gauge(name: str, value: float, tags: Optional[Dict[str, str]] = None):
    """Set a gauge metric value."""
    metrics_collector.gauge(name, value, tags)


def histogram(name: str, value: float, tags: Optional[Dict[str, str]] = None):
    """Add value to histogram metric."""
    metrics_collector.histogram(name, value, tags)


def timing(name: str, duration: float, tags: Optional[Dict[str, str]] = None):
    """Record timing metric."""
    metrics_collector.timing(name, duration, tags)


def timer(name: str, tags: Optional[Dict[str, str]] = None) -> PerformanceTimer:
    """Create a performance timer context manager."""
    return PerformanceTimer(metrics_collector, name, tags)


# Decorator for timing function calls
def timed(metric_name: Optional[str] = None, tags: Optional[Dict[str, str]] = None):
    """Decorator to time function execution."""
    def decorator(func):
        import functools
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            name = metric_name or f"function.{func.__name__}.duration"
            with timer(name, tags):
                return await func(*args, **kwargs)
                
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            name = metric_name or f"function.{func.__name__}.duration"
            with timer(name, tags):
                return func(*args, **kwargs)
                
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator