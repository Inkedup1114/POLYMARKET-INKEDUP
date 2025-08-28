"""
Comprehensive tests for WebSocket message handlers.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from inkedup_bot.handlers.base_handler import BaseMessageHandler
from inkedup_bot.handlers.book_handler import BookHandler
from inkedup_bot.handlers.order_handler import OrderHandler
from inkedup_bot.handlers.price_handler import PriceHandler
from inkedup_bot.handlers.trade_handler import TradeHandler
from inkedup_bot.models.ws_messages import (
    BookMessage,
    OrderMessage,
    OrderSide,
    OrderStatus,
    OrderType,
    PriceChangeMessage,
    TradeMessage,
)


# Mock message classes for testing
class MockWebSocketMessage:
    def __init__(self, msg_type: str, timestamp: datetime = None):
        self.type = msg_type
        self.timestamp = timestamp or datetime.utcnow()


class TestBaseMessageHandler:
    """Test suite for BaseMessageHandler."""

    def test_initialization(self):
        """Test handler initialization."""

        # Create a concrete implementation for testing
        class TestHandler(BaseMessageHandler):
            async def _handle_message(self, message):
                return {"processed": True}

        handler = TestHandler("TestHandler")
        assert handler.name == "TestHandler"
        assert handler.message_count == 0
        assert handler.error_count == 0
        assert len(handler._callbacks) == 0

    def test_add_remove_callback(self):
        """Test callback management."""

        class TestHandler(BaseMessageHandler):
            async def _handle_message(self, message):
                return {"processed": True}

        handler = TestHandler("TestHandler")

        async def callback1(data):
            pass

        async def callback2(data):
            pass

        # Add callbacks
        handler.add_callback(callback1)
        handler.add_callback(callback2)
        assert len(handler._callbacks) == 2

        # Remove callback
        assert handler.remove_callback(callback1) is True
        assert len(handler._callbacks) == 1

        # Try to remove non-existent callback
        assert handler.remove_callback(callback1) is False
        assert len(handler._callbacks) == 1

    @pytest.mark.asyncio
    async def test_process_message_success(self):
        """Test successful message processing."""

        class TestHandler(BaseMessageHandler):
            async def _handle_message(self, message):
                return {"type": message.type, "processed": True}

        handler = TestHandler("TestHandler")
        message = MockWebSocketMessage("test")

        result = await handler.process_message(message)
        assert result is True
        assert handler.message_count == 1
        assert handler.error_count == 0

    @pytest.mark.asyncio
    async def test_process_message_validation_failure(self):
        """Test message processing with validation failure."""

        class TestHandler(BaseMessageHandler):
            async def _handle_message(self, message):
                return {"processed": True}

        handler = TestHandler("TestHandler")

        # Test with None message
        result = await handler.process_message(None)
        assert result is False
        assert handler.error_count == 1

    @pytest.mark.asyncio
    async def test_process_message_handler_error(self):
        """Test message processing with handler error."""

        class TestHandler(BaseMessageHandler):
            async def _handle_message(self, message):
                raise ValueError("Test error")

        handler = TestHandler("TestHandler")
        message = MockWebSocketMessage("test")

        result = await handler.process_message(message)
        assert result is False
        assert handler.error_count == 1

    @pytest.mark.asyncio
    async def test_process_message_with_callbacks(self):
        """Test message processing with callbacks."""

        class TestHandler(BaseMessageHandler):
            async def _handle_message(self, message):
                return {"processed": True}

        handler = TestHandler("TestHandler")
        message = MockWebSocketMessage("test")

        # Add successful callback
        callback_called = False
        callback_data = None

        async def success_callback(data):
            nonlocal callback_called, callback_data
            callback_called = True
            callback_data = data

        handler.add_callback(success_callback)

        result = await handler.process_message(message)
        assert result is True
        assert callback_called is True
        assert callback_data == {"processed": True}

    @pytest.mark.asyncio
    async def test_process_message_callback_error(self):
        """Test message processing with callback error."""

        class TestHandler(BaseMessageHandler):
            async def _handle_message(self, message):
                return {"processed": True}

        handler = TestHandler("TestHandler")
        message = MockWebSocketMessage("test")

        # Add failing callback
        async def failing_callback(data):
            raise Exception("Callback error")

        handler.add_callback(failing_callback)

        # Should still succeed even if callback fails
        result = await handler.process_message(message)
        assert result is True

    def test_validate_message_timestamp(self):
        """Test message timestamp validation."""

        class TestHandler(BaseMessageHandler):
            async def _handle_message(self, message):
                return {"processed": True}

        handler = TestHandler("TestHandler")

        # Test with current timestamp
        message = MockWebSocketMessage("test", datetime.utcnow())
        assert handler._validate_message_timestamp(message) is True

        # Test with old timestamp
        old_time = datetime(2020, 1, 1)
        old_message = MockWebSocketMessage("test", old_time)
        assert handler._validate_message_timestamp(old_message) is False

    def test_not_implemented_error(self):
        """Test that abstract method raises NotImplementedError."""

        # Python's ABC prevents instantiation of incomplete classes
        with pytest.raises(TypeError) as exc_info:

            class IncompleteHandler(BaseMessageHandler):
                pass  # Don't implement _handle_message

            IncompleteHandler("Incomplete")

        # Verify the error message mentions the missing abstract method
        assert "_handle_message" in str(exc_info.value)


class TestBookHandler:
    """Test suite for BookHandler."""

    def test_initialization(self):
        """Test BookHandler initialization."""
        handler = BookHandler()
        assert handler.name == "BookHandler"
        assert handler.supports_message_type("book") is True
        assert handler.supports_message_type("order") is False
        assert "book" in handler.get_supported_message_types()

    @pytest.mark.asyncio
    async def test_handle_book_message(self):
        """Test handling valid book message."""
        handler = BookHandler()

        # Mock BookMessage
        book_message = MagicMock(spec=BookMessage)
        book_message.market = "0x123"
        book_message.timestamp = datetime.utcnow()
        book_message.bids = [MagicMock(price=Decimal("0.6"), size=Decimal("100"))]
        book_message.asks = [MagicMock(price=Decimal("0.65"), size=Decimal("50"))]
        book_message.get_best_bid.return_value = Decimal("0.6")
        book_message.get_best_ask.return_value = Decimal("0.65")
        book_message.get_spread.return_value = Decimal("0.05")

        result = await handler._handle_message(book_message)

        assert result["market"] == "0x123"
        assert result["best_bid"] == Decimal("0.6")
        assert result["best_ask"] == Decimal("0.65")
        assert result["spread"] == Decimal("0.05")
        assert len(result["bids"]) == 1
        assert len(result["asks"]) == 1

    def test_validate_book_message_success(self):
        """Test successful book message validation."""
        handler = BookHandler()

        book_message = MagicMock(spec=BookMessage)
        book_message.type = "book"
        book_message.timestamp = datetime.utcnow()
        book_message.market = "0x123"
        book_message.bids = [MagicMock()]
        book_message.asks = [MagicMock()]

        assert handler._validate_message(book_message) is True

    def test_validate_book_message_failure(self):
        """Test book message validation failure."""
        handler = BookHandler()

        # Test with wrong message type
        order_message = MagicMock()
        order_message.type = "order"
        order_message.timestamp = datetime.utcnow()

        assert handler._validate_message(order_message) is False


class TestOrderHandler:
    """Test suite for OrderHandler."""

    def test_initialization(self):
        """Test OrderHandler initialization."""
        handler = OrderHandler()
        assert handler.name == "OrderHandler"
        assert handler.supports_message_type("order") is True
        assert handler.supports_message_type("book") is False
        assert "order" in handler.get_supported_message_types()

    @pytest.mark.asyncio
    async def test_handle_order_message(self):
        """Test handling valid order message."""
        handler = OrderHandler()

        # Mock OrderMessage
        order_message = MagicMock(spec=OrderMessage)
        order_message.order_id = "order123"
        order_message.market = "0x123"
        order_message.owner = "0xabc"
        order_message.side = OrderSide.BUY
        order_message.price = Decimal("0.6")
        order_message.size = Decimal("100")
        order_message.status = OrderStatus.OPEN
        order_message.order_type = OrderType.LIMIT
        order_message.timestamp = datetime.utcnow()
        order_message.dict.return_value = {"raw": "data"}

        result = await handler._handle_message(order_message)

        assert result["order_id"] == "order123"
        assert result["market"] == "0x123"
        assert result["side"] == OrderSide.BUY.value
        assert result["price"] == Decimal("0.6")
        assert result["size"] == Decimal("100")
        assert result["status"] == OrderStatus.OPEN.value

    def test_validate_order_message_success(self):
        """Test successful order message validation."""
        handler = OrderHandler()

        order_message = MagicMock(spec=OrderMessage)
        order_message.type = "order"
        order_message.timestamp = datetime.utcnow()
        order_message.order_id = "order123"
        order_message.market = "0x123"
        order_message.owner = "0xabc"
        order_message.side = OrderSide.BUY
        order_message.price = Decimal("0.6")
        order_message.size = Decimal("100")
        order_message.status = OrderStatus.OPEN

        assert handler._validate_message(order_message) is True

    def test_validate_order_message_invalid_price(self):
        """Test order message validation with invalid price."""
        handler = OrderHandler()

        order_message = MagicMock(spec=OrderMessage)
        order_message.type = "order"
        order_message.timestamp = datetime.utcnow()
        order_message.order_id = "order123"
        order_message.market = "0x123"
        order_message.owner = "0xabc"
        order_message.side = OrderSide.BUY
        order_message.price = Decimal("-0.6")  # Invalid negative price
        order_message.size = Decimal("100")
        order_message.status = OrderStatus.OPEN

        assert handler._validate_message(order_message) is False


class TestPriceHandler:
    """Test suite for PriceHandler."""

    def test_initialization(self):
        """Test PriceHandler initialization."""
        handler = PriceHandler()
        assert handler.name == "PriceHandler"
        assert handler.supports_message_type("price_change") is True
        assert handler.supports_message_type("last_trade_price") is True
        assert handler.supports_message_type("tick_size_change") is True
        assert handler.supports_message_type("book") is False
        assert len(handler.get_supported_message_types()) == 3

    @pytest.mark.asyncio
    async def test_handle_price_change_message(self):
        """Test handling price change message."""
        handler = PriceHandler()

        price_message = MagicMock(spec=PriceChangeMessage)
        price_message.market = "0x123"
        price_message.price = Decimal("0.6")
        price_message.change = Decimal("0.05")
        price_message.percentage = Decimal("9.09")
        price_message.timestamp = datetime.utcnow()

        result = await handler._handle_message(price_message)

        assert result["type"] == "price_change"
        assert result["market"] == "0x123"
        assert result["price"] == Decimal("0.6")
        assert result["change"] == Decimal("0.05")
        assert result["percentage"] == Decimal("9.09")

    def test_validate_price_change_message_success(self):
        """Test successful price change message validation."""
        handler = PriceHandler()

        price_message = MagicMock(spec=PriceChangeMessage)
        price_message.type = "price_change"
        price_message.timestamp = datetime.utcnow()
        price_message.market = "0x123"
        price_message.price = Decimal("0.6")
        price_message.change = Decimal("0.05")
        price_message.percentage = Decimal("9.09")

        assert handler._validate_message(price_message) is True

    def test_validate_price_change_message_invalid_price(self):
        """Test price change message validation with invalid price."""
        handler = PriceHandler()

        price_message = MagicMock(spec=PriceChangeMessage)
        price_message.type = "price_change"
        price_message.timestamp = datetime.utcnow()
        price_message.market = "0x123"
        price_message.price = Decimal("-0.6")  # Invalid negative price
        price_message.change = Decimal("0.05")
        price_message.percentage = Decimal("9.09")

        assert handler._validate_message(price_message) is False


class TestTradeHandler:
    """Test suite for TradeHandler."""

    def test_initialization(self):
        """Test TradeHandler initialization."""
        handler = TradeHandler()
        assert handler.name == "TradeHandler"
        assert handler.supports_message_type("trade") is True
        assert handler.supports_message_type("book") is False
        assert "trade" in handler.get_supported_message_types()

    @pytest.mark.asyncio
    async def test_handle_trade_message(self):
        """Test handling valid trade message."""
        handler = TradeHandler()

        trade_message = MagicMock(spec=TradeMessage)
        trade_message.market = "0x123"
        trade_message.transaction_hash = "0xdef"
        trade_message.taker_order_id = "taker123"
        trade_message.timestamp = datetime.utcnow()
        trade_message.maker_orders = [
            {
                "orderId": "maker1",
                "owner": "0xuser1",
                "price": "0.6",
                "size": "100",
                "side": "buy",
            }
        ]

        result = await handler._handle_message(trade_message)

        assert result["market"] == "0x123"
        assert result["transaction_hash"] == "0xdef"
        assert result["taker_order_id"] == "taker123"
        assert result["trade_count"] == 1
        assert len(result["maker_orders"]) == 1
        assert result["total_size"] == Decimal("100")

    def test_validate_trade_message_success(self):
        """Test successful trade message validation."""
        handler = TradeHandler()

        trade_message = MagicMock(spec=TradeMessage)
        trade_message.type = "trade"
        trade_message.timestamp = datetime.utcnow()
        trade_message.market = "0x123"
        trade_message.transaction_hash = "0xdef"
        trade_message.taker_order_id = "taker123"
        trade_message.maker_orders = [{"orderId": "maker1"}]

        assert handler._validate_message(trade_message) is True

    def test_validate_trade_message_empty_maker_orders(self):
        """Test trade message validation with empty maker orders."""
        handler = TradeHandler()

        trade_message = MagicMock(spec=TradeMessage)
        trade_message.type = "trade"
        trade_message.timestamp = datetime.utcnow()
        trade_message.market = "0x123"
        trade_message.transaction_hash = "0xdef"
        trade_message.taker_order_id = "taker123"
        trade_message.maker_orders = []  # Empty list

        # Should still pass validation (warning logged but not failed)
        assert handler._validate_message(trade_message) is True


class TestHandlerIntegration:
    """Integration tests for handler interactions."""

    @pytest.mark.asyncio
    async def test_handler_routing(self):
        """Test that handlers correctly route different message types."""

        # Create all handlers
        handlers = [BookHandler(), OrderHandler(), PriceHandler(), TradeHandler()]

        # Test message type routing
        message_types = ["book", "order", "price_change", "trade"]

        for msg_type in message_types:
            supporting_handlers = [
                h for h in handlers if h.supports_message_type(msg_type)
            ]

            if msg_type == "book":
                assert len(supporting_handlers) == 1
                assert isinstance(supporting_handlers[0], BookHandler)
            elif msg_type == "order":
                assert len(supporting_handlers) == 1
                assert isinstance(supporting_handlers[0], OrderHandler)
            elif msg_type == "price_change":
                assert len(supporting_handlers) == 1
                assert isinstance(supporting_handlers[0], PriceHandler)
            elif msg_type == "trade":
                assert len(supporting_handlers) == 1
                assert isinstance(supporting_handlers[0], TradeHandler)

    def test_all_handlers_implement_required_methods(self):
        """Test that all handlers implement required methods."""

        handlers = [BookHandler(), OrderHandler(), PriceHandler(), TradeHandler()]

        for handler in handlers:
            # Check that all handlers implement required methods
            assert hasattr(handler, "_handle_message")
            assert hasattr(handler, "supports_message_type")
            assert hasattr(handler, "get_supported_message_types")
            assert hasattr(handler, "_validate_message")

            # Check that they return proper types
            supported_types = handler.get_supported_message_types()
            assert isinstance(supported_types, list)
            assert len(supported_types) > 0

            # Check that supports_message_type works for supported types
            for msg_type in supported_types:
                assert handler.supports_message_type(msg_type) is True
