"""
Advanced cache performance monitoring and analytics system.

This module provides comprehensive monitoring, analysis, and reporting for the
intelligent caching system including performance metrics, optimization recommendations,
and real-time dashboard capabilities.
"""

import asyncio
import json
import logging
import threading
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from statistics import mean
from typing import Any

logger = logging.getLogger(__name__)


class CacheEventType(Enum):
    """Types of cache events for analytics tracking."""

    HIT = "hit"
    MISS = "miss"
    EVICTION = "eviction"
    INVALIDATION = "invalidation"
    REFRESH = "refresh"
    ERROR = "error"
    MEMORY_WARNING = "memory_warning"


class AlertSeverity(Enum):
    """Alert severity levels for cache performance issues."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CacheEvent:
    """Individual cache event for detailed tracking."""

    cache_name: str
    event_type: CacheEventType
    key: str
    timestamp: datetime
    response_time_ms: float | None = None
    data_size_bytes: int | None = None
    ttl_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CachePerformanceSnapshot:
    """Point-in-time performance snapshot of a cache."""

    cache_name: str
    timestamp: datetime
    hit_rate: float
    miss_rate: float
    total_requests: int
    average_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    memory_usage_mb: float
    entry_count: int
    eviction_count: int
    error_count: int


@dataclass
class CacheAlert:
    """Cache performance alert."""

    cache_name: str
    alert_type: str
    severity: AlertSeverity
    message: str
    timestamp: datetime
    metrics: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False


class CacheAnalytics:
    """Advanced cache analytics and monitoring system."""

    def __init__(
        self,
        retention_hours: int = 24,
        alert_thresholds: dict[str, float] | None = None,
    ):
        self.retention_hours = retention_hours
        self.alert_thresholds = alert_thresholds or self._default_alert_thresholds()

        # Event storage
        self._events: deque = deque(maxlen=10000)  # Rolling window of events
        self._events_lock = threading.Lock()

        # Performance snapshots by cache
        self._snapshots: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=1440)
        )  # 24h of minute snapshots
        self._snapshots_lock = threading.Lock()

        # Real-time metrics tracking
        self._metrics_by_cache: dict[str, dict[str, Any]] = defaultdict(dict)
        self._response_times: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._metrics_lock = threading.Lock()

        # Alert system
        self._alerts: deque = deque(maxlen=1000)
        self._alert_callbacks: list[Callable[[CacheAlert], None]] = []
        self._alerts_lock = threading.Lock()

        # Background tasks
        self._cleanup_task: asyncio.Task | None = None
        self._monitoring_task: asyncio.Task | None = None
        self._running = False

    def _default_alert_thresholds(self) -> dict[str, float]:
        """Default alert thresholds for cache performance monitoring."""
        return {
            "hit_rate_low": 0.7,  # Alert if hit rate drops below 70%
            "response_time_high_ms": 50.0,  # Alert if avg response time > 50ms
            "error_rate_high": 0.05,  # Alert if error rate > 5%
            "memory_usage_high_mb": 500.0,  # Alert if memory usage > 500MB
            "eviction_rate_high": 0.1,  # Alert if eviction rate > 10%
        }

    async def start_monitoring(self):
        """Start background monitoring tasks."""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_old_data())
        self._monitoring_task = asyncio.create_task(self._continuous_monitoring())

        logger.info("Cache analytics monitoring started")

    async def stop_monitoring(self):
        """Stop background monitoring tasks."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Cache analytics monitoring stopped")

    def record_event(self, event: CacheEvent):
        """Record a cache event for analytics tracking."""
        with self._events_lock:
            self._events.append(event)

        # Update real-time metrics
        with self._metrics_lock:
            cache_metrics = self._metrics_by_cache[event.cache_name]

            # Update counters
            cache_metrics[f"{event.event_type.value}_count"] = (
                cache_metrics.get(f"{event.event_type.value}_count", 0) + 1
            )
            cache_metrics["total_requests"] = cache_metrics.get("total_requests", 0) + 1

            # Track response times
            if event.response_time_ms is not None:
                self._response_times[event.cache_name].append(event.response_time_ms)

    def record_cache_hit(
        self,
        cache_name: str,
        key: str,
        response_time_ms: float,
        data_size_bytes: int | None = None,
    ):
        """Record a cache hit event."""
        event = CacheEvent(
            cache_name=cache_name,
            event_type=CacheEventType.HIT,
            key=key,
            timestamp=datetime.now(),
            response_time_ms=response_time_ms,
            data_size_bytes=data_size_bytes,
        )
        self.record_event(event)

    def record_cache_miss(self, cache_name: str, key: str, response_time_ms: float):
        """Record a cache miss event."""
        event = CacheEvent(
            cache_name=cache_name,
            event_type=CacheEventType.MISS,
            key=key,
            timestamp=datetime.now(),
            response_time_ms=response_time_ms,
        )
        self.record_event(event)

    def record_cache_error(
        self, cache_name: str, key: str, error_details: dict[str, Any]
    ):
        """Record a cache error event."""
        event = CacheEvent(
            cache_name=cache_name,
            event_type=CacheEventType.ERROR,
            key=key,
            timestamp=datetime.now(),
            metadata=error_details,
        )
        self.record_event(event)

    def get_cache_performance(
        self, cache_name: str, time_window_minutes: int = 60
    ) -> dict[str, Any]:
        """Get comprehensive performance metrics for a specific cache."""
        cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)

        # Filter events for the specified cache and time window
        relevant_events = [
            event
            for event in self._events
            if event.cache_name == cache_name and event.timestamp >= cutoff_time
        ]

        if not relevant_events:
            return {
                "cache_name": cache_name,
                "time_window_minutes": time_window_minutes,
                "no_data": True,
            }

        # Calculate metrics
        hit_events = [e for e in relevant_events if e.event_type == CacheEventType.HIT]
        miss_events = [
            e for e in relevant_events if e.event_type == CacheEventType.MISS
        ]
        error_events = [
            e for e in relevant_events if e.event_type == CacheEventType.ERROR
        ]
        eviction_events = [
            e for e in relevant_events if e.event_type == CacheEventType.EVICTION
        ]

        total_requests = len(hit_events) + len(miss_events)
        hit_rate = len(hit_events) / total_requests if total_requests > 0 else 0.0
        miss_rate = len(miss_events) / total_requests if total_requests > 0 else 0.0
        error_rate = (
            len(error_events) / len(relevant_events) if relevant_events else 0.0
        )

        # Response time statistics
        response_times = [
            e.response_time_ms
            for e in relevant_events
            if e.response_time_ms is not None
        ]
        avg_response_time = mean(response_times) if response_times else 0.0
        p95_response_time = (
            self._calculate_percentile(response_times, 95) if response_times else 0.0
        )
        p99_response_time = (
            self._calculate_percentile(response_times, 99) if response_times else 0.0
        )

        # Data size statistics
        data_sizes = [
            e.data_size_bytes for e in hit_events if e.data_size_bytes is not None
        ]
        avg_data_size = mean(data_sizes) if data_sizes else 0.0
        total_data_served = sum(data_sizes) if data_sizes else 0.0

        return {
            "cache_name": cache_name,
            "time_window_minutes": time_window_minutes,
            "timestamp": datetime.now().isoformat(),
            "requests": {
                "total": total_requests,
                "hits": len(hit_events),
                "misses": len(miss_events),
                "errors": len(error_events),
                "evictions": len(eviction_events),
            },
            "rates": {
                "hit_rate": hit_rate,
                "miss_rate": miss_rate,
                "error_rate": error_rate,
            },
            "response_times_ms": {
                "average": avg_response_time,
                "p95": p95_response_time,
                "p99": p99_response_time,
                "min": min(response_times) if response_times else 0.0,
                "max": max(response_times) if response_times else 0.0,
            },
            "data": {
                "average_size_bytes": avg_data_size,
                "total_served_bytes": total_data_served,
                "cache_efficiency": (
                    hit_rate * total_data_served if total_data_served > 0 else 0.0
                ),
            },
            "health_score": self._calculate_health_score(
                hit_rate, avg_response_time, error_rate
            ),
        }

    def get_all_caches_summary(self, time_window_minutes: int = 60) -> dict[str, Any]:
        """Get performance summary for all monitored caches."""
        cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)

        # Get all cache names from recent events
        cache_names = {
            event.cache_name for event in self._events if event.timestamp >= cutoff_time
        }

        cache_summaries = {}
        total_requests = 0
        total_hits = 0
        total_errors = 0

        for cache_name in cache_names:
            performance = self.get_cache_performance(cache_name, time_window_minutes)
            cache_summaries[cache_name] = performance

            if not performance.get("no_data", False):
                total_requests += performance["requests"]["total"]
                total_hits += performance["requests"]["hits"]
                total_errors += performance["requests"]["errors"]

        overall_hit_rate = total_hits / total_requests if total_requests > 0 else 0.0
        overall_error_rate = (
            total_errors / (total_requests + total_errors)
            if (total_requests + total_errors) > 0
            else 0.0
        )

        return {
            "timestamp": datetime.now().isoformat(),
            "time_window_minutes": time_window_minutes,
            "overall_metrics": {
                "total_requests": total_requests,
                "overall_hit_rate": overall_hit_rate,
                "overall_error_rate": overall_error_rate,
                "active_caches": len(cache_names),
            },
            "cache_details": cache_summaries,
            "recommendations": self._generate_optimization_recommendations(
                cache_summaries
            ),
        }

    def get_active_alerts(
        self, severity_filter: AlertSeverity | None = None
    ) -> list[CacheAlert]:
        """Get currently active cache alerts."""
        with self._alerts_lock:
            alerts = [alert for alert in self._alerts if not alert.resolved]

            if severity_filter:
                alerts = [
                    alert for alert in alerts if alert.severity == severity_filter
                ]

            return sorted(alerts, key=lambda x: x.timestamp, reverse=True)

    def add_alert_callback(self, callback: Callable[[CacheAlert], None]):
        """Add a callback function to be called when new alerts are generated."""
        self._alert_callbacks.append(callback)

    def _calculate_percentile(self, data: list[float], percentile: int) -> float:
        """Calculate the specified percentile of a list of values."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]

    def _calculate_health_score(
        self, hit_rate: float, avg_response_time: float, error_rate: float
    ) -> float:
        """Calculate an overall health score (0-100) for cache performance."""
        # Hit rate component (0-40 points)
        hit_score = min(40, hit_rate * 40)

        # Response time component (0-40 points)
        response_score = max(
            0, 40 - (avg_response_time / 10)
        )  # Penalize high response times

        # Error rate component (0-20 points)
        error_score = max(0, 20 - (error_rate * 200))  # Heavy penalty for errors

        return min(100, hit_score + response_score + error_score)

    def _generate_optimization_recommendations(
        self, cache_summaries: dict[str, Any]
    ) -> list[str]:
        """Generate optimization recommendations based on cache performance."""
        recommendations = []

        for cache_name, performance in cache_summaries.items():
            if performance.get("no_data", False):
                continue

            hit_rate = performance["rates"]["hit_rate"]
            avg_response_time = performance["response_times_ms"]["average"]
            error_rate = performance["rates"]["error_rate"]

            # Low hit rate recommendations
            if hit_rate < 0.7:
                recommendations.append(
                    f"{cache_name}: Consider increasing TTL or cache size (hit rate: {hit_rate:.2%})"
                )

            # High response time recommendations
            if avg_response_time > 20:
                recommendations.append(
                    f"{cache_name}: Consider optimizing cache lookup or data serialization (avg response: {avg_response_time:.1f}ms)"
                )

            # High error rate recommendations
            if error_rate > 0.02:
                recommendations.append(
                    f"{cache_name}: Investigate cache errors and improve error handling (error rate: {error_rate:.2%})"
                )

        return recommendations

    async def _continuous_monitoring(self):
        """Continuous monitoring task that checks for performance issues and generates alerts."""
        while self._running:
            try:
                await self._check_performance_thresholds()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in continuous monitoring: {e}")
                await asyncio.sleep(60)

    async def _check_performance_thresholds(self):
        """Check performance thresholds and generate alerts if needed."""
        cache_names = {event.cache_name for event in self._events}

        for cache_name in cache_names:
            performance = self.get_cache_performance(
                cache_name, 10
            )  # Check last 10 minutes

            if performance.get("no_data", False):
                continue

            # Check hit rate
            hit_rate = performance["rates"]["hit_rate"]
            if hit_rate < self.alert_thresholds["hit_rate_low"]:
                await self._create_alert(
                    cache_name,
                    "low_hit_rate",
                    AlertSeverity.HIGH,
                    f"Hit rate dropped to {hit_rate:.2%} (threshold: {self.alert_thresholds['hit_rate_low']:.2%})",
                    {"hit_rate": hit_rate},
                )

            # Check response time
            avg_response_time = performance["response_times_ms"]["average"]
            if avg_response_time > self.alert_thresholds["response_time_high_ms"]:
                await self._create_alert(
                    cache_name,
                    "high_response_time",
                    AlertSeverity.MEDIUM,
                    f"Average response time: {avg_response_time:.1f}ms (threshold: {self.alert_thresholds['response_time_high_ms']}ms)",
                    {"avg_response_time_ms": avg_response_time},
                )

            # Check error rate
            error_rate = performance["rates"]["error_rate"]
            if error_rate > self.alert_thresholds["error_rate_high"]:
                await self._create_alert(
                    cache_name,
                    "high_error_rate",
                    AlertSeverity.CRITICAL,
                    f"Error rate: {error_rate:.2%} (threshold: {self.alert_thresholds['error_rate_high']:.2%})",
                    {"error_rate": error_rate},
                )

    async def _create_alert(
        self,
        cache_name: str,
        alert_type: str,
        severity: AlertSeverity,
        message: str,
        metrics: dict[str, Any],
    ):
        """Create and process a new alert."""
        alert = CacheAlert(
            cache_name=cache_name,
            alert_type=alert_type,
            severity=severity,
            message=message,
            timestamp=datetime.now(),
            metrics=metrics,
        )

        with self._alerts_lock:
            self._alerts.append(alert)

        # Execute alert callbacks
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Error executing alert callback: {e}")

        logger.warning(
            f"Cache alert [{severity.value.upper()}] {cache_name}: {message}"
        )

    async def _cleanup_old_data(self):
        """Clean up old events and snapshots beyond retention period."""
        while self._running:
            try:
                cutoff_time = datetime.now() - timedelta(hours=self.retention_hours)

                # Clean up old events
                with self._events_lock:
                    # Convert deque to list, filter, and recreate deque
                    filtered_events = [
                        event
                        for event in self._events
                        if event.timestamp >= cutoff_time
                    ]
                    self._events.clear()
                    self._events.extend(filtered_events)

                # Clean up old snapshots
                with self._snapshots_lock:
                    for cache_name in self._snapshots:
                        filtered_snapshots = [
                            snapshot
                            for snapshot in self._snapshots[cache_name]
                            if snapshot.timestamp >= cutoff_time
                        ]
                        self._snapshots[cache_name].clear()
                        self._snapshots[cache_name].extend(filtered_snapshots)

                await asyncio.sleep(3600)  # Clean up every hour
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(3600)

    def export_performance_report(
        self, output_file: str, time_window_hours: int = 24
    ) -> dict[str, Any]:
        """Export a comprehensive performance report to file."""
        summary = self.get_all_caches_summary(time_window_hours * 60)

        report = {
            "report_metadata": {
                "generated_at": datetime.now().isoformat(),
                "time_window_hours": time_window_hours,
                "total_events": len(self._events),
            },
            "performance_summary": summary,
            "alerts_summary": {
                "active_alerts": len(self.get_active_alerts()),
                "critical_alerts": len(self.get_active_alerts(AlertSeverity.CRITICAL)),
                "high_alerts": len(self.get_active_alerts(AlertSeverity.HIGH)),
            },
        }

        try:
            with open(output_file, "w") as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"Performance report exported to {output_file}")
        except Exception as e:
            logger.error(f"Failed to export performance report: {e}")

        return report


# Global cache analytics instance
_cache_analytics: CacheAnalytics | None = None


def get_cache_analytics() -> CacheAnalytics:
    """Get the global cache analytics instance."""
    global _cache_analytics
    if _cache_analytics is None:
        _cache_analytics = CacheAnalytics()
    return _cache_analytics


async def initialize_cache_analytics(
    retention_hours: int = 24, alert_thresholds: dict[str, float] | None = None
):
    """Initialize and start the global cache analytics system."""
    global _cache_analytics
    _cache_analytics = CacheAnalytics(retention_hours, alert_thresholds)
    await _cache_analytics.start_monitoring()
    logger.info("Cache analytics system initialized and monitoring started")


async def shutdown_cache_analytics():
    """Shutdown the global cache analytics system."""
    global _cache_analytics
    if _cache_analytics:
        await _cache_analytics.stop_monitoring()
        _cache_analytics = None
    logger.info("Cache analytics system shutdown complete")
