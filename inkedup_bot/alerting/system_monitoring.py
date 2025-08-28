"""
System Failure and Performance Degradation Alerts

Comprehensive monitoring for system failures, performance degradation,
resource exhaustion, and infrastructure issues with intelligent alerting
and automated recovery suggestions.
"""

import asyncio
import logging
import os
import socket
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import psutil

from .core import (
    AlertCategory,
    AlertManager,
    AlertRule,
    AlertSeverity,
    get_alert_manager,
)

logger = logging.getLogger(__name__)


class SystemMetricType(Enum):
    """Types of system metrics to monitor"""

    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    DISK_USAGE = "disk_usage"
    DISK_IO = "disk_io"
    NETWORK_IO = "network_io"
    PROCESS_COUNT = "process_count"
    LOAD_AVERAGE = "load_average"
    CONNECTION_COUNT = "connection_count"
    THREAD_COUNT = "thread_count"
    FILE_DESCRIPTOR_COUNT = "fd_count"
    RESPONSE_TIME = "response_time"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    QUEUE_DEPTH = "queue_depth"
    CACHE_HIT_RATE = "cache_hit_rate"


class SystemComponentType(Enum):
    """System components to monitor"""

    OPERATING_SYSTEM = "os"
    PYTHON_PROCESS = "python"
    DATABASE = "database"
    WEBSOCKET = "websocket"
    HTTP_SERVER = "http_server"
    ORDER_CLIENT = "order_client"
    SIGNAL_PROCESSOR = "signal_processor"
    RISK_MANAGER = "risk_manager"
    MARKET_DATA = "market_data"
    NETWORK = "network"
    STORAGE = "storage"


class HealthStatus(Enum):
    """Health status levels"""

    HEALTHY = "healthy"
    WARNING = "warning"
    DEGRADED = "degraded"
    FAILING = "failing"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class SystemMetric:
    """Individual system metric measurement"""

    metric_type: SystemMetricType
    component: SystemComponentType
    value: float
    unit: str
    timestamp: datetime
    labels: dict[str, str] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthCheckResult:
    """Result of a health check"""

    component: SystemComponentType
    check_name: str
    status: HealthStatus
    message: str
    timestamp: datetime
    metrics: dict[str, float] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)
    execution_time_ms: float | None = None


@dataclass
class SystemAlert:
    """System-specific alert information"""

    component: SystemComponentType
    metric_type: SystemMetricType
    current_value: float
    threshold_value: float
    unit: str
    duration_seconds: int
    suggested_actions: list[str] = field(default_factory=list)
    related_metrics: dict[str, float] = field(default_factory=dict)
    impact_assessment: str = "unknown"


class SystemMetricsCollector:
    """Collects system metrics for monitoring"""

    def __init__(self, collection_interval: int = 30):
        self.collection_interval = collection_interval
        self.metrics_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=1440)
        )  # 12 hours at 30s intervals
        self.collectors: dict[SystemMetricType, Callable] = {}

        # Register built-in collectors
        self._register_builtin_collectors()

        # Collection state
        self.running = False
        self.collection_task: asyncio.Task | None = None

        logger.info("System metrics collector initialized")

    def _register_builtin_collectors(self):
        """Register built-in metric collectors"""
        self.collectors[SystemMetricType.CPU_USAGE] = self._collect_cpu_usage
        self.collectors[SystemMetricType.MEMORY_USAGE] = self._collect_memory_usage
        self.collectors[SystemMetricType.DISK_USAGE] = self._collect_disk_usage
        self.collectors[SystemMetricType.DISK_IO] = self._collect_disk_io
        self.collectors[SystemMetricType.NETWORK_IO] = self._collect_network_io
        self.collectors[SystemMetricType.PROCESS_COUNT] = self._collect_process_count
        self.collectors[SystemMetricType.LOAD_AVERAGE] = self._collect_load_average
        self.collectors[SystemMetricType.CONNECTION_COUNT] = (
            self._collect_connection_count
        )
        self.collectors[SystemMetricType.THREAD_COUNT] = self._collect_thread_count
        self.collectors[SystemMetricType.FILE_DESCRIPTOR_COUNT] = self._collect_fd_count

    async def start_collection(self):
        """Start metrics collection"""
        if self.running:
            return

        self.running = True
        self.collection_task = asyncio.create_task(self._collection_loop())
        logger.info("System metrics collection started")

    async def stop_collection(self):
        """Stop metrics collection"""
        if not self.running:
            return

        self.running = False
        if self.collection_task:
            self.collection_task.cancel()
            try:
                await self.collection_task
            except asyncio.CancelledError:
                pass

        logger.info("System metrics collection stopped")

    async def _collection_loop(self):
        """Main collection loop"""
        while self.running:
            try:
                await self._collect_all_metrics()
                await asyncio.sleep(self.collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics collection: {e}")
                await asyncio.sleep(5)

    async def _collect_all_metrics(self):
        """Collect all registered metrics"""
        timestamp = datetime.now()

        for metric_type, collector in self.collectors.items():
            try:
                metrics = await self._run_collector(collector, timestamp)
                for metric in metrics:
                    self._store_metric(metric)
            except Exception as e:
                logger.error(f"Error collecting {metric_type.value}: {e}")

    async def _run_collector(
        self, collector: Callable, timestamp: datetime
    ) -> list[SystemMetric]:
        """Run metric collector"""
        if asyncio.iscoroutinefunction(collector):
            return await collector(timestamp)
        else:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, collector, timestamp)

    def _store_metric(self, metric: SystemMetric):
        """Store metric in history"""
        key = f"{metric.component.value}_{metric.metric_type.value}"
        self.metrics_history[key].append(metric)

    def get_recent_metrics(
        self,
        component: SystemComponentType,
        metric_type: SystemMetricType,
        minutes: int = 10,
    ) -> list[SystemMetric]:
        """Get recent metrics for component and type"""
        key = f"{component.value}_{metric_type.value}"
        cutoff_time = datetime.now() - timedelta(minutes=minutes)

        return [
            metric
            for metric in self.metrics_history.get(key, [])
            if metric.timestamp >= cutoff_time
        ]

    def get_latest_metric(
        self, component: SystemComponentType, metric_type: SystemMetricType
    ) -> SystemMetric | None:
        """Get latest metric value"""
        key = f"{component.value}_{metric_type.value}"
        history = self.metrics_history.get(key, [])
        return history[-1] if history else None

    # Built-in metric collectors

    def _collect_cpu_usage(self, timestamp: datetime) -> list[SystemMetric]:
        """Collect CPU usage metrics"""
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_per_core = psutil.cpu_percent(interval=1, percpu=True)
        load_avg = os.getloadavg() if hasattr(os, "getloadavg") else (0, 0, 0)

        metrics = [
            SystemMetric(
                SystemMetricType.CPU_USAGE,
                SystemComponentType.OPERATING_SYSTEM,
                cpu_percent,
                "%",
                timestamp,
                {"type": "total"},
            ),
            SystemMetric(
                SystemMetricType.LOAD_AVERAGE,
                SystemComponentType.OPERATING_SYSTEM,
                load_avg[0],
                "load",
                timestamp,
                {"period": "1min"},
            ),
        ]

        # Add per-core metrics
        for i, core_usage in enumerate(cpu_per_core):
            metrics.append(
                SystemMetric(
                    SystemMetricType.CPU_USAGE,
                    SystemComponentType.OPERATING_SYSTEM,
                    core_usage,
                    "%",
                    timestamp,
                    {"type": "core", "core": str(i)},
                )
            )

        return metrics

    def _collect_memory_usage(self, timestamp: datetime) -> list[SystemMetric]:
        """Collect memory usage metrics"""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        return [
            SystemMetric(
                SystemMetricType.MEMORY_USAGE,
                SystemComponentType.OPERATING_SYSTEM,
                mem.percent,
                "%",
                timestamp,
                {"type": "physical"},
                {"total": mem.total, "available": mem.available, "used": mem.used},
            ),
            SystemMetric(
                SystemMetricType.MEMORY_USAGE,
                SystemComponentType.OPERATING_SYSTEM,
                swap.percent,
                "%",
                timestamp,
                {"type": "swap"},
                {"total": swap.total, "used": swap.used, "free": swap.free},
            ),
        ]

    def _collect_disk_usage(self, timestamp: datetime) -> list[SystemMetric]:
        """Collect disk usage metrics"""
        metrics = []

        # Get disk usage for all mounted filesystems
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                metrics.append(
                    SystemMetric(
                        SystemMetricType.DISK_USAGE,
                        SystemComponentType.STORAGE,
                        (usage.used / usage.total) * 100,
                        "%",
                        timestamp,
                        {
                            "mountpoint": partition.mountpoint,
                            "fstype": partition.fstype,
                        },
                        {"total": usage.total, "used": usage.used, "free": usage.free},
                    )
                )
            except (PermissionError, OSError):
                continue

        return metrics

    def _collect_disk_io(self, timestamp: datetime) -> list[SystemMetric]:
        """Collect disk I/O metrics"""
        disk_io = psutil.disk_io_counters()
        if not disk_io:
            return []

        return [
            SystemMetric(
                SystemMetricType.DISK_IO,
                SystemComponentType.STORAGE,
                disk_io.read_bytes,
                "bytes",
                timestamp,
                {"type": "read_bytes"},
            ),
            SystemMetric(
                SystemMetricType.DISK_IO,
                SystemComponentType.STORAGE,
                disk_io.write_bytes,
                "bytes",
                timestamp,
                {"type": "write_bytes"},
            ),
            SystemMetric(
                SystemMetricType.DISK_IO,
                SystemComponentType.STORAGE,
                disk_io.read_count,
                "ops",
                timestamp,
                {"type": "read_ops"},
            ),
            SystemMetric(
                SystemMetricType.DISK_IO,
                SystemComponentType.STORAGE,
                disk_io.write_count,
                "ops",
                timestamp,
                {"type": "write_ops"},
            ),
        ]

    def _collect_network_io(self, timestamp: datetime) -> list[SystemMetric]:
        """Collect network I/O metrics"""
        net_io = psutil.net_io_counters()
        if not net_io:
            return []

        return [
            SystemMetric(
                SystemMetricType.NETWORK_IO,
                SystemComponentType.NETWORK,
                net_io.bytes_sent,
                "bytes",
                timestamp,
                {"type": "sent"},
            ),
            SystemMetric(
                SystemMetricType.NETWORK_IO,
                SystemComponentType.NETWORK,
                net_io.bytes_recv,
                "bytes",
                timestamp,
                {"type": "received"},
            ),
            SystemMetric(
                SystemMetricType.NETWORK_IO,
                SystemComponentType.NETWORK,
                net_io.packets_sent,
                "packets",
                timestamp,
                {"type": "sent"},
            ),
            SystemMetric(
                SystemMetricType.NETWORK_IO,
                SystemComponentType.NETWORK,
                net_io.packets_recv,
                "packets",
                timestamp,
                {"type": "received"},
            ),
        ]

    def _collect_process_count(self, timestamp: datetime) -> list[SystemMetric]:
        """Collect process count metrics"""
        process_count = len(psutil.pids())

        # Count processes by status
        status_counts = defaultdict(int)
        for proc in psutil.process_iter(["status"]):
            try:
                status_counts[proc.info["status"]] += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        metrics = [
            SystemMetric(
                SystemMetricType.PROCESS_COUNT,
                SystemComponentType.OPERATING_SYSTEM,
                process_count,
                "processes",
                timestamp,
                {"type": "total"},
            )
        ]

        for status, count in status_counts.items():
            metrics.append(
                SystemMetric(
                    SystemMetricType.PROCESS_COUNT,
                    SystemComponentType.OPERATING_SYSTEM,
                    count,
                    "processes",
                    timestamp,
                    {"type": status},
                )
            )

        return metrics

    def _collect_load_average(self, timestamp: datetime) -> list[SystemMetric]:
        """Collect load average metrics"""
        if not hasattr(os, "getloadavg"):
            return []

        load_1, load_5, load_15 = os.getloadavg()

        return [
            SystemMetric(
                SystemMetricType.LOAD_AVERAGE,
                SystemComponentType.OPERATING_SYSTEM,
                load_1,
                "load",
                timestamp,
                {"period": "1min"},
            ),
            SystemMetric(
                SystemMetricType.LOAD_AVERAGE,
                SystemComponentType.OPERATING_SYSTEM,
                load_5,
                "load",
                timestamp,
                {"period": "5min"},
            ),
            SystemMetric(
                SystemMetricType.LOAD_AVERAGE,
                SystemComponentType.OPERATING_SYSTEM,
                load_15,
                "load",
                timestamp,
                {"period": "15min"},
            ),
        ]

    def _collect_connection_count(self, timestamp: datetime) -> list[SystemMetric]:
        """Collect network connection count metrics"""
        try:
            connections = psutil.net_connections()

            # Count by status
            status_counts = defaultdict(int)
            for conn in connections:
                status_counts[conn.status] += 1

            metrics = [
                SystemMetric(
                    SystemMetricType.CONNECTION_COUNT,
                    SystemComponentType.NETWORK,
                    len(connections),
                    "connections",
                    timestamp,
                    {"type": "total"},
                )
            ]

            for status, count in status_counts.items():
                metrics.append(
                    SystemMetric(
                        SystemMetricType.CONNECTION_COUNT,
                        SystemComponentType.NETWORK,
                        count,
                        "connections",
                        timestamp,
                        {"status": status},
                    )
                )

            return metrics

        except (psutil.AccessDenied, OSError):
            return []

    def _collect_thread_count(self, timestamp: datetime) -> list[SystemMetric]:
        """Collect thread count metrics"""
        current_process = psutil.Process()

        try:
            thread_count = current_process.num_threads()

            return [
                SystemMetric(
                    SystemMetricType.THREAD_COUNT,
                    SystemComponentType.PYTHON_PROCESS,
                    thread_count,
                    "threads",
                    timestamp,
                    {"process": "current"},
                )
            ]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return []

    def _collect_fd_count(self, timestamp: datetime) -> list[SystemMetric]:
        """Collect file descriptor count metrics"""
        try:
            current_process = psutil.Process()
            fd_count = (
                current_process.num_fds() if hasattr(current_process, "num_fds") else 0
            )

            return [
                SystemMetric(
                    SystemMetricType.FILE_DESCRIPTOR_COUNT,
                    SystemComponentType.PYTHON_PROCESS,
                    fd_count,
                    "fds",
                    timestamp,
                    {"process": "current"},
                )
            ]
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            return []


class HealthChecker:
    """Performs health checks on system components"""

    def __init__(self):
        self.health_checks: dict[str, Callable] = {}
        self.check_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        # Register built-in health checks
        self._register_builtin_checks()

        logger.info("Health checker initialized")

    def _register_builtin_checks(self):
        """Register built-in health checks"""
        self.health_checks["os_resources"] = self._check_os_resources
        self.health_checks["python_process"] = self._check_python_process
        self.health_checks["network_connectivity"] = self._check_network_connectivity
        self.health_checks["disk_space"] = self._check_disk_space

    def register_health_check(self, name: str, check_func: Callable):
        """Register custom health check"""
        self.health_checks[name] = check_func
        logger.info(f"Registered health check: {name}")

    async def run_health_checks(self) -> list[HealthCheckResult]:
        """Run all health checks"""
        results = []

        for check_name, check_func in self.health_checks.items():
            try:
                start_time = time.perf_counter()

                if asyncio.iscoroutinefunction(check_func):
                    result = await check_func()
                else:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, check_func)

                execution_time = (time.perf_counter() - start_time) * 1000
                result.execution_time_ms = execution_time

                results.append(result)
                self.check_history[check_name].append(result)

            except Exception as e:
                logger.error(f"Health check {check_name} failed: {e}")
                result = HealthCheckResult(
                    component=SystemComponentType.OPERATING_SYSTEM,
                    check_name=check_name,
                    status=HealthStatus.UNKNOWN,
                    message=f"Health check failed: {str(e)}",
                    timestamp=datetime.now(),
                )
                results.append(result)

        return results

    def _check_os_resources(self) -> HealthCheckResult:
        """Check OS resource usage"""
        cpu_percent = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()

        status = HealthStatus.HEALTHY
        issues = []
        suggestions = []

        # Check CPU usage
        if cpu_percent > 90:
            status = HealthStatus.CRITICAL
            issues.append(f"CPU usage very high: {cpu_percent:.1f}%")
            suggestions.append("Investigate high CPU processes")
        elif cpu_percent > 75:
            status = HealthStatus.WARNING
            issues.append(f"CPU usage high: {cpu_percent:.1f}%")
            suggestions.append("Monitor CPU usage trends")

        # Check memory usage
        if mem.percent > 95:
            status = HealthStatus.CRITICAL
            issues.append(f"Memory usage critical: {mem.percent:.1f}%")
            suggestions.append("Free memory or restart processes")
        elif mem.percent > 85:
            status = max(status, HealthStatus.WARNING)
            issues.append(f"Memory usage high: {mem.percent:.1f}%")
            suggestions.append("Monitor memory usage")

        message = "System resources healthy"
        if issues:
            message = "; ".join(issues)

        return HealthCheckResult(
            component=SystemComponentType.OPERATING_SYSTEM,
            check_name="os_resources",
            status=status,
            message=message,
            timestamp=datetime.now(),
            metrics={"cpu_percent": cpu_percent, "memory_percent": mem.percent},
            suggestions=suggestions,
        )

    def _check_python_process(self) -> HealthCheckResult:
        """Check Python process health"""
        try:
            current_process = psutil.Process()

            # Get process metrics
            memory_info = current_process.memory_info()
            memory_percent = current_process.memory_percent()
            cpu_percent = current_process.cpu_percent()

            status = HealthStatus.HEALTHY
            issues = []
            suggestions = []

            # Check memory usage
            if memory_percent > 50:
                status = HealthStatus.WARNING
                issues.append(f"Process memory usage high: {memory_percent:.1f}%")
                suggestions.append("Check for memory leaks")

            # Check thread count
            try:
                thread_count = current_process.num_threads()
                if thread_count > 50:
                    status = max(status, HealthStatus.WARNING)
                    issues.append(f"High thread count: {thread_count}")
                    suggestions.append("Review thread management")
            except AttributeError:
                pass

            message = "Python process healthy"
            if issues:
                message = "; ".join(issues)

            return HealthCheckResult(
                component=SystemComponentType.PYTHON_PROCESS,
                check_name="python_process",
                status=status,
                message=message,
                timestamp=datetime.now(),
                metrics={
                    "memory_percent": memory_percent,
                    "memory_rss": memory_info.rss,
                    "cpu_percent": cpu_percent,
                },
                suggestions=suggestions,
            )

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            return HealthCheckResult(
                component=SystemComponentType.PYTHON_PROCESS,
                check_name="python_process",
                status=HealthStatus.UNKNOWN,
                message=f"Cannot access process info: {e}",
                timestamp=datetime.now(),
            )

    def _check_network_connectivity(self) -> HealthCheckResult:
        """Check network connectivity"""
        try:
            # Simple connectivity check
            socket.create_connection(("8.8.8.8", 53), timeout=5)

            return HealthCheckResult(
                component=SystemComponentType.NETWORK,
                check_name="network_connectivity",
                status=HealthStatus.HEALTHY,
                message="Network connectivity OK",
                timestamp=datetime.now(),
            )

        except (TimeoutError, OSError) as e:
            return HealthCheckResult(
                component=SystemComponentType.NETWORK,
                check_name="network_connectivity",
                status=HealthStatus.CRITICAL,
                message=f"Network connectivity failed: {e}",
                timestamp=datetime.now(),
                suggestions=["Check network configuration", "Verify DNS settings"],
            )

    def _check_disk_space(self) -> HealthCheckResult:
        """Check disk space"""
        try:
            usage = psutil.disk_usage("/")
            usage_percent = (usage.used / usage.total) * 100

            status = HealthStatus.HEALTHY
            issues = []
            suggestions = []

            if usage_percent > 95:
                status = HealthStatus.CRITICAL
                issues.append(f"Disk usage critical: {usage_percent:.1f}%")
                suggestions.append("Free disk space immediately")
            elif usage_percent > 85:
                status = HealthStatus.WARNING
                issues.append(f"Disk usage high: {usage_percent:.1f}%")
                suggestions.append("Clean up old files")

            message = "Disk space healthy"
            if issues:
                message = "; ".join(issues)

            return HealthCheckResult(
                component=SystemComponentType.STORAGE,
                check_name="disk_space",
                status=status,
                message=message,
                timestamp=datetime.now(),
                metrics={"usage_percent": usage_percent},
                suggestions=suggestions,
            )

        except OSError as e:
            return HealthCheckResult(
                component=SystemComponentType.STORAGE,
                check_name="disk_space",
                status=HealthStatus.UNKNOWN,
                message=f"Cannot check disk space: {e}",
                timestamp=datetime.now(),
            )


class SystemAlertsManager:
    """
    Manages system failure and performance degradation alerts

    Integrates with metrics collection and health checks to provide
    intelligent alerting for system issues.
    """

    def __init__(self, alert_manager: AlertManager | None = None):
        self.alert_manager = alert_manager or get_alert_manager()
        self.metrics_collector = SystemMetricsCollector()
        self.health_checker = HealthChecker()

        # Alert thresholds
        self.thresholds: dict[str, dict[str, float]] = {
            "cpu_usage": {"warning": 75.0, "critical": 90.0, "emergency": 95.0},
            "memory_usage": {"warning": 80.0, "critical": 90.0, "emergency": 95.0},
            "disk_usage": {"warning": 85.0, "critical": 95.0, "emergency": 98.0},
            "load_average": {"warning": 2.0, "critical": 4.0, "emergency": 8.0},
            "response_time": {
                "warning": 1000.0,
                "critical": 5000.0,
                "emergency": 10000.0,
            },  # ms
        }

        # Monitoring state
        self.running = False
        self.monitoring_tasks: list[asyncio.Task] = []

        # Setup default alert rules
        self._setup_default_alert_rules()

        logger.info("System alerts manager initialized")

    def _setup_default_alert_rules(self):
        """Setup default system alert rules"""

        # CPU usage alert
        cpu_rule = AlertRule(
            rule_id="system_cpu_high",
            name="High CPU Usage",
            category=AlertCategory.SYSTEM_FAILURE,
            description="System CPU usage is high",
            condition="cpu_usage > threshold",
            severity=AlertSeverity.HIGH,
            enabled=True,
            tags={"metric": "cpu_usage", "component": "system"},
            auto_resolve=True,
            cooldown_seconds=600,
            max_frequency=10,
        )
        self.alert_manager.add_alert_rule(cpu_rule)

        # Memory usage alert
        memory_rule = AlertRule(
            rule_id="system_memory_high",
            name="High Memory Usage",
            category=AlertCategory.SYSTEM_FAILURE,
            description="System memory usage is high",
            condition="memory_usage > threshold",
            severity=AlertSeverity.HIGH,
            enabled=True,
            tags={"metric": "memory_usage", "component": "system"},
            auto_resolve=True,
            cooldown_seconds=600,
            max_frequency=10,
        )
        self.alert_manager.add_alert_rule(memory_rule)

        # Disk usage alert
        disk_rule = AlertRule(
            rule_id="system_disk_full",
            name="Disk Space Low",
            category=AlertCategory.SYSTEM_FAILURE,
            description="System disk usage is high",
            condition="disk_usage > threshold",
            severity=AlertSeverity.CRITICAL,
            enabled=True,
            tags={"metric": "disk_usage", "component": "storage"},
            auto_resolve=True,
            cooldown_seconds=1800,  # 30 minutes
            max_frequency=5,
        )
        self.alert_manager.add_alert_rule(disk_rule)

        # Health check failure alert
        health_rule = AlertRule(
            rule_id="system_health_check_failed",
            name="Health Check Failed",
            category=AlertCategory.SYSTEM_FAILURE,
            description="System health check failed",
            condition="health_status != healthy",
            severity=AlertSeverity.HIGH,
            enabled=True,
            tags={"metric": "health_check", "component": "system"},
            auto_resolve=True,
            cooldown_seconds=300,
            max_frequency=20,
        )
        self.alert_manager.add_alert_rule(health_rule)

    async def start_monitoring(self):
        """Start system monitoring"""
        if self.running:
            return

        self.running = True

        # Start metrics collection
        await self.metrics_collector.start_collection()

        # Start monitoring tasks
        self.monitoring_tasks = [
            asyncio.create_task(self._metrics_monitoring_loop()),
            asyncio.create_task(self._health_check_loop()),
            asyncio.create_task(self._performance_analysis_loop()),
        ]

        logger.info("System monitoring started")

    async def stop_monitoring(self):
        """Stop system monitoring"""
        if not self.running:
            return

        self.running = False

        # Stop metrics collection
        await self.metrics_collector.stop_collection()

        # Cancel monitoring tasks
        for task in self.monitoring_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.monitoring_tasks.clear()
        logger.info("System monitoring stopped")

    async def _metrics_monitoring_loop(self):
        """Monitor metrics and trigger alerts"""
        while self.running:
            try:
                await self._check_metric_thresholds()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics monitoring: {e}")
                await asyncio.sleep(30)

    async def _health_check_loop(self):
        """Run health checks and trigger alerts"""
        while self.running:
            try:
                health_results = await self.health_checker.run_health_checks()
                await self._process_health_results(health_results)
                await asyncio.sleep(120)  # Check every 2 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(60)

    async def _performance_analysis_loop(self):
        """Analyze performance trends and predict issues"""
        while self.running:
            try:
                await self._analyze_performance_trends()
                await asyncio.sleep(300)  # Analyze every 5 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in performance analysis: {e}")
                await asyncio.sleep(120)

    async def _check_metric_thresholds(self):
        """Check current metrics against thresholds"""

        # Check CPU usage
        cpu_metric = self.metrics_collector.get_latest_metric(
            SystemComponentType.OPERATING_SYSTEM, SystemMetricType.CPU_USAGE
        )
        if cpu_metric and "total" in cpu_metric.labels.get("type", ""):
            await self._check_threshold_breach(
                "cpu_usage", cpu_metric.value, cpu_metric, "system_cpu_high"
            )

        # Check memory usage
        mem_metric = self.metrics_collector.get_latest_metric(
            SystemComponentType.OPERATING_SYSTEM, SystemMetricType.MEMORY_USAGE
        )
        if mem_metric and "physical" in mem_metric.labels.get("type", ""):
            await self._check_threshold_breach(
                "memory_usage", mem_metric.value, mem_metric, "system_memory_high"
            )

        # Check disk usage
        disk_metrics = self.metrics_collector.get_recent_metrics(
            SystemComponentType.STORAGE, SystemMetricType.DISK_USAGE, minutes=1
        )
        for disk_metric in disk_metrics:
            if disk_metric.labels.get("mountpoint") == "/":  # Root filesystem
                await self._check_threshold_breach(
                    "disk_usage", disk_metric.value, disk_metric, "system_disk_full"
                )

    async def _check_threshold_breach(
        self, metric_name: str, value: float, metric: SystemMetric, rule_id: str
    ):
        """Check if metric breaches thresholds and create alert"""

        thresholds = self.thresholds.get(metric_name, {})
        severity = None
        threshold_value = None

        # Determine severity based on thresholds
        if value >= thresholds.get("emergency", float("inf")):
            severity = AlertSeverity.EMERGENCY
            threshold_value = thresholds["emergency"]
        elif value >= thresholds.get("critical", float("inf")):
            severity = AlertSeverity.CRITICAL
            threshold_value = thresholds["critical"]
        elif value >= thresholds.get("warning", float("inf")):
            severity = AlertSeverity.HIGH
            threshold_value = thresholds["warning"]

        if severity:
            # Create system alert with suggestions
            system_alert = self._create_system_alert(
                metric_name, value, threshold_value, metric
            )

            alert = self.alert_manager.create_alert(
                rule_id=rule_id,
                triggered_by=f"{metric_name} threshold breach",
                current_value=value,
                threshold_value=threshold_value,
                affected_components=[f"{metric.component.value}_{metric_name}"],
                context={
                    "metric_type": metric.metric_type.value,
                    "component": metric.component.value,
                    "unit": metric.unit,
                    "suggested_actions": system_alert.suggested_actions,
                    "impact_assessment": system_alert.impact_assessment,
                    "related_metrics": system_alert.related_metrics,
                },
            )

            if alert:
                logger.warning(
                    f"System threshold breach: {metric_name} = {value:.1f}{metric.unit} "
                    f"(threshold: {threshold_value}{metric.unit})"
                )

    async def _process_health_results(self, health_results: list[HealthCheckResult]):
        """Process health check results and create alerts if needed"""

        for result in health_results:
            if result.status in [HealthStatus.CRITICAL, HealthStatus.FAILING]:
                severity = (
                    AlertSeverity.CRITICAL
                    if result.status == HealthStatus.CRITICAL
                    else AlertSeverity.HIGH
                )

                alert = self.alert_manager.create_alert(
                    rule_id="system_health_check_failed",
                    triggered_by=f"Health check failed: {result.check_name}",
                    affected_components=[
                        f"{result.component.value}_{result.check_name}"
                    ],
                    context={
                        "health_check": result.check_name,
                        "component": result.component.value,
                        "status": result.status.value,
                        "message": result.message,
                        "suggestions": result.suggestions,
                        "metrics": result.metrics,
                        "execution_time_ms": result.execution_time_ms,
                    },
                )

                if alert:
                    logger.warning(
                        f"Health check alert: {result.check_name} - {result.message}"
                    )

    async def _analyze_performance_trends(self):
        """Analyze performance trends and predict potential issues"""

        # Analyze CPU trend
        cpu_metrics = self.metrics_collector.get_recent_metrics(
            SystemComponentType.OPERATING_SYSTEM, SystemMetricType.CPU_USAGE, minutes=30
        )

        if len(cpu_metrics) > 10:  # Need enough data points
            cpu_values = [
                m.value for m in cpu_metrics if "total" in m.labels.get("type", "")
            ]
            if cpu_values:
                trend_slope = self._calculate_trend_slope(cpu_values)

                # If CPU is trending upward rapidly, predict potential issue
                if trend_slope > 2.0:  # 2% per data point (roughly per minute)
                    predicted_value = cpu_values[-1] + (
                        trend_slope * 10
                    )  # 10 minutes ahead

                    if predicted_value > self.thresholds["cpu_usage"]["warning"]:
                        # Create predictive alert
                        alert = self.alert_manager.create_alert(
                            rule_id="system_performance_degrading",
                            triggered_by="Performance degradation predicted",
                            current_value=cpu_values[-1],
                            threshold_value=self.thresholds["cpu_usage"]["warning"],
                            affected_components=["system_cpu_trending"],
                            context={
                                "prediction_type": "cpu_usage_trend",
                                "current_value": cpu_values[-1],
                                "trend_slope": trend_slope,
                                "predicted_value": predicted_value,
                                "prediction_horizon": "10_minutes",
                                "suggested_actions": [
                                    "Monitor CPU usage closely",
                                    "Identify processes causing high CPU",
                                    "Consider scaling resources",
                                ],
                            },
                        )

                        if alert:
                            logger.warning(
                                f"Performance degradation predicted: CPU trending up "
                                f"({trend_slope:.2f}%/min), predicted: {predicted_value:.1f}%"
                            )

    def _calculate_trend_slope(self, values: list[float]) -> float:
        """Calculate trend slope using simple linear regression"""
        if len(values) < 2:
            return 0.0

        n = len(values)
        x = list(range(n))

        # Calculate slope using least squares
        x_mean = sum(x) / n
        y_mean = sum(values) / n

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def _create_system_alert(
        self,
        metric_name: str,
        current_value: float,
        threshold_value: float,
        metric: SystemMetric,
    ) -> SystemAlert:
        """Create system alert with context and suggestions"""

        suggestions = []
        impact = "low"

        if metric_name == "cpu_usage":
            suggestions = [
                "Identify high CPU processes using 'top' or 'htop'",
                "Check for runaway processes or infinite loops",
                "Consider scaling CPU resources",
                "Optimize CPU-intensive operations",
            ]
            if current_value > 95:
                impact = "critical"
                suggestions.append("Consider emergency process termination")
            elif current_value > 85:
                impact = "high"

        elif metric_name == "memory_usage":
            suggestions = [
                "Identify memory-intensive processes",
                "Check for memory leaks",
                "Clear system caches if appropriate",
                "Consider adding more RAM",
                "Restart memory-intensive services",
            ]
            if current_value > 95:
                impact = "critical"
                suggestions.append("Risk of system instability")
            elif current_value > 85:
                impact = "high"

        elif metric_name == "disk_usage":
            suggestions = [
                "Clean up temporary files",
                "Remove old log files",
                "Clear application caches",
                "Move files to different storage",
                "Expand disk capacity",
            ]
            if current_value > 98:
                impact = "critical"
                suggestions.append("System may become unstable")
            elif current_value > 90:
                impact = "high"

        # Get related metrics for context
        related_metrics = {}
        if metric.component == SystemComponentType.OPERATING_SYSTEM:
            # Get other OS metrics for correlation
            for metric_type in [
                SystemMetricType.CPU_USAGE,
                SystemMetricType.MEMORY_USAGE,
                SystemMetricType.LOAD_AVERAGE,
            ]:
                latest = self.metrics_collector.get_latest_metric(
                    metric.component, metric_type
                )
                if latest and latest.metric_type != metric.metric_type:
                    related_metrics[latest.metric_type.value] = latest.value

        return SystemAlert(
            component=metric.component,
            metric_type=metric.metric_type,
            current_value=current_value,
            threshold_value=threshold_value,
            unit=metric.unit,
            duration_seconds=60,  # Simplified for this example
            suggested_actions=suggestions,
            related_metrics=related_metrics,
            impact_assessment=impact,
        )

    def get_system_health_summary(self) -> dict[str, Any]:
        """Get comprehensive system health summary"""

        # Get latest metrics
        latest_metrics = {}
        for component in SystemComponentType:
            for metric_type in SystemMetricType:
                metric = self.metrics_collector.get_latest_metric(
                    component, metric_type
                )
                if metric:
                    key = f"{component.value}_{metric_type.value}"
                    latest_metrics[key] = {
                        "value": metric.value,
                        "unit": metric.unit,
                        "timestamp": metric.timestamp.isoformat(),
                        "labels": metric.labels,
                    }

        # Get recent health check results
        recent_health = {}
        for check_name, history in self.health_checker.check_history.items():
            if history:
                latest = history[-1]
                recent_health[check_name] = {
                    "status": latest.status.value,
                    "message": latest.message,
                    "timestamp": latest.timestamp.isoformat(),
                    "suggestions": latest.suggestions,
                    "metrics": latest.metrics,
                }

        return {
            "timestamp": datetime.now().isoformat(),
            "monitoring_running": self.running,
            "latest_metrics": latest_metrics,
            "health_checks": recent_health,
            "alert_thresholds": self.thresholds,
            "metrics_collection_interval": self.metrics_collector.collection_interval,
        }


# Global system alerts manager instance
_system_alerts_manager = None


def get_system_alerts_manager() -> SystemAlertsManager:
    """Get global system alerts manager instance"""
    global _system_alerts_manager

    if _system_alerts_manager is None:
        _system_alerts_manager = SystemAlertsManager()

    return _system_alerts_manager


def initialize_system_monitoring(
    thresholds: dict[str, dict[str, float]] | None = None,
) -> SystemAlertsManager:
    """Initialize system monitoring with custom thresholds"""
    global _system_alerts_manager

    _system_alerts_manager = SystemAlertsManager()

    if thresholds:
        _system_alerts_manager.thresholds.update(thresholds)

    logger.info("System monitoring initialized")
    return _system_alerts_manager
