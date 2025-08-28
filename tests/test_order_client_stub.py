"""
Tests for the stub client functionality when py-clob-client is not available.
"""

import logging
from unittest.mock import patch

import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.order_client import StubClobClient, UnavailableClientError
from inkedup_bot.state import StateManager


def test_stub_client_raises_unavailable_error():
    """Test that stub client raises UnavailableClientError for all methods."""
    stub = StubClobClient()

    with pytest.raises(UnavailableClientError, match="py-clob-client not available"):
        stub.create_order()

    with pytest.raises(UnavailableClientError, match="py-clob-client not available"):
        stub.cancel_all()

    with pytest.raises(UnavailableClientError, match="py-clob-client not available"):
        stub.get_positions()

    with pytest.raises(UnavailableClientError, match="py-clob-client not available"):
        stub.some_other_method()


def test_order_client_with_stub():
    """Test OrderClient gracefully handles missing py-clob-client."""
    # Mock the import to simulate py-clob-client not being available
    with patch.dict("sys.modules", {"py_clob_client": None}):
        # Force re-import to trigger the stub path
        import importlib

        import inkedup_bot.order_client

        importlib.reload(inkedup_bot.order_client)

        from inkedup_bot.order_client import OrderClient

        # Create config and state
        cfg = BotConfig(api_base="https://example.com", private_key=None)
        state = StateManager(":memory:")

        # Create order client
        client = OrderClient(cfg, state)

        # Should use stub client
        assert not client.ready()

        # All methods should return gracefully
        assert client.place_limit("token123", "buy", 0.5, 100) is None
        assert client.cancel_all() == []
        assert client.get_positions() == []
        assert client.exposure_usd() == 0.0

        # Should not crash
        client.exposure_usd()


def test_order_client_debug_logging():
    """Test that debug messages are logged appropriately."""
    import io

    # Capture log output
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    logger = logging.getLogger("order_client")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    try:
        # Mock import failure
        with patch.dict("sys.modules", {"py_clob_client": None}):
            import importlib

            import inkedup_bot.order_client

            importlib.reload(inkedup_bot.order_client)

            log_output = log_capture.getvalue()
            assert "py-clob-client not available; using stub client" in log_output

    finally:
        logger.removeHandler(handler)


def test_order_client_with_private_key():
    """Test OrderClient with private key but no py-clob-client."""
    with patch.dict("sys.modules", {"py_clob_client": None}):
        import importlib

        import inkedup_bot.order_client

        importlib.reload(inkedup_bot.order_client)

        from inkedup_bot.order_client import OrderClient

        cfg = BotConfig(
            api_base="https://example.com", private_key="0x1234567890abcdef"
        )
        state = StateManager(":memory:")

        client = OrderClient(cfg, state)

        # Should still use stub client
        assert not client.ready()
        assert client.place_limit("token123", "buy", 0.5, 100) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
