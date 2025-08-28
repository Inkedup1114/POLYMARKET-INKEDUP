"""
Comprehensive monitoring and metrics collection for retry logic and circuit breakers.

This module provides detailed insights into retry behavior, circuit breaker states,
and system resilience patterns to help optimize configuration and identify issues.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class RetryAttempt:
    """Information about a single retry attempt."""

    operation_name: str
    attempt_number: int
    timestamp: datetime
    duration: float
    success: bool
    error_type: str | None = None
    error_message: str | None = None
    backoff_delay: float | None = None


@dataclass
class OperationMetrics:
    """Comprehensive metrics for a specific operation."""

    operation_name: str

    # Success/failure counters
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    retried_calls: int = 0

    # Timing metrics
    total_duration: float = 0.0
    min_duration: float = float("inf")
    max_duration: float = 0.0

    # Retry-specific metrics
    total_retry_attempts: int = 0
    max_retries_used: int = 0
    retry_success_rate: float = 0.0

    # Circuit breaker metrics
    circuit_breaker_trips: int = 0
    time_in_open_state: float = 0.0
    time_in_half_open_state: float = 0.0

    # Error categorization
    error_types: dict[str, int] = field(default_factory=dict)

    # Recent history (last 100 operations)
    recent_attempts: deque[RetryAttempt] = field(
        default_factory=lambda: deque(maxlen=100)
    )

    def update_call(
        self,
        duration: float,
        success: bool,
        retry_count: int = 0,
        error_type: str | None = None,
    ) -> None:
        """Update metrics with a completed call."""
        self.total_calls += 1
        self.total_duration += duration

        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
            if error_type:
                self.error_types[error_type] = self.error_types.get(error_type, 0) + 1

        if retry_count > 0:
            self.retried_calls += 1
            self.total_retry_attempts += retry_count
            self.max_retries_used = max(self.max_retries_used, retry_count)

        # Update timing
        self.min_duration = min(self.min_duration, duration)
        self.max_duration = max(self.max_duration, duration)

        # Calculate retry success rate
        if self.retried_calls > 0:
            self.retry_success_rate = (
                sum(
                    1
                    for attempt in self.recent_attempts
                    if attempt.attempt_number > 1 and attempt.success
                )
                / self.total_retry_attempts
            )

    @property
    def success_rate(self) -> float:
        """Calculate overall success rate."""
        return self.successful_calls / max(self.total_calls, 1)

    @property
    def avg_duration(self) -> float:
        """Calculate average operation duration."""
        return self.total_duration / max(self.total_calls, 1)

    @property
    def retry_rate(self) -> float:
        """Calculate percentage of operations that required retries."""
        return self.retried_calls / max(self.total_calls, 1)


class RetryMonitor:
    """
    Comprehensive monitoring system for retry operations and circuit breakers.

    This class collects, aggregates, and provides insights into retry behavior
    across all operations in the system.
    """

    def __init__(self, max_history: int = 10000):
        self.max_history = max_history

        # Operation-specific metrics
        self.operation_metrics: dict[str, OperationMetrics] = {}

        # Global metrics
        self.global_start_time = time.time()
        self.retry_attempts: deque[RetryAttempt] = deque(maxlen=max_history)

        # Circuit breaker state tracking
        self.circuit_breaker_states: dict[str, dict[str, Any]] = {}
        self.circuit_breaker_history: deque[dict[str, Any]] = deque(maxlen=1000)

        log.info("Retry monitor initialized")

    def record_retry_attempt(
        self,
        operation_name: str,
        attempt_number: int,
        duration: float,
        success: bool,
        error_type: str | None = None,
        error_message: str | None = None,
        backoff_delay: float | None = None,
    ) -> None:
        """Record a retry attempt for monitoring and analysis."""

        attempt = RetryAttempt(
            operation_name=operation_name,
            attempt_number=attempt_number,
            timestamp=datetime.utcnow(),
            duration=duration,
            success=success,
            error_type=error_type,
            error_message=error_message,
            backoff_delay=backoff_delay,
        )

        self.retry_attempts.append(attempt)

        # Update operation metrics
        if operation_name not in self.operation_metrics:
            self.operation_metrics[operation_name] = OperationMetrics(
                operation_name=operation_name
            )
        metrics = self.operation_metrics[operation_name]

        metrics.recent_attempts.append(attempt)

        # If this is the final attempt (success or final failure)
        if success or attempt_number > 1:
            retry_count = attempt_number - 1 if attempt_number > 1 else 0
            metrics.update_call(duration, success, retry_count, error_type)

        log.debug(
            f"Recorded retry attempt: {operation_name} attempt {attempt_number}, "
            f"success={success}, duration={duration:.3f}s"
        )

    def record_circuit_breaker_state(
        self, circuit_name: str, state: str, metrics: dict[str, Any]
    ) -> None:
        """Record circuit breaker state change."""

        timestamp = datetime.utcnow()

        # Track state transitions
        if circuit_name in self.circuit_breaker_states:
            previous_state = self.circuit_breaker_states[circuit_name].get("state")
            if previous_state != state:
                self.circuit_breaker_history.append(
                    {
                        "circuit_name": circuit_name,
                        "previous_state": previous_state,
                        "new_state": state,
                        "timestamp": timestamp,
                        "metrics": metrics,
                    }
                )

                log.info(
                    f"Circuit breaker {circuit_name} state changed: "
                    f"{previous_state} -> {state}"
                )

        # Update current state
        self.circuit_breaker_states[circuit_name] = {
            "state": state,
            "timestamp": timestamp,
            "metrics": metrics,
        }

        # Update operation metrics for circuit breaker trips
        if state == "open":
            operation_name = circuit_name.replace("_circuit_breaker", "")
            if operation_name in self.operation_metrics:
                self.operation_metrics[operation_name].circuit_breaker_trips += 1

    def get_operation_summary(self, operation_name: str) -> dict[str, Any]:
        """Get comprehensive summary for a specific operation."""

        if operation_name not in self.operation_metrics:
            return {"error": f"No metrics found for operation: {operation_name}"}

        metrics = self.operation_metrics[operation_name]

        # Calculate recent metrics (last 50 attempts)
        recent_attempts = list(metrics.recent_attempts)[-50:]
        recent_success_rate = sum(
            1 for attempt in recent_attempts if attempt.success
        ) / max(len(recent_attempts), 1)

        # Calculate average backoff delays
        backoff_delays = [
            attempt.backoff_delay
            for attempt in recent_attempts
            if attempt.backoff_delay is not None
        ]
        avg_backoff = sum(backoff_delays) / max(len(backoff_delays), 1)

        return {
            "operation_name": operation_name,
            "total_calls": metrics.total_calls,
            "success_rate": metrics.success_rate,
            "recent_success_rate": recent_success_rate,
            "retry_rate": metrics.retry_rate,
            "avg_duration": metrics.avg_duration,
            "min_duration": (
                metrics.min_duration if metrics.min_duration != float("inf") else 0.0
            ),
            "max_duration": metrics.max_duration,
            "total_retry_attempts": metrics.total_retry_attempts,
            "max_retries_used": metrics.max_retries_used,
            "retry_success_rate": metrics.retry_success_rate,
            "circuit_breaker_trips": metrics.circuit_breaker_trips,
            "avg_backoff_delay": avg_backoff,
            "error_distribution": dict(metrics.error_types),
            "recent_errors": [
                {
                    "timestamp": attempt.timestamp.isoformat(),
                    "error_type": attempt.error_type,
                }
                for attempt in recent_attempts[-10:]
                if not attempt.success and attempt.error_type
            ],
        }

    def get_global_summary(self) -> dict[str, Any]:
        """Get global retry and circuit breaker summary."""

        total_operations = sum(
            metrics.total_calls for metrics in self.operation_metrics.values()
        )
        total_retries = sum(
            metrics.total_retry_attempts for metrics in self.operation_metrics.values()
        )
        total_cb_trips = sum(
            metrics.circuit_breaker_trips for metrics in self.operation_metrics.values()
        )

        # Calculate global success rate
        successful_ops = sum(
            metrics.successful_calls for metrics in self.operation_metrics.values()
        )
        global_success_rate = successful_ops / max(total_operations, 1)

        # Recent activity (last hour)
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_attempts = [
            attempt
            for attempt in self.retry_attempts
            if attempt.timestamp > one_hour_ago
        ]

        return {
            "monitoring_duration": time.time() - self.global_start_time,
            "tracked_operations": len(self.operation_metrics),
            "total_operations": total_operations,
            "total_retry_attempts": total_retries,
            "global_success_rate": global_success_rate,
            "total_circuit_breaker_trips": total_cb_trips,
            "active_circuit_breakers": len(self.circuit_breaker_states),
            "recent_activity": {
                "last_hour_attempts": len(recent_attempts),
                "last_hour_failures": sum(1 for a in recent_attempts if not a.success),
                "last_hour_success_rate": (
                    sum(1 for a in recent_attempts if a.success)
                    / max(len(recent_attempts), 1)
                ),
            },
            "circuit_breaker_states": {
                name: data["state"]
                for name, data in self.circuit_breaker_states.items()
            },
        }

    def get_health_assessment(self) -> dict[str, Any]:
        """Assess overall system health based on retry patterns."""

        issues = []
        warnings = []
        recommendations = []

        global_summary = self.get_global_summary()

        # Check global success rate
        if global_summary["global_success_rate"] < 0.8:
            issues.append(
                f"Low global success rate: {global_summary['global_success_rate']:.2%}"
            )
            recommendations.append(
                "Investigate frequent failures and consider adjusting retry parameters"
            )
        elif global_summary["global_success_rate"] < 0.95:
            warnings.append(
                f"Moderate success rate: {global_summary['global_success_rate']:.2%}"
            )

        # Check for problematic operations
        for op_name, metrics in self.operation_metrics.items():
            if metrics.success_rate < 0.7:
                issues.append(
                    f"Operation {op_name} has low success rate: {metrics.success_rate:.2%}"
                )

            if metrics.retry_rate > 0.5:
                warnings.append(
                    f"Operation {op_name} requires retries frequently: {metrics.retry_rate:.2%}"
                )

            if metrics.circuit_breaker_trips > 5:
                issues.append(
                    f"Operation {op_name} has excessive circuit breaker trips: {metrics.circuit_breaker_trips}"
                )

        # Check circuit breaker states
        open_circuits = [
            name
            for name, data in self.circuit_breaker_states.items()
            if data["state"] == "open"
        ]

        if open_circuits:
            issues.append(f"Open circuit breakers: {', '.join(open_circuits)}")
            recommendations.append("Investigate root causes of circuit breaker trips")

        # Determine overall health status
        if issues:
            health_status = "critical" if len(issues) > 3 else "degraded"
        elif warnings:
            health_status = "warning"
        else:
            health_status = "healthy"

        return {
            "health_status": health_status,
            "issues": issues,
            "warnings": warnings,
            "recommendations": recommendations,
            "assessment_time": datetime.utcnow().isoformat(),
        }

    def export_metrics(self) -> dict[str, Any]:
        """Export all metrics for external monitoring systems."""

        return {
            "global_summary": self.get_global_summary(),
            "operation_metrics": {
                name: self.get_operation_summary(name)
                for name in self.operation_metrics.keys()
            },
            "circuit_breaker_history": [
                {
                    "circuit_name": event["circuit_name"],
                    "state_change": f"{event['previous_state']} -> {event['new_state']}",
                    "timestamp": event["timestamp"].isoformat(),
                }
                for event in list(self.circuit_breaker_history)[
                    -20:
                ]  # Last 20 state changes
            ],
            "health_assessment": self.get_health_assessment(),
        }


# Global retry monitor instance
retry_monitor = RetryMonitor()


def get_retry_metrics() -> dict[str, Any]:
    """Get current retry metrics for monitoring dashboards."""
    return retry_monitor.export_metrics()


def get_retry_health_status() -> str:
    """Get current health status for health checks."""
    return retry_monitor.get_health_assessment()["health_status"]
