"""
Comprehensive metrics collection framework.

This module provides detailed metrics collection for trading operations,
system performance, database operations, and all other system components.
"""

import logging
import statistics
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics that can be collected."""

    COUNTER = "counter"  # Monotonically increasing values
    GAUGE = "gauge"  # Current value at a point in time
    HISTOGRAM = "histogram"  # Distribution of values
    TIMER = "timer"  # Duration measurements
    RATE = "rate"  # Events per time period


@dataclass
class MetricValue:
    """A single metric value with metadata."""

    timestamp: float
    value: float
    tags: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


@dataclass
class MetricSummary:
    """Summary statistics for a metric."""

    name: str
    metric_type: MetricType
    count: int
    sum: float
    min_value: float
    max_value: float
    mean: float
    percentiles: dict[float, float] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)


class Metric(ABC):
    """Base class for all metrics."""

    def __init__(
        self, name: str, description: str = "", tags: dict[str, str] | None = None
    ):
        self.name = name
        self.description = description
        self.tags = tags or {}
        self.created_at = time.time()
        self.last_updated = time.time()
        self.lock = threading.RLock()

    @abstractmethod
    def record(self, value: float, tags: dict[str, str] | None = None):
        """Record a metric value."""
        pass

    @abstractmethod
    def get_summary(self) -> MetricSummary:
        """Get summary statistics for this metric."""
        pass

    def _merge_tags(self, additional_tags: dict[str, str] | None) -> dict[str, str]:
        """Merge metric tags with additional tags."""
        merged = self.tags.copy()
        if additional_tags:
            merged.update(additional_tags)
        return merged


class Counter(Metric):
    """Counter metric - monotonically increasing value."""

    def __init__(
        self, name: str, description: str = "", tags: dict[str, str] | None = None
    ):
        super().__init__(name, description, tags)
        self.value = 0.0
        self.history: deque = deque(maxlen=1000)

    def record(self, value: float = 1.0, tags: dict[str, str] | None = None):
        """Increment the counter."""
        with self.lock:
            self.value += abs(value)  # Ensure monotonic increase
            self.last_updated = time.time()

            self.history.append(
                MetricValue(
                    timestamp=self.last_updated,
                    value=value,
                    tags=self._merge_tags(tags),
                )
            )

    def get_value(self) -> float:
        """Get current counter value."""
        with self.lock:
            return self.value

    def get_summary(self) -> MetricSummary:
        """Get counter summary."""
        with self.lock:
            return MetricSummary(
                name=self.name,
                metric_type=MetricType.COUNTER,
                count=len(self.history),
                sum=self.value,
                min_value=0.0,
                max_value=self.value,
                mean=self.value / max(len(self.history), 1),
                tags=self.tags,
                last_updated=self.last_updated,
            )


class Gauge(Metric):
    """Gauge metric - current value at a point in time."""

    def __init__(
        self, name: str, description: str = "", tags: dict[str, str] | None = None
    ):
        super().__init__(name, description, tags)
        self.value = 0.0
        self.history: deque = deque(maxlen=1000)

    def record(self, value: float, tags: dict[str, str] | None = None):
        """Set the gauge value."""
        with self.lock:
            self.value = value
            self.last_updated = time.time()

            self.history.append(
                MetricValue(
                    timestamp=self.last_updated,
                    value=value,
                    tags=self._merge_tags(tags),
                )
            )

    def get_value(self) -> float:
        """Get current gauge value."""
        with self.lock:
            return self.value

    def get_summary(self) -> MetricSummary:
        """Get gauge summary."""
        with self.lock:
            if not self.history:
                return MetricSummary(
                    name=self.name,
                    metric_type=MetricType.GAUGE,
                    count=0,
                    sum=0.0,
                    min_value=0.0,
                    max_value=0.0,
                    mean=0.0,
                    tags=self.tags,
                    last_updated=self.last_updated,
                )

            values = [entry.value for entry in self.history]
            return MetricSummary(
                name=self.name,
                metric_type=MetricType.GAUGE,
                count=len(values),
                sum=sum(values),
                min_value=min(values),
                max_value=max(values),
                mean=statistics.mean(values),
                tags=self.tags,
                last_updated=self.last_updated,
            )


class Histogram(Metric):
    """Histogram metric - distribution of values."""

    def __init__(
        self,
        name: str,
        description: str = "",
        buckets: list[float] | None = None,
        tags: dict[str, str] | None = None,
    ):
        super().__init__(name, description, tags)
        self.buckets = buckets or [
            0.005,
            0.01,
            0.025,
            0.05,
            0.1,
            0.25,
            0.5,
            1.0,
            2.5,
            5.0,
            10.0,
        ]
        self.bucket_counts: dict[float, int] = {bucket: 0 for bucket in self.buckets}
        self.values: deque = deque(maxlen=10000)
        self.count = 0
        self.sum = 0.0

    def record(self, value: float, tags: dict[str, str] | None = None):
        """Record a value in the histogram."""
        with self.lock:
            self.values.append(
                MetricValue(
                    timestamp=time.time(), value=value, tags=self._merge_tags(tags)
                )
            )

            self.count += 1
            self.sum += value
            self.last_updated = time.time()

            # Update bucket counts
            for bucket in self.buckets:
                if value <= bucket:
                    self.bucket_counts[bucket] += 1

    def get_summary(self) -> MetricSummary:
        """Get histogram summary with percentiles."""
        with self.lock:
            if not self.values:
                return MetricSummary(
                    name=self.name,
                    metric_type=MetricType.HISTOGRAM,
                    count=0,
                    sum=0.0,
                    min_value=0.0,
                    max_value=0.0,
                    mean=0.0,
                    tags=self.tags,
                    last_updated=self.last_updated,
                )

            values = [entry.value for entry in self.values]
            sorted_values = sorted(values)

            # Calculate percentiles
            percentiles = {}
            for p in [50, 90, 95, 99]:
                percentiles[p] = self._percentile(sorted_values, p)

            return MetricSummary(
                name=self.name,
                metric_type=MetricType.HISTOGRAM,
                count=len(values),
                sum=sum(values),
                min_value=min(values),
                max_value=max(values),
                mean=statistics.mean(values),
                percentiles=percentiles,
                tags=self.tags,
                last_updated=self.last_updated,
            )

    def get_buckets(self) -> dict[float, int]:
        """Get bucket counts."""
        with self.lock:
            return self.bucket_counts.copy()

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


class Timer(Histogram):
    """Timer metric - specialized histogram for duration measurements."""

    def __init__(
        self, name: str, description: str = "", tags: dict[str, str] | None = None
    ):
        # Use timer-specific buckets (in seconds)
        timer_buckets = [
            0.001,
            0.005,
            0.01,
            0.025,
            0.05,
            0.1,
            0.25,
            0.5,
            1.0,
            2.5,
            5.0,
            10.0,
        ]
        super().__init__(name, description, timer_buckets, tags)
        self.active_timers: dict[str, float] = {}

    def start_timer(self, timer_id: str = "default") -> str:
        """Start a timer and return timer ID."""
        timer_key = f"{self.name}:{timer_id}"
        self.active_timers[timer_key] = time.time()
        return timer_key

    def stop_timer(
        self, timer_id: str = "default", tags: dict[str, str] | None = None
    ) -> float:
        """Stop a timer and record the duration."""
        timer_key = f"{self.name}:{timer_id}"

        if timer_key not in self.active_timers:
            logger.warning(f"Timer '{timer_key}' was not started")
            return 0.0

        duration = time.time() - self.active_timers[timer_key]
        del self.active_timers[timer_key]

        self.record(duration, tags)
        return duration

    def time_context(self, tags: dict[str, str] | None = None):
        """Context manager for timing operations."""
        return TimerContext(self, tags)


class TimerContext:
    """Context manager for timing operations."""

    def __init__(self, timer: Timer, tags: dict[str, str] | None = None):
        self.timer = timer
        self.tags = tags
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time
            self.timer.record(duration, self.tags)


class TradingMetrics:
    """Specialized metrics for trading operations."""

    def __init__(self):
        # Order metrics
        self.orders_placed = Counter("orders_placed", "Total orders placed")
        self.orders_filled = Counter("orders_filled", "Total orders filled")
        self.orders_cancelled = Counter("orders_cancelled", "Total orders cancelled")
        self.orders_failed = Counter("orders_failed", "Total orders that failed")

        # Order timing
        self.order_placement_time = Timer(
            "order_placement_time", "Time to place orders"
        )
        self.order_fill_time = Timer("order_fill_time", "Time from placement to fill")

        # Position metrics
        self.positions_opened = Counter("positions_opened", "Total positions opened")
        self.positions_closed = Counter("positions_closed", "Total positions closed")
        self.current_positions = Gauge(
            "current_positions", "Current number of open positions"
        )

        # P&L metrics
        self.realized_pnl = Gauge("realized_pnl", "Realized P&L in USD")
        self.unrealized_pnl = Gauge("unrealized_pnl", "Unrealized P&L in USD")
        self.total_exposure = Gauge("total_exposure", "Total position exposure in USD")

        # Risk metrics
        self.max_drawdown = Gauge("max_drawdown", "Maximum drawdown")
        self.risk_limit_breaches = Counter(
            "risk_limit_breaches", "Risk limit violations"
        )

        # Market data metrics
        self.market_data_updates = Counter(
            "market_data_updates", "Market data updates received"
        )
        self.market_data_latency = Timer(
            "market_data_latency", "Market data processing latency"
        )

        # Strategy metrics
        self.strategy_signals = Counter(
            "strategy_signals", "Strategy signals generated"
        )
        self.strategy_execution_time = Timer(
            "strategy_execution_time", "Strategy execution time"
        )

        self.metrics = {
            # Orders
            "orders_placed": self.orders_placed,
            "orders_filled": self.orders_filled,
            "orders_cancelled": self.orders_cancelled,
            "orders_failed": self.orders_failed,
            "order_placement_time": self.order_placement_time,
            "order_fill_time": self.order_fill_time,
            # Positions
            "positions_opened": self.positions_opened,
            "positions_closed": self.positions_closed,
            "current_positions": self.current_positions,
            # P&L
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "total_exposure": self.total_exposure,
            # Risk
            "max_drawdown": self.max_drawdown,
            "risk_limit_breaches": self.risk_limit_breaches,
            # Market data
            "market_data_updates": self.market_data_updates,
            "market_data_latency": self.market_data_latency,
            # Strategy
            "strategy_signals": self.strategy_signals,
            "strategy_execution_time": self.strategy_execution_time,
        }

    def record_order_placed(self, order_type: str, market: str, amount: float):
        """Record an order placement."""
        tags = {"type": order_type, "market": market}
        self.orders_placed.record(1, tags)

        # Record order size distribution
        size_histogram = self.get_or_create_histogram(
            "order_sizes", "Order size distribution"
        )
        size_histogram.record(amount, tags)

    def record_order_filled(self, order_type: str, market: str, fill_time: float):
        """Record an order fill."""
        tags = {"type": order_type, "market": market}
        self.orders_filled.record(1, tags)
        self.order_fill_time.record(fill_time, tags)

    def record_pnl_update(
        self, realized_pnl: float, unrealized_pnl: float, total_exposure: float
    ):
        """Record P&L and exposure update."""
        self.realized_pnl.record(realized_pnl)
        self.unrealized_pnl.record(unrealized_pnl)
        self.total_exposure.record(total_exposure)

    def record_strategy_signal(
        self, strategy_name: str, signal_type: str, execution_time: float
    ):
        """Record strategy signal generation."""
        tags = {"strategy": strategy_name, "signal_type": signal_type}
        self.strategy_signals.record(1, tags)
        self.strategy_execution_time.record(execution_time, tags)

    def get_or_create_histogram(self, name: str, description: str) -> Histogram:
        """Get or create a histogram metric."""
        if name not in self.metrics:
            self.metrics[name] = Histogram(name, description)
        return self.metrics[name]

    def get_all_metrics(self) -> dict[str, Metric]:
        """Get all trading metrics."""
        return self.metrics.copy()


class SystemMetrics:
    """System-level metrics for monitoring infrastructure."""

    def __init__(self):
        # CPU and memory
        self.cpu_usage = Gauge("cpu_usage_percent", "CPU usage percentage")
        self.memory_usage = Gauge("memory_usage_percent", "Memory usage percentage")
        self.memory_used_mb = Gauge("memory_used_mb", "Memory used in MB")

        # Disk
        self.disk_usage = Gauge("disk_usage_percent", "Disk usage percentage")
        self.disk_free_gb = Gauge("disk_free_gb", "Free disk space in GB")

        # Network
        self.network_bytes_sent = Counter("network_bytes_sent", "Network bytes sent")
        self.network_bytes_received = Counter(
            "network_bytes_received", "Network bytes received"
        )

        # Process metrics
        self.process_cpu_percent = Gauge("process_cpu_percent", "Process CPU usage")
        self.process_memory_mb = Gauge(
            "process_memory_mb", "Process memory usage in MB"
        )
        self.open_connections = Gauge("open_connections", "Number of open connections")

        # Application metrics
        self.requests_total = Counter("requests_total", "Total HTTP requests")
        self.request_duration = Timer("request_duration", "HTTP request duration")
        self.errors_total = Counter("errors_total", "Total errors")

        self.metrics = {
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "memory_used_mb": self.memory_used_mb,
            "disk_usage": self.disk_usage,
            "disk_free_gb": self.disk_free_gb,
            "network_bytes_sent": self.network_bytes_sent,
            "network_bytes_received": self.network_bytes_received,
            "process_cpu_percent": self.process_cpu_percent,
            "process_memory_mb": self.process_memory_mb,
            "open_connections": self.open_connections,
            "requests_total": self.requests_total,
            "request_duration": self.request_duration,
            "errors_total": self.errors_total,
        }

    def update_system_stats(
        self,
        cpu_percent: float,
        memory_percent: float,
        memory_mb: float,
        disk_percent: float,
        disk_free_gb: float,
    ):
        """Update system resource metrics."""
        self.cpu_usage.record(cpu_percent)
        self.memory_usage.record(memory_percent)
        self.memory_used_mb.record(memory_mb)
        self.disk_usage.record(disk_percent)
        self.disk_free_gb.record(disk_free_gb)

    def update_process_stats(
        self, cpu_percent: float, memory_mb: float, connections: int
    ):
        """Update process-specific metrics."""
        self.process_cpu_percent.record(cpu_percent)
        self.process_memory_mb.record(memory_mb)
        self.open_connections.record(connections)

    def record_request(
        self, method: str, endpoint: str, status_code: int, duration: float
    ):
        """Record HTTP request metrics."""
        tags = {"method": method, "endpoint": endpoint, "status": str(status_code)}
        self.requests_total.record(1, tags)
        self.request_duration.record(duration, tags)

        if status_code >= 400:
            self.errors_total.record(1, tags)

    def get_all_metrics(self) -> dict[str, Metric]:
        """Get all system metrics."""
        return self.metrics.copy()


class DatabaseMetrics:
    """Database-specific metrics."""

    def __init__(self):
        # Connection metrics
        self.connections_active = Gauge(
            "db_connections_active", "Active database connections"
        )
        self.connections_total = Counter(
            "db_connections_total", "Total database connections"
        )
        self.connection_errors = Counter(
            "db_connection_errors", "Database connection errors"
        )

        # Query metrics
        self.queries_total = Counter("db_queries_total", "Total database queries")
        self.query_duration = Timer("db_query_duration", "Database query duration")
        self.slow_queries = Counter("db_slow_queries", "Slow database queries")

        # Transaction metrics
        self.transactions_total = Counter(
            "db_transactions_total", "Total database transactions"
        )
        self.transaction_duration = Timer(
            "db_transaction_duration", "Transaction duration"
        )
        self.transaction_rollbacks = Counter(
            "db_transaction_rollbacks", "Transaction rollbacks"
        )

        # Lock metrics
        self.lock_waits = Counter("db_lock_waits", "Database lock waits")
        self.lock_timeouts = Counter("db_lock_timeouts", "Database lock timeouts")

        self.metrics = {
            "connections_active": self.connections_active,
            "connections_total": self.connections_total,
            "connection_errors": self.connection_errors,
            "queries_total": self.queries_total,
            "query_duration": self.query_duration,
            "slow_queries": self.slow_queries,
            "transactions_total": self.transactions_total,
            "transaction_duration": self.transaction_duration,
            "transaction_rollbacks": self.transaction_rollbacks,
            "lock_waits": self.lock_waits,
            "lock_timeouts": self.lock_timeouts,
        }

    def record_query(self, query_type: str, duration: float, success: bool = True):
        """Record database query metrics."""
        tags = {"type": query_type, "success": str(success)}
        self.queries_total.record(1, tags)
        self.query_duration.record(duration, tags)

        if duration > 1.0:  # Slow query threshold
            self.slow_queries.record(1, tags)

    def record_transaction(self, duration: float, success: bool = True):
        """Record database transaction metrics."""
        tags = {"success": str(success)}
        self.transactions_total.record(1, tags)
        self.transaction_duration.record(duration, tags)

        if not success:
            self.transaction_rollbacks.record(1, tags)

    def update_connection_count(self, active_connections: int):
        """Update active connection count."""
        self.connections_active.record(active_connections)

    def get_all_metrics(self) -> dict[str, Metric]:
        """Get all database metrics."""
        return self.metrics.copy()
