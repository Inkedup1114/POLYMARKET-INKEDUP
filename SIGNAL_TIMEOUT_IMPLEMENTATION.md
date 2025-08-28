# Signal Timeout Handling Implementation

This document describes the comprehensive signal timeout handling system implemented in the signal processing pipeline.

## Overview

The signal timeout handling system ensures that old signals don't interfere with current trading decisions by implementing:

- **Timestamp tracking** for all signals
- **Configurable timeout periods** based on signal type
- **Automatic cleanup** of stale/expired signals
- **Signal deduplication** to prevent duplicate processing
- **Comprehensive metrics** and monitoring

## Architecture

### Core Components

1. **SignalManager** (`inkedup_bot/signal_manager.py`)
   - Central component managing signal lifecycle
   - Handles timeout tracking, cleanup, and processing coordination
   - Thread-safe with async/await support

2. **SignalMetadata** (Dataclass)
   - Tracks signal creation time, expiration, status, and processing history
   - Supports retry counting and error tracking

3. **TradingEngine Integration** (`inkedup_bot/engine.py`)
   - Enhanced to use SignalManager for all signal processing
   - Maintains backward compatibility with existing signal interface

4. **Configuration** (`inkedup_bot/config.py`)
   - Configurable timeout periods for different signal types
   - Cleanup intervals and processing limits

## Key Features

### 1. Timestamp Tracking

Every signal is automatically timestamped when submitted:

```python
signal_metadata = SignalMetadata(
    signal_id=signal.signal_id,
    created_at=time.time(),
    expires_at=current_time + timeout,
    status=SignalStatus.PENDING
)
```

### 2. Configurable Timeout Periods

Different signal types have different timeout periods:

- **Spread signals**: 15 seconds (fast market opportunities)
- **Complement arbitrage**: 45 seconds (more analysis time needed)
- **Market making**: 60 seconds (longer-term positioning)
- **Default signals**: 30 seconds (general purpose)

### 3. Automatic Cleanup

Background cleanup task runs periodically:

```python
async def _cleanup_signals(self):
    """Clean up expired signals and stale deduplication cache."""
    current_time = time.time()
    
    # Find and expire old signals
    for signal_id, wrapper in list(self._pending_signals.items()):
        if current_time >= wrapper.metadata.expires_at:
            await self._handle_expired_signal(wrapper)
```

### 4. Signal Deduplication

Prevents duplicate signal processing within a configurable window:

```python
def _generate_dedup_key(self, signal: TradingSignal) -> str:
    """Generate unique key for deduplication."""
    return "|".join([
        signal.market_slug,
        signal.token_id, 
        signal.side,
        f"{signal.price:.6f}",
        f"{signal.size:.6f}"
    ])
```

### 5. Processing Metrics

Comprehensive metrics tracking:

```python
metrics = {
    "signals_received": 0,
    "signals_processed": 0, 
    "signals_expired": 0,
    "signals_failed": 0,
    "signals_deduplicated": 0,
    "avg_processing_time": 0.0,
    "pending_signals": len(pending),
    "processing_signals": len(processing)
}
```

## Usage

### Basic Usage

The signal timeout handling is automatically integrated into the existing TradingEngine:

```python
from inkedup_bot.engine import TradingEngine
from inkedup_bot.signals import TradingSignal

engine = TradingEngine(config)
await engine.initialize()

# Submit signal - timeout handling is automatic
signal = TradingSignal(
    market_slug="test-market",
    token_id="token-123", 
    side="buy",
    price=0.55,
    size=100.0
)

signal_id = engine.process_signal(signal)
```

### Monitoring Signal Status

```python
# Check signal status
status = engine.get_signal_status(signal_id)
print(f"Signal status: {status}")  # pending, processing, processed, expired, failed

# Get processing metrics
metrics = engine.get_signal_metrics()
print(f"Processed: {metrics['signals_processed']}")
print(f"Expired: {metrics['signals_expired']}")
```

### Configuration

Configure timeout periods in your bot configuration:

```python
config = BotConfig()
config.signal_default_timeout_seconds = 30.0
config.signal_spread_timeout_seconds = 15.0
config.signal_complement_timeout_seconds = 45.0
config.signal_market_making_timeout_seconds = 60.0
config.signal_cleanup_interval_seconds = 10.0
config.signal_enable_deduplication = True
config.signal_deduplication_window_seconds = 5.0
```

## Signal Lifecycle

1. **Submission**
   - Signal submitted to engine via `process_signal()`
   - SignalManager creates metadata with timestamps
   - Deduplication check performed
   - Signal queued for processing

2. **Processing** 
   - Signal moved to processing state
   - Actual trading logic executed
   - Success/failure tracked in metadata

3. **Completion**
   - Signal marked as processed/failed
   - Moved to appropriate history queue
   - Metrics updated

4. **Expiration/Cleanup**
   - Expired signals automatically detected
   - Moved to expired queue
   - Periodic cleanup of old records

## Signal States

- **PENDING**: Signal submitted, waiting for processing
- **PROCESSING**: Signal currently being processed
- **PROCESSED**: Signal successfully processed
- **EXPIRED**: Signal timed out before processing
- **FAILED**: Signal processing failed with error

## Integration Points

### Scanner Integration

The scanner automatically benefits from signal timeout handling:

```python
# In scanner.py - existing code unchanged
for signal in strategy_signals:
    self.engine.process_signal(signal)  # Now includes timeout handling
```

Signal metrics are displayed during scanning:

```
INFO: Signal processing: 15 processed, 2 expired, 3 pending, avg time: 0.125s
```

### Strategy Integration

Strategies can submit signals normally - timeout handling is transparent:

```python
class MyStrategy:
    def on_spread(self, spread_signal):
        if self.should_trade(spread_signal):
            trading_signal = TradingSignal(...)
            return trading_signal  # Timeout handling automatic
```

## Error Handling

### Timeout Errors

```python
class SignalTimeoutError(Exception):
    """Raised when a signal expires before processing."""
    pass
```

### Deduplication Errors

```python
class SignalDeduplicationError(Exception): 
    """Raised when a duplicate signal is detected."""
    pass
```

### Graceful Degradation

- If signal manager fails to start, engine falls back to direct processing
- Individual signal failures don't affect other signals
- Cleanup continues even if individual signals fail

## Performance Considerations

### Memory Management

- Expired signals are kept in bounded queues (max 1000 by default)
- Deduplication cache is periodically cleaned
- Processing queues have size limits

### Concurrent Processing

- Configurable maximum concurrent signals (default: 10)
- Thread-safe operations with proper locking
- Async/await support for non-blocking operations

### Monitoring Overhead

- Metrics collection is optional and can be disabled
- Cleanup interval is configurable
- Background tasks use minimal resources

## Testing

### Unit Tests

```bash
# Run signal timeout tests
python -m pytest tests/test_signal_manager.py -v
```

### Integration Testing

```bash
# Run full integration test
python test_signal_timeout.py
```

### Example Usage

```bash
# Run simple example
python examples/signal_timeout_example.py
```

## Configuration Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `signal_default_timeout_seconds` | 30.0 | Default signal timeout |
| `signal_spread_timeout_seconds` | 15.0 | Spread signal timeout |
| `signal_complement_timeout_seconds` | 45.0 | Complement arb timeout |
| `signal_market_making_timeout_seconds` | 60.0 | Market making timeout |
| `signal_cleanup_interval_seconds` | 10.0 | Cleanup frequency |
| `signal_max_concurrent` | 10 | Max concurrent signals |
| `signal_enable_deduplication` | True | Enable deduplication |
| `signal_deduplication_window_seconds` | 5.0 | Dedup window |

## Benefits

1. **Prevents Stale Signals**: Old signals are automatically expired
2. **Improved Performance**: Concurrent processing with limits
3. **Better Monitoring**: Comprehensive metrics and status tracking
4. **Duplicate Prevention**: Automatic deduplication
5. **Configurable**: Timeout periods tuned per signal type
6. **Backward Compatible**: Existing code works unchanged
7. **Robust Error Handling**: Graceful failure handling
8. **Memory Efficient**: Automatic cleanup and bounded queues

## Future Enhancements

1. **Priority-based Processing**: Higher priority for certain signal types
2. **Dynamic Timeout Adjustment**: Adjust timeouts based on market conditions
3. **Advanced Metrics**: Percentile tracking, success rates by signal type
4. **Signal Replay**: Ability to replay failed signals
5. **External Monitoring**: Integration with monitoring systems
6. **Signal Batching**: Group related signals for efficient processing
