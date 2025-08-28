"""
Enhanced retry client that integrates circuit breakers, failure classification,
and comprehensive retry logic for resilient API operations.

This module combines all retry mechanisms into a unified client interface
that provides production-ready resilience patterns.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .circuit_breaker import (
    CircuitBreakerConfig,
    CircuitOpenError,
    circuit_breaker_manager,
)
from .failure_classifier import (
    ErrorContext,
    RetryStrategy,
    error_classifier,
)
from .retry_monitor import retry_monitor
from .retry_monitoring import retry_monitor as enhanced_retry_monitor

log = logging.getLogger(__name__)


@dataclass
class ResilientClientConfig:
    """Configuration for the resilient retry client."""

    # Circuit breaker configuration
    circuit_breaker_enabled: bool = True
    circuit_breaker_config: CircuitBreakerConfig | None = None

    # Retry configuration
    default_max_attempts: int = 3
    default_base_delay: float = 1.0
    default_max_delay: float = 300.0
    exponential_base: float = 2.0
    jitter_enabled: bool = True
    jitter_range: float = 0.1

    # Operation timeouts
    call_timeout: float = 30.0
    total_timeout: float = 300.0  # Maximum time for all retry attempts

    # Advanced settings
    enable_classification_cache: bool = True
    enable_metrics_collection: bool = True

    def __post_init__(self):
        """Initialize default circuit breaker config if not provided."""
        if self.circuit_breaker_enabled and not self.circuit_breaker_config:
            self.circuit_breaker_config = CircuitBreakerConfig(
                call_timeout=self.call_timeout
            )


@dataclass
class OperationMetrics:
    """Metrics for tracking operation performance and reliability."""

    operation_name: str
    total_attempts: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    circuit_breaker_trips: int = 0

    # Timing metrics
    total_duration: float = 0.0
    avg_duration: float = 0.0
    min_duration: float = float("inf")
    max_duration: float = 0.0

    # Error tracking
    error_counts: dict[str, int] = field(default_factory=dict)
    last_error: str | None = None
    last_error_time: datetime | None = None

    def update_success(self, duration: float):
        """Update metrics for successful operation."""
        self.successful_operations += 1
        self.total_attempts += 1
        self._update_timing(duration)

    def update_failure(self, error: str, duration: float):
        """Update metrics for failed operation."""
        self.failed_operations += 1
        self.total_attempts += 1
        self.last_error = error
        self.last_error_time = datetime.utcnow()

        error_type = error.split(":")[0] if ":" in error else error
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

        self._update_timing(duration)

    def update_circuit_breaker_trip(self):
        """Update metrics for circuit breaker trip."""
        self.circuit_breaker_trips += 1

    def _update_timing(self, duration: float):
        """Update timing statistics."""
        self.total_duration += duration
        self.avg_duration = self.total_duration / self.total_attempts
        self.min_duration = min(self.min_duration, duration)
        self.max_duration = max(self.max_duration, duration)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        return self.successful_operations / max(self.total_attempts, 1)

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate."""
        return self.failed_operations / max(self.total_attempts, 1)


class ResilientRetryClient:
    """
    Resilient client that combines circuit breakers, intelligent retry logic,
    and comprehensive error classification for reliable API operations.
    """

    def __init__(self, client_name: str, config: ResilientClientConfig | None = None):
        self.client_name = client_name
        self.config = config or ResilientClientConfig()

        # Initialize circuit breaker
        self.circuit_breaker = None
        if self.config.circuit_breaker_enabled:
            self.circuit_breaker = circuit_breaker_manager.get_circuit_breaker(
                f"{client_name}_circuit_breaker", self.config.circuit_breaker_config
            )

        # Initialize error classifier
        self.error_classifier = error_classifier

        # Metrics tracking
        self.operation_metrics: dict[str, OperationMetrics] = {}

        log.info(
            f"Initialized resilient retry client '{client_name}' with config: {self.config}"
        )

    def call(
        self,
        operation_name: str,
        func: Callable,
        *args,
        max_attempts: int | None = None,
        base_delay: float | None = None,
        max_delay: float | None = None,
        context: dict[str, Any] | None = None,
        **kwargs,
    ) -> Any:
        """
        Execute a function with comprehensive retry and circuit breaker protection.

        Args:
            operation_name: Name of the operation for metrics and logging
            func: Function to execute
            *args: Function arguments
            max_attempts: Override default max retry attempts
            base_delay: Override default base delay
            max_delay: Override default maximum delay
            context: Additional context for error classification
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Original exception after all retries exhausted
            CircuitOpenError: When circuit breaker is open
        """

        # Get or create metrics tracker
        if operation_name not in self.operation_metrics:
            self.operation_metrics[operation_name] = OperationMetrics(operation_name)

        metrics = self.operation_metrics[operation_name]

        # Set retry parameters
        max_attempts = max_attempts or self.config.default_max_attempts
        base_delay = base_delay or self.config.default_base_delay
        max_delay = max_delay or self.config.default_max_delay

        operation_start_time = time.time()
        last_exception = None

        for attempt in range(max_attempts):
            attempt_start_time = time.time()

            try:
                # Check total timeout
                if time.time() - operation_start_time > self.config.total_timeout:
                    raise TimeoutError(
                        f"Total timeout exceeded for operation {operation_name}"
                    )

                # Execute with circuit breaker if enabled
                if self.circuit_breaker:
                    result = self.circuit_breaker.call(func, *args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Record successful operation
                operation_duration = time.time() - operation_start_time
                metrics.update_success(operation_duration)

                # Record monitoring event
                circuit_state = (
                    self.circuit_breaker.get_metrics()["state"]
                    if self.circuit_breaker
                    else "unknown"
                )
                retry_monitor.record_event(
                    operation_name=operation_name,
                    attempt_number=attempt + 1,
                    success=True,
                    error_category="",
                    error_message="",
                    delay=0.0 if attempt == 0 else getattr(self, "_last_delay", 0.0),
                    duration=operation_duration,
                    circuit_breaker_state=circuit_state,
                )

                # Enhanced monitoring
                attempt_duration = time.time() - attempt_start_time
                enhanced_retry_monitor.record_retry_attempt(
                    operation_name=operation_name,
                    attempt_number=attempt + 1,
                    duration=attempt_duration,
                    success=True,
                )

                if attempt > 0:
                    log.info(
                        f"Operation '{operation_name}' succeeded after {attempt + 1} attempts "
                        f"in {operation_duration:.2f}s"
                    )

                return result

            except CircuitOpenError as e:
                # Circuit breaker is open, don't retry
                metrics.update_circuit_breaker_trip()

                # Record monitoring event for circuit breaker opening
                retry_monitor.record_event(
                    operation_name=operation_name,
                    attempt_number=attempt + 1,
                    success=False,
                    error_category="circuit_open",
                    error_message=str(e),
                    delay=0.0,
                    duration=time.time() - operation_start_time,
                    circuit_breaker_state="open",
                )

                log.error(f"Circuit breaker open for operation '{operation_name}': {e}")
                raise

            except Exception as e:
                last_exception = e
                attempt_duration = time.time() - attempt_start_time

                # Classify the error
                error_context = self.error_classifier.classify(
                    e, context=context or {"operation_type": operation_name}
                )

                # Record the failure
                error_description = f"{e.__class__.__name__}: {str(e)}"
                metrics.update_failure(error_description, attempt_duration)

                # Log the error with context
                log.warning(
                    f"Operation '{operation_name}' failed (attempt {attempt + 1}/{max_attempts}): "
                    f"{error_description} - Category: {error_context.error_category.value}, "
                    f"Strategy: {error_context.retry_strategy.value}"
                )

                # Check if we should retry
                if not error_context.is_retryable:
                    log.info(
                        f"Error is not retryable for operation '{operation_name}', giving up"
                    )
                    break

                # Don't retry on the last attempt
                if attempt == max_attempts - 1:
                    break

                # Calculate delay based on error context and configuration
                delay = self._calculate_retry_delay(
                    attempt, error_context, base_delay, max_delay
                )

                # Record monitoring event for retry attempt
                circuit_state = (
                    self.circuit_breaker.get_metrics()["state"]
                    if self.circuit_breaker
                    else "unknown"
                )
                retry_monitor.record_event(
                    operation_name=operation_name,
                    attempt_number=attempt + 1,
                    success=False,
                    error_category=error_context.error_category.value,
                    error_message=error_description,
                    delay=delay,
                    duration=attempt_duration,
                    circuit_breaker_state=circuit_state,
                )

                # Store delay for success event recording
                self._last_delay = delay

                log.info(
                    f"Retrying operation '{operation_name}' in {delay:.2f}s "
                    f"(attempt {attempt + 2}/{max_attempts})"
                )

                time.sleep(delay)

        # All retries exhausted
        operation_duration = time.time() - operation_start_time

        # Record final failure event
        if last_exception:
            error_context = self.error_classifier.classify(
                last_exception, context=context
            )
            circuit_state = (
                self.circuit_breaker.get_metrics()["state"]
                if self.circuit_breaker
                else "unknown"
            )

            retry_monitor.record_event(
                operation_name=operation_name,
                attempt_number=max_attempts,
                success=False,
                error_category=error_context.error_category.value,
                error_message=f"{last_exception.__class__.__name__}: {str(last_exception)}",
                delay=0.0,
                duration=operation_duration,
                circuit_breaker_state=circuit_state,
            )

        log.error(
            f"Operation '{operation_name}' failed after {max_attempts} attempts "
            f"in {operation_duration:.2f}s. Final error: {last_exception}"
        )

        if last_exception:
            raise last_exception

    async def call_async(
        self,
        operation_name: str,
        func: Callable,
        *args,
        max_attempts: int | None = None,
        base_delay: float | None = None,
        max_delay: float | None = None,
        context: dict[str, Any] | None = None,
        **kwargs,
    ) -> Any:
        """
        Execute an async function with comprehensive retry and circuit breaker protection.

        Args:
            operation_name: Name of the operation for metrics and logging
            func: Async function to execute
            *args: Function arguments
            max_attempts: Override default max retry attempts
            base_delay: Override default base delay
            max_delay: Override default maximum delay
            context: Additional context for error classification
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Original exception after all retries exhausted
            CircuitOpenError: When circuit breaker is open
        """

        # Get or create metrics tracker
        if operation_name not in self.operation_metrics:
            self.operation_metrics[operation_name] = OperationMetrics(operation_name)

        metrics = self.operation_metrics[operation_name]

        # Set retry parameters
        max_attempts = max_attempts or self.config.default_max_attempts
        base_delay = base_delay or self.config.default_base_delay
        max_delay = max_delay or self.config.default_max_delay

        operation_start_time = time.time()
        last_exception = None

        for attempt in range(max_attempts):
            attempt_start_time = time.time()

            try:
                # Check total timeout
                if time.time() - operation_start_time > self.config.total_timeout:
                    raise TimeoutError(
                        f"Total timeout exceeded for operation {operation_name}"
                    )

                # Execute with circuit breaker if enabled
                if self.circuit_breaker:
                    result = await self.circuit_breaker.call_async(
                        func, *args, **kwargs
                    )
                else:
                    result = await func(*args, **kwargs)

                # Record successful operation
                operation_duration = time.time() - operation_start_time
                metrics.update_success(operation_duration)

                if attempt > 0:
                    log.info(
                        f"Async operation '{operation_name}' succeeded after {attempt + 1} attempts "
                        f"in {operation_duration:.2f}s"
                    )

                return result

            except CircuitOpenError as e:
                # Circuit breaker is open, don't retry
                metrics.update_circuit_breaker_trip()
                log.error(
                    f"Circuit breaker open for async operation '{operation_name}': {e}"
                )
                raise

            except Exception as e:
                last_exception = e
                attempt_duration = time.time() - attempt_start_time

                # Classify the error
                error_context = self.error_classifier.classify(
                    e, context=context or {"operation_type": operation_name}
                )

                # Record the failure
                error_description = f"{e.__class__.__name__}: {str(e)}"
                metrics.update_failure(error_description, attempt_duration)

                # Log the error with context
                log.warning(
                    f"Async operation '{operation_name}' failed (attempt {attempt + 1}/{max_attempts}): "
                    f"{error_description} - Category: {error_context.error_category.value}, "
                    f"Strategy: {error_context.retry_strategy.value}"
                )

                # Check if we should retry
                if not error_context.is_retryable:
                    log.info(
                        f"Error is not retryable for async operation '{operation_name}', giving up"
                    )
                    break

                # Don't retry on the last attempt
                if attempt == max_attempts - 1:
                    break

                # Calculate delay based on error context and configuration
                delay = self._calculate_retry_delay(
                    attempt, error_context, base_delay, max_delay
                )

                log.info(
                    f"Retrying async operation '{operation_name}' in {delay:.2f}s "
                    f"(attempt {attempt + 2}/{max_attempts})"
                )

                await asyncio.sleep(delay)

        # All retries exhausted
        operation_duration = time.time() - operation_start_time
        log.error(
            f"Async operation '{operation_name}' failed after {max_attempts} attempts "
            f"in {operation_duration:.2f}s. Final error: {last_exception}"
        )

        if last_exception:
            raise last_exception

    def _calculate_retry_delay(
        self,
        attempt: int,
        error_context: ErrorContext,
        base_delay: float,
        max_delay: float,
    ) -> float:
        """Calculate retry delay based on error context and retry strategy."""

        # Use retry-after header if available
        if error_context.retry_after:
            return min(error_context.retry_after, max_delay)

        # Use error-specific retry parameters if available
        effective_base_delay = error_context.base_delay or base_delay
        effective_max_delay = error_context.max_delay or max_delay

        # Calculate delay based on strategy
        if error_context.retry_strategy == RetryStrategy.IMMEDIATE_RETRY:
            return 0.0

        elif error_context.retry_strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = effective_base_delay * (attempt + 1)

        elif error_context.retry_strategy == RetryStrategy.RATE_LIMIT_BACKOFF:
            # More aggressive backoff for rate limiting
            delay = effective_base_delay * (3**attempt)

        else:  # EXPONENTIAL_BACKOFF (default)
            delay = effective_base_delay * (self.config.exponential_base**attempt)

        # Apply maximum delay limit
        delay = min(delay, effective_max_delay)

        # Add jitter if enabled
        if self.config.jitter_enabled and delay > 0:
            import random

            jitter_amount = delay * self.config.jitter_range
            jitter = random.uniform(-jitter_amount, jitter_amount)
            delay = max(0, delay + jitter)

        return delay

    def get_metrics(self) -> dict[str, Any]:
        """Get comprehensive metrics for all operations."""

        circuit_breaker_metrics = {}
        if self.circuit_breaker:
            circuit_breaker_metrics = self.circuit_breaker.get_metrics()

        operation_metrics = {}
        for name, metrics in self.operation_metrics.items():
            operation_metrics[name] = {
                "total_attempts": metrics.total_attempts,
                "successful_operations": metrics.successful_operations,
                "failed_operations": metrics.failed_operations,
                "circuit_breaker_trips": metrics.circuit_breaker_trips,
                "success_rate": metrics.success_rate,
                "failure_rate": metrics.failure_rate,
                "avg_duration": metrics.avg_duration,
                "min_duration": (
                    metrics.min_duration if metrics.min_duration != float("inf") else 0
                ),
                "max_duration": metrics.max_duration,
                "error_counts": metrics.error_counts,
                "last_error": metrics.last_error,
                "last_error_time": (
                    metrics.last_error_time.isoformat()
                    if metrics.last_error_time
                    else None
                ),
            }

        return {
            "client_name": self.client_name,
            "config": {
                "circuit_breaker_enabled": self.config.circuit_breaker_enabled,
                "default_max_attempts": self.config.default_max_attempts,
                "default_base_delay": self.config.default_base_delay,
                "jitter_enabled": self.config.jitter_enabled,
            },
            "circuit_breaker": circuit_breaker_metrics,
            "operations": operation_metrics,
            "classification_stats": self.error_classifier.get_classification_stats(),
        }

    def get_health_status(self) -> dict[str, Any]:
        """Get overall health status of the client."""

        # Calculate overall statistics
        total_operations = sum(
            m.total_attempts for m in self.operation_metrics.values()
        )
        total_successes = sum(
            m.successful_operations for m in self.operation_metrics.values()
        )
        total_failures = sum(
            m.failed_operations for m in self.operation_metrics.values()
        )
        total_circuit_trips = sum(
            m.circuit_breaker_trips for m in self.operation_metrics.values()
        )

        overall_success_rate = total_successes / max(total_operations, 1)

        # Determine health status
        circuit_healthy = True
        if self.circuit_breaker:
            cb_metrics = self.circuit_breaker.get_metrics()
            circuit_healthy = cb_metrics["state"] == "closed"

        # Consider healthy if success rate > 90% and circuit breaker is closed
        is_healthy = overall_success_rate > 0.9 and circuit_healthy

        return {
            "healthy": is_healthy,
            "total_operations": total_operations,
            "success_rate": overall_success_rate,
            "circuit_breaker_healthy": circuit_healthy,
            "circuit_breaker_trips": total_circuit_trips,
            "active_operations": len(self.operation_metrics),
        }

    def reset_metrics(self):
        """Reset all metrics and circuit breaker state."""
        self.operation_metrics.clear()

        if self.circuit_breaker:
            self.circuit_breaker.reset()

        if self.config.enable_classification_cache:
            self.error_classifier.clear_cache()

        log.info(f"Reset all metrics for resilient client '{self.client_name}'")

    def force_circuit_breaker_open(self):
        """Force circuit breaker to open state (for testing/maintenance)."""
        if self.circuit_breaker:
            self.circuit_breaker.force_open()
            log.warning(
                f"Forced circuit breaker to OPEN for client '{self.client_name}'"
            )
        else:
            log.warning(
                f"Cannot force circuit breaker - not enabled for client '{self.client_name}'"
            )

    def force_circuit_breaker_close(self):
        """Force circuit breaker to closed state (for testing/maintenance)."""
        if self.circuit_breaker:
            self.circuit_breaker.force_close()
            log.info(
                f"Forced circuit breaker to CLOSED for client '{self.client_name}'"
            )
        else:
            log.warning(
                f"Cannot force circuit breaker - not enabled for client '{self.client_name}'"
            )

    # Monitoring and observability methods

    def get_monitoring_metrics(self) -> dict[str, Any]:
        """Get comprehensive monitoring metrics from the retry monitor."""
        return retry_monitor.get_all_metrics()

    def get_monitoring_alerts(
        self, unresolved_only: bool = True
    ) -> list[dict[str, Any]]:
        """Get monitoring alerts."""
        if unresolved_only:
            alerts = retry_monitor.get_unresolved_alerts()
        else:
            alerts = retry_monitor.get_recent_alerts(60)  # Last hour

        return [alert.to_dict() for alert in alerts]

    def get_health_summary(self) -> dict[str, Any]:
        """Get overall health summary including monitoring data."""
        return retry_monitor.get_health_summary()

    def resolve_alerts_for_operations(self, operation_names: list[str] = None):
        """Resolve alerts for specific operations or all operations."""
        if operation_names:
            for operation_name in operation_names:
                retry_monitor.resolve_alerts_for_operation(operation_name)
        else:
            # Resolve alerts for all operations tracked by this client
            for operation_name in self.operation_metrics.keys():
                retry_monitor.resolve_alerts_for_operation(operation_name)

    def get_operation_health(self, operation_name: str) -> dict[str, Any]:
        """Get detailed health information for a specific operation."""
        # Get local metrics
        local_metrics = self.operation_metrics.get(operation_name)

        # Get monitoring metrics
        monitoring_metrics = retry_monitor.get_operation_metrics(operation_name)

        # Get recent alerts for this operation
        recent_alerts = [
            alert.to_dict()
            for alert in retry_monitor.get_recent_alerts(60)
            if alert.operation_name == operation_name
        ]

        unresolved_alerts = [alert for alert in recent_alerts if not alert["resolved"]]

        health_status = "healthy"
        if unresolved_alerts:
            critical_alerts = [
                a for a in unresolved_alerts if a["severity"] == "critical"
            ]
            if critical_alerts:
                health_status = "critical"
            elif len(unresolved_alerts) > 3:
                health_status = "degraded"
            else:
                health_status = "warning"

        result = {
            "operation_name": operation_name,
            "health_status": health_status,
            "unresolved_alerts": len(unresolved_alerts),
            "recent_alerts": len(recent_alerts),
        }

        if local_metrics:
            result.update(
                {
                    "local_total_attempts": local_metrics.total_attempts,
                    "local_successful_operations": local_metrics.successful_operations,
                    "local_success_rate": local_metrics.success_rate,
                    "local_circuit_breaker_trips": local_metrics.circuit_breaker_trips,
                }
            )

        if monitoring_metrics:
            result.update(
                {
                    "monitoring_success_rate": monitoring_metrics.success_rate,
                    "monitoring_failure_rate": monitoring_metrics.failure_rate,
                    "monitoring_average_duration": monitoring_metrics.average_duration,
                    "monitoring_average_delay": monitoring_metrics.average_delay,
                    "monitoring_error_counts": monitoring_metrics.error_counts,
                }
            )

        return result
