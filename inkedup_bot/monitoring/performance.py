"""
Performance monitoring system for trading operations and system components.

This module provides detailed performance tracking including latency monitoring,
throughput analysis, resource utilization, and trading performance analytics.
"""

import asyncio
import logging
import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psutil

logger = logging.getLogger(__name__)


@dataclass
class PerformanceSnapshot:
    """Point-in-time performance metrics snapshot."""

    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_mb: float
    disk_io_read: int
    disk_io_write: int
    network_bytes_sent: int
    network_bytes_recv: int
    open_connections: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_mb": self.memory_mb,
            "disk_io_read": self.disk_io_read,
            "disk_io_write": self.disk_io_write,
            "network_bytes_sent": self.network_bytes_sent,
            "network_bytes_recv": self.network_bytes_recv,
            "open_connections": self.open_connections,
        }


class LatencyTracker:
    """Tracks latency for various operations with percentile calculations."""

    def __init__(self, name: str, max_samples: int = 10000):
        self.name = name
        self.max_samples = max_samples
        self.latencies: deque = deque(maxlen=max_samples)
        self.lock = threading.RLock()

        # Pre-computed percentiles for efficiency
        self._percentiles_cache = {}
        self._cache_time = 0
        self._cache_ttl = 60  # Cache for 60 seconds

    def record_latency(self, latency_ms: float, tags: dict[str, str] | None = None):
        """Record a latency measurement."""
        with self.lock:
            entry = {
                "timestamp": time.time(),
                "latency_ms": latency_ms,
                "tags": tags or {},
            }
            self.latencies.append(entry)

            # Invalidate cache
            self._percentiles_cache.clear()

    def get_percentiles(self, percentiles: list[float] = None) -> dict[float, float]:
        """Get latency percentiles."""
        if percentiles is None:
            percentiles = [50, 90, 95, 99, 99.9]

        with self.lock:
            # Check cache
            cache_key = tuple(sorted(percentiles))
            current_time = time.time()

            if (
                cache_key in self._percentiles_cache
                and current_time - self._cache_time < self._cache_ttl
            ):
                return self._percentiles_cache[cache_key].copy()

            if not self.latencies:
                return {p: 0.0 for p in percentiles}

            # Extract latency values
            latency_values = [entry["latency_ms"] for entry in self.latencies]
            sorted_latencies = sorted(latency_values)

            # Calculate percentiles
            result = {}
            for p in percentiles:
                result[p] = self._calculate_percentile(sorted_latencies, p)

            # Cache result
            self._percentiles_cache[cache_key] = result.copy()
            self._cache_time = current_time

            return result

    def get_summary(self) -> dict[str, Any]:
        """Get comprehensive latency summary."""
        with self.lock:
            if not self.latencies:
                return {
                    "name": self.name,
                    "count": 0,
                    "min": 0.0,
                    "max": 0.0,
                    "mean": 0.0,
                    "percentiles": {},
                }

            latency_values = [entry["latency_ms"] for entry in self.latencies]
            percentiles = self.get_percentiles()

            return {
                "name": self.name,
                "count": len(latency_values),
                "min": min(latency_values),
                "max": max(latency_values),
                "mean": statistics.mean(latency_values),
                "stddev": (
                    statistics.stdev(latency_values) if len(latency_values) > 1 else 0.0
                ),
                "percentiles": percentiles,
            }

    def get_recent_latencies(self, minutes: int = 5) -> list[dict[str, Any]]:
        """Get recent latencies within the specified time window."""
        with self.lock:
            cutoff_time = time.time() - (minutes * 60)
            return [
                entry for entry in self.latencies if entry["timestamp"] >= cutoff_time
            ]

    def _calculate_percentile(
        self, sorted_values: list[float], percentile: float
    ) -> float:
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


class ThroughputMonitor:
    """Monitors throughput (events per second) for various operations."""

    def __init__(self, name: str, window_size_seconds: int = 60):
        self.name = name
        self.window_size = window_size_seconds
        self.events: deque = deque()
        self.lock = threading.RLock()

        # Cached throughput values
        self._cached_throughput = 0.0
        self._cache_time = 0
        self._cache_ttl = 5  # Cache for 5 seconds

    def record_event(self, count: int = 1, tags: dict[str, str] | None = None):
        """Record throughput events."""
        with self.lock:
            current_time = time.time()
            entry = {"timestamp": current_time, "count": count, "tags": tags or {}}
            self.events.append(entry)

            # Clean old events
            cutoff_time = current_time - self.window_size
            while self.events and self.events[0]["timestamp"] < cutoff_time:
                self.events.popleft()

            # Invalidate cache
            self._cached_throughput = 0.0

    def get_throughput(self) -> float:
        """Get current throughput (events per second)."""
        with self.lock:
            current_time = time.time()

            # Check cache
            if (
                self._cached_throughput > 0
                and current_time - self._cache_time < self._cache_ttl
            ):
                return self._cached_throughput

            # Clean old events
            cutoff_time = current_time - self.window_size
            while self.events and self.events[0]["timestamp"] < cutoff_time:
                self.events.popleft()

            if not self.events:
                self._cached_throughput = 0.0
            else:
                total_events = sum(event["count"] for event in self.events)
                actual_window = current_time - self.events[0]["timestamp"]
                self._cached_throughput = total_events / max(actual_window, 1.0)

            self._cache_time = current_time
            return self._cached_throughput

    def get_summary(self) -> dict[str, Any]:
        """Get throughput summary with statistics."""
        with self.lock:
            current_throughput = self.get_throughput()
            total_events = sum(event["count"] for event in self.events)

            # Calculate throughput over different time windows
            throughput_1m = self._get_throughput_for_window(60)
            throughput_5m = self._get_throughput_for_window(300)
            throughput_15m = self._get_throughput_for_window(900)

            return {
                "name": self.name,
                "current_throughput": current_throughput,
                "total_events": total_events,
                "throughput_1m": throughput_1m,
                "throughput_5m": throughput_5m,
                "throughput_15m": throughput_15m,
                "window_size_seconds": self.window_size,
            }

    def _get_throughput_for_window(self, window_seconds: int) -> float:
        """Calculate throughput for a specific time window."""
        current_time = time.time()
        cutoff_time = current_time - window_seconds

        relevant_events = [
            event for event in self.events if event["timestamp"] >= cutoff_time
        ]

        if not relevant_events:
            return 0.0

        total_events = sum(event["count"] for event in relevant_events)
        actual_window = current_time - relevant_events[0]["timestamp"]
        return total_events / max(actual_window, 1.0)


class ResourceMonitor:
    """Monitors system resource utilization."""

    def __init__(self, collection_interval: float = 10.0):
        self.collection_interval = collection_interval
        self.snapshots: deque = deque(maxlen=8640)  # 24 hours at 10s intervals
        self.is_running = False
        self.monitor_task = None
        self.lock = threading.RLock()

        # Resource usage trends
        self.cpu_history: deque = deque(maxlen=360)  # 1 hour at 10s intervals
        self.memory_history: deque = deque(maxlen=360)
        self.disk_io_history: deque = deque(maxlen=360)
        self.network_io_history: deque = deque(maxlen=360)

        # Process reference
        self.process = psutil.Process()

    async def start_monitoring(self):
        """Start resource monitoring."""
        if self.is_running:
            logger.warning("Resource monitoring already running")
            return

        self.is_running = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Resource monitoring started")

    async def stop_monitoring(self):
        """Stop resource monitoring."""
        if not self.is_running:
            return

        self.is_running = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("Resource monitoring stopped")

    def get_current_snapshot(self) -> PerformanceSnapshot:
        """Get current system resource snapshot."""
        try:
            # System-wide metrics
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk_io = psutil.disk_io_counters()
            network_io = psutil.net_io_counters()

            # Process-specific metrics
            process_memory = self.process.memory_info()
            connections = len(psutil.net_connections())

            return PerformanceSnapshot(
                timestamp=time.time(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_mb=process_memory.rss / (1024 * 1024),
                disk_io_read=disk_io.read_bytes if disk_io else 0,
                disk_io_write=disk_io.write_bytes if disk_io else 0,
                network_bytes_sent=network_io.bytes_sent if network_io else 0,
                network_bytes_recv=network_io.bytes_recv if network_io else 0,
                open_connections=connections,
            )

        except Exception as e:
            logger.error(f"Error collecting resource snapshot: {e}")
            return PerformanceSnapshot(
                timestamp=time.time(),
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_mb=0.0,
                disk_io_read=0,
                disk_io_write=0,
                network_bytes_sent=0,
                network_bytes_recv=0,
                open_connections=0,
            )

    def get_resource_summary(self) -> dict[str, Any]:
        """Get comprehensive resource utilization summary."""
        with self.lock:
            current = self.get_current_snapshot()

            # Calculate trends if we have history
            cpu_trend = self._calculate_trend(self.cpu_history)
            memory_trend = self._calculate_trend(self.memory_history)

            # Get recent averages
            recent_snapshots = [
                s for s in self.snapshots if s.timestamp > time.time() - 300
            ]  # 5 min

            avg_cpu = (
                statistics.mean([s.cpu_percent for s in recent_snapshots])
                if recent_snapshots
                else current.cpu_percent
            )
            avg_memory = (
                statistics.mean([s.memory_percent for s in recent_snapshots])
                if recent_snapshots
                else current.memory_percent
            )

            return {
                "current": current.to_dict(),
                "averages_5m": {
                    "cpu_percent": avg_cpu,
                    "memory_percent": avg_memory,
                },
                "trends": {"cpu_trend": cpu_trend, "memory_trend": memory_trend},
                "alerts": self._generate_resource_alerts(current, avg_cpu, avg_memory),
                "snapshots_collected": len(self.snapshots),
            }

    def get_resource_history(self, hours: int = 1) -> list[dict[str, Any]]:
        """Get resource history for the specified number of hours."""
        with self.lock:
            cutoff_time = time.time() - (hours * 3600)
            return [s.to_dict() for s in self.snapshots if s.timestamp >= cutoff_time]

    async def _monitoring_loop(self):
        """Main resource monitoring loop."""
        logger.info("Starting resource monitoring loop")

        try:
            while self.is_running:
                snapshot = self.get_current_snapshot()

                with self.lock:
                    self.snapshots.append(snapshot)

                    # Update trend histories
                    self.cpu_history.append(snapshot.cpu_percent)
                    self.memory_history.append(snapshot.memory_percent)

                    # Calculate disk I/O rate
                    if len(self.snapshots) > 1:
                        prev_snapshot = self.snapshots[-2]
                        time_diff = snapshot.timestamp - prev_snapshot.timestamp

                        if time_diff > 0:
                            disk_read_rate = (
                                snapshot.disk_io_read - prev_snapshot.disk_io_read
                            ) / time_diff
                            disk_write_rate = (
                                snapshot.disk_io_write - prev_snapshot.disk_io_write
                            ) / time_diff
                            self.disk_io_history.append(
                                (disk_read_rate, disk_write_rate)
                            )

                            network_send_rate = (
                                snapshot.network_bytes_sent
                                - prev_snapshot.network_bytes_sent
                            ) / time_diff
                            network_recv_rate = (
                                snapshot.network_bytes_recv
                                - prev_snapshot.network_bytes_recv
                            ) / time_diff
                            self.network_io_history.append(
                                (network_send_rate, network_recv_rate)
                            )

                await asyncio.sleep(self.collection_interval)

        except asyncio.CancelledError:
            logger.info("Resource monitoring loop cancelled")
        except Exception as e:
            logger.error(f"Resource monitoring loop error: {e}")

    def _calculate_trend(self, history: deque) -> str:
        """Calculate trend from historical data."""
        if len(history) < 10:
            return "insufficient_data"

        recent = list(history)[-10:]
        early = list(history)[:10]

        recent_avg = statistics.mean(recent)
        early_avg = statistics.mean(early)

        diff_percent = (
            ((recent_avg - early_avg) / early_avg) * 100 if early_avg > 0 else 0
        )

        if diff_percent > 10:
            return "increasing"
        elif diff_percent < -10:
            return "decreasing"
        else:
            return "stable"

    def _generate_resource_alerts(
        self, current: PerformanceSnapshot, avg_cpu: float, avg_memory: float
    ) -> list[str]:
        """Generate resource utilization alerts."""
        alerts = []

        # CPU alerts
        if current.cpu_percent > 90:
            alerts.append(f"Critical CPU usage: {current.cpu_percent:.1f}%")
        elif current.cpu_percent > 75:
            alerts.append(f"High CPU usage: {current.cpu_percent:.1f}%")

        # Memory alerts
        if current.memory_percent > 90:
            alerts.append(f"Critical memory usage: {current.memory_percent:.1f}%")
        elif current.memory_percent > 75:
            alerts.append(f"High memory usage: {current.memory_percent:.1f}%")

        # Process memory alerts
        if current.memory_mb > 1000:
            alerts.append(f"High process memory: {current.memory_mb:.1f}MB")

        return alerts


class TradingPerformanceTracker:
    """Specialized performance tracking for trading operations."""

    def __init__(self):
        # Latency trackers
        self.order_placement_latency = LatencyTracker("order_placement")
        self.market_data_latency = LatencyTracker("market_data_processing")
        self.strategy_execution_latency = LatencyTracker("strategy_execution")

        # Throughput monitors
        self.order_throughput = ThroughputMonitor("orders")
        self.market_data_throughput = ThroughputMonitor("market_data_updates")
        self.trade_throughput = ThroughputMonitor("trades")

        # Trading-specific metrics
        self.fill_rates = defaultdict(list)  # Fill rates by market
        self.slippage_tracking = defaultdict(list)  # Price slippage tracking
        self.strategy_performance = defaultdict(dict)  # Performance by strategy

        # Performance snapshots
        self.performance_snapshots: deque = deque(
            maxlen=1440
        )  # 24 hours at 1min intervals

        self.lock = threading.RLock()

    def record_order_performance(
        self,
        order_id: str,
        market: str,
        order_type: str,
        placement_latency: float,
        fill_time: float | None = None,
        expected_price: float | None = None,
        actual_price: float | None = None,
    ):
        """Record comprehensive order performance metrics."""
        with self.lock:
            # Record latency
            tags = {"market": market, "type": order_type}
            self.order_placement_latency.record_latency(placement_latency, tags)

            # Record throughput
            self.order_throughput.record_event(1, tags)

            # Calculate fill rate
            if fill_time is not None:
                self.fill_rates[market].append(
                    {
                        "timestamp": time.time(),
                        "order_id": order_id,
                        "fill_time": fill_time,
                        "order_type": order_type,
                    }
                )

                # Keep only recent data
                cutoff_time = time.time() - 3600  # 1 hour
                self.fill_rates[market] = [
                    entry
                    for entry in self.fill_rates[market]
                    if entry["timestamp"] >= cutoff_time
                ]

            # Calculate slippage
            if expected_price is not None and actual_price is not None:
                slippage = abs(actual_price - expected_price) / expected_price * 100
                self.slippage_tracking[market].append(
                    {
                        "timestamp": time.time(),
                        "order_id": order_id,
                        "expected_price": expected_price,
                        "actual_price": actual_price,
                        "slippage_percent": slippage,
                    }
                )

                # Keep only recent data
                cutoff_time = time.time() - 3600
                self.slippage_tracking[market] = [
                    entry
                    for entry in self.slippage_tracking[market]
                    if entry["timestamp"] >= cutoff_time
                ]

    def record_strategy_performance(
        self, strategy_name: str, execution_time: float, signal_type: str, success: bool
    ):
        """Record strategy execution performance."""
        with self.lock:
            tags = {
                "strategy": strategy_name,
                "signal_type": signal_type,
                "success": str(success),
            }
            self.strategy_execution_latency.record_latency(execution_time, tags)

            # Update strategy performance tracking
            if strategy_name not in self.strategy_performance:
                self.strategy_performance[strategy_name] = {
                    "total_signals": 0,
                    "successful_signals": 0,
                    "execution_times": deque(maxlen=1000),
                    "signal_types": defaultdict(int),
                }

            strategy_stats = self.strategy_performance[strategy_name]
            strategy_stats["total_signals"] += 1
            if success:
                strategy_stats["successful_signals"] += 1

            strategy_stats["execution_times"].append(execution_time)
            strategy_stats["signal_types"][signal_type] += 1

    def record_market_data_performance(
        self, market: str, processing_time: float, update_type: str, data_age_ms: float
    ):
        """Record market data processing performance."""
        with self.lock:
            tags = {"market": market, "type": update_type}
            self.market_data_latency.record_latency(processing_time, tags)
            self.market_data_throughput.record_event(1, tags)

            # Track data freshness
            if hasattr(self, "data_freshness"):
                self.data_freshness[market].append(
                    {
                        "timestamp": time.time(),
                        "age_ms": data_age_ms,
                        "update_type": update_type,
                    }
                )
            else:
                self.data_freshness = defaultdict(lambda: deque(maxlen=1000))
                self.data_freshness[market].append(
                    {
                        "timestamp": time.time(),
                        "age_ms": data_age_ms,
                        "update_type": update_type,
                    }
                )

    def get_trading_performance_summary(self) -> dict[str, Any]:
        """Get comprehensive trading performance summary."""
        with self.lock:
            summary = {
                "timestamp": datetime.now().isoformat(),
                "latency_metrics": {
                    "order_placement": self.order_placement_latency.get_summary(),
                    "market_data_processing": self.market_data_latency.get_summary(),
                    "strategy_execution": self.strategy_execution_latency.get_summary(),
                },
                "throughput_metrics": {
                    "orders": self.order_throughput.get_summary(),
                    "market_data_updates": self.market_data_throughput.get_summary(),
                    "trades": self.trade_throughput.get_summary(),
                },
                "fill_rates": {},
                "slippage_analysis": {},
                "strategy_performance": {},
            }

            # Calculate fill rates by market
            for market, fills in self.fill_rates.items():
                if fills:
                    avg_fill_time = statistics.mean([f["fill_time"] for f in fills])
                    fill_rate = (
                        len([f for f in fills if f["fill_time"] < 10.0])
                        / len(fills)
                        * 100
                    )
                    summary["fill_rates"][market] = {
                        "average_fill_time": avg_fill_time,
                        "fill_rate_under_10s": fill_rate,
                        "total_orders": len(fills),
                    }

            # Calculate slippage analysis
            for market, slippages in self.slippage_tracking.items():
                if slippages:
                    slippage_values = [s["slippage_percent"] for s in slippages]
                    summary["slippage_analysis"][market] = {
                        "average_slippage": statistics.mean(slippage_values),
                        "max_slippage": max(slippage_values),
                        "slippage_95th_percentile": self._percentile(
                            sorted(slippage_values), 95
                        ),
                        "orders_analyzed": len(slippages),
                    }

            # Strategy performance summary
            for strategy_name, stats in self.strategy_performance.items():
                if stats["total_signals"] > 0:
                    success_rate = (
                        stats["successful_signals"] / stats["total_signals"]
                    ) * 100
                    avg_execution_time = statistics.mean(list(stats["execution_times"]))

                    summary["strategy_performance"][strategy_name] = {
                        "success_rate": success_rate,
                        "average_execution_time": avg_execution_time,
                        "total_signals": stats["total_signals"],
                        "signal_types": dict(stats["signal_types"]),
                    }

            return summary

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


class PerformanceMonitor:
    """Comprehensive performance monitoring system coordinator."""

    def __init__(self, collection_interval: float = 10.0):
        # Core monitoring components
        self.resource_monitor = ResourceMonitor(collection_interval)
        self.trading_performance = TradingPerformanceTracker()

        # System-level latency and throughput tracking
        self.system_latency = LatencyTracker("system_operations")
        self.system_throughput = ThroughputMonitor("system_events")

        # Performance alerts and thresholds
        self.alert_thresholds = {
            "cpu_critical": 90.0,
            "cpu_warning": 75.0,
            "memory_critical": 90.0,
            "memory_warning": 75.0,
            "latency_critical": 5000.0,  # 5 seconds
            "latency_warning": 1000.0,  # 1 second
        }

        self.is_monitoring = False

    async def start_monitoring(self):
        """Start comprehensive performance monitoring."""
        if self.is_monitoring:
            logger.warning("Performance monitoring already running")
            return

        self.is_monitoring = True
        await self.resource_monitor.start_monitoring()
        logger.info("Performance monitoring started")

    async def stop_monitoring(self):
        """Stop performance monitoring."""
        if not self.is_monitoring:
            return

        self.is_monitoring = False
        await self.resource_monitor.stop_monitoring()
        logger.info("Performance monitoring stopped")

    def get_comprehensive_performance_report(self) -> dict[str, Any]:
        """Get comprehensive performance report across all components."""
        return {
            "timestamp": datetime.now().isoformat(),
            "system_resources": self.resource_monitor.get_resource_summary(),
            "trading_performance": self.trading_performance.get_trading_performance_summary(),
            "system_latency": self.system_latency.get_summary(),
            "system_throughput": self.system_throughput.get_summary(),
            "performance_alerts": self._generate_performance_alerts(),
            "monitoring_status": {
                "is_monitoring": self.is_monitoring,
                "resource_snapshots": len(self.resource_monitor.snapshots),
            },
        }

    def record_operation_performance(
        self,
        operation_name: str,
        duration_ms: float,
        success: bool = True,
        tags: dict[str, str] | None = None,
    ):
        """Record performance for a general system operation."""
        operation_tags = {"operation": operation_name, "success": str(success)}
        if tags:
            operation_tags.update(tags)

        self.system_latency.record_latency(duration_ms, operation_tags)
        self.system_throughput.record_event(1, operation_tags)

    def _generate_performance_alerts(self) -> list[dict[str, Any]]:
        """Generate performance alerts based on current metrics."""
        alerts = []

        # Get current resource snapshot
        current_resources = self.resource_monitor.get_current_snapshot()

        # CPU alerts
        if current_resources.cpu_percent >= self.alert_thresholds["cpu_critical"]:
            alerts.append(
                {
                    "level": "critical",
                    "component": "cpu",
                    "message": f"Critical CPU usage: {current_resources.cpu_percent:.1f}%",
                    "value": current_resources.cpu_percent,
                    "threshold": self.alert_thresholds["cpu_critical"],
                }
            )
        elif current_resources.cpu_percent >= self.alert_thresholds["cpu_warning"]:
            alerts.append(
                {
                    "level": "warning",
                    "component": "cpu",
                    "message": f"High CPU usage: {current_resources.cpu_percent:.1f}%",
                    "value": current_resources.cpu_percent,
                    "threshold": self.alert_thresholds["cpu_warning"],
                }
            )

        # Memory alerts
        if current_resources.memory_percent >= self.alert_thresholds["memory_critical"]:
            alerts.append(
                {
                    "level": "critical",
                    "component": "memory",
                    "message": f"Critical memory usage: {current_resources.memory_percent:.1f}%",
                    "value": current_resources.memory_percent,
                    "threshold": self.alert_thresholds["memory_critical"],
                }
            )
        elif (
            current_resources.memory_percent >= self.alert_thresholds["memory_warning"]
        ):
            alerts.append(
                {
                    "level": "warning",
                    "component": "memory",
                    "message": f"High memory usage: {current_resources.memory_percent:.1f}%",
                    "value": current_resources.memory_percent,
                    "threshold": self.alert_thresholds["memory_warning"],
                }
            )

        # Latency alerts
        system_latency_summary = self.system_latency.get_summary()
        if system_latency_summary["count"] > 0:
            mean_latency = system_latency_summary["mean"]

            if mean_latency >= self.alert_thresholds["latency_critical"]:
                alerts.append(
                    {
                        "level": "critical",
                        "component": "latency",
                        "message": f"Critical system latency: {mean_latency:.1f}ms",
                        "value": mean_latency,
                        "threshold": self.alert_thresholds["latency_critical"],
                    }
                )
            elif mean_latency >= self.alert_thresholds["latency_warning"]:
                alerts.append(
                    {
                        "level": "warning",
                        "component": "latency",
                        "message": f"High system latency: {mean_latency:.1f}ms",
                        "value": mean_latency,
                        "threshold": self.alert_thresholds["latency_warning"],
                    }
                )

        return alerts
