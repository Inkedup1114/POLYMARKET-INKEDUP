"""
Tests for order client retry functionality.

Tests the integration of retry mechanisms, circuit breakers, and failure classification
in OrderClient for handling transient API failures during trading operations.
"""

import logging
import time
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from inkedup_bot.circuit_breaker import CircuitState
from inkedup_bot.config import BotConfig
from inkedup_bot.enhanced_stub_client import EnhancedStubClobClient, StubClientConfig
from inkedup_bot.order_client import OrderClient
from inkedup_bot.retry_utils import NetworkError, RateLimitError, ServerError
from inkedup_bot.state import StateManager


@pytest.fixture
def mock_config():
    """Create a mock bot configuration with retry settings."""
    config = MagicMock(spec=BotConfig)
    config.private_key = "test_private_key"
    config.api_base = "https://test-api.polymarket.com"
    # Retry configuration
    config.api_retry_attempts = 3
    config.api_retry_delay_seconds = 1
    config.api_retry_max_delay_seconds = 60.0
    config.api_retry_exponential_base = 2.0
    config.api_retry_jitter_enabled = True
    config.api_retry_jitter_range = 0.1
    config.api_retry_backoff_strategy = "exponential"
    return config


@pytest.fixture
def mock_config_no_retries():
    """Create config with retries disabled."""
    config = MagicMock(spec=BotConfig)
    config.private_key = "test_private_key"
    config.api_base = "https://test-api.polymarket.com"
    config.api_retry_attempts = 1  # No retries
    config.api_retry_delay_seconds = 1
    config.api_retry_max_delay_seconds = 60.0
    config.api_retry_exponential_base = 2.0
    config.api_retry_jitter_enabled = False
    config.api_retry_jitter_range = 0.1
    config.api_retry_backoff_strategy = "constant"
    return config


@pytest.fixture
def mock_state():
    """Create a mock state manager."""
    return MagicMock(spec=StateManager)


@pytest.fixture
def log_capture():
    """Capture log output for testing."""
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)

    # Capture logs from both order_client and retry_utils
    order_logger = logging.getLogger("order_client")
    retry_logger = logging.getLogger("inkedup_bot.retry_utils")

    order_logger.addHandler(handler)
    retry_logger.addHandler(handler)
    order_logger.setLevel(logging.DEBUG)
    retry_logger.setLevel(logging.DEBUG)

    yield log_stream

    order_logger.removeHandler(handler)
    retry_logger.removeHandler(handler)


class TestOrderClientRetryInitialization:
    """Test retry initialization in OrderClient."""

    def test_retry_manager_initialization_with_config(self, mock_config, mock_state):
        """Test that retry manager is initialized with config values."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
        ):

            mock_clob.return_value = MagicMock()
            client = OrderClient(mock_config, mock_state)

            # Check retry manager is initialized
            assert client.retry_manager is not None

            # Check config values are applied
            retry_config = client.retry_manager.default_config
            assert retry_config.max_attempts == 3
            assert retry_config.base_delay == 1.0
            assert retry_config.max_delay == 60.0
            assert retry_config.exponential_base == 2.0
            assert retry_config.jitter is True
            assert retry_config.jitter_range == 0.1
            assert retry_config.backoff_strategy == "exponential"

    def test_retry_stats_methods(self, mock_config, mock_state):
        """Test retry statistics methods."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
        ):

            mock_clob.return_value = MagicMock()
            client = OrderClient(mock_config, mock_state)

            # Test initial stats
            stats = client.get_retry_stats()
            assert stats["total_attempts"] == 0
            assert stats["successful_retries"] == 0
            assert stats["failed_retries"] == 0

            # Test reset (should not error)
            client.reset_retry_stats()


class TestOrderClientCreateOrderRetry:
    """Test retry behavior for create_order API calls."""

    def test_create_order_success_no_retry(self, mock_config, mock_state, log_capture):
        """Test successful order creation without retry."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
            patch("inkedup_bot.order_client.OrderArgs") as mock_order_args,
            patch("inkedup_bot.order_client.asdict") as mock_asdict,
        ):

            mock_order = MagicMock()
            mock_order.id = "test_order_123"
            mock_client = MagicMock()
            mock_client.create_order.return_value = mock_order
            mock_clob.return_value = mock_client
            mock_asdict.return_value = {"id": "test_order_123"}

            client = OrderClient(mock_config, mock_state)
            result = client.place_limit("token_123", "buy", 0.5, 100)

            # Should succeed without retry
            assert result is not None
            assert result["id"] == "test_order_123"

            # Should only call create_order once
            assert mock_client.create_order.call_count == 1

            # Check no retry warnings in logs
            log_output = log_capture.getvalue()
            assert "Retryable error" not in log_output

    def test_create_order_retry_on_server_error(
        self, mock_config, mock_state, log_capture
    ):
        """Test retry behavior on server errors."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
            patch("inkedup_bot.order_client.OrderArgs") as mock_order_args,
            patch("inkedup_bot.order_client.asdict") as mock_asdict,
        ):

            mock_order = MagicMock()
            mock_order.id = "test_order_123"
            mock_client = MagicMock()

            # Fail twice, then succeed
            mock_client.create_order.side_effect = [
                Exception("503 Service Unavailable"),
                Exception("502 Bad Gateway"),
                mock_order,
            ]
            mock_clob.return_value = mock_client
            mock_asdict.return_value = {"id": "test_order_123"}

            client = OrderClient(mock_config, mock_state)
            result = client.place_limit("token_123", "buy", 0.5, 100)

            # Should eventually succeed
            assert result is not None
            assert result["id"] == "test_order_123"

            # Should retry and eventually succeed
            assert mock_client.create_order.call_count == 3

            # Check retry messages in logs
            log_output = log_capture.getvalue()
            assert "Retryable error" in log_output
            assert "attempt 1/3" in log_output
            assert "attempt 2/3" in log_output

    def test_create_order_exhausts_retries(self, mock_config, mock_state, log_capture):
        """Test behavior when all retry attempts are exhausted."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
            patch("inkedup_bot.order_client.OrderArgs") as mock_order_args,
        ):

            mock_client = MagicMock()
            # Always fail with server error
            mock_client.create_order.side_effect = Exception(
                "500 Internal Server Error"
            )
            mock_clob.return_value = mock_client

            client = OrderClient(mock_config, mock_state)
            result = client.place_limit("token_123", "buy", 0.5, 100)

            # Should return None when all retries exhausted
            assert result is None

            # Should try max attempts
            assert mock_client.create_order.call_count == 3

            # Check failure messages in logs (either from retry manager or order client)
            log_output = log_capture.getvalue()
            assert (
                "failed after 3 attempts" in log_output
                or "Unexpected order failure" in log_output
            )

    def test_create_order_no_retry_on_non_retryable_error(
        self, mock_config, mock_state, log_capture
    ):
        """Test no retry on non-retryable errors like validation errors."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
            patch("inkedup_bot.order_client.OrderArgs") as mock_order_args,
        ):

            mock_client = MagicMock()
            # Non-retryable error (client error)
            mock_client.create_order.side_effect = ValueError(
                "Invalid order parameters"
            )
            mock_clob.return_value = mock_client

            client = OrderClient(mock_config, mock_state)
            result = client.place_limit("token_123", "buy", 0.5, 100)

            # Should return None immediately
            assert result is None

            # Should not retry
            assert mock_client.create_order.call_count == 1

            # Check no retry messages
            log_output = log_capture.getvalue()
            assert "Retryable error" not in log_output


class TestOrderClientCancelAllRetry:
    """Test retry behavior for cancel_all API calls."""

    def test_cancel_all_retry_on_network_error(
        self, mock_config, mock_state, log_capture
    ):
        """Test retry behavior on network errors."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
        ):

            mock_client = MagicMock()
            # Network error on first call, success on second
            mock_client.cancel_all.side_effect = [
                OSError("Network unreachable"),
                [{"id": "order1"}, {"id": "order2"}],
            ]
            mock_clob.return_value = mock_client

            client = OrderClient(mock_config, mock_state)
            result = client.cancel_all()

            # Should succeed after retry
            assert len(result) == 2
            assert mock_client.cancel_all.call_count == 2

            # Check retry logs
            log_output = log_capture.getvalue()
            assert "Retryable error" in log_output

    def test_cancel_all_no_retries_when_disabled(
        self, mock_config_no_retries, mock_state
    ):
        """Test no retries when retry attempts is 1."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
        ):

            mock_client = MagicMock()
            mock_client.cancel_all.side_effect = Exception("503 Service Unavailable")
            mock_clob.return_value = mock_client

            client = OrderClient(mock_config_no_retries, mock_state)
            result = client.cancel_all()

            # Should fail immediately
            assert result == []
            assert mock_client.cancel_all.call_count == 1


class TestOrderClientGetPositionsRetry:
    """Test retry behavior for get_positions API calls."""

    def test_get_positions_retry_on_timeout(self, mock_config, mock_state, log_capture):
        """Test retry behavior on timeout errors."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
        ):

            mock_client = MagicMock()
            # Timeout error on first call, success on second
            mock_client.get_positions.side_effect = [
                Exception("ReadTimeout: Connection timed out"),
                [{"token": "123", "size": 10.0}],
            ]
            mock_clob.return_value = mock_client

            client = OrderClient(mock_config, mock_state)
            result = client.get_positions()

            # Should succeed after retry
            assert len(result) == 1
            assert mock_client.get_positions.call_count == 2

            # Check retry logs
            log_output = log_capture.getvalue()
            assert "Retryable error" in log_output


class TestRetryStatistics:
    """Test retry statistics collection."""

    def test_retry_stats_tracking(self, mock_config, mock_state):
        """Test that retry statistics are tracked correctly."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
            patch("inkedup_bot.order_client.OrderArgs") as mock_order_args,
            patch("inkedup_bot.order_client.asdict") as mock_asdict,
        ):

            mock_order = MagicMock()
            mock_order.id = "test_order_123"
            mock_client = MagicMock()

            # First call fails twice then succeeds
            mock_client.create_order.side_effect = [
                Exception("503 Service Unavailable"),
                Exception("502 Bad Gateway"),
                mock_order,
            ]
            mock_clob.return_value = mock_client
            mock_asdict.return_value = {"id": "test_order_123"}

            client = OrderClient(mock_config, mock_state)

            # Initial stats should be zero
            stats = client.get_retry_stats()
            assert stats["total_attempts"] == 0
            assert stats["successful_retries"] == 0

            # Make API call that requires retries
            result = client.place_limit("token_123", "buy", 0.5, 100)
            assert result is not None

            # Check updated stats
            stats = client.get_retry_stats()
            assert stats["total_attempts"] == 3
            assert stats["successful_retries"] == 1
            assert stats["failed_retries"] == 0
            assert "Exception" in stats["error_types"]

    def test_retry_stats_reset(self, mock_config, mock_state):
        """Test retry statistics reset functionality."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
        ):

            mock_client = MagicMock()
            mock_client.cancel_all.side_effect = [
                Exception("503 Service Unavailable"),
                [],
            ]
            mock_clob.return_value = mock_client

            client = OrderClient(mock_config, mock_state)

            # Generate some retry stats
            client.cancel_all()
            stats = client.get_retry_stats()
            assert stats["total_attempts"] > 0

            # Reset stats
            client.reset_retry_stats()
            stats_after = client.get_retry_stats()
            assert stats_after["total_attempts"] == 0
            assert stats_after["successful_retries"] == 0
            assert stats_after["failed_retries"] == 0

    def test_multiple_api_calls_accumulate_stats(self, mock_config, mock_state):
        """Test that stats accumulate across multiple API calls."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
        ):

            mock_client = MagicMock()
            # Both calls fail once then succeed
            mock_client.cancel_all.side_effect = [
                Exception("503 Service Unavailable"),
                [],
            ]
            mock_client.get_positions.side_effect = [Exception("502 Bad Gateway"), []]
            mock_clob.return_value = mock_client

            client = OrderClient(mock_config, mock_state)

            # Make two different API calls
            client.cancel_all()
            client.get_positions()

            stats = client.get_retry_stats()
            assert stats["total_attempts"] == 4  # 2 calls, each with 2 attempts
            assert stats["successful_retries"] == 2  # Both eventually succeeded


class TestRetryConfiguration:
    """Test different retry configurations."""

    def test_linear_backoff_strategy(self, mock_state):
        """Test linear backoff strategy."""
        config = MagicMock(spec=BotConfig)
        config.private_key = "test_key"
        config.api_base = "https://test-api.polymarket.com"
        config.api_retry_attempts = 3
        config.api_retry_delay_seconds = 1
        config.api_retry_max_delay_seconds = 10.0
        config.api_retry_exponential_base = 2.0
        config.api_retry_jitter_enabled = False
        config.api_retry_jitter_range = 0.0
        config.api_retry_backoff_strategy = "linear"

        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
        ):

            mock_client = MagicMock()
            mock_client.get_positions.side_effect = [
                Exception("503 Service Unavailable"),
                Exception("503 Service Unavailable"),
                [],
            ]
            mock_clob.return_value = mock_client

            client = OrderClient(config, mock_state)
            result = client.get_positions()

            assert result == []
            assert mock_client.get_positions.call_count == 3

    def test_constant_backoff_strategy(self, mock_state):
        """Test constant backoff strategy."""
        config = MagicMock(spec=BotConfig)
        config.private_key = "test_key"
        config.api_base = "https://test-api.polymarket.com"
        config.api_retry_attempts = 2
        config.api_retry_delay_seconds = 0.1  # Fast for testing
        config.api_retry_max_delay_seconds = 1.0
        config.api_retry_exponential_base = 2.0
        config.api_retry_jitter_enabled = False
        config.api_retry_jitter_range = 0.0
        config.api_retry_backoff_strategy = "constant"

        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
        ):

            mock_client = MagicMock()
            mock_client.cancel_all.side_effect = [
                Exception("503 Service Unavailable"),
                [],
            ]
            mock_clob.return_value = mock_client

            client = OrderClient(config, mock_state)
            result = client.cancel_all()

            assert result == []
            assert mock_client.cancel_all.call_count == 2


class TestEnhancedRetrySystem:
    """Test enhanced retry system with circuit breakers and failure classification."""

    @pytest.fixture
    def enhanced_stub_client(self):
        """Enhanced stub client for testing."""
        config = StubClientConfig()
        return EnhancedStubClobClient(config)

    @pytest.fixture
    def order_client_with_enhanced_retry(self, mock_config, mock_state):
        """OrderClient with enhanced retry system."""
        # Configure to use enhanced stub client with relaxed validation for testing
        stub_config = StubClientConfig()
        stub_config.strict_parameter_validation = (
            False  # Disable strict validation for tests
        )
        stub_config.enable_order_validation = False  # Disable order validation entirely
        with patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", False):
            return OrderClient(mock_config, mock_state, stub_config=stub_config)

    def test_circuit_breaker_initialization(self, order_client_with_enhanced_retry):
        """Test that circuit breaker is properly initialized."""
        client = order_client_with_enhanced_retry

        # Check that resilient client exists
        assert hasattr(client, "resilient_client")
        assert client.resilient_client is not None

        # Check circuit breaker state
        circuit_metrics = client.resilient_client.circuit_breaker.get_metrics()
        assert circuit_metrics["state"] == CircuitState.CLOSED.value
        assert circuit_metrics["failure_count"] == 0
        assert circuit_metrics["success_count"] == 0

    def test_successful_operation_updates_circuit_breaker(
        self, order_client_with_enhanced_retry
    ):
        """Test that successful operations update circuit breaker metrics."""
        client = order_client_with_enhanced_retry

        # Configure stub for successful operations
        mock_order = MagicMock()
        mock_order.id = "test_order_success"
        client.client.set_create_order_result(mock_order)

        with (
            patch("inkedup_bot.order_client.OrderArgs") as mock_order_args,
            patch("inkedup_bot.order_client.asdict") as mock_asdict,
        ):
            mock_asdict.return_value = {"id": "test_order_success"}

            # Perform successful operation
            result = client.place_limit("token_123", "buy", 0.5, 100)

            assert result is not None
            assert result["id"] == "test_order_success"

        # Check circuit breaker metrics
        circuit_metrics = client.resilient_client.circuit_breaker.get_metrics()
        assert circuit_metrics["success_count"] >= 1
        assert circuit_metrics["state"] == CircuitState.CLOSED.value

    def test_circuit_breaker_opens_on_repeated_failures(
        self, order_client_with_enhanced_retry
    ):
        """Test that circuit breaker opens after repeated failures."""
        client = order_client_with_enhanced_retry

        # Configure circuit breaker with low threshold for testing
        client.resilient_client.circuit_breaker.config.failure_threshold = 2
        client.resilient_client.circuit_breaker.config.recovery_timeout = 0.1

        # Configure stub to always fail with server errors
        def always_fail(order_args):
            raise ServerError("Internal server error", 500)

        client.client.create_order = always_fail

        with patch("inkedup_bot.order_client.OrderArgs") as mock_order_args:
            # First two attempts should trigger circuit breaker opening
            for i in range(3):
                result = client.place_limit("token_123", "buy", 0.5, 100)
                assert result is None  # Should fail

        # Check circuit breaker is now open
        circuit_metrics = client.resilient_client.circuit_breaker.get_metrics()
        assert circuit_metrics["state"] == CircuitState.OPEN.value
        assert circuit_metrics["failure_count"] >= 2

    def test_failure_classification_determines_retry_behavior(
        self, order_client_with_enhanced_retry
    ):
        """Test that failure classification determines retry behavior."""
        client = order_client_with_enhanced_retry

        # Test network error (should be retried)
        network_call_count = 0

        def network_error_then_success(order_args):
            nonlocal network_call_count
            network_call_count += 1
            if network_call_count == 1:
                raise NetworkError("Connection failed")
            return MagicMock(id="network_retry_success")

        client.client.create_order = network_error_then_success

        with (
            patch("inkedup_bot.order_client.OrderArgs") as mock_order_args,
            patch("inkedup_bot.order_client.asdict") as mock_asdict,
        ):
            mock_asdict.return_value = {"id": "network_retry_success"}

            result = client.place_limit("token_123", "buy", 0.5, 100)

            assert result is not None
            assert network_call_count == 2  # Should have retried once

    def test_rate_limit_errors_get_special_backoff(
        self, order_client_with_enhanced_retry
    ):
        """Test that rate limit errors get special backoff treatment."""
        client = order_client_with_enhanced_retry

        rate_limit_call_count = 0

        def rate_limit_then_success(order_args):
            nonlocal rate_limit_call_count
            rate_limit_call_count += 1
            if rate_limit_call_count == 1:
                raise RateLimitError("Rate limit exceeded", retry_after=0.1)
            return MagicMock(id="rate_limit_success")

        client.client.create_order = rate_limit_then_success

        with (
            patch("inkedup_bot.order_client.OrderArgs") as mock_order_args,
            patch("inkedup_bot.order_client.asdict") as mock_asdict,
        ):
            mock_asdict.return_value = {"id": "rate_limit_success"}

            start_time = time.time()
            result = client.place_limit("token_123", "buy", 0.5, 100)
            end_time = time.time()

            assert result is not None
            assert rate_limit_call_count == 2  # Should have retried
            assert end_time - start_time >= 0.1  # Should have waited for rate limit

    def test_enhanced_retry_metrics_collection(self, order_client_with_enhanced_retry):
        """Test that enhanced retry system collects comprehensive metrics."""
        client = order_client_with_enhanced_retry

        # Perform some operations to generate metrics
        mock_order = MagicMock()
        mock_order.id = "metrics_test"
        client.client.set_create_order_result(mock_order)

        with (
            patch("inkedup_bot.order_client.OrderArgs") as mock_order_args,
            patch("inkedup_bot.order_client.asdict") as mock_asdict,
        ):
            mock_asdict.return_value = {"id": "metrics_test"}

            # Successful operation
            result = client.place_limit("token_123", "buy", 0.5, 100)
            assert result is not None

        # Check operation metrics
        operation_stats = client.resilient_client.get_operation_stats()
        assert "create_order" in operation_stats
        assert operation_stats["create_order"]["total_calls"] >= 1
        assert operation_stats["create_order"]["success_count"] >= 1

        # Check circuit breaker metrics
        circuit_metrics = client.resilient_client.circuit_breaker.get_metrics()
        assert circuit_metrics["success_count"] >= 1

        # Check failure classifier stats
        classifier_stats = (
            client.resilient_client.failure_classifier.get_classification_stats()
        )
        assert "total_classifications" in classifier_stats

    def test_circuit_breaker_half_open_recovery(self, order_client_with_enhanced_retry):
        """Test circuit breaker recovery through HALF_OPEN state."""
        client = order_client_with_enhanced_retry

        # Configure fast recovery for testing
        client.resilient_client.circuit_breaker.config.failure_threshold = 2
        client.resilient_client.circuit_breaker.config.recovery_timeout = 0.1

        # Force circuit breaker to open
        def always_fail(order_args):
            raise ServerError("Service down", 503)

        client.client.create_order = always_fail

        with patch("inkedup_bot.order_client.OrderArgs") as mock_order_args:
            # Trigger failures to open circuit breaker
            for i in range(3):
                result = client.place_limit("token_123", "buy", 0.5, 100)
                assert result is None

        # Verify circuit breaker is open
        circuit_metrics = client.resilient_client.circuit_breaker.get_metrics()
        assert circuit_metrics["state"] == CircuitState.OPEN.value

        # Wait for recovery timeout
        time.sleep(0.2)

        # Configure client to succeed
        mock_order = MagicMock()
        mock_order.id = "recovery_success"
        client.client.set_create_order_result(mock_order)

        with (
            patch("inkedup_bot.order_client.OrderArgs") as mock_order_args,
            patch("inkedup_bot.order_client.asdict") as mock_asdict,
        ):
            mock_asdict.return_value = {"id": "recovery_success"}

            # Should transition to HALF_OPEN and then CLOSED
            result = client.place_limit("token_123", "buy", 0.5, 100)
            assert result is not None

        # Verify circuit breaker is closed
        circuit_metrics = client.resilient_client.circuit_breaker.get_metrics()
        assert circuit_metrics["state"] == CircuitState.CLOSED.value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
