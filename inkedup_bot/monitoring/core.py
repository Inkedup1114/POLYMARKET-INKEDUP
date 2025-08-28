"""
Core monitoring infrastructure for the InkedUp Polymarket bot.

This module provides the foundational monitoring system that coordinates
health checks, metrics collection, and performance monitoring across all components.
"""

import asyncio
import logging
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MonitoringLevel(Enum):
    """Monitoring detail levels."""

    BASIC = "basic"
    DETAILED = "detailed"
    DEBUG = "debug"


@dataclass
class MonitoringConfig:
    """Configuration for the monitoring system."""

    # Health check intervals
    health_check_interval: float = 30.0
    component_health_timeout: float = 5.0

    # Metrics collection
    metrics_collection_interval: float = 10.0
    metrics_retention_hours: int = 24
    metrics_aggregation_window: float = 60.0

    # Performance monitoring
    performance_sampling_rate: float = 1.0
    latency_percentiles: list[float] = field(default_factory=lambda: [50, 90, 95, 99])

    # Alert thresholds
    error_rate_threshold: float = 0.05  # 5%
    response_time_threshold: float = 1.0  # 1 second
    memory_threshold_mb: int = 500
    cpu_threshold_percent: float = 80.0

    # Storage
    enable_persistent_metrics: bool = True
    monitoring_level: MonitoringLevel = MonitoringLevel.DETAILED


class MetricsCollector:
    """
    Centralized metrics collection and aggregation system.

    Handles collection, storage, and retrieval of metrics from all components
    with support for different metric types and time-series data.
    """

    def __init__(self, config: MonitoringConfig):
        self.config = config
        self.metrics: dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self.metric_metadata: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.last_cleanup = time.time()

        # Metric aggregators
        self.counters: dict[str, float] = defaultdict(float)
        self.gauges: dict[str, float] = {}
        self.histograms: dict[str, list[float]] = defaultdict(list)
        self.timers: dict[str, list[float]] = defaultdict(list)

        logger.info("Metrics collector initialized")

    def record_counter(
        self, name: str, value: float = 1.0, tags: dict[str, str] | None = None
    ):
        """Record a counter metric (monotonically increasing)."""
        with self.lock:
            metric_key = self._build_metric_key(name, tags)
            self.counters[metric_key] += value
            self._store_metric(metric_key, "counter", value, tags)

    def record_gauge(self, name: str, value: float, tags: dict[str, str] | None = None):
        """Record a gauge metric (current value)."""
        with self.lock:
            metric_key = self._build_metric_key(name, tags)
            self.gauges[metric_key] = value
            self._store_metric(metric_key, "gauge", value, tags)

    def record_histogram(
        self, name: str, value: float, tags: dict[str, str] | None = None
    ):
        """Record a histogram metric (distribution of values)."""
        with self.lock:
            metric_key = self._build_metric_key(name, tags)
            self.histograms[metric_key].append(value)
            self._store_metric(metric_key, "histogram", value, tags)

            # Keep histogram sizes manageable
            if len(self.histograms[metric_key]) > 1000:
                self.histograms[metric_key] = self.histograms[metric_key][-500:]

    def record_timer(
        self, name: str, duration: float, tags: dict[str, str] | None = None
    ):
        """Record a timer metric (duration measurements)."""
        with self.lock:
            metric_key = self._build_metric_key(name, tags)
            self.timers[metric_key].append(duration)
            self._store_metric(metric_key, "timer", duration, tags)

            # Keep timer sizes manageable
            if len(self.timers[metric_key]) > 1000:
                self.timers[metric_key] = self.timers[metric_key][-500:]

    def time_operation(self, name: str, tags: dict[str, str] | None = None):
        """Context manager for timing operations."""
        return TimingContext(self, name, tags)

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get a summary of all current metrics."""
        with self.lock:
            summary = {
                "timestamp": datetime.now().isoformat(),
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "histograms": {},
                "timers": {},
            }

            # Calculate histogram statistics
            for name, values in self.histograms.items():
                if values:
                    sorted_values = sorted(values)
                    summary["histograms"][name] = {
                        "count": len(values),
                        "min": min(values),
                        "max": max(values),
                        "mean": sum(values) / len(values),
                        "percentiles": {
                            p: self._percentile(sorted_values, p)
                            for p in self.config.latency_percentiles
                        },
                    }

            # Calculate timer statistics
            for name, durations in self.timers.items():
                if durations:
                    sorted_durations = sorted(durations)
                    summary["timers"][name] = {
                        "count": len(durations),
                        "min": min(durations),
                        "max": max(durations),
                        "mean": sum(durations) / len(durations),
                        "percentiles": {
                            p: self._percentile(sorted_durations, p)
                            for p in self.config.latency_percentiles
                        },
                    }

            return summary

    def get_metric_history(self, name: str, minutes: int = 60) -> list[dict[str, Any]]:
        """Get historical data for a specific metric."""
        with self.lock:
            cutoff_time = time.time() - (minutes * 60)
            history = []

            if name in self.metrics:
                for entry in self.metrics[name]:
                    if entry["timestamp"] >= cutoff_time:
                        history.append(entry)

            return sorted(history, key=lambda x: x["timestamp"])

    def cleanup_old_metrics(self):
        """Clean up old metrics based on retention policy."""
        if time.time() - self.last_cleanup < 300:  # Only cleanup every 5 minutes
            return

        with self.lock:
            cutoff_time = time.time() - (self.config.metrics_retention_hours * 3600)

            for metric_name in list(self.metrics.keys()):
                metric_data = self.metrics[metric_name]
                # Remove old entries
                while metric_data and metric_data[0]["timestamp"] < cutoff_time:
                    metric_data.popleft()

                # Remove empty metrics
                if not metric_data:
                    del self.metrics[metric_name]

            self.last_cleanup = time.time()
            logger.debug("Completed metrics cleanup")

    def _build_metric_key(self, name: str, tags: dict[str, str] | None = None) -> str:
        """Build a unique key for a metric with tags."""
        if not tags:
            return name

        tag_parts = [f"{k}={v}" for k, v in sorted(tags.items())]
        return f"{name}[{','.join(tag_parts)}]"

    def _store_metric(
        self, key: str, metric_type: str, value: float, tags: dict[str, str] | None
    ):
        """Store a metric entry with timestamp."""
        entry = {
            "timestamp": time.time(),
            "type": metric_type,
            "value": value,
            "tags": tags or {},
        }
        self.metrics[key].append(entry)

        # Store metadata
        if key not in self.metric_metadata:
            self.metric_metadata[key] = {
                "type": metric_type,
                "first_seen": entry["timestamp"],
                "tags": tags or {},
            }
        self.metric_metadata[key]["last_seen"] = entry["timestamp"]

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


class TimingContext:
    """Context manager for timing operations."""

    def __init__(
        self,
        collector: MetricsCollector,
        name: str,
        tags: dict[str, str] | None = None,
    ):
        self.collector = collector
        self.name = name
        self.tags = tags
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time
            self.collector.record_timer(self.name, duration, self.tags)


class HealthChecker:
    """
    System-wide health checking coordinator.

    Manages health checks for all components and provides aggregated system health status.
    """

    def __init__(self, config: MonitoringConfig):
        self.config = config
        self.health_checks: dict[str, Callable] = {}
        self.health_results: dict[str, dict[str, Any]] = {}
        self.last_check_time = {}
        self.lock = threading.RLock()

        logger.info("Health checker initialized")

    def register_health_check(self, name: str, check_func: Callable):
        """Register a health check function."""
        with self.lock:
            self.health_checks[name] = check_func
            logger.info(f"Registered health check: {name}")

    async def run_health_checks(self) -> dict[str, Any]:
        """Run all registered health checks."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "components": {},
            "summary": {
                "total_checks": len(self.health_checks),
                "healthy_checks": 0,
                "unhealthy_checks": 0,
                "warning_checks": 0,
            },
        }

        for name, check_func in self.health_checks.items():
            try:
                # Run health check with timeout
                check_result = await asyncio.wait_for(
                    self._run_single_check(check_func),
                    timeout=self.config.component_health_timeout,
                )

                results["components"][name] = check_result

                # Update summary counts
                if check_result["status"] == "healthy":
                    results["summary"]["healthy_checks"] += 1
                elif check_result["status"] == "warning":
                    results["summary"]["warning_checks"] += 1
                else:
                    results["summary"]["unhealthy_checks"] += 1
                    results["overall_status"] = "unhealthy"

            except TimeoutError:
                results["components"][name] = {
                    "status": "unhealthy",
                    "message": f"Health check timed out after {self.config.component_health_timeout}s",
                    "timestamp": datetime.now().isoformat(),
                }
                results["summary"]["unhealthy_checks"] += 1
                results["overall_status"] = "unhealthy"

            except Exception as e:
                logger.error(f"Health check failed for {name}: {e}")
                results["components"][name] = {
                    "status": "unhealthy",
                    "message": f"Health check failed: {str(e)}",
                    "timestamp": datetime.now().isoformat(),
                }
                results["summary"]["unhealthy_checks"] += 1
                results["overall_status"] = "unhealthy"

        # Determine overall status
        if results["summary"]["unhealthy_checks"] == 0:
            if results["summary"]["warning_checks"] > 0:
                results["overall_status"] = "warning"
            else:
                results["overall_status"] = "healthy"

        with self.lock:
            self.health_results = results
            self.last_check_time[datetime.now().isoformat()] = results

        return results

    def get_last_health_check(self) -> dict[str, Any] | None:
        """Get the results of the last health check."""
        with self.lock:
            return self.health_results.copy() if self.health_results else None

    async def _run_single_check(self, check_func: Callable) -> dict[str, Any]:
        """Run a single health check function."""
        if asyncio.iscoroutinefunction(check_func):
            return await check_func()
        else:
            return check_func()


class MonitoringManager:
    """
    Central monitoring system coordinator.

    Integrates metrics collection, health checking, and performance monitoring
    to provide comprehensive system observability.
    """

    def __init__(self, config: MonitoringConfig | None = None):
        self.config = config or MonitoringConfig()

        # Initialize core components
        self.metrics = MetricsCollector(self.config)
        self.health = HealthChecker(self.config)

        # Monitoring state
        self.is_running = False
        self.monitoring_task = None

        # Component references for monitoring
        self.monitored_components: dict[str, Any] = {}

        logger.info("Monitoring manager initialized")

    async def start(self):
        """Start the monitoring system."""
        if self.is_running:
            logger.warning("Monitoring system already running")
            return

        self.is_running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())

        logger.info("Monitoring system started")

    async def stop(self):
        """Stop the monitoring system."""
        if not self.is_running:
            return

        self.is_running = False

        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Monitoring system stopped")

    def register_component(self, name: str, component: Any):
        """Register a component for monitoring."""
        self.monitored_components[name] = component

        # If component has health check method, register it
        if hasattr(component, "health_check"):
            self.health.register_health_check(name, component.health_check)

        logger.info(f"Registered component for monitoring: {name}")

    def get_system_status(self) -> dict[str, Any]:
        """Get comprehensive system status."""
        health_status = self.health.get_last_health_check()
        metrics_summary = self.metrics.get_metrics_summary()

        return {
            "timestamp": datetime.now().isoformat(),
            "monitoring_system": {
                "running": self.is_running,
                "components_monitored": len(self.monitored_components),
                "health_checks_registered": len(self.health.health_checks),
            },
            "health": health_status,
            "metrics": metrics_summary,
            "uptime": self._get_uptime(),
        }

    async def _monitoring_loop(self):
        """Main monitoring loop."""
        logger.info("Starting monitoring loop")

        last_health_check = 0
        last_metrics_cleanup = 0

        try:
            while self.is_running:
                current_time = time.time()

                # Run health checks
                if (
                    current_time - last_health_check
                    >= self.config.health_check_interval
                ):
                    try:
                        await self.health.run_health_checks()
                        last_health_check = current_time
                    except Exception as e:
                        logger.error(f"Error during health checks: {e}")

                # Cleanup old metrics
                if current_time - last_metrics_cleanup >= 300:  # Every 5 minutes
                    try:
                        self.metrics.cleanup_old_metrics()
                        last_metrics_cleanup = current_time
                    except Exception as e:
                        logger.error(f"Error during metrics cleanup: {e}")

                # Wait before next iteration
                await asyncio.sleep(10)

        except asyncio.CancelledError:
            logger.info("Monitoring loop cancelled")
        except Exception as e:
            logger.error(f"Monitoring loop error: {e}")
            raise

    def _get_uptime(self) -> str:
        """Get system uptime (placeholder - would integrate with actual system start time)."""
        # This would be implemented with actual system start time tracking
        return "N/A"
