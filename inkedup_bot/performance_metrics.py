"""
Comprehensive performance metrics tracking for all major components.

This module provides detailed performance instrumentation including:
- Latency monitoring with percentile analysis
- Throughput measurement with time window analysis
- Error rate tracking with trend detection
- Signal processing speed metrics
- Order execution latency tracking
- Database query performance monitoring
"""

import asyncio
import logging
import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of performance metrics."""

    LATENCY = "latency"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    COUNTER = "counter"
    GAUGE = "gauge"


class ComponentType(Enum):
    """Major system components for performance tracking."""

    SIGNAL_PROCESSOR = "signal_processor"
    ORDER_CLIENT = "order_client"
    DATABASE = "database"
    WEBSOCKET = "websocket"
    STRATEGY = "strategy"
    MARKET_DATA = "market_data"
    RISK_MANAGER = "risk_manager"


@dataclass
class PerformanceMetric:
    """Individual performance metric with timing and metadata."""

    component: ComponentType
    operation: str
    metric_type: MetricType
    value: float
    timestamp: float
    tags: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


@dataclass
class LatencyStats:
    """Latency statistics with percentile analysis."""

    component: ComponentType
    operation: str
    count: int
    min_latency: float
    max_latency: float
    mean_latency: float
    median_latency: float
    p90_latency: float
    p95_latency: float
    p99_latency: float
    std_deviation: float
    total_time: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component.value,
            "operation": self.operation,
            "count": self.count,
            "min_ms": self.min_latency,
            "max_ms": self.max_latency,
            "mean_ms": self.mean_latency,
            "median_ms": self.median_latency,
            "p90_ms": self.p90_latency,
            "p95_ms": self.p95_latency,
            "p99_ms": self.p99_latency,
            "std_dev_ms": self.std_deviation,
            "total_time_ms": self.total_time,
        }


@dataclass
class ThroughputStats:
    """Throughput statistics with time window analysis."""

    component: ComponentType
    operation: str
    total_events: int
    events_per_second: float
    events_1min: int
    events_5min: int
    events_15min: int
    peak_throughput: float
    avg_throughput: float
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component.value,
            "operation": self.operation,
            "total_events": self.total_events,
            "events_per_second": self.events_per_second,
            "events_1min": self.events_1min,
            "events_5min": self.events_5min,
            "events_15min": self.events_15min,
            "peak_throughput": self.peak_throughput,
            "avg_throughput": self.avg_throughput,
            "timestamp": self.timestamp,
        }


class PerformanceTimer:
    """Context manager for measuring operation latency."""

    def __init__(
        self,
        metrics_tracker,
        component: ComponentType,
        operation: str,
        tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.metrics_tracker = metrics_tracker
        self.component = component
        self.operation = operation
        self.tags = tags or {}
        self.metadata = metadata or {}
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        latency_ms = (self.end_time - self.start_time) * 1000

        # Record success/failure based on exception
        success = exc_type is None
        if not success:
            self.tags["error"] = exc_type.__name__ if exc_type else "unknown"

        # Record the performance metric
        self.metrics_tracker.record_latency(
            self.component,
            self.operation,
            latency_ms,
            success=success,
            tags=self.tags,
            metadata=self.metadata,
        )

    def get_elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        if self.start_time is None:
            return 0.0
        current_time = self.end_time or time.time()
        return (current_time - self.start_time) * 1000


class PerformanceMetricsTracker:
    """Comprehensive performance metrics tracking system."""

    def __init__(self, retention_seconds: int = 3600):
        self.retention_seconds = retention_seconds
        self.lock = threading.RLock()

        # Raw metrics storage
        self.metrics: dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))

        # Aggregated statistics
        self.latency_stats: dict[str, LatencyStats] = {}
        self.throughput_stats: dict[str, ThroughputStats] = {}
        self.error_rates: dict[str, dict[str, float]] = defaultdict(dict)

        # Real-time tracking
        self.active_operations: dict[str, list[float]] = defaultdict(list)
        self.throughput_counters: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=1000)
        )

        # Cache for performance
        self._stats_cache: dict[str, tuple[float, dict]] = {}
        self._cache_ttl = 10.0  # 10 seconds

        logger.info("Performance metrics tracker initialized")

    def timer(
        self,
        component: ComponentType,
        operation: str,
        tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PerformanceTimer:
        """Create a performance timer context manager."""
        return PerformanceTimer(self, component, operation, tags, metadata)

    def record_latency(
        self,
        component: ComponentType,
        operation: str,
        latency_ms: float,
        success: bool = True,
        tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Record latency metric for an operation."""
        metric = PerformanceMetric(
            component=component,
            operation=operation,
            metric_type=MetricType.LATENCY,
            value=latency_ms,
            timestamp=time.time(),
            tags=tags or {},
            metadata=metadata or {},
        )

        # Add success/failure tag
        metric.tags["success"] = str(success)

        key = f"{component.value}:{operation}"

        with self.lock:
            self.metrics[key].append(metric)

            # Update real-time tracking
            self.active_operations[key].append(latency_ms)
            if len(self.active_operations[key]) > 100:
                self.active_operations[key] = self.active_operations[key][-100:]

            # Invalidate cache
            self._invalidate_cache(key)

    def record_throughput(
        self,
        component: ComponentType,
        operation: str,
        count: int = 1,
        tags: dict[str, str] | None = None,
    ):
        """Record throughput metric for an operation."""
        metric = PerformanceMetric(
            component=component,
            operation=operation,
            metric_type=MetricType.THROUGHPUT,
            value=count,
            timestamp=time.time(),
            tags=tags or {},
        )

        key = f"{component.value}:{operation}"

        with self.lock:
            self.metrics[key].append(metric)
            self.throughput_counters[key].append(time.time())

            # Clean old throughput data
            cutoff_time = time.time() - 900  # 15 minutes
            while (
                self.throughput_counters[key]
                and self.throughput_counters[key][0] < cutoff_time
            ):
                self.throughput_counters[key].popleft()

            self._invalidate_cache(key)

    def record_error(
        self,
        component: ComponentType,
        operation: str,
        error_type: str,
        tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Record error metric for an operation."""
        metric = PerformanceMetric(
            component=component,
            operation=operation,
            metric_type=MetricType.ERROR_RATE,
            value=1.0,
            timestamp=time.time(),
            tags=(tags or {}) | {"error_type": error_type},
            metadata=metadata or {},
        )

        key = f"{component.value}:{operation}"

        with self.lock:
            self.metrics[key].append(metric)
            self._invalidate_cache(key)

    def get_latency_stats(
        self,
        component: ComponentType,
        operation: str,
        window_seconds: int | None = None,
    ) -> LatencyStats | None:
        """Get latency statistics for a component operation."""
        key = f"{component.value}:{operation}"

        # Check cache
        if key in self._stats_cache:
            cached_time, cached_stats = self._stats_cache[key]
            if time.time() - cached_time < self._cache_ttl:
                return cached_stats.get("latency")

        with self.lock:
            latency_metrics = self._get_metrics_in_window(
                key, MetricType.LATENCY, window_seconds
            )

            if not latency_metrics:
                return None

            latencies = [m.value for m in latency_metrics]
            latencies.sort()

            stats = LatencyStats(
                component=component,
                operation=operation,
                count=len(latencies),
                min_latency=min(latencies),
                max_latency=max(latencies),
                mean_latency=statistics.mean(latencies),
                median_latency=statistics.median(latencies),
                p90_latency=self._percentile(latencies, 90),
                p95_latency=self._percentile(latencies, 95),
                p99_latency=self._percentile(latencies, 99),
                std_deviation=(
                    statistics.stdev(latencies) if len(latencies) > 1 else 0.0
                ),
                total_time=sum(latencies),
            )

            # Cache the result
            if key not in self._stats_cache:
                self._stats_cache[key] = (time.time(), {})
            self._stats_cache[key][1]["latency"] = stats

            return stats

    def get_throughput_stats(
        self, component: ComponentType, operation: str
    ) -> ThroughputStats | None:
        """Get throughput statistics for a component operation."""
        key = f"{component.value}:{operation}"

        with self.lock:
            current_time = time.time()

            # Count events in different time windows
            events_1min = len(
                [t for t in self.throughput_counters[key] if current_time - t <= 60]
            )
            events_5min = len(
                [t for t in self.throughput_counters[key] if current_time - t <= 300]
            )
            events_15min = len(
                [t for t in self.throughput_counters[key] if current_time - t <= 900]
            )

            total_events = len(self.throughput_counters[key])

            if total_events == 0:
                return None

            # Calculate throughput rates
            events_per_second = events_1min / 60.0 if events_1min > 0 else 0.0

            # Calculate peak and average throughput
            peak_throughput = 0.0
            avg_throughput = 0.0

            if len(self.throughput_counters[key]) > 1:
                time_span = current_time - self.throughput_counters[key][0]
                avg_throughput = total_events / max(time_span, 1.0)

                # Calculate peak throughput in 10-second windows
                for i in range(0, len(self.throughput_counters[key]), 10):
                    window_events = len(
                        [t for t in list(self.throughput_counters[key])[i : i + 10]]
                    )
                    window_throughput = window_events / 10.0
                    peak_throughput = max(peak_throughput, window_throughput)

            stats = ThroughputStats(
                component=component,
                operation=operation,
                total_events=total_events,
                events_per_second=events_per_second,
                events_1min=events_1min,
                events_5min=events_5min,
                events_15min=events_15min,
                peak_throughput=peak_throughput,
                avg_throughput=avg_throughput,
                timestamp=current_time,
            )

            return stats

    def get_error_rate(
        self, component: ComponentType, operation: str, window_seconds: int = 300
    ) -> dict[str, Any]:
        """Get error rate statistics for a component operation."""
        key = f"{component.value}:{operation}"

        with self.lock:
            # Get all metrics in window
            all_metrics = self._get_metrics_in_window(key, None, window_seconds)
            error_metrics = [
                m for m in all_metrics if m.metric_type == MetricType.ERROR_RATE
            ]
            latency_metrics = [
                m for m in all_metrics if m.metric_type == MetricType.LATENCY
            ]

            total_operations = len(latency_metrics)
            total_errors = len(error_metrics)

            error_rate = (
                (total_errors / total_operations * 100) if total_operations > 0 else 0.0
            )

            # Group errors by type
            error_types = defaultdict(int)
            for error_metric in error_metrics:
                error_type = error_metric.tags.get("error_type", "unknown")
                error_types[error_type] += 1

            # Calculate success rate
            success_rate = 100.0 - error_rate

            return {
                "component": component.value,
                "operation": operation,
                "error_rate_percent": error_rate,
                "success_rate_percent": success_rate,
                "total_operations": total_operations,
                "total_errors": total_errors,
                "error_types": dict(error_types),
                "window_seconds": window_seconds,
                "timestamp": time.time(),
            }

    def get_comprehensive_stats(
        self, component: ComponentType | None = None
    ) -> dict[str, Any]:
        """Get comprehensive performance statistics."""
        stats = {
            "timestamp": datetime.now().isoformat(),
            "components": {},
            "summary": {
                "total_operations": 0,
                "total_errors": 0,
                "avg_latency": 0.0,
                "total_throughput": 0.0,
            },
        }

        with self.lock:
            # Group metrics by component
            component_metrics = defaultdict(set)
            for key in self.metrics.keys():
                comp_str, operation = key.split(":", 1)
                comp = ComponentType(comp_str)
                if component is None or comp == component:
                    component_metrics[comp].add(operation)

            total_ops = 0
            total_errors = 0
            total_latency = 0.0
            total_throughput = 0.0

            for comp, operations in component_metrics.items():
                comp_stats = {
                    "operations": {},
                    "summary": {
                        "operations_count": len(operations),
                        "avg_latency": 0.0,
                        "total_throughput": 0.0,
                        "error_rate": 0.0,
                    },
                }

                comp_latencies = []
                comp_throughput = 0.0
                comp_errors = 0
                comp_ops = 0

                for operation in operations:
                    # Get latency stats
                    latency_stats = self.get_latency_stats(comp, operation)
                    throughput_stats = self.get_throughput_stats(comp, operation)
                    error_stats = self.get_error_rate(comp, operation)

                    op_stats = {
                        "latency": latency_stats.to_dict() if latency_stats else None,
                        "throughput": (
                            throughput_stats.to_dict() if throughput_stats else None
                        ),
                        "error_rate": error_stats,
                    }

                    comp_stats["operations"][operation] = op_stats

                    # Aggregate for component summary
                    if latency_stats:
                        comp_latencies.append(latency_stats.mean_latency)
                        total_latency += (
                            latency_stats.mean_latency * latency_stats.count
                        )
                        total_ops += latency_stats.count

                    if throughput_stats:
                        comp_throughput += throughput_stats.events_per_second
                        total_throughput += throughput_stats.events_per_second

                    comp_errors += error_stats.get("total_errors", 0)
                    comp_ops += error_stats.get("total_operations", 0)

                # Component summary
                comp_stats["summary"]["avg_latency"] = (
                    statistics.mean(comp_latencies) if comp_latencies else 0.0
                )
                comp_stats["summary"]["total_throughput"] = comp_throughput
                comp_stats["summary"]["error_rate"] = (
                    (comp_errors / comp_ops * 100) if comp_ops > 0 else 0.0
                )

                stats["components"][comp.value] = comp_stats
                total_errors += comp_errors

            # Overall summary
            stats["summary"]["total_operations"] = total_ops
            stats["summary"]["total_errors"] = total_errors
            stats["summary"]["avg_latency"] = (
                (total_latency / total_ops) if total_ops > 0 else 0.0
            )
            stats["summary"]["total_throughput"] = total_throughput

        return stats

    def get_real_time_stats(self) -> dict[str, Any]:
        """Get real-time performance statistics."""
        with self.lock:
            real_time_stats = {
                "timestamp": time.time(),
                "active_operations": {},
                "current_throughput": {},
                "recent_errors": {},
            }

            # Current active operations latency
            for key, latencies in self.active_operations.items():
                if latencies:
                    comp_op = key.split(":", 1)
                    real_time_stats["active_operations"][key] = {
                        "component": comp_op[0],
                        "operation": comp_op[1],
                        "current_latency_ms": latencies[-1],
                        "avg_latency_ms": statistics.mean(
                            latencies[-10:]
                        ),  # Last 10 operations
                        "active_count": len(latencies),
                    }

            # Current throughput rates
            current_time = time.time()
            for key, timestamps in self.throughput_counters.items():
                recent_count = len(
                    [t for t in timestamps if current_time - t <= 60]
                )  # Last minute
                comp_op = key.split(":", 1)
                real_time_stats["current_throughput"][key] = {
                    "component": comp_op[0],
                    "operation": comp_op[1],
                    "events_per_minute": recent_count,
                    "events_per_second": recent_count / 60.0,
                }

            return real_time_stats

    def cleanup_old_metrics(self):
        """Clean up old metrics based on retention policy."""
        cutoff_time = time.time() - self.retention_seconds

        with self.lock:
            for key in list(self.metrics.keys()):
                # Remove old metrics
                while (
                    self.metrics[key] and self.metrics[key][0].timestamp < cutoff_time
                ):
                    self.metrics[key].popleft()

                # Remove empty keys
                if not self.metrics[key]:
                    del self.metrics[key]

            # Clear cache
            self._stats_cache.clear()

            logger.debug("Cleaned up old performance metrics")

    def _get_metrics_in_window(
        self, key: str, metric_type: MetricType | None, window_seconds: int | None
    ) -> list[PerformanceMetric]:
        """Get metrics for a key within a time window."""
        if key not in self.metrics:
            return []

        current_time = time.time()
        cutoff_time = current_time - (window_seconds or self.retention_seconds)

        metrics = []
        for metric in self.metrics[key]:
            if metric.timestamp >= cutoff_time:
                if metric_type is None or metric.metric_type == metric_type:
                    metrics.append(metric)

        return metrics

    def _percentile(self, sorted_values: list[float], percentile: float) -> float:
        """Calculate percentile from sorted values."""
        if not sorted_values:
            return 0.0

        index = (percentile / 100.0) * (len(sorted_values) - 1)
        if index == int(index):
            return sorted_values[int(index)]
        else:
            lower = sorted_values[int(index)]
            upper = sorted_values[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))

    def _invalidate_cache(self, key: str):
        """Invalidate cache for a specific key."""
        if key in self._stats_cache:
            del self._stats_cache[key]


# Global performance tracker instance
_performance_tracker: PerformanceMetricsTracker | None = None


def get_performance_tracker() -> PerformanceMetricsTracker:
    """Get or create the global performance metrics tracker."""
    global _performance_tracker

    if _performance_tracker is None:
        _performance_tracker = PerformanceMetricsTracker()

    return _performance_tracker


def performance_timer(
    component: ComponentType,
    operation: str,
    tags: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> PerformanceTimer:
    """Convenience function to create a performance timer."""
    tracker = get_performance_tracker()
    return tracker.timer(component, operation, tags, metadata)


# Decorator for automatic performance tracking
def track_performance(
    component: ComponentType,
    operation: str | None = None,
    tags: dict[str, str] | None = None,
):
    """Decorator for automatic performance tracking."""

    def decorator(func):
        op_name = operation or func.__name__

        if asyncio.iscoroutinefunction(func):

            async def async_wrapper(*args, **kwargs):
                with performance_timer(component, op_name, tags) as timer:
                    try:
                        result = await func(*args, **kwargs)
                        # Record throughput on success
                        get_performance_tracker().record_throughput(
                            component, op_name, 1, tags
                        )
                        return result
                    except Exception as e:
                        get_performance_tracker().record_error(
                            component, op_name, type(e).__name__, tags
                        )
                        raise

            return async_wrapper
        else:

            def sync_wrapper(*args, **kwargs):
                with performance_timer(component, op_name, tags) as timer:
                    try:
                        result = func(*args, **kwargs)
                        # Record throughput on success
                        get_performance_tracker().record_throughput(
                            component, op_name, 1, tags
                        )
                        return result
                    except Exception as e:
                        get_performance_tracker().record_error(
                            component, op_name, type(e).__name__, tags
                        )
                        raise

            return sync_wrapper

    return decorator
