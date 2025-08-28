# Risk Management Fallback System

This document describes the enhanced fallback mechanisms implemented in the inkedup-bot risk management system to handle database unavailability.

## Overview

The risk system now operates in three distinct modes to ensure continuous operation even when the database becomes unavailable:

1. **NORMAL** - Full database functionality with complete risk tracking
2. **DEGRADED** - In-memory cache fallback with limited functionality
3. **EMERGENCY_HALT** - All trading suspended due to critical database issues

## Architecture

### DatabaseFallbackCache

A lightweight in-memory cache that maintains essential risk data:

```python
class DatabaseFallbackCache:
    def __init__(self):
        self.positions: dict[str, dict[str, Any]] = {}
        self.market_exposures: dict[str, float] = {}
        self.outcome_exposures: dict[str, float] = {}
        self.total_exposure: float = 0.0
        self.last_updated: float = time.time()
        self.cache_hits: int = 0
        self.cache_misses: int = 0
```

### RiskManager Enhancements

The `RiskManager` class now includes:

- **Automatic failure detection** - Monitors database health
- **Mode switching logic** - Transitions between operating modes
- **Fallback data access** - Seamless access to cached data
- **Recovery mechanisms** - Automatic return to normal operation

## Operating Modes

### NORMAL Mode

- **Description**: Full database functionality
- **Behavior**: All risk checks use live database data
- **Characteristics**:
  - Complete position tracking
  - Full historical data access
  - Real-time risk calculations
  - No data limitations

### DEGRADED Mode

- **Description**: In-memory cache fallback
- **Trigger**: 3+ consecutive database failures (configurable)
- **Behavior**: Risk checks use cached position data
- **Characteristics**:
  - Limited to cached positions
  - No historical data access
  - Basic risk calculations only
  - Position updates still attempted

**Example Log Output:**
```
CRITICAL - RISK SYSTEM: Switching to DEGRADED mode - Database instability detected: 3 failures
CRITICAL - Risk checks will continue using in-memory cache with limited functionality
WARNING - Preflight check completed in degraded mode - using fallback data
```

### EMERGENCY_HALT Mode

- **Description**: All trading suspended
- **Trigger**: 10+ consecutive database failures (configurable)
- **Behavior**: All trading operations blocked
- **Characteristics**:
  - Complete trading halt
  - No new orders allowed
  - Manual intervention required
  - Critical alerts generated

**Example Log Output:**
```
CRITICAL - RISK SYSTEM: EMERGENCY HALT ACTIVATED - Database failure threshold exceeded: 10
CRITICAL - ALL TRADING ACTIVITY SUSPENDED
CRITICAL - Manual intervention required to restore trading functionality
```

## Configuration

### Thresholds

The following thresholds control mode transitions:

```python
self.max_failure_threshold = 3      # NORMAL -> DEGRADED
self.emergency_halt_threshold = 10  # DEGRADED -> EMERGENCY_HALT
self.database_check_interval = 60   # Seconds between recovery attempts
```

### Customization

Adjust thresholds based on your requirements:

```python
# More conservative (faster degradation)
risk_manager.max_failure_threshold = 2
risk_manager.emergency_halt_threshold = 5

# More tolerant (slower degradation)
risk_manager.max_failure_threshold = 5
risk_manager.emergency_halt_threshold = 20
```

## Recovery Mechanisms

### Automatic Recovery

The system automatically attempts recovery:

1. **Health Checks**: Periodic database connectivity tests
2. **Gradual Recovery**: Failure count decreases on successful operations
3. **Mode Restoration**: Automatic return to NORMAL mode when database is healthy

### Manual Recovery

Several manual recovery options are available:

```python
# Force immediate database health check
risk_manager.force_database_check()

# Reset failure count
risk_manager.reset_database_failure_count()

# Manually trigger emergency halt
risk_manager.set_emergency_halt("Manual emergency stop")

# Attempt to clear emergency halt
success = risk_manager.clear_emergency_halt()
```

## Monitoring and Observability

### Status Monitoring

Get comprehensive system status:

```python
status = risk_manager.get_risk_system_status()
print(f"Mode: {status['mode']}")
print(f"Failures: {status['database_failure_count']}")
print(f"Cache stats: {status['fallback_cache']}")
```

### Example Status Output

```json
{
  "mode": "degraded",
  "database_failure_count": 5,
  "trading_enabled": true,
  "last_database_check": 1629825600.0,
  "fallback_cache": {
    "cache_hits": 45,
    "cache_misses": 2,
    "positions_count": 8,
    "markets_count": 3,
    "outcomes_count": 6,
    "total_exposure": 2500.0,
    "last_updated": 1629825550.0,
    "age_seconds": 50.0
  },
  "thresholds": {
    "max_failure_threshold": 3,
    "emergency_halt_threshold": 10,
    "database_check_interval": 60
  }
}
```

### Log Monitoring

Monitor these log patterns for system health:

```bash
# Normal operation
grep "Preflight passed" logs/app.log

# Degraded mode warnings
grep "DEGRADED mode" logs/app.log

# Emergency situations
grep "EMERGENCY HALT" logs/app.log

# Database issues
grep "Database failure" logs/app.log
```

## Integration with State Manager

The StateManager now coordinates with the RiskManager for fallback cache maintenance:

```python
# Set up coordination
state_manager.set_risk_manager(risk_manager)

# Position updates automatically sync to fallback cache
state_manager.update_position(position_data)
# -> Automatically calls risk_manager.update_fallback_cache_position()
```

## Best Practices

### Deployment

1. **Monitor Thresholds**: Start with conservative thresholds and adjust based on experience
2. **Alert Setup**: Configure alerts for mode changes, especially EMERGENCY_HALT
3. **Health Checks**: Implement external monitoring of risk system status
4. **Recovery Procedures**: Document manual recovery procedures

### Operations

1. **Regular Monitoring**: Check `get_risk_system_status()` periodically
2. **Proactive Recovery**: Don't wait for emergency halt - investigate degraded mode
3. **Database Maintenance**: Address database issues promptly to prevent degradation
4. **Testing**: Regular testing of fallback mechanisms

### Example Monitoring Script

```python
#!/usr/bin/env python3
"""Risk system health monitor."""

import time
import logging
from your_bot import get_risk_manager

def monitor_risk_system():
    risk_manager = get_risk_manager()
    
    while True:
        status = risk_manager.get_risk_system_status()
        
        if status['mode'] != 'normal':
            logging.warning(f"Risk system in {status['mode']} mode")
            
            if status['mode'] == 'emergency_halt':
                logging.critical("EMERGENCY HALT - Manual intervention required")
                # Send alerts, notifications, etc.
                
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    monitor_risk_system()
```

## Error Scenarios and Responses

### Database Connection Loss

**Scenario**: Database server becomes unreachable

**Response**:
1. First 3 failures -> Continue with warnings
2. 3+ failures -> Switch to DEGRADED mode
3. 10+ failures -> EMERGENCY_HALT

**Recovery**: Automatic when database connectivity restored

### Database Corruption

**Scenario**: Database files corrupted, queries fail

**Response**:
1. Immediate error detection
2. Fast progression to EMERGENCY_HALT
3. Manual intervention required

**Recovery**: Fix database, then `clear_emergency_halt()`

### High Database Latency

**Scenario**: Database responds slowly, timeouts occur

**Response**:
1. Some operations may timeout and count as failures
2. Gradual degradation based on failure rate
3. May trigger DEGRADED mode if persistent

**Recovery**: Address database performance issues

### Memory Pressure

**Scenario**: System under memory pressure, fallback cache at risk

**Response**:
1. Fallback cache designed to be lightweight
2. Only essential data cached
3. Periodic cleanup of old data

**Recovery**: Monitor memory usage, optimize cache size if needed

## Implementation Details

### Thread Safety

The fallback system is designed for single-threaded operation but includes basic protection:

- Atomic updates to failure counters
- Consistent state management
- Safe mode transitions

### Performance Considerations

- **Minimal Overhead**: Fallback checks add minimal latency in NORMAL mode
- **Cache Efficiency**: In-memory cache provides fast access during DEGRADED mode
- **Recovery Throttling**: Database health checks are rate-limited to prevent spam

### Data Consistency

- **Best Effort**: Fallback cache provides best-effort consistency
- **Eventual Consistency**: System returns to full consistency when database recovers
- **Staleness**: Cache data may become stale during extended outages

## Testing

Comprehensive test suite covers:

- Cache functionality
- Mode transitions
- Recovery mechanisms
- Integration between components
- Edge cases and error scenarios

Run tests:
```bash
pytest tests/test_risk_fallback.py -v
```

## Security Considerations

1. **Data Exposure**: Fallback cache kept in memory only, not persisted
2. **Access Control**: Same access controls apply to fallback operations
3. **Audit Trail**: All mode changes and critical operations logged
4. **Recovery Security**: Manual recovery operations require appropriate permissions

## Future Enhancements

Potential improvements for future versions:

1. **Distributed Cache**: Redis-based fallback cache for multi-instance deployments
2. **Predictive Degradation**: ML-based prediction of database issues
3. **Advanced Recovery**: More sophisticated recovery strategies
4. **Real-time Monitoring**: Built-in monitoring dashboard
5. **Custom Thresholds**: Per-market or per-strategy failure thresholds

## Troubleshooting

### Common Issues

**Issue**: System stuck in DEGRADED mode
**Solution**: Check database connectivity, force health check, reset failure count

**Issue**: Frequent mode switching
**Solution**: Investigate intermittent database issues, adjust thresholds

**Issue**: Emergency halt triggered unexpectedly
**Solution**: Review logs for database errors, check system resources

### Diagnostic Commands

```python
# Check current status
status = risk_manager.get_risk_system_status()

# Force health check
risk_manager.force_database_check()

# Get cache statistics
cache_stats = risk_manager.fallback_cache.get_cache_stats()

# Reset system state
risk_manager.reset_database_failure_count()
```

This fallback system ensures that the trading bot can continue operating safely even during database outages, while providing clear visibility into system health and automatic recovery capabilities.
