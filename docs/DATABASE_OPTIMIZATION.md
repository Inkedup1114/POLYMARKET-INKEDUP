# Database Optimization and Index Strategy

This document outlines the comprehensive database optimization strategy implemented in the InkedUp Polymarket trading bot, including indexing best practices, performance monitoring, and query optimization techniques.

## Overview

The database optimization system provides:
- **Comprehensive Index Coverage**: Strategic indexes for all common query patterns
- **Performance Monitoring**: Real-time query performance tracking and analysis
- **Query Caching**: Intelligent caching system for frequently accessed data
- **Optimization Analysis**: Automated recommendations for index improvements
- **Production-Ready Monitoring**: Detailed performance metrics and alerting

## Database Schema and Indexing Strategy

### Core Tables and Their Optimization

#### 1. Orders Table
**Primary Use Cases**: Order tracking, status updates, market analysis

**Existing Indexes**:
```sql
CREATE INDEX idx_orders_token ON orders(token_id);
CREATE INDEX idx_orders_market ON orders(market_slug);
CREATE INDEX idx_orders_status ON orders(status);
```

**Optimized Indexes**:
```sql
-- Compound index for status + timestamp queries
CREATE INDEX idx_orders_status_created_at ON orders(status, created_at);

-- Compound index for token + status queries
CREATE INDEX idx_orders_token_status ON orders(token_id, status);

-- Compound index for market + status queries  
CREATE INDEX idx_orders_market_status ON orders(market_slug, status);

-- Partial index for active orders
CREATE INDEX idx_orders_open_status ON orders(created_at) WHERE status = 'OPEN';
```

**Query Patterns Optimized**:
- `SELECT * FROM orders WHERE token_id = ? AND status = ?`
- `SELECT * FROM orders WHERE status = 'OPEN' ORDER BY created_at`
- `SELECT * FROM orders WHERE market_slug = ? AND status IN ('OPEN', 'FILLED')`

#### 2. Positions Table
**Primary Use Cases**: Portfolio tracking, exposure calculation, position management

**Existing Indexes**:
```sql
CREATE INDEX idx_positions_market ON positions(market_slug);
```

**Optimized Indexes**:
```sql
-- Compound index for market + outcome analysis
CREATE INDEX idx_positions_market_outcome ON positions(market_slug, outcome_type);

-- Index for outcome + update time queries
CREATE INDEX idx_positions_outcome_updated ON positions(outcome_type, updated_at);

-- Partial index for positions with significant notional value
CREATE INDEX idx_positions_nonzero ON positions(market_slug, notional_value) 
WHERE ABS(notional_value) > 0;
```

**Query Patterns Optimized**:
- `SELECT * FROM positions WHERE market_slug = ? GROUP BY outcome_type`
- `SELECT SUM(notional_value) FROM positions WHERE outcome_type = ?`
- `SELECT * FROM positions WHERE market_slug = ? AND ABS(notional_value) > 0`

#### 3. Trades Table
**Primary Use Cases**: Trade history, execution analysis, performance tracking

**Existing Indexes**:
```sql
CREATE INDEX idx_trades_order ON trades(order_id);
CREATE INDEX idx_trades_token ON trades(token_id);
```

**Optimized Indexes**:
```sql
-- Compound index for token + execution time
CREATE INDEX idx_trades_token_executed ON trades(token_id, executed_at);

-- Descending index for recent trades
CREATE INDEX idx_trades_executed_at_desc ON trades(executed_at DESC);
```

**Query Patterns Optimized**:
- `SELECT * FROM trades WHERE token_id = ? ORDER BY executed_at DESC`
- `SELECT * FROM trades WHERE executed_at > ? ORDER BY executed_at DESC`

#### 4. Market Snapshots Table
**Primary Use Cases**: Market data analysis, historical trends, liquidity tracking

**Existing Indexes**:
```sql
CREATE INDEX idx_market_snapshots_token ON market_snapshots(token_id);
```

**Optimized Indexes**:
```sql
-- Compound index for token + snapshot time
CREATE INDEX idx_market_snapshots_token_snapshot ON market_snapshots(token_id, snapshot_at);

-- Compound index for market + snapshot time
CREATE INDEX idx_market_snapshots_market_snapshot ON market_snapshots(market_slug, snapshot_at);
```

#### 5. Outcome Exposures Table
**Primary Use Cases**: Risk management, exposure tracking, correlation analysis

**Existing Indexes**:
```sql
CREATE INDEX idx_outcome_exposures_market ON outcome_exposures(market_slug);
CREATE INDEX idx_outcome_exposures_outcome ON outcome_exposures(outcome_id);
CREATE INDEX idx_outcome_exposures_updated ON outcome_exposures(last_updated);
```

**Optimized Indexes**:
```sql
-- Compound index for market + update time
CREATE INDEX idx_outcome_exposures_market_updated ON outcome_exposures(market_slug, last_updated);

-- Compound index for outcome + update time
CREATE INDEX idx_outcome_exposures_outcome_updated ON outcome_exposures(outcome_id, last_updated);
```

## Performance Monitoring System

### Query Performance Tracking

The `OptimizedDatabaseManager` provides comprehensive query performance monitoring:

```python
from inkedup_bot.database_optimized import OptimizedDatabaseManager

# Initialize with monitoring enabled
db_manager = OptimizedDatabaseManager(
    db_path="bot_data.db",
    enable_monitoring=True,
    slow_query_threshold=0.1,  # 100ms threshold
    metrics_retention_hours=24
)

# Execute monitored queries
result = await db_manager.execute_monitored_query(
    "SELECT * FROM positions WHERE market_slug = ?",
    ("market_slug",),
    cache_key="positions_market_slug"  # Optional caching
)

# Get performance statistics  
stats = db_manager.get_performance_stats()
```

### Key Performance Metrics

1. **Query Execution Metrics**:
   - Total queries executed
   - Average query execution time
   - Slow query count and identification
   - Query error tracking

2. **Cache Performance**:
   - Cache hit/miss ratios
   - Cache size and TTL management
   - Cache effectiveness analysis

3. **Connection Management**:
   - Active connection count
   - Connection pool utilization
   - Connection establishment time

### Performance Analysis Report

Generate comprehensive performance reports:

```python
# Generate detailed analysis
report = await db_manager.analyze_performance()
print(report)
```

Example output:
```
DATABASE PERFORMANCE ANALYSIS
========================================
Generated: 2024-08-24 15:30:45

PERFORMANCE SUMMARY:
--------------------
Total queries executed: 1,247
Average query time: 12.3ms
Slow queries (>100ms): 15
Query errors: 0
Cache hit ratio: 78.5%

TOP SLOW QUERIES:
-----------------
1. SELECT * FROM trades WHERE token_id = ? ORDER BY executed_at DESC
   Avg: 156.2ms, Max: 342.1ms
   Executions: 89, Slow: 23

2. SELECT SUM(notional_value) FROM positions WHERE market_slug = ?
   Avg: 134.7ms, Max: 198.3ms
   Executions: 156, Slow: 45
```

## Index Optimization Recommendations

### Automated Index Analysis

The `DatabaseAnalyzer` provides automated index optimization recommendations:

```python
from inkedup_bot.database_analyzer import DatabaseAnalyzer

analyzer = DatabaseAnalyzer(db_manager)
analysis = await analyzer.analyze_database()

# Get optimization report
report = await analyzer.generate_optimization_report()
```

### Priority-Based Recommendations

Recommendations are categorized by priority:

**High Priority (1)**:
- Indexes for frequent queries with high execution counts
- Missing indexes for slow queries
- Compound indexes for common WHERE clauses

**Medium Priority (2)**:
- Indexes for moderately frequent queries
- Optimization of existing index structures
- Performance improvements for specific use cases

**Low Priority (3)**:
- Indexes for infrequent but potentially slow queries
- Redundant index cleanup recommendations
- Advanced optimization opportunities

### Example Recommendations

```sql
-- HIGH PRIORITY
CREATE INDEX idx_orders_market_status ON orders(market_slug, status);
-- Reason: Frequent WHERE clause on market_slug, status (frequency: 85)

CREATE INDEX idx_positions_outcome_updated ON positions(outcome_type, updated_at);
-- Reason: WHERE + ORDER BY optimization on outcome_type, updated_at

-- MEDIUM PRIORITY  
CREATE INDEX idx_trades_executed_at_desc ON trades(executed_at DESC);
-- Reason: Frequent ORDER BY clause on executed_at (frequency: 45)
```

## Query Optimization Best Practices

### 1. Index Design Principles

**Column Order in Compound Indexes**:
```sql
-- Good: Most selective column first
CREATE INDEX idx_orders_status_token ON orders(status, token_id);

-- Less optimal: Less selective column first  
CREATE INDEX idx_orders_token_status ON orders(token_id, status);
```

**Use Partial Indexes for Filtered Queries**:
```sql
-- Efficient for queries filtering on active orders
CREATE INDEX idx_orders_open ON orders(created_at) WHERE status = 'OPEN';

-- Better than full index for sparse data
CREATE INDEX idx_positions_nonzero ON positions(market_slug, notional_value) 
WHERE ABS(notional_value) > 0;
```

### 2. Query Pattern Optimization

**Optimize WHERE Clauses**:
```python
# Good: Uses compound index efficiently
SELECT * FROM orders 
WHERE market_slug = ? AND status = 'OPEN'
ORDER BY created_at DESC;

# Less optimal: Requires separate lookups
SELECT * FROM orders WHERE market_slug = ?
UNION ALL
SELECT * FROM orders WHERE status = 'OPEN';
```

**Use Appropriate JOINs**:
```python
# Good: Efficient JOIN with proper indexes
SELECT o.*, p.notional_value
FROM orders o
JOIN positions p ON o.token_id = p.token_id
WHERE o.market_slug = ?;

# Less optimal: Separate queries
orders = await db.execute("SELECT * FROM orders WHERE market_slug = ?", (market,))
for order in orders:
    position = await db.execute("SELECT * FROM positions WHERE token_id = ?", (order.token_id,))
```

### 3. Caching Strategies

**Cache Frequently Accessed Data**:
```python
# Cache expensive aggregations
total_exposure = await db_manager.execute_monitored_query(
    "SELECT SUM(ABS(notional_value)) FROM positions",
    cache_key="total_exposure"
)

# Cache market summaries
market_data = await db_manager.execute_monitored_query(
    "SELECT * FROM positions WHERE market_slug = ?",
    (market_slug,),
    cache_key=f"positions_market_{market_slug}"
)
```

**Cache Invalidation Strategy**:
- Time-based TTL (5 minutes for market data)
- Event-based invalidation (on position updates)
- LRU eviction for memory management

## Production Deployment Guidelines

### 1. Index Creation Strategy

**Gradual Index Rollout**:
```python
# Create indexes during maintenance windows
# Monitor system impact during creation
async def deploy_indexes_gradually():
    indexes = get_high_priority_indexes()
    for index_sql in indexes:
        print(f"Creating index: {index_sql}")
        await db.execute(index_sql)
        await asyncio.sleep(1)  # Allow system to recover
```

**Index Validation**:
```python
# Validate index effectiveness after creation
async def validate_index_performance():
    analyzer = DatabaseAnalyzer(db_manager)
    
    # Benchmark queries before and after index creation
    queries = get_common_query_patterns()
    before_times = await analyzer.benchmark_query_performance(queries)
    
    await create_optimized_indexes()
    
    after_times = await analyzer.benchmark_query_performance(queries)
    
    # Compare performance improvements
    for query, before_time in before_times.items():
        after_time = after_times[query]
        improvement = (before_time - after_time) / before_time * 100
        print(f"Query improvement: {improvement:.1f}% faster")
```

### 2. Monitoring and Alerting

**Performance Thresholds**:
```python
# Configure appropriate thresholds for production
PRODUCTION_THRESHOLDS = {
    'slow_query_threshold': 0.2,  # 200ms
    'error_rate_threshold': 0.01,  # 1% error rate
    'cache_hit_ratio_min': 0.7,   # 70% cache hit ratio
}

# Set up alerting
async def check_performance_thresholds():
    stats = db_manager.get_performance_stats()
    db_stats = stats['database_stats']
    
    if db_stats['avg_query_time'] > PRODUCTION_THRESHOLDS['slow_query_threshold']:
        send_alert("High average query time detected")
    
    if db_stats['cache_hit_ratio'] < PRODUCTION_THRESHOLDS['cache_hit_ratio_min']:
        send_alert("Low cache hit ratio detected")
```

**Automated Reporting**:
```python
# Daily performance reports
async def generate_daily_report():
    report = await db_manager.analyze_performance()
    
    # Extract key metrics
    stats = db_manager.get_performance_stats()
    
    # Send to monitoring system
    metrics = {
        'total_queries': stats['database_stats']['total_queries'],
        'avg_query_time': stats['database_stats']['avg_query_time'],
        'slow_queries': stats['database_stats']['slow_queries'],
        'cache_hit_ratio': stats['database_stats']['cache_hit_ratio']
    }
    
    send_metrics_to_monitoring(metrics)
```

### 3. Capacity Planning

**Database Growth Monitoring**:
```python
async def monitor_database_growth():
    # Track table sizes
    table_sizes = await get_table_sizes()
    
    # Project growth rates
    growth_rates = calculate_growth_rates(table_sizes)
    
    # Alert on rapid growth
    for table, rate in growth_rates.items():
        if rate > GROWTH_THRESHOLD:
            send_alert(f"Rapid growth in {table}: {rate}% per day")
```

**Index Maintenance**:
```python
# Regular index analysis and optimization
async def periodic_index_maintenance():
    analyzer = DatabaseAnalyzer(db_manager)
    analysis = await analyzer.analyze_database()
    
    # Identify redundant indexes
    if analysis.redundant_indexes:
        for redundant in analysis.redundant_indexes:
            print(f"Consider removing redundant index: {redundant}")
    
    # Apply new recommendations
    high_priority = [r for r in analysis.missing_indexes if r.priority == 1]
    for rec in high_priority:
        if rec.estimated_benefit > BENEFIT_THRESHOLD:
            await create_recommended_index(rec)
```

## Testing and Validation

### Performance Testing Framework

Run the comprehensive test suite to validate optimizations:

```bash
# Run database optimization tests
pytest tests/test_database_optimization.py -v

# Run specific test categories
pytest tests/test_database_optimization.py::TestDatabaseOptimization -v
pytest tests/test_database_optimization.py::TestDatabaseAnalyzer -v
pytest tests/test_database_optimization.py::TestIndexOptimizationIntegration -v
```

### Benchmarking

```python
# Benchmark query performance
from tests.test_database_optimization import TestIndexOptimizationIntegration

async def benchmark_production_queries():
    # Set up test environment with realistic data
    test_suite = TestIndexOptimizationIntegration()
    manager = await test_suite.full_system().__aenter__()
    
    # Run performance benchmarks
    await test_suite.test_comprehensive_optimization_workflow(manager)
    await test_suite.test_index_impact_on_query_performance(manager)
    
    # Generate performance report
    report = await manager.analyze_performance()
    print(report)
```

## Troubleshooting Common Issues

### Slow Query Analysis

1. **Identify Slow Queries**:
```python
stats = db_manager.get_performance_stats()
slow_queries = stats['top_slow_queries']

for query in slow_queries[:5]:
    print(f"Slow query: {query['sql']}")
    print(f"Average time: {query['avg_time']*1000:.1f}ms")
    print(f"Executions: {query['execution_count']}")
```

2. **Analyze Query Plans**:
```python
# Use EXPLAIN QUERY PLAN to understand query execution
async with db_manager.connection() as db:
    async with db.execute("EXPLAIN QUERY PLAN SELECT * FROM orders WHERE token_id = ?") as cursor:
        plan = await cursor.fetchall()
        for row in plan:
            print(row)
```

3. **Verify Index Usage**:
```python
# Check if queries are using expected indexes
async def verify_index_usage():
    # This would show in the query plan
    await db.execute("EXPLAIN QUERY PLAN SELECT * FROM orders WHERE market_slug = ? AND status = ?")
    # Should show: SEARCH TABLE orders USING INDEX idx_orders_market_status
```

### Cache Performance Issues

1. **Low Cache Hit Ratio**:
- Review cache TTL settings
- Identify cache-worthy queries
- Implement proper cache keys

2. **Memory Usage**:
- Monitor cache size growth
- Implement proper eviction policies
- Adjust max cache size

### Index Maintenance

1. **Index Bloat**:
- Monitor index size growth
- Implement periodic VACUUM operations
- Consider index rebuilding for large tables

2. **Redundant Indexes**:
- Use DatabaseAnalyzer to identify redundant indexes
- Remove unused indexes to save space and maintenance overhead

## Conclusion

This comprehensive database optimization strategy provides:

1. **Strategic Index Coverage** - Optimized indexes for all common query patterns
2. **Real-time Monitoring** - Continuous performance tracking and analysis  
3. **Automated Optimization** - AI-driven recommendations for improvements
4. **Production Readiness** - Battle-tested monitoring and alerting systems
5. **Scalable Architecture** - Design patterns that scale with data growth

The implementation ensures optimal database performance while maintaining the flexibility to adapt to changing query patterns and data growth over time.