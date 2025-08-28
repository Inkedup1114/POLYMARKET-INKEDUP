# Disaster Recovery Testing Guide for InkedUp Trading Bot

## Overview

This guide describes the comprehensive disaster recovery testing framework for validating the InkedUp Polymarket trading bot's ability to handle catastrophic failures and recover gracefully under extreme conditions.

## What is Disaster Recovery Testing?

Disaster recovery testing validates a system's ability to:
- **Detect** catastrophic failures quickly
- **Respond** to failures with appropriate fallback mechanisms  
- **Maintain** critical functionality during disasters
- **Recover** to normal operations after failures are resolved
- **Preserve** data integrity throughout the disaster lifecycle

Unlike standard error handling tests, disaster recovery testing simulates complete system breakdowns that could occur in production trading environments.

## Disaster Recovery Testing Framework

### Components

#### `test_disaster_recovery.py`
Main disaster recovery testing module containing:
- **DisasterScenario**: Base class for disaster simulations
- **DisasterRecoveryTester**: Comprehensive testing framework
- **TestDisasterRecoveryScenarios**: Core disaster scenario tests
- **TestSystemResilienceMetrics**: Resilience measurement tests

#### `scripts/run_disaster_recovery_tests.py`
Disaster recovery test runner with multiple execution modes:
- Quick tests for CI/CD validation
- Full disaster recovery test suite  
- Specific scenario testing
- Mean Time To Recovery (MTTR) focused tests
- System availability measurement tests

## Disaster Scenarios Covered

### 1. Database Corruption (`DatabaseCorruptionScenario`)
**Purpose**: Test system behavior when database becomes completely inaccessible or corrupted

**Scenario**: Complete database failure where all database operations fail
- **Simulation**: All DB methods return exceptions (connection lost, corruption, etc.)
- **Expected Behavior**: 
  - System detects database failure
  - Fallback systems activate immediately  
  - Operations continue using in-memory fallback
  - Data integrity maintained in fallback store
- **Recovery Test**: Database restoration and data synchronization
- **Success Criteria**: System continues operating with <5 second switching delay

**Real-World Context**: Database corruption from hardware failure, filesystem issues, or network storage problems.

### 2. Network Partition (`NetworkPartitionScenario`) 
**Purpose**: Test system behavior when network connectivity to trading APIs is lost

**Scenario**: Complete network isolation preventing all external API calls
- **Simulation**: All network calls to trading APIs fail with connection errors
- **Expected Behavior**:
  - System detects API connectivity loss
  - Switches to cached data for position information
  - Prevents new order placement (safety measure)
  - Maintains risk calculations using last known positions
- **Recovery Test**: Network restoration and reconnection to APIs
- **Success Criteria**: No data loss, graceful degradation of functionality

**Real-World Context**: Network outages, API server failures, firewall issues, or DDoS attacks.

### 3. Memory Exhaustion (`MemoryExhaustionScenario`)
**Purpose**: Test system behavior under extreme memory pressure conditions

**Scenario**: System runs out of available memory
- **Simulation**: Allocate large amounts of memory to trigger memory pressure
- **Expected Behavior**:
  - System detects memory pressure
  - Activates memory cleanup procedures
  - Reduces memory usage by purging non-critical caches
  - Continues core operations with minimal memory footprint
- **Recovery Test**: Memory cleanup and return to normal operations
- **Success Criteria**: System remains stable, no crashes, memory recovered

**Real-World Context**: Memory leaks, large market data bursts, or insufficient system resources.

### 4. Cascading Failures (`CascadingFailureScenario`)
**Purpose**: Test system behavior when multiple components fail in sequence

**Scenario**: Sequential failure of database, network, and WebSocket connections
- **Simulation**: 
  1. Database fails (connection lost)
  2. API network fails (compounds the problem)
  3. WebSocket connection fails (complete isolation)
- **Expected Behavior**:
  - System gracefully degrades with each failure
  - Fallback systems activate in stages
  - Emergency protocols engage for complete isolation
  - System maintains safe state throughout
- **Recovery Test**: Sequential restoration of components
- **Success Criteria**: System recovers fully, no data corruption

**Real-World Context**: Infrastructure failures that cascade across multiple systems, data center outages, or coordinated attacks.

## Running Disaster Recovery Tests

### Prerequisites
```bash
# Install testing dependencies
pip install pytest pytest-asyncio psutil

# Ensure project is properly installed
pip install -e .
```

### Quick Disaster Recovery Tests (CI/CD)
```bash
# Run essential disaster recovery tests
python scripts/run_disaster_recovery_tests.py --quick

# Or directly with pytest
python -m pytest tests/test_disaster_recovery.py -m disaster_recovery -k "database_corruption or network_partition"
```

### Full Disaster Recovery Suite
```bash
# Run comprehensive disaster recovery tests
python scripts/run_disaster_recovery_tests.py --full

# Or all disaster recovery tests with pytest
python -m pytest tests/test_disaster_recovery.py -m disaster_recovery -v
```

### Specific Disaster Scenarios
```bash
# Run specific scenarios only
python scripts/run_disaster_recovery_tests.py --scenarios database,network,cascading

# Run memory exhaustion test only
python -m pytest tests/test_disaster_recovery.py -k "memory_exhaustion"
```

### Mean Time To Recovery (MTTR) Testing
```bash
# Focus on recovery time measurements
python scripts/run_disaster_recovery_tests.py --mttr

# Generate MTTR metrics
python -m pytest tests/test_disaster_recovery.py::TestSystemResilienceMetrics::test_mean_time_to_recovery -v
```

### System Availability Testing
```bash
# Test system availability during disasters  
python scripts/run_disaster_recovery_tests.py --availability

# Measure availability percentage
python -m pytest tests/test_disaster_recovery.py::TestSystemResilienceMetrics::test_system_availability_during_disasters -v
```

### Generate Detailed Reports
```bash
# Generate comprehensive disaster recovery report
python scripts/run_disaster_recovery_tests.py --full --report
```

## Understanding Test Results

### Key Metrics

#### Recovery Metrics
- **Mean Time To Recovery (MTTR)**: Average time for system to recover from disasters
- **Recovery Success Rate**: Percentage of disasters system successfully recovers from
- **Data Integrity Score**: Percentage of data preserved through disasters
- **Availability During Disasters**: Percentage uptime during catastrophic failures

#### Performance Metrics  
- **Failure Detection Time**: How quickly system detects disasters
- **Fallback Activation Time**: Time to activate backup systems
- **Recovery Validation Time**: Time to verify system health after recovery

### Success Criteria

#### High-Availability Trading Requirements
- **MTTR**: ≤15 seconds for database failures, ≤30 seconds for cascading failures
- **System Availability**: ≥70% availability even during disasters (via fallback systems)
- **Data Integrity**: 100% preservation of critical trading data
- **Recovery Success Rate**: ≥80% automatic recovery from disasters
- **Failure Detection**: ≤5 seconds to detect critical system failures

#### Resilience Grades
- **EXCELLENT (A)**: ≥95% disaster recovery success rate
- **GOOD (B)**: ≥85% disaster recovery success rate  
- **ADEQUATE (C)**: ≥70% disaster recovery success rate
- **INADEQUATE (F)**: <70% disaster recovery success rate

### Interpreting Results

#### Sample Output
```
🔥 DISASTER RECOVERY TESTING SUMMARY
================================================================================

🎯 Quick Tests:
  test_database_corruption_recovery                  ✅ PASSED (3.2s)
  test_network_partition_recovery                   ✅ PASSED (2.8s)

🎯 Full Tests:
  test_memory_exhaustion_recovery                   ✅ PASSED (5.1s)
  test_cascading_failure_recovery                   ✅ PASSED (7.4s)
  test_comprehensive_disaster_recovery_suite        ✅ PASSED (12.3s)

================================================================================
Overall Result: 5/5 tests passed (100.0%)
🏆 EXCELLENT DISASTER RECOVERY CAPABILITIES!
✅ System is exceptionally resilient to catastrophic failures
================================================================================
```

## Troubleshooting Common Issues

### Low Recovery Success Rate
- **Database Fallback Issues**: Check fallback manager configuration and in-memory store
- **Network Recovery Problems**: Verify API client retry mechanisms and timeout settings
- **Memory Management**: Review memory cleanup procedures and garbage collection
- **Cascade Recovery**: Ensure proper component dependency management

### High Mean Time To Recovery (MTTR)
- **Slow Failure Detection**: Tune health check intervals and failure thresholds
- **Inefficient Fallback**: Optimize fallback system performance and data structures
- **Complex Recovery**: Simplify recovery procedures and remove unnecessary steps
- **Resource Contention**: Check for bottlenecks during recovery operations

### Poor System Availability
- **Insufficient Fallback Coverage**: Extend fallback systems to cover more operations
- **Aggressive Failure Thresholds**: Adjust thresholds to be less sensitive
- **Recovery Time Issues**: Improve recovery speed to minimize downtime
- **Cascade Prevention**: Better isolation between system components

## Advanced Disaster Recovery Testing

### Custom Disaster Scenarios
Create custom disaster scenarios by extending the `DisasterScenario` class:

```python
class CustomDisaster(DisasterScenario):
    def __init__(self):
        super().__init__(
            "Custom Disaster",
            "Description of custom failure scenario"
        )
    
    async def _execute_disaster(self, components):
        # Implement custom disaster simulation
        # Access system components: components['state_manager'], etc.
        pass
```

### Integration with Monitoring
Integrate disaster recovery testing with production monitoring:
- **Prometheus**: Export disaster recovery metrics
- **Grafana**: Create disaster recovery dashboards
- **PagerDuty**: Alert on disaster recovery test failures
- **DataDog**: Track disaster recovery trends over time

### Chaos Engineering Integration
Combine with chaos engineering tools:
- **Chaos Monkey**: Random component failures during trading
- **Gremlin**: Infrastructure-level fault injection
- **Litmus**: Kubernetes-based chaos testing
- **Pumba**: Docker container chaos testing

## Best Practices

### Test Environment
1. **Isolated Testing**: Run disaster recovery tests in dedicated environments
2. **Production-Like Data**: Use realistic data volumes and patterns
3. **Resource Monitoring**: Monitor system resources during disaster tests
4. **Baseline Metrics**: Establish performance baselines before disasters

### Test Design
1. **Realistic Disasters**: Model actual failure scenarios from production
2. **Gradual Escalation**: Start with single failures, progress to cascading
3. **Recovery Validation**: Ensure complete recovery, not just survival
4. **Data Integrity Checks**: Verify no data loss or corruption

### Continuous Testing
1. **Automated Scheduling**: Run disaster recovery tests regularly (weekly/monthly)
2. **Regression Tracking**: Monitor disaster recovery capabilities over time
3. **Failure Analysis**: Investigate and fix any disaster recovery failures
4. **Improvement Cycles**: Continuously improve disaster recovery based on results

## Integration with CI/CD

### GitHub Actions Integration
```yaml
# Add to .github/workflows/disaster-recovery.yml
name: Disaster Recovery Testing
on:
  schedule:
    - cron: '0 3 * * 1'  # Weekly on Monday at 3 AM
  workflow_dispatch:

jobs:
  disaster-recovery:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -e . pytest pytest-asyncio psutil
      - name: Run disaster recovery tests
        run: python scripts/run_disaster_recovery_tests.py --quick --report
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: disaster-recovery-results
          path: DISASTER_RECOVERY_TESTING_REPORT.md
```

### Production Monitoring
- **Failure Rate Alerting**: Alert when disaster recovery tests fail
- **MTTR Trending**: Track recovery time improvements over releases
- **Availability Dashboards**: Monitor system availability during disasters
- **Capacity Planning**: Use disaster test results for infrastructure planning

This comprehensive disaster recovery testing framework ensures the InkedUp trading bot can survive and recover from catastrophic failures that could occur in production high-frequency trading environments.