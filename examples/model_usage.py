#!/usr/bin/env python3
"""
Example usage of Polymarket WebSocket models and state management.

This file demonstrates how to use the newly created models for:
1. Parsing WebSocket messages
2. Managing trading state
3. Validating messages
4. Calculating positions and P&L
"""

from datetime import datetime
from decimal import Decimal
import json

from inkedup_bot.models.ws_messages import (
    TradeMessage, OrderMessage, BookMessage, parse_websocket_message,
    serialize_message
)
from inkedup_bot.models.state import (
    TradingState, OrderState, PositionState, MarketDataState, OrderLifecycle, PositionSide,
    StateManager
)
from inkedup_bot.validation.schemas import message_validator</search>
</search_and_replace>


def example_1_parse_messages():
    """Example 1: Parsing WebSocket messages."""
    print("=== Example 1: Parsing WebSocket Messages ===")
    
    # Sample trade message
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
                "side": "buy"
            }
        ],
        "timestamp": "2024-01-01T12:00:00Z"
    }
    
    # Parse using the generic parser
    message = parse_websocket_message(trade_data)
    print(f"Parsed message type: {type(message).__name__}")
    print(f"Market: {message.market}")
    print(f"Maker orders: {len(message.maker_orders)}")
    
    # Validate the message
    is_valid = message_validator.validate_message_silent(trade_data, "trade")
    print(f"Message valid: {is_valid[0]}")
    
    return message


def example_2_order_management():
    """Example 2: Managing order lifecycle."""
    print("\n=== Example 2: Order Management ===")
    
    # Create trading state
    state = TradingState(
        owner="0x9876543210fedcba9876543210fedcba98765432",
        last_update=datetime.now()
    )
    
    # Create a new order
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
        created_at=datetime.now(),
        updated_at=datetime.now(),
        filled_size=Decimal("0"),
        remaining_size=Decimal("100.0"),
        average_fill_price=None,
        transaction_hashes=[]
    )
    
    state.add_order(order)
    print(f"Added order: {order.order_id}")
    
    # Simulate partial fill
    order.update_fill(Decimal("50.0"), Decimal("0.545"))
    print(f"After 50% fill:")
    print(f"  Filled size: {order.filled_size}")
    print(f"  Remaining: {order.remaining_size}")
    print(f"  Avg fill price: {order.average_fill_price}")
    
    # Complete the order
    order.update_fill(Decimal("50.0"), Decimal("0.548"))
    print(f"Order complete: {order.is_complete()}")
    
    return state


def example_3_position_tracking():
    """Example 3: Position tracking and P&L calculation."""
    print("\n=== Example 3: Position Tracking ===")
    
    # Create position from fills
    position = PositionState(
        market="0x1234567890abcdef1234567890abcdef12345678",
        owner="0x9876543210fedcba9876543210fedcba98765432",
        side=PositionSide.LONG,
        size=Decimal("100.0"),
        entry_price=Decimal("0.5465"),  # Average fill price
        current_price=Decimal("0.57"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        last_update=datetime.now()
    )
    
    print(f"Position details:")
    print(f"  Side: {position.side}")
    print(f"  Size: {position.size}")
    print(f"  Entry price: {position.entry_price}")
    print(f"  Current price: {position.current_price}")
    print(f"  Unrealized P&L: {position.calculate_unrealized_pnl()}")
    
    # Simulate price change
    position.current_price = Decimal("0.58")
    print(f"After price increase to 0.58:")
    print(f"  New unrealized P&L: {position.calculate_unrealized_pnl()}")
    
    return position


def example_4_market_data_management():
    """Example 4: Managing market data."""
    print("\n=== Example 4: Market Data Management ===")
    
    # Create market data state
    market_data = MarketDataState(
        market="0x1234567890abcdef1234567890abcdef12345678",
        timestamp=datetime.now()
    )
    
    # Update from order book
    bids = [
        {"price": Decimal("0.54"), "size": Decimal("100.0")},
        {"price": Decimal("0.53"), "size": Decimal("200.0")}
    ]
    asks = [
        {"price": Decimal("0.56"), "size": Decimal("150.0")},
        {"price": Decimal("0.57"), "size": Decimal("75.0")}
    ]
    
    market_data.update_from_book(bids, asks)
    
    print(f"Market data updated:")
    print(f"  Best bid: {market_data.best_bid}")
    print(f"  Best ask: {market_data.best_ask}")
    print(f"  Spread: {market_data.spread}")
    print(f"  Mid price: {market_data.mid_price}")
    
    # Get liquidity metrics
    metrics = market_data.get_liquidity_metrics()
    print(f"  Liquidity metrics:")
    for key, value in metrics.items():
        print(f"    {key}: {value}")
    
    return market_data


def example_5_complete_trading_flow():
    """Example 5: Complete trading flow."""
    print("\n=== Example 5: Complete Trading Flow ===")
    
    # Initialize trading state
    state = TradingState(
        owner="0x9876543210fedcba9876543210fedcba98765432",
        last_update=datetime.now()
    )
    
    # 1. Place an order
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
        created_at=datetime.now(),
        updated_at=datetime.now(),
        filled_size=Decimal("0"),
        remaining_size=Decimal("100.0"),
        average_fill_price=None,
        transaction_hashes=[]
    )
    state.add_order(order)
    
    # 2. Update market data
    market_data = MarketDataState(
        market="0x1234567890abcdef1234567890abcdef12345678",
        timestamp=datetime.now()
    )
    bids = [{"price": Decimal("0.54"), "size": Decimal("50.0")}]
    asks = [{"price": Decimal("0.56"), "size": Decimal("50.0")}]
    market_data.update_from_book(bids, asks)
    state.add_market_data(market_data)
    
    # 3. Simulate fills
    order.update_fill(Decimal("100.0"), Decimal("0.545"))
    
    # 4. Update position