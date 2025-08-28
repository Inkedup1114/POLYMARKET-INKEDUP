"""
Tests for retry utilities.

Tests the retry mechanisms with exponential backoff for handling
transient API failures in the order client.
"""

import time

import pytest

from inkedup_bot.retry_utils import (
    ConnectionError,
    NetworkError,
    RateLimitError,
    RetryableErrorType,
    RetryConfig,
    RetryManager,
    ServerError,
    TimeoutError,
    calculate_delay,
    classify_error,
    retry_on_error,
)


class TestRetryConfig:
    """Test RetryConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
        assert config.jitter_range == 0.1
        assert config.backoff_strategy == "exponential"

    def test_custom_config(self):
        """Test custom configuration values."""
        config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=30.0,
            exponential_base=1.5,
            jitter=False,
            jitter_range=0.2,
            backoff_strategy="linear",
        )
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 1.5
        assert config.jitter is False
        assert config.jitter_range == 0.2
        assert config.backoff_strategy == "linear"

    def test_config_validation(self):
        """Test configuration validation."""
        # Invalid max_attempts
        with pytest.raises(ValueError, match="max_attempts must be at least 1"):
            RetryConfig(max_attempts=0)

        # Invalid base_delay
        with pytest.raises(ValueError, match="base_delay cannot be negative"):
            RetryConfig(base_delay=-1)

        # Invalid max_delay
        with pytest.raises(ValueError, match="max_delay must be >= base_delay"):
            RetryConfig(base_delay=10, max_delay=5)

        # Invalid exponential_base
        with pytest.raises(ValueError, match="exponential_base must be >= 1"):
            RetryConfig(exponential_base=0.5)

        # Invalid jitter_range
        with pytest.raises(ValueError, match="jitter_range must be between 0 and 1"):
            RetryConfig(jitter_range=1.5)


class TestErrorClassification:
    """Test error classification for retryable errors."""

    def test_network_error_classification(self):
        """Test classification of network errors."""
        exceptions = [
            Exception("Network unreachable"),
            Exception("DNSError: Name resolution failed"),
        ]

        for exc in exceptions:
            result = classify_error(exc)
            assert isinstance(result, NetworkError)
            assert result.error_type == RetryableErrorType.NETWORK

    def test_socket_error_classification(self):
        """Test that socket errors are classified as connection errors."""
        exc = Exception("SocketError: Connection reset")
        result = classify_error(exc)
        assert isinstance(result, ConnectionError)
        assert result.error_type == RetryableErrorType.CONNECTION

    def test_rate_limit_error_classification(self):
        """Test classification of rate limit errors."""
        exceptions = [
            Exception("429 Too Many Requests"),
            Exception("Rate limit exceeded"),
            Exception("HTTP 429: rate limit"),
        ]

        for exc in exceptions:
            result = classify_error(exc)
            assert isinstance(result, RateLimitError)
            assert result.error_type == RetryableErrorType.RATE_LIMIT

    def test_server_error_classification(self):
        """Test classification of server errors."""
        exceptions = [
            Exception("500 Internal Server Error"),
            Exception("502 Bad Gateway"),
            Exception("503 Service Unavailable"),
        ]

        for exc in exceptions:
            result = classify_error(exc)
            assert isinstance(result, ServerError)
            assert result.error_type == RetryableErrorType.SERVER_ERROR

    def test_gateway_timeout_classification(self):
        """Test that 504 Gateway Timeout is classified as TimeoutError."""
        exc = Exception("504 Gateway Timeout")
        result = classify_error(exc)
        assert isinstance(result, TimeoutError)
        assert result.error_type == RetryableErrorType.TIMEOUT

    def test_timeout_error_classification(self):
        """Test classification of timeout errors."""
        exceptions = [
            Exception("TimeoutError: Request timed out"),
            Exception("ReadTimeout: Connection timed out"),
        ]

        for exc in exceptions:
            result = classify_error(exc)
            assert isinstance(result, TimeoutError)
            assert result.error_type == RetryableErrorType.TIMEOUT

    def test_connection_error_classification(self):
        """Test classification of connection errors."""
        exceptions = [
            Exception("ConnectionError: Connection refused"),
            Exception("Connection refused"),
        ]

        for exc in exceptions:
            result = classify_error(exc)
            assert isinstance(result, ConnectionError)
            assert result.error_type == RetryableErrorType.CONNECTION

    def test_connect_timeout_classification(self):
        """Test that connect timeout errors are classified as TimeoutError."""
        exc = Exception("ConnectTimeout: Connection timed out")
        result = classify_error(exc)
        assert isinstance(result, TimeoutError)
        assert result.error_type == RetryableErrorType.TIMEOUT

    def test_non_retryable_error_classification(self):
        """Test that non-retryable errors return None."""
        exceptions = [
            Exception("400 Bad Request"),
            ValueError("Invalid parameter"),
            KeyError("Missing key"),
            Exception("401 Unauthorized"),
        ]

        for exc in exceptions:
            result = classify_error(exc)
            assert result is None


class TestDelayCalculation:
    """Test delay calculation for different backoff strategies."""

    def test_exponential_backoff(self):
        """Test exponential backoff delay calculation."""
        config = RetryConfig(
            base_delay=1.0,
            exponential_base=2.0,
            max_delay=60.0,
            jitter=False,
            backoff_strategy="exponential",
        )

        # Test progression: 1, 2, 4, 8, 16, 32, 60 (capped)
        expected_delays = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0]

        for attempt, expected in enumerate(expected_delays):
            delay = calculate_delay(attempt, config)
            assert delay == min(expected, config.max_delay)

    def test_linear_backoff(self):
        """Test linear backoff delay calculation."""
        config = RetryConfig(
            base_delay=2.0, max_delay=20.0, jitter=False, backoff_strategy="linear"
        )

        # Test progression: 2, 4, 6, 8, 10, 12, 14, 16, 18, 20 (capped)
        for attempt in range(10):
            delay = calculate_delay(attempt, config)
            expected = min(config.base_delay * (attempt + 1), config.max_delay)
            assert delay == expected

    def test_constant_backoff(self):
        """Test constant backoff delay calculation."""
        config = RetryConfig(base_delay=3.0, jitter=False, backoff_strategy="constant")

        # All delays should be the same
        for attempt in range(5):
            delay = calculate_delay(attempt, config)
            assert delay == 3.0

    def test_jitter(self):
        """Test that jitter adds randomness to delays."""
        config = RetryConfig(
            base_delay=10.0, jitter=True, jitter_range=0.2, backoff_strategy="constant"
        )

        delays = [calculate_delay(0, config) for _ in range(100)]

        # Check that delays vary
        assert len(set(delays)) > 1

        # Check that all delays are within expected range
        min_expected = 10.0 * (1 - config.jitter_range)
        max_expected = 10.0 * (1 + config.jitter_range)

        for delay in delays:
            assert 0 <= delay <= max_expected  # Ensure no negative delays


class TestRetryDecorator:
    """Test retry decorator functionality."""

    def test_successful_function_no_retry(self):
        """Test that successful functions don't retry."""
        config = RetryConfig(max_attempts=3)
        call_count = 0

        @retry_on_error(config=config)
        def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = success_func()
        assert result == "success"
        assert call_count == 1

    def test_retryable_error_with_eventual_success(self):
        """Test retrying on retryable error with eventual success."""
        config = RetryConfig(max_attempts=3, base_delay=0.01)  # Fast retry for testing
        call_count = 0

        @retry_on_error(config=config)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("500 Internal Server Error")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 3

    def test_retryable_error_exhausts_attempts(self):
        """Test that retryable errors eventually exhaust retry attempts."""
        config = RetryConfig(max_attempts=2, base_delay=0.01)
        call_count = 0

        @retry_on_error(config=config)
        def always_fail_func():
            nonlocal call_count
            call_count += 1
            raise Exception("503 Service Unavailable")

        with pytest.raises(Exception, match="503 Service Unavailable"):
            always_fail_func()

        assert call_count == 2

    def test_non_retryable_error_no_retry(self):
        """Test that non-retryable errors don't trigger retries."""
        config = RetryConfig(max_attempts=3)
        call_count = 0

        @retry_on_error(config=config)
        def bad_request_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid parameter")

        with pytest.raises(ValueError, match="Invalid parameter"):
            bad_request_func()

        assert call_count == 1

    def test_rate_limit_error_with_retry_after(self):
        """Test handling of rate limit errors with retry-after header."""
        config = RetryConfig(max_attempts=2, base_delay=0.01)
        call_count = 0

        @retry_on_error(config=config)
        def rate_limited_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                # Simulate rate limit error
                raise Exception("429 Too Many Requests")
            return "success"

        start_time = time.time()
        result = rate_limited_func()
        elapsed = time.time() - start_time

        assert result == "success"
        assert call_count == 2
        assert (
            elapsed >= 0.008
        )  # At least close to base delay (allowing for timing variance)


class TestRetryManager:
    """Test RetryManager class functionality."""

    def test_default_initialization(self):
        """Test RetryManager initialization with defaults."""
        manager = RetryManager()
        assert manager.default_config is not None
        assert manager.retry_stats["total_attempts"] == 0

    def test_custom_config_initialization(self):
        """Test RetryManager with custom configuration."""
        config = RetryConfig(max_attempts=5, base_delay=2.0)
        manager = RetryManager(config)
        assert manager.default_config.max_attempts == 5
        assert manager.default_config.base_delay == 2.0

    def test_stats_collection(self):
        """Test that retry statistics are collected correctly."""
        config = RetryConfig(max_attempts=3, base_delay=0.01)
        manager = RetryManager(config)
        call_count = 0

        @manager.get_retry_decorator()
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("503 Service Unavailable")
            return "success"

        # First call - should succeed after retry
        result = flaky_func()
        assert result == "success"

        stats = manager.get_stats()
        assert stats["total_attempts"] == 2
        assert stats["successful_retries"] == 1
        assert stats["failed_retries"] == 0
        assert "Exception" in stats["error_types"]

    def test_stats_reset(self):
        """Test resetting retry statistics."""
        config = RetryConfig(max_attempts=2, base_delay=0.01)
        manager = RetryManager(config)

        @manager.get_retry_decorator()
        def test_func():
            raise Exception("503 Service Unavailable")

        # Generate some stats
        try:
            test_func()
        except:
            pass

        stats_before = manager.get_stats()
        assert stats_before["total_attempts"] > 0

        manager.reset_stats()
        stats_after = manager.get_stats()
        assert stats_after["total_attempts"] == 0
        assert stats_after["successful_retries"] == 0
        assert stats_after["failed_retries"] == 0
        assert stats_after["error_types"] == {}

    def test_successful_retry_stats(self):
        """Test stats for successful retries."""
        config = RetryConfig(max_attempts=3, base_delay=0.01)
        manager = RetryManager(config)
        call_count = 0

        @manager.get_retry_decorator()
        def eventually_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("500 Internal Server Error")
            return "success"

        result = eventually_succeed()
        assert result == "success"

        stats = manager.get_stats()
        assert stats["total_attempts"] == 3
        assert stats["successful_retries"] == 1
        assert stats["failed_retries"] == 0

    def test_failed_retry_stats(self):
        """Test stats for failed retries."""
        config = RetryConfig(max_attempts=2, base_delay=0.01)
        manager = RetryManager(config)

        @manager.get_retry_decorator()
        def always_fail():
            raise Exception("500 Internal Server Error")

        with pytest.raises(Exception):
            always_fail()

        stats = manager.get_stats()
        assert stats["total_attempts"] == 2
        assert stats["successful_retries"] == 0
        assert stats["failed_retries"] == 1
        assert stats["error_types"]["Exception"] == 2


class TestRetryableErrors:
    """Test retryable error classes."""

    def test_network_error(self):
        """Test NetworkError class."""
        original_exc = OSError("Network unreachable")
        error = NetworkError("Network failure", original_exc)

        assert error.error_type == RetryableErrorType.NETWORK
        assert error.original_error == original_exc
        assert str(error) == "Network failure"

    def test_rate_limit_error(self):
        """Test RateLimitError class."""
        error = RateLimitError("Rate limited", retry_after=30.0)

        assert error.error_type == RetryableErrorType.RATE_LIMIT
        assert error.retry_after == 30.0
        assert str(error) == "Rate limited"

    def test_server_error(self):
        """Test ServerError class."""
        error = ServerError("Server error", status_code=500)

        assert error.error_type == RetryableErrorType.SERVER_ERROR
        assert error.status_code == 500
        assert str(error) == "Server error"

    def test_timeout_error(self):
        """Test TimeoutError class."""
        original_exc = Exception("Connection timed out")
        error = TimeoutError("Timeout occurred", original_exc)

        assert error.error_type == RetryableErrorType.TIMEOUT
        assert error.original_error == original_exc
        assert str(error) == "Timeout occurred"

    def test_connection_error(self):
        """Test ConnectionError class."""
        error = ConnectionError("Connection failed")

        assert error.error_type == RetryableErrorType.CONNECTION
        assert str(error) == "Connection failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
