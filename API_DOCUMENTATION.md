# WebSocket Manager API Documentation

## Overview

The unified WebSocket manager provides a comprehensive interface for connecting to Polymarket's streaming API with automatic reconnection, message routing, and subscription management.

## Core Components

### 1. WebSocket Manager (`inkedup_bot/ws_manager.py`)

#### Main Class: `WebSocketManager`

**Initialization:**
```python
from inkedup_bot.ws_manager import create_ws_manager

ws_manager = await create_ws_manager(
    private_key: str,
    signature_type: str = "EOA",
    ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws",
    max_reconnect_attempts: int = 5,
    reconnect_delay: float = 1.0,
    max_reconnect_delay: float = 60.0,
    heartbeat_interval: float = 30.0
)
```

**Key Methods:**

| Method | Description | Parameters | Returns |
|--------|-------------|------------|---------|
| `start()` | Start the WebSocket connection | None | None |
| `stop()` | Stop the WebSocket connection | None | None |
| `subscribe_market(market, types)` | Subscribe to market data | `market`: str, `types`: List[str] | None |
| `unsubscribe_market(market, types)` | Unsubscribe from market data | `market`: str, `types`: List[str] | None |
| `subscribe_user(user, types)` | Subscribe to user data | `user`: str, `types`: List[str] | None |
| `unsubscribe_user(user, types)` | Unsubscribe from user data | `user`: str, `types`: List[str] | None |
| `health_check()` | Check connection health | None | Dict[str, Any] |
| `get_status()` | Get current status | None | Dict[str, Any] |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `is_running` | bool | Whether the WebSocket is connected |
| `is_connected` | bool | Whether the WebSocket is connected |
| `uptime` | float | Connection uptime in seconds |
| `messages_processed` | int | Total messages processed |

**Callbacks:**

```python
# Connection callbacks
ws_manager.add_connect_callback(callback: Callable[[], None])
ws_manager.add_disconnect_callback(callback: Callable[[], None])
ws_manager.add_error_callback(callback: Callable[[Exception], None])
ws_manager.add_message_callback(callback: Callable[[Dict[str, Any]], None])
```

### 2. Authentication Manager (`inkedup_bot/auth.py`)

#### Class: `AuthManager`

**Usage:**
```python
from inkedup_bot.auth import AuthManager

auth_manager = AuthManager(
    private_key="your_private_key",
    signature_type="EOA"
)

# Get authentication headers
headers = await auth_manager.get_auth_headers()
```

**Supported Signature Types:**
- `"EOA"` - Externally Owned Account
- `"POLY_GNOSIS_SAFE"` - Gnosis Safe
- `"POLY_PROXY"` - Proxy Account

### 3. Subscription Manager (`inkedup_bot/subscription.py`)

#### Class: `SubscriptionManager`

**Usage:**
```python
from inkedup_bot.subscription import SubscriptionManager

subscription_manager = SubscriptionManager()

# Add market subscription
await subscription_manager.add_market_subscription(
    market="0x123...",
    types=["trade", "book", "price_change"]
)

# Add user subscription
await subscription_manager.add_user_subscription(
    user="0xabc...",
    types=["order"]
)
```

### 4. Message Handlers (`inkedup_bot/handlers/`)

#### Base Handler (`base_handler.py`)

All handlers inherit from `BaseHandler` and provide:

- **TradeHandler** (`trade_handler.py`): Processes trade messages
- **OrderHandler** (`order_handler.py`): Processes order messages
- **BookHandler** (`book_handler.py`): Processes order book updates
- **PriceHandler** (`price_handler.py`): Processes price change notifications

**Handler Configuration:**
```python
from inkedup_bot.handlers.trade_handler import TradeHandler

# Create handler with custom cache size
trade_handler = TradeHandler(max_cache_size=1000)

# Process message
result = await trade_handler.handle(message_data)
```

## Message Types

### Trade Messages
```python
{
    "type": "trade",
    "market": "0x1234567890abcdef1234567890abcdef12345678",
    "asset_id": "12345",
    "price": "0.65",
    "size": "100.0",
    "side": "buy",
    "timestamp": "2024-01-01T12:00:00Z",
    "transactionHash": "0xabc...",
    "takerOrderId": "order_123",
    "makerOrders": [...]
}
```

### Order Messages
```python
{
    "type": "order",
    "market": "0x1234567890abcdef1234567890abcdef12345678",
    "orderId": "order_456",
    "owner": "0xuser...",
    "price": "0.65",
    "size": "100.0",
    "side": "buy",
    "status": "open",
    "timestamp": "2024-01-01T12:00:00Z"
}
```

### Book Messages
```python
{
    "type": "book",
    "market": "0x1234567890abcdef1234567890abcdef12345678",
    "bids": [...],
    "asks": [...],
    "timestamp": "2024-01-01T12:00:00Z"
}
```

### Price Messages
```python
{
    "type": "price_change",
    "market": "0x1234567890abcdef1234567890abcdef12345678",
    "price": "0.65",
    "change": "0.05",
    "timestamp": "2024-01-01T12:00:00Z"
}
```

## Usage Examples

### Basic Usage
```python
import asyncio
from inkedup_bot.ws_manager import create_ws_manager

async def main():
    # Create manager
    ws_manager = await create_ws_manager(
        private_key="your_private_key",
        signature_type="EOA"
    )
    
    # Add message callback
    def on_message(data):
        print(f"Received: {data}")
    
    ws_manager.add_message_callback(on_message)
    
    # Start and subscribe
    await ws_manager.start()
    await ws_manager.subscribe_market(
        "0x1234567890abcdef1234567890abcdef12345678",
        ["trade", "book"]
    )
    
    # Keep running
    await asyncio.sleep(60)
    await ws_manager.stop()

asyncio.run(main())
```

### Advanced Usage
```python
import asyncio
from inkedup_bot.ws_manager import create_ws_manager

async def advanced_example():
    # Create with custom configuration
    ws_manager = await create_ws_manager(
        private_key="your_private_key",
        signature_type="EOA",
        max_reconnect_attempts=10,
        reconnect_delay=2.0,
        heartbeat_interval=15.0
    )
    
    # Add multiple callbacks
    def on_connect():
        print("Connected!")
    
    def on_disconnect():
        print("Disconnected!")
    
    def on_error(error):
        print(f"Error: {error}")
    
    def on_message(data):
        if data['type'] == 'trade':
            print(f"Trade: {data['price']} @ {data['size']}")
    
    ws_manager.add_connect_callback(on_connect)
    ws_manager.add_disconnect_callback(on_disconnect)
    ws_manager.add_error_callback(on_error)
    ws_manager.add_message_callback(on_message)
    
    # Start
    await ws_manager.start()
    
    # Subscribe to multiple markets
    markets = ["0x123...", "0x456..."]
    for market in markets:
        await ws_manager.subscribe_market(market, ["trade", "price_change"])
    
    # Monitor health
    health = await ws_manager.health_check()
    print(f"Health: {health}")
    
    # Run
    await asyncio.sleep(300)
    await ws_manager.stop()

asyncio.run(advanced_example())
```

## Error Handling

### Connection Errors
```python
def on_error(error):
    if isinstance(error, ConnectionError):
        logger.error("Connection failed - will retry")
    elif isinstance(error, AuthenticationError):
        logger.error("Authentication failed - check credentials")
    else:
        logger.error(f"Unexpected error: {error}")

ws_manager.add_error_callback(on_error)
```

### Health Monitoring
```python
async def monitor_health():
    while True:
        health = await ws_manager.health_check()
        if health['status'] != 'healthy':
            logger.warning(f"Health degraded: {health}")
        await asyncio.sleep(30)
```

## Configuration Reference

### Environment Variables
```bash
PRIVATE_KEY=your_private_key_here
SIGNATURE_TYPE=EOA
WS_URL=wss://ws-subscriptions-clob.polymarket.com/ws
```

### Configuration Options
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `private_key` | str | Required | Ethereum private key |
| `signature_type` | str | "EOA" | Signature type for authentication |
| `ws_url` | str | Polymarket WS | WebSocket endpoint URL |
| `max_reconnect_attempts` | int | 5 | Maximum reconnection attempts |
| `reconnect_delay` | float | 1.0 | Initial reconnection delay (seconds) |
| `max_reconnect_delay` | float | 60.0 | Maximum reconnection delay (seconds) |
| `heartbeat_interval` | float | 30.0 | Health check interval (seconds) |

## Testing

### Unit Tests
```bash
python -m pytest tests/test_ws_manager.py -v
```

### Integration Tests
```bash
python -m pytest tests/test_integration.py -v
```

### Example Usage
```bash
python examples/ws_manager_usage.py
```

## Migration from Legacy

See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for detailed migration instructions from the legacy WebSocket implementations.

## Support

For issues and questions:
1. Check the examples in `examples/`
2. Review the test cases in `tests/`
3. Consult the migration guide
4. Check logs for detailed error information