"""
Retry utilities with exponential backoff for API operations.

This module provides decorators and utilities for handling transient failures
in API communications with configurable retry strategies.
"""

import asyncio
import functools
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)


class RetryableErrorType(Enum):
    """Categories of errors that can be retried."""

    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    CONNECTION = "connection"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_range: float = 0.1
    backoff_strategy: str = "exponential"  # exponential, linear, constant

    def __post_init__(self):
        """Validate configuration parameters."""
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay < 0:
            raise ValueError("base_delay cannot be negative")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be >= base_delay")
        if self.exponential_base < 1:
            raise ValueError("exponential_base must be >= 1")
        if not 0 <= self.jitter_range <= 1:
            raise ValueError("jitter_range must be between 0 and 1")


class RetryableError(Exception):
    """Base class for errors that can be retried."""

    def __init__(
        self,
        message: str,
        error_type: RetryableErrorType,
        original_error: Exception = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.original_error = original_error


class NetworkError(RetryableError):
    """Network-related errors that can be retried."""

    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message, RetryableErrorType.NETWORK, original_error)


class RateLimitError(RetryableError):
    """Rate limiting errors that can be retried."""

    def __init__(
        self,
        message: str,
        retry_after: float | None = None,
        original_error: Exception = None,
    ):
        super().__init__(message, RetryableErrorType.RATE_LIMIT, original_error)
        self.retry_after = retry_after


class ServerError(RetryableError):
    """Server errors that can be retried."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        original_error: Exception = None,
    ):
        super().__init__(message, RetryableErrorType.SERVER_ERROR, original_error)
        self.status_code = status_code


class TimeoutError(RetryableError):
    """Timeout errors that can be retried."""

    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message, RetryableErrorType.TIMEOUT, original_error)


class ConnectionError(RetryableError):
    """Connection errors that can be retried."""

    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message, RetryableErrorType.CONNECTION, original_error)


def classify_error(exception: Exception) -> RetryableError | None:
    """
    Classify an exception to determine if it's retryable.

    Args:
        exception: The exception to classify

    Returns:
        RetryableError instance if retryable, None otherwise
    """
    # Map common exception types to retryable errors
    error_name = exception.__class__.__name__.lower()
    error_message = str(exception).lower()

    # Rate limiting (highest priority - check first)
    if any(
        keyword in error_message
        for keyword in ["rate limit", "429", "too many requests"]
    ):
        return RateLimitError(
            f"Rate limit error: {exception}", original_error=exception
        )

    # Server errors (5xx status codes) - but exclude 504 if it mentions timeout
    if any(
        keyword in error_message
        for keyword in [
            "500",
            "502",
            "503",
            "internal server error",
            "bad gateway",
            "service unavailable",
        ]
    ):
        return ServerError(f"Server error: {exception}", original_error=exception)

    # Specific 504 Gateway Timeout (could be timeout or server error, treat as timeout)
    if "504" in error_message or "gateway timeout" in error_message:
        return TimeoutError(f"Timeout error: {exception}", exception)

    # Timeout errors (specific timeout keywords)
    if any(keyword in error_name for keyword in ["timeout", "readtimeout"]) or any(
        keyword in error_message
        for keyword in ["timeouterror", "readtimeout", "request timed out", "timed out"]
    ):
        return TimeoutError(f"Timeout error: {exception}", exception)

    # Connection-specific errors (more specific than network)
    if (
        any(
            keyword in error_message
            for keyword in ["connectionerror", "connection refused", "connecttimeout"]
        )
        or "connect" in error_message
    ):
        return ConnectionError(f"Connection error: {exception}", exception)

    # Network-related errors (broader category)
    if any(keyword in error_name for keyword in ["network", "dns", "socket"]) or any(
        keyword in error_message
        for keyword in ["network", "dns", "socket", "unreachable"]
    ):
        return NetworkError(f"Network error: {exception}", exception)

    # Generic API errors that might be transient
    if any(keyword in error_name for keyword in ["apierror", "httperror"]):
        # Check if it's a server error vs client error
        if any(code in error_message for code in ["500", "502", "503"]):
            return ServerError(
                f"API server error: {exception}", original_error=exception
            )
        elif "504" in error_message:
            return TimeoutError(
                f"API timeout error: {exception}", original_error=exception
            )
        elif "429" in error_message:
            return RateLimitError(
                f"API rate limit: {exception}", original_error=exception
            )

    return None


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """
    Calculate delay for a retry attempt.

    Args:
        attempt: Current attempt number (starting from 0)
        config: Retry configuration

    Returns:
        Delay in seconds
    """
    if config.backoff_strategy == "constant":
        delay = config.base_delay
    elif config.backoff_strategy == "linear":
        delay = config.base_delay * (attempt + 1)
    else:  # exponential
        delay = config.base_delay * (config.exponential_base**attempt)

    # Apply maximum delay limit
    delay = min(delay, config.max_delay)

    # Add jitter if enabled
    if config.jitter and delay > 0:
        jitter_amount = delay * config.jitter_range
        jitter = random.uniform(-jitter_amount, jitter_amount)
        delay = max(0, delay + jitter)

    return delay


def retry_on_error(
    retryable_errors: tuple[type[Exception], ...] = None,
    config: RetryConfig = None,
    error_classifier: Callable[[Exception], RetryableError | None] = classify_error,
):
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        retryable_errors: Tuple of exception types to retry on
        config: Retry configuration
        error_classifier: Function to classify exceptions as retryable

    Returns:
        Decorated function
    """
    if config is None:
        config = RetryConfig()

    if retryable_errors is None:
        # Default set of retryable exceptions
        retryable_errors = (
            ConnectionError,
            TimeoutError,
            NetworkError,
            RateLimitError,
            ServerError,
            OSError,
        )

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        log.info(
                            f"Function {func.__name__} succeeded after {attempt + 1} attempts"
                        )
                    return result

                except Exception as e:
                    last_exception = e

                    # Check if this is a retryable error
                    retryable_error = error_classifier(e)
                    is_retryable_type = isinstance(e, retryable_errors)

                    if not (retryable_error or is_retryable_type):
                        log.debug(
                            f"Non-retryable error in {func.__name__}: {type(e).__name__}: {e}"
                        )
                        raise

                    # Don't retry on the last attempt
                    if attempt == config.max_attempts - 1:
                        break

                    # Calculate delay for this attempt
                    delay = calculate_delay(attempt, config)

                    # Special handling for rate limit errors
                    if (
                        retryable_error
                        and isinstance(retryable_error, RateLimitError)
                        and retryable_error.retry_after
                    ):
                        delay = max(delay, retryable_error.retry_after)

                    log.warning(
                        f"Retryable error in {func.__name__} (attempt {attempt + 1}/{config.max_attempts}): "
                        f"{type(e).__name__}: {e}. Retrying in {delay:.2f}s"
                    )

                    time.sleep(delay)

            # All retries exhausted
            log.error(
                f"Function {func.__name__} failed after {config.max_attempts} attempts. "
                f"Last error: {type(last_exception).__name__}: {last_exception}"
            )
            raise last_exception

        return wrapper

    return decorator


def retry_async_on_error(
    retryable_errors: tuple[type[Exception], ...] = None,
    config: RetryConfig = None,
    error_classifier: Callable[[Exception], RetryableError | None] = classify_error,
):
    """
    Async decorator for retrying async functions with exponential backoff.

    Args:
        retryable_errors: Tuple of exception types to retry on
        config: Retry configuration
        error_classifier: Function to classify exceptions as retryable

    Returns:
        Decorated async function
    """
    if config is None:
        config = RetryConfig()

    if retryable_errors is None:
        retryable_errors = (
            ConnectionError,
            TimeoutError,
            NetworkError,
            RateLimitError,
            ServerError,
            OSError,
        )

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    result = await func(*args, **kwargs)
                    if attempt > 0:
                        log.info(
                            f"Async function {func.__name__} succeeded after {attempt + 1} attempts"
                        )
                    return result

                except Exception as e:
                    last_exception = e

                    # Check if this is a retryable error
                    retryable_error = error_classifier(e)
                    is_retryable_type = isinstance(e, retryable_errors)

                    if not (retryable_error or is_retryable_type):
                        log.debug(
                            f"Non-retryable error in async {func.__name__}: {type(e).__name__}: {e}"
                        )
                        raise

                    # Don't retry on the last attempt
                    if attempt == config.max_attempts - 1:
                        break

                    # Calculate delay for this attempt
                    delay = calculate_delay(attempt, config)

                    # Special handling for rate limit errors
                    if (
                        retryable_error
                        and isinstance(retryable_error, RateLimitError)
                        and retryable_error.retry_after
                    ):
                        delay = max(delay, retryable_error.retry_after)

                    log.warning(
                        f"Retryable error in async {func.__name__} (attempt {attempt + 1}/{config.max_attempts}): "
                        f"{type(e).__name__}: {e}. Retrying in {delay:.2f}s"
                    )

                    await asyncio.sleep(delay)

            # All retries exhausted
            log.error(
                f"Async function {func.__name__} failed after {config.max_attempts} attempts. "
                f"Last error: {type(last_exception).__name__}: {last_exception}"
            )
            raise last_exception

        return wrapper

    return decorator


class RetryManager:
    """
    Manager class for retry operations with metrics and monitoring.
    """

    def __init__(self, default_config: RetryConfig = None):
        self.default_config = default_config or RetryConfig()
        self.retry_stats = {
            "total_attempts": 0,
            "successful_retries": 0,
            "failed_retries": 0,
            "error_types": {},
        }

    def get_retry_decorator(self, config: RetryConfig = None):
        """Get a retry decorator with the specified or default configuration."""
        retry_config = config or self.default_config

        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return self._execute_with_retry(func, retry_config, args, kwargs)

            return wrapper

        return decorator

    def _execute_with_retry(
        self, func: Callable, config: RetryConfig, args: tuple, kwargs: dict
    ):
        """Execute function with retry logic and collect metrics."""
        last_exception = None

        for attempt in range(config.max_attempts):
            self.retry_stats["total_attempts"] += 1

            try:
                result = func(*args, **kwargs)
                if attempt > 0:
                    self.retry_stats["successful_retries"] += 1
                    log.info(
                        f"Function {func.__name__} succeeded after {attempt + 1} attempts"
                    )
                return result

            except Exception as e:
                last_exception = e
                error_type = type(e).__name__
                self.retry_stats["error_types"][error_type] = (
                    self.retry_stats["error_types"].get(error_type, 0) + 1
                )

                # Check if this is a retryable error
                retryable_error = classify_error(e)
                if not retryable_error:
                    log.debug(
                        f"Non-retryable error in {func.__name__}: {error_type}: {e}"
                    )
                    raise

                # Don't retry on the last attempt
                if attempt == config.max_attempts - 1:
                    break

                # Calculate delay for this attempt
                delay = calculate_delay(attempt, config)

                log.warning(
                    f"Retryable error in {func.__name__} (attempt {attempt + 1}/{config.max_attempts}): "
                    f"{error_type}: {e}. Retrying in {delay:.2f}s"
                )

                time.sleep(delay)

        # All retries exhausted
        self.retry_stats["failed_retries"] += 1
        log.error(
            f"Function {func.__name__} failed after {config.max_attempts} attempts. "
            f"Last error: {type(last_exception).__name__}: {last_exception}"
        )
        raise last_exception

    def get_stats(self) -> dict:
        """Get retry statistics."""
        return self.retry_stats.copy()

    def reset_stats(self):
        """Reset retry statistics."""
        self.retry_stats = {
            "total_attempts": 0,
            "successful_retries": 0,
            "failed_retries": 0,
            "error_types": {},
        }
