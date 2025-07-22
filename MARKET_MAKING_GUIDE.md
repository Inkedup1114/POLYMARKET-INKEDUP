# Market Making Strategy Guide

## Overview

The InkedUp Polymarket bot now includes a fully implemented market making strategy that provides liquidity by placing bid and ask orders around fair value. This strategy is designed to profit from the bid-ask spread while managing inventory risk.

## Features

✅ **Core Market Making Features**:
- [x] **MarketMakingStrategy class** - Complete implementation
- [x] **Bid/ask placement logic** - Places orders around fair value with configurable spreads
- [x] **Inventory management** - Skews quotes based on current position to manage risk
- [x] **Spread targeting** - Configurable target spreads and minimum/maximum spread filters
- [x] **TradingEngine integration** - Fully integrated with risk management and order execution
- [x] **Risk management** - Position limits and per-market risk controls
- [x] **Configuration parameters** - Comprehensive configuration through environment variables

## Configuration

The market making strategy can be configured through environment variables in your `.env` file:

### Basic Configuration

```bash
# Enable market making
MM_ENABLED=true

# Target spread in basis points (50 bps = 0.5%)
MM_TARGET_SPREAD_BPS=50

# Maximum position size in USD
MM_MAX_POSITION_SIZE_USD=100

# Quote size in USD for each order
MM_QUOTE_SIZE_USD=10
```

### Advanced Configuration

```bash
# Minimum spread before withdrawing quotes (20 bps = 0.2%)
MM_MIN_SPREAD_BPS=20

# Maximum spread before withdrawing quotes (5000 bps = 50%)
MM_MAX_SPREAD_BPS=5000

# Inventory skew factor (0.1 = 10% price adjustment per position)
MM_INVENTORY_SKEW_FACTOR=0.1

# Edge to add to fair value in basis points (5 bps = 0.05%)
MM_EDGE_BPS=5

# Minimum market liquidity required (USD)
MM_MIN_LIQUIDITY=1000

# Comma-separated list of market slugs to trade (empty = all markets)
MM_ENABLED_MARKETS=
```

## How It Works

### 1. Fair Value Calculation
The strategy calculates fair value as the mid-point between current best bid and ask:
```
fair_value = (best_bid + best_ask) / 2
```

### 2. Spread Management
- Places bid and ask orders around fair value with target spread
- Withdraws quotes when spreads become too tight (unprofitable) or too wide (risky)
- Adds configurable edge for positive expected value

### 3. Inventory Management
The strategy tracks positions and skews quotes to manage inventory risk:
- When long: lowers both bid and ask to encourage selling
- When short: raises both bid and ask to encourage buying
- Skew amount based on `inventory_skew_factor` and current position

### 4. Risk Controls
- **Position limits**: Won't exceed `max_position_size` in USD
- **Market filtering**: Only trades markets with sufficient liquidity
- **Spread filtering**: Only makes markets when spreads are profitable
- **Integration with global risk management**: All trades go through TradingEngine risk checks

## Strategy Logic Flow

1. **Market Filtering**: Skip markets that don't meet liquidity requirements or aren't in enabled markets list
2. **Spread Calculation**: Calculate current bid-ask spread for each outcome
3. **Market Making Decision**: Only make market if spread is within profitable range
4. **Quote Generation**: Calculate target bid/ask prices with inventory skew
5. **Position Check**: Ensure quotes won't exceed position limits
6. **Signal Generation**: Create TradingSignal objects for execution
7. **Risk Processing**: All signals processed through TradingEngine with full risk checks

## Usage Examples

### Basic Market Making
```bash
# Enable with default settings
MM_ENABLED=true
MM_TARGET_SPREAD_BPS=50
MM_MAX_POSITION_SIZE_USD=100
MM_QUOTE_SIZE_USD=10
```

### Conservative Market Making
```bash
# Tighter risk controls and larger spreads
MM_ENABLED=true
MM_TARGET_SPREAD_BPS=100
MM_MIN_SPREAD_BPS=50
MM_MAX_POSITION_SIZE_USD=50
MM_QUOTE_SIZE_USD=5
MM_INVENTORY_SKEW_FACTOR=0.2
```

### Aggressive Market Making
```bash
# Smaller spreads and larger positions
MM_ENABLED=true
MM_TARGET_SPREAD_BPS=25
MM_MIN_SPREAD_BPS=10
MM_MAX_POSITION_SIZE_USD=200
MM_QUOTE_SIZE_USD=20
MM_INVENTORY_SKEW_FACTOR=0.05
```

### Market-Specific Trading
```bash
# Only trade specific markets
MM_ENABLED=true
MM_ENABLED_MARKETS=market-slug-1,market-slug-2,market-slug-3
```

## Monitoring

The strategy provides comprehensive logging:

```
[INFO] Processed market making signal: election-2024-winner buy 0.425
[INFO] Updated position for token-abc: 45.50
[DEBUG] Spread too tight for election-2024 yes: 15.2 bps
[DEBUG] Skipping market-xyz: insufficient liquidity (750)
```

## Risk Management Integration

The market making strategy is fully integrated with the bot's risk management system:

- **Global risk cap**: Won't exceed total portfolio risk limits
- **Per-market risk cap**: Won't exceed per-market exposure limits  
- **Per-outcome risk cap**: Won't exceed per-outcome position limits
- **Position tracking**: All trades update persistent position state
- **Risk pre-flight checks**: Every signal validated before execution

## Testing

The strategy includes comprehensive test coverage:

```bash
# Run market making tests
python -m pytest tests/test_market_making.py -v

# Run all tests
python -m pytest tests/ -v
```

## Performance Considerations

- **Latency**: Signals generated in scan loop with 30-second default interval
- **Position tracking**: Uses persistent database storage for accurate position management
- **Inventory skew**: Automatically adjusts quotes to manage directional risk
- **Spread monitoring**: Continuous monitoring of market conditions

## Integration with Existing Features

The market making strategy works alongside other bot features:

- **Scanner**: Integrates with existing market scanning and analysis
- **Database**: Uses persistent storage for position and trade tracking
- **Snapshot service**: Benefits from historical market data collection
- **Risk management**: Full integration with existing risk controls
- **Order client**: Uses existing Polymarket API integration

## Best Practices

1. **Start Conservative**: Begin with larger spreads and smaller position sizes
2. **Monitor Inventory**: Watch position accumulation and adjust skew factor
3. **Market Selection**: Use `MM_ENABLED_MARKETS` to focus on liquid, familiar markets
4. **Risk Limits**: Set appropriate position limits based on account size
5. **Paper Trading**: Test thoroughly with paper trading before live deployment

## Troubleshooting

### No Signals Generated
- Check `MM_ENABLED=true`
- Verify markets meet `MM_MIN_LIQUIDITY` requirement
- Ensure spreads are within `MM_MIN_SPREAD_BPS` and `MM_MAX_SPREAD_BPS` range
- Check if position limits are already reached

### Position Accumulation
- Increase `MM_INVENTORY_SKEW_FACTOR` for stronger position management
- Reduce `MM_MAX_POSITION_SIZE_USD` 
- Monitor and manually close positions if needed

### Performance Issues  
- Reduce number of markets with `MM_ENABLED_MARKETS`
- Increase scan interval to reduce signal frequency
- Monitor database performance and optimize if needed

## Status

✅ **Implementation**: Complete and fully tested
✅ **Integration**: Integrated with TradingEngine and risk management
✅ **Configuration**: Comprehensive configuration system
✅ **Testing**: Full test coverage with multiple scenarios
✅ **Documentation**: Complete usage guide and examples

The market making strategy is ready for production use with appropriate risk management and monitoring.
