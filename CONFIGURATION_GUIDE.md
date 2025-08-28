# InkedUp Polymarket Bot Configuration Guide

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Configuration Categories](#configuration-categories)
- [Environment Variables](#environment-variables)
- [Security Best Practices](#security-best-practices)
- [Risk Management](#risk-management)
- [Performance Tuning](#performance-tuning)
- [Troubleshooting](#troubleshooting)

## Overview

The InkedUp Polymarket Bot uses a comprehensive configuration system built on Pydantic for type safety and validation. This guide covers all configuration options and provides best practices for different use cases.

### Key Features

- **Type Safety**: Pydantic validation prevents configuration errors
- **Environment Variable Support**: All settings can be configured via environment variables
- **Validation**: Automatic validation ensures parameters are within safe ranges
- **Documentation**: Built-in help text for every configuration parameter

## Quick Start

### 1. Basic Environment Setup

Create a `.env` file in your project root:

```bash
# Required - Your Ethereum keys
PRIVATE_KEY=0x1234567890abcdef...  # 66 characters including 0x
PUBLIC_KEY=0x1234567890abcdef...   # 42 characters including 0x

# Optional - Override defaults
GLOBAL_RISK_CAP=1000.0
MAX_POSITION_SIZE=100.0
COMPLEMENT_ARB_MIN_DEVIATION=0.02
```

### 2. Initialize Configuration

```python
from inkedup_bot.config import BotConfig

# Load from environment variables
cfg = BotConfig()

# Or override specific settings
cfg = BotConfig(
    global_risk_cap=5000.0,
    max_position_size=500.0,
    complement_arb_min_deviation=0.01
)
```

### 3. Validate Configuration

```python
print(f"API Base: {cfg.api_base}")
print(f"Max Position: ${cfg.max_position_size}")
print(f"Risk Cap: ${cfg.global_risk_cap}")

# Check if ready for live trading
if cfg.private_key:
    print("⚠️  LIVE TRADING MODE")
else:
    print("✅ STUB MODE (Safe)")
```

## Configuration Categories

### API Configuration

Controls connection to the Polymarket platform.

```python
# API endpoints
api_base: str = "https://clob.polymarket.com"
ws_url: str = "wss://ws-subscriptions-clob.polymarket.com"

# Authentication
public_key: str = "0x..."   # Your Ethereum public key
private_key: str = "0x..."  # Your Ethereum private key

# Request settings
api_timeout_seconds: int = 30        # Request timeout
api_retry_attempts: int = 3          # Number of retries
api_retry_delay_seconds: int = 1     # Initial retry delay
```

**Environment Variables:**
- `POLYMARKET_API_BASE`
- `POLYMARKET_WS_URL`
- `PUBLIC_KEY` (required)
- `PRIVATE_KEY` (required)
- `API_TIMEOUT_SECONDS`
- `API_RETRY_ATTEMPTS`
- `API_RETRY_DELAY_SECONDS`

### Enhanced Retry Configuration

Advanced retry logic with exponential backoff and jitter.

```python
# Exponential backoff parameters
api_retry_max_delay_seconds: float = 60.0    # Max delay between retries
api_retry_exponential_base: float = 2.0      # Backoff multiplier
api_retry_jitter_enabled: bool = True        # Add randomization
api_retry_jitter_range: float = 0.1          # Jitter amount (10%)
api_retry_backoff_strategy: str = "exponential"  # exponential|linear|constant
```

**Environment Variables:**
- `API_RETRY_MAX_DELAY_SECONDS`
- `API_RETRY_EXPONENTIAL_BASE`
- `API_RETRY_JITTER_ENABLED`
- `API_RETRY_JITTER_RANGE`
- `API_RETRY_BACKOFF_STRATEGY`

### Database Configuration

Persistent storage for positions, orders, and market data.

```python
# Database connection
database_url: str = "sqlite:///bot_data.db"  # SQLite file path
database_pool_size: int = 5                  # Connection pool size
database_pool_timeout: int = 30              # Pool timeout seconds
database_pool_recycle: int = 3600            # Connection recycle time
```

**Environment Variables:**
- `DATABASE_URL`
- `DATABASE_POOL_SIZE`
- `DATABASE_POOL_TIMEOUT`
- `DATABASE_POOL_RECYCLE`

### Risk Management

Multi-layered risk controls to protect capital.

```python
# Global limits
global_risk_cap: float = 1000.0         # Maximum total exposure ($)
max_position_size: float = 100.0        # Maximum per-position size ($)
max_market_exposure: float = 250.0      # Maximum per-market exposure ($)

# Concentration limits
max_outcome_exposure: float = 500.0     # Max YES or NO exposure ($)
correlation_limit: float = 0.7          # Max correlation between positions
max_correlated_positions: int = 3       # Max correlated positions

# Dynamic adjustments
volatility_adjustment_enabled: bool = True   # Adjust limits based on volatility
liquidity_adjustment_enabled: bool = True    # Adjust based on liquidity
risk_adjustment_factor: float = 1.0          # Global risk multiplier
```

**Environment Variables:**
- `GLOBAL_RISK_CAP`
- `MAX_POSITION_SIZE`
- `MAX_MARKET_EXPOSURE`
- `MAX_OUTCOME_EXPOSURE`
- `CORRELATION_LIMIT`
- `MAX_CORRELATED_POSITIONS`
- `VOLATILITY_ADJUSTMENT_ENABLED`
- `LIQUIDITY_ADJUSTMENT_ENABLED`
- `RISK_ADJUSTMENT_FACTOR`

### Strategy Parameters

Configure trading algorithms and signal generation.

#### Complement Arbitrage

```python
# Threshold settings
complement_arb_min_deviation: float = 0.01    # 1% minimum deviation
complement_arb_max_deviation: float = 0.20    # 20% maximum deviation

# Position sizing
complement_arb_base_size: float = 10.0        # Base trade size ($)
complement_arb_max_size: float = 100.0       # Maximum trade size ($)
complement_arb_size_scaling: float = 50.0    # Scaling factor

# Risk controls
complement_arb_liquidity_check: bool = True   # Check liquidity before trading
complement_arb_risk_adjustment: bool = True   # Enable risk-based sizing
```

**Environment Variables:**
- `COMPLEMENT_ARB_MIN_DEVIATION`
- `COMPLEMENT_ARB_MAX_DEVIATION`
- `COMPLEMENT_ARB_BASE_SIZE`
- `COMPLEMENT_ARB_MAX_SIZE`
- `COMPLEMENT_ARB_SIZE_SCALING`
- `COMPLEMENT_ARB_LIQUIDITY_CHECK`
- `COMPLEMENT_ARB_RISK_ADJUSTMENT`

#### Spread Alerts

```python
# Spread thresholds
spread_alert_bps: int = 100              # Alert threshold (100 bps = 1%)
spread_alert_min_size: float = 1000.0    # Minimum market size for alerts
spread_alert_max_size: float = 10000.0   # Maximum trade size from alerts
```

**Environment Variables:**
- `SPREAD_ALERT_BPS`
- `SPREAD_ALERT_MIN_SIZE`
- `SPREAD_ALERT_MAX_SIZE`

### Market Data

Control data fetching and caching behavior.

```python
# Caching
market_cache_ttl: int = 300           # Market data cache TTL (seconds)
book_cache_ttl: int = 30              # Order book cache TTL (seconds)

# Batch processing
book_batch_size: int = 10             # Tokens per batch request
max_concurrent_requests: int = 5      # Concurrent API requests
request_rate_limit: float = 10.0      # Requests per second

# Market filtering
min_market_volume: float = 1000.0     # Minimum 24h volume ($)
max_markets_to_scan: int = 50         # Maximum markets to monitor
excluded_markets: List[str] = []      # Market slugs to exclude
```

**Environment Variables:**
- `MARKET_CACHE_TTL`
- `BOOK_CACHE_TTL`
- `BOOK_BATCH_SIZE`
- `MAX_CONCURRENT_REQUESTS`
- `REQUEST_RATE_LIMIT`
- `MIN_MARKET_VOLUME`
- `MAX_MARKETS_TO_SCAN`
- `EXCLUDED_MARKETS`

### Liquidity Analysis

Configure market liquidity calculations.

```python
# Calculation method
liquidity_method: str = "effective_spread"    # effective_spread|depth|composite

# Parameters
liquidity_top_n_levels: int = 5              # Order book levels to analyze
liquidity_effective_spread_pct: float = 0.01  # 1% from mid price
liquidity_min_price_threshold: float = 0.05   # Minimum price (5¢)
liquidity_max_price_threshold: float = 0.95   # Maximum price (95¢)
liquidity_cache_ttl_seconds: int = 60         # Cache TTL
liquidity_weight_decay_factor: float = 0.9    # Weight decay for deeper levels
```

**Environment Variables:**
- `LIQUIDITY_METHOD`
- `LIQUIDITY_TOP_N_LEVELS`
- `LIQUIDITY_EFFECTIVE_SPREAD_PCT`
- `LIQUIDITY_MIN_PRICE_THRESHOLD`
- `LIQUIDITY_MAX_PRICE_THRESHOLD`
- `LIQUIDITY_CACHE_TTL_SECONDS`
- `LIQUIDITY_WEIGHT_DECAY_FACTOR`

### System Settings

General system configuration.

```python
# Logging
log_level: str = "INFO"               # DEBUG|INFO|WARNING|ERROR|CRITICAL
log_file: Optional[str] = None        # Log file path (None = console only)
log_max_size: int = 10                # Log file size MB
log_backup_count: int = 5             # Number of backup files

# Performance
worker_threads: int = 4               # Thread pool size
async_timeout: int = 30               # Async operation timeout
memory_limit_mb: int = 512            # Memory usage limit

# Monitoring
enable_metrics: bool = True           # Enable performance metrics
metrics_port: int = 8080             # Metrics server port
health_check_interval: int = 60       # Health check frequency (seconds)
```

**Environment Variables:**
- `LOG_LEVEL`
- `LOG_FILE`
- `LOG_MAX_SIZE`
- `LOG_BACKUP_COUNT`
- `WORKER_THREADS`
- `ASYNC_TIMEOUT`
- `MEMORY_LIMIT_MB`
- `ENABLE_METRICS`
- `METRICS_PORT`
- `HEALTH_CHECK_INTERVAL`

## Environment Variables

### Creating .env File

```bash
# Create .env file in project root
cat > .env << 'EOF'
# Required Authentication
PRIVATE_KEY=0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
PUBLIC_KEY=0x1234567890abcdef1234567890abcdef12345678

# Risk Management
GLOBAL_RISK_CAP=1000.0
MAX_POSITION_SIZE=100.0
MAX_MARKET_EXPOSURE=250.0

# Strategy Settings
COMPLEMENT_ARB_MIN_DEVIATION=0.02
COMPLEMENT_ARB_MAX_DEVIATION=0.15
SPREAD_ALERT_BPS=100

# System Settings
LOG_LEVEL=INFO
MARKET_CACHE_TTL=300
BOOK_BATCH_SIZE=10

# Optional overrides
# API_RETRY_ATTEMPTS=5
# DATABASE_URL=postgresql://user:pass@localhost/polymarket
EOF
```

### Environment Variable Naming

Environment variables use SCREAMING_SNAKE_CASE:

| Config Parameter | Environment Variable |
|------------------|---------------------|
| `api_base` | `POLYMARKET_API_BASE` |
| `global_risk_cap` | `GLOBAL_RISK_CAP` |
| `max_position_size` | `MAX_POSITION_SIZE` |
| `complement_arb_min_deviation` | `COMPLEMENT_ARB_MIN_DEVIATION` |
| `log_level` | `LOG_LEVEL` |

### Loading Environment Variables

```python
# Automatic loading with python-dotenv
from inkedup_bot.config import BotConfig

cfg = BotConfig()  # Automatically loads from .env

# Manual environment setup
import os
os.environ['GLOBAL_RISK_CAP'] = '2000.0'
os.environ['LOG_LEVEL'] = 'DEBUG'

cfg = BotConfig()  # Uses environment values
```

## Security Best Practices

### Private Key Management

```bash
# ✅ GOOD: Use environment variables
export PRIVATE_KEY=0x1234...
python bot.py

# ✅ GOOD: Use .env file (add to .gitignore)
echo "PRIVATE_KEY=0x1234..." > .env

# ❌ BAD: Never hardcode in source
cfg = BotConfig(private_key="0x1234...")  # NEVER DO THIS

# ❌ BAD: Never commit to version control
git add .env  # Make sure .env is in .gitignore
```

### Secure Configuration

```python
# Use secure practices
cfg = BotConfig(
    # Load private key from environment only
    # private_key loaded automatically from PRIVATE_KEY env var
    
    # Start with conservative risk limits
    global_risk_cap=500.0,
    max_position_size=50.0,
    
    # Enable all safety features
    complement_arb_liquidity_check=True,
    complement_arb_risk_adjustment=True,
    volatility_adjustment_enabled=True
)

# Validate before use
assert cfg.global_risk_cap > 0, "Risk cap must be positive"
assert cfg.private_key, "Private key required for live trading"
print("✅ Configuration validated")
```

### Testing vs Production

```python
# Testing configuration (safe)
test_cfg = BotConfig(
    private_key=None,  # Use stub client
    global_risk_cap=100.0,  # Low limits
    log_level="DEBUG"  # Verbose logging
)

# Production configuration
prod_cfg = BotConfig(
    # private_key loaded from environment
    global_risk_cap=10000.0,
    log_level="INFO",
    enable_metrics=True
)
```

## Risk Management

### Conservative Settings (Recommended for Beginners)

```python
cfg = BotConfig(
    # Low risk limits
    global_risk_cap=500.0,          # $500 max exposure
    max_position_size=50.0,         # $50 per position
    max_market_exposure=125.0,      # $125 per market
    
    # Conservative strategy settings
    complement_arb_min_deviation=0.03,  # 3% minimum (higher threshold)
    complement_arb_max_deviation=0.10,  # 10% maximum (safety limit)
    complement_arb_base_size=5.0,       # $5 base size
    complement_arb_max_size=25.0,       # $25 max size
    
    # Enable all safety features
    complement_arb_liquidity_check=True,
    complement_arb_risk_adjustment=True,
    volatility_adjustment_enabled=True,
    liquidity_adjustment_enabled=True
)
```

### Moderate Settings

```python
cfg = BotConfig(
    # Moderate risk limits
    global_risk_cap=2500.0,         # $2.5k max exposure
    max_position_size=250.0,        # $250 per position
    max_market_exposure=625.0,      # $625 per market
    
    # Balanced strategy settings
    complement_arb_min_deviation=0.02,  # 2% minimum
    complement_arb_max_deviation=0.15,  # 15% maximum
    complement_arb_base_size=25.0,      # $25 base size
    complement_arb_max_size=125.0,      # $125 max size
)
```

### Aggressive Settings (Experienced Users Only)

```python
cfg = BotConfig(
    # Higher risk limits
    global_risk_cap=10000.0,        # $10k max exposure
    max_position_size=1000.0,       # $1k per position
    max_market_exposure=2500.0,     # $2.5k per market
    
    # Aggressive strategy settings
    complement_arb_min_deviation=0.01,  # 1% minimum (lower threshold)
    complement_arb_max_deviation=0.20,  # 20% maximum
    complement_arb_base_size=100.0,     # $100 base size
    complement_arb_max_size=500.0,      # $500 max size
    
    # Faster execution
    market_cache_ttl=60,            # 1-minute cache
    book_batch_size=20,             # Larger batches
)
```

### Risk Monitoring

```python
# Monitor risk utilization
def check_risk_utilization(cfg: BotConfig, current_exposure: float) -> None:
    utilization = current_exposure / cfg.global_risk_cap
    
    if utilization > 0.9:
        print("🔴 WARNING: >90% risk capacity used")
    elif utilization > 0.7:
        print("🟡 CAUTION: >70% risk capacity used")
    else:
        print(f"🟢 OK: {utilization:.1%} risk capacity used")

# Example usage
current_exposure = 750.0  # $750 current exposure
check_risk_utilization(cfg, current_exposure)
```

## Performance Tuning

### High-Frequency Trading

```python
cfg = BotConfig(
    # Fast data refresh
    market_cache_ttl=30,            # 30-second cache
    book_cache_ttl=5,               # 5-second book cache
    
    # Large batch sizes
    book_batch_size=50,             # More tokens per request
    max_concurrent_requests=10,     # More concurrent requests
    
    # Aggressive retry settings
    api_retry_attempts=5,           # More retries
    api_retry_delay_seconds=0.5,    # Faster retries
    api_retry_max_delay_seconds=10.0,
    
    # Higher throughput
    worker_threads=8,               # More worker threads
    request_rate_limit=20.0,        # 20 requests/second
)
```

### Low-Frequency Trading

```python
cfg = BotConfig(
    # Slower data refresh (saves API calls)
    market_cache_ttl=900,           # 15-minute cache
    book_cache_ttl=120,             # 2-minute book cache
    
    # Smaller batch sizes
    book_batch_size=5,              # Fewer tokens per request
    max_concurrent_requests=2,      # Fewer concurrent requests
    
    # Conservative retry settings
    api_retry_attempts=3,           # Standard retries
    api_retry_delay_seconds=2,      # Slower retries
    
    # Lower resource usage
    worker_threads=2,               # Fewer worker threads
    request_rate_limit=2.0,         # 2 requests/second
    memory_limit_mb=256,            # Lower memory limit
)
```

### Memory Optimization

```python
cfg = BotConfig(
    # Smaller caches
    market_cache_ttl=300,           # Standard cache
    max_markets_to_scan=20,         # Fewer markets
    
    # Limit data retention
    log_max_size=5,                 # 5MB log files
    log_backup_count=3,             # 3 backup files
    
    # Resource limits
    memory_limit_mb=256,            # 256MB limit
    worker_threads=2,               # Fewer threads
)
```

## Troubleshooting

### Common Issues

#### Configuration Validation Errors

```python
# Problem: Invalid private key format
try:
    cfg = BotConfig(private_key="invalid_key")
except ValidationError as e:
    print(f"Config error: {e}")
    # Solution: Use proper 66-character hex string
    cfg = BotConfig(private_key="0x" + "0" * 64)
```

#### Environment Variable Issues

```bash
# Problem: Variables not loading
echo $PRIVATE_KEY  # Check if set

# Solution: Source .env file
set -a; source .env; set +a

# Or use python-dotenv
pip install python-dotenv
```

#### Risk Limit Violations

```python
# Problem: Orders rejected due to risk limits
# Solution: Check and adjust risk settings
cfg = BotConfig(
    global_risk_cap=2000.0,  # Increase if needed
    max_position_size=200.0,  # Increase if needed
)

# Or check current exposure
print(f"Current exposure: ${get_current_exposure()}")
print(f"Available capacity: ${cfg.global_risk_cap - get_current_exposure()}")
```

### Debug Mode

```python
# Enable debug logging
cfg = BotConfig(
    log_level="DEBUG",
    api_retry_attempts=1,  # Fail fast for debugging
)

# Check configuration
print("Configuration Summary:")
for field_name, field_info in cfg.model_fields.items():
    value = getattr(cfg, field_name)
    print(f"  {field_name}: {value}")
```

### Validation

```python
# Validate all settings
def validate_config(cfg: BotConfig) -> None:
    # Check required fields
    assert cfg.private_key, "Private key required"
    assert cfg.public_key, "Public key required"
    
    # Check risk limits
    assert cfg.global_risk_cap > 0, "Risk cap must be positive"
    assert cfg.max_position_size <= cfg.global_risk_cap, "Position size too large"
    
    # Check strategy settings
    assert cfg.complement_arb_min_deviation > 0, "Min deviation must be positive"
    assert cfg.complement_arb_min_deviation < cfg.complement_arb_max_deviation, "Invalid deviation range"
    
    print("✅ Configuration validated successfully")

# Use validation
validate_config(cfg)
```

### Performance Monitoring

```python
# Monitor configuration impact
import time
start_time = time.time()

# Run operations with current config
results = scan_markets(cfg)

elapsed = time.time() - start_time
print(f"Scan completed in {elapsed:.2f}s with {len(results)} results")

# Tune based on results
if elapsed > 30:  # Too slow
    cfg.book_batch_size *= 2  # Larger batches
    cfg.max_concurrent_requests += 1  # More concurrency
elif elapsed < 5:  # Too fast, might be hitting rate limits
    cfg.request_rate_limit /= 2  # Slower rate
```

---

For additional help with configuration, please refer to the source code documentation or create an issue in the project repository.