# Enhanced Configuration System

## Overview

The enhanced configuration system (`inkedup_bot/config_enhanced.py`) provides comprehensive type safety, validation, and error handling for the Polymarket trading bot configuration. This system uses pydantic v2 with separate models for each configuration section, providing enhanced validation and better organization.

## Key Features

### ✅ **Modular Configuration Structure**
- **Separate pydantic models** for each major configuration section
- **Type-safe** configuration with comprehensive validation
- **Clear organization** with logical grouping of related settings

### ✅ **Enhanced Type Safety**
- **Custom bounded types**: `BoundedInt(min, max)`, `BoundedFloat(min, max)`, `BasisPoints`, `PercentageFloat`
- **Enum-based validation**: LogLevel, OrderType, BackoffStrategy, LiquidityMethod, DatabaseScheme
- **Business logic constants**: ValidationConstants class with realistic limits
- **Comprehensive range validation** for all numeric fields

### ✅ **Advanced Field Validation**
- **Ethereum address/key validation**: Format, length, and security checks
- **URL validation**: Scheme validation and parsing checks
- **Database URL validation**: Scheme validation with path existence checks
- **File system validation**: Log file path and permissions validation
- **Format validation**: Log format string testing

### ✅ **Business Logic Validation**
- **Risk hierarchy validation**: Global → Market → Per-Market → Per-Outcome risk caps
- **Cross-section validation**: Order rate limits vs risk caps, cache TTL vs scan intervals
- **Strategy constraints**: Market making spread relationships, arbitrage deviation limits
- **Position size consistency**: Order size ≤ Position size ≤ Risk caps

### ✅ **Runtime Safety Features**
- **Security warnings**: Weak keys, zero addresses, trivial values
- **Performance warnings**: Rate limiting risks, memory usage concerns
- **Configuration warnings**: Missing strategies, unlimited risk exposure
- **Validation summary**: Complete status overview of all configuration sections

## Configuration Sections

### 1. **APIConfig**
```python
api = APIConfig(
    public_key="0x...",           # Required: 42-character Ethereum address
    private_key="0x...",          # Required: 66-character Ethereum private key
    api_base="https://...",       # API endpoint URL
    ws_url="wss://...",          # WebSocket endpoint URL
    api_timeout_seconds=30,       # 1-300 seconds
    api_retry_attempts=3,         # 0-50 attempts
    api_retry_backoff_strategy="exponential"  # exponential|linear|constant
)
```

### 2. **DatabaseConfig**
```python
database = DatabaseConfig(
    database_url="sqlite:///bot_data.db",  # sqlite|postgresql|mysql
    database_echo=False,                   # Query logging
    database_pool_size=5,                  # 1-100 connections
    database_pool_timeout=30               # 1-300 seconds
)
```

### 3. **RiskManagementConfig**
```python
risk = RiskManagementConfig(
    global_risk_cap=10000.0,        # Global USD limit
    max_position_size=1000.0,       # Per-position USD limit
    max_order_size=100.0,           # Per-order USD limit
    emergency_stop_enabled=True,     # Emergency stop functionality
    risk_alert_threshold_pct=0.8     # Alert at 80% of limits
)
```

### 4. **TradingConfig**
```python
trading = TradingConfig(
    default_order_type="GTC",               # GTC|FOK|IOC|MARKET
    order_timeout_seconds=30,               # 1-300 seconds
    slippage_tolerance_bps=50,              # 0-10000 basis points
    order_rate_limit_per_second=2.0,       # 0.1-100.0 orders/sec
    profit_taking_enabled=False,            # Auto profit taking
    stop_loss_enabled=False                 # Auto stop loss
)
```

### 5. **MarketMakingConfig**
```python
market_making = MarketMakingConfig(
    mm_enabled=False,                    # Enable market making
    mm_target_spread_bps=50.0,          # Target spread (1-10000 BPS)
    mm_min_spread_bps=20.0,             # Minimum spread
    mm_max_spread_bps=200.0,            # Maximum spread
    mm_max_position_size=100.0,         # Max MM position size
    mm_risk_adjustment_enabled=True      # Risk-based spread adjustment
)
```

### 6. **MonitoringConfig**
```python
monitoring = MonitoringConfig(
    health_check_enabled=True,              # System health checks
    health_check_interval_seconds=60,       # Check frequency
    alert_enabled=True,                     # Alert system
    max_memory_usage_mb=2048,              # Memory limit
    max_cpu_usage_percent=80               # CPU limit
)
```

## Validation Features

### **Numeric Range Validation**
```python
# All numeric fields have realistic business limits
api_timeout_seconds: BoundedInt(1, 300)           # 1 second to 5 minutes
max_position_size: BoundedFloat(1.0, 1_000_000)   # $1 to $1M
spread_bps: BasisPoints                            # 0-10000 (0-100%)
percentage_fields: PercentageFloat                 # 0.0-1.0 (0-100%)
```

### **Cross-Section Validation**
```python
# Risk hierarchy: Global ≥ Market ≥ Per-Market ≥ Per-Outcome
# Order size ≤ Position size ≤ Risk caps
# Cache TTL ≥ Scan interval (avoid unnecessary API calls)
# MM spreads: Min < Target < Max
```

### **Security Validation**
```python
# Ethereum address format: 0x + 40 hex chars
# Private key format: 0x + 64 hex chars  
# No zero addresses or trivial keys
# URL scheme validation (http/https/ws/wss)
# Database URL scheme validation
```

## Usage Examples

### **Basic Usage**
```python
from inkedup_bot.config_enhanced import BotConfigEnhanced

# Load from environment variables and .env file
config = BotConfigEnhanced()

# Override specific sections
config = BotConfigEnhanced(
    api={
        "public_key": "0x1234...",
        "private_key": "0x5678...",
        "api_timeout_seconds": 45
    },
    risk={
        "global_risk_cap": 5000.0,
        "max_order_size": 50.0
    }
)
```

### **Runtime Validation**
```python
# Get validation summary
summary = config.get_validation_summary()
print(f"Config version: {summary['config_version']}")
print(f"API keys valid: {summary['sections']['api']['public_key_valid']}")

# Check for runtime safety issues
warnings = config.validate_runtime_safety()
for warning in warnings:
    print(f"WARNING: {warning}")
```

### **Error Handling**
```python
from pydantic import ValidationError

try:
    config = BotConfigEnhanced(
        api={"public_key": "invalid_key"}  # Will fail validation
    )
except ValidationError as e:
    for error in e.errors():
        print(f"Field: {error['loc']}")
        print(f"Error: {error['msg']}")
        print(f"Input: {error['input']}")
```

## Migration from Original Config

### **Key Changes**
1. **Nested structure**: `config.api.public_key` vs `config.public_key`
2. **Enhanced types**: Bounded numeric types instead of basic int/float
3. **Enum validation**: String literals replaced with proper enums
4. **Business logic validation**: Cross-field and cross-section validation
5. **Runtime safety**: Additional security and performance checks

### **Environment Variables**
```bash
# Original format still supported
PUBLIC_KEY=0x1234567890123456789012345678901234567890
PRIVATE_KEY=0x1234567890123456789012345678901234567890123456789012345678901234
API_TIMEOUT_SECONDS=30
DATABASE_URL=sqlite:///bot_data.db

# Nested configuration can be accessed via:
config.api.public_key
config.database.database_url
config.risk.global_risk_cap
```

## Validation Constants

The `ValidationConstants` class provides realistic business limits:

```python
class ValidationConstants:
    MAX_API_TIMEOUT = 300              # 5 minutes
    MAX_RETRY_ATTEMPTS = 50            # Reasonable retry limit
    MAX_BACKOFF_DELAY = 3600           # 1 hour max delay
    MAX_POSITION_SIZE_USD = 1_000_000  # $1M position limit
    MAX_ORDER_SIZE_USD = 100_000       # $100K order limit
    MAX_RISK_CAP_USD = 10_000_000      # $10M risk limit
    MAX_SPREAD_BPS = 10000             # 100% spread limit
    MAX_LIQUIDITY_USD = 1_000_000_000  # $1B liquidity limit
```

## Error Messages

The enhanced configuration provides clear, specific error messages:

```
✅ Validation Examples:
- "PUBLIC_KEY must start with '0x'"
- "PRIVATE_KEY must be exactly 66 characters (0x + 64 hex chars)"
- "API timeout must be between 1 and 300 seconds"
- "Global risk cap must be >= market risk cap"
- "Order rate limit could exceed global risk cap: 30000 > 100"
- "Market cache TTL should be >= scan interval to avoid unnecessary API calls"
```

## Performance and Security

### **Security Features**
- Validates against weak/trivial private keys
- Checks for zero addresses
- Validates URL schemes and formats
- File system permission validation
- Input sanitization and bounds checking

### **Performance Optimizations**
- Warns about aggressive rate limits
- Validates memory and CPU usage limits
- Cache TTL vs scan interval validation
- Batch size optimization warnings
- Resource usage monitoring configuration

## Testing

The enhanced configuration includes comprehensive test coverage:

- ✅ **Valid configuration loading**
- ✅ **Missing required field validation**
- ✅ **Invalid format rejection** (Ethereum keys, URLs, etc.)
- ✅ **Numeric range validation**
- ✅ **Business logic constraint validation**
- ✅ **Cross-section validation**
- ✅ **Runtime safety checks**
- ✅ **Advanced field validation** (file systems, permissions)

Run tests with:
```bash
python3 test_enhanced_config.py
```

## Benefits

### **Type Safety**
- Compile-time type checking with mypy/pyright
- Runtime type validation with pydantic
- IDE autocompletion and documentation

### **Error Prevention**
- Validates configuration at startup
- Prevents invalid combinations
- Business logic constraint checking
- Clear error messages with context

### **Maintainability** 
- Organized into logical sections
- Self-documenting with field descriptions
- Consistent validation patterns
- Easy to extend and modify

### **Production Ready**
- Comprehensive validation coverage
- Security best practices
- Performance considerations
- Monitoring and alerting integration

The enhanced configuration system provides enterprise-grade configuration management with comprehensive validation, type safety, and runtime checks suitable for production trading systems.