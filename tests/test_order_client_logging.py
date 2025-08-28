"""
Tests for order client logging improvements.

This test verifies that all exception handlers in order_client.py
properly log errors with traceback information instead of silently
swallowing exceptions.
"""

import logging
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.order_client import OrderClient, StubClobClient
from inkedup_bot.state import StateManager


@pytest.fixture
def mock_config():
    """Create a mock bot configuration."""
    config = MagicMock(spec=BotConfig)
    config.private_key = "test_private_key"
    config.api_base = "https://test-api.polymarket.com"
    # Add retry configuration values
    config.api_retry_attempts = 3
    config.api_retry_delay_seconds = 1
    config.api_retry_max_delay_seconds = 60.0
    config.api_retry_exponential_base = 2.0
    config.api_retry_jitter_enabled = True
    config.api_retry_jitter_range = 0.1
    config.api_retry_backoff_strategy = "exponential"
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
    logger = logging.getLogger("order_client")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield log_stream
    logger.removeHandler(handler)


class TestOrderClientLogging:
    """Test logging in OrderClient exception handlers."""

    def test_clob_client_initialization_error_logging(
        self, mock_config, mock_state, log_capture
    ):
        """Test that ClobClient initialization errors are properly logged."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
        ):

            # Make ClobClient initialization raise an exception
            mock_clob.side_effect = Exception("Connection failed")

            # Create OrderClient - this should trigger the exception
            client = OrderClient(mock_config, mock_state)

            # Check that error was logged with traceback
            log_output = log_capture.getvalue()
            assert "Failed to initialize ClobClient" in log_output
            assert "Connection failed" in log_output
            # Check that exc_info=True was used (traceback should be present)
            assert "Traceback" in log_output

            # Verify fallback to StubClobClient
            assert isinstance(client.client, StubClobClient)

    def test_state_add_order_error_logging(self, mock_config, mock_state, log_capture):
        """Test that state.add_order errors are properly logged."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
            patch("inkedup_bot.order_client.OrderArgs") as mock_order_args,
            patch("inkedup_bot.order_client.asdict") as mock_asdict,
        ):

            # Setup successful order creation but failing state update
            mock_client = MagicMock()
            mock_clob.return_value = mock_client
            mock_order = MagicMock()
            mock_order.id = "test_order_id"
            mock_client.create_order.return_value = mock_order
            mock_asdict.return_value = {"id": "test_order_id"}
            mock_state.add_order.side_effect = Exception("Database error")

            client = OrderClient(mock_config, mock_state)

            # Place order - this should trigger the state update error
            result = client.place_limit("test_token", "buy", 0.5, 100)

            # Check that error was logged with traceback
            log_output = log_capture.getvalue()
            assert "Failed to add order to state" in log_output
            assert "Database error" in log_output
            assert "Traceback" in log_output

    def test_risk_record_trade_error_logging(
        self, mock_config, mock_state, log_capture
    ):
        """Test that risk.record_trade errors are properly logged."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
            patch("inkedup_bot.order_client.OrderArgs") as mock_order_args,
            patch("inkedup_bot.order_client.asdict") as mock_asdict,
        ):

            # Setup successful order creation but failing risk recording
            mock_client = MagicMock()
            mock_clob.return_value = mock_client
            mock_order = MagicMock()
            mock_order.id = "test_order_id"
            mock_client.create_order.return_value = mock_order
            mock_asdict.return_value = {"id": "test_order_id"}

            mock_risk = MagicMock()
            mock_risk.record_trade.side_effect = Exception("Risk manager error")

            client = OrderClient(mock_config, mock_state)

            # Place order with risk manager - this should trigger the recording error
            result = client.place_limit(
                "test_token", "buy", 0.5, 100, risk=mock_risk, notional_value=50.0
            )

            # Check that error was logged with traceback
            log_output = log_capture.getvalue()
            assert "Failed to record trade in risk manager" in log_output
            assert "Risk manager error" in log_output
            assert "Traceback" in log_output

    def test_cancel_all_error_logging(self, mock_config, mock_state, log_capture):
        """Test that cancel_all errors are properly logged."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
        ):

            # Setup client that throws exception on cancel_all
            mock_client = MagicMock()
            mock_clob.return_value = mock_client
            mock_client.cancel_all.side_effect = Exception("Cancel failed")

            client = OrderClient(mock_config, mock_state)

            # Call cancel_all - this should trigger the error
            result = client.cancel_all()

            # Check that error was logged with traceback
            log_output = log_capture.getvalue()
            assert "Cancel error" in log_output
            assert "Cancel failed" in log_output
            assert "Traceback" in log_output

            # Should return empty list on error
            assert result == []

    def test_get_positions_error_logging(self, mock_config, mock_state, log_capture):
        """Test that get_positions errors are properly logged."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
        ):

            # Setup client that throws exception on get_positions
            mock_client = MagicMock()
            mock_clob.return_value = mock_client
            mock_client.get_positions.side_effect = Exception("Positions fetch failed")

            client = OrderClient(mock_config, mock_state)

            # Call get_positions - this should trigger the error
            result = client.get_positions()

            # Check that error was logged with traceback
            log_output = log_capture.getvalue()
            assert "Positions error" in log_output
            assert "Positions fetch failed" in log_output
            assert "Traceback" in log_output

            # Should return empty list on error
            assert result == []

    def test_exposure_usd_error_logging(self, mock_config, mock_state, log_capture):
        """Test that exposure_usd handles position parsing gracefully with robust error handling."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
        ):

            # Setup client that returns malformed position data
            mock_client = MagicMock()
            mock_clob.return_value = mock_client

            # Create position data that will be handled gracefully by the robust parser
            test_positions = [
                {"usd_value": "invalid_number"},  # Handled gracefully - debug logged
                {"usd_value": None},  # Handled gracefully - debug logged
                {"no_usd_value": True},  # Fallback parsing finds numeric value
            ]
            mock_client.get_positions.return_value = test_positions

            client = OrderClient(mock_config, mock_state)

            # Call exposure_usd - this should handle all cases gracefully
            result = client.exposure_usd()

            # Check that graceful handling is logged appropriately
            log_output = log_capture.getvalue()
            assert (
                "Cannot parse string value to float" in log_output
            )  # Debug messages for invalid strings
            assert (
                "Processing" in log_output
                and "positions for USD exposure calculation" in log_output
            )

            # Should still return a valid float result
            assert isinstance(result, float)
            # The third position should contribute 1.0 via fallback parsing
            assert result >= 0.0

    def test_place_limit_comprehensive_error_logging(
        self, mock_config, mock_state, log_capture
    ):
        """Test comprehensive error logging in place_limit method."""
        with (
            patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", True),
            patch("inkedup_bot.order_client.ClobClient") as mock_clob,
            patch("inkedup_bot.order_client.OrderArgs") as mock_order_args,
        ):

            # Setup client that throws exception during order creation
            mock_client = MagicMock()
            mock_clob.return_value = mock_client
            mock_client.create_order.side_effect = Exception("Unexpected API error")

            client = OrderClient(mock_config, mock_state)

            # Place order - this should trigger the unexpected error handler
            result = client.place_limit("test_token", "buy", 0.5, 100)

            # Check that error was logged with comprehensive details
            log_output = log_capture.getvalue()
            assert "Unexpected order failure" in log_output
            assert "Exception" in log_output  # Exception type name
            assert "Unexpected API error" in log_output
            assert "Traceback" in log_output

            # Should return None on error
            assert result is None


class TestStubClientLogging:
    """Test that StubClobClient properly raises informative errors."""

    def test_stub_client_methods_raise_informative_errors(
        self, mock_config, mock_state
    ):
        """Test that StubClobClient methods raise informative UnavailableClientError."""
        # Create OrderClient with no py-clob-client installed
        with patch("inkedup_bot.order_client.PY_CLOB_CLIENT_INSTALLED", False):
            client = OrderClient(mock_config, mock_state)

            # Verify stub client is used
            assert isinstance(client.client, StubClobClient)

            # Test that methods raise informative errors
            with pytest.raises(Exception) as exc_info:
                client.client.create_order()
            assert "py-clob-client not available" in str(exc_info.value)

            with pytest.raises(Exception) as exc_info:
                client.client.cancel_all()
            assert "py-clob-client not available" in str(exc_info.value)

            with pytest.raises(Exception) as exc_info:
                client.client.get_positions()
            assert "py-clob-client not available" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
