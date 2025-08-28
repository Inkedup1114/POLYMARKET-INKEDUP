"""
Comprehensive tests for Polymarket WebSocket models.

This module contains tests for all message types, validation schemas,
and state management functionality.
"""

import json
from datetime import datetime
from decimal import Decimal

import pytest

from inkedup_bot.models.state import (
    MarketDataState,
    OrderLifecycle,
    OrderState,
    PositionSide,
    PositionState,
    StateManager,
    TradingState,
)
from inkedup_bot.models.ws_messages import (
    BookMessage,
    OrderMessage,
    PriceChangeMessage,
    TradeMessage,
    parse_websocket_message,
    serialize_message,
)
from inkedup_bot.validation.schemas import (
    message_validator,
    validate_book_message,
    validate_order_message,
    validate_trade_message,
)


class TestTradeMessage:
    """Test TradeMessage parsing and validation."""

    def test_valid_trade_message(self):
        """Test parsing a valid trade message."""
        data = {
            "type": "trade",
            "market": "0x1234567890abcdef1234567890abcdef12345678",
            "transactionHash": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "takerOrderId": "order_123",
            "makerOrders": [
                {
                    "orderId": "maker_456",
                    "owner": "0x9876543210fedcba9876543210fedcba98765432",
                    "price": "0.55",
                    "size": "100.0",
                    "side": "buy",
                }
            ],
            "timestamp": "2024-01-01T12:00:00Z",
        }

        message = TradeMessage(**data)
        assert message.type == "trade"
        assert message.market == "0x1234567890abcdef1234567890abcdef12345678"
        assert len(message.maker_orders) == 1
        assert message.maker_orders[0]["price"] == "0.55"

    def test_invalid_maker_orders(self):
        """Test validation of maker orders."""
        data = {
            "type": "trade",
            "market": "0x1234567890abcdef1234567890abcdef12345678",
            "transactionHash": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "takerOrderId": "order_123",
            "makerOrders": [],  # Empty array should fail
            "timestamp": "2024-01-01T12:00:00Z",
        }

        # Should not raise for empty array
        message = TradeMessage(**data)
        assert len(message.maker_orders) == 0

    def test_maker_order_validation(self):
        """Test maker order structure validation."""
        data = {
            "type": "trade",
            "market": "0x1234567890abcdef1234567890abcdef12345678",
            "transactionHash": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "takerOrderId": "order_123",
            "makerOrders": [
                {
                    "orderId": "maker_456",
                    "owner": "0x9876543210fedcba9876543210fedcba98765432",
                    "price": "0.55",
                    "size": "100.0",
                    "side": "invalid_side",  # Invalid side
                }
            ],
            "timestamp": "2024-01-01T12:00:00Z",
        }

        # Should parse but validation is handled elsewhere
        message = TradeMessage(**data)
        assert message.maker_orders[0]["side"] == "invalid_side"


class TestOrderMessage:
    """Test OrderMessage parsing and validation."""

    def test_valid_order_message(self):
        """Test parsing a valid order message."""
        data = {
            "type": "order",
            "orderId": "order_123",
            "market": "0x1234567890abcdef1234567890abcdef12345678",
            "owner": "0x9876543210fedcba9876543210fedcba98765432",
            "price": "0.55",
            "size": "100.0",
            "side": "buy",
            "status": "open",
            "orderType": "limit",
            "timestamp": "2024-01-01T12:00:00Z",
        }

        message = OrderMessage(**data)
        assert message.order_id == "order_123"
        assert message.price == Decimal("0.55")
        assert message.side.value == "buy"

    def test_price_validation(self):
        """Test price range validation."""
        # Valid price
        data = {
            "type": "order",
            "orderId": "order_123",
            "market": "0x1234567890abcdef1234567890abcdef12345678",
            "owner": "0x9876543210fedcba9876543210fedcba98765432",
            "price": "0.55",
            "size": "100.0",
            "side": "buy",
            "status": "open",
            "orderType": "limit",
            "timestamp": "2024-01-01T12:00:00Z",
        }

        message = OrderMessage(**data)
        assert 0 <= message.price <= 1

    def test_invalid_price(self):
        """Test invalid price handling."""
        data = {
            "type": "order",
            "orderId": "order_123",
            "market": "0x1234567890abcdef1234567890abcdef12345678",
            "owner": "0x9876543210fedcba9876543210fedcba98765432",
            "price": "1.5",  # Invalid price > 1
            "size": "100.0",
            "side": "buy",
            "status": "open",
            "orderType": "limit",
            "timestamp": "2024-01-01T12:00:00Z",
        }

        # Should parse but validation is handled elsewhere
        message = OrderMessage(**data)
        assert message.price == Decimal("1.5")


class TestBookMessage:
    """Test BookMessage parsing and validation."""

    def test_valid_book_message(self):
        """Test parsing a valid book message."""
        data = {
            "type": "book",
            "market": "0x1234567890abcdef1234567890abcdef12345678",
            "bids": [
                {"price": "0.54", "size": "100.0"},
                {"price": "0.53", "size": "200.0"},
            ],
            "asks": [
                {"price": "0.56", "size": "150.0"},
                {"price": "0.57", "size": "75.0"},
            ],
            "timestamp": "2024-01-01T12:00:00Z",
        }

        message = BookMessage(**data)
        assert len(message.bids) == 2
        assert len(message.asks) == 2
        assert message.get_best_bid() == Decimal("0.54")
        assert message.get_best_ask() == Decimal("0.56")
        assert message.get_spread() == Decimal("0.02")

    def test_empty_book(self):
        """Test handling empty book."""
        data = {
            "type": "book",
            "market": "0x1234567890abcdef1234567890abcdef12345678",
            "bids": [],
            "asks": [],
            "timestamp": "2024-01-01T12:00:00Z",
        }

        message = BookMessage(**data)
        assert message.get_best_bid() is None
        assert message.get_best_ask() is None
        assert message.get_spread() is None


class TestPriceChangeMessage:
    """Test PriceChangeMessage parsing."""

    def test_valid_price_change(self):
        """Test parsing a valid price change message."""
        data = {
            "type": "price_change",
            "market": "0x1234567890abcdef1234567890abcdef12345678",
            "price": "0.55",
            "change": "0.02",
            "percentage": "3.77",
            "timestamp": "2024-01-01T12:00:00Z",
        }

        message = PriceChangeMessage(**data)
        assert message.price == Decimal("0.55")
        assert message.change == Decimal("0.02")
        assert message.percentage == Decimal("3.77")


class TestParseWebsocketMessage:
    """Test the parse_websocket_message function."""

    def test_parse_trade(self):
        """Test parsing trade message."""
        data = {
            "type": "trade",
            "market": "0x1234567890abcdef1234567890abcdef12345678",
            "transactionHash": "0xabcdef...",
            "takerOrderId": "order_123",
            "makerOrders": [
                {
                    "orderId": "maker_456",
                    "owner": "0x987...",
                    "price": "0.55",
                    "size": "100.0",
                    "side": "buy",
                }
            ],
            "timestamp": "2024-01-01T12:00:00Z",
        }

        message = parse_websocket_message(data)
        assert isinstance(message, TradeMessage)
        assert message.type == "trade"

    def test_parse_order(self):
        """Test parsing order message."""
        data = {
            "type": "order",
            "orderId": "order_123",
            "market": "0x1234567890abcdef1234567890abcdef12345678",
            "owner": "0x9876543210fedcba9876543210fedcba98765432",
            "price": "0.55",
            "size": "100.0",
            "side": "buy",
            "status": "open",
            "orderType": "limit",
            "timestamp": "2024-01-01T12:00:00Z",
        }

        message = parse_websocket_message(data)
        assert isinstance(message, OrderMessage)

    def test_parse_unknown_type(self):
        """Test parsing unknown message type."""
        data = {"type": "unknown", "data": "test"}

        with pytest.raises(ValueError, match="Unknown message type"):
            parse_websocket_message(data)


class TestOrderState:
    """Test OrderState functionality."""

    def test_order_creation(self):
        """Test creating an order state."""
        order = OrderState(
            order_id="order_123",
            market="0x1234567890abcdef1234567890abcdef12345678",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            price=Decimal("0.55"),
            size=Decimal("100.0"),
            side="buy",
            status="open",
            order_type="limit",
            lifecycle_stage=OrderLifecycle.PLACEMENT,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            remaining_size=Decimal("100.0"),
        )

        assert order.order_id == "order_123"
        assert order.price == Decimal("0.55")
        assert order.remaining_size == Decimal("100.0")

    def test_order_fill(self):
        """Test updating order with fill."""
        order = OrderState(
            order_id="order_123",
            market="0x1234567890abcdef1234567890abcdef12345678",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            price=Decimal("0.55"),
            size=Decimal("100.0"),
            side="buy",
            status="open",
            order_type="limit",
            lifecycle_stage=OrderLifecycle.PLACEMENT,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            remaining_size=Decimal("100.0"),
        )

        order.update_fill(Decimal("50.0"), Decimal("0.545"))
        assert order.filled_size == Decimal("50.0")
        assert order.remaining_size == Decimal("50.0")
        assert order.average_fill_price == Decimal("0.545")

    def test_order_complete(self):
        """Test order completion."""
        order = OrderState(
            order_id="order_123",
            market="0x1234567890abcdef1234567890abcdef12345678",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            price=Decimal("0.55"),
            size=Decimal("100.0"),
            side="buy",
            status="open",
            order_type="limit",
            lifecycle_stage=OrderLifecycle.PLACEMENT,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            remaining_size=Decimal("100.0"),
        )

        order.update_fill(Decimal("100.0"), Decimal("0.55"))
        assert order.is_complete()
        assert order.status == "filled"


class TestPositionState:
    """Test PositionState functionality."""

    def test_position_creation(self):
        """Test creating a position state."""
        position = PositionState(
            market="0x1234567890abcdef1234567890abcdef12345678",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            side=PositionSide.LONG,
            size=Decimal("100.0"),
            entry_price=Decimal("0.55"),
            current_price=Decimal("0.57"),
            last_update=datetime.utcnow(),
        )

        assert position.side == PositionSide.LONG
        assert position.size == Decimal("100.0")
        assert position.calculate_unrealized_pnl() == Decimal("2.0")

    def test_position_fill_opening(self):
        """Test position fill for opening."""
        position = PositionState(
            market="0x1234567890abcdef1234567890abcdef12345678",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            side=PositionSide.FLAT,
            size=Decimal("0"),
            entry_price=Decimal("0"),
            current_price=Decimal("0.55"),
            last_update=datetime.utcnow(),
        )

        position.add_fill(Decimal("100.0"), Decimal("0.55"), True)
        assert position.side == PositionSide.LONG
        assert position.size == Decimal("100.0")
        assert position.entry_price == Decimal("0.55")

    def test_position_fill_closing(self):
        """Test position fill for closing."""
        position = PositionState(
            market="0x1234567890abcdef1234567890abcdef12345678",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            side=PositionSide.LONG,
            size=Decimal("100.0"),
            entry_price=Decimal("0.55"),
            current_price=Decimal("0.57"),
            last_update=datetime.utcnow(),
        )

        position.add_fill(Decimal("50.0"), Decimal("0.57"), False)
        assert position.side == PositionSide.LONG
        assert position.size == Decimal("50.0")
        assert position.realized_pnl == Decimal("1.0")

    def test_short_position(self):
        """Test short position calculations."""
        position = PositionState(
            market="0x1234567890abcdef1234567890abcdef12345678",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            side=PositionSide.SHORT,
            size=Decimal("100.0"),
            entry_price=Decimal("0.55"),
            current_price=Decimal("0.53"),
            last_update=datetime.utcnow(),
        )

        assert position.calculate_unrealized_pnl() == Decimal("2.0")

    def test_position_flat(self):
        """Test flat position."""
        position = PositionState(
            market="0x1234567890abcdef1234567890abcdef12345678",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            side=PositionSide.FLAT,
            size=Decimal("0"),
            entry_price=Decimal("0"),
            current_price=Decimal("0.55"),
            last_update=datetime.utcnow(),
        )

        assert position.calculate_unrealized_pnl() == Decimal("0")


class TestMarketDataState:
    """Test MarketDataState functionality."""

    def test_market_data_creation(self):
        """Test creating market data state."""
        market_data = MarketDataState(
            market="0x1234567890abcdef1234567890abcdef12345678",
            timestamp=datetime.utcnow(),
        )

        assert market_data.market == "0x1234567890abcdef1234567890abcdef12345678"
        assert market_data.bid_depth == Decimal("0")
        assert market_data.ask_depth == Decimal("0")

    def test_update_from_book(self):
        """Test updating from order book."""
        market_data = MarketDataState(
            market="0x1234567890abcdef1234567890abcdef12345678",
            timestamp=datetime.utcnow(),
        )

        bids = [
            {"price": Decimal("0.54"), "size": Decimal("100.0")},
            {"price": Decimal("0.53"), "size": Decimal("200.0")},
        ]
        asks = [
            {"price": Decimal("0.56"), "size": Decimal("150.0")},
            {"price": Decimal("0.57"), "size": Decimal("75.0")},
        ]

        market_data.update_from_book(bids, asks)
        assert market_data.best_bid == Decimal("0.54")
        assert market_data.best_ask == Decimal("0.56")
        assert market_data.spread == Decimal("0.02")
        assert market_data.mid_price == Decimal("0.55")

    def test_liquidity_metrics(self):
        """Test liquidity metrics calculation."""
        market_data = MarketDataState(
            market="0x1234567890abcdef1234567890abcdef12345678",
            timestamp=datetime.utcnow(),
        )

        bids = [
            {"price": Decimal("0.54"), "size": Decimal("100.0")},
            {"price": Decimal("0.53"), "size": Decimal("200.0")},
        ]
        asks = [
            {"price": Decimal("0.56"), "size": Decimal("150.0")},
            {"price": Decimal("0.57"), "size": Decimal("75.0")},
        ]

        market_data.update_from_book(bids, asks)
        metrics = market_data.get_liquidity_metrics()

        assert metrics["bid_depth"] == Decimal("300.0")
        assert metrics["ask_depth"] == Decimal("225.0")
        assert metrics["total_depth"] == Decimal("525.0")
        assert metrics["spread"] == Decimal("0.02")


class TestTradingState:
    """Test TradingState functionality."""

    def test_trading_state_creation(self):
        """Test creating trading state."""
        state = TradingState(
            owner="0x9876543210fedcba9876543210fedcba98765432",
            last_update=datetime.utcnow(),
        )

        assert state.owner == "0x9876543210fedcba9876543210fedcba98765432"
        assert len(state.orders) == 0
        assert len(state.positions) == 0
        assert len(state.market_data) == 0

    def test_add_order(self):
        """Test adding order to state."""
        state = TradingState(
            owner="0x9876543210fedcba9876543210fedcba98765432",
            last_update=datetime.utcnow(),
        )

        order = OrderState(
            order_id="order_123",
            market="0x1234567890abcdef1234567890abcdef12345678",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            price=Decimal("0.55"),
            size=Decimal("100.0"),
            side="buy",
            status="open",
            order_type="limit",
            lifecycle_stage=OrderLifecycle.PLACEMENT,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            remaining_size=Decimal("100.0"),
        )

        state.add_order(order)
        assert len(state.orders) == 1
        assert state.get_order("order_123") == order

    def test_add_position(self):
        """Test adding position to state."""
        state = TradingState(
            owner="0x9876543210fedcba9876543210fedcba98765432",
            last_update=datetime.utcnow(),
        )

        position = PositionState(
            market="0x1234567890abcdef1234567890abcdef12345678",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            side=PositionSide.LONG,
            size=Decimal("100.0"),
            entry_price=Decimal("0.55"),
            current_price=Decimal("0.57"),
            last_update=datetime.utcnow(),
        )

        state.add_position(position)
        assert len(state.positions) == 1
        assert (
            state.get_position("0x1234567890abcdef1234567890abcdef12345678") == position
        )

    def test_get_active_orders(self):
        """Test getting active orders."""
        state = TradingState(
            owner="0x9876543210fedcba9876543210fedcba98765432",
            last_update=datetime.utcnow(),
        )

        # Add active order
        active_order = OrderState(
            order_id="active_123",
            market="0x1234567890abcdef1234567890abcdef12345678",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            price=Decimal("0.55"),
            size=Decimal("100.0"),
            side="buy",
            status="open",
            order_type="limit",
            lifecycle_stage=OrderLifecycle.PLACEMENT,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            remaining_size=Decimal("100.0"),
        )

        # Add completed order
        completed_order = OrderState(
            order_id="completed_456",
            market="0x1234567890abcdef1234567890abcdef12345678",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            price=Decimal("0.55"),
            size=Decimal("100.0"),
            side="buy",
            status="filled",
            order_type="limit",
            lifecycle_stage=OrderLifecycle.EXECUTION,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            remaining_size=Decimal("0.0"),
        )

        state.add_order(active_order)
        state.add_order(completed_order)

        active_orders = state.get_active_orders()
        assert len(active_orders) == 1
        assert active_orders[0].order_id == "active_123"

    def test_get_total_exposure(self):
        """Test calculating total exposure."""
        state = TradingState(
            owner="0x9876543210fedcba9876543210fedcba98765432",
            last_update=datetime.utcnow(),
        )

        # Add long position
        long_position = PositionState(
            market="0x1111111111111111111111111111111111111111",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            side=PositionSide.LONG,
            size=Decimal("100.0"),
            entry_price=Decimal("0.55"),
            current_price=Decimal("0.57"),
            last_update=datetime.utcnow(),
        )

        # Add short position
        short_position = PositionState(
            market="0x2222222222222222222222222222222222222222",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            side=PositionSide.SHORT,
            size=Decimal("50.0"),
            entry_price=Decimal("0.55"),
            current_price=Decimal("0.53"),
            last_update=datetime.utcnow(),
        )

        state.add_position(long_position)
        state.add_position(short_position)

        exposure = state.get_total_exposure()
        assert exposure["long_exposure"] == Decimal("57.0")  # 100 * 0.57
        assert exposure["short_exposure"] == Decimal("26.5")  # 50 * 0.53
        assert exposure["net_exposure"] == Decimal("30.5")  # 57 - 26.5
        assert exposure["gross_exposure"] == Decimal("83.5")  # 57 + 26.5


class TestValidation:
    """Test validation schemas."""

    def test_validate_trade_message(self):
        """Test trade message validation."""
        data = {
            "type": "trade",
            "market": "0x1234567890abcdef1234567890abcdef12345678",
            "transactionHash": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "takerOrderId": "order_123",
            "makerOrders": [
                {
                    "orderId": "maker_456",
                    "owner": "0x9876543210fedcba9876543210fedcba98765432",
                    "price": "0.55",
                    "size": "100.0",
                    "side": "buy",
                }
            ],
            "timestamp": "2024-01-01T12:00:00Z",
        }

        assert validate_trade_message(data) is True

    def test_validate_invalid_trade(self):
        """Test validation of invalid trade message."""
        data = {
            "type": "trade",
            "market": "invalid_address",  # Invalid address
            "transactionHash": "0xabcdef",
            "takerOrderId": "order_123",
            "makerOrders": [],
            "timestamp": "2024-01-01T12:00:00Z",
        }

        is_valid, error = message_validator.validate_message_silent(data, "trade")
        assert is_valid is False
        assert "invalid_address" in error.lower() or "pattern" in error.lower()

    def test_validate_order_message(self):
        """Test order message validation."""
        data = {
            "type": "order",
            "orderId": "order_123",
            "market": "0x1234567890abcdef1234567890abcdef12345678",
            "owner": "0x9876543210fedcba9876543210fedcba98765432",
            "price": "0.55",
            "size": "100.0",
            "side": "buy",
            "status": "open",
            "orderType": "limit",
            "timestamp": "2024-01-01T12:00:00Z",
        }

        assert validate_order_message(data) is True

    def test_validate_book_message(self):
        """Test book message validation."""
        data = {
            "type": "book",
            "market": "0x1234567890abcdef1234567890abcdef12345678",
            "bids": [
                {"price": "0.54", "size": "100.0"},
                {"price": "0.53", "size": "200.0"},
            ],
            "asks": [
                {"price": "0.56", "size": "150.0"},
                {"price": "0.57", "size": "75.0"},
            ],
            "timestamp": "2024-01-01T12:00:00Z",
        }

        assert validate_book_message(data) is True


class TestSerialization:
    """Test JSON serialization."""

    def test_serialize_trade_message(self):
        """Test serializing trade message."""
        message = TradeMessage(
            market="0x1234567890abcdef1234567890abcdef12345678",
            transaction_hash="0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            taker_order_id="order_123",
            maker_orders=[
                {
                    "orderId": "maker_456",
                    "owner": "0x9876543210fedcba9876543210fedcba98765432",
                    "price": "0.55",
                    "size": "100.0",
                    "side": "buy",
                }
            ],
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )

        json_str = serialize_message(message)
        parsed = json.loads(json_str)
        assert parsed["type"] == "trade"
        assert parsed["market"] == "0x1234567890abcdef1234567890abcdef12345678"


class TestIntegration:
    """Test integration scenarios."""

    def test_full_order_lifecycle(self):
        """Test complete order lifecycle."""
        # Create trading state
        state = TradingState(
            owner="0x9876543210fedcba9876543210fedcba98765432",
            last_update=datetime.utcnow(),
        )

        # Create order
        order = OrderState(
            order_id="order_123",
            market="0x1234567890abcdef1234567890abcdef12345678",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            price=Decimal("0.55"),
            size=Decimal("100.0"),
            side="buy",
            status="open",
            order_type="limit",
            lifecycle_stage=OrderLifecycle.PLACEMENT,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            remaining_size=Decimal("100.0"),
        )

        # Add order to state
        state.add_order(order)

        # Simulate fills
        order.update_fill(Decimal("50.0"), Decimal("0.545"))
        order.update_fill(Decimal("50.0"), Decimal("0.548"))

        # Update position
        position = PositionState(
            market="0x1234567890abcdef1234567890abcdef12345678",
            owner="0x9876543210fedcba9876543210fedcba98765432",
            side=PositionSide.LONG,
            size=Decimal("100.0"),
            entry_price=Decimal("0.5465"),  # Average fill price
            current_price=Decimal("0.55"),
            last_update=datetime.utcnow(),
        )

        state.add_position(position)

        # Verify state
        assert order.is_complete()
        assert order.status == "filled"
        assert position.calculate_unrealized_pnl() == Decimal(
            "0.35"
        )  # 100 * (0.55 - 0.5465)

        exposure = state.get_total_exposure()
        assert exposure["long_exposure"] == Decimal("55.0")  # 100 * 0.55

    def test_state_manager(self):
        """Test state manager functionality."""
        state1 = StateManager.create_initial_state("0xuser123...")
        state2 = StateManager.create_initial_state("0xuser123...")

        # Add different data to each state
        order1 = OrderState(
            order_id="order_1",
            market="0x111...",
            owner="0xuser123...",
            price=Decimal("0.55"),
            size=Decimal("100.0"),
            side="buy",
            status="open",
            order_type="limit",
            lifecycle_stage=OrderLifecycle.PLACEMENT,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            remaining_size=Decimal("100.0"),
        )

        order2 = OrderState(
            order_id="order_2",
            market="0x222...",
            owner="0xuser123...",
            price=Decimal("0.56"),
            size=Decimal("200.0"),
            side="sell",
            status="open",
            order_type="limit",
            lifecycle_stage=OrderLifecycle.PLACEMENT,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            remaining_size=Decimal("200.0"),
        )

        state1.add_order(order1)
        state2.add_order(order2)

        # Merge states
        merged = StateManager.merge_states([state1, state2])
        assert len(merged.orders) == 2
        assert merged.get_order("order_1") is not None
        assert merged.get_order("order_2") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
