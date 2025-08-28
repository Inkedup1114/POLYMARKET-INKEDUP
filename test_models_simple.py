#!/usr/bin/env python3
"""
Simple test to verify the models work correctly.
"""

import os
import sys
from datetime import datetime
from decimal import Decimal

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from inkedup_bot.models.state import (
    OrderLifecycle,
    OrderState,
    PositionSide,
    PositionState,
    TradingState,
)
from inkedup_bot.models.ws_messages import (
    BookMessage,
    OrderMessage,
    TradeMessage,
    parse_websocket_message,
)


def test_trade_message():
    """Test TradeMessage creation."""
    print("Testing TradeMessage...")

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
    print(f"✓ TradeMessage created: {message.type}")
    print(f"  Market: {message.market}")
    print(f"  Maker orders: {len(message.maker_orders)}")
    return True


def test_order_message():
    """Test OrderMessage creation."""
    print("\nTesting OrderMessage...")

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
    print(f"✓ OrderMessage created: {message.type}")
    print(f"  Order ID: {message.order_id}")
    print(f"  Price: {message.price}")
    print(f"  Side: {message.side}")
    return True


def test_book_message():
    """Test BookMessage creation."""
    print("\nTesting BookMessage...")

    data = {
        "type": "book",
        "market": "0x1234567890abcdef1234567890abcdef12345678",
        "bids": [
            {"price": "0.54", "size": "100.0"},
            {"price": "0.53", "size": "200.0"},
        ],
        "asks": [{"price": "0.56", "size": "150.0"}, {"price": "0.57", "size": "75.0"}],
        "timestamp": "2024-01-01T12:00:00Z",
    }

    message = BookMessage(**data)
    print(f"✓ BookMessage created: {message.type}")
    print(f"  Best bid: {message.get_best_bid()}")
    print(f"  Best ask: {message.get_best_ask()}")
    print(f"  Spread: {message.get_spread()}")
    return True


def test_parse_websocket_message():
    """Test message parsing."""
    print("\nTesting parse_websocket_message...")

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

    message = parse_websocket_message(data)
    print(f"✓ Parsed message type: {type(message).__name__}")
    return True


def test_order_state():
    """Test OrderState functionality."""
    print("\nTesting OrderState...")

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
        filled_size=Decimal("0"),
        remaining_size=Decimal("100.0"),
        average_fill_price=None,
        transaction_hashes=[],
    )

    print(f"✓ OrderState created: {order.order_id}")
    print(f"  Initial remaining: {order.remaining_size}")

    # Test fill
    order.update_fill(Decimal("50.0"), Decimal("0.545"))
    print(
        f"  After fill - filled: {order.filled_size}, remaining: {order.remaining_size}"
    )
    print(f"  Average fill price: {order.average_fill_price}")

    return True


def test_position_state():
    """Test PositionState functionality."""
    print("\nTesting PositionState...")

    position = PositionState(
        market="0x1234567890abcdef1234567890abcdef12345678",
        owner="0x9876543210fedcba9876543210fedcba98765432",
        side=PositionSide.LONG,
        size=Decimal("100.0"),
        entry_price=Decimal("0.55"),
        current_price=Decimal("0.57"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        last_update=datetime.utcnow(),
    )

    print(f"✓ PositionState created: {position.side}")
    print(f"  Size: {position.size}")
    print(f"  Entry price: {position.entry_price}")
    print(f"  Current price: {position.current_price}")
    print(f"  Unrealized P&L: {position.calculate_unrealized_pnl()}")

    return True


def test_trading_state():
    """Test TradingState functionality."""
    print("\nTesting TradingState...")

    state = TradingState(
        owner="0x9876543210fedcba9876543210fedcba98765432",
        last_update=datetime.utcnow(),
    )

    # Add an order
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
        filled_size=Decimal("0"),
        remaining_size=Decimal("100.0"),
        average_fill_price=None,
        transaction_hashes=[],
    )

    state.add_order(order)
    print(f"✓ TradingState created with {len(state.orders)} orders")

    # Add a position
    position = PositionState(
        market="0x1234567890abcdef1234567890abcdef12345678",
        owner="0x9876543210fedcba9876543210fedcba98765432",
        side=PositionSide.LONG,
        size=Decimal("100.0"),
        entry_price=Decimal("0.55"),
        current_price=Decimal("0.57"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        last_update=datetime.utcnow(),
    )

    state.add_position(position)
    print(f"  TradingState now has {len(state.positions)} positions")

    exposure = state.get_total_exposure()
    print(f"  Total exposure: {exposure}")

    return True


def main():
    """Run all tests."""
    print("🧪 Testing Polymarket WebSocket Models")
    print("=" * 50)

    try:
        test_trade_message()
        test_order_message()
        test_book_message()
        test_parse_websocket_message()
        test_order_state()
        test_position_state()
        test_trading_state()

        print("\n" + "=" * 50)
        print("✅ All tests passed!")
        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
