# WebSocket Manager Migration Guide

This guide helps you migrate from the legacy WebSocket implementations (`polymarket_ws_stream.py` and `inkedup_bot/ws_stream.py`) to the new unified WebSocket manager.

## Overview

The new unified WebSocket manager (`inkedup_bot/ws_manager.py`) provides:
- **Unified API**: Single interface for all WebSocket operations
- **Automatic reconnection**: Built-in retry logic with exponential backoff
- **Type safety**: Full type hints and Pydantic models
- **Modular handlers**: Separate handlers for different message types
- **Subscription management**: Dynamic subscription updates
- **Health monitoring**: Built-in health checks and status reporting

## Quick Migration

### 1. Basic Setup

**Old way (polymarket_ws_stream.py):**
```python
from polymarket_ws_stream import PolymarketWSStream

ws = PolymarketWSStream(
    private_key="your_private_key",
    signature_type="EOA"
)
await ws.start()
```

**New way:**
```python
from inkedup_bot.ws_manager import create_ws_manager

ws_manager = await create_ws_manager(
    private_key="your_private_key",
    signature_type="EOA"
)
await ws_manager.start()
```

### 2. Market Subscriptions

**Old way:**
```python
# Subscribe to market data
await ws.subscribe_market(market_address, ["trade", "book"])
```

**New way:**
```python
# Subscribe to market data
await ws_manager.subscribe_market(market_address, ["trade", "book", "price_change"])
```

### 3. User Subscriptions

**Old way:**
```python
# Subscribe to user data
await ws.subscribe_user(user_address, ["order"])
```

**New way:**
```python
# Subscribe to user data
await ws_manager.subscribe_user(user_address, ["order"])
```

### 4. Message Handling

**Old way (callback-based):**
```python
def on_message(message):
    if message['type'] == 'trade':
        handle_trade(message)
    elif message['type'] == 'order':
        handle_order(message)

ws.add_message_callback(on_message)
```

**New way (automatic routing):**
```python
def on_message(data):
    # Data is already processed and typed
    if data['type'] == 'trade':
        logger.info(f"Trade: {data}")

ws_manager.add_message_callback(on_message)
```

## Detailed Migration Steps

### Step 1: Replace Imports

**Replace:**
```python
from polymarket_ws_stream import PolymarketWSStream
```

**With:**
```python
from inkedup_bot.ws_manager import create_ws_manager
```

### Step 2: Update Initialization

**Replace:**
```python
ws = PolymarketWSStream(
    private_key=private_key,
    signature_type="EOA",
    ws_url="wss://ws-subscriptions-clob.polymarket.com/ws"
)
```

**With:**
```python
ws_manager = await create_ws_manager(
    private_key=private_key,
    signature_type="EOA",
    ws_url="wss://ws-subscriptions-clob.polymarket.com/ws",
    max_reconnect_attempts=5,
    reconnect_delay=1.0
)
```

### Step 3: Update Subscription Methods

**Market subscriptions:**
```python
# Old
await ws.subscribe_market(market_address, ["trade", "book"])

# New
await ws_manager.subscribe_market(market_address, ["trade", "book", "price_change"])
```

**User subscriptions:**
```python
# Old
await ws.subscribe_user(user_address, ["order"])

# New
await ws_manager.subscribe_user(user_address, ["order"])
```

### Step 4: Update Message Handling

**Old callback style:**
```python
def on_message(message):
    try:
        if message['type'] == 'trade':
            # Handle trade
            pass
    except KeyError:
        logger.error("Invalid message format")

ws.add_message_callback(on_message)
```

**New callback style:**
```python
def on_message(data):
    # Data is already validated and processed
    logger.info(f"Received {data['type']}: {data}")

ws_manager.add_message_callback(on_message)
```

### Step 5: Update Error Handling

**Old way:**
```python
try:
    await ws.start()
except Exception as e:
    logger.error(f"Failed to start: {e}")
```

**New way:**
```python
try:
    await ws_manager.start()
except Exception as e:
    logger.error(f"Failed to start: {e}")
    # Automatic reconnection is handled internally
```

## Advanced Features

### Custom Message Processing

The new system provides automatic message routing and processing:

```python
# Add custom processing for specific message types
def process_trades(data):
    if data['type'] == 'trade':
        # Process trade data
        pass

ws_manager.add_message_callback(process_trades)
```

### Health Monitoring

```python
# Check connection health
health = await ws_manager.health_check()
print(f"Connection status: {health['status']}")
print(f"Uptime: {health['uptime']}")
print(f"Messages processed: {health['messages_processed']}")
```

### Dynamic Subscriptions

```python
# Add subscriptions dynamically
await ws_manager.subscribe_market(new_market, ["trade"])

# Remove subscriptions
await ws_manager.unsubscribe_market(market_address, ["book"])
```

## Configuration Options

### WebSocket Manager Configuration

```python
ws_manager = await create_ws_manager(
    private_key="your_private_key",
    signature_type="EOA",  # "EOA", "POLY_GNOSIS_SAFE", or "POLY_PROXY"
    ws_url="wss://ws-subscriptions-clob.polymarket.com/ws",
    max_reconnect_attempts=5,  # Max reconnection attempts
    reconnect_delay=1.0,      # Initial reconnection delay (seconds)
    max_reconnect_delay=60.0,  # Maximum reconnection delay (seconds)
    heartbeat_interval=30.0    # Health check interval (seconds)
)
```

### Handler Configuration

Each handler can be configured individually:

```python
from inkedup_bot.handlers.trade_handler import TradeHandler

# Configure trade handler with custom cache size
trade_handler = TradeHandler(max_cache_size=1000)
```

## Error Codes and Troubleshooting

### Common Migration Issues

1. **Import errors**: Ensure all new modules are imported correctly
2. **Type mismatches**: Update message handling to use new typed structures
3. **Subscription format**: Update subscription types to match new API

### Error Handling

The new system provides better error handling:

```python
# Add error callback
def on_error(error):
    if isinstance(error, ConnectionError):
        logger.error("Connection failed")
    elif isinstance(error, AuthenticationError):
        logger.error("Authentication failed")
    else:
        logger.error(f"Unknown error: {error}")

ws_manager.add_error_callback(on_error)
```

## Testing Your Migration

### 1. Basic Connectivity Test

```python
async def test_migration():
    ws_manager = await create_ws_manager(private_key="test_key")
    
    # Test connection
    await ws_manager.start()
    assert ws_manager.is_running
    
    # Test subscription
    await ws_manager.subscribe_market("test_market", ["trade"])
    
    # Test cleanup
    await ws_manager.stop()
    assert not ws_manager.is_running
```

### 2. Message Processing Test

```python
def test_message_processing():
    messages_received = []
    
    def on_message(data):
        messages_received.append(data)
    
    ws_manager.add_message_callback(on_message)
    
    # Simulate message
    # ... test implementation
```

## Performance Improvements

The new system provides several performance benefits:

1. **Reduced memory usage**: Efficient caching with configurable limits
2. **Better error recovery**: Automatic reconnection with exponential backoff
3. **Type safety**: Reduced runtime errors with static type checking
4. **Modular design**: Easier testing and maintenance

## Backward Compatibility

While the new system is not directly backward compatible, migration is straightforward:

- **Function names**: Most function names remain the same
- **Subscription types**: Updated to match Polymarket's current API
- **Message formats**: Improved with consistent structure

## Migration Checklist

- [ ] Replace imports
- [ ] Update initialization
- [ ] Update subscription calls
- [ ] Update message handlers
- [ ] Test connectivity
- [ ] Test message processing
- [ ] Update error handling
- [ ] Update documentation
- [ ] Remove old WebSocket files
- [ ] Update deployment scripts

## Support

For migration assistance:
1. Check the examples in `examples/ws_manager_usage.py`
2. Review the API documentation in `inkedup_bot/ws_manager.py`
3. Run the test suite: `python -m pytest tests/test_ws_manager.py -v`