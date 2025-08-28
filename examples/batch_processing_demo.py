#!/usr/bin/env python3
"""
Comprehensive Batch Processing Demo for InkedUp Bot

This demo showcases the advanced batch processing capabilities including:
- Batch inserts, updates, and queries
- Transaction optimization
- Query optimization with caching
- Real-time monitoring and metrics
- Performance analysis and recommendations
"""

import asyncio
import os
import random
import sys
import time
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from inkedup_bot.batch_monitoring import (
    BatchMonitor,
    MonitoringConfig,
    initialize_batch_monitoring,
    print_performance_dashboard,
)
from inkedup_bot.batch_processor import BatchConfig, BatchPriority, BatchStrategy
from inkedup_bot.database_batched import BatchedDatabaseManager
from inkedup_bot.query_optimizer import QueryOptimizer
from inkedup_bot.transaction_optimizer import (
    TransactionOptimizer,
)


async def generate_sample_data(count: int = 1000) -> dict:
    """Generate sample trading data for testing batch operations."""
    print(f"Generating {count} sample records...")

    markets = [f"market_{i}" for i in range(10)]
    tokens = [f"token_{i}" for i in range(50)]
    sides = ["BUY", "SELL"]
    statuses = ["OPEN", "FILLED", "PARTIALLY_FILLED", "CANCELLED"]
    outcome_types = ["YES", "NO"]

    orders = []
    positions = []
    trades = []

    for i in range(count):
        market = random.choice(markets)
        token = random.choice(tokens)
        side = random.choice(sides)
        price = random.uniform(0.01, 0.99)
        size = random.uniform(10, 1000)

        # Generate order
        order = {
            "id": f"order_{i}_{int(time.time() * 1000)}",
            "token_id": token,
            "market_slug": market,
            "side": side,
            "price": price,
            "size": size,
            "status": random.choice(statuses),
            "notional_value": price * size,
            "outcome_type": random.choice(outcome_types),
        }
        orders.append(order)

        # Generate position (60% chance)
        if random.random() < 0.6:
            position = {
                "token_id": token,
                "market_slug": market,
                "size": size if side == "BUY" else -size,
                "notional_value": price * size,
                "outcome_type": random.choice(outcome_types),
                "side": side,
            }
            positions.append(position)

        # Generate trade (40% chance)
        if random.random() < 0.4:
            trade = {
                "id": f"trade_{i}_{int(time.time() * 1000)}",
                "order_id": order["id"],
                "token_id": token,
                "market_slug": market,
                "side": side,
                "price": price,
                "size": random.uniform(10, size),
                "fee": random.uniform(0.1, 2.0),
                "outcome_type": random.choice(outcome_types),
            }
            trades.append(trade)

    return {"orders": orders, "positions": positions, "trades": trades}


async def demonstrate_batch_inserts(
    db_manager: BatchedDatabaseManager, sample_data: dict
):
    """Demonstrate batch insert operations."""
    print("\n🔄 BATCH INSERT OPERATIONS DEMO")
    print("-" * 60)

    # Batch insert orders
    start_time = time.time()
    success = await db_manager.batch_insert_orders(
        sample_data["orders"], priority=BatchPriority.HIGH
    )
    orders_time = time.time() - start_time

    print(f"✅ Batch inserted {len(sample_data['orders'])} orders: {success}")
    print(
        f"   Time: {orders_time:.2f}s ({len(sample_data['orders'])/orders_time:.1f} ops/sec)"
    )

    # Batch insert positions
    start_time = time.time()
    success = await db_manager.batch_insert_positions(
        sample_data["positions"], priority=BatchPriority.NORMAL
    )
    positions_time = time.time() - start_time

    print(f"✅ Batch inserted {len(sample_data['positions'])} positions: {success}")
    print(
        f"   Time: {positions_time:.2f}s ({len(sample_data['positions'])/positions_time:.1f} ops/sec)"
    )

    # Batch insert trades
    start_time = time.time()
    success = await db_manager.batch_insert_trades(
        sample_data["trades"], priority=BatchPriority.HIGH
    )
    trades_time = time.time() - start_time

    print(f"✅ Batch inserted {len(sample_data['trades'])} trades: {success}")
    print(
        f"   Time: {trades_time:.2f}s ({len(sample_data['trades'])/trades_time:.1f} ops/sec)"
    )

    total_time = orders_time + positions_time + trades_time
    total_ops = (
        len(sample_data["orders"])
        + len(sample_data["positions"])
        + len(sample_data["trades"])
    )

    print("\n📊 BATCH INSERT SUMMARY:")
    print(f"   Total Operations: {total_ops:,}")
    print(f"   Total Time: {total_time:.2f}s")
    print(f"   Average Throughput: {total_ops/total_time:.1f} ops/sec")


async def demonstrate_batch_updates(
    db_manager: BatchedDatabaseManager, sample_data: dict
):
    """Demonstrate batch update operations."""
    print("\n🔄 BATCH UPDATE OPERATIONS DEMO")
    print("-" * 60)

    # Create batch order updates
    order_updates = []
    for i, order in enumerate(sample_data["orders"][:100]):  # Update first 100 orders
        if i % 3 == 0:
            update_data = {"status": "FILLED", "filled_at": datetime.now()}
        elif i % 3 == 1:
            update_data = {"status": "PARTIALLY_FILLED", "size": order["size"] * 0.7}
        else:
            update_data = {"status": "CANCELLED"}

        order_updates.append((order["id"], update_data))

    start_time = time.time()
    success = await db_manager.batch_update_orders(
        order_updates, priority=BatchPriority.HIGH
    )
    update_time = time.time() - start_time

    print(f"✅ Batch updated {len(order_updates)} orders: {success}")
    print(f"   Time: {update_time:.2f}s ({len(order_updates)/update_time:.1f} ops/sec)")

    # Batch update outcome prices
    price_updates = []
    for i in range(50):
        price_updates.append(
            {
                "token_id": f"token_{i}",
                "market_slug": f"market_{i % 10}",
                "price": random.uniform(0.01, 0.99),
            }
        )

    start_time = time.time()
    success = await db_manager.batch_update_outcome_prices(
        price_updates, priority=BatchPriority.CRITICAL
    )
    price_update_time = time.time() - start_time

    print(f"✅ Batch updated {len(price_updates)} outcome prices: {success}")
    print(
        f"   Time: {price_update_time:.2f}s ({len(price_updates)/price_update_time:.1f} ops/sec)"
    )


async def demonstrate_batch_queries(
    db_manager: BatchedDatabaseManager, sample_data: dict
):
    """Demonstrate optimized batch query operations."""
    print("\n🔍 BATCH QUERY OPERATIONS DEMO")
    print("-" * 60)

    # Batch get orders
    order_ids = [order["id"] for order in sample_data["orders"][:50]]
    start_time = time.time()
    retrieved_orders = await db_manager.batch_get_orders(order_ids)
    query_time = time.time() - start_time

    print(
        f"✅ Batch retrieved {len(retrieved_orders)} orders from {len(order_ids)} requested"
    )
    print(f"   Time: {query_time:.3f}s ({len(order_ids)/query_time:.1f} ops/sec)")

    # Batch get positions
    token_ids = [f"token_{i}" for i in range(20)]
    start_time = time.time()
    retrieved_positions = await db_manager.batch_get_positions(token_ids)
    position_query_time = time.time() - start_time

    print(
        f"✅ Batch retrieved {len(retrieved_positions)} positions from {len(token_ids)} tokens"
    )
    print(
        f"   Time: {position_query_time:.3f}s ({len(token_ids)/position_query_time:.1f} ops/sec)"
    )

    # Batch get market data
    market_slugs = [f"market_{i}" for i in range(5)]
    start_time = time.time()
    market_data = await db_manager.batch_get_market_data(market_slugs)
    market_query_time = time.time() - start_time

    print(f"✅ Batch retrieved market data for {len(market_data)} markets")
    print(f"   Time: {market_query_time:.3f}s")
    print(
        f"   Sample market outcomes: {len(market_data.get('market_0', {}).get('outcomes', {}))}"
    )


async def demonstrate_transaction_optimization(db_manager: BatchedDatabaseManager):
    """Demonstrate advanced transaction optimization."""
    print("\n⚡ TRANSACTION OPTIMIZATION DEMO")
    print("-" * 60)

    # Create a complex batch transaction
    operations = [
        {
            "type": "insert_order",
            "data": {
                "id": f"tx_order_{int(time.time() * 1000)}",
                "token_id": "token_tx_1",
                "market_slug": "market_tx",
                "side": "BUY",
                "price": 0.55,
                "size": 100,
                "status": "OPEN",
                "notional_value": 55.0,
                "outcome_type": "YES",
            },
        },
        {
            "type": "insert_position",
            "data": {
                "token_id": "token_tx_1",
                "market_slug": "market_tx",
                "size": 100,
                "notional_value": 55.0,
                "outcome_type": "YES",
                "side": "BUY",
            },
        },
        {
            "type": "insert_trade",
            "data": {
                "id": f"tx_trade_{int(time.time() * 1000)}",
                "order_id": f"tx_order_{int(time.time() * 1000)}",
                "token_id": "token_tx_1",
                "market_slug": "market_tx",
                "side": "BUY",
                "price": 0.55,
                "size": 100,
                "fee": 1.1,
                "outcome_type": "YES",
            },
        },
        {
            "type": "custom_query",
            "query": "UPDATE outcomes SET last_updated = CURRENT_TIMESTAMP WHERE token_id = ?",
            "parameters": ("token_tx_1",),
        },
    ]

    start_time = time.time()
    result = await db_manager.execute_batch_transaction(operations)
    transaction_time = time.time() - start_time

    print(f"✅ Executed batch transaction: {result['success']}")
    print(
        f"   Operations completed: {result['operations_completed']}/{result['total_operations']}"
    )
    print(f"   Time: {transaction_time:.3f}s")
    if result.get("errors"):
        print(f"   Errors: {len(result['errors'])}")


async def demonstrate_performance_monitoring(monitor: BatchMonitor):
    """Demonstrate real-time performance monitoring."""
    print("\n📊 PERFORMANCE MONITORING DEMO")
    print("-" * 60)

    # Allow some time for metrics collection
    await asyncio.sleep(2)

    # Display current metrics
    current_metrics = monitor.get_current_metrics()
    if current_metrics:
        print("📈 Current Performance Metrics:")

        if current_metrics["batch_processor"]:
            bp = current_metrics["batch_processor"]
            print(
                f"   Batch Processor Throughput: {bp.get('throughput_ops_per_second', 0):.1f} ops/sec"
            )
            print(f"   Batch Error Rate: {bp.get('error_rate', 0):.2%}")
            print(f"   Total Operations: {bp.get('total_operations', 0):,}")

        if current_metrics["system_metrics"]:
            sm = current_metrics["system_metrics"]
            print(f"   Memory Usage: {sm.get('memory_usage_mb', 0):.1f}MB")
            print(f"   Database Size: {sm.get('database_size_mb', 0):.1f}MB")

    # Get performance trends
    trends = monitor.get_performance_trends(hours=1)
    print("\n📈 Performance Trends (Last Hour):")
    print(f"   Data Points Collected: {trends.get('data_points', 0)}")

    if "metrics" in trends:
        for metric_name, data in trends["metrics"].items():
            if isinstance(data, dict) and "current" in data:
                print(
                    f"   {metric_name.replace('_', ' ').title()}: {data['current']:.3f} (trend: {data.get('trend', 'unknown')})"
                )

    # Check for active alerts
    active_alerts = monitor.get_active_alerts()
    if active_alerts:
        print(f"\n⚠️  Active Alerts ({len(active_alerts)}):")
        for alert in active_alerts[:3]:  # Show first 3
            print(
                f"   [{alert.severity.value.upper()}] {alert.component}: {alert.message}"
            )
    else:
        print("\n✅ No active alerts - system performing well!")


async def demonstrate_advanced_operations(db_manager: BatchedDatabaseManager):
    """Demonstrate advanced batch operations like reconciliation and cleanup."""
    print("\n🔧 ADVANCED BATCH OPERATIONS DEMO")
    print("-" * 60)

    # Position reconciliation
    print("🔄 Performing position reconciliation...")
    start_time = time.time()
    reconciliation_result = await db_manager.batch_reconcile_positions("market_0")
    reconciliation_time = time.time() - start_time

    print("✅ Position reconciliation completed:")
    print(f"   Market: {reconciliation_result['market_slug']}")
    print(f"   Positions Updated: {reconciliation_result['positions_updated']}")
    print(f"   Discrepancies Found: {reconciliation_result['discrepancies_found']}")
    print(f"   Corrections Made: {reconciliation_result['corrections_made']}")
    print(f"   Time: {reconciliation_time:.3f}s")

    # Database cleanup (use short retention for demo)
    print("\n🧹 Performing database cleanup...")
    start_time = time.time()
    cleanup_result = await db_manager.batch_cleanup_old_data(days_to_keep=1)
    cleanup_time = time.time() - start_time

    print("✅ Database cleanup completed:")
    print(f"   Orders Deleted: {cleanup_result['orders_deleted']}")
    print(f"   Trades Deleted: {cleanup_result['trades_deleted']}")
    print(f"   Old Outcomes Deleted: {cleanup_result['old_outcomes_deleted']}")
    print(f"   Time: {cleanup_time:.3f}s")


async def performance_comparison_demo(db_manager: BatchedDatabaseManager):
    """Compare batch vs individual operations performance."""
    print("\n⚡ PERFORMANCE COMPARISON: BATCH vs INDIVIDUAL")
    print("-" * 60)

    # Generate test data
    test_orders = []
    for i in range(100):
        test_orders.append(
            {
                "id": f"perf_test_{i}_{int(time.time() * 1000)}",
                "token_id": f"token_{i % 10}",
                "market_slug": f"market_{i % 5}",
                "side": "BUY" if i % 2 == 0 else "SELL",
                "price": random.uniform(0.1, 0.9),
                "size": random.uniform(10, 100),
                "status": "OPEN",
                "notional_value": random.uniform(10, 90),
                "outcome_type": "YES" if i % 2 == 0 else "NO",
            }
        )

    # Test individual operations (with batching disabled)
    print("🔄 Testing individual operations...")
    db_manager.disable_batching()

    start_time = time.time()
    for order in test_orders:
        await db_manager.insert_order(order)
    individual_time = time.time() - start_time

    individual_throughput = len(test_orders) / individual_time

    print(
        f"   Individual operations: {individual_time:.2f}s ({individual_throughput:.1f} ops/sec)"
    )

    # Test batch operations
    print("🔄 Testing batch operations...")
    db_manager.enable_batching()

    # Generate new test data to avoid conflicts
    batch_test_orders = []
    for i in range(100):
        batch_test_orders.append(
            {
                "id": f"batch_test_{i}_{int(time.time() * 1000)}",
                "token_id": f"token_{i % 10}",
                "market_slug": f"market_{i % 5}",
                "side": "BUY" if i % 2 == 0 else "SELL",
                "price": random.uniform(0.1, 0.9),
                "size": random.uniform(10, 100),
                "status": "OPEN",
                "notional_value": random.uniform(10, 90),
                "outcome_type": "YES" if i % 2 == 0 else "NO",
            }
        )

    start_time = time.time()
    await db_manager.batch_insert_orders(batch_test_orders, BatchPriority.HIGH)
    batch_time = time.time() - start_time

    batch_throughput = len(batch_test_orders) / batch_time
    improvement = (individual_time - batch_time) / individual_time * 100
    throughput_improvement = (
        (batch_throughput - individual_throughput) / individual_throughput * 100
    )

    print(f"   Batch operations: {batch_time:.2f}s ({batch_throughput:.1f} ops/sec)")
    print("\n📈 PERFORMANCE IMPROVEMENT:")
    print(f"   Time Reduction: {improvement:.1f}%")
    print(f"   Throughput Increase: {throughput_improvement:.1f}%")
    print(f"   Speed-up Factor: {individual_time/batch_time:.1f}x")


async def main():
    """Main demo function showcasing batch processing capabilities."""
    print("🚀 InkedUp Bot Advanced Batch Processing Demo")
    print("=" * 80)

    try:
        # Initialize database with batch processing
        print("Initializing batch-enabled database...")
        batch_config = BatchConfig(
            max_batch_size=100,
            max_wait_time_ms=500,
            strategy=BatchStrategy.HYBRID,
            enable_metrics=True,
            max_concurrent_batches=3,
        )

        db_manager = BatchedDatabaseManager(":memory:", batch_config)
        await db_manager.initialize()
        await db_manager.initialize_batch_processing()

        # Initialize query optimizer
        query_optimizer = QueryOptimizer(cache_size=1000, enable_optimization=True)

        # Initialize transaction optimizer
        transaction_optimizer = TransactionOptimizer(
            max_batch_size=50, batch_timeout_ms=1000
        )

        # Initialize monitoring
        monitoring_config = MonitoringConfig(
            collection_interval_seconds=10,
            enable_alerting=True,
            enable_performance_tracking=True,
        )

        await initialize_batch_monitoring(
            db_manager._batch_processor,
            query_optimizer,
            transaction_optimizer,
            monitoring_config,
        )

        print("✅ All systems initialized successfully!")

        # Generate sample data
        sample_data = await generate_sample_data(500)  # Reduced for demo speed

        # Run demonstrations
        await demonstrate_batch_inserts(db_manager, sample_data)
        await demonstrate_batch_updates(db_manager, sample_data)
        await demonstrate_batch_queries(db_manager, sample_data)
        await demonstrate_transaction_optimization(db_manager)

        # Allow time for metrics collection
        await asyncio.sleep(3)

        # Show monitoring capabilities
        monitor = get_batch_monitor()
        if monitor:
            await demonstrate_performance_monitoring(monitor)

        await demonstrate_advanced_operations(db_manager)
        await performance_comparison_demo(db_manager)

        # Final metrics and dashboard
        print("\n📊 FINAL PERFORMANCE DASHBOARD")
        print("=" * 80)
        print_performance_dashboard()

        # Get comprehensive report
        if monitor:
            print("\n📋 GENERATING COMPREHENSIVE REPORT...")
            report = monitor.get_performance_report(hours=1)

            if "summary" in report:
                print("📊 Performance Summary:")
                for metric_name, stats in report["summary"].items():
                    if isinstance(stats, dict) and "average" in stats:
                        print(
                            f"   {metric_name.replace('_', ' ').title()}: {stats['average']:.2f} {stats.get('unit', '')}"
                        )

            if "recommendations" in report:
                print("\n💡 Optimization Recommendations:")
                for i, rec in enumerate(report["recommendations"][:3], 1):
                    print(f"   {i}. {rec}")

            # Export detailed metrics
            export_file = f"batch_performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            export_result = monitor.export_metrics(export_file, hours=1)

            if export_result["success"]:
                print(f"\n📄 Detailed report exported: {export_file}")
                print(f"   File size: {export_result['file_size_bytes']:,} bytes")

        print("\n🎉 Batch processing demo completed successfully!")
        print("=" * 80)

        # Final statistics
        if db_manager._batch_processor:
            final_metrics = await db_manager.get_batch_metrics()
            if final_metrics:
                print("\n📈 FINAL BATCH PROCESSING STATISTICS:")
                print(f"   Total Operations: {final_metrics['total_operations']:,}")
                print(
                    f"   Success Rate: {(final_metrics['successful_operations'] / max(final_metrics['total_operations'], 1) * 100):.1f}%"
                )
                print(
                    f"   Average Throughput: {final_metrics['throughput_ops_per_second']:.1f} ops/sec"
                )
                print(
                    f"   Total Processing Time: {final_metrics['total_operations'] / max(final_metrics['throughput_ops_per_second'], 1):.1f}s"
                )

    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Cleanup
        print("\n🧹 Cleaning up...")
        if "db_manager" in locals():
            await db_manager.shutdown_batch_processing()

        # Import after defining the function to avoid circular import
        from inkedup_bot.batch_monitoring import shutdown_batch_monitoring

        await shutdown_batch_monitoring()

        print("✅ Cleanup completed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
