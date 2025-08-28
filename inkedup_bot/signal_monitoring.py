"""
Comprehensive signal monitoring and alerting system for the trading bot.

This module provides real-time monitoring of signal processing with advanced alerting,
performance tracking, and anomaly detection capabilities.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .signal_cleanup_manager import SignalInterferenceLevel
from .signals import TradingSignal

logger = logging.getLogger("signal_monitoring")


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class MonitoringMetric(str, Enum):
    """Types of monitoring metrics."""

    SIGNAL_THROUGHPUT = "signal_throughput"
    PROCESSING_LATENCY = "processing_latency"
    ERROR_RATE = "error_rate"
    INTERFERENCE_RATE = "interference_rate"
    TIMEOUT_RATE = "timeout_rate"
    QUEUE_DEPTH = "queue_depth"
    SYSTEM_LOAD = "system_load"
    MEMORY_USAGE = "memory_usage"
    SUCCESS_RATE = "success_rate"


@dataclass
class Alert:
    """Signal processing alert."""

    id: str
    severity: AlertSeverity
    metric: MonitoringMetric
    message: str
    details: dict[str, Any]
    timestamp: float
    signal_id: str | None = None
    auto_resolved: bool = False
    resolution_actions: list[str] = field(default_factory=list)


@dataclass
class MetricThreshold:
    """Threshold configuration for monitoring metrics."""

    metric: MonitoringMetric
    warning_threshold: float
    error_threshold: float
    critical_threshold: float
    emergency_threshold: float | None = None
    measurement_window: float = 60.0  # seconds
    minimum_samples: int = 5


@dataclass
class MonitoringWindow:
    """Time-based monitoring window for metrics."""

    window_size: float  # seconds
    max_samples: int
    samples: deque = field(default_factory=deque)

    def add_sample(self, value: float, timestamp: float | None = None) -> None:
        """Add a sample to the monitoring window."""
        if timestamp is None:
            timestamp = time.time()

        # Remove old samples outside the window
        cutoff_time = timestamp - self.window_size
        while self.samples and self.samples[0][1] < cutoff_time:
            self.samples.popleft()

        # Add new sample
        self.samples.append((value, timestamp))

        # Enforce max samples
        if len(self.samples) > self.max_samples:
            self.samples.popleft()

    def get_average(self) -> float:
        """Get average value in the window."""
        if not self.samples:
            return 0.0
        return sum(sample[0] for sample in self.samples) / len(self.samples)

    def get_rate(self) -> float:
        """Get rate (samples per second) in the window."""
        if len(self.samples) < 2:
            return 0.0

        time_span = self.samples[-1][1] - self.samples[0][1]
        return len(self.samples) / time_span if time_span > 0 else 0.0

    def get_max(self) -> float:
        """Get maximum value in the window."""
        if not self.samples:
            return 0.0
        return max(sample[0] for sample in self.samples)


class SignalMonitoringSystem:
    """
    Comprehensive signal monitoring and alerting system.

    Features:
    - Real-time performance monitoring
    - Threshold-based alerting with multiple severity levels
    - Anomaly detection for unusual patterns
    - Historical trend analysis
    - Automatic alert escalation and resolution
    - Integration with external alerting systems
    - Performance regression detection
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

        # Monitoring windows for different metrics
        self._metric_windows: dict[MonitoringMetric, MonitoringWindow] = {}

        # Alert management
        self._active_alerts: dict[str, Alert] = {}
        self._alert_history: deque = deque(maxlen=10000)
        self._alert_handlers: dict[AlertSeverity, list[Callable]] = defaultdict(list)

        # Metric thresholds
        self._metric_thresholds: dict[MonitoringMetric, MetricThreshold] = {}

        # Performance tracking
        self._signal_metrics: dict[str, dict[str, Any]] = defaultdict(dict)
        self._performance_baselines: dict[MonitoringMetric, float] = {}

        # Anomaly detection
        self._anomaly_detectors: dict[MonitoringMetric, Any] = {}

        # System state tracking
        self._last_health_check: float = 0.0
        self._system_healthy: bool = True

        # Initialize default configuration
        self._initialize_default_thresholds()
        self._initialize_monitoring_windows()

        # Background monitoring task
        self._monitoring_task: asyncio.Task | None = None
        self._monitoring_active: bool = False

        logger.info("SignalMonitoringSystem initialized")

    def _initialize_default_thresholds(self):
        """Initialize default metric thresholds."""

        self._metric_thresholds = {
            MonitoringMetric.SIGNAL_THROUGHPUT: MetricThreshold(
                metric=MonitoringMetric.SIGNAL_THROUGHPUT,
                warning_threshold=0.5,  # signals/sec
                error_threshold=0.1,  # signals/sec
                critical_threshold=0.05,  # signals/sec
                emergency_threshold=0.0,  # signals/sec
                measurement_window=60.0,
                minimum_samples=10,
            ),
            MonitoringMetric.PROCESSING_LATENCY: MetricThreshold(
                metric=MonitoringMetric.PROCESSING_LATENCY,
                warning_threshold=5.0,  # seconds
                error_threshold=15.0,  # seconds
                critical_threshold=30.0,  # seconds
                emergency_threshold=60.0,  # seconds
                measurement_window=300.0,
                minimum_samples=5,
            ),
            MonitoringMetric.ERROR_RATE: MetricThreshold(
                metric=MonitoringMetric.ERROR_RATE,
                warning_threshold=0.05,  # 5%
                error_threshold=0.15,  # 15%
                critical_threshold=0.30,  # 30%
                emergency_threshold=0.50,  # 50%
                measurement_window=120.0,
                minimum_samples=10,
            ),
            MonitoringMetric.TIMEOUT_RATE: MetricThreshold(
                metric=MonitoringMetric.TIMEOUT_RATE,
                warning_threshold=0.02,  # 2%
                error_threshold=0.10,  # 10%
                critical_threshold=0.25,  # 25%
                emergency_threshold=0.40,  # 40%
                measurement_window=300.0,
                minimum_samples=5,
            ),
            MonitoringMetric.INTERFERENCE_RATE: MetricThreshold(
                metric=MonitoringMetric.INTERFERENCE_RATE,
                warning_threshold=0.03,  # 3%
                error_threshold=0.10,  # 10%
                critical_threshold=0.20,  # 20%
                emergency_threshold=0.35,  # 35%
                measurement_window=180.0,
                minimum_samples=8,
            ),
            MonitoringMetric.QUEUE_DEPTH: MetricThreshold(
                metric=MonitoringMetric.QUEUE_DEPTH,
                warning_threshold=10.0,  # signals
                error_threshold=25.0,  # signals
                critical_threshold=50.0,  # signals
                emergency_threshold=100.0,  # signals
                measurement_window=60.0,
                minimum_samples=3,
            ),
            MonitoringMetric.MEMORY_USAGE: MetricThreshold(
                metric=MonitoringMetric.MEMORY_USAGE,
                warning_threshold=0.70,  # 70%
                error_threshold=0.85,  # 85%
                critical_threshold=0.95,  # 95%
                emergency_threshold=0.98,  # 98%
                measurement_window=30.0,
                minimum_samples=3,
            ),
            MonitoringMetric.SUCCESS_RATE: MetricThreshold(
                metric=MonitoringMetric.SUCCESS_RATE,
                warning_threshold=0.90,  # 90% (below this is warning)
                error_threshold=0.75,  # 75%
                critical_threshold=0.50,  # 50%
                emergency_threshold=0.25,  # 25%
                measurement_window=600.0,
                minimum_samples=10,
            ),
        }

    def _initialize_monitoring_windows(self):
        """Initialize monitoring windows for each metric."""

        for metric, threshold in self._metric_thresholds.items():
            window_size = threshold.measurement_window
            max_samples = max(threshold.minimum_samples * 10, 1000)

            self._metric_windows[metric] = MonitoringWindow(
                window_size=window_size, max_samples=max_samples
            )

    async def start_monitoring(self):
        """Start the background monitoring system."""
        if self._monitoring_active:
            logger.warning("Monitoring already active")
            return

        self._monitoring_active = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Signal monitoring system started")

    async def stop_monitoring(self):
        """Stop the background monitoring system."""
        if not self._monitoring_active:
            return

        self._monitoring_active = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Signal monitoring system stopped")

    async def _monitoring_loop(self):
        """Main monitoring loop."""
        try:
            while self._monitoring_active:
                await self._perform_health_check()
                await self._check_metric_thresholds()
                await self._detect_anomalies()
                await self._update_baselines()

                # Check for alert auto-resolution
                await self._check_alert_resolution()

                # Sleep for monitoring interval
                await asyncio.sleep(self.config.get("monitoring_interval", 10.0))

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")

    def record_signal_submitted(
        self, signal: TradingSignal, timestamp: float | None = None
    ):
        """Record that a signal was submitted for processing."""
        if timestamp is None:
            timestamp = time.time()

        signal_id = signal.signal_id
        self._signal_metrics[signal_id]["submitted_at"] = timestamp

        # Update throughput metric
        self._metric_windows[MonitoringMetric.SIGNAL_THROUGHPUT].add_sample(
            1.0, timestamp
        )

    def record_signal_completed(self, signal_id: str, timestamp: float | None = None):
        """Record that a signal completed processing."""
        if timestamp is None:
            timestamp = time.time()

        if signal_id in self._signal_metrics:
            self._signal_metrics[signal_id]["completed_at"] = timestamp

            # Calculate and record processing latency
            submitted_at = self._signal_metrics[signal_id].get("submitted_at")
            if submitted_at:
                latency = timestamp - submitted_at
                self._metric_windows[MonitoringMetric.PROCESSING_LATENCY].add_sample(
                    latency, timestamp
                )

        # Update success rate
        self._record_success_rate(True, timestamp)

    def record_signal_failed(
        self, signal_id: str, error: str, timestamp: float | None = None
    ):
        """Record that a signal failed processing."""
        if timestamp is None:
            timestamp = time.time()

        if signal_id in self._signal_metrics:
            self._signal_metrics[signal_id]["failed_at"] = timestamp
            self._signal_metrics[signal_id]["error"] = error

        # Update error rate and success rate
        self._metric_windows[MonitoringMetric.ERROR_RATE].add_sample(1.0, timestamp)
        self._record_success_rate(False, timestamp)

    def record_signal_timeout(self, signal_id: str, timestamp: float | None = None):
        """Record that a signal timed out."""
        if timestamp is None:
            timestamp = time.time()

        if signal_id in self._signal_metrics:
            self._signal_metrics[signal_id]["timeout_at"] = timestamp

        # Update timeout rate
        self._metric_windows[MonitoringMetric.TIMEOUT_RATE].add_sample(1.0, timestamp)
        self._record_success_rate(False, timestamp)

    def record_signal_interference(
        self,
        signal_id: str,
        interference_level: SignalInterferenceLevel,
        timestamp: float | None = None,
    ):
        """Record signal interference incident."""
        if timestamp is None:
            timestamp = time.time()

        # Weight interference by severity
        interference_weights = {
            SignalInterferenceLevel.NONE: 0.0,
            SignalInterferenceLevel.LOW: 0.2,
            SignalInterferenceLevel.MODERATE: 0.5,
            SignalInterferenceLevel.HIGH: 0.8,
            SignalInterferenceLevel.CRITICAL: 1.0,
        }

        weight = interference_weights.get(interference_level, 0.5)
        self._metric_windows[MonitoringMetric.INTERFERENCE_RATE].add_sample(
            weight, timestamp
        )

    def record_queue_depth(self, depth: int, timestamp: float | None = None):
        """Record current signal queue depth."""
        if timestamp is None:
            timestamp = time.time()

        self._metric_windows[MonitoringMetric.QUEUE_DEPTH].add_sample(
            float(depth), timestamp
        )

    def record_system_metrics(
        self, cpu_usage: float, memory_usage: float, timestamp: float | None = None
    ):
        """Record system performance metrics."""
        if timestamp is None:
            timestamp = time.time()

        self._metric_windows[MonitoringMetric.SYSTEM_LOAD].add_sample(
            cpu_usage, timestamp
        )
        self._metric_windows[MonitoringMetric.MEMORY_USAGE].add_sample(
            memory_usage, timestamp
        )

    def _record_success_rate(self, success: bool, timestamp: float):
        """Record success/failure for success rate calculation."""
        # Success rate is inverse - record 1.0 for success, 0.0 for failure
        value = 1.0 if success else 0.0
        self._metric_windows[MonitoringMetric.SUCCESS_RATE].add_sample(value, timestamp)

    async def _perform_health_check(self):
        """Perform comprehensive system health check."""
        current_time = time.time()

        # Skip if too recent
        if current_time - self._last_health_check < 30.0:
            return

        self._last_health_check = current_time
        health_issues = []

        # Check each metric window for health
        for metric, window in self._metric_windows.items():
            if len(window.samples) == 0:
                continue

            threshold = self._metric_thresholds.get(metric)
            if not threshold:
                continue

            current_value = self._get_metric_current_value(metric, window)
            severity = self._assess_metric_severity(metric, current_value, threshold)

            if severity != AlertSeverity.INFO:
                health_issues.append(
                    {
                        "metric": metric,
                        "value": current_value,
                        "severity": severity,
                        "threshold": threshold,
                    }
                )

        # Update system health status
        previous_health = self._system_healthy
        self._system_healthy = len(health_issues) == 0

        # Generate alert if health status changed
        if previous_health and not self._system_healthy:
            await self._generate_alert(
                severity=AlertSeverity.ERROR,
                metric=MonitoringMetric.SYSTEM_LOAD,  # Generic system metric
                message=f"System health degraded - {len(health_issues)} issues detected",
                details={"health_issues": health_issues},
            )
        elif not previous_health and self._system_healthy:
            await self._generate_alert(
                severity=AlertSeverity.INFO,
                metric=MonitoringMetric.SYSTEM_LOAD,
                message="System health restored - all metrics within normal ranges",
                details={"recovery_time": current_time},
            )

    def _get_metric_current_value(
        self, metric: MonitoringMetric, window: MonitoringWindow
    ) -> float:
        """Get current value for a metric based on its type."""

        if metric in [
            MonitoringMetric.ERROR_RATE,
            MonitoringMetric.TIMEOUT_RATE,
            MonitoringMetric.INTERFERENCE_RATE,
            MonitoringMetric.SUCCESS_RATE,
        ]:
            return window.get_average()  # Rate metrics use average
        elif metric == MonitoringMetric.SIGNAL_THROUGHPUT:
            return window.get_rate()  # Throughput is samples per second
        elif metric in [
            MonitoringMetric.PROCESSING_LATENCY,
            MonitoringMetric.QUEUE_DEPTH,
            MonitoringMetric.SYSTEM_LOAD,
            MonitoringMetric.MEMORY_USAGE,
        ]:
            return window.get_average()  # Value metrics use average
        else:
            return window.get_average()  # Default to average

    def _assess_metric_severity(
        self, metric: MonitoringMetric, value: float, threshold: MetricThreshold
    ) -> AlertSeverity:
        """Assess severity level for a metric value."""

        # Special handling for success rate (lower is worse)
        if metric == MonitoringMetric.SUCCESS_RATE:
            if value <= threshold.emergency_threshold:
                return AlertSeverity.EMERGENCY
            elif value <= threshold.critical_threshold:
                return AlertSeverity.CRITICAL
            elif value <= threshold.error_threshold:
                return AlertSeverity.ERROR
            elif value <= threshold.warning_threshold:
                return AlertSeverity.WARNING
            else:
                return AlertSeverity.INFO

        # Normal handling (higher is worse)
        if threshold.emergency_threshold and value >= threshold.emergency_threshold:
            return AlertSeverity.EMERGENCY
        elif value >= threshold.critical_threshold:
            return AlertSeverity.CRITICAL
        elif value >= threshold.error_threshold:
            return AlertSeverity.ERROR
        elif value >= threshold.warning_threshold:
            return AlertSeverity.WARNING
        else:
            return AlertSeverity.INFO

    async def _check_metric_thresholds(self):
        """Check all metrics against their thresholds and generate alerts."""

        for metric, threshold in self._metric_thresholds.items():
            window = self._metric_windows.get(metric)
            if not window or len(window.samples) < threshold.minimum_samples:
                continue

            current_value = self._get_metric_current_value(metric, window)
            severity = self._assess_metric_severity(metric, current_value, threshold)

            if severity != AlertSeverity.INFO:
                await self._generate_alert(
                    severity=severity,
                    metric=metric,
                    message=f"{metric.value} threshold exceeded: {current_value:.3f}",
                    details={
                        "current_value": current_value,
                        "threshold": threshold.__dict__,
                        "window_samples": len(window.samples),
                    },
                )

    async def _generate_alert(
        self,
        severity: AlertSeverity,
        metric: MonitoringMetric,
        message: str,
        details: dict[str, Any],
        signal_id: str | None = None,
    ):
        """Generate and process an alert."""

        alert_id = f"{metric.value}_{severity.value}_{int(time.time() * 1000)}"

        alert = Alert(
            id=alert_id,
            severity=severity,
            metric=metric,
            message=message,
            details=details,
            timestamp=time.time(),
            signal_id=signal_id,
        )

        # Check for duplicate alerts (same metric + severity in last 60 seconds)
        if self._is_duplicate_alert(alert):
            return

        # Store alert
        self._active_alerts[alert_id] = alert
        self._alert_history.append(alert)

        # Execute alert handlers
        handlers = self._alert_handlers.get(severity, [])
        for handler in handlers:
            try:
                await handler(alert)
            except Exception as e:
                logger.error(f"Error executing alert handler: {e}")

        logger.warning(f"Generated alert [{severity.value}] {message}")

    def _is_duplicate_alert(self, alert: Alert) -> bool:
        """Check if this is a duplicate of a recent alert."""
        cutoff_time = alert.timestamp - 60.0  # 60 second dedup window

        for existing_alert in self._active_alerts.values():
            if (
                existing_alert.metric == alert.metric
                and existing_alert.severity == alert.severity
                and existing_alert.timestamp > cutoff_time
            ):
                return True

        return False

    async def _detect_anomalies(self):
        """Detect anomalous patterns in metrics."""
        # This could be enhanced with more sophisticated anomaly detection
        # For now, implement simple statistical anomaly detection

        for metric, window in self._metric_windows.items():
            if len(window.samples) < 20:  # Need sufficient data
                continue

            recent_values = [sample[0] for sample in list(window.samples)[-10:]]
            historical_values = [sample[0] for sample in list(window.samples)[:-10]]

            if len(historical_values) < 10:
                continue

            # Simple anomaly detection: check if recent average is significantly different
            recent_avg = sum(recent_values) / len(recent_values)
            historical_avg = sum(historical_values) / len(historical_values)

            if historical_avg == 0:
                continue

            deviation = abs(recent_avg - historical_avg) / historical_avg

            # Flag as anomaly if deviation > 200%
            if deviation > 2.0:
                await self._generate_alert(
                    severity=AlertSeverity.WARNING,
                    metric=metric,
                    message=f"Anomalous pattern detected in {metric.value}",
                    details={
                        "recent_average": recent_avg,
                        "historical_average": historical_avg,
                        "deviation_percentage": deviation * 100,
                    },
                )

    async def _update_baselines(self):
        """Update performance baselines for comparison."""
        for metric, window in self._metric_windows.items():
            if len(window.samples) >= 100:  # Need sufficient historical data
                self._performance_baselines[metric] = window.get_average()

    async def _check_alert_resolution(self):
        """Check if any active alerts can be automatically resolved."""
        current_time = time.time()
        resolved_alerts = []

        for alert_id, alert in list(self._active_alerts.items()):
            # Auto-resolve alerts older than 1 hour if conditions are normal
            if current_time - alert.timestamp > 3600:
                window = self._metric_windows.get(alert.metric)
                if window and len(window.samples) > 0:
                    current_value = self._get_metric_current_value(alert.metric, window)
                    threshold = self._metric_thresholds.get(alert.metric)

                    if threshold:
                        severity = self._assess_metric_severity(
                            alert.metric, current_value, threshold
                        )
                        if severity == AlertSeverity.INFO:
                            alert.auto_resolved = True
                            alert.resolution_actions.append(
                                "Auto-resolved: metric returned to normal"
                            )
                            resolved_alerts.append(alert_id)

        # Remove resolved alerts
        for alert_id in resolved_alerts:
            del self._active_alerts[alert_id]
            logger.info(f"Auto-resolved alert {alert_id}")

    def add_alert_handler(
        self, severity: AlertSeverity, handler: Callable[[Alert], None]
    ):
        """Add a custom alert handler for specific severity levels."""
        self._alert_handlers[severity].append(handler)

    def get_monitoring_summary(self) -> dict[str, Any]:
        """Get comprehensive monitoring summary."""
        current_time = time.time()

        summary = {
            "system_healthy": self._system_healthy,
            "active_alerts": len(self._active_alerts),
            "total_signals_tracked": len(self._signal_metrics),
            "monitoring_active": self._monitoring_active,
            "last_health_check": self._last_health_check,
            "metrics": {},
            "recent_alerts": [],
        }

        # Add metric summaries
        for metric, window in self._metric_windows.items():
            if len(window.samples) > 0:
                summary["metrics"][metric.value] = {
                    "current_value": self._get_metric_current_value(metric, window),
                    "samples_count": len(window.samples),
                    "max_value": window.get_max(),
                    "average_value": window.get_average(),
                }

        # Add recent alerts (last 24 hours)
        cutoff_time = current_time - 86400  # 24 hours
        recent_alerts = [
            {
                "severity": alert.severity.value,
                "metric": alert.metric.value,
                "message": alert.message,
                "timestamp": alert.timestamp,
            }
            for alert in self._alert_history
            if alert.timestamp > cutoff_time
        ]
        summary["recent_alerts"] = recent_alerts[-50:]  # Last 50 alerts

        return summary
