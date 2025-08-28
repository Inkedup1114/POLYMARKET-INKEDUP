"""
Enhanced metrics collection and export system for the InkedUp Polymarket trading bot.

This module provides advanced metrics collection, aggregation, and export capabilities
with support for multiple formats (Prometheus, InfluxDB, JSON) and time-series data.
"""

import asyncio
import json
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from statistics import mean, median, stdev
from typing import Any

log = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics supported by the system."""

    COUNTER = "counter"  # Monotonically increasing
    GAUGE = "gauge"  # Current value
    HISTOGRAM = "histogram"  # Distribution of values
    TIMER = "timer"  # Duration measurements
    SET = "set"  # Unique value counting


@dataclass
class MetricValue:
    """A single metric measurement."""

    name: str
    value: float | int | str | set[str]
    timestamp: float
    labels: dict[str, str] = field(default_factory=dict)
    metric_type: MetricType = MetricType.GAUGE

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        result["timestamp"] = self.timestamp
        result["metric_type"] = self.metric_type.value
        if isinstance(self.value, set):
            result["value"] = list(self.value)
        return result


@dataclass
class MetricAggregation:
    """Aggregated metric statistics over a time window."""

    name: str
    metric_type: MetricType
    count: int
    min_value: float
    max_value: float
    avg_value: float
    sum_value: float
    median_value: float
    std_dev: float
    percentiles: dict[int, float] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    window_start: float = 0
    window_end: float = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        result["metric_type"] = self.metric_type.value
        return result


class MetricsBuffer:
    """Thread-safe buffer for metric values with time-based retention."""

    def __init__(self, max_size: int = 10000, retention_seconds: int = 3600):
        self.max_size = max_size
        self.retention_seconds = retention_seconds
        self._buffer: deque = deque(maxlen=max_size)
        self._lock = threading.RLock()
        self._last_cleanup = time.time()

    def add(self, metric: MetricValue):
        """Add a metric to the buffer."""
        with self._lock:
            self._buffer.append(metric)
            self._cleanup_if_needed()

    def get_values_in_range(
        self, start_time: float | None = None, end_time: float | None = None
    ) -> list[MetricValue]:
        """Get metric values within a time range."""
        with self._lock:
            if not start_time:
                start_time = time.time() - self.retention_seconds
            if not end_time:
                end_time = time.time()

            return [
                metric
                for metric in self._buffer
                if start_time <= metric.timestamp <= end_time
            ]

    def get_latest_values(self, count: int = 100) -> list[MetricValue]:
        """Get the most recent metric values."""
        with self._lock:
            return list(self._buffer)[-count:]

    def clear(self):
        """Clear all buffered metrics."""
        with self._lock:
            self._buffer.clear()

    def _cleanup_if_needed(self):
        """Remove old metrics if cleanup is due."""
        current_time = time.time()
        if current_time - self._last_cleanup < 300:  # Only cleanup every 5 minutes
            return

        cutoff_time = current_time - self.retention_seconds

        # Remove old metrics from the left side
        while self._buffer and self._buffer[0].timestamp < cutoff_time:
            self._buffer.popleft()

        self._last_cleanup = current_time


class EnhancedMetricsCollector:
    """
    Advanced metrics collection system with support for multiple metric types,
    aggregation, and export formats.
    """

    def __init__(
        self,
        buffer_size: int = 50000,
        retention_hours: int = 24,
        aggregation_window_seconds: int = 60,
        enable_percentiles: bool = True,
    ):
        self.buffer_size = buffer_size
        self.retention_seconds = retention_hours * 3600
        self.aggregation_window_seconds = aggregation_window_seconds
        self.enable_percentiles = enable_percentiles

        # Metric storage
        self._metrics: dict[str, MetricsBuffer] = {}
        self._metric_metadata: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

        # Aggregated data cache
        self._aggregations: dict[str, MetricAggregation] = {}
        self._last_aggregation = time.time()

        # Performance tracking
        self._collection_stats = {
            "total_metrics_recorded": 0,
            "collection_errors": 0,
            "last_collection_time": time.time(),
            "collection_duration_ms": 0,
        }

        log.info(
            f"Enhanced metrics collector initialized (retention: {retention_hours}h)"
        )

    def counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
        description: str = "",
    ):
        """Record a counter metric (monotonically increasing)."""
        self._record_metric(name, value, labels, MetricType.COUNTER, description)

    def gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        description: str = "",
    ):
        """Record a gauge metric (current value)."""
        self._record_metric(name, value, labels, MetricType.GAUGE, description)

    def histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        description: str = "",
    ):
        """Record a histogram metric (value distribution)."""
        self._record_metric(name, value, labels, MetricType.HISTOGRAM, description)

    def timer(
        self,
        name: str,
        duration_ms: float,
        labels: dict[str, str] | None = None,
        description: str = "",
    ):
        """Record a timer metric (duration measurement)."""
        self._record_metric(name, duration_ms, labels, MetricType.TIMER, description)

    def set_metric(
        self,
        name: str,
        value: str,
        labels: dict[str, str] | None = None,
        description: str = "",
    ):
        """Record a set metric (unique value counting)."""
        metric_key = self._build_metric_key(name, labels)

        with self._lock:
            if metric_key not in self._metrics:
                self._metrics[metric_key] = MetricsBuffer(
                    max_size=self.buffer_size, retention_seconds=self.retention_seconds
                )
                self._metric_metadata[metric_key] = {
                    "type": MetricType.SET,
                    "name": name,
                    "description": description,
                    "labels": labels or {},
                    "first_seen": time.time(),
                }

            # For sets, we maintain the unique values
            existing_values = set()
            recent_metrics = self._metrics[metric_key].get_latest_values(1000)
            for metric in recent_metrics:
                if isinstance(metric.value, set):
                    existing_values.update(metric.value)
                elif isinstance(metric.value, str):
                    existing_values.add(metric.value)

            existing_values.add(value)

            metric_value = MetricValue(
                name=name,
                value=existing_values,
                timestamp=time.time(),
                labels=labels or {},
                metric_type=MetricType.SET,
            )

            self._metrics[metric_key].add(metric_value)
            self._collection_stats["total_metrics_recorded"] += 1

    def timing_context(
        self, name: str, labels: dict[str, str] | None = None, description: str = ""
    ):
        """Context manager for timing operations."""
        return TimingContextManager(self, name, labels, description)

    def increment_counter(self, name: str, labels: dict[str, str] | None = None):
        """Convenience method to increment a counter by 1."""
        self.counter(name, 1.0, labels)

    def _record_metric(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None,
        metric_type: MetricType,
        description: str = "",
    ):
        """Internal method to record a metric."""
        start_time = time.time()

        try:
            metric_key = self._build_metric_key(name, labels)

            with self._lock:
                # Initialize metric buffer if needed
                if metric_key not in self._metrics:
                    self._metrics[metric_key] = MetricsBuffer(
                        max_size=self.buffer_size,
                        retention_seconds=self.retention_seconds,
                    )
                    self._metric_metadata[metric_key] = {
                        "type": metric_type,
                        "name": name,
                        "description": description,
                        "labels": labels or {},
                        "first_seen": time.time(),
                    }

                # Create metric value
                metric_value = MetricValue(
                    name=name,
                    value=value,
                    timestamp=time.time(),
                    labels=labels or {},
                    metric_type=metric_type,
                )

                # Add to buffer
                self._metrics[metric_key].add(metric_value)
                self._collection_stats["total_metrics_recorded"] += 1

        except Exception as e:
            log.error(f"Error recording metric {name}: {e}")
            self._collection_stats["collection_errors"] += 1
        finally:
            duration_ms = (time.time() - start_time) * 1000
            self._collection_stats["collection_duration_ms"] = duration_ms
            self._collection_stats["last_collection_time"] = time.time()

    def _build_metric_key(self, name: str, labels: dict[str, str] | None = None) -> str:
        """Build a unique key for a metric with labels."""
        if not labels:
            return name

        label_parts = [f"{k}={v}" for k, v in sorted(labels.items())]
        return f"{name}{{{','.join(label_parts)}}}"

    def get_metric_aggregation(
        self,
        name: str,
        labels: dict[str, str] | None = None,
        window_seconds: int | None = None,
    ) -> MetricAggregation | None:
        """Get aggregated statistics for a metric over a time window."""
        metric_key = self._build_metric_key(name, labels)

        if metric_key not in self._metrics:
            return None

        window_seconds = window_seconds or self.aggregation_window_seconds
        end_time = time.time()
        start_time = end_time - window_seconds

        values = self._metrics[metric_key].get_values_in_range(start_time, end_time)

        if not values:
            return None

        # Extract numeric values for aggregation
        numeric_values = []
        for value in values:
            if isinstance(value.value, (int, float)):
                numeric_values.append(float(value.value))

        if not numeric_values:
            return None

        # Calculate statistics
        try:
            aggregation = MetricAggregation(
                name=name,
                metric_type=values[0].metric_type,
                count=len(numeric_values),
                min_value=min(numeric_values),
                max_value=max(numeric_values),
                avg_value=mean(numeric_values),
                sum_value=sum(numeric_values),
                median_value=median(numeric_values),
                std_dev=stdev(numeric_values) if len(numeric_values) > 1 else 0,
                labels=labels or {},
                window_start=start_time,
                window_end=end_time,
            )

            # Calculate percentiles if enabled
            if self.enable_percentiles and len(numeric_values) >= 2:
                sorted_values = sorted(numeric_values)
                percentiles = [50, 90, 95, 99]
                for p in percentiles:
                    index = (p / 100.0) * (len(sorted_values) - 1)
                    if index == int(index):
                        aggregation.percentiles[p] = sorted_values[int(index)]
                    else:
                        lower = sorted_values[int(index)]
                        upper = sorted_values[int(index) + 1]
                        aggregation.percentiles[p] = lower + (upper - lower) * (
                            index - int(index)
                        )

            return aggregation

        except Exception as e:
            log.error(f"Error calculating aggregation for {name}: {e}")
            return None

    def get_all_metric_names(self) -> list[str]:
        """Get list of all metric names."""
        with self._lock:
            names = set()
            for metadata in self._metric_metadata.values():
                names.add(metadata["name"])
            return sorted(names)

    def get_metrics_summary(self, window_minutes: int = 5) -> dict[str, Any]:
        """Get comprehensive metrics summary."""
        summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "collection_stats": self._collection_stats.copy(),
            "metrics_count": len(self._metrics),
            "window_minutes": window_minutes,
            "aggregations": {},
        }

        # Get aggregations for all metrics
        window_seconds = window_minutes * 60

        with self._lock:
            for metric_key, metadata in self._metric_metadata.items():
                name = metadata["name"]
                labels = metadata["labels"]

                aggregation = self.get_metric_aggregation(name, labels, window_seconds)

                if aggregation:
                    summary["aggregations"][metric_key] = aggregation.to_dict()

        return summary

    def export_prometheus_format(self) -> str:
        """Export all metrics in Prometheus exposition format."""
        lines = [
            "# Prometheus metrics export from InkedUp Polymarket Bot",
            f"# Timestamp: {datetime.utcnow().isoformat()}",
            "",
        ]

        current_time_ms = int(time.time() * 1000)

        with self._lock:
            # Group metrics by name and type
            metric_groups: dict[str, list[tuple]] = defaultdict(list)

            for metric_key, metadata in self._metric_metadata.items():
                name = metadata["name"]
                metric_type = metadata["type"]
                labels = metadata["labels"]

                # Get recent values
                recent_values = self._metrics[metric_key].get_latest_values(1)
                if recent_values:
                    latest_value = recent_values[-1]
                    metric_groups[name].append((metric_type, latest_value, labels))

            # Export each metric group
            for name, metric_data in sorted(metric_groups.items()):
                if not metric_data:
                    continue

                metric_type = metric_data[0][0]  # Type from first entry

                # Add type declaration
                prometheus_type = {
                    MetricType.COUNTER: "counter",
                    MetricType.GAUGE: "gauge",
                    MetricType.HISTOGRAM: "histogram",
                    MetricType.TIMER: "histogram",
                    MetricType.SET: "gauge",
                }.get(metric_type, "gauge")

                lines.append(f"# TYPE {name} {prometheus_type}")

                # Export values
                for _, value, labels in metric_data:
                    if isinstance(value.value, set):
                        # For sets, export the count
                        metric_value = len(value.value)
                    elif isinstance(value.value, (int, float)):
                        metric_value = value.value
                    else:
                        continue  # Skip non-numeric values

                    # Build labels string
                    if labels:
                        label_pairs = [f'{k}="{v}"' for k, v in sorted(labels.items())]
                        labels_str = f"{{{','.join(label_pairs)}}}"
                    else:
                        labels_str = ""

                    lines.append(f"{name}{labels_str} {metric_value} {current_time_ms}")

                lines.append("")  # Empty line between metrics

        return "\n".join(lines)

    def export_json_format(self, window_minutes: int = 5) -> str:
        """Export metrics in structured JSON format."""
        summary = self.get_metrics_summary(window_minutes)
        return json.dumps(summary, indent=2, default=str)

    def export_influxdb_format(self) -> list[str]:
        """Export metrics in InfluxDB line protocol format."""
        lines = []
        current_time_ns = int(time.time() * 1_000_000_000)

        with self._lock:
            for metric_key, metadata in self._metric_metadata.items():
                name = metadata["name"]
                labels = metadata["labels"]

                # Get latest value
                recent_values = self._metrics[metric_key].get_latest_values(1)
                if not recent_values:
                    continue

                latest_value = recent_values[-1]

                if isinstance(latest_value.value, set):
                    value = len(latest_value.value)
                elif isinstance(latest_value.value, (int, float)):
                    value = latest_value.value
                else:
                    continue

                # Build tags
                tag_pairs = []
                if labels:
                    tag_pairs.extend([f"{k}={v}" for k, v in sorted(labels.items())])

                tags_str = f",{','.join(tag_pairs)}" if tag_pairs else ""

                # Create line protocol entry
                line = f"{name}{tags_str} value={value} {current_time_ns}"
                lines.append(line)

        return lines

    def cleanup_old_metrics(self):
        """Clean up old metric data based on retention policy."""
        with self._lock:
            for metric_key in list(self._metrics.keys()):
                # The MetricsBuffer handles its own cleanup
                buffer = self._metrics[metric_key]

                # Remove empty buffers
                if not buffer.get_latest_values(1):
                    del self._metrics[metric_key]
                    if metric_key in self._metric_metadata:
                        del self._metric_metadata[metric_key]

        log.debug("Completed metrics cleanup")


class TimingContextManager:
    """Context manager for timing operations."""

    def __init__(
        self,
        collector: EnhancedMetricsCollector,
        name: str,
        labels: dict[str, str] | None = None,
        description: str = "",
    ):
        self.collector = collector
        self.name = name
        self.labels = labels
        self.description = description
        self.start_time: float | None = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
            self.collector.timer(self.name, duration_ms, self.labels, self.description)


class MetricsExporter:
    """Service for exporting metrics to external systems."""

    def __init__(self, collector: EnhancedMetricsCollector):
        self.collector = collector
        self.export_tasks: dict[str, asyncio.Task] = {}
        self.export_configs: dict[str, dict[str, Any]] = {}
        self._running = False

    def configure_export(self, name: str, export_type: str, config: dict[str, Any]):
        """Configure an export destination."""
        self.export_configs[name] = {
            "type": export_type,
            "config": config,
            "enabled": config.get("enabled", True),
            "interval_seconds": config.get("interval_seconds", 60),
        }
        log.info(f"Configured metrics export: {name} ({export_type})")

    async def start_exports(self):
        """Start all configured exports."""
        if self._running:
            return

        self._running = True

        for name, export_config in self.export_configs.items():
            if export_config["enabled"]:
                task = asyncio.create_task(self._export_loop(name, export_config))
                self.export_tasks[name] = task

        log.info(f"Started {len(self.export_tasks)} metrics export tasks")

    async def stop_exports(self):
        """Stop all export tasks."""
        if not self._running:
            return

        self._running = False

        for task in self.export_tasks.values():
            task.cancel()

        await asyncio.gather(*self.export_tasks.values(), return_exceptions=True)
        self.export_tasks.clear()

        log.info("Stopped all metrics export tasks")

    async def _export_loop(self, name: str, export_config: dict[str, Any]):
        """Background loop for metrics export."""
        interval = export_config["interval_seconds"]
        export_type = export_config["type"]

        while self._running:
            try:
                if export_type == "prometheus_file":
                    await self._export_prometheus_file(export_config["config"])
                elif export_type == "json_file":
                    await self._export_json_file(export_config["config"])
                elif export_type == "influxdb":
                    await self._export_influxdb(export_config["config"])

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in export loop {name}: {e}")
                await asyncio.sleep(10)  # Brief pause before retry

    async def _export_prometheus_file(self, config: dict[str, Any]):
        """Export to Prometheus format file."""
        file_path = config["file_path"]
        prometheus_data = self.collector.export_prometheus_format()

        with open(file_path, "w") as f:
            f.write(prometheus_data)

    async def _export_json_file(self, config: dict[str, Any]):
        """Export to JSON format file."""
        file_path = config["file_path"]
        window_minutes = config.get("window_minutes", 5)
        json_data = self.collector.export_json_format(window_minutes)

        with open(file_path, "w") as f:
            f.write(json_data)

    async def _export_influxdb(self, config: dict[str, Any]):
        """Export to InfluxDB."""
        # This would implement actual InfluxDB client integration
        lines = self.collector.export_influxdb_format()
        log.debug(f"Would export {len(lines)} metrics to InfluxDB")
        # Implementation would use influxdb client to send data
