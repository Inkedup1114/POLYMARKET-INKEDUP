# InkedUp Polymarket Bot API Reference

## Table of Contents

- [Overview](#overview)
- [Core Components](#core-components)
  - [OrderClient](#orderclient)
  - [Scanner](#scanner)
  - [RiskManager](#riskmanager)
  - [StateManager](#statemanager)
- [Trading Strategies](#trading-strategies)
- [Configuration](#configuration)
- [Risk Management](#risk-management)
- [Examples](#examples)

## Overview

The InkedUp Polymarket Bot is a sophisticated trading system designed for automated prediction market operations on the Polymarket platform. It provides comprehensive risk management, multiple trading strategies, and robust error handling.

### Key Features

- **Multi-Strategy Support**: Complement arbitrage, spread alerts, and market making
- **Advanced Risk Management**: Multi-layered exposure controls and real-time monitoring
- **Circuit Breaker Protection**: Automatic trading halts during adverse conditions
- **Database Failover**: In-memory cache fallback for system resilience
- **Comprehensive Logging**: Security-focused logging with sensitive data protection

## Core Components

### OrderClient

The `OrderClient` class provides the primary interface for order placement and management.

#### Class Definition

```python
class OrderClient:
    """Advanced order management client for Polymarket trading operations."""
    
    def __init__(
        self, 
        cfg: BotConfig, 
        state: StateManager, 
        stub_config: StubClientConfig = None
    ) -> None
```

#### Key Methods

##### `ready() -> bool`

Checks if the client is ready for live trading operations.

```python
# Example usage
if client.ready():
    print("Ready for live trading")
else:
    print("Using stub client for testing")
```

**Returns**: `True` if ready for live trading, `False` if using stub client

##### `place_limit(...) -> dict[str, Any] | None`

Places a limit order with comprehensive validation and retry logic.

```python
order = client.place_limit(
    token_id="0x123abc...",
    side="buy",
    price=0.65,
    size=100.0,
    market_slug="2024-election-winner",
    outcome_type="YES"
)
```

**Parameters**:
- `token_id` (str): Unique identifier for the prediction market token
- `side` (str): Order side, either "buy" or "sell"
- `price` (float): Limit price between 0.0 and 1.0 (probability)
- `size` (float): Order size in number of shares
- `tif` (str, optional): Time in force, defaults to "GTC"
- `market_slug` (str, optional): Human-readable market identifier
- `outcome_type` (str, optional): Type of outcome ("YES" or "NO")
- `notional_value` (float, optional): USD value of the order
- `risk` (Any, optional): Risk assessment data

**Returns**: Order details dictionary or `None` if placement fails

##### `cancel_all() -> list[Any]`

Cancels all open orders for the account.

```python
cancelled_orders = client.cancel_all()
print(f"Cancelled {len(cancelled_orders)} orders")
```

##### `get_positions() -> list[Any]`

Retrieves current positions for the account.

```python
positions = client.get_positions()
for position in positions:
    print(f"Token: {position['token_id']}, Size: {position['size']}")
```

##### `exposure_usd() -> float`

Calculates total USD exposure across all positions.

```python
total_exposure = client.exposure_usd()
print(f"Total exposure: ${total_exposure:.2f}")
```

### Scanner

The `Scanner` class monitors prediction markets to identify trading opportunities.

#### Class Definition

```python
class Scanner:
    """Market scanner for identifying trading opportunities on Polymarket."""
    
    def __init__(self, cfg: BotConfig | None = None) -> None
```

#### Key Methods

##### `scan_once(top: int = 15) -> list[MarketComposite]`

Performs a single scan of the top markets for opportunities.

```python
# Scan top 20 markets for opportunities
composites = await scanner.scan_once(top=20)

# Check for arbitrage opportunities
for comp in composites:
    if comp.complement_deviation and abs(comp.complement_deviation) > 0.05:
        print(f"Arbitrage opportunity in {comp.slug}: {comp.complement_deviation:.4f}")
```

##### `loop(interval: int = 30, top: int = 15) -> None`

Runs continuous market scanning with specified interval.

```python
# Start continuous scanning every 30 seconds
await scanner.loop(interval=30, top=15)
```

##### `ensure_markets(force: bool = False) -> None`

Ensures market data is cached and up-to-date.

```python
# Force refresh market cache
await scanner.ensure_markets(force=True)
```

### RiskManager

The `RiskManager` class provides comprehensive risk controls and monitoring.

#### Class Definition

```python
class RiskManager:
    """Comprehensive risk management system for Polymarket trading operations."""
    
    def __init__(
        self, 
        cfg: BotConfig, 
        order_client: OrderClient, 
        state: StateManager
    ) -> None
```

#### Operating Modes

- **NORMAL**: Full database functionality with complete risk tracking
- **DEGRADED**: In-memory cache fallback with essential risk controls  
- **EMERGENCY_HALT**: All trading halted due to critical system issues

#### Key Methods

##### `validate_order(order_data: dict) -> bool`

Validates whether an order would violate risk limits.

```python
order_data = {
    "token_id": "0x123...",
    "side": "buy", 
    "price": 0.65,
    "size": 500.0,
    "market_slug": "2024-election"
}

if await risk_manager.validate_order(order_data):
    # Proceed with order placement
    pass
else:
    print("Order rejected - would exceed risk limits")
```

##### `get_current_exposure() -> dict`

Retrieves current exposure metrics.

```python
exposure = await risk_manager.get_current_exposure()
print(f"Total exposure: ${exposure['total']:.2f}")
print(f"Available capacity: ${exposure['available']:.2f}")
```

##### `emergency_halt(reason: str) -> None`

Immediately halts all trading operations.

```python
await risk_manager.emergency_halt("Market crash detected")
```

### StateManager

The `StateManager` class handles persistent storage of trading data.

#### Class Definition

```python
class StateManager:
    """Manages persistent trading state and position tracking."""
    
    def __init__(self, db_path: str = "bot_data.db") -> None
```

#### Key Methods

##### `initialize_async() -> None`

Initializes the database and creates necessary tables.

```python
state = StateManager(db_path="trading.db")
await state.initialize_async()
```

##### `update_position_async(position_data: dict) -> None`

Updates position information in the database.

```python
position_data = {
    "token_id": "0x123...",
    "market_slug": "election-2024",
    "size": 100.0,
    "notional_value": 65.0
}
await state.update_position_async(position_data)
```

##### `get_total_exposure_async() -> float`

Calculates total exposure across all positions.

```python
total_exposure = await state.get_total_exposure_async()
print(f"Total exposure: ${total_exposure:.2f}")
```

## Trading Strategies

### ComplementArbStrategy

Exploits pricing inefficiencies in binary prediction markets.

```python
# Initialize complement arbitrage strategy
strategy = ComplementArbStrategy(
    min_deviation_threshold=0.02,  # 2% minimum deviation
    max_deviation_threshold=0.20,  # 20% maximum deviation  
    base_trade_size=10.0,          # $10 base trade size
    max_trade_size=100.0,          # $100 maximum trade size
    size_scaling_factor=50.0       # Scale size with deviation
)

# Process complement signal
signals = strategy.on_complement(complement_signal)
```

#### Arbitrage Logic

1. **YES + NO > 1.0**: Sell both outcomes (collect premium)
2. **YES + NO < 1.0**: Buy both outcomes (guaranteed profit on resolution)

### WideSpreadAlertStrategy  

Identifies markets with unusual bid-ask spreads.

```python
# Initialize spread alert strategy
strategy = WideSpreadAlertStrategy(spread_alert_bps=100)

# Process spread signal
trading_signal = strategy.on_spread(spread_signal)
```

## Configuration

### BotConfig

Core configuration class for bot settings.

```python
cfg = BotConfig(
    # API Configuration
    api_base="https://clob.polymarket.com",
    private_key="your_private_key_here",
    
    # Risk Management
    global_risk_cap=10000.0,        # $10k total exposure limit
    max_position_size=1000.0,       # $1k per position limit
    max_market_exposure=2500.0,     # $2.5k per market limit
    
    # Strategy Parameters
    complement_arb_min_deviation=0.01,    # 1% minimum arbitrage deviation
    complement_arb_max_deviation=0.20,    # 20% maximum arbitrage deviation
    complement_arb_base_size=10.0,        # $10 base arbitrage size
    complement_arb_max_size=100.0,        # $100 max arbitrage size
    
    # System Parameters
    market_cache_ttl=300,           # 5-minute market cache TTL
    book_batch_size=10,             # Batch size for order book requests
    api_retry_attempts=3,           # Number of retry attempts
    api_retry_delay_seconds=1.0,    # Delay between retries
)
```

## Risk Management

### Risk Control Layers

1. **Global Exposure Limits**: Total portfolio exposure caps
2. **Position Limits**: Per-position size and concentration controls
3. **Market Limits**: Per-market exposure limits to prevent concentration
4. **Outcome Limits**: Per-outcome type (YES/NO) exposure management
5. **Correlation Controls**: Dynamic adjustments for correlated positions

### Risk Metrics

The system tracks comprehensive risk metrics:

- Total portfolio exposure and utilization
- Position-level exposure and P&L
- Market concentration and diversification
- Outcome distribution (YES/NO balance)
- Historical volatility and drawdowns
- Correlation-adjusted exposure
- Liquidity-adjusted position sizes

### Alert Channels

- Console output with color coding
- Log file persistence  
- Webhook notifications (if configured)
- Email alerts (if configured)
- Slack integration (if configured)

## Examples

### Basic Trading Bot Setup

```python
import asyncio
from inkedup_bot.config import BotConfig
from inkedup_bot.state import StateManager
from inkedup_bot.order_client import OrderClient
from inkedup_bot.risk.manager import RiskManager
from inkedup_bot.scanner import Scanner

async def main():
    # Initialize configuration
    cfg = BotConfig(
        private_key="your_private_key",
        global_risk_cap=5000.0,
        complement_arb_min_deviation=0.02
    )
    
    # Initialize core components
    state = StateManager(db_path="trading.db")
    await state.initialize_async()
    
    order_client = OrderClient(cfg, state)
    risk_manager = RiskManager(cfg, order_client, state)
    scanner = Scanner(cfg)
    
    # Check if ready for trading
    if order_client.ready():
        print("✓ Ready for live trading")
    else:
        print("⚠ Using stub client for testing")
    
    # Start continuous market scanning
    await scanner.loop(interval=30, top=15)

if __name__ == "__main__":
    asyncio.run(main())
```

### Manual Order Placement

```python
async def place_manual_order():
    cfg = BotConfig(private_key="your_key")
    state = StateManager()
    await state.initialize_async()
    
    client = OrderClient(cfg, state)
    
    # Place a limit order
    order = client.place_limit(
        token_id="0x123abc...",
        side="buy",
        price=0.65,
        size=100.0,
        market_slug="2024-election-winner"
    )
    
    if order:
        print(f"Order placed: {order['id']}")
        print(f"Status: {order['status']}")
    else:
        print("Order placement failed")
```

### Risk Monitoring

```python
async def monitor_risk():
    cfg = BotConfig()
    state = StateManager()
    await state.initialize_async()
    
    client = OrderClient(cfg, state)
    risk_manager = RiskManager(cfg, client, state)
    
    # Get current exposure
    exposure = await risk_manager.get_current_exposure()
    print(f"Total exposure: ${exposure['total']:.2f}")
    print(f"Available capacity: ${exposure['available']:.2f}")
    print(f"Utilization: {exposure['utilization']:.1%}")
    
    # Check risk limits
    order_data = {
        "token_id": "0x123...",
        "side": "buy",
        "price": 0.65,
        "size": 1000.0
    }
    
    if await risk_manager.validate_order(order_data):
        print("✓ Order approved")
    else:
        print("✗ Order would exceed risk limits")
```

### Strategy Backtesting

```python
from inkedup_bot.strategies.complement import ComplementArbStrategy

def backtest_complement_strategy():
    strategy = ComplementArbStrategy(
        min_deviation_threshold=0.01,
        max_deviation_threshold=0.15,
        base_trade_size=25.0,
        max_trade_size=250.0
    )
    
    # Test with historical market data
    test_signals = [
        ComplementSignal(
            market_slug="test-market-1",
            yes_price=0.6,
            no_price=0.5,  # Sum = 1.1, deviation = +0.1
            complement_deviation=0.1
        ),
        ComplementSignal(
            market_slug="test-market-2", 
            yes_price=0.4,
            no_price=0.5,  # Sum = 0.9, deviation = -0.1
            complement_deviation=-0.1
        )
    ]
    
    for signal in test_signals:
        trading_signals = strategy.on_complement(signal)
        print(f"Market: {signal.market_slug}")
        print(f"Generated {len(trading_signals)} trading signals")
        for ts in trading_signals:
            print(f"  {ts.side} {ts.size} @ {ts.price}")
```

## Error Handling

The system includes comprehensive error handling and recovery mechanisms:

### Circuit Breaker Pattern

```python
# Circuit breaker automatically opens after consecutive failures
# Prevents cascade failures and allows system recovery
resilient_config = ResilientClientConfig(
    circuit_breaker_enabled=True,
    failure_threshold=5,        # Open after 5 failures
    recovery_timeout=60.0,      # Wait 60s before retry
    success_threshold=2         # Close after 2 successes
)
```

### Database Fallback

```python
# Automatic fallback to in-memory cache during database issues
# Maintains essential risk controls while allowing degraded operation
if risk_manager.mode == RiskSystemMode.DEGRADED:
    print("⚠ Operating in degraded mode - using cache")
elif risk_manager.mode == RiskSystemMode.EMERGENCY_HALT:
    print("🛑 Emergency halt - all trading suspended")
```

### Retry Logic

```python
# Automatic retries with exponential backoff
@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=3,
    max_time=30
)
def robust_operation():
    # Operation with automatic retry
    pass
```

---

For additional questions or support, please refer to the source code documentation or create an issue in the project repository.