#!/usr/bin/env python3
"""
Simple demonstration of the Polymarket WebSocket models.
"""

from datetime import datetime
from decimal import Decimal

from inkedup_bot.models.state import (
    OrderLifecycle,
    OrderState,
    PositionSide,
    PositionState,
    TradingState,
)
from inkedup_bot.models.ws_messages import BookMessage, OrderMessage, TradeMessage
from inkedup_bot.validation.schemas import message_validator


def main():
    print("🚀 Polymarket WebSocket Models Demo")
    print("=" * 50)

    # 1. Create and validate a trade message
    print("\n1. Trade Message Example")
    trade_data = {
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

    trade = TradeMessage(**trade_data)
    print(f"✓ Trade created: {trade.market}")
    print(f"  Maker orders: {len(trade.maker_orders)}")

    # 2. Create an order message
    print("\n2. Order Message Example")
    order_data = {
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

    order = OrderMessage(**order_data)
    print(f"✓ Order created: {order.order_id}")
    print(f"  Price: {order.price}")
    print(f"  Side: {order.side}")

    # 3. Create book message
    print("\n3. Book Message Example")
    book_data = {
        "type": "book",
        "market": "0x1234567890abcdef1234567890abcdef12345678",
        "bids": [
            {"price": "0.54", "size": "100.0"},
            {"price": "0.53", "size": "200.0"},
        ],
        "asks": [{"price": "0.56", "size": "150.0"}, {"price": "0.57", "size": "75.0"}],
        "timestamp": "2024-01-01T12:00:00Z",
    }

    book = BookMessage(**book_data)
    print(f"✓ Book created: {book.market}")
    print(f"  Best bid: {book.get_best_bid()}")
    print(f"  Best ask: {book.get_best_ask()}")
    print(f"  Spread: {book.get_spread()}")

    # 4. Create trading state
    print("\n4. Trading State Example")
    state = TradingState(
        owner="0x9876543210fedcba9876543210fedcba98765432", last_update=datetime.now()
    )

    # Add order to state
    order_state = OrderState(
        order_id="order_123",
        market="0x1234567890abcdef1234567890abcdef12345678",
        owner="0x9876543210fedcba9876543210fedcba98765432",
        price=Decimal("0.55"),
        size=Decimal("100.0"),
        side="buy",
        status="open",
        order_type="limit",
        lifecycle_stage=OrderLifecycle.PLACEMENT,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        filled_size=Decimal("0"),
        remaining_size=Decimal("100.0"),
        average_fill_price=None,
        transaction_hashes=[],
    )

    state.add_order(order_state)
    print(f"✓ Added order to state: {len(state.orders)} orders")

    # Add position to state
    position = PositionState(
        market="0x1234567890abcdef1234567890abcdef12345678",
        owner="0x9876543210fedcba9876543210fedcba98765432",
        side=PositionSide.LONG,
        size=Decimal("100.0"),
        entry_price=Decimal("0.55"),
        current_price=Decimal("0.57"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        last_update=datetime.now(),
    )

    state.add_position(position)
    print(f"✓ Added position to state: {len(state.positions)} positions")

    # Calculate exposure
    exposure = state.get_total_exposure()
    print(f"  Total exposure: {exposure}")

    # 5. Validate messages
    print("\n5. Message Validation Example")
    is_valid, error = message_validator.validate_message_silent(trade_data, "trade")
    print(f"✓ Trade message valid: {is_valid}")
    if not is_valid:
        print(f"  Error: {error}")

    print("\n" + "=" * 50)
    print("✅ Demo completed successfully!")


if __name__ == "__main__":
    main()
