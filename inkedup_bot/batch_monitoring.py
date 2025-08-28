#!/usr/bin/env python3
"""
Comprehensive Batch Processing Monitoring and Analytics System

This module provides real-time monitoring, performance analytics, and reporting
for batch database operations including metrics collection, alerting, and optimization insights.
"""

import asyncio
import json
import logging
import statistics
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from .batch_processor import BatchMetrics, BatchProcessor
from .query_optimizer import QueryMetrics, QueryOptimizer
from .transaction_optimizer import TransactionMetrics, TransactionOptimizer

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels for batch processing issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MetricType(Enum):
    """Types of metrics tracked by the monitoring system."""

    PERFORMANCE = "performance"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    RESOURCE_USAGE = "resource_usage"
    BATCH_EFFICIENCY = "batch_efficiency"


@dataclass
class BatchAlert:
    """Alert for batch processing issues."""

    alert_id: str
    severity: AlertSeverity
    metric_type: MetricType
    message: str
    current_value: float
    threshold_value: float
    component: str  # 'batch_processor', 'query_optimizer', 'transaction_optimizer'
    timestamp: datetime
    resolved: bool = False
    metadata: dict[str, Any] = None


@dataclass
class PerformanceSnapshot:
    """Point-in-time performance snapshot."""

    timestamp: datetime
    batch_metrics: BatchMetrics
    query_metrics: QueryMetrics
    transaction_metrics: TransactionMetrics
    system_metrics: dict[str, float]


@dataclass
class MonitoringConfig:
    """Configuration for batch monitoring system."""

    collection_interval_seconds: int = 30
    retention_hours: int = 24
    alert_thresholds: dict[str, float] = None
    enable_alerting: bool = True
    enable_performance_tracking: bool = True
    max_snapshots: int = 2880  # 24 hours at 30-second intervals

    def __post_init__(self):
        if self.alert_thresholds is None:
            self.alert_thresholds = {
                "batch_error_rate": 0.05,  # 5% error rate threshold
                "query_cache_hit_rate_low": 0.6,  # 60% minimum cache hit rate
                "avg_response_time_ms": 1000,  # 1 second average response time
                "transaction_deadlock_rate": 0.02,  # 2% deadlock rate
                "batch_efficiency_low": 0.7,  # 70% minimum batch efficiency
                "memory_usage_mb": 1000,  # 1GB memory usage warning
                "queue_size_high": 5000,  # High queue size warning
            }


class BatchMonitor:
    """
    Comprehensive monitoring system for batch database operations with
    real-time metrics collection, alerting, and performance analytics.
    """

    def __init__(
        self,
        batch_processor: BatchProcessor,
        query_optimizer: QueryOptimizer = None,
        transaction_optimizer: TransactionOptimizer = None,
        config: MonitoringConfig = None,
    ):
        self.batch_processor = batch_processor
        self.query_optimizer = query_optimizer
        self.transaction_optimizer = transaction_optimizer
        self.config = config or MonitoringConfig()

        # Monitoring state
        self._monitoring_active = False
        self._collection_task: asyncio.Task | None = None
        self._alert_task: asyncio.Task | None = None

        # Data storage
        self._performance_snapshots: deque = deque(maxlen=self.config.max_snapshots)
        self._alerts: deque = deque(maxlen=1000)
        self._alert_callbacks: list[Callable[[BatchAlert], None]] = []

        # Thread safety
        self._data_lock = threading.RLock()

        # Performance tracking
        self._performance_trends: dict[str, deque] = {
            "throughput": deque(maxlen=100),
            "error_rate": deque(maxlen=100),
            "response_time": deque(maxlen=100),
            "batch_efficiency": deque(maxlen=100),
            "cache_hit_rate": deque(maxlen=100),
        }

        # System resource tracking
        self._system_metrics: dict[str, float] = {
            "cpu_usage_percent": 0.0,
            "memory_usage_mb": 0.0,
            "disk_io_mb_per_sec": 0.0,
            "network_io_mb_per_sec": 0.0,
        }

        logger.info("BatchMonitor initialized")

    async def start_monitoring(self):
        """Start the monitoring system."""
        if self._monitoring_active:
            return

        self._monitoring_active = True

        # Start metrics collection task
        self._collection_task = asyncio.create_task(self._metrics_collection_loop())

        # Start alerting task if enabled
        if self.config.enable_alerting:
            self._alert_task = asyncio.create_task(self._alerting_loop())

        logger.info("Batch monitoring started")

    async def stop_monitoring(self):
        """Stop the monitoring system."""
        if not self._monitoring_active:
            return

        self._monitoring_active = False

        # Cancel tasks
        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass

        if self._alert_task:
            self._alert_task.cancel()
            try:
                await self._alert_task
            except asyncio.CancelledError:
                pass

        logger.info("Batch monitoring stopped")

    async def _metrics_collection_loop(self):
        """Main metrics collection loop."""
        while self._monitoring_active:
            try:
                await self._collect_performance_snapshot()
                await asyncio.sleep(self.config.collection_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics collection: {e}")
                await asyncio.sleep(self.config.collection_interval_seconds)

    async def _collect_performance_snapshot(self):
        """Collect a comprehensive performance snapshot."""
        try:
            # Collect metrics from all components
            batch_metrics = await self.batch_processor.get_metrics()

            query_metrics = None
            if self.query_optimizer:
                query_metrics = self.query_optimizer.get_metrics()

            transaction_metrics = None
            if self.transaction_optimizer:
                transaction_metrics = self.transaction_optimizer.get_metrics()

            # Collect system metrics
            system_metrics = await self._collect_system_metrics()

            # Create snapshot
            snapshot = PerformanceSnapshot(
                timestamp=datetime.now(),
                batch_metrics=batch_metrics,
                query_metrics=query_metrics,
                transaction_metrics=transaction_metrics,
                system_metrics=system_metrics,
            )

            # Store snapshot
            with self._data_lock:
                self._performance_snapshots.append(snapshot)

                # Update performance trends
                self._update_performance_trends(snapshot)

            logger.debug(f"Performance snapshot collected at {snapshot.timestamp}")

        except Exception as e:
            logger.error(f"Failed to collect performance snapshot: {e}")

    async def _collect_system_metrics(self) -> dict[str, float]:
        """Collect system resource metrics."""
        metrics = {}

        try:
            # In a real implementation, you would use psutil or similar
            # For now, we'll use placeholder values
            import os

            # Memory usage (simplified)
            try:
                with open("/proc/meminfo") as f:
                    mem_info = f.read()
                    for line in mem_info.split("\n"):
                        if line.startswith("MemAvailable:"):
                            available_kb = int(line.split()[1])
                            metrics["memory_available_mb"] = available_kb / 1024
                        elif line.startswith("MemTotal:"):
                            total_kb = int(line.split()[1])
                            metrics["memory_total_mb"] = total_kb / 1024

                if "memory_total_mb" in metrics and "memory_available_mb" in metrics:
                    used_mb = (
                        metrics["memory_total_mb"] - metrics["memory_available_mb"]
                    )
                    metrics["memory_usage_mb"] = used_mb
                    metrics["memory_usage_percent"] = (
                        used_mb / metrics["memory_total_mb"]
                    ) * 100

            except Exception:
                # Fallback values
                metrics["memory_usage_mb"] = 0.0
                metrics["memory_usage_percent"] = 0.0

            # CPU usage (simplified)
            try:
                with open("/proc/loadavg") as f:
                    load_avg = f.read().split()
                    metrics["cpu_load_1min"] = float(load_avg[0])
                    metrics["cpu_load_5min"] = float(load_avg[1])
                    metrics["cpu_load_15min"] = float(load_avg[2])
            except Exception:
                metrics["cpu_load_1min"] = 0.0

            # Disk usage for database file
            try:
                if hasattr(self.batch_processor, "db") and hasattr(
                    self.batch_processor.db, "db_path"
                ):
                    db_path = self.batch_processor.db.db_path
                    if os.path.exists(db_path):
                        stat = os.stat(db_path)
                        metrics["database_size_mb"] = stat.st_size / (1024 * 1024)
                else:
                    metrics["database_size_mb"] = 0.0
            except Exception:
                metrics["database_size_mb"] = 0.0

        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            # Return default metrics
            metrics = {
                "memory_usage_mb": 0.0,
                "memory_usage_percent": 0.0,
                "cpu_load_1min": 0.0,
                "database_size_mb": 0.0,
            }

        return metrics

    def _update_performance_trends(self, snapshot: PerformanceSnapshot):
        """Update performance trend data."""
        try:
            # Batch processor trends
            if snapshot.batch_metrics:
                self._performance_trends["throughput"].append(
                    snapshot.batch_metrics.throughput_ops_per_second
                )
                self._performance_trends["error_rate"].append(
                    snapshot.batch_metrics.error_rate
                )
                self._performance_trends["response_time"].append(
                    snapshot.batch_metrics.average_processing_time_ms
                )
                self._performance_trends["batch_efficiency"].append(
                    snapshot.batch_metrics.average_batch_size
                    / self.batch_processor.config.max_batch_size
                )

            # Query optimizer trends
            if snapshot.query_metrics and self.query_optimizer:
                total_queries = snapshot.query_metrics.total_queries
                cache_hit_rate = 0.0
                if total_queries > 0:
                    cache_hit_rate = snapshot.query_metrics.cache_hits / total_queries

                self._performance_trends["cache_hit_rate"].append(cache_hit_rate)

        except Exception as e:
            logger.error(f"Error updating performance trends: {e}")

    async def _alerting_loop(self):
        """Main alerting loop that checks thresholds and generates alerts."""
        while self._monitoring_active:
            try:
                await self._check_alert_conditions()
                await asyncio.sleep(60)  # Check alerts every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in alerting loop: {e}")
                await asyncio.sleep(60)

    async def _check_alert_conditions(self):
        """Check all alert conditions and generate alerts if needed."""
        if not self._performance_snapshots:
            return

        latest_snapshot = self._performance_snapshots[-1]
        current_time = datetime.now()

        # Check batch processor alerts
        if latest_snapshot.batch_metrics:
            await self._check_batch_processor_alerts(
                latest_snapshot.batch_metrics, current_time
            )

        # Check query optimizer alerts
        if latest_snapshot.query_metrics:
            await self._check_query_optimizer_alerts(
                latest_snapshot.query_metrics, current_time
            )

        # Check transaction optimizer alerts
        if latest_snapshot.transaction_metrics:
            await self._check_transaction_optimizer_alerts(
                latest_snapshot.transaction_metrics, current_time
            )

        # Check system resource alerts
        await self._check_system_alerts(latest_snapshot.system_metrics, current_time)

    async def _check_batch_processor_alerts(
        self, metrics: BatchMetrics, timestamp: datetime
    ):
        """Check batch processor specific alert conditions."""
        # High error rate
        if metrics.error_rate > self.config.alert_thresholds["batch_error_rate"]:
            await self._create_alert(
                severity=AlertSeverity.ERROR,
                metric_type=MetricType.ERROR_RATE,
                component="batch_processor",
                message=f"High batch error rate: {metrics.error_rate:.2%}",
                current_value=metrics.error_rate,
                threshold_value=self.config.alert_thresholds["batch_error_rate"],
                timestamp=timestamp,
            )

        # Low batch efficiency
        if self.batch_processor.config.max_batch_size > 0:
            efficiency = (
                metrics.average_batch_size / self.batch_processor.config.max_batch_size
            )
            if efficiency < self.config.alert_thresholds["batch_efficiency_low"]:
                await self._create_alert(
                    severity=AlertSeverity.WARNING,
                    metric_type=MetricType.BATCH_EFFICIENCY,
                    component="batch_processor",
                    message=f"Low batch efficiency: {efficiency:.2%}",
                    current_value=efficiency,
                    threshold_value=self.config.alert_thresholds[
                        "batch_efficiency_low"
                    ],
                    timestamp=timestamp,
                )

        # High response time
        if (
            metrics.average_processing_time_ms
            > self.config.alert_thresholds["avg_response_time_ms"]
        ):
            await self._create_alert(
                severity=AlertSeverity.WARNING,
                metric_type=MetricType.PERFORMANCE,
                component="batch_processor",
                message=f"High average processing time: {metrics.average_processing_time_ms:.1f}ms",
                current_value=metrics.average_processing_time_ms,
                threshold_value=self.config.alert_thresholds["avg_response_time_ms"],
                timestamp=timestamp,
            )

    async def _check_query_optimizer_alerts(
        self, metrics: QueryMetrics, timestamp: datetime
    ):
        """Check query optimizer specific alert conditions."""
        # Low cache hit rate
        if metrics.total_queries > 0:
            cache_hit_rate = metrics.cache_hits / metrics.total_queries
            if (
                cache_hit_rate
                < self.config.alert_thresholds["query_cache_hit_rate_low"]
            ):
                await self._create_alert(
                    severity=AlertSeverity.WARNING,
                    metric_type=MetricType.PERFORMANCE,
                    component="query_optimizer",
                    message=f"Low query cache hit rate: {cache_hit_rate:.2%}",
                    current_value=cache_hit_rate,
                    threshold_value=self.config.alert_thresholds[
                        "query_cache_hit_rate_low"
                    ],
                    timestamp=timestamp,
                )

        # High average execution time
        if (
            metrics.average_execution_time_ms
            > self.config.alert_thresholds["avg_response_time_ms"]
        ):
            await self._create_alert(
                severity=AlertSeverity.WARNING,
                metric_type=MetricType.PERFORMANCE,
                component="query_optimizer",
                message=f"High average query execution time: {metrics.average_execution_time_ms:.1f}ms",
                current_value=metrics.average_execution_time_ms,
                threshold_value=self.config.alert_thresholds["avg_response_time_ms"],
                timestamp=timestamp,
            )

    async def _check_transaction_optimizer_alerts(
        self, metrics: TransactionMetrics, timestamp: datetime
    ):
        """Check transaction optimizer specific alert conditions."""
        # High deadlock rate
        if metrics.total_transactions > 0:
            deadlock_rate = metrics.deadlocks_detected / metrics.total_transactions
            if (
                deadlock_rate
                > self.config.alert_thresholds["transaction_deadlock_rate"]
            ):
                await self._create_alert(
                    severity=AlertSeverity.ERROR,
                    metric_type=MetricType.ERROR_RATE,
                    component="transaction_optimizer",
                    message=f"High deadlock rate: {deadlock_rate:.2%}",
                    current_value=deadlock_rate,
                    threshold_value=self.config.alert_thresholds[
                        "transaction_deadlock_rate"
                    ],
                    timestamp=timestamp,
                )

        # Low batch efficiency
        if (
            metrics.batch_efficiency_ratio
            < self.config.alert_thresholds["batch_efficiency_low"]
        ):
            await self._create_alert(
                severity=AlertSeverity.WARNING,
                metric_type=MetricType.BATCH_EFFICIENCY,
                component="transaction_optimizer",
                message=f"Low transaction batch efficiency: {metrics.batch_efficiency_ratio:.2%}",
                current_value=metrics.batch_efficiency_ratio,
                threshold_value=self.config.alert_thresholds["batch_efficiency_low"],
                timestamp=timestamp,
            )

    async def _check_system_alerts(
        self, system_metrics: dict[str, float], timestamp: datetime
    ):
        """Check system resource alert conditions."""
        # High memory usage
        memory_usage = system_metrics.get("memory_usage_mb", 0.0)
        if memory_usage > self.config.alert_thresholds["memory_usage_mb"]:
            await self._create_alert(
                severity=AlertSeverity.WARNING,
                metric_type=MetricType.RESOURCE_USAGE,
                component="system",
                message=f"High memory usage: {memory_usage:.1f}MB",
                current_value=memory_usage,
                threshold_value=self.config.alert_thresholds["memory_usage_mb"],
                timestamp=timestamp,
            )

    async def _create_alert(
        self,
        severity: AlertSeverity,
        metric_type: MetricType,
        component: str,
        message: str,
        current_value: float,
        threshold_value: float,
        timestamp: datetime,
        metadata: dict[str, Any] = None,
    ):
        """Create and process a new alert."""
        alert_id = f"{component}_{metric_type.value if metric_type else 'unknown'}_{int(timestamp.timestamp())}"

        alert = BatchAlert(
            alert_id=alert_id,
            severity=severity,
            metric_type=metric_type,
            component=component,
            message=message,
            current_value=current_value,
            threshold_value=threshold_value,
            timestamp=timestamp,
            metadata=metadata or {},
        )

        # Store alert
        with self._data_lock:
            self._alerts.append(alert)

        # Execute alert callbacks
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Error executing alert callback: {e}")

        logger.warning(f"ALERT [{severity.value.upper()}] {component}: {message}")

    def add_alert_callback(self, callback: Callable[[BatchAlert], None]):
        """Add a callback function to be called when alerts are generated."""
        self._alert_callbacks.append(callback)

    def get_current_metrics(self) -> dict[str, Any] | None:
        """Get the most recent performance metrics."""
        with self._data_lock:
            if not self._performance_snapshots:
                return None

            latest = self._performance_snapshots[-1]

            return {
                "timestamp": latest.timestamp.isoformat(),
                "batch_processor": (
                    asdict(latest.batch_metrics) if latest.batch_metrics else None
                ),
                "query_optimizer": (
                    asdict(latest.query_metrics) if latest.query_metrics else None
                ),
                "transaction_optimizer": (
                    asdict(latest.transaction_metrics)
                    if latest.transaction_metrics
                    else None
                ),
                "system_metrics": latest.system_metrics,
            }

    def get_performance_trends(self, hours: int = 1) -> dict[str, Any]:
        """Get performance trends over the specified time period."""
        cutoff_time = datetime.now() - timedelta(hours=hours)

        with self._data_lock:
            # Filter snapshots to the requested time window
            relevant_snapshots = [
                snapshot
                for snapshot in self._performance_snapshots
                if snapshot.timestamp >= cutoff_time
            ]

            if not relevant_snapshots:
                return {"error": "No data available for the requested time period"}

            trends = {
                "time_period_hours": hours,
                "data_points": len(relevant_snapshots),
                "metrics": {},
            }

            # Calculate trends for each metric
            for metric_name, values in self._performance_trends.items():
                if values:
                    recent_values = list(values)[
                        -int(hours * 120) :
                    ]  # Approximate based on collection interval
                    if recent_values:
                        trends["metrics"][metric_name] = {
                            "current": recent_values[-1],
                            "average": statistics.mean(recent_values),
                            "min": min(recent_values),
                            "max": max(recent_values),
                            "trend": self._calculate_trend(recent_values),
                            "data_points": len(recent_values),
                        }

            return trends

    def _calculate_trend(self, values: list[float]) -> str:
        """Calculate trend direction for a list of values."""
        if len(values) < 2:
            return "stable"

        # Simple trend calculation using first and last quarters
        quarter_size = len(values) // 4
        if quarter_size < 1:
            return "stable"

        first_quarter = statistics.mean(values[:quarter_size])
        last_quarter = statistics.mean(values[-quarter_size:])

        change_ratio = (
            (last_quarter - first_quarter) / first_quarter if first_quarter != 0 else 0
        )

        if change_ratio > 0.1:
            return "increasing"
        elif change_ratio < -0.1:
            return "decreasing"
        else:
            return "stable"

    def get_active_alerts(
        self, severity_filter: AlertSeverity | None = None
    ) -> list[BatchAlert]:
        """Get currently active alerts."""
        with self._data_lock:
            alerts = [alert for alert in self._alerts if not alert.resolved]

            if severity_filter:
                alerts = [
                    alert for alert in alerts if alert.severity == severity_filter
                ]

            return sorted(alerts, key=lambda x: x.timestamp, reverse=True)

    def resolve_alert(self, alert_id: str) -> bool:
        """Mark an alert as resolved."""
        with self._data_lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.resolved = True
                    logger.info(f"Alert {alert_id} marked as resolved")
                    return True

            return False

    def get_performance_report(self, hours: int = 24) -> dict[str, Any]:
        """Generate a comprehensive performance report."""
        cutoff_time = datetime.now() - timedelta(hours=hours)

        with self._data_lock:
            relevant_snapshots = [
                snapshot
                for snapshot in self._performance_snapshots
                if snapshot.timestamp >= cutoff_time
            ]

            if not relevant_snapshots:
                return {"error": "Insufficient data for report generation"}

            # Extract metrics for analysis
            batch_throughputs = []
            batch_error_rates = []
            response_times = []
            cache_hit_rates = []
            memory_usages = []

            for snapshot in relevant_snapshots:
                if snapshot.batch_metrics:
                    batch_throughputs.append(
                        snapshot.batch_metrics.throughput_ops_per_second
                    )
                    batch_error_rates.append(snapshot.batch_metrics.error_rate)
                    response_times.append(
                        snapshot.batch_metrics.average_processing_time_ms
                    )

                if snapshot.query_metrics and snapshot.query_metrics.total_queries > 0:
                    hit_rate = (
                        snapshot.query_metrics.cache_hits
                        / snapshot.query_metrics.total_queries
                    )
                    cache_hit_rates.append(hit_rate)

                memory_usage = snapshot.system_metrics.get("memory_usage_mb", 0)
                if memory_usage > 0:
                    memory_usages.append(memory_usage)

            # Calculate summary statistics
            report = {
                "report_period_hours": hours,
                "generated_at": datetime.now().isoformat(),
                "data_points": len(relevant_snapshots),
                "summary": {
                    "batch_throughput": self._calculate_stats(
                        batch_throughputs, "ops/sec"
                    ),
                    "batch_error_rate": self._calculate_stats(
                        batch_error_rates, "%", multiply_by_100=True
                    ),
                    "response_time": self._calculate_stats(response_times, "ms"),
                    "cache_hit_rate": self._calculate_stats(
                        cache_hit_rates, "%", multiply_by_100=True
                    ),
                    "memory_usage": self._calculate_stats(memory_usages, "MB"),
                },
                "active_alerts": len(self.get_active_alerts()),
                "recommendations": self._generate_performance_recommendations(),
            }

            return report

    def _calculate_stats(
        self, values: list[float], unit: str, multiply_by_100: bool = False
    ) -> dict[str, Any]:
        """Calculate statistical summary for a list of values."""
        if not values:
            return {"error": "No data available"}

        multiplier = 100 if multiply_by_100 else 1

        return {
            "current": values[-1] * multiplier,
            "average": statistics.mean(values) * multiplier,
            "min": min(values) * multiplier,
            "max": max(values) * multiplier,
            "median": statistics.median(values) * multiplier,
            "std_dev": statistics.stdev(values) * multiplier if len(values) > 1 else 0,
            "unit": unit,
            "trend": self._calculate_trend(values),
        }

    def _generate_performance_recommendations(self) -> list[str]:
        """Generate performance optimization recommendations."""
        recommendations = []

        # Analyze recent performance trends
        if (
            self._performance_trends["error_rate"]
            and len(self._performance_trends["error_rate"]) > 10
        ):
            recent_error_rate = statistics.mean(
                list(self._performance_trends["error_rate"])[-10:]
            )
            if recent_error_rate > 0.03:
                recommendations.append(
                    f"High error rate detected ({recent_error_rate:.2%}). Consider reviewing error logs and optimizing batch operations."
                )

        if (
            self._performance_trends["cache_hit_rate"]
            and len(self._performance_trends["cache_hit_rate"]) > 10
        ):
            recent_hit_rate = statistics.mean(
                list(self._performance_trends["cache_hit_rate"])[-10:]
            )
            if recent_hit_rate < 0.7:
                recommendations.append(
                    f"Low cache hit rate ({recent_hit_rate:.2%}). Consider adjusting cache TTL settings or cache size."
                )

        if (
            self._performance_trends["batch_efficiency"]
            and len(self._performance_trends["batch_efficiency"]) > 10
        ):
            recent_efficiency = statistics.mean(
                list(self._performance_trends["batch_efficiency"])[-10:]
            )
            if recent_efficiency < 0.6:
                recommendations.append(
                    f"Low batch efficiency ({recent_efficiency:.2%}). Consider adjusting batch size or timeout settings."
                )

        if (
            self._performance_trends["response_time"]
            and len(self._performance_trends["response_time"]) > 10
        ):
            recent_response_time = statistics.mean(
                list(self._performance_trends["response_time"])[-10:]
            )
            if recent_response_time > 500:
                recommendations.append(
                    f"High response times ({recent_response_time:.1f}ms). Consider database optimization or increasing batch processing resources."
                )

        if not recommendations:
            recommendations.append(
                "System performance is within acceptable parameters."
            )

        return recommendations

    def export_metrics(self, output_file: str, hours: int = 24) -> dict[str, Any]:
        """Export performance metrics to a file."""
        try:
            report = self.get_performance_report(hours)
            trends = self.get_performance_trends(hours)
            current_metrics = self.get_current_metrics()
            active_alerts = self.get_active_alerts()

            export_data = {
                "export_metadata": {
                    "exported_at": datetime.now().isoformat(),
                    "time_period_hours": hours,
                    "monitoring_system_version": "1.0",
                },
                "performance_report": report,
                "performance_trends": trends,
                "current_metrics": current_metrics,
                "active_alerts": [asdict(alert) for alert in active_alerts],
                "configuration": asdict(self.config),
            }

            with open(output_file, "w") as f:
                json.dump(export_data, f, indent=2, default=str)

            return {
                "success": True,
                "message": f"Metrics exported to {output_file}",
                "file_size_bytes": len(json.dumps(export_data)),
            }

        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")
            return {"success": False, "error": str(e)}


# Global monitoring instance
_batch_monitor: BatchMonitor | None = None


def get_batch_monitor() -> BatchMonitor | None:
    """Get the global batch monitor instance."""
    return _batch_monitor


async def initialize_batch_monitoring(
    batch_processor: BatchProcessor,
    query_optimizer: QueryOptimizer = None,
    transaction_optimizer: TransactionOptimizer = None,
    config: MonitoringConfig = None,
):
    """Initialize and start the global batch monitoring system."""
    global _batch_monitor
    _batch_monitor = BatchMonitor(
        batch_processor, query_optimizer, transaction_optimizer, config
    )
    await _batch_monitor.start_monitoring()
    logger.info("Global batch monitoring system initialized and started")


async def shutdown_batch_monitoring():
    """Shutdown the global batch monitoring system."""
    global _batch_monitor
    if _batch_monitor:
        await _batch_monitor.stop_monitoring()
        _batch_monitor = None
    logger.info("Global batch monitoring system shutdown complete")


def print_performance_dashboard():
    """Print a formatted performance dashboard to console."""
    monitor = get_batch_monitor()
    if not monitor:
        print("Batch monitoring not initialized")
        return

    try:
        current_metrics = monitor.get_current_metrics()
        active_alerts = monitor.get_active_alerts()

        print("\n" + "=" * 80)
        print("BATCH PROCESSING PERFORMANCE DASHBOARD")
        print("=" * 80)

        if current_metrics:
            print(f"\nLAST UPDATED: {current_metrics['timestamp']}")

            # Batch processor metrics
            if current_metrics["batch_processor"]:
                bp = current_metrics["batch_processor"]
                print("\nBATCH PROCESSOR:")
                print(
                    f"├── Throughput: {bp.get('throughput_ops_per_second', 0):.1f} ops/sec"
                )
                print(f"├── Error Rate: {bp.get('error_rate', 0):.2%}")
                print(
                    f"├── Avg Processing Time: {bp.get('average_processing_time_ms', 0):.1f}ms"
                )
                print(f"├── Total Operations: {bp.get('total_operations', 0):,}")
                print(f"└── Avg Batch Size: {bp.get('average_batch_size', 0):.1f}")

            # Query optimizer metrics
            if current_metrics["query_optimizer"]:
                qo = current_metrics["query_optimizer"]
                total_queries = qo.get("total_queries", 0)
                cache_hits = qo.get("cache_hits", 0)
                hit_rate = (
                    (cache_hits / total_queries * 100) if total_queries > 0 else 0
                )

                print("\nQUERY OPTIMIZER:")
                print(f"├── Total Queries: {total_queries:,}")
                print(f"├── Cache Hit Rate: {hit_rate:.1f}%")
                print(
                    f"├── Avg Execution Time: {qo.get('average_execution_time_ms', 0):.1f}ms"
                )
                print(f"└── Cache Misses: {qo.get('cache_misses', 0):,}")

            # Transaction optimizer metrics
            if current_metrics["transaction_optimizer"]:
                to = current_metrics["transaction_optimizer"]
                print("\nTRANSACTION OPTIMIZER:")
                print(f"├── Total Transactions: {to.get('total_transactions', 0):,}")
                print(
                    f"├── Success Rate: {(to.get('successful_transactions', 0) / max(to.get('total_transactions', 1), 1) * 100):.1f}%"
                )
                print(
                    f"├── Avg Transaction Time: {to.get('average_transaction_time_ms', 0):.1f}ms"
                )
                print(f"└── Deadlocks Detected: {to.get('deadlocks_detected', 0)}")

            # System metrics
            if current_metrics["system_metrics"]:
                sm = current_metrics["system_metrics"]
                print("\nSYSTEM RESOURCES:")
                print(f"├── Memory Usage: {sm.get('memory_usage_mb', 0):.1f}MB")
                print(f"├── CPU Load (1min): {sm.get('cpu_load_1min', 0):.2f}")
                print(f"└── Database Size: {sm.get('database_size_mb', 0):.1f}MB")

        # Active alerts
        if active_alerts:
            print(f"\nACTIVE ALERTS ({len(active_alerts)}):")
            for alert in active_alerts[:5]:  # Show first 5 alerts
                print(
                    f"├── [{alert.severity.value.upper()}] {alert.component}: {alert.message}"
                )
        else:
            print("\n✅ NO ACTIVE ALERTS")

        print("\n" + "=" * 80)

    except Exception as e:
        print(f"Error displaying dashboard: {e}")
