"""
Database optimization demonstration script.
Shows the performance monitoring and index optimization features.
"""

import asyncio
import logging
import sys
import tempfile
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from inkedup_bot.database_analyzer import DatabaseAnalyzer
from inkedup_bot.database_optimized import OptimizedDatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
log = logging.getLogger("db_optimization_demo")


async def demo_database_optimization():
    """Comprehensive demonstration of database optimization features."""
    log.info("=== Database Optimization Demo ===")

    # Create temporary database
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
        db_path = tmp_file.name

    try:
        # Initialize optimized database manager
        log.info("Initializing optimized database manager...")
        db_manager = OptimizedDatabaseManager(
            db_path=db_path,
            enable_monitoring=True,
            slow_query_threshold=0.01,  # 10ms threshold
            metrics_retention_hours=1,
        )

        await db_manager.initialize()
        log.info("✓ Database initialized with optimized indexes")

        # Demo 1: Show existing indexes
        await demo_existing_indexes(db_manager)

        # Demo 2: Insert test data
        await demo_data_insertion(db_manager)

        # Demo 3: Performance monitoring
        await demo_performance_monitoring(db_manager)

        # Demo 4: Query caching
        await demo_query_caching(db_manager)

        # Demo 5: Database analysis
        await demo_database_analysis(db_manager)

        # Demo 6: Performance statistics
        await demo_performance_statistics(db_manager)

        await db_manager.close()
        log.info("✓ Demo completed successfully!")

    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)


async def demo_existing_indexes(db_manager):
    """Demonstrate existing index analysis."""
    log.info("\n=== Demo 1: Existing Index Analysis ===")

    analyzer = DatabaseAnalyzer(db_manager)
    existing_indexes = await analyzer._analyze_existing_indexes()

    log.info("Existing indexes by table:")
    for table_name, indexes in existing_indexes.items():
        log.info(f"  {table_name}: {len(indexes)} indexes")
        for index in indexes[:3]:  # Show first 3 indexes per table
            columns = ", ".join(index.get("columns", []))
            unique_str = " [UNIQUE]" if index.get("is_unique") else ""
            log.info(f"    - {index['name']}: ({columns}){unique_str}")


async def demo_data_insertion(db_manager):
    """Demonstrate data insertion with validation."""
    log.info("\n=== Demo 2: Data Insertion ===")

    # Insert orders
    log.info("Inserting test orders...")
    for i in range(20):
        order = {
            "id": f"demo_order_{i}",
            "token_id": f"token_{i % 5}",  # 5 different tokens
            "market_slug": f"market_{i % 3}",  # 3 different markets
            "side": "BUY" if i % 2 == 0 else "SELL",
            "price": round(0.1 + (i % 9) * 0.1, 2),  # Price range 0.1 to 1.0
            "size": 10.0 + i,
            "status": ["OPEN", "FILLED", "CANCELLED"][i % 3],
        }
        await db_manager.insert_order(order)

    # Insert positions
    log.info("Inserting test positions...")
    for i in range(10):
        position = {
            "token_id": f"token_{i % 5}",
            "market_slug": f"market_{i % 3}",
            "outcome_type": "YES" if i % 2 == 0 else "NO",
            "size": 50.0 + i * 5,
            "notional_value": 25.0 + i * 2.5,
        }
        await db_manager.upsert_position(position)

    # Insert outcome exposures
    log.info("Inserting test outcome exposures...")
    for i in range(8):
        exposure_data = {
            "market_slug": f"market_{i % 3}",
            "outcome_id": f"outcome_{i}",
            "outcome_name": f"Test Outcome {i}",
            "position_size": 100.0 + i * 10,
            "notional_value": 50.0 + i * 5,
            "average_price": round(0.4 + i * 0.05, 2),
            "current_price": round(0.45 + i * 0.05, 2),
            "unrealized_pnl": i * 2.5,
            "realized_pnl": i * 1.0,
        }
        await db_manager.upsert_outcome_exposure(**exposure_data)

    log.info("✓ Test data inserted successfully")


async def demo_performance_monitoring(db_manager):
    """Demonstrate query performance monitoring."""
    log.info("\n=== Demo 3: Performance Monitoring ===")

    # Execute various monitored queries
    queries = [
        ("SELECT * FROM orders WHERE token_id = ?", ("token_1",)),
        ("SELECT * FROM orders WHERE market_slug = ?", ("market_1",)),
        ("SELECT * FROM orders WHERE status = ?", ("OPEN",)),
        ("SELECT * FROM positions WHERE market_slug = ?", ("market_0",)),
        ("SELECT * FROM positions WHERE outcome_type = ?", ("YES",)),
        ("SELECT COUNT(*) FROM orders", ()),
    ]

    log.info("Executing monitored queries...")
    for sql, params in queries:
        result = await db_manager.execute_monitored_query(sql, params)
        log.info(
            f"  Query returned {len(result) if isinstance(result, list) else 1} results"
        )

    # Show some metrics
    stats = db_manager.get_performance_stats()
    db_stats = stats["database_stats"]
    log.info(f"✓ Executed {db_stats['total_queries']} queries")
    log.info(f"  Average query time: {db_stats['avg_query_time']*1000:.1f}ms")
    log.info(f"  Slow queries: {db_stats['slow_queries']}")


async def demo_query_caching(db_manager):
    """Demonstrate query caching capabilities."""
    log.info("\n=== Demo 4: Query Caching ===")

    # Execute same query multiple times with caching
    cache_key = "demo_cache_key"
    query = "SELECT * FROM positions WHERE market_slug = ?"
    params = ("market_1",)

    # First execution (cache miss)
    start_time = time.perf_counter()
    result1 = await db_manager.execute_monitored_query(
        query, params, cache_key=cache_key
    )
    first_time = time.perf_counter() - start_time

    # Second execution (cache hit)
    start_time = time.perf_counter()
    result2 = await db_manager.execute_monitored_query(
        query, params, cache_key=cache_key
    )
    second_time = time.perf_counter() - start_time

    # Verify results are identical
    assert result1 == result2

    # Show cache statistics
    stats = db_manager.get_performance_stats()
    cache_stats = stats["cache_stats"]
    db_stats = stats["database_stats"]

    log.info("✓ Cache demonstration completed")
    log.info(f"  First query time: {first_time*1000:.2f}ms")
    log.info(f"  Second query time: {second_time*1000:.2f}ms")
    log.info(f"  Cache hits: {db_stats['cache_hits']}")
    log.info(f"  Cache hit ratio: {db_stats['cache_hit_ratio']*100:.1f}%")
    log.info(f"  Cached entries: {cache_stats['cached_entries']}")


async def demo_database_analysis(db_manager):
    """Demonstrate comprehensive database analysis."""
    log.info("\n=== Demo 5: Database Analysis ===")

    analyzer = DatabaseAnalyzer(db_manager)

    # Perform full analysis
    log.info("Performing comprehensive database analysis...")
    analysis = await analyzer.analyze_database()

    log.info("✓ Analysis completed")
    log.info(
        f"  Existing indexes: {sum(len(indexes) for indexes in analysis.existing_indexes.values())}"
    )
    log.info(f"  Missing index recommendations: {len(analysis.missing_indexes)}")
    log.info(f"  Potentially redundant indexes: {len(analysis.redundant_indexes)}")
    log.info(f"  Performance issues identified: {len(analysis.performance_issues)}")

    # Show top recommendations
    if analysis.missing_indexes:
        log.info("\n  Top index recommendations:")
        high_priority = [r for r in analysis.missing_indexes if r.priority == 1][:3]
        for i, rec in enumerate(high_priority, 1):
            cols = ", ".join(rec.columns)
            log.info(f"    {i}. {rec.table_name}({cols}) - {rec.reason[:50]}...")

    # Generate optimization report
    log.info("\nGenerating optimization report...")
    report = await analyzer.generate_optimization_report()

    # Show key sections of the report
    lines = report.split("\n")
    summary_start = next(
        i for i, line in enumerate(lines) if "RECOMMENDATIONS SUMMARY" in line
    )
    summary_lines = lines[summary_start : summary_start + 10]

    log.info("✓ Optimization report generated")
    for line in summary_lines:
        if line.strip():
            log.info(f"  {line}")


async def demo_performance_statistics(db_manager):
    """Demonstrate detailed performance statistics."""
    log.info("\n=== Demo 6: Performance Statistics ===")

    # Execute more queries to build statistics
    log.info("Building performance statistics...")

    # Execute various patterns multiple times
    patterns = [
        ("SELECT * FROM orders WHERE token_id = ?", "token_0"),
        ("SELECT * FROM orders WHERE token_id = ?", "token_1"),
        ("SELECT * FROM orders WHERE token_id = ?", "token_2"),
        ("SELECT * FROM positions WHERE market_slug = ?", "market_0"),
        ("SELECT * FROM positions WHERE market_slug = ?", "market_1"),
        ("SELECT COUNT(*) FROM orders WHERE status = ?", "OPEN"),
    ]

    # Execute each pattern multiple times
    for _ in range(5):
        for sql, param in patterns:
            await db_manager.execute_monitored_query(sql, (param,))

    # Get comprehensive statistics
    stats = db_manager.get_performance_stats()

    log.info("✓ Performance statistics:")
    log.info(f"  Total queries: {stats['database_stats']['total_queries']}")
    log.info(
        f"  Average query time: {stats['database_stats']['avg_query_time']*1000:.2f}ms"
    )
    log.info(f"  Slow queries: {stats['database_stats']['slow_queries']}")
    log.info(f"  Query errors: {stats['database_stats']['query_errors']}")
    log.info(
        f"  Cache hit ratio: {stats['database_stats']['cache_hit_ratio']*100:.1f}%"
    )

    # Show most frequent queries
    if stats["most_frequent_queries"]:
        log.info("\n  Most frequent queries:")
        for i, query in enumerate(stats["most_frequent_queries"][:3], 1):
            sql_preview = (
                query["sql"][:50] + "..." if len(query["sql"]) > 50 else query["sql"]
            )
            log.info(f"    {i}. {sql_preview}")
            log.info(
                f"       Executions: {query['execution_count']}, Avg time: {query['avg_time']*1000:.1f}ms"
            )

    # Generate performance analysis report
    log.info("\nGenerating performance analysis report...")
    analysis_report = await db_manager.analyze_performance()

    # Show summary section
    lines = analysis_report.split("\n")
    summary_start = next(
        i for i, line in enumerate(lines) if "PERFORMANCE SUMMARY" in line
    )
    summary_end = next(
        i
        for i, line in enumerate(lines[summary_start:], summary_start)
        if line.startswith("TOP SLOW QUERIES") or line == ""
    )

    log.info("✓ Performance analysis summary:")
    for line in lines[summary_start:summary_end]:
        if line.strip():
            log.info(f"  {line}")


async def main():
    """Run the complete database optimization demonstration."""
    try:
        await demo_database_optimization()
    except Exception as e:
        log.error(f"Demo failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
