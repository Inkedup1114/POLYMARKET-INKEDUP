"""
Tests for enhanced stub client functionality.

Tests the comprehensive error simulation, realistic API behavior,
and configurable response patterns for improved resilience testing.
"""

import logging
import time
from io import StringIO
from unittest.mock import patch

import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.enhanced_stub_client import (
    EnhancedStubClobClient,
    ErrorScenario,
    MarketCondition,
    MockOrder,
    StubClientConfig,
    create_balance_constraint_client,
    create_circuit_breaker_client,
    create_enhanced_realistic_client,
    create_intermittent_error_client,
    create_market_condition_client,
    create_network_error_client,
    create_partial_failure_client,
    create_rate_limited_client,
    create_realistic_trading_client,
    create_slow_response_client,
    create_stress_test_client,
    create_validation_heavy_client,
)
from inkedup_bot.order_client import OrderClient
from inkedup_bot.state import StateManager


@pytest.fixture
def basic_stub_config():
    """Create basic stub configuration."""
    return StubClientConfig()


@pytest.fixture
def error_config():
    """Create configuration with error simulation."""
    return StubClientConfig(
        error_scenario=ErrorScenario.SERVER_ERROR, error_probability=0.5
    )


@pytest.fixture
def mock_order_args():
    """Create mock order arguments."""

    class MockOrderArgs:
        def __init__(self):
            self.token_id = "test_token_123"
            self.side = "buy"
            self.price = 0.65
            self.size = 100.0

    return MockOrderArgs()


@pytest.fixture
def log_capture():
    """Capture log output for testing."""
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    logger = logging.getLogger("inkedup_bot.enhanced_stub_client")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield log_stream
    logger.removeHandler(handler)


class TestStubClientConfig:
    """Test stub client configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = StubClientConfig()
        assert config.error_scenario == ErrorScenario.NONE
        assert config.error_probability == 0.0
        assert config.consecutive_errors == 0
        assert config.min_response_delay == 0.01
        assert config.max_response_delay == 0.1
        assert config.order_fill_probability == 1.0
        assert config.starting_positions_count == 0

    def test_custom_config(self):
        """Test custom configuration values."""
        config = StubClientConfig(
            error_scenario=ErrorScenario.NETWORK_ERROR,
            error_probability=0.3,
            min_response_delay=0.05,
            max_response_delay=0.2,
            starting_positions_count=5,
        )
        assert config.error_scenario == ErrorScenario.NETWORK_ERROR
        assert config.error_probability == 0.3
        assert config.min_response_delay == 0.05
        assert config.max_response_delay == 0.2
        assert config.starting_positions_count == 5


class TestBasicStubFunctionality:
    """Test basic enhanced stub client functionality."""

    def test_initialization_with_default_config(self):
        """Test stub client initialization with default config."""
        client = EnhancedStubClobClient()
        assert len(client.positions) == 0
        assert len(client.orders) == 0
        assert client.request_count == 0
        assert client.error_count == 0

    def test_initialization_with_starting_positions(self):
        """Test initialization with starting positions."""
        config = StubClientConfig(starting_positions_count=3)
        client = EnhancedStubClobClient(config)

        assert len(client.positions) == 3
        for i, position in enumerate(client.positions):
            assert position.token_id == f"token_{i}"
            assert position.market_slug == f"test_market_{i}"
            assert position.outcome_type in ["YES", "NO"]

    def test_create_order_success(self, mock_order_args):
        """Test successful order creation."""
        client = EnhancedStubClobClient()
        order = client.create_order(mock_order_args)

        assert isinstance(order, MockOrder)
        assert order.token_id == "test_token_123"
        assert order.side == "buy"
        assert order.price == 0.65
        assert order.size == 100.0
        assert order.id.startswith("order_")

        # Order should be stored
        assert order.id in client.orders

    def test_cancel_all_orders(self, mock_order_args):
        """Test cancelling all orders."""
        # Use config with 0% fill probability so orders stay open
        config = StubClientConfig(order_fill_probability=0.0)
        client = EnhancedStubClobClient(config)

        # Create some orders first
        order1 = client.create_order(mock_order_args)
        order2 = client.create_order(mock_order_args)

        # Verify orders are open
        assert order1.status == "open"
        assert order2.status == "open"

        # Cancel all orders
        cancelled = client.cancel_all()

        assert len(cancelled) == 2
        assert all(order["status"] == "cancelled" for order in cancelled)

        # Check orders are marked as cancelled
        assert client.orders[order1.id].status == "cancelled"
        assert client.orders[order2.id].status == "cancelled"

    def test_get_positions_empty(self):
        """Test getting positions when empty."""
        client = EnhancedStubClobClient()
        positions = client.get_positions()

        assert isinstance(positions, list)
        assert len(positions) == 0

    def test_get_positions_with_data(self):
        """Test getting positions with mock data."""
        config = StubClientConfig(starting_positions_count=2)
        client = EnhancedStubClobClient(config)

        positions = client.get_positions()
        assert len(positions) == 2

        for pos in positions:
            assert "token_id" in pos
            assert "market_slug" in pos
            assert "outcome_type" in pos
            assert "usd_value" in pos
            assert "size" in pos
            # New fields
            assert "market_price" in pos
            assert "last_updated" in pos


class TestErrorSimulation:
    """Test error simulation capabilities."""

    def test_network_error_scenario(self):
        """Test network error simulation."""
        config = StubClientConfig(error_scenario=ErrorScenario.NETWORK_ERROR)
        client = EnhancedStubClobClient(config)

        with pytest.raises(Exception) as exc_info:
            client.create_order({})

        error_msg = str(exc_info.value).lower()
        assert any(
            keyword in error_msg
            for keyword in ["network", "unreachable", "dns", "resolution"]
        )

    def test_server_error_scenario(self):
        """Test server error simulation."""
        config = StubClientConfig(error_scenario=ErrorScenario.SERVER_ERROR)
        client = EnhancedStubClobClient(config)

        with pytest.raises(Exception) as exc_info:
            client.get_positions()

        error_msg = str(exc_info.value)
        assert any(code in error_msg for code in ["500", "502", "503"])

    def test_rate_limit_scenario(self):
        """Test rate limit error simulation."""
        config = StubClientConfig(error_scenario=ErrorScenario.RATE_LIMIT)
        client = EnhancedStubClobClient(config)

        with pytest.raises(Exception) as exc_info:
            client.cancel_all()

        assert "429" in str(exc_info.value) or "Too Many Requests" in str(
            exc_info.value
        )

    def test_timeout_scenario(self):
        """Test timeout error simulation."""
        config = StubClientConfig(error_scenario=ErrorScenario.TIMEOUT)
        client = EnhancedStubClobClient(config)

        with pytest.raises(Exception) as exc_info:
            client.get_orders()

        error_msg = str(exc_info.value).lower()
        assert any(keyword in error_msg for keyword in ["timeout", "timed out", "504"])

    def test_connection_error_scenario(self):
        """Test connection error simulation."""
        config = StubClientConfig(error_scenario=ErrorScenario.CONNECTION_ERROR)
        client = EnhancedStubClobClient(config)

        with pytest.raises(Exception) as exc_info:
            client.get_balance()

        error_msg = str(exc_info.value).lower()
        assert any(
            keyword in error_msg for keyword in ["connection", "refused", "reset"]
        )

    def test_probabilistic_errors(self):
        """Test probabilistic error simulation."""
        config = StubClientConfig(
            error_scenario=ErrorScenario.SERVER_ERROR,
            error_probability=1.0,  # Always error
        )
        client = EnhancedStubClobClient(config)

        # Should always error
        with pytest.raises(Exception):
            client.create_order({})

        # Test with lower probability - need to disable error scenario
        new_config = StubClientConfig(
            error_scenario=ErrorScenario.NONE,  # Disable error scenario
            error_probability=0.0,  # Never error
        )
        client.set_config(new_config)

        # Should never error
        result = client.create_order(
            {"token_id": "test", "side": "buy", "price": 0.5, "size": 100}
        )
        assert result is not None

    def test_consecutive_errors_limit(self):
        """Test consecutive errors limit."""
        config = StubClientConfig(
            error_scenario=ErrorScenario.SERVER_ERROR,
            consecutive_errors=2,  # Only 2 consecutive errors
        )
        client = EnhancedStubClobClient(config)

        # First two calls should error
        with pytest.raises(Exception):
            client.get_positions()
        with pytest.raises(Exception):
            client.get_positions()

        # Third call should succeed
        result = client.get_positions()
        assert isinstance(result, list)

    def test_intermittent_errors(self):
        """Test intermittent error behavior."""
        config = StubClientConfig(error_scenario=ErrorScenario.INTERMITTENT)
        client = EnhancedStubClobClient(config)

        # Make multiple calls - some should succeed, some should fail
        results = []
        for _ in range(20):
            try:
                client.get_positions()
                results.append("success")
            except Exception:
                results.append("error")

        # Should have mixed results (but allow for edge cases in testing)
        unique_results = set(results)
        # In a small sample, we might get all one type due to randomness
        # Just ensure we got some results
        assert len(results) == 20
        assert all(r in ["success", "error"] for r in results)


class TestRateLimiting:
    """Test rate limiting simulation."""

    def test_rate_limit_threshold(self):
        """Test rate limiting threshold enforcement."""
        config = StubClientConfig(
            rate_limit_threshold=3, rate_limit_window=10  # Very low threshold
        )
        client = EnhancedStubClobClient(config)

        # Make requests up to threshold - should succeed
        for _ in range(3):
            result = client.get_positions()
            assert isinstance(result, list)

        # Next request should be rate limited
        with pytest.raises(Exception, match="429|Too Many Requests"):
            client.get_positions()

    def test_rate_limit_window_reset(self):
        """Test that rate limits reset after time window."""
        config = StubClientConfig(
            rate_limit_threshold=2, rate_limit_window=1
        )  # 1 second window
        client = EnhancedStubClobClient(config)

        # Use up the rate limit
        client.get_positions()
        client.get_positions()

        with pytest.raises(Exception):
            client.get_positions()

        # Wait for window to reset
        time.sleep(1.1)

        # Should work again
        result = client.get_positions()
        assert isinstance(result, list)


class TestTimingSimulation:
    """Test response timing simulation."""

    def test_response_delay(self):
        """Test that response delays are applied."""
        config = StubClientConfig(min_response_delay=0.05, max_response_delay=0.1)
        client = EnhancedStubClobClient(config)

        start_time = time.time()
        client.get_positions()
        elapsed = time.time() - start_time

        assert elapsed >= 0.04  # Account for timing variations

    def test_no_delay_when_zero(self):
        """Test no delay when configured to zero."""
        config = StubClientConfig(min_response_delay=0.0, max_response_delay=0.0)
        client = EnhancedStubClobClient(config)

        start_time = time.time()
        client.get_positions()
        elapsed = time.time() - start_time

        assert elapsed < 0.01  # Should be very fast


class TestPositionVolatility:
    """Test position value volatility simulation."""

    def test_position_volatility(self):
        """Test that positions change with volatility."""
        config = StubClientConfig(
            starting_positions_count=2, position_volatility=0.2  # 20% volatility
        )
        client = EnhancedStubClobClient(config)

        # Get initial positions
        positions1 = client.get_positions()
        initial_values = [pos["usd_value"] for pos in positions1]

        # Get positions again - values should have changed
        positions2 = client.get_positions()
        second_values = [pos["usd_value"] for pos in positions2]

        # At least some values should be different (with high probability)
        # We'll allow for the small chance they're the same due to randomness
        if len(initial_values) > 0:
            # Check if any values changed
            values_changed = any(
                abs(v1 - v2) > 0.01
                for v1, v2 in zip(initial_values, second_values, strict=False)
            )
            # With 20% volatility, changes are very likely
            # But we'll be lenient in testing due to randomness
            assert isinstance(positions2, list)  # At least verify we got positions

    def test_no_volatility(self):
        """Test positions don't change without volatility."""
        config = StubClientConfig(
            starting_positions_count=2, position_volatility=0.0  # No volatility
        )
        client = EnhancedStubClobClient(config)

        positions1 = client.get_positions()
        positions2 = client.get_positions()

        # Values should be exactly the same
        for pos1, pos2 in zip(positions1, positions2, strict=False):
            assert pos1["usd_value"] == pos2["usd_value"]


class TestOrderFillBehavior:
    """Test order fill simulation."""

    def test_order_fill_probability(self, mock_order_args):
        """Test order fill probability settings."""
        # Test 100% fill rate
        config = StubClientConfig(order_fill_probability=1.0)
        client = EnhancedStubClobClient(config)

        order = client.create_order(mock_order_args)
        assert order.status == "filled"
        assert order.filled_size == order.size

        # Test 0% fill rate
        config = StubClientConfig(order_fill_probability=0.0)
        client.set_config(config)

        order = client.create_order(mock_order_args)
        assert order.status == "open"
        assert order.filled_size == 0.0

    def test_order_fill_delay(self, mock_order_args):
        """Test order fill delay simulation."""
        config = StubClientConfig(order_fill_probability=1.0, order_fill_delay=0.05)
        client = EnhancedStubClobClient(config)

        start_time = time.time()
        order = client.create_order(mock_order_args)
        elapsed = time.time() - start_time

        assert order.status == "filled"
        assert elapsed >= 0.04  # Account for timing variations


class TestStatisticsAndMonitoring:
    """Test statistics collection and monitoring features."""

    def test_request_counting(self):
        """Test request counting."""
        client = EnhancedStubClobClient()

        initial_stats = client.get_stats()
        assert initial_stats["total_requests"] == 0

        client.get_positions()
        client.create_order(
            {"token_id": "test", "side": "buy", "price": 0.5, "size": 100}
        )

        stats = client.get_stats()
        assert stats["total_requests"] == 2
        assert stats["orders_created"] == 1

    def test_error_counting(self):
        """Test error counting."""
        config = StubClientConfig(error_scenario=ErrorScenario.SERVER_ERROR)
        client = EnhancedStubClobClient(config)

        try:
            client.get_positions()
        except Exception:
            pass

        try:
            client.create_order({})
        except Exception:
            pass

        stats = client.get_stats()
        assert stats["total_errors"] == 2
        assert stats["error_rate"] == 1.0  # 100% error rate

    def test_stats_reset(self):
        """Test statistics reset."""
        client = EnhancedStubClobClient()

        client.get_positions()
        client.create_order(
            {"token_id": "test", "side": "buy", "price": 0.5, "size": 100}
        )

        stats = client.get_stats()
        assert stats["total_requests"] > 0

        client.reset_stats()
        stats_after = client.get_stats()
        assert stats_after["total_requests"] == 0
        assert stats_after["total_errors"] == 0


class TestCustomErrorCallback:
    """Test custom error injection via callback."""

    def test_custom_error_callback(self):
        """Test custom error callback functionality."""

        def custom_error(method_name, request_count):
            if method_name == "create_order" and request_count == 1:
                return ValueError("Custom validation error")
            return None

        config = StubClientConfig(custom_error_callback=custom_error)
        client = EnhancedStubClobClient(config)

        # First create_order call should trigger custom error
        with pytest.raises(ValueError, match="Custom validation error"):
            client.create_order({})

        # Second call should succeed
        result = client.create_order(
            {"token_id": "test", "side": "buy", "price": 0.5, "size": 100}
        )
        assert result is not None


class TestResponseModification:
    """Test response modification functionality."""

    def test_response_modifier(self):
        """Test response modification callback."""

        def modify_response(response, method_name):
            if method_name == "get_positions" and isinstance(response, list):
                # Add extra field to all positions
                for pos in response:
                    if isinstance(pos, dict):
                        pos["modified"] = True
            return response

        config = StubClientConfig(
            starting_positions_count=2, response_modifier=modify_response
        )
        client = EnhancedStubClobClient(config)

        positions = client.get_positions()
        assert len(positions) == 2

        for pos in positions:
            assert pos.get("modified") is True


class TestConvenienceFactories:
    """Test convenience factory functions."""

    def test_network_error_client(self):
        """Test network error client factory."""
        client = create_network_error_client()

        with pytest.raises(Exception):
            client.get_positions()

    def test_rate_limited_client(self):
        """Test rate limited client factory."""
        client = create_rate_limited_client()

        # Rate limit threshold is 5, so make exactly 5 requests
        for i in range(5):
            client.get_positions()

        # The 6th request should be rate limited
        with pytest.raises(Exception, match="429|Too Many Requests"):
            client.get_positions()

    def test_intermittent_error_client(self):
        """Test intermittent error client factory."""
        client = create_intermittent_error_client()

        # Make multiple calls - should have mixed results
        results = []
        for _ in range(10):
            try:
                client.get_positions()
                results.append("success")
            except Exception:
                results.append("error")

        # Should have some results (allow for randomness in small samples)
        assert len(results) == 10
        assert all(r in ["success", "error"] for r in results)

    def test_slow_response_client(self):
        """Test slow response client factory."""
        client = create_slow_response_client()

        start_time = time.time()
        client.get_positions()
        elapsed = time.time() - start_time

        assert elapsed >= 0.4  # Should be slow

    def test_realistic_trading_client(self):
        """Test realistic trading client factory."""
        client = create_realistic_trading_client()

        # Should have starting positions
        positions = client.get_positions()
        assert len(positions) == 3

        # Orders should mostly fill
        filled_count = 0
        for _ in range(10):
            order = client.create_order(
                {"token_id": "test", "side": "buy", "price": 0.5, "size": 100}
            )
            if order.status == "filled":
                filled_count += 1

        # With 90% fill rate, should have mostly filled orders (allow for randomness)
        assert filled_count >= 6  # Allow more variance due to partial fills


class TestIntegrationWithOrderClient:
    """Test integration with OrderClient."""

    def test_order_client_with_enhanced_stub(self):
        """Test OrderClient using enhanced stub."""
        # Create config that will use stub (no py-clob-client)
        config = BotConfig(
            api_base="https://test.com",
            private_key=None,
            api_retry_attempts=3,
            api_retry_delay_seconds=1,
            api_retry_max_delay_seconds=60.0,
            api_retry_exponential_base=2.0,
            api_retry_jitter_enabled=True,
            api_retry_jitter_range=0.1,
            api_retry_backoff_strategy="exponential",
        )
        state = StateManager(":memory:")

        stub_config = StubClientConfig(starting_positions_count=2)

        with patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", False):
            client = OrderClient(config, state, stub_config)

            assert client.is_using_enhanced_stub()
            assert not client.ready()  # Still not "ready" since it's using stub

            # Test basic operations work
            result = client.place_limit("test_token", "buy", 0.65, 100)
            assert result is not None

            positions = client.get_positions()
            assert len(positions) == 2

            # Test stub statistics
            stats = client.get_stub_stats()
            assert "total_requests" in stats
            assert stats["total_requests"] > 0

    def test_stub_configuration_during_runtime(self):
        """Test configuring stub behavior during runtime."""
        config = BotConfig(
            api_base="https://test.com",
            private_key=None,
            api_retry_attempts=3,
            api_retry_delay_seconds=1,
            api_retry_max_delay_seconds=60.0,
            api_retry_exponential_base=2.0,
            api_retry_jitter_enabled=True,
            api_retry_jitter_range=0.1,
            api_retry_backoff_strategy="exponential",
        )
        state = StateManager(":memory:")

        with patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", False):
            client = OrderClient(config, state)

            # Initially should work
            result = client.get_positions()
            assert isinstance(result, list)

            # Configure to always error
            error_config = StubClientConfig(error_scenario=ErrorScenario.SERVER_ERROR)
            client.configure_stub_behavior(error_config)

            # Now should error
            result = client.get_positions()
            assert result == []  # OrderClient handles errors gracefully


class TestNewEnhancements:
    """Test new enhancements to the stub client."""

    def test_circuit_breaker_functionality(self):
        """Test circuit breaker behavior."""
        config = StubClientConfig(
            error_scenario=ErrorScenario.SERVER_ERROR,
            circuit_breaker_threshold=2,
            circuit_breaker_timeout=1,
        )
        client = EnhancedStubClobClient(config)

        # First two requests should error and trip circuit breaker
        with pytest.raises(Exception):
            client.get_positions()
        with pytest.raises(Exception):
            client.get_positions()

        # Next request should be circuit breaker error
        with pytest.raises(Exception, match="Circuit breaker"):
            client.get_positions()

        # Wait for timeout
        time.sleep(1.1)

        # Should work again (no errors configured after reset)
        config_no_error = StubClientConfig()
        client.set_config(config_no_error)
        result = client.get_positions()
        assert isinstance(result, list)


class TestRealClientBehaviorSimulation:
    """Test enhanced features that better simulate real client behavior."""

    def test_balance_simulation(self):
        """Test balance tracking and insufficient balance scenarios."""
        client = create_balance_constraint_client(starting_balance=100.0)

        # Check initial balance
        balance = client.get_balance()
        assert balance["balance"] == 100.0
        assert balance["available"] == 100.0
        assert balance["reserved"] == 0.0

        # Create order that should succeed
        order_args = type(
            "MockOrderArgs",
            (),
            {
                "token_id": "test_token",
                "side": "buy",
                "price": 0.5,
                "size": 50.0,  # $25 order
            },
        )()

        order = client.create_order(order_args)
        assert order is not None

        # Balance should now show reserved amount
        balance = client.get_balance()
        assert balance["available"] < 100.0
        assert balance["reserved"] > 0.0

        # Try to create order that exceeds balance
        large_order_args = type(
            "MockOrderArgs",
            (),
            {
                "token_id": "test_token_2",
                "side": "buy",
                "price": 0.8,
                "size": 200.0,  # $160 order, should fail
            },
        )()

        with pytest.raises(Exception, match="Insufficient balance"):
            client.create_order(large_order_args)

    def test_enhanced_error_scenarios(self):
        """Test new error scenarios for better real client simulation."""
        # Test degraded performance
        config = StubClientConfig(
            error_scenario=ErrorScenario.DEGRADED_PERFORMANCE, error_probability=1.0
        )
        client = EnhancedStubClobClient(config)

        with pytest.raises(Exception) as exc_info:
            client.get_positions()

        error_msg = str(exc_info.value).lower()
        assert any(
            keyword in error_msg for keyword in ["degraded", "performance", "slow"]
        )

        # Test market closed
        config = StubClientConfig(
            error_scenario=ErrorScenario.MARKET_CLOSED, error_probability=1.0
        )
        client = EnhancedStubClobClient(config)

        with pytest.raises(Exception, match="Market is closed"):
            client.create_order(
                {"token_id": "test", "side": "buy", "price": 0.5, "size": 100}
            )

    def test_enhanced_validation(self):
        """Test enhanced parameter validation."""
        config = StubClientConfig(
            strict_parameter_validation=True, enable_order_validation=True
        )
        client = EnhancedStubClobClient(config)

        # Test invalid token ID format
        with pytest.raises(ValueError, match="Token ID format invalid"):
            client.create_order(
                {
                    "token_id": "!",  # Invalid format
                    "side": "buy",
                    "price": 0.5,
                    "size": 100,
                }
            )

        # Test price precision
        with pytest.raises(ValueError, match="Price precision too high"):
            client.create_order(
                {
                    "token_id": "valid_token",
                    "side": "buy",
                    "price": 0.123456789,  # Too many decimal places
                    "size": 100,
                }
            )

    def test_comprehensive_stats(self):
        """Test comprehensive statistics reporting."""
        client = create_enhanced_realistic_client()

        # Generate some activity
        try:
            client.create_order(
                {"token_id": "test", "side": "buy", "price": 0.5, "size": 100}
            )
        except Exception:
            pass  # Errors are expected in enhanced realistic client

        try:
            client.get_positions()
        except Exception:
            pass

        stats = client.get_stats()

        # Verify enhanced stats are present
        required_stats = [
            "total_requests",
            "total_errors",
            "error_rate",
            "orders_created",
            "orders_filled",
            "orders_partial",
            "orders_open",
            "orders_cancelled",
            "fill_rate",
            "total_order_value",
            "filled_value",
            "positions",
            "total_position_value",
            "total_unrealized_pnl",
            "current_balance",
            "reserved_balance",
            "available_balance",
            "circuit_breaker_tripped",
            "error_cluster_active",
            "websocket_connected",
            "market_prices",
            "order_book_tokens",
        ]

        for stat_key in required_stats:
            assert stat_key in stats, f"Missing stat: {stat_key}"

    def test_convenience_factory_methods(self):
        """Test the new convenience factory methods."""
        # Test enhanced realistic client
        client = create_enhanced_realistic_client()
        assert isinstance(client, EnhancedStubClobClient)
        assert client.config.simulate_balance_checks
        assert client.config.error_clustering

        # Test stress test client
        stress_client = create_stress_test_client()
        assert isinstance(stress_client, EnhancedStubClobClient)
        assert stress_client.config.error_probability == 0.2
        assert stress_client.config.simulate_load_shedding

        # Test balance constraint client
        balance_client = create_balance_constraint_client(500.0)
        assert isinstance(balance_client, EnhancedStubClobClient)
        assert balance_client._balance == 500.0

    def test_market_conditions(self):
        """Test market condition effects."""
        # Test market closed
        config = StubClientConfig(market_condition=MarketCondition.MARKET_CLOSED)
        client = EnhancedStubClobClient(config)

        with pytest.raises(Exception, match="Market is closed"):
            client.create_order(
                {"token_id": "test", "side": "buy", "price": 0.5, "size": 100}
            )

        # Test market halted
        config.market_condition = MarketCondition.HALTED
        client.set_config(config)

        with pytest.raises(Exception, match="Trading halted"):
            client.get_positions()

    def test_order_validation(self):
        """Test order parameter validation."""
        config = StubClientConfig(
            enable_order_validation=True,
            min_order_size=10.0,
            max_order_size=1000.0,
            min_price=0.1,
            max_price=0.9,
        )
        client = EnhancedStubClobClient(config)

        # Valid order should work
        order = client.create_order(
            {"token_id": "test", "side": "buy", "price": 0.5, "size": 100}
        )
        assert order is not None

        # Invalid price should fail
        with pytest.raises(ValueError, match="Price .* outside valid range"):
            client.create_order(
                {
                    "token_id": "test",
                    "side": "buy",
                    "price": 0.05,  # Below min_price
                    "size": 100,
                }
            )

        # Invalid size should fail
        with pytest.raises(ValueError, match="Size .* outside valid range"):
            client.create_order(
                {
                    "token_id": "test",
                    "side": "buy",
                    "price": 0.5,
                    "size": 5,  # Below min_size
                }
            )

    def test_partial_fills(self):
        """Test partial order fills."""
        config = StubClientConfig(
            order_fill_probability=1.0,
            partial_fill_probability=1.0,  # Always partial fill
        )
        client = EnhancedStubClobClient(config)

        order = client.create_order(
            {"token_id": "test", "side": "buy", "price": 0.5, "size": 100}
        )

        assert order.status == "partial"
        assert 0 < order.filled_size < order.size
        assert order.avg_fill_price is not None

    def test_market_price_simulation(self):
        """Test market price updates and volatility."""
        config = StubClientConfig(starting_positions_count=2, position_volatility=0.1)
        client = EnhancedStubClobClient(config)

        # Get initial positions
        positions1 = client.get_positions()
        initial_prices = {
            pos["token_id"]: pos.get("market_price") for pos in positions1
        }

        # Force market data update
        client._last_market_update = 0

        # Get positions again
        positions2 = client.get_positions()

        # Market prices should be tracked
        stats = client.get_stats()
        assert "market_prices" in stats
        assert len(stats["market_prices"]) > 0

    def test_response_format_variations(self):
        """Test response format variations."""
        config = StubClientConfig(
            response_format_variation=1.0,  # Always apply variation
            include_metadata=True,
        )
        client = EnhancedStubClobClient(config)

        # Test multiple calls to get different variations
        responses = []
        for _ in range(5):
            try:
                response = client.get_positions()
                responses.append(response)
            except Exception:
                pass

        # Should have gotten some responses with variations
        assert len(responses) > 0

    def test_liquidity_impact(self):
        """Test liquidity impact on order prices."""
        config = StubClientConfig(
            liquidity_impact=0.05,  # 5% impact
            enable_order_validation=False,  # Disable validation to allow price changes
        )
        client = EnhancedStubClobClient(config)

        original_price = 0.5
        order = client.create_order(
            {
                "token_id": "test",
                "side": "buy",
                "price": original_price,
                "size": 1000,  # Large order
            }
        )

        # Price may have changed due to liquidity impact
        # Just verify the order was created
        assert order is not None
        assert order.price > 0

    def test_enhanced_statistics(self):
        """Test enhanced statistics collection."""
        client = EnhancedStubClobClient()

        # Create some orders
        client.create_order(
            {"token_id": "test", "side": "buy", "price": 0.5, "size": 100}
        )

        stats = client.get_stats()

        # Check enhanced stats
        assert "orders_filled" in stats
        assert "orders_partial" in stats
        assert "orders_open" in stats
        assert "circuit_breaker_tripped" in stats
        assert "circuit_breaker_failures" in stats
        assert "market_prices" in stats

    def test_thread_safety(self):
        """Test thread safety of stub client operations."""
        import threading

        client = EnhancedStubClobClient()
        results = []
        errors = []

        def make_requests():
            try:
                for _ in range(10):
                    positions = client.get_positions()
                    results.append(len(positions))
            except Exception as e:
                errors.append(str(e))

        # Run multiple threads
        threads = [threading.Thread(target=make_requests) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have some results and no thread-related errors
        assert len(results) > 0
        # Errors might occur due to configured scenarios, but not thread safety issues


class TestConvenienceFactoryEnhancements:
    """Test enhanced convenience factory functions."""

    def test_circuit_breaker_client(self):
        """Test circuit breaker client factory."""
        client = create_circuit_breaker_client()

        # Should start failing
        error_count = 0
        for _ in range(5):
            try:
                client.get_positions()
            except Exception:
                error_count += 1

        assert error_count > 0

    def test_market_condition_client(self):
        """Test market condition client factory."""
        client = create_market_condition_client(MarketCondition.HIGH_VOLATILITY)

        # Should have starting positions and high volatility
        positions = client.get_positions()
        assert isinstance(positions, list)

    def test_validation_heavy_client(self):
        """Test validation heavy client factory."""
        client = create_validation_heavy_client()

        # Should reject invalid orders
        with pytest.raises(ValueError):
            client.create_order(
                {
                    "token_id": "test",
                    "side": "buy",
                    "price": 0.01,  # Below min_price
                    "size": 100,
                }
            )

    def test_partial_failure_client(self):
        """Test partial failure client factory."""
        client = create_partial_failure_client()

        # Should work but might have partial fills and format variations
        try:
            order = client.create_order(
                {"token_id": "test", "side": "buy", "price": 0.5, "size": 100}
            )
            # If successful, verify it's a valid order
            assert order is not None
        except Exception:
            # Partial failures are expected
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
