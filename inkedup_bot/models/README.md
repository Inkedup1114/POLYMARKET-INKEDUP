# Polymarket WebSocket Models Documentation

This directory contains comprehensive models for parsing and managing Polymarket WebSocket messages and trading state.

## Overview

The models are organized into three main components:

1. **Message Models** (`ws_messages.py`) - Pydantic models for WebSocket message parsing
2. **Validation Schemas** (`../validation/schemas.py`) - JSON schema validation
3. **State Models** (`state.py`) - State management for orders, positions, and market data

## Quick Start

```python
from inkedup_bot.models.ws_messages import parse_websocket_message
from inkedup_bot.validation.schemas import message_validator
from inkedup_bot.models.state import TradingState, StateManager

# Parse a WebSocket message
message_data = {
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

# Parse and validate
message = parse_websocket_message(message_data)
is_valid = message_validator.validate_message(message_data, "trade")

# Create trading state
state = StateManager.create_initial_state("0xuser123...")
```

## Message Types

### TradeMessage
Represents trade execution events with maker order details.

**Fields:**
- `type`: Always "trade"
- `market`: Market contract address
- `transaction_hash`: Transaction hash
- `taker_order_id`: Taker order ID
- `maker_orders`: Array of maker order objects
- `timestamp`: Trade timestamp

**Example:**
```python
from inkedup_bot.models.ws_messages import TradeMessage

trade = TradeMessage(
    market="0x1234567890abcdef1234567890abcdef12345678",
    transaction_hash="0xabcdef...",
    taker_order_id="order_123",
    maker_orders=[{
        "orderId": "maker_456",
        "owner": "0x9876543210fedcba9876543210fedcba98765432",
        "price": "0.55",
        "size": "100.0",
        "side": "buy"
    }],
    timestamp="2024-01-01T12:00:00Z"
)
```

### OrderMessage
Represents order placement, update, or cancellation events.

**Fields:**
- `type`: Always "order"
- `order_id`: Unique order identifier
- `market`: Market contract address
- `owner`: Order owner address
- `price`: Order price (0-1)
- `size`: Order size
- `side`: "buy" or "sell"
- `status`: Order status
- `order_type`: "limit" or "market"
- `timestamp`: Order timestamp

### BookMessage
Represents order book updates with bids and asks arrays.

**Fields:**
- `type`: Always "book"
- `market`: Market contract address
- `bids`: Array of bid levels
- `asks`: Array of ask levels
- `timestamp`: Book timestamp

**Utility Methods:**
- `get_best_bid()`: Get best bid price
- `get_best_ask()`: Get best ask price
- `get_spread()`: Get bid-ask spread

### PriceChangeMessage
Represents price level changes.

### TickSizeChangeMessage
Represents tick size adjustments.

### LastTradePriceMessage
Represents the most recent trade price.

## State Management

### OrderState
Tracks order lifecycle from placement through execution.

**Key Features:**
- Tracks filled vs remaining size
- Calculates average fill price
- Manages order status transitions
- Maintains transaction history

```python
from inkedup_bot.models.state import OrderState, OrderLifecycle

order = OrderState(
    order_id="order_123",
    market="0x123...",
    owner="0xuser...",
    price=Decimal("0.55"),
    size=Decimal("100.0"),
    side="buy",
    status="open",
    order_type="limit",
    lifecycle_stage=OrderLifecycle.PLACEMENT,
    created_at=datetime.utcnow(),
    updated_at=datetime.utcnow(),
    remaining_size=Decimal("100.0")
)

# Update with fill
order.update_fill(Decimal("50.0"), Decimal("0.545"))
print(order.filled_size)  # 50.0
print(order.remaining_size)  # 50.0
```

### PositionState
Tracks positions with size and P&L calculations.

**Key Features:**
- Tracks realized and unrealized P&L
- Handles position sizing
- Calculates exposure metrics
- Manages position lifecycle

```python
from inkedup_bot.models.state import PositionState, PositionSide

position = PositionState(
    market="0x123...",
    owner="0xuser...",
    side=PositionSide.LONG,
    size=Decimal("100.0"),
    entry_price=Decimal("0.55"),
    current_price=Decimal("0.57"),
    last_update=datetime.utcnow()
)

print(position.calculate_unrealized_pnl())  # 2.0
print(position.get_total_pnl())  # 2.0
```

### MarketDataState
Caches market data snapshots.

**Key Features:**
- Tracks order book state
- Calculates liquidity metrics
- Maintains price history
- Provides market analytics

### TradingState
Complete trading state for a user.

**Key Features:**
- Aggregates orders, positions, and market data
- Provides exposure calculations
- Manages state across multiple markets
- Supports state merging

## Validation

All messages are validated against JSON schemas:

```python
from inkedup_bot.validation.schemas import message_validator

# Validate a message
try:
    message_validator.validate_message(message_data, "trade")
    print("Message is valid")
except ValidationError as e:
    print(f"Validation error: {e}")

# Validate silently
is_valid, error = message_validator.validate_message_silent(message_data, "trade")
```

## Usage Examples

### Real-time Message Processing

```python
from inkedup_bot.models.ws_messages import parse_websocket_message
from inkedup_bot.models.state import TradingState

state = TradingState(owner="0xuser123...")

def process_websocket_message(raw_message: dict):
    """Process incoming WebSocket message."""
    try:
        # Parse message
        message = parse_websocket_message(raw_message)
        
        # Update state based on message type
        if message.type == "trade":
            # Process trade
            pass
        elif message.type == "order":
            # Process order update
            pass
        elif message.type == "book":
            # Update market data
            market_data = state.get_market_data(message.market)
            if market_data:
                market_data.update_from_book(message.bids, message.asks)
        
    except ValueError as e:
        print(f"Error processing message: {e}")
```

### Position Management

```python
from inkedup_bot.models.state import PositionState, PositionSide

# Create initial position
position = PositionState(
    market="0x123...",
    owner="0xuser...",
    side=PositionSide.FLAT,
    size=Decimal("0"),
    entry_price=Decimal("0"),
    current_price=Decimal("0.55"),
    last_update=datetime.utcnow()
)

# Add a fill (opening position)
position.add_fill(
    fill_size=Decimal("100.0"),
    fill_price=Decimal("0.55"),
    is_buy=True
)
print(position.side)  # PositionSide.LONG
print(position.size)  # 100.0

# Add another fill (closing position)
position.add_fill(
    fill_size=Decimal("50.0"),
    fill_price=Decimal("0.57"),
    is_buy=False
)
print(position.size)  # 50.0
print(position.realized_pnl)  # 1.0
```

### Risk Monitoring

```python
from inkedup_bot.models.state import TradingState

def calculate_portfolio_metrics(state: TradingState):
    """Calculate portfolio risk metrics."""
    exposure = state.get_total_exposure()
    total_pnl = state.get_total_pnl()
    
    return {
        "net_exposure": exposure["net_exposure"],
        "gross_exposure": exposure["gross_exposure"],
        "total_pnl": total_pnl,
        "active_orders": len(state.get_active_orders()),
        "open_positions": len(state.get_open_positions())
    }
```

## Error Handling

All models include comprehensive validation:

```python
from inkedup_bot.models.ws_messages import TradeMessage

try:
    # This will raise validation error
    trade = TradeMessage(
        market="invalid_address",  # Invalid address format
        transaction_hash="0x123",
        taker_order_id="order_123",
        maker_orders=[],
        timestamp="invalid_date"
    )
except ValueError as e:
    print(f"Validation error: {e}")
```

## Serialization

All models support JSON serialization:

```python
import json
from inkedup_bot.models.ws_messages import serialize_message

# Serialize to JSON
json_str = serialize_message(message)

# Deserialize from JSON
from inkedup_bot.models.ws_messages import parse_websocket_message
message = parse_websocket_message(json.loads(json_str))
```

## Best Practices

1. **Always validate messages** before processing
2. **Use Decimal for prices and sizes** to avoid floating-point errors
3. **Handle None values** for optional fields
4. **Update timestamps** when state changes
5. **Use state managers** for complex state operations
6. **Monitor position exposure** regularly
7. **Cache market data** for performance

## Testing

Create test data for development:

```python
from inkedup_bot.models.ws_messages import TradeMessage, OrderMessage, BookMessage
from inkedup_bot.models.state import TradingState

# Test trade message
test_trade = {
    "type": "trade",
    "market": "0x1234567890abcdef1234567890abcdef12345678",
    "transactionHash": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
    "takerOrderId": "test_order_123",
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

# Test order message
test_order = {
    "type": "order",
    "orderId": "test_order_123",
    "market": "0x1234567890abcdef1234567890abcdef12345678",
    "owner": "0x9876543210fedcba9876543210fedcba98765432",
    "price": "0.55",
    "size": "100.0",
    "side": "buy",
    "status": "open",
    "orderType": "limit",
    "timestamp": "2024-01-01T12:00:00Z"
}

# Test book message
test_book = {
    "type": "book",
    "market": "0x1234567890abcdef1234567890abcdef12345678",
    "bids": [
        {"price": "0.54", "size": "100.0"},
        {"price": "0.53", "size": "200.0"}
    ],
    "asks": [
        {"price": "0.56", "size": "150.0"},
        {"price": "0.57", "size": "75.0"}
    ],
    "timestamp": "2024-01-01T12:00:00Z"
}