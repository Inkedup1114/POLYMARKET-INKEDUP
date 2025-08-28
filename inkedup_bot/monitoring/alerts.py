"""
Error rate tracking and alerting system.

This module provides comprehensive error tracking, rate analysis, and intelligent
alerting for all system components with configurable thresholds and escalation.
"""

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


class AlertLevel(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Alert status states."""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


@dataclass
class Alert:
    """Individual alert with metadata and tracking."""

    id: str
    level: AlertLevel
    component: str
    title: str
    message: str
    timestamp: float = field(default_factory=time.time)
    status: AlertStatus = AlertStatus.ACTIVE
    tags: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Tracking fields
    first_occurrence: float | None = None
    last_occurrence: float | None = None
    occurrence_count: int = 1
    acknowledged_at: float | None = None
    resolved_at: float | None = None

    def __post_init__(self):
        if self.first_occurrence is None:
            self.first_occurrence = self.timestamp
        self.last_occurrence = self.timestamp

    def update_occurrence(self):
        """Update alert occurrence tracking."""
        self.last_occurrence = time.time()
        self.occurrence_count += 1

        # Reactivate if resolved
        if self.status == AlertStatus.RESOLVED:
            self.status = AlertStatus.ACTIVE
            self.resolved_at = None

    def acknowledge(self, acknowledged_by: str = "system"):
        """Acknowledge the alert."""
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_at = time.time()
        self.metadata["acknowledged_by"] = acknowledged_by

    def resolve(self, resolved_by: str = "system"):
        """Resolve the alert."""
        self.status = AlertStatus.RESOLVED
        self.resolved_at = time.time()
        self.metadata["resolved_by"] = resolved_by

    def suppress(self, duration_minutes: int = 60, suppressed_by: str = "system"):
        """Suppress the alert for a specified duration."""
        self.status = AlertStatus.SUPPRESSED
        self.metadata["suppressed_by"] = suppressed_by
        self.metadata["suppressed_until"] = time.time() + (duration_minutes * 60)

    def is_suppressed(self) -> bool:
        """Check if alert is currently suppressed."""
        if self.status != AlertStatus.SUPPRESSED:
            return False

        suppressed_until = self.metadata.get("suppressed_until", 0)
        return time.time() < suppressed_until

    def to_dict(self) -> dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "id": self.id,
            "level": self.level.value,
            "component": self.component,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "tags": self.tags,
            "metadata": self.metadata,
            "first_occurrence": self.first_occurrence,
            "last_occurrence": self.last_occurrence,
            "occurrence_count": self.occurrence_count,
            "acknowledged_at": self.acknowledged_at,
            "resolved_at": self.resolved_at,
        }


class ErrorRateTracker:
    """Tracks error rates for different components and operations."""

    def __init__(self, window_minutes: int = 5, bucket_size_seconds: int = 30):
        self.window_minutes = window_minutes
        self.bucket_size = bucket_size_seconds
        self.max_buckets = (window_minutes * 60) // bucket_size_seconds

        # Error tracking by component/operation
        self.error_buckets: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self.max_buckets)
        )
        self.success_buckets: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self.max_buckets)
        )

        # Current bucket tracking
        self.current_bucket_start: dict[str, float] = {}
        self.current_errors: dict[str, int] = defaultdict(int)
        self.current_successes: dict[str, int] = defaultdict(int)

        self.lock = threading.RLock()

    def record_event(
        self,
        component: str,
        operation: str,
        success: bool,
        tags: dict[str, str] | None = None,
    ):
        """Record an event (success or error) for error rate calculation."""
        key = f"{component}:{operation}"
        if tags:
            tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
            key = f"{key}[{tag_str}]"

        with self.lock:
            current_time = time.time()
            bucket_start = self._get_bucket_start(current_time)

            # Check if we need to rotate buckets
            if (
                key not in self.current_bucket_start
                or self.current_bucket_start[key] != bucket_start
            ):
                self._rotate_bucket(key, bucket_start)

            # Record the event
            if success:
                self.current_successes[key] += 1
            else:
                self.current_errors[key] += 1

    def get_error_rate(
        self, component: str, operation: str, tags: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Get current error rate for a component/operation."""
        key = f"{component}:{operation}"
        if tags:
            tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
            key = f"{key}[{tag_str}]"

        with self.lock:
            # Ensure current bucket is up to date
            current_time = time.time()
            bucket_start = self._get_bucket_start(current_time)
            if (
                key not in self.current_bucket_start
                or self.current_bucket_start[key] != bucket_start
            ):
                self._rotate_bucket(key, bucket_start)

            # Calculate error rate from all buckets
            total_errors = sum(self.error_buckets[key]) + self.current_errors[key]
            total_successes = (
                sum(self.success_buckets[key]) + self.current_successes[key]
            )
            total_events = total_errors + total_successes

            error_rate = (
                (total_errors / total_events) * 100 if total_events > 0 else 0.0
            )

            # Calculate trend (compare first half vs second half of window)
            half_buckets = len(self.error_buckets[key]) // 2
            if half_buckets > 0:
                first_half_errors = sum(list(self.error_buckets[key])[:half_buckets])
                first_half_successes = sum(
                    list(self.success_buckets[key])[:half_buckets]
                )
                first_half_total = first_half_errors + first_half_successes
                first_half_rate = (
                    (first_half_errors / first_half_total) * 100
                    if first_half_total > 0
                    else 0.0
                )

                second_half_errors = (
                    sum(list(self.error_buckets[key])[half_buckets:])
                    + self.current_errors[key]
                )
                second_half_successes = (
                    sum(list(self.success_buckets[key])[half_buckets:])
                    + self.current_successes[key]
                )
                second_half_total = second_half_errors + second_half_successes
                second_half_rate = (
                    (second_half_errors / second_half_total) * 100
                    if second_half_total > 0
                    else 0.0
                )

                if second_half_rate > first_half_rate * 1.5:
                    trend = "increasing"
                elif second_half_rate < first_half_rate * 0.5:
                    trend = "decreasing"
                else:
                    trend = "stable"
            else:
                trend = "insufficient_data"

            return {
                "component": component,
                "operation": operation,
                "tags": tags or {},
                "error_rate_percent": error_rate,
                "total_errors": total_errors,
                "total_successes": total_successes,
                "total_events": total_events,
                "window_minutes": self.window_minutes,
                "trend": trend,
                "timestamp": current_time,
            }

    def get_all_error_rates(self) -> dict[str, dict[str, Any]]:
        """Get error rates for all tracked components/operations."""
        with self.lock:
            results = {}

            # Get all unique keys
            all_keys = (
                set(self.error_buckets.keys())
                | set(self.success_buckets.keys())
                | set(self.current_errors.keys())
                | set(self.current_successes.keys())
            )

            for key in all_keys:
                # Parse key back to component and operation
                if "[" in key:
                    base_key, tag_part = key.split("[", 1)
                    tag_part = tag_part.rstrip("]")
                    tags = dict(
                        item.split("=", 1)
                        for item in tag_part.split(",")
                        if "=" in item
                    )
                else:
                    base_key = key
                    tags = {}

                if ":" in base_key:
                    component, operation = base_key.split(":", 1)
                    results[key] = self.get_error_rate(component, operation, tags)

            return results

    def _get_bucket_start(self, timestamp: float) -> float:
        """Get the start time of the bucket for a given timestamp."""
        return (timestamp // self.bucket_size) * self.bucket_size

    def _rotate_bucket(self, key: str, new_bucket_start: float):
        """Rotate to a new bucket, storing current counts."""
        if key in self.current_bucket_start:
            # Store current bucket data
            self.error_buckets[key].append(self.current_errors[key])
            self.success_buckets[key].append(self.current_successes[key])

        # Reset current counters
        self.current_errors[key] = 0
        self.current_successes[key] = 0
        self.current_bucket_start[key] = new_bucket_start


class ThresholdAlert:
    """Alert based on threshold conditions."""

    def __init__(
        self,
        name: str,
        component: str,
        metric_name: str,
        warning_threshold: float,
        critical_threshold: float,
        comparison: str = "greater_than",
        duration_seconds: int = 60,
    ):
        self.name = name
        self.component = component
        self.metric_name = metric_name
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.comparison = comparison  # "greater_than", "less_than", "equals"
        self.duration_seconds = duration_seconds

        # State tracking
        self.breach_start_time: float | None = None
        self.current_level: AlertLevel | None = None
        self.consecutive_breaches = 0

    def check_threshold(self, current_value: float) -> Alert | None:
        """Check if current value breaches thresholds and return alert if needed."""
        current_time = time.time()

        # Determine if threshold is breached
        is_critical = self._is_threshold_breached(
            current_value, self.critical_threshold
        )
        is_warning = self._is_threshold_breached(current_value, self.warning_threshold)

        breach_level = None
        if is_critical:
            breach_level = AlertLevel.CRITICAL
        elif is_warning:
            breach_level = AlertLevel.WARNING

        # Handle breach logic
        if breach_level:
            if self.breach_start_time is None:
                self.breach_start_time = current_time
                self.consecutive_breaches = 1
            else:
                self.consecutive_breaches += 1

            # Check if breach duration threshold is met
            breach_duration = current_time - self.breach_start_time
            if breach_duration >= self.duration_seconds:
                # Generate alert if level changed or first time
                if self.current_level != breach_level:
                    self.current_level = breach_level

                    alert_id = f"{self.component}_{self.name}_{breach_level.value}"

                    return Alert(
                        id=alert_id,
                        level=breach_level,
                        component=self.component,
                        title=f"{self.metric_name} {breach_level.value.upper()}",
                        message=f"{self.metric_name} is {current_value} ({self.comparison} {self.warning_threshold if breach_level == AlertLevel.WARNING else self.critical_threshold})",
                        tags={
                            "metric": self.metric_name,
                            "threshold_type": self.comparison,
                            "duration_seconds": str(self.duration_seconds),
                        },
                        metadata={
                            "current_value": current_value,
                            "warning_threshold": self.warning_threshold,
                            "critical_threshold": self.critical_threshold,
                            "breach_duration": breach_duration,
                            "consecutive_breaches": self.consecutive_breaches,
                        },
                    )
        else:
            # Reset breach tracking
            self.breach_start_time = None
            self.current_level = None
            self.consecutive_breaches = 0

        return None

    def _is_threshold_breached(self, value: float, threshold: float) -> bool:
        """Check if value breaches the threshold based on comparison type."""
        if self.comparison == "greater_than":
            return value > threshold
        elif self.comparison == "less_than":
            return value < threshold
        elif self.comparison == "equals":
            return abs(value - threshold) < 0.001  # Float comparison tolerance
        else:
            return False


class ErrorRateAlert:
    """Specialized alert for error rate thresholds."""

    def __init__(
        self,
        name: str,
        component: str,
        operation: str,
        warning_rate: float,
        critical_rate: float,
        min_events: int = 10,
        duration_minutes: int = 2,
    ):
        self.name = name
        self.component = component
        self.operation = operation
        self.warning_rate = warning_rate
        self.critical_rate = critical_rate
        self.min_events = min_events
        self.duration_minutes = duration_minutes

        # State tracking
        self.breach_start_time: float | None = None
        self.current_level: AlertLevel | None = None

    def check_error_rate(self, error_rate_data: dict[str, Any]) -> Alert | None:
        """Check error rate and generate alert if needed."""
        error_rate = error_rate_data.get("error_rate_percent", 0.0)
        total_events = error_rate_data.get("total_events", 0)

        # Don't alert if insufficient data
        if total_events < self.min_events:
            self._reset_breach_tracking()
            return None

        current_time = time.time()

        # Determine alert level
        alert_level = None
        if error_rate >= self.critical_rate:
            alert_level = AlertLevel.CRITICAL
        elif error_rate >= self.warning_rate:
            alert_level = AlertLevel.WARNING

        # Handle breach logic
        if alert_level:
            if self.breach_start_time is None:
                self.breach_start_time = current_time

            # Check duration threshold
            breach_duration = current_time - self.breach_start_time
            if breach_duration >= (self.duration_minutes * 60):
                # Generate alert if level changed
                if self.current_level != alert_level:
                    self.current_level = alert_level

                    alert_id = f"{self.component}_{self.operation}_error_rate_{alert_level.value}"

                    return Alert(
                        id=alert_id,
                        level=alert_level,
                        component=self.component,
                        title=f"High Error Rate: {self.operation}",
                        message=f"Error rate for {self.operation} is {error_rate:.2f}% (threshold: {self.warning_rate if alert_level == AlertLevel.WARNING else self.critical_rate}%)",
                        tags={"operation": self.operation, "alert_type": "error_rate"},
                        metadata={
                            "error_rate_percent": error_rate,
                            "warning_threshold": self.warning_rate,
                            "critical_threshold": self.critical_rate,
                            "total_events": total_events,
                            "total_errors": error_rate_data.get("total_errors", 0),
                            "trend": error_rate_data.get("trend", "unknown"),
                            "breach_duration_minutes": breach_duration / 60,
                        },
                    )
        else:
            self._reset_breach_tracking()

        return None

    def _reset_breach_tracking(self):
        """Reset breach tracking state."""
        self.breach_start_time = None
        self.current_level = None


class PerformanceAlert:
    """Alert for performance degradation (latency, throughput)."""

    def __init__(
        self,
        name: str,
        component: str,
        metric_type: str,
        warning_threshold: float,
        critical_threshold: float,
        percentile: float = 95.0,
        duration_minutes: int = 3,
    ):
        self.name = name
        self.component = component
        self.metric_type = metric_type  # "latency" or "throughput"
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.percentile = percentile
        self.duration_minutes = duration_minutes

        # State tracking
        self.breach_history: deque = deque(maxlen=20)  # Track recent breaches
        self.current_alert_level: AlertLevel | None = None

    def check_performance(self, performance_data: dict[str, Any]) -> Alert | None:
        """Check performance metrics and generate alert if needed."""
        current_time = time.time()

        # Extract relevant metric based on type
        if self.metric_type == "latency":
            percentiles = performance_data.get("percentiles", {})
            metric_value = percentiles.get(self.percentile, 0.0)
            metric_name = f"P{self.percentile} Latency"
            metric_unit = "ms"
            # For latency, higher is worse
            is_critical = metric_value >= self.critical_threshold
            is_warning = metric_value >= self.warning_threshold
        elif self.metric_type == "throughput":
            metric_value = performance_data.get("current_throughput", 0.0)
            metric_name = "Throughput"
            metric_unit = "events/sec"
            # For throughput, lower is worse
            is_critical = metric_value <= self.critical_threshold
            is_warning = metric_value <= self.warning_threshold
        else:
            return None

        # Record breach status
        alert_level = None
        if is_critical:
            alert_level = AlertLevel.CRITICAL
        elif is_warning:
            alert_level = AlertLevel.WARNING

        self.breach_history.append(
            {"timestamp": current_time, "level": alert_level, "value": metric_value}
        )

        # Check if we have sustained breaches
        recent_breaches = [
            entry
            for entry in self.breach_history
            if current_time - entry["timestamp"] <= (self.duration_minutes * 60)
        ]

        # Determine if we should alert
        if len(recent_breaches) >= 3 and alert_level:  # Need at least 3 data points
            breach_levels = [
                entry["level"] for entry in recent_breaches if entry["level"]
            ]

            if len(breach_levels) >= 2:  # At least 2 breaches in the window
                max_breach_level = max(
                    breach_levels, key=lambda x: x.value if x else ""
                )

                # Generate alert if level escalated or first time
                if self.current_alert_level != max_breach_level:
                    self.current_alert_level = max_breach_level

                    alert_id = f"{self.component}_{self.name}_performance_{max_breach_level.value}"

                    comparison = "above" if self.metric_type == "latency" else "below"
                    threshold = (
                        self.critical_threshold
                        if max_breach_level == AlertLevel.CRITICAL
                        else self.warning_threshold
                    )

                    return Alert(
                        id=alert_id,
                        level=max_breach_level,
                        component=self.component,
                        title=f"Performance Issue: {metric_name}",
                        message=f"{metric_name} is {metric_value:.2f}{metric_unit} ({comparison} {threshold}{metric_unit} threshold)",
                        tags={
                            "metric_type": self.metric_type,
                            "percentile": (
                                str(self.percentile)
                                if self.metric_type == "latency"
                                else None
                            ),
                            "alert_type": "performance",
                        },
                        metadata={
                            "current_value": metric_value,
                            "warning_threshold": self.warning_threshold,
                            "critical_threshold": self.critical_threshold,
                            "breach_count": len(breach_levels),
                            "sustained_minutes": self.duration_minutes,
                            "recent_values": [
                                entry["value"] for entry in recent_breaches[-5:]
                            ],
                        },
                    )
        else:
            # Reset if no recent breaches
            if not alert_level:
                self.current_alert_level = None

        return None


class AlertManager:
    """Central alert management system."""

    def __init__(self):
        self.active_alerts: dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=10000)
        self.alert_handlers: list[Callable[[Alert], None]] = []

        # Alert suppression rules
        self.suppression_rules: list[dict[str, Any]] = []

        # Error rate tracking
        self.error_tracker = ErrorRateTracker()

        # Configured alerts
        self.threshold_alerts: list[ThresholdAlert] = []
        self.error_rate_alerts: list[ErrorRateAlert] = []
        self.performance_alerts: list[PerformanceAlert] = []

        self.lock = threading.RLock()

        logger.info("Alert manager initialized")

        # Initialize default alerts
        self._setup_default_alerts()

    def add_alert_handler(self, handler: Callable[[Alert], None]):
        """Add a handler function for alerts."""
        self.alert_handlers.append(handler)

    def add_threshold_alert(self, alert: ThresholdAlert):
        """Add a threshold-based alert."""
        self.threshold_alerts.append(alert)

    def add_error_rate_alert(self, alert: ErrorRateAlert):
        """Add an error rate alert."""
        self.error_rate_alerts.append(alert)

    def add_performance_alert(self, alert: PerformanceAlert):
        """Add a performance alert."""
        self.performance_alerts.append(alert)

    def record_event(
        self,
        component: str,
        operation: str,
        success: bool,
        duration_ms: float | None = None,
        tags: dict[str, str] | None = None,
    ):
        """Record an event for error rate and performance tracking."""
        # Record for error rate tracking
        self.error_tracker.record_event(component, operation, success, tags)

        # Check error rate alerts
        self._check_error_rate_alerts(component, operation, tags)

    def check_metric_thresholds(self, component: str, metrics: dict[str, float]):
        """Check metric values against configured thresholds."""
        for alert in self.threshold_alerts:
            if alert.component == component and alert.metric_name in metrics:
                metric_value = metrics[alert.metric_name]
                generated_alert = alert.check_threshold(metric_value)
                if generated_alert:
                    self._process_alert(generated_alert)

    def check_performance_metrics(
        self, component: str, performance_data: dict[str, Any]
    ):
        """Check performance metrics against configured alerts."""
        for alert in self.performance_alerts:
            if alert.component == component:
                generated_alert = alert.check_performance(performance_data)
                if generated_alert:
                    self._process_alert(generated_alert)

    def fire_alert(self, alert: Alert):
        """Manually fire an alert."""
        self._process_alert(alert)

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str = "user"):
        """Acknowledge an active alert."""
        with self.lock:
            if alert_id in self.active_alerts:
                self.active_alerts[alert_id].acknowledge(acknowledged_by)
                logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by}")

    def resolve_alert(self, alert_id: str, resolved_by: str = "user"):
        """Resolve an active alert."""
        with self.lock:
            if alert_id in self.active_alerts:
                alert = self.active_alerts[alert_id]
                alert.resolve(resolved_by)

                # Move to history
                self.alert_history.append(alert)
                del self.active_alerts[alert_id]

                logger.info(f"Alert {alert_id} resolved by {resolved_by}")

    def suppress_alert(
        self, alert_id: str, duration_minutes: int = 60, suppressed_by: str = "user"
    ):
        """Suppress an active alert."""
        with self.lock:
            if alert_id in self.active_alerts:
                self.active_alerts[alert_id].suppress(duration_minutes, suppressed_by)
                logger.info(
                    f"Alert {alert_id} suppressed for {duration_minutes} minutes by {suppressed_by}"
                )

    def get_active_alerts(
        self, level: AlertLevel | None = None
    ) -> list[dict[str, Any]]:
        """Get all active alerts, optionally filtered by level."""
        with self.lock:
            alerts = []
            for alert in self.active_alerts.values():
                if not alert.is_suppressed() and (
                    level is None or alert.level == level
                ):
                    alerts.append(alert.to_dict())

            # Sort by severity and timestamp
            severity_order = {
                AlertLevel.CRITICAL: 0,
                AlertLevel.ERROR: 1,
                AlertLevel.WARNING: 2,
                AlertLevel.INFO: 3,
            }
            alerts.sort(
                key=lambda x: (
                    severity_order.get(AlertLevel(x["level"]), 4),
                    -x["timestamp"],
                )
            )

            return alerts

    def get_alert_summary(self) -> dict[str, Any]:
        """Get summary of alert system status."""
        with self.lock:
            active_by_level = defaultdict(int)
            suppressed_count = 0

            for alert in self.active_alerts.values():
                if alert.is_suppressed():
                    suppressed_count += 1
                else:
                    active_by_level[alert.level.value] += 1

            return {
                "timestamp": datetime.now().isoformat(),
                "active_alerts": {
                    "total": len(self.active_alerts),
                    "by_level": dict(active_by_level),
                    "suppressed": suppressed_count,
                },
                "alert_history_size": len(self.alert_history),
                "configured_alerts": {
                    "threshold_alerts": len(self.threshold_alerts),
                    "error_rate_alerts": len(self.error_rate_alerts),
                    "performance_alerts": len(self.performance_alerts),
                },
                "error_tracking": {
                    "tracked_operations": len(self.error_tracker.get_all_error_rates())
                },
            }

    def get_error_rates(self) -> dict[str, Any]:
        """Get current error rates for all tracked operations."""
        return self.error_tracker.get_all_error_rates()

    def _process_alert(self, alert: Alert):
        """Process a new alert through the system."""
        with self.lock:
            # Check if this alert already exists
            if alert.id in self.active_alerts:
                # Update existing alert
                existing_alert = self.active_alerts[alert.id]
                existing_alert.update_occurrence()
                logger.debug(
                    f"Updated existing alert {alert.id} (count: {existing_alert.occurrence_count})"
                )
            else:
                # Add new alert
                self.active_alerts[alert.id] = alert
                logger.info(f"New alert fired: {alert.title} ({alert.level.value})")

                # Call alert handlers
                for handler in self.alert_handlers:
                    try:
                        handler(alert)
                    except Exception as e:
                        logger.error(f"Alert handler failed: {e}")

    def _check_error_rate_alerts(
        self, component: str, operation: str, tags: dict[str, str] | None
    ):
        """Check error rate alerts for a specific operation."""
        for alert in self.error_rate_alerts:
            if alert.component == component and alert.operation == operation:
                error_rate_data = self.error_tracker.get_error_rate(
                    component, operation, tags
                )
                generated_alert = alert.check_error_rate(error_rate_data)
                if generated_alert:
                    self._process_alert(generated_alert)

    def _setup_default_alerts(self):
        """Set up comprehensive default alert rules for critical system conditions."""

        # System Resource Threshold Alerts
        system_alerts = [
            # CPU Usage Alerts
            ThresholdAlert(
                name="cpu_usage_high",
                component="system",
                metric_name="cpu_percent",
                warning_threshold=80.0,
                critical_threshold=95.0,
                comparison="greater_than",
                duration_seconds=300,  # 5 minutes
            ),
            # Memory Usage Alerts
            ThresholdAlert(
                name="memory_usage_high",
                component="system",
                metric_name="memory_percent",
                warning_threshold=85.0,
                critical_threshold=95.0,
                comparison="greater_than",
                duration_seconds=300,
            ),
            # Disk Usage Alerts
            ThresholdAlert(
                name="disk_usage_high",
                component="system",
                metric_name="disk_percent",
                warning_threshold=85.0,
                critical_threshold=95.0,
                comparison="greater_than",
                duration_seconds=600,  # 10 minutes
            ),
            # Response Time Alerts
            ThresholdAlert(
                name="api_response_slow",
                component="api",
                metric_name="avg_response_time",
                warning_threshold=1000.0,  # 1 second
                critical_threshold=5000.0,  # 5 seconds
                comparison="greater_than",
                duration_seconds=180,
            ),
            # Database Connection Alerts
            ThresholdAlert(
                name="db_connections_high",
                component="database",
                metric_name="active_connections",
                warning_threshold=80.0,
                critical_threshold=95.0,
                comparison="greater_than",
                duration_seconds=120,
            ),
        ]

        for alert in system_alerts:
            self.add_threshold_alert(alert)

        # Error Rate Alerts
        error_rate_alerts = [
            # Order Processing Error Rates
            ErrorRateAlert(
                name="order_errors_high",
                component="trading",
                operation="place_order",
                warning_rate=5.0,  # 5% error rate
                critical_rate=15.0,  # 15% error rate
                min_events=10,
                duration_minutes=3,
            ),
            # WebSocket Connection Errors
            ErrorRateAlert(
                name="websocket_errors_high",
                component="websocket",
                operation="message_processing",
                warning_rate=10.0,
                critical_rate=25.0,
                min_events=5,
                duration_minutes=2,
            ),
            # Database Query Errors
            ErrorRateAlert(
                name="database_errors_high",
                component="database",
                operation="query_execution",
                warning_rate=3.0,
                critical_rate=10.0,
                min_events=20,
                duration_minutes=5,
            ),
            # API Request Errors
            ErrorRateAlert(
                name="api_errors_high",
                component="api",
                operation="http_requests",
                warning_rate=5.0,
                critical_rate=20.0,
                min_events=15,
                duration_minutes=3,
            ),
        ]

        for alert in error_rate_alerts:
            self.add_error_rate_alert(alert)

        # Performance Alerts
        performance_alerts = [
            # API Latency Performance
            PerformanceAlert(
                name="api_latency_high",
                component="api",
                metric_type="latency",
                warning_threshold=500.0,  # 500ms
                critical_threshold=2000.0,  # 2 seconds
                percentile=95.0,
                duration_minutes=5,
            ),
            # Database Query Performance
            PerformanceAlert(
                name="db_query_latency_high",
                component="database",
                metric_type="latency",
                warning_threshold=200.0,  # 200ms
                critical_threshold=1000.0,  # 1 second
                percentile=90.0,
                duration_minutes=3,
            ),
            # Trading Throughput Performance
            PerformanceAlert(
                name="trading_throughput_low",
                component="trading",
                metric_type="throughput",
                warning_threshold=10.0,  # 10 ops/sec
                critical_threshold=5.0,  # 5 ops/sec
                duration_minutes=5,
            ),
            # WebSocket Message Processing Performance
            PerformanceAlert(
                name="websocket_processing_slow",
                component="websocket",
                metric_type="latency",
                warning_threshold=100.0,  # 100ms
                critical_threshold=500.0,  # 500ms
                percentile=95.0,
                duration_minutes=3,
            ),
        ]

        for alert in performance_alerts:
            self.add_performance_alert(alert)

        # Log setup completion
        total_alerts = (
            len(system_alerts) + len(error_rate_alerts) + len(performance_alerts)
        )
        logger.info(f"Set up {total_alerts} default alert rules:")
        logger.info(f"  - {len(system_alerts)} system threshold alerts")
        logger.info(f"  - {len(error_rate_alerts)} error rate alerts")
        logger.info(f"  - {len(performance_alerts)} performance alerts")

    def create_custom_alert_rule(
        self, rule_type: str, name: str, component: str, **kwargs
    ) -> bool:
        """
        Create a custom alert rule dynamically.

        Args:
            rule_type: "threshold", "error_rate", or "performance"
            name: Unique name for the alert
            component: Component to monitor
            **kwargs: Additional parameters specific to alert type

        Returns:
            True if alert was created successfully
        """
        try:
            if rule_type == "threshold":
                alert = ThresholdAlert(
                    name=name,
                    component=component,
                    metric_name=kwargs.get("metric_name", ""),
                    warning_threshold=kwargs.get("warning_threshold", 0),
                    critical_threshold=kwargs.get("critical_threshold", 0),
                    comparison=kwargs.get("comparison", "greater_than"),
                    duration_seconds=kwargs.get("duration_seconds", 300),
                )
                self.add_threshold_alert(alert)

            elif rule_type == "error_rate":
                alert = ErrorRateAlert(
                    name=name,
                    component=component,
                    operation=kwargs.get("operation", ""),
                    warning_rate=kwargs.get("warning_rate", 5.0),
                    critical_rate=kwargs.get("critical_rate", 15.0),
                    min_events=kwargs.get("min_events", 10),
                    duration_minutes=kwargs.get("duration_minutes", 3),
                )
                self.add_error_rate_alert(alert)

            elif rule_type == "performance":
                alert = PerformanceAlert(
                    name=name,
                    component=component,
                    metric_type=kwargs.get("metric_type", "latency"),
                    warning_threshold=kwargs.get("warning_threshold", 500),
                    critical_threshold=kwargs.get("critical_threshold", 2000),
                    percentile=kwargs.get("percentile", 95.0),
                    duration_minutes=kwargs.get("duration_minutes", 3),
                )
                self.add_performance_alert(alert)

            else:
                logger.error(f"Unknown alert rule type: {rule_type}")
                return False

            logger.info(f"Created custom {rule_type} alert: {name} for {component}")
            return True

        except Exception as e:
            logger.error(f"Failed to create custom alert {name}: {e}")
            return False

    def get_alert_configuration_summary(self) -> dict[str, Any]:
        """Get summary of all configured alert rules."""
        with self.lock:
            return {
                "timestamp": datetime.now().isoformat(),
                "alert_rules": {
                    "threshold_alerts": [
                        {
                            "name": alert.name,
                            "component": alert.component,
                            "metric": alert.metric_name,
                            "warning_threshold": alert.warning_threshold,
                            "critical_threshold": alert.critical_threshold,
                            "duration_seconds": alert.duration_seconds,
                        }
                        for alert in self.threshold_alerts
                    ],
                    "error_rate_alerts": [
                        {
                            "name": alert.name,
                            "component": alert.component,
                            "operation": alert.operation,
                            "warning_rate": alert.warning_rate,
                            "critical_rate": alert.critical_rate,
                            "duration_minutes": alert.duration_minutes,
                        }
                        for alert in self.error_rate_alerts
                    ],
                    "performance_alerts": [
                        {
                            "name": alert.name,
                            "component": alert.component,
                            "metric_type": alert.metric_type,
                            "warning_threshold": alert.warning_threshold,
                            "critical_threshold": alert.critical_threshold,
                            "duration_minutes": alert.duration_minutes,
                        }
                        for alert in self.performance_alerts
                    ],
                },
                "totals": {
                    "threshold_alerts": len(self.threshold_alerts),
                    "error_rate_alerts": len(self.error_rate_alerts),
                    "performance_alerts": len(self.performance_alerts),
                    "total_rules": len(self.threshold_alerts)
                    + len(self.error_rate_alerts)
                    + len(self.performance_alerts),
                },
                "handlers": len(self.alert_handlers),
            }
