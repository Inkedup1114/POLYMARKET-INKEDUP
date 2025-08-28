"""
Comprehensive tests for the unified WebSocket manager.

This module provides a complete test suite for the Polymarket WebSocket system.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inkedup_bot.auth import AuthManager
from inkedup_bot.ws_manager import WebSocketManager


class TestWebSocketManagerUnit:
    """Unit tests for WebSocketManager."""

    @pytest.fixture
    def auth_manager(self) -> MagicMock:
        """Create mock auth manager."""
        auth = MagicMock(spec=AuthManager)
        auth.get_auth_headers = AsyncMock(
            return_value={"Authorization": "Bearer test-token"}
        )
        auth.sign_message = AsyncMock(return_value="test-signature")
        return auth

    @pytest.fixture
    def ws_manager(self, auth_manager: MagicMock) -> WebSocketManager:
        """Create WebSocket manager instance."""
        return WebSocketManager(
            auth_manager=auth_manager,
            ws_url="wss://test-ws.polymarket.com",
            max_reconnect_attempts=3,
            reconnect_delay=0.1,
            max_reconnect_delay=1.0,
            heartbeat_interval=5.0,
        )

    @pytest.fixture
    def mock_websocket(self) -> AsyncMock:
        """Create mock WebSocket."""
        ws = AsyncMock()
        ws.send = AsyncMock()
        ws.close = AsyncMock()
        ws.ping = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_initialization(self, ws_manager: WebSocketManager) -> None:
        """Test WebSocket manager initialization."""
        assert ws_manager.is_connected is False
        assert ws_manager.is_running is False
        assert ws_manager.reconnect_attempts == 0

    @pytest.mark.asyncio
    async def test_start_stop(
        self, ws_manager: WebSocketManager, mock_websocket: AsyncMock
    ) -> None:
        """Test start and stop functionality."""
        with patch("websockets.connect", return_value=mock_websocket):
            await ws_manager.start()
            assert ws_manager.is_running is True

            await ws_manager.stop()
            assert ws_manager.is_running is False

    @pytest.mark.asyncio
    async def test_subscription_management(
        self, ws_manager: WebSocketManager, mock_websocket: AsyncMock
    ) -> None:
        """Test subscription management."""
        ws_manager.websocket = mock_websocket
        ws_manager.is_connected = True

        await ws_manager.subscribe_market("0x123", ["trade", "book"])
        await ws_manager.subscribe_user("0xuser", ["order"])

        assert len(mock_websocket.send.call_args_list) >= 2


class TestWebSocketManagerIntegration:
    """Integration tests for WebSocketManager."""

    @pytest.fixture
    def mock_server(self) -> AsyncMock:
        """Create mock WebSocket server."""
        server = AsyncMock()
        server.send = AsyncMock()
        server.close = AsyncMock()
        return server

    @pytest.mark.asyncio
    async def test_integration_flow(
        self, mock_server: AsyncMock, auth_manager: MagicMock
    ) -> None:
        """Test complete integration flow."""
        manager = WebSocketManager(
            auth_manager=auth_manager,
            ws_url="wss://test-ws.polymarket.com",
            max_reconnect_attempts=1,
            reconnect_delay=0.1,
        )

        with patch("websockets.connect", return_value=mock_server):
            await manager.start()
            await asyncio.sleep(0.1)

            await manager.subscribe_market("0x123", ["trade", "book"])
            await manager.subscribe_user("0xuser", ["order"])

            await manager.stop()


@pytest.mark.asyncio
async def test_create_ws_manager() -> None:
    """Test WebSocket manager creation."""
    auth_manager = MagicMock(spec=AuthManager)
    manager = WebSocketManager(
        auth_manager=auth_manager, ws_url="wss://test-ws.polymarket.com"
    )

    assert isinstance(manager, WebSocketManager)
    assert manager.ws_url == "wss://test-ws.polymarket.com"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
