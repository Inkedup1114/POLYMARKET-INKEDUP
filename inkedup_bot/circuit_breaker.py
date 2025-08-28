"""
Circuit breaker pattern implementation for resilient API operations.

This module provides comprehensive circuit breaker functionality to prevent
cascading failures and provide graceful degradation when APIs are unreliable.
"""

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any

log = logging.getLogger(__name__)


class CircuitState(Enum):
    """States of the circuit breaker."""

    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Circuit is open, requests fail fast
    HALF_OPEN = "half_open"  # Testing recovery, limited requests allowed


class FailureReason(Enum):
    """Reasons for circuit breaker failures."""

    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    RATE_LIMIT = "rate_limit"
    SERVICE_UNAVAILABLE = "service_unavailable"
    CIRCUIT_OPEN = "circuit_open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    # Basic circuit breaker parameters
    failure_threshold: int = 5  # Failures before opening circuit
    recovery_timeout: float = 60.0  # Seconds before attempting recovery
    half_open_max_calls: int = 3  # Max calls in half-open state
    success_threshold: int = 2  # Successes needed to close circuit

    # Sliding window configuration
    sliding_window_size: int = 100  # Number of calls to track
    sliding_window_time_seconds: float = 300.0  # 5 minute window
    failure_rate_threshold: float = 0.5  # 50% failure rate threshold

    # Timeout settings
    call_timeout: float = 30.0  # Individual call timeout

    # Advanced settings
    exponential_backoff_multiplier: float = 1.5  # Backoff multiplier for recovery
    max_recovery_timeout: float = 600.0  # Maximum recovery timeout (10 min)

    def __post_init__(self):
        """Validate configuration parameters."""
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if self.recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be positive")
        if self.half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be at least 1")
        if self.success_threshold < 1:
            raise ValueError("success_threshold must be at least 1")
        if not 0 < self.failure_rate_threshold <= 1:
            raise ValueError("failure_rate_threshold must be between 0 and 1")


@dataclass
class CallResult:
    """Result of a circuit breaker call attempt."""

    success: bool
    timestamp: float
    duration: float
    error: Exception | None = None
    failure_reason: FailureReason | None = None


@dataclass
class CircuitBreakerMetrics:
    """Metrics and statistics for circuit breaker monitoring."""

    name: str
    state: CircuitState
    failure_count: int = 0
    success_count: int = 0
    total_calls: int = 0

    # Timing metrics
    last_failure_time: float | None = None
    state_change_time: float = field(default_factory=time.time)

    # Sliding window metrics
    recent_calls: deque = field(default_factory=deque)

    # Performance metrics
    avg_response_time: float = 0.0
    min_response_time: float = float("inf")
    max_response_time: float = 0.0

    # Recovery attempts
    recovery_attempts: int = 0
    last_recovery_attempt: float | None = None


class CircuitOpenError(Exception):
    """Exception raised when circuit breaker is open."""

    def __init__(self, circuit_name: str, retry_after: float):
        self.circuit_name = circuit_name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit '{circuit_name}' is open. Retry after {retry_after:.1f} seconds"
        )


class CircuitBreaker:
    """
    Circuit breaker implementation with sliding window failure tracking.

    Features:
    - State management (CLOSED, OPEN, HALF_OPEN)
    - Sliding window failure rate calculation
    - Exponential backoff for recovery attempts
    - Comprehensive metrics collection
    - Thread-safe operation
    """

    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()

        # Thread safety
        self._lock = Lock()

        # State management
        self.state = CircuitState.CLOSED
        self.metrics = CircuitBreakerMetrics(name=name, state=self.state)

        # Half-open state tracking
        self._half_open_calls = 0
        self._half_open_successes = 0

        # Recovery backoff
        self._current_recovery_timeout = self.config.recovery_timeout

        log.info(f"Circuit breaker '{name}' initialized with config: {self.config}")

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitOpenError: When circuit is open
            Original exception: When function fails and circuit allows it
        """
        with self._lock:
            # Check if we should allow this call
            if not self._should_allow_call():
                raise CircuitOpenError(self.name, self._time_until_retry())

            # Track the call attempt
            self.metrics.total_calls += 1

            # Execute the call
            start_time = time.time()
            call_result = None

            try:
                # Apply timeout if configured
                if self.config.call_timeout > 0:
                    result = self._execute_with_timeout(func, *args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Record successful call
                duration = time.time() - start_time
                call_result = CallResult(
                    success=True, timestamp=start_time, duration=duration
                )

                self._record_success(call_result)
                return result

            except Exception as e:
                # Record failed call
                duration = time.time() - start_time
                failure_reason = self._classify_failure(e)

                call_result = CallResult(
                    success=False,
                    timestamp=start_time,
                    duration=duration,
                    error=e,
                    failure_reason=failure_reason,
                )

                self._record_failure(call_result)
                raise

    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute an async function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitOpenError: When circuit is open
            Original exception: When function fails and circuit allows it
        """
        with self._lock:
            # Check if we should allow this call
            if not self._should_allow_call():
                raise CircuitOpenError(self.name, self._time_until_retry())

            # Track the call attempt
            self.metrics.total_calls += 1

        # Execute the call (without lock to avoid blocking)
        start_time = time.time()
        call_result = None

        try:
            # Apply timeout if configured
            if self.config.call_timeout > 0:
                result = await asyncio.wait_for(
                    func(*args, **kwargs), timeout=self.config.call_timeout
                )
            else:
                result = await func(*args, **kwargs)

            # Record successful call
            duration = time.time() - start_time
            call_result = CallResult(
                success=True, timestamp=start_time, duration=duration
            )

            with self._lock:
                self._record_success(call_result)

            return result

        except Exception as e:
            # Record failed call
            duration = time.time() - start_time
            failure_reason = self._classify_failure(e)

            call_result = CallResult(
                success=False,
                timestamp=start_time,
                duration=duration,
                error=e,
                failure_reason=failure_reason,
            )

            with self._lock:
                self._record_failure(call_result)

            raise

    def _should_allow_call(self) -> bool:
        """Determine if a call should be allowed based on circuit state."""
        current_time = time.time()

        if self.state == CircuitState.CLOSED:
            return True

        elif self.state == CircuitState.OPEN:
            # Check if enough time has passed to attempt recovery
            if (
                self.metrics.last_failure_time
                and current_time - self.metrics.last_failure_time
                >= self._current_recovery_timeout
            ):
                self._transition_to_half_open()
                return True
            return False

        elif self.state == CircuitState.HALF_OPEN:
            # Allow limited calls in half-open state
            return self._half_open_calls < self.config.half_open_max_calls

        return False

    def _record_success(self, call_result: CallResult):
        """Record a successful call and update circuit state."""
        self.metrics.success_count += 1
        self._update_response_time_metrics(call_result.duration)
        self._add_to_sliding_window(call_result)

        if self.state == CircuitState.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self.config.success_threshold:
                self._transition_to_closed()

        log.debug(f"Circuit '{self.name}' recorded success. State: {self.state.value}")

    def _record_failure(self, call_result: CallResult):
        """Record a failed call and update circuit state."""
        self.metrics.failure_count += 1
        self.metrics.last_failure_time = call_result.timestamp
        self._update_response_time_metrics(call_result.duration)
        self._add_to_sliding_window(call_result)

        if self.state == CircuitState.CLOSED:
            if self._should_open_circuit():
                self._transition_to_open()
        elif self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open state transitions back to open
            self._transition_to_open()

        log.warning(
            f"Circuit '{self.name}' recorded failure: {call_result.failure_reason}. "
            f"State: {self.state.value}, Failures: {self.metrics.failure_count}"
        )

    def _should_open_circuit(self) -> bool:
        """Determine if the circuit should be opened based on failure metrics."""
        # Check simple failure count threshold
        if self.metrics.failure_count >= self.config.failure_threshold:
            return True

        # Check sliding window failure rate
        failure_rate = self._calculate_failure_rate()
        if failure_rate >= self.config.failure_rate_threshold:
            return True

        return False

    def _calculate_failure_rate(self) -> float:
        """Calculate failure rate over the sliding window."""
        current_time = time.time()
        window_start = current_time - self.config.sliding_window_time_seconds

        # Filter calls within the time window
        recent_calls = [
            call for call in self.metrics.recent_calls if call.timestamp >= window_start
        ]

        if not recent_calls:
            return 0.0

        failures = sum(1 for call in recent_calls if not call.success)
        return failures / len(recent_calls)

    def _add_to_sliding_window(self, call_result: CallResult):
        """Add call result to sliding window and maintain size limits."""
        self.metrics.recent_calls.append(call_result)

        # Remove old calls beyond window size
        while len(self.metrics.recent_calls) > self.config.sliding_window_size:
            self.metrics.recent_calls.popleft()

        # Remove calls beyond time window
        current_time = time.time()
        window_start = current_time - self.config.sliding_window_time_seconds

        while (
            self.metrics.recent_calls
            and self.metrics.recent_calls[0].timestamp < window_start
        ):
            self.metrics.recent_calls.popleft()

    def _update_response_time_metrics(self, duration: float):
        """Update response time statistics."""
        self.metrics.min_response_time = min(self.metrics.min_response_time, duration)
        self.metrics.max_response_time = max(self.metrics.max_response_time, duration)

        # Calculate rolling average
        total_calls = self.metrics.total_calls
        if total_calls > 0:
            self.metrics.avg_response_time = (
                self.metrics.avg_response_time * (total_calls - 1) + duration
            ) / total_calls

    def _transition_to_closed(self):
        """Transition circuit breaker to CLOSED state."""
        log.info(f"Circuit '{self.name}' transitioning to CLOSED state")
        self.state = CircuitState.CLOSED
        self.metrics.state = self.state
        self.metrics.state_change_time = time.time()

        # Reset counters for clean state
        self.metrics.failure_count = 0
        self._half_open_calls = 0
        self._half_open_successes = 0
        self._current_recovery_timeout = self.config.recovery_timeout

    def _transition_to_open(self):
        """Transition circuit breaker to OPEN state."""
        log.warning(f"Circuit '{self.name}' transitioning to OPEN state")
        self.state = CircuitState.OPEN
        self.metrics.state = self.state
        self.metrics.state_change_time = time.time()

        # Apply exponential backoff to recovery timeout
        self._current_recovery_timeout = min(
            self._current_recovery_timeout * self.config.exponential_backoff_multiplier,
            self.config.max_recovery_timeout,
        )

        self.metrics.recovery_attempts += 1
        self.metrics.last_recovery_attempt = time.time()

    def _transition_to_half_open(self):
        """Transition circuit breaker to HALF_OPEN state."""
        log.info(
            f"Circuit '{self.name}' transitioning to HALF_OPEN state (recovery attempt)"
        )
        self.state = CircuitState.HALF_OPEN
        self.metrics.state = self.state
        self.metrics.state_change_time = time.time()

        # Reset half-open counters
        self._half_open_calls = 0
        self._half_open_successes = 0

    def _classify_failure(self, exception: Exception) -> FailureReason:
        """Classify an exception to determine failure reason."""
        error_name = exception.__class__.__name__.lower()
        error_message = str(exception).lower()

        # Network and connection errors
        if any(
            keyword in error_name for keyword in ["network", "connection", "socket"]
        ):
            return FailureReason.NETWORK_ERROR
        if any(
            keyword in error_message
            for keyword in ["connection", "network", "unreachable"]
        ):
            return FailureReason.NETWORK_ERROR

        # Timeout errors
        if "timeout" in error_name or "timeout" in error_message:
            return FailureReason.TIMEOUT

        # Rate limiting
        if any(
            keyword in error_message for keyword in ["rate limit", "429", "too many"]
        ):
            return FailureReason.RATE_LIMIT

        # Server errors
        if any(code in error_message for code in ["500", "502", "503", "504"]):
            return FailureReason.SERVER_ERROR
        if "service unavailable" in error_message:
            return FailureReason.SERVICE_UNAVAILABLE

        # Default to network error for unknown failures
        return FailureReason.NETWORK_ERROR

    def _execute_with_timeout(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with timeout (synchronous version)."""
        # For synchronous functions, we can't easily implement timeout
        # without additional complexity. This is a placeholder for future enhancement.
        return func(*args, **kwargs)

    def _time_until_retry(self) -> float:
        """Calculate time until next retry attempt is allowed."""
        if self.state != CircuitState.OPEN or not self.metrics.last_failure_time:
            return 0.0

        current_time = time.time()
        elapsed = current_time - self.metrics.last_failure_time
        return max(0.0, self._current_recovery_timeout - elapsed)

    def get_metrics(self) -> dict[str, Any]:
        """Get comprehensive metrics for monitoring and debugging."""
        failure_rate = self._calculate_failure_rate()
        time_until_retry = self._time_until_retry()

        return {
            "name": self.name,
            "state": self.state.value,
            "total_calls": self.metrics.total_calls,
            "success_count": self.metrics.success_count,
            "failure_count": self.metrics.failure_count,
            "failure_rate": failure_rate,
            "recovery_attempts": self.metrics.recovery_attempts,
            "time_until_retry": time_until_retry,
            "response_time": {
                "avg": self.metrics.avg_response_time,
                "min": (
                    self.metrics.min_response_time
                    if self.metrics.min_response_time != float("inf")
                    else 0
                ),
                "max": self.metrics.max_response_time,
            },
            "sliding_window_size": len(self.metrics.recent_calls),
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "current_recovery_timeout": self._current_recovery_timeout,
            },
        }

    def reset(self):
        """Reset circuit breaker to initial state."""
        with self._lock:
            log.info(f"Resetting circuit breaker '{self.name}'")

            self.state = CircuitState.CLOSED
            self.metrics = CircuitBreakerMetrics(name=self.name, state=self.state)
            self._half_open_calls = 0
            self._half_open_successes = 0
            self._current_recovery_timeout = self.config.recovery_timeout

    def force_open(self):
        """Force circuit breaker to OPEN state (for testing/maintenance)."""
        with self._lock:
            log.warning(f"Forcing circuit breaker '{self.name}' to OPEN state")
            self._transition_to_open()

    def force_close(self):
        """Force circuit breaker to CLOSED state (for testing/maintenance)."""
        with self._lock:
            log.info(f"Forcing circuit breaker '{self.name}' to CLOSED state")
            self._transition_to_closed()


class CircuitBreakerManager:
    """
    Manager for multiple circuit breakers with centralized monitoring.
    """

    def __init__(self):
        self.circuit_breakers: dict[str, CircuitBreaker] = {}
        self._lock = Lock()

    def get_circuit_breaker(
        self, name: str, config: CircuitBreakerConfig = None
    ) -> CircuitBreaker:
        """Get or create a circuit breaker with the given name."""
        with self._lock:
            if name not in self.circuit_breakers:
                self.circuit_breakers[name] = CircuitBreaker(name, config)
                log.info(f"Created new circuit breaker: {name}")

            return self.circuit_breakers[name]

    def get_all_metrics(self) -> dict[str, dict[str, Any]]:
        """Get metrics for all circuit breakers."""
        with self._lock:
            return {
                name: cb.get_metrics() for name, cb in self.circuit_breakers.items()
            }

    def reset_all(self):
        """Reset all circuit breakers."""
        with self._lock:
            for cb in self.circuit_breakers.values():
                cb.reset()
            log.info("All circuit breakers reset")

    def get_health_summary(self) -> dict[str, Any]:
        """Get overall health summary of all circuit breakers."""
        all_metrics = self.get_all_metrics()

        total_circuits = len(all_metrics)
        open_circuits = sum(
            1 for metrics in all_metrics.values() if metrics["state"] == "open"
        )
        half_open_circuits = sum(
            1 for metrics in all_metrics.values() if metrics["state"] == "half_open"
        )

        total_calls = sum(metrics["total_calls"] for metrics in all_metrics.values())
        total_failures = sum(
            metrics["failure_count"] for metrics in all_metrics.values()
        )

        overall_failure_rate = total_failures / total_calls if total_calls > 0 else 0.0

        return {
            "total_circuits": total_circuits,
            "open_circuits": open_circuits,
            "half_open_circuits": half_open_circuits,
            "closed_circuits": total_circuits - open_circuits - half_open_circuits,
            "overall_failure_rate": overall_failure_rate,
            "total_calls": total_calls,
            "total_failures": total_failures,
            "healthy": open_circuits == 0,
        }


# Global circuit breaker manager instance
circuit_breaker_manager = CircuitBreakerManager()
