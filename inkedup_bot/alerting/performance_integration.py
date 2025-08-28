"""
Performance Metrics System Integration

Integration between the alerting system and existing performance metrics
infrastructure, enabling seamless monitoring and alerting based on
performance data from all system components.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .core import (
    AlertCategory,
    AlertManager,
    AlertRule,
    AlertSeverity,
    get_alert_manager,
)
from .operational_monitoring import OperationalIssueType, OperationalMonitor
from .risk_integration import RiskMetricsMonitor
from .system_monitoring import (
    SystemAlertsManager,
)

# Import existing performance metrics components
try:
    from ..database_performance_metrics import DatabasePerformanceTracker
    from ..error_rate_tracking import ErrorRateTracker
    from ..order_execution_metrics import OrderExecutionPerformanceTracker
    from ..performance_integration import PerformanceIntegrationManager
    from ..performance_metrics import (
        PerformanceMetricsTracker,
    )
    from ..signal_processing_metrics import SignalProcessingPerformanceTracker
    from ..throughput_metrics import ThroughputTracker
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"Could not import performance metrics components: {e}")

    # Define placeholder classes for type hints
    class PerformanceMetricsTracker:
        pass

    class SignalProcessingPerformanceTracker:
        pass

    class OrderExecutionPerformanceTracker:
        pass

    class DatabasePerformanceTracker:
        pass

    class ThroughputTracker:
        pass

    class ErrorRateTracker:
        pass

    class PerformanceIntegrationManager:
        pass


logger = logging.getLogger(__name__)


@dataclass
class MetricThreshold:
    """Performance metric threshold configuration"""

    metric_name: str
    component: str
    warning_threshold: float
    critical_threshold: float
    emergency_threshold: float | None = None
    comparison_operator: str = ">"  # >, <, >=, <=, ==, !=
    duration_minutes: int = 5  # How long threshold must be breached
    enabled: bool = True
    alert_rule_id: str | None = None


@dataclass
class PerformanceAlert:
    """Performance-based alert configuration"""

    alert_id: str
    name: str
    description: str
    metric_thresholds: list[MetricThreshold]
    severity: AlertSeverity
    category: AlertCategory
    enabled: bool = True
    cooldown_minutes: int = 15
    auto_resolve: bool = True


class PerformanceMetricsConnector:
    """
    Connects alerting system to performance metrics infrastructure

    Monitors performance metrics and triggers alerts when thresholds are breached.
    """

    def __init__(self, alert_manager: AlertManager | None = None):
        self.alert_manager = alert_manager or get_alert_manager()

        # Performance trackers
        self.performance_tracker: PerformanceMetricsTracker | None = None
        self.signal_tracker: SignalProcessingPerformanceTracker | None = None
        self.order_tracker: OrderExecutionPerformanceTracker | None = None
        self.database_tracker: DatabasePerformanceTracker | None = None
        self.throughput_tracker: ThroughputTracker | None = None
        self.error_tracker: ErrorRateTracker | None = None

        # Integration components
        self.system_monitor: SystemAlertsManager | None = None
        self.operational_monitor: OperationalMonitor | None = None
        self.risk_monitor: RiskMetricsMonitor | None = None

        # Metric thresholds and alerts
        self.metric_thresholds: dict[str, MetricThreshold] = {}
        self.performance_alerts: dict[str, PerformanceAlert] = {}
        self.breach_tracking: dict[str, list[datetime]] = {}

        # Monitoring state
        self.running = False
        self.monitoring_tasks: list[asyncio.Task] = []
        self.check_interval = 30  # seconds

        logger.info("Performance metrics connector initialized")

    def set_performance_tracker(self, tracker: PerformanceMetricsTracker):
        """Set performance metrics tracker"""
        self.performance_tracker = tracker
        logger.info("Performance metrics tracker connected")

    def set_signal_tracker(self, tracker: SignalProcessingPerformanceTracker):
        """Set signal processing tracker"""
        self.signal_tracker = tracker
        logger.info("Signal processing tracker connected")

    def set_order_tracker(self, tracker: OrderExecutionPerformanceTracker):
        """Set order execution tracker"""
        self.order_tracker = tracker
        logger.info("Order execution tracker connected")

    def set_database_tracker(self, tracker: DatabasePerformanceTracker):
        """Set database performance tracker"""
        self.database_tracker = tracker
        logger.info("Database performance tracker connected")

    def set_throughput_tracker(self, tracker: ThroughputTracker):
        """Set throughput tracker"""
        self.throughput_tracker = tracker
        logger.info("Throughput tracker connected")

    def set_error_tracker(self, tracker: ErrorRateTracker):
        """Set error rate tracker"""
        self.error_tracker = tracker
        logger.info("Error rate tracker connected")

    def connect_system_monitor(self, monitor: SystemAlertsManager):
        """Connect system alerts manager"""
        self.system_monitor = monitor
        logger.info("System monitor connected")

    def connect_operational_monitor(self, monitor: OperationalMonitor):
        """Connect operational monitor"""
        self.operational_monitor = monitor
        logger.info("Operational monitor connected")

    def connect_risk_monitor(self, monitor: RiskMetricsMonitor):
        """Connect risk metrics monitor"""
        self.risk_monitor = monitor
        logger.info("Risk monitor connected")

    def add_metric_threshold(self, threshold: MetricThreshold):
        """Add metric threshold for monitoring"""
        threshold_key = f"{threshold.component}_{threshold.metric_name}"
        self.metric_thresholds[threshold_key] = threshold

        # Create corresponding alert rule
        rule_id = f"perf_metric_{threshold_key}"
        threshold.alert_rule_id = rule_id

        alert_rule = AlertRule(
            rule_id=rule_id,
            name=f"Performance Metric: {threshold.metric_name}",
            category=AlertCategory.PERFORMANCE_DEGRADATION,
            description=f"Performance metric {threshold.metric_name} on {threshold.component} exceeded threshold",
            condition=f"{threshold.metric_name} {threshold.comparison_operator} {threshold.warning_threshold}",
            severity=AlertSeverity.MEDIUM,
            enabled=threshold.enabled,
            tags={
                "metric": threshold.metric_name,
                "component": threshold.component,
                "type": "performance",
            },
            auto_resolve=True,
            cooldown_seconds=threshold.duration_minutes * 60,
            max_frequency=10,
        )

        self.alert_manager.add_alert_rule(alert_rule)
        logger.info(
            f"Added metric threshold: {threshold.metric_name} on {threshold.component}"
        )

    def add_performance_alert(self, alert_config: PerformanceAlert):
        """Add performance alert configuration"""
        self.performance_alerts[alert_config.alert_id] = alert_config

        # Add thresholds for this alert
        for threshold in alert_config.metric_thresholds:
            self.add_metric_threshold(threshold)

        logger.info(f"Added performance alert: {alert_config.name}")

    async def start_monitoring(self):
        """Start performance metrics monitoring"""
        if self.running:
            return

        self.running = True

        # Start monitoring tasks
        self.monitoring_tasks = [
            asyncio.create_task(self._performance_monitoring_loop()),
            asyncio.create_task(self._signal_monitoring_loop()),
            asyncio.create_task(self._order_monitoring_loop()),
            asyncio.create_task(self._database_monitoring_loop()),
            asyncio.create_task(self._throughput_monitoring_loop()),
            asyncio.create_task(self._error_rate_monitoring_loop()),
            asyncio.create_task(self._integration_health_loop()),
        ]

        logger.info("Performance metrics monitoring started")

    async def stop_monitoring(self):
        """Stop performance metrics monitoring"""
        if not self.running:
            return

        self.running = False

        # Cancel monitoring tasks
        for task in self.monitoring_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.monitoring_tasks.clear()
        logger.info("Performance metrics monitoring stopped")

    async def _performance_monitoring_loop(self):
        """Monitor core performance metrics"""
        while self.running:
            try:
                if self.performance_tracker:
                    await self._check_performance_metrics()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in performance monitoring loop: {e}")
                await asyncio.sleep(30)

    async def _signal_monitoring_loop(self):
        """Monitor signal processing metrics"""
        while self.running:
            try:
                if self.signal_tracker:
                    await self._check_signal_processing_metrics()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in signal monitoring loop: {e}")
                await asyncio.sleep(30)

    async def _order_monitoring_loop(self):
        """Monitor order execution metrics"""
        while self.running:
            try:
                if self.order_tracker:
                    await self._check_order_execution_metrics()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in order monitoring loop: {e}")
                await asyncio.sleep(30)

    async def _database_monitoring_loop(self):
        """Monitor database performance metrics"""
        while self.running:
            try:
                if self.database_tracker:
                    await self._check_database_metrics()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in database monitoring loop: {e}")
                await asyncio.sleep(30)

    async def _throughput_monitoring_loop(self):
        """Monitor throughput metrics"""
        while self.running:
            try:
                if self.throughput_tracker:
                    await self._check_throughput_metrics()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in throughput monitoring loop: {e}")
                await asyncio.sleep(30)

    async def _error_rate_monitoring_loop(self):
        """Monitor error rate metrics"""
        while self.running:
            try:
                if self.error_tracker:
                    await self._check_error_rate_metrics()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in error rate monitoring loop: {e}")
                await asyncio.sleep(30)

    async def _integration_health_loop(self):
        """Monitor integration health"""
        while self.running:
            try:
                await self._check_integration_health()
                await asyncio.sleep(120)  # Check every 2 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in integration health loop: {e}")
                await asyncio.sleep(60)

    async def _check_performance_metrics(self):
        """Check core performance metrics against thresholds"""
        if not self.performance_tracker:
            return

        try:
            # Get recent metrics
            recent_metrics = getattr(
                self.performance_tracker, "get_recent_metrics", lambda x: []
            )(minutes=10)

            for threshold_key, threshold in self.metric_thresholds.items():
                if not threshold.enabled or threshold.component != "performance":
                    continue

                # Find matching metrics
                matching_metrics = [
                    m
                    for m in recent_metrics
                    if m.get("metric_name") == threshold.metric_name
                ]

                if matching_metrics:
                    latest_metric = matching_metrics[-1]
                    await self._evaluate_threshold_breach(
                        threshold, latest_metric["value"], latest_metric
                    )

        except Exception as e:
            logger.error(f"Error checking performance metrics: {e}")

    async def _check_signal_processing_metrics(self):
        """Check signal processing metrics against thresholds"""
        if not self.signal_tracker:
            return

        try:
            # Get performance summary
            summary = getattr(
                self.signal_tracker, "get_performance_summary", lambda **kwargs: {}
            )(minutes=10)

            # Check average processing time
            if "avg_processing_time_ms" in summary:
                await self._check_metric_threshold(
                    "signal_processor",
                    "avg_processing_time_ms",
                    summary["avg_processing_time_ms"],
                    summary,
                )

            # Check success rate
            if "success_rate" in summary:
                success_rate_pct = summary["success_rate"] * 100
                await self._check_metric_threshold(
                    "signal_processor", "success_rate", success_rate_pct, summary
                )

            # Check throughput
            if "signals_per_minute" in summary:
                await self._check_metric_threshold(
                    "signal_processor",
                    "throughput",
                    summary["signals_per_minute"],
                    summary,
                )

        except Exception as e:
            logger.error(f"Error checking signal processing metrics: {e}")

    async def _check_order_execution_metrics(self):
        """Check order execution metrics against thresholds"""
        if not self.order_tracker:
            return

        try:
            # Get execution summary
            summary = getattr(
                self.order_tracker, "get_execution_summary", lambda **kwargs: {}
            )(minutes=10)

            # Check average execution time
            if "avg_execution_time_ms" in summary:
                await self._check_metric_threshold(
                    "order_client",
                    "avg_execution_time_ms",
                    summary["avg_execution_time_ms"],
                    summary,
                )

            # Check fill rate
            if "fill_rate" in summary:
                fill_rate_pct = summary["fill_rate"] * 100
                await self._check_metric_threshold(
                    "order_client", "fill_rate", fill_rate_pct, summary
                )

            # Check error rate
            if "error_rate" in summary:
                error_rate_pct = summary["error_rate"] * 100
                await self._check_metric_threshold(
                    "order_client", "error_rate", error_rate_pct, summary
                )

        except Exception as e:
            logger.error(f"Error checking order execution metrics: {e}")

    async def _check_database_metrics(self):
        """Check database performance metrics against thresholds"""
        if not self.database_tracker:
            return

        try:
            # Get database health summary
            health = getattr(
                self.database_tracker, "get_database_health_summary", lambda: {}
            )()

            # Check query performance
            query_perf = health.get("query_performance", {})
            if "execution_time_stats" in query_perf:
                avg_query_time = query_perf["execution_time_stats"].get("avg_ms", 0)
                await self._check_metric_threshold(
                    "database", "avg_query_time_ms", avg_query_time, health
                )

            # Check success rate
            if "success_rate" in query_perf:
                success_rate_pct = query_perf["success_rate"] * 100
                await self._check_metric_threshold(
                    "database", "success_rate", success_rate_pct, health
                )

        except Exception as e:
            logger.error(f"Error checking database metrics: {e}")

    async def _check_throughput_metrics(self):
        """Check throughput metrics against thresholds"""
        if not self.throughput_tracker:
            return

        try:
            # Get system throughput health
            health = getattr(
                self.throughput_tracker, "get_system_throughput_health", lambda: {}
            )()

            # Check total throughput rate
            if "total_throughput_rate" in health:
                await self._check_metric_threshold(
                    "system",
                    "total_throughput_rate",
                    health["total_throughput_rate"],
                    health,
                )

            # Check for bottlenecks
            if health.get("bottlenecks"):
                await self._handle_throughput_bottlenecks(health["bottlenecks"])

        except Exception as e:
            logger.error(f"Error checking throughput metrics: {e}")

    async def _check_error_rate_metrics(self):
        """Check error rate metrics against thresholds"""
        if not self.error_tracker:
            return

        try:
            # Get system error health
            health = getattr(
                self.error_tracker, "get_system_error_health", lambda: {}
            )()

            # Check total error rate
            if "total_error_rate" in health:
                await self._check_metric_threshold(
                    "system", "total_error_rate", health["total_error_rate"], health
                )

            # Check for error patterns
            if health.get("error_patterns_detected", 0) > 5:
                await self._handle_error_patterns(health)

        except Exception as e:
            logger.error(f"Error checking error rate metrics: {e}")

    async def _check_metric_threshold(
        self,
        component: str,
        metric_name: str,
        current_value: float,
        context: dict[str, Any],
    ):
        """Check specific metric against threshold"""
        threshold_key = f"{component}_{metric_name}"

        if threshold_key not in self.metric_thresholds:
            return

        threshold = self.metric_thresholds[threshold_key]
        await self._evaluate_threshold_breach(threshold, current_value, context)

    async def _evaluate_threshold_breach(
        self, threshold: MetricThreshold, current_value: float, context: dict[str, Any]
    ):
        """Evaluate if threshold is breached and create alert if needed"""

        if not threshold.enabled:
            return

        # Evaluate condition
        breached = False
        threshold_value = None
        severity = AlertSeverity.MEDIUM

        if threshold.emergency_threshold is not None:
            if self._compare_values(
                current_value,
                threshold.emergency_threshold,
                threshold.comparison_operator,
            ):
                breached = True
                threshold_value = threshold.emergency_threshold
                severity = AlertSeverity.EMERGENCY

        if not breached and self._compare_values(
            current_value, threshold.critical_threshold, threshold.comparison_operator
        ):
            breached = True
            threshold_value = threshold.critical_threshold
            severity = AlertSeverity.CRITICAL

        if not breached and self._compare_values(
            current_value, threshold.warning_threshold, threshold.comparison_operator
        ):
            breached = True
            threshold_value = threshold.warning_threshold
            severity = AlertSeverity.HIGH

        if breached:
            await self._handle_threshold_breach(
                threshold, current_value, threshold_value, severity, context
            )
        else:
            # Check if we should resolve existing alert
            await self._check_threshold_resolution(threshold, current_value)

    def _compare_values(self, value1: float, value2: float, operator: str) -> bool:
        """Compare two values using specified operator"""
        if operator == ">":
            return value1 > value2
        elif operator == "<":
            return value1 < value2
        elif operator == ">=":
            return value1 >= value2
        elif operator == "<=":
            return value1 <= value2
        elif operator == "==":
            return value1 == value2
        elif operator == "!=":
            return value1 != value2
        else:
            return False

    async def _handle_threshold_breach(
        self,
        threshold: MetricThreshold,
        current_value: float,
        threshold_value: float,
        severity: AlertSeverity,
        context: dict[str, Any],
    ):
        """Handle threshold breach"""

        breach_key = f"{threshold.component}_{threshold.metric_name}"
        current_time = datetime.now()

        # Track breach duration
        if breach_key not in self.breach_tracking:
            self.breach_tracking[breach_key] = []

        self.breach_tracking[breach_key].append(current_time)

        # Clean old breach records
        cutoff_time = current_time - timedelta(minutes=threshold.duration_minutes * 2)
        self.breach_tracking[breach_key] = [
            t for t in self.breach_tracking[breach_key] if t >= cutoff_time
        ]

        # Check if breach has persisted long enough
        breach_duration_cutoff = current_time - timedelta(
            minutes=threshold.duration_minutes
        )
        persistent_breaches = [
            t for t in self.breach_tracking[breach_key] if t >= breach_duration_cutoff
        ]

        if len(persistent_breaches) >= threshold.duration_minutes / (
            self.check_interval / 60
        ):
            # Create alert
            if threshold.alert_rule_id:
                alert = self.alert_manager.create_alert(
                    rule_id=threshold.alert_rule_id,
                    triggered_by=f"Performance metric threshold breach: {threshold.metric_name}",
                    current_value=current_value,
                    threshold_value=threshold_value,
                    affected_components=[
                        f"{threshold.component}_{threshold.metric_name}"
                    ],
                    context={
                        "metric_name": threshold.metric_name,
                        "component": threshold.component,
                        "current_value": current_value,
                        "threshold_value": threshold_value,
                        "comparison_operator": threshold.comparison_operator,
                        "breach_duration_minutes": threshold.duration_minutes,
                        "severity": severity.value,
                        "context": context,
                    },
                )

                if alert:
                    logger.warning(
                        f"Performance threshold breach: {threshold.component}.{threshold.metric_name} "
                        f"= {current_value} {threshold.comparison_operator} {threshold_value}"
                    )

    async def _check_threshold_resolution(
        self, threshold: MetricThreshold, current_value: float
    ):
        """Check if threshold breach should be resolved"""

        # Simple resolution check - value is no longer breaching any threshold
        if not (
            self._compare_values(
                current_value,
                threshold.warning_threshold,
                threshold.comparison_operator,
            )
            or self._compare_values(
                current_value,
                threshold.critical_threshold,
                threshold.comparison_operator,
            )
            or (
                threshold.emergency_threshold
                and self._compare_values(
                    current_value,
                    threshold.emergency_threshold,
                    threshold.comparison_operator,
                )
            )
        ):
            # Clear breach tracking
            breach_key = f"{threshold.component}_{threshold.metric_name}"
            if breach_key in self.breach_tracking:
                del self.breach_tracking[breach_key]

            # Find and resolve any active alerts for this threshold
            if threshold.alert_rule_id:
                active_alerts = self.alert_manager.get_active_alerts()
                for alert in active_alerts:
                    if alert.rule_id == threshold.alert_rule_id:
                        self.alert_manager.resolve_alert(
                            alert.alert_id,
                            resolved_by="performance_monitor",
                            notes=f"Metric {threshold.metric_name} returned to acceptable level: {current_value}",
                            auto_resolved=True,
                        )

    async def _handle_throughput_bottlenecks(self, bottlenecks: list[str]):
        """Handle detected throughput bottlenecks"""
        if self.operational_monitor:
            self.operational_monitor.record_operational_event(
                OperationalIssueType.API_DEGRADATION,
                "throughput_monitor",
                f"Throughput bottlenecks detected: {', '.join(bottlenecks[:3])}",
                AlertSeverity.HIGH,
                {"bottlenecks": bottlenecks},
            )

    async def _handle_error_patterns(self, health: dict[str, Any]):
        """Handle detected error patterns"""
        if self.operational_monitor:
            self.operational_monitor.record_operational_event(
                OperationalIssueType.TRADING_ANOMALY,
                "error_pattern_detector",
                f"Multiple error patterns detected ({health['error_patterns_detected']} patterns)",
                AlertSeverity.HIGH,
                {"error_health": health},
            )

    async def _check_integration_health(self):
        """Check health of performance metrics integration"""

        # Check if trackers are responsive
        unhealthy_trackers = []

        try:
            # Simple health check - try to get recent data
            if self.performance_tracker:
                try:
                    getattr(
                        self.performance_tracker, "get_recent_metrics", lambda x: []
                    )(minutes=1)
                except Exception:
                    unhealthy_trackers.append("performance_tracker")

            if self.signal_tracker:
                try:
                    getattr(
                        self.signal_tracker,
                        "get_performance_summary",
                        lambda **kwargs: {},
                    )(minutes=1)
                except Exception:
                    unhealthy_trackers.append("signal_tracker")

            if self.order_tracker:
                try:
                    getattr(
                        self.order_tracker, "get_execution_summary", lambda **kwargs: {}
                    )(minutes=1)
                except Exception:
                    unhealthy_trackers.append("order_tracker")

            if unhealthy_trackers and self.operational_monitor:
                self.operational_monitor.record_operational_event(
                    OperationalIssueType.BUSINESS_PROCESS_FAILURE,
                    "performance_integration",
                    f"Performance trackers not responsive: {', '.join(unhealthy_trackers)}",
                    AlertSeverity.HIGH,
                    {"unhealthy_trackers": unhealthy_trackers},
                )

        except Exception as e:
            logger.error(f"Error in integration health check: {e}")

    def get_integration_status(self) -> dict[str, Any]:
        """Get status of performance metrics integration"""

        connected_trackers = []
        if self.performance_tracker:
            connected_trackers.append("performance_tracker")
        if self.signal_tracker:
            connected_trackers.append("signal_tracker")
        if self.order_tracker:
            connected_trackers.append("order_tracker")
        if self.database_tracker:
            connected_trackers.append("database_tracker")
        if self.throughput_tracker:
            connected_trackers.append("throughput_tracker")
        if self.error_tracker:
            connected_trackers.append("error_tracker")

        connected_monitors = []
        if self.system_monitor:
            connected_monitors.append("system_monitor")
        if self.operational_monitor:
            connected_monitors.append("operational_monitor")
        if self.risk_monitor:
            connected_monitors.append("risk_monitor")

        return {
            "running": self.running,
            "connected_trackers": connected_trackers,
            "connected_monitors": connected_monitors,
            "metric_thresholds": len(self.metric_thresholds),
            "performance_alerts": len(self.performance_alerts),
            "active_breaches": len(self.breach_tracking),
            "check_interval_seconds": self.check_interval,
            "timestamp": datetime.now().isoformat(),
        }


def create_default_performance_thresholds() -> list[MetricThreshold]:
    """Create default performance metric thresholds"""

    return [
        # Signal Processing Metrics
        MetricThreshold(
            metric_name="avg_processing_time_ms",
            component="signal_processor",
            warning_threshold=100.0,
            critical_threshold=500.0,
            emergency_threshold=1000.0,
            comparison_operator=">",
            duration_minutes=3,
        ),
        MetricThreshold(
            metric_name="success_rate",
            component="signal_processor",
            warning_threshold=95.0,
            critical_threshold=90.0,
            emergency_threshold=80.0,
            comparison_operator="<",
            duration_minutes=5,
        ),
        # Order Execution Metrics
        MetricThreshold(
            metric_name="avg_execution_time_ms",
            component="order_client",
            warning_threshold=200.0,
            critical_threshold=1000.0,
            emergency_threshold=5000.0,
            comparison_operator=">",
            duration_minutes=2,
        ),
        MetricThreshold(
            metric_name="fill_rate",
            component="order_client",
            warning_threshold=90.0,
            critical_threshold=80.0,
            emergency_threshold=70.0,
            comparison_operator="<",
            duration_minutes=5,
        ),
        MetricThreshold(
            metric_name="error_rate",
            component="order_client",
            warning_threshold=5.0,
            critical_threshold=15.0,
            emergency_threshold=25.0,
            comparison_operator=">",
            duration_minutes=3,
        ),
        # Database Metrics
        MetricThreshold(
            metric_name="avg_query_time_ms",
            component="database",
            warning_threshold=100.0,
            critical_threshold=500.0,
            emergency_threshold=2000.0,
            comparison_operator=">",
            duration_minutes=2,
        ),
        MetricThreshold(
            metric_name="success_rate",
            component="database",
            warning_threshold=98.0,
            critical_threshold=95.0,
            emergency_threshold=90.0,
            comparison_operator="<",
            duration_minutes=3,
        ),
        # System Metrics
        MetricThreshold(
            metric_name="total_throughput_rate",
            component="system",
            warning_threshold=10.0,
            critical_threshold=5.0,
            emergency_threshold=1.0,
            comparison_operator="<",
            duration_minutes=5,
        ),
        MetricThreshold(
            metric_name="total_error_rate",
            component="system",
            warning_threshold=10.0,
            critical_threshold=50.0,
            emergency_threshold=100.0,
            comparison_operator=">",
            duration_minutes=2,
        ),
    ]


def create_default_performance_alerts() -> list[PerformanceAlert]:
    """Create default performance alert configurations"""

    thresholds = create_default_performance_thresholds()

    # Group thresholds by component
    threshold_groups = {}
    for threshold in thresholds:
        if threshold.component not in threshold_groups:
            threshold_groups[threshold.component] = []
        threshold_groups[threshold.component].append(threshold)

    alerts = []

    for component, component_thresholds in threshold_groups.items():
        alert = PerformanceAlert(
            alert_id=f"perf_alert_{component}",
            name=f"Performance Alert - {component.title()}",
            description=f"Performance degradation detected in {component} component",
            metric_thresholds=component_thresholds,
            severity=AlertSeverity.HIGH,
            category=AlertCategory.PERFORMANCE_DEGRADATION,
            cooldown_minutes=10,
            auto_resolve=True,
        )
        alerts.append(alert)

    return alerts


async def initialize_performance_integration(
    performance_integration_manager: PerformanceIntegrationManager | None = None,
    alert_manager: AlertManager | None = None,
    auto_start: bool = True,
) -> PerformanceMetricsConnector:
    """Initialize performance metrics integration with alerting system"""

    connector = PerformanceMetricsConnector(alert_manager)

    # Connect to performance integration manager if provided
    if performance_integration_manager:
        if hasattr(performance_integration_manager, "performance_tracker"):
            connector.set_performance_tracker(
                performance_integration_manager.performance_tracker
            )
        if hasattr(performance_integration_manager, "signal_tracker"):
            connector.set_signal_tracker(performance_integration_manager.signal_tracker)
        if hasattr(performance_integration_manager, "order_tracker"):
            connector.set_order_tracker(performance_integration_manager.order_tracker)
        if hasattr(performance_integration_manager, "database_tracker"):
            connector.set_database_tracker(
                performance_integration_manager.database_tracker
            )
        if hasattr(performance_integration_manager, "throughput_tracker"):
            connector.set_throughput_tracker(
                performance_integration_manager.throughput_tracker
            )
        if hasattr(performance_integration_manager, "error_tracker"):
            connector.set_error_tracker(performance_integration_manager.error_tracker)

    # Add default thresholds and alerts
    default_thresholds = create_default_performance_thresholds()
    for threshold in default_thresholds:
        connector.add_metric_threshold(threshold)

    default_alerts = create_default_performance_alerts()
    for alert in default_alerts:
        connector.add_performance_alert(alert)

    # Start monitoring if requested
    if auto_start:
        await connector.start_monitoring()

    logger.info("Performance metrics integration initialized")
    return connector
