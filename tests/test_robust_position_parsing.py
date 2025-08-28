"""
Comprehensive tests for robust position parsing in order_client.py.

Tests various edge cases and data structure inconsistencies that may occur
in exchange API responses, ensuring the exposure_usd() method can handle
all scenarios gracefully.
"""

import logging
from collections import namedtuple
from dataclasses import dataclass
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.order_client import OrderClient
from inkedup_bot.state import StateManager


# Test data structures
@dataclass
class MockPosition:
    usd_value: float
    size: float
    symbol: str


PositionTuple = namedtuple("PositionTuple", ["usd_value", "quantity", "market"])


class MockPositionObject:
    def __init__(self, usd_value=None, notional=None, value=None):
        self.usd_value = usd_value
        self.notional = notional
        self.value = value


@pytest.fixture
def mock_config():
    """Create a mock bot configuration."""
    config = MagicMock(spec=BotConfig)
    config.private_key = None  # Use stub client for testing
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
def order_client(mock_config, mock_state):
    """Create OrderClient instance for testing."""
    return OrderClient(mock_config, mock_state)


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


class TestRobustPositionParsing:
    """Test robust position parsing logic."""

    def test_standard_dictionary_positions(self, order_client):
        """Test parsing standard dictionary positions."""
        positions = [
            {"usd_value": 100.5},
            {"usd_value": 250.75},
            {"usd_value": -50.25},  # Short position
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        assert result == 301.0  # 100.5 + 250.75 + (-50.25)

    def test_dataclass_positions(self, order_client):
        """Test parsing dataclass positions."""
        positions = [
            MockPosition(usd_value=100.0, size=10.0, symbol="BTC"),
            MockPosition(usd_value=200.0, size=5.0, symbol="ETH"),
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        assert result == 300.0

    def test_named_tuple_positions(self, order_client):
        """Test parsing named tuple positions."""
        positions = [
            PositionTuple(usd_value=150.0, quantity=10, market="BTCUSD"),
            PositionTuple(usd_value=75.5, quantity=5, market="ETHUSD"),
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        assert result == 225.5

    def test_object_positions(self, order_client):
        """Test parsing object positions."""
        positions = [
            MockPositionObject(usd_value=100.0),
            MockPositionObject(notional=200.0),  # Alternative field name
            MockPositionObject(value=50.0),  # Generic field name
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        assert result == 350.0

    def test_mixed_data_structures(self, order_client):
        """Test parsing mixed data structures."""
        positions = [
            {"usd_value": 100.0},
            MockPosition(usd_value=150.0, size=10.0, symbol="BTC"),
            PositionTuple(usd_value=75.0, quantity=5, market="ETHUSD"),
            MockPositionObject(usd_value=25.0),
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        assert result == 350.0

    def test_alternative_field_names(self, order_client):
        """Test parsing positions with various field names."""
        positions = [
            {"usd_value": 100.0},
            {"usdValue": 50.0},  # camelCase
            {"USD_VALUE": 25.0},  # UPPER_CASE
            {"value_usd": 75.0},  # alternative format
            {"notional": 200.0},  # financial term
            {"market_value": 150.0},  # descriptive name
            {"position_value": 100.0},  # position-specific
            {"amount_usd": 50.0},  # amount variant
            {"total_value": 25.0},  # total variant
            {"value": 10.0},  # generic fallback
            {"amount": 5.0},  # generic fallback
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        # Should find the first valid field in each position
        expected = (
            100.0
            + 50.0
            + 25.0
            + 75.0
            + 200.0
            + 150.0
            + 100.0
            + 50.0
            + 25.0
            + 10.0
            + 5.0
        )
        assert result == expected

    def test_nested_position_structures(self, order_client):
        """Test parsing nested position structures."""
        positions = [
            {"position": {"usd_value": 100.0, "size": 10.0}},
            {"data": {"financials": {"notional": 200.0}}},
            {"info": {"value": 50.0}},
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        assert result == 350.0

    def test_string_numeric_values(self, order_client):
        """Test parsing string representations of numeric values."""
        positions = [
            {"usd_value": "100.50"},
            {"usd_value": "1,250.75"},  # With thousands separator
            {"usd_value": "$500.25"},  # With currency symbol
            {"usd_value": "€300.00"},  # Different currency symbol
            {"usd_value": "(75.50)"},  # Accounting format (negative)
            {"usd_value": "25.5%"},  # Percentage format
            {"usd_value": "1.5e2"},  # Scientific notation
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        # 100.5 + 1250.75 + 500.25 + 300.0 + (-75.5) + 0.255 + 150.0
        expected = 100.5 + 1250.75 + 500.25 + 300.0 - 75.5 + 0.255 + 150.0
        assert abs(result - expected) < 0.01  # Allow for floating point precision

    def test_invalid_and_null_values(self, order_client, log_capture):
        """Test handling of invalid and null values."""
        positions = [
            {"usd_value": None},
            {"usd_value": ""},
            {"usd_value": "null"},
            {"usd_value": "N/A"},
            {"usd_value": "invalid_number"},
            {"usd_value": float("nan")},
            {"usd_value": 100.0},  # Valid value
            {},  # Empty dict
            None,  # None position
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        # Should only sum the valid value
        assert result == 100.0

        # Check that warnings were logged for problematic positions
        log_output = log_capture.getvalue()
        assert "no valid USD value found" in log_output

    def test_list_and_array_values(self, order_client):
        """Test handling of list/array values."""
        positions = [
            {"usd_value": [100.0, 200.0]},  # Should take first numeric
            {"usd_value": ["invalid", 150.0]},  # Should take first valid numeric
            {"usd_value": []},  # Empty array
            {"usd_value": [None, None, 75.0]},  # Should find valid value
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        # 100.0 + 150.0 + 0.0 + 75.0
        assert result == 325.0

    def test_boolean_values(self, order_client):
        """Test handling of boolean values."""
        positions = [
            {"usd_value": True},  # Should be 1.0
            {"usd_value": False},  # Should be 0.0
            {"active": True, "value": 100.0},  # Should find value field
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        # 1.0 + 0.0 + 100.0
        assert result == 101.0

    def test_case_insensitive_field_matching(self, order_client):
        """Test case-insensitive field name matching."""
        positions = [
            {"USD_VALUE": 100.0},
            {"usd_value": 50.0},
            {"Usd_Value": 25.0},
            {"NOTIONAL": 200.0},
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        assert result == 375.0

    def test_dot_notation_nested_access(self, order_client):
        """Test dot notation for nested field access."""
        # This tests the _extract_nested_value method's dot notation support
        position = {"position": {"financial": {"usd_value": 100.0}}}

        # Test the nested value extraction directly
        result = order_client._extract_nested_value(
            position, "position.financial.usd_value"
        )
        assert result == 100.0

    def test_fallback_numeric_extraction(self, order_client):
        """Test fallback numeric value extraction when no standard fields exist."""
        positions = [
            {
                "unknown_field_1": "not_numeric",
                "unknown_field_2": 150.0,  # Should be picked as fallback
                "unknown_field_3": 50.0,  # Smaller value, should not be picked
                "metadata": {"info": "test"},
            },
            {"random_numeric": 0.0, "another_field": "text"},  # Zero value
            {
                "large_value": 2_000_000,  # Out of reasonable range
                "reasonable_value": 75.0,  # Should be picked
            },
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        # Should pick 150.0 (largest non-zero), 0.0 (only candidate), 75.0 (in range)
        assert result == 225.0

    def test_empty_positions_list(self, order_client, log_capture):
        """Test handling of empty positions list."""
        with patch.object(order_client, "get_positions", return_value=[]):
            result = order_client.exposure_usd()

        assert result == 0.0

        log_output = log_capture.getvalue()
        assert "No positions data available" in log_output

    def test_get_positions_returns_none(self, order_client, log_capture):
        """Test handling when get_positions returns None."""
        with patch.object(order_client, "get_positions", return_value=None):
            result = order_client.exposure_usd()

        assert result == 0.0

    def test_sanitization_of_sensitive_data(self, order_client, log_capture):
        """Test that sensitive data is properly sanitized in logs."""
        # Create a position that will cause an exception after normalization
        position_data = {
            "usd_value": "invalid",
            "private_key": "secret_key_123",
            "wallet_address": "0x123456789abcdef",
            "normal_field": "normal_value",
        }

        positions = [position_data]

        # Mock the _extract_usd_value_from_position to raise an exception
        original_method = order_client._extract_usd_value_from_position

        def mock_extract_usd_value(position):
            # This will cause an exception to be logged in the main loop with sanitization
            raise Exception("Simulated extraction error")

        with (
            patch.object(order_client, "get_positions", return_value=positions),
            patch.object(
                order_client,
                "_extract_usd_value_from_position",
                side_effect=mock_extract_usd_value,
            ),
        ):
            result = order_client.exposure_usd()

        log_output = log_capture.getvalue()
        assert "secret_key_123" not in log_output  # Should be redacted
        assert "0x123456789abcdef" not in log_output  # Should be redacted
        assert "[REDACTED]" in log_output
        assert "normal_value" in log_output  # Should not be redacted

    def test_performance_with_many_positions(self, order_client):
        """Test performance with a large number of positions."""
        positions = [{"usd_value": i * 0.1} for i in range(1000)]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        # Sum of 0.1 * (0 + 1 + 2 + ... + 999) = 0.1 * (999 * 1000 / 2)
        expected = 0.1 * (999 * 1000 / 2)
        assert abs(result - expected) < 0.01

    def test_exception_handling_in_position_processing(self, order_client, log_capture):
        """Test that exceptions during position processing are handled gracefully."""

        # Create a position that will cause an exception during processing
        class ProblematicPosition:
            def __getattribute__(self, name):
                if name == "__class__":
                    return ProblematicPosition
                raise Exception("Simulated processing error")

        positions = [
            {"usd_value": 100.0},  # Valid position
            ProblematicPosition(),  # Will cause exception
            {"usd_value": 50.0},  # Another valid position
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        # Should still process valid positions
        assert result == 150.0

        # Should log the exception (either normalization error or processing error)
        log_output = log_capture.getvalue()
        assert (
            "Failed to process position 1" in log_output
            or "Error normalizing position to dict" in log_output
        )
        assert "Simulated processing error" in log_output

    def test_currency_symbol_removal(self, order_client):
        """Test removal of various currency symbols."""
        positions = [
            {"usd_value": "$100.50"},
            {"usd_value": "€75.25"},
            {"usd_value": "£50.00"},
            {"usd_value": "¥1000.00"},
            {"usd_value": "₹500.75"},
            {"usd_value": "₽200.25"},
            {"usd_value": "₿0.01"},
            {"usd_value": "100.00USD"},
            {"usd_value": "75.50EUR"},
            {"usd_value": "50.25GBP"},
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        expected = (
            100.50
            + 75.25
            + 50.00
            + 1000.00
            + 500.75
            + 200.25
            + 0.01
            + 100.00
            + 75.50
            + 50.25
        )
        assert abs(result - expected) < 0.01

    def test_percentage_value_conversion(self, order_client):
        """Test conversion of percentage values to decimals."""
        positions = [
            {"usd_value": "50%"},  # Should become 0.5
            {"usd_value": "100%"},  # Should become 1.0
            {"usd_value": "25.5%"},  # Should become 0.255
            {"usd_value": "200%"},  # Should become 2.0
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        expected = 0.5 + 1.0 + 0.255 + 2.0
        assert abs(result - expected) < 0.001

    def test_accounting_format_negative_values(self, order_client):
        """Test handling of accounting format negative values (parentheses)."""
        positions = [
            {"usd_value": "(100.50)"},  # Should become -100.50
            {"usd_value": "(25.75)"},  # Should become -25.75
            {"usd_value": "50.00"},  # Positive value
            {"usd_value": "(0.25)"},  # Should become -0.25
        ]

        with patch.object(order_client, "get_positions", return_value=positions):
            result = order_client.exposure_usd()

        expected = -100.50 - 25.75 + 50.00 - 0.25
        assert abs(result - expected) < 0.01


class TestHelperMethods:
    """Test individual helper methods."""

    def test_normalize_position_to_dict(self, order_client):
        """Test position normalization to dictionary."""
        # Test dataclass
        position = MockPosition(usd_value=100.0, size=10.0, symbol="BTC")
        result = order_client._normalize_position_to_dict(position)
        assert result == {"usd_value": 100.0, "size": 10.0, "symbol": "BTC"}

        # Test dictionary
        position = {"usd_value": 100.0}
        result = order_client._normalize_position_to_dict(position)
        assert result == {"usd_value": 100.0}

        # Test named tuple
        position = PositionTuple(usd_value=100.0, quantity=10, market="BTCUSD")
        result = order_client._normalize_position_to_dict(position)
        assert result == {"usd_value": 100.0, "quantity": 10, "market": "BTCUSD"}

        # Test object (only includes non-None attributes)
        position = MockPositionObject(usd_value=100.0)
        result = order_client._normalize_position_to_dict(position)
        assert result == {"usd_value": 100.0}

    def test_parse_numeric_value(self, order_client):
        """Test numeric value parsing."""
        # Test various formats
        assert order_client._parse_numeric_value(100) == 100.0
        assert order_client._parse_numeric_value(100.5) == 100.5
        assert order_client._parse_numeric_value("100.5") == 100.5
        assert order_client._parse_numeric_value("$100.50") == 100.5
        assert order_client._parse_numeric_value("1,000.25") == 1000.25
        assert order_client._parse_numeric_value("(50.00)") == -50.0
        assert order_client._parse_numeric_value("25%") == 0.25
        assert order_client._parse_numeric_value(True) == 1.0
        assert order_client._parse_numeric_value(False) == 0.0

        # Test invalid values
        assert order_client._parse_numeric_value(None) is None
        assert order_client._parse_numeric_value("") is None
        assert order_client._parse_numeric_value("invalid") is None
        assert order_client._parse_numeric_value(float("nan")) is None

    def test_extract_nested_value(self, order_client):
        """Test nested value extraction."""
        data = {
            "level1": {"level2": {"usd_value": 100.0}},
            "USD_VALUE": 200.0,
            "direct": 50.0,
        }

        # Test direct access
        assert order_client._extract_nested_value(data, "direct") == 50.0

        # Test case-insensitive access
        assert order_client._extract_nested_value(data, "usd_value") == 200.0

        # Test nested access
        assert order_client._extract_nested_value(data, "level1") == {
            "level2": {"usd_value": 100.0}
        }

    def test_sanitize_position_data_for_logging(self, order_client):
        """Test position data sanitization."""
        # Test sensitive data redaction
        position = {
            "usd_value": 100.0,
            "private_key": "secret123",
            "normal_field": "normal_value",
        }

        result = order_client._sanitize_position_data_for_logging(position)
        assert "[REDACTED]" in result
        assert "secret123" not in result
        assert "normal_value" in result

        # Test truncation of long strings
        position = {"long_field": "a" * 150}

        result = order_client._sanitize_position_data_for_logging(position)
        assert "..." in result
        assert len(result) < 500  # Should be truncated


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
