import os

import pytest
from pydantic import ValidationError

from inkedup_bot.config import BotConfig


@pytest.fixture(autouse=True)
def clear_env_vars():
    # Clear relevant environment variables before each test
    os.environ.pop("PUBLIC_KEY", None)
    os.environ.pop("PRIVATE_KEY", None)
    os.environ.pop("POLYMARKET_API_BASE", None)
    os.environ.pop("POLYMARKET_WS_URL", None)
    os.environ.pop("WS_ENABLED", None)


def test_missing_required_env_vars():
    """Test that BotConfig raises an error if required environment variables are missing."""
    with pytest.raises(ValidationError) as excinfo:
        BotConfig()
    assert "PUBLIC_KEY" in str(excinfo.value)
    assert "PRIVATE_KEY" in str(excinfo.value)


def test_invalid_key_format():
    """Test that BotConfig raises an error for invalid key formats."""
    os.environ["PUBLIC_KEY"] = "0x123"
    os.environ["PRIVATE_KEY"] = "0x456"
    with pytest.raises(ValidationError) as excinfo:
        BotConfig()
    assert "PUBLIC_KEY must be exactly 42 characters" in str(excinfo.value)
    assert "PRIVATE_KEY must be exactly 66 characters" in str(excinfo.value)

    os.environ["PUBLIC_KEY"] = "0x" + "g" * 40
    os.environ["PRIVATE_KEY"] = "0x" + "h" * 64
    with pytest.raises(ValidationError) as excinfo:
        BotConfig()
    assert "PUBLIC_KEY must contain only valid hexadecimal characters" in str(
        excinfo.value
    )
    assert "PRIVATE_KEY must contain only valid hexadecimal characters" in str(
        excinfo.value
    )


def test_invalid_url_format():
    """Test that BotConfig raises an error for invalid URL formats."""
    os.environ["PUBLIC_KEY"] = "0x" + "a" * 40
    os.environ["PRIVATE_KEY"] = "0x" + "b" * 64
    os.environ["POLYMARKET_API_BASE"] = "ftp://invalid-url"
    with pytest.raises(ValidationError):
        BotConfig()


def test_websocket_config_validation():
    """Test the validation of WebSocket configuration."""
    os.environ["PUBLIC_KEY"] = "0x" + "a" * 40
    os.environ["PRIVATE_KEY"] = "0x" + "b" * 64
    os.environ["WS_ENABLED"] = "true"
    os.environ["POLYMARKET_WS_URL"] = "http://invalid-ws-url"
    with pytest.raises(ValidationError) as excinfo:
        BotConfig()
    assert "ws_url must be a WebSocket URL" in str(excinfo.value)


def test_spread_constraints():
    """Test the validation of spread constraints."""
    os.environ["PUBLIC_KEY"] = "0x" + "a" * 40
    os.environ["PRIVATE_KEY"] = "0x" + "b" * 64
    with pytest.raises(ValidationError) as excinfo:
        BotConfig(min_spread_bps=100, max_spread_bps=50)
    assert "min_spread_bps must be less than max_spread_bps" in str(excinfo.value)


def test_complement_arb_constraints():
    """Test the validation of complement arbitrage constraints."""
    os.environ["PUBLIC_KEY"] = "0x" + "a" * 40
    os.environ["PRIVATE_KEY"] = "0x" + "b" * 64
    with pytest.raises(ValidationError) as excinfo:
        BotConfig(complement_arb_min_deviation=0.5, complement_arb_max_deviation=0.1)
    assert (
        "complement_arb_min_deviation must be less than complement_arb_max_deviation"
        in str(excinfo.value)
    )

    with pytest.raises(ValidationError) as excinfo:
        BotConfig(complement_arb_base_size=100, complement_arb_max_size=50)
    assert (
        "complement_arb_base_size must be less than or equal to complement_arb_max_size"
        in str(excinfo.value)
    )


def test_liquidity_thresholds():
    """Test the validation of liquidity thresholds."""
    os.environ["PUBLIC_KEY"] = "0x" + "a" * 40
    os.environ["PRIVATE_KEY"] = "0x" + "b" * 64
    with pytest.raises(ValidationError) as excinfo:
        BotConfig(liquidity_min_price_threshold=0.8, liquidity_max_price_threshold=0.5)
    assert (
        "liquidity_min_price_threshold must be less than liquidity_max_price_threshold"
        in str(excinfo.value)
    )
