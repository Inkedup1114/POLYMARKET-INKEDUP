"""
Comprehensive failure classification system for retry and circuit breaker decisions.

This module provides sophisticated error classification to determine appropriate
retry strategies, circuit breaker behavior, and failure handling approaches.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from re import Pattern
from typing import Any

log = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Classification of errors for retry and circuit breaker decision making."""

    # Retryable errors
    NETWORK_ERROR = "network_error"  # Connection issues, DNS failures
    RATE_LIMIT = "rate_limit"  # API rate limiting
    SERVICE_UNAVAILABLE = "service_unavailable"  # 503, 504 responses
    TRANSIENT_ERROR = "transient_error"  # Temporary server issues
    TIMEOUT = "timeout"  # Request timeouts

    # Non-retryable errors
    VALIDATION_ERROR = "validation_error"  # Invalid parameters
    AUTHENTICATION_ERROR = "authentication_error"  # Auth failures
    PERMISSION_DENIED = "permission_denied"  # Insufficient permissions
    NOT_FOUND = "not_found"  # Resource not found
    INSUFFICIENT_FUNDS = "insufficient_funds"  # Balance issues
    DUPLICATE_ORDER = "duplicate_order"  # Idempotency violations

    # Circuit breaker errors
    CIRCUIT_OPEN = "circuit_open"  # Circuit breaker is open
    CRITICAL_ERROR = "critical_error"  # System-level failures

    # Unknown/unclassified
    UNKNOWN = "unknown"  # Unclassified errors


class RetryStrategy(Enum):
    """Retry strategies for different error types."""

    IMMEDIATE_RETRY = "immediate_retry"  # Retry immediately
    EXPONENTIAL_BACKOFF = "exponential_backoff"  # Standard exponential backoff
    LINEAR_BACKOFF = "linear_backoff"  # Linear increase in delay
    RATE_LIMIT_BACKOFF = "rate_limit_backoff"  # Respect rate limit headers
    NO_RETRY = "no_retry"  # Don't retry
    CIRCUIT_BREAKER = "circuit_breaker"  # Use circuit breaker logic


@dataclass
class ErrorContext:
    """Context information for error classification and handling decisions."""

    error_category: ErrorCategory
    error_message: str
    retry_strategy: RetryStrategy

    # HTTP-specific information
    http_status: int | None = None
    retry_after: int | None = None  # Seconds from Retry-After header
    rate_limit_reset: datetime | None = None

    # Error details
    error_details: dict[str, Any] | None = None
    original_exception: Exception | None = None

    # Retry control
    max_retry_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 300.0

    # Circuit breaker influence
    contributes_to_circuit_breaker: bool = True
    circuit_breaker_weight: float = 1.0  # How much this error affects circuit breaker

    @property
    def is_retryable(self) -> bool:
        """Determine if this error should trigger a retry."""
        return self.retry_strategy not in {RetryStrategy.NO_RETRY}

    @property
    def should_circuit_break(self) -> bool:
        """Determine if this error should count towards circuit breaker metrics."""
        circuit_break_categories = {
            ErrorCategory.NETWORK_ERROR,
            ErrorCategory.SERVICE_UNAVAILABLE,
            ErrorCategory.TIMEOUT,
            ErrorCategory.CRITICAL_ERROR,
            ErrorCategory.TRANSIENT_ERROR,
        }
        return (
            self.error_category in circuit_break_categories
            and self.contributes_to_circuit_breaker
        )

    @property
    def is_client_error(self) -> bool:
        """Determine if this is a client-side error (4xx-style)."""
        client_error_categories = {
            ErrorCategory.VALIDATION_ERROR,
            ErrorCategory.AUTHENTICATION_ERROR,
            ErrorCategory.PERMISSION_DENIED,
            ErrorCategory.NOT_FOUND,
            ErrorCategory.INSUFFICIENT_FUNDS,
            ErrorCategory.DUPLICATE_ORDER,
        }
        return self.error_category in client_error_categories

    @property
    def is_server_error(self) -> bool:
        """Determine if this is a server-side error (5xx-style)."""
        server_error_categories = {
            ErrorCategory.SERVICE_UNAVAILABLE,
            ErrorCategory.TRANSIENT_ERROR,
            ErrorCategory.CRITICAL_ERROR,
        }
        return self.error_category in server_error_categories


class ErrorPattern:
    """Pattern matching for error classification."""

    def __init__(
        self,
        category: ErrorCategory,
        retry_strategy: RetryStrategy,
        patterns: set[str],
        regex_patterns: set[Pattern] | None = None,
        status_codes: set[int] | None = None,
        exception_types: set[str] | None = None,
    ):
        self.category = category
        self.retry_strategy = retry_strategy
        self.patterns = {p.lower() for p in patterns}
        self.regex_patterns = regex_patterns or set()
        self.status_codes = status_codes or set()
        self.exception_types = {t.lower() for t in (exception_types or set())}


class ErrorClassifier:
    """Service for classifying errors into appropriate categories and strategies."""

    def __init__(self):
        self.error_patterns = self._initialize_error_patterns()
        self.classification_cache: dict[str, ErrorContext] = {}
        self.cache_max_size = 1000

    def _initialize_error_patterns(self) -> list[ErrorPattern]:
        """Initialize comprehensive error classification patterns."""

        patterns = [
            # Network errors
            ErrorPattern(
                category=ErrorCategory.NETWORK_ERROR,
                retry_strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
                patterns={
                    "connection error",
                    "connection refused",
                    "connection reset",
                    "network unreachable",
                    "host unreachable",
                    "dns",
                    "socket",
                    "connection timeout",
                    "connection aborted",
                    "connection failed",
                    "no route to host",
                    "network is down",
                    "connection lost",
                },
                exception_types={
                    "ConnectionError",
                    "NetworkError",
                    "SocketError",
                    "DNSError",
                    "URLError",
                    "HTTPConnectionPool",
                    "ConnectTimeout",
                    "ConnectionTimeout",
                },
            ),
            # Timeout errors
            ErrorPattern(
                category=ErrorCategory.TIMEOUT,
                retry_strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
                patterns={
                    "timeout",
                    "timed out",
                    "read timeout",
                    "connect timeout",
                    "request timeout",
                    "gateway timeout",
                    "deadline exceeded",
                },
                status_codes={408, 504},
                exception_types={
                    "TimeoutError",
                    "ReadTimeout",
                    "ConnectTimeout",
                    "Timeout",
                },
            ),
            # Rate limiting
            ErrorPattern(
                category=ErrorCategory.RATE_LIMIT,
                retry_strategy=RetryStrategy.RATE_LIMIT_BACKOFF,
                patterns={
                    "rate limit",
                    "rate limited",
                    "too many requests",
                    "quota exceeded",
                    "throttled",
                    "requests per second",
                    "requests per minute",
                },
                status_codes={429},
                exception_types={"RateLimitError", "TooManyRequests"},
            ),
            # Service unavailable
            ErrorPattern(
                category=ErrorCategory.SERVICE_UNAVAILABLE,
                retry_strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
                patterns={
                    "service unavailable",
                    "temporarily unavailable",
                    "maintenance mode",
                    "server overloaded",
                    "service temporarily overloaded",
                    "internal server error",
                    "bad gateway",
                    "service down",
                },
                status_codes={500, 502, 503},
                exception_types={
                    "ServiceUnavailable",
                    "InternalServerError",
                    "BadGateway",
                },
            ),
            # Authentication errors (non-retryable)
            ErrorPattern(
                category=ErrorCategory.AUTHENTICATION_ERROR,
                retry_strategy=RetryStrategy.NO_RETRY,
                patterns={
                    "unauthorized",
                    "authentication failed",
                    "invalid credentials",
                    "access denied",
                    "login failed",
                    "authentication required",
                    "invalid token",
                    "expired token",
                    "token not found",
                },
                status_codes={401},
                exception_types={
                    "AuthenticationError",
                    "Unauthorized",
                    "InvalidCredentials",
                },
            ),
            # Permission errors (non-retryable)
            ErrorPattern(
                category=ErrorCategory.PERMISSION_DENIED,
                retry_strategy=RetryStrategy.NO_RETRY,
                patterns={
                    "forbidden",
                    "permission denied",
                    "access denied",
                    "not authorized",
                    "insufficient permissions",
                    "operation not permitted",
                },
                status_codes={403},
                exception_types={"PermissionError", "Forbidden", "AccessDenied"},
            ),
            # Validation errors (non-retryable)
            ErrorPattern(
                category=ErrorCategory.VALIDATION_ERROR,
                retry_strategy=RetryStrategy.NO_RETRY,
                patterns={
                    "invalid",
                    "validation error",
                    "bad request",
                    "malformed",
                    "invalid parameter",
                    "invalid format",
                    "invalid input",
                    "missing parameter",
                    "parameter required",
                    "invalid value",
                },
                status_codes={400, 422},
                exception_types={
                    "ValidationError",
                    "ValueError",
                    "BadRequest",
                    "InvalidInput",
                },
            ),
            # Not found errors (non-retryable)
            ErrorPattern(
                category=ErrorCategory.NOT_FOUND,
                retry_strategy=RetryStrategy.NO_RETRY,
                patterns={
                    "not found",
                    "does not exist",
                    "no such",
                    "unknown",
                    "resource not found",
                    "endpoint not found",
                    "page not found",
                },
                status_codes={404},
                exception_types={"NotFound", "DoesNotExist"},
            ),
            # Insufficient funds (non-retryable)
            ErrorPattern(
                category=ErrorCategory.INSUFFICIENT_FUNDS,
                retry_strategy=RetryStrategy.NO_RETRY,
                patterns={
                    "insufficient funds",
                    "insufficient balance",
                    "not enough balance",
                    "insufficient collateral",
                    "balance too low",
                    "overdraft",
                },
                exception_types={"InsufficientFunds", "InsufficientBalance"},
            ),
            # Duplicate orders (non-retryable)
            ErrorPattern(
                category=ErrorCategory.DUPLICATE_ORDER,
                retry_strategy=RetryStrategy.NO_RETRY,
                patterns={
                    "duplicate order",
                    "order already exists",
                    "already placed",
                    "duplicate request",
                    "idempotency key",
                    "request already processed",
                },
                status_codes={409},
                exception_types={"DuplicateOrder", "AlreadyExists", "Conflict"},
            ),
            # Circuit breaker errors
            ErrorPattern(
                category=ErrorCategory.CIRCUIT_OPEN,
                retry_strategy=RetryStrategy.CIRCUIT_BREAKER,
                patterns={"circuit", "circuit breaker", "circuit open"},
                exception_types={"CircuitOpenError", "CircuitBreakerOpen"},
            ),
        ]

        return patterns

    def classify(
        self,
        exception: Exception,
        response_data: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> ErrorContext:
        """
        Classify an exception into an error context with retry strategy.

        Args:
            exception: The exception to classify
            response_data: Optional HTTP response data
            context: Additional context for classification

        Returns:
            ErrorContext with classification and retry strategy
        """
        # Create cache key
        cache_key = self._create_cache_key(exception, response_data)

        # Check cache first
        if cache_key in self.classification_cache:
            return self.classification_cache[cache_key]

        # Extract basic information
        error_message = str(exception)
        exception_name = exception.__class__.__name__
        http_status = None
        retry_after = None
        error_details = response_data or {}

        # Extract HTTP information from response
        if response_data:
            http_status = response_data.get("status")
            headers = response_data.get("headers", {})
            if "Retry-After" in headers:
                try:
                    retry_after = int(headers["Retry-After"])
                except (ValueError, TypeError):
                    pass

        # Find matching pattern
        error_pattern = self._find_matching_pattern(
            exception_name, error_message, http_status
        )

        # Create error context
        error_context = ErrorContext(
            error_category=error_pattern.category,
            error_message=error_message,
            retry_strategy=error_pattern.retry_strategy,
            http_status=http_status,
            retry_after=retry_after,
            error_details=error_details,
            original_exception=exception,
        )

        # Apply context-specific adjustments
        self._apply_context_adjustments(error_context, context)

        # Cache the result
        self._cache_classification(cache_key, error_context)

        log.debug(
            f"Classified error: {exception_name} -> {error_context.error_category.value} "
            f"(strategy: {error_context.retry_strategy.value})"
        )

        return error_context

    def _find_matching_pattern(
        self, exception_name: str, error_message: str, http_status: int | None
    ) -> ErrorPattern:
        """Find the best matching error pattern for the given error."""

        exception_name_lower = exception_name.lower()
        error_message_lower = error_message.lower()

        # Check each pattern for matches
        for pattern in self.error_patterns:
            match_score = 0

            # Check exception type match
            if (
                pattern.exception_types
                and exception_name_lower in pattern.exception_types
            ):
                match_score += 10

            # Check HTTP status code match
            if pattern.status_codes and http_status in pattern.status_codes:
                match_score += 8

            # Check text pattern matches
            for text_pattern in pattern.patterns:
                if text_pattern in error_message_lower:
                    match_score += 5
                    break

            # Check regex pattern matches
            for regex_pattern in pattern.regex_patterns:
                if regex_pattern.search(error_message_lower):
                    match_score += 5
                    break

            # If we have a strong match, return this pattern
            if match_score >= 8:
                return pattern

        # Default to transient error if no specific pattern matches
        return ErrorPattern(
            category=ErrorCategory.TRANSIENT_ERROR,
            retry_strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            patterns=set(),
        )

    def _apply_context_adjustments(
        self, error_context: ErrorContext, context: dict[str, Any] | None
    ):
        """Apply context-specific adjustments to error classification."""

        if not context:
            return

        # Adjust retry parameters based on context
        if "max_retries" in context:
            error_context.max_retry_attempts = context["max_retries"]

        if "base_delay" in context:
            error_context.base_delay = context["base_delay"]

        if "max_delay" in context:
            error_context.max_delay = context["max_delay"]

        # Adjust circuit breaker behavior
        if "circuit_breaker_weight" in context:
            error_context.circuit_breaker_weight = context["circuit_breaker_weight"]

        # Override category for specific conditions
        operation_type = context.get("operation_type")
        if (
            operation_type == "order_placement"
            and error_context.error_category == ErrorCategory.TRANSIENT_ERROR
        ):
            # Be more conservative with order placement errors
            error_context.max_retry_attempts = min(error_context.max_retry_attempts, 2)
            error_context.circuit_breaker_weight = 2.0

    def _create_cache_key(
        self, exception: Exception, response_data: dict | None
    ) -> str:
        """Create a cache key for error classification."""

        exception_name = exception.__class__.__name__
        error_message = str(exception)
        status_code = response_data.get("status") if response_data else None

        # Create a simple hash-like key
        key_parts = [
            exception_name,
            error_message[:100],  # Truncate long messages
            str(status_code) if status_code else "no_status",
        ]

        return "|".join(key_parts)

    def _cache_classification(self, cache_key: str, error_context: ErrorContext):
        """Cache error classification result with size management."""

        # Remove oldest entries if cache is full
        if len(self.classification_cache) >= self.cache_max_size:
            # Remove first 10% of entries
            keys_to_remove = list(self.classification_cache.keys())[
                : self.cache_max_size // 10
            ]
            for key in keys_to_remove:
                del self.classification_cache[key]

        self.classification_cache[cache_key] = error_context

    def get_classification_stats(self) -> dict[str, Any]:
        """Get statistics about error classifications."""

        if not self.classification_cache:
            return {"total_classifications": 0}

        category_counts = {}
        strategy_counts = {}

        for context in self.classification_cache.values():
            category = context.error_category.value
            strategy = context.retry_strategy.value

            category_counts[category] = category_counts.get(category, 0) + 1
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

        return {
            "total_classifications": len(self.classification_cache),
            "category_distribution": category_counts,
            "strategy_distribution": strategy_counts,
            "cache_hit_potential": len(self.classification_cache)
            / max(len(self.classification_cache), 1),
        }

    def clear_cache(self):
        """Clear the classification cache."""
        self.classification_cache.clear()
        log.info("Error classification cache cleared")


# Global error classifier instance
error_classifier = ErrorClassifier()
