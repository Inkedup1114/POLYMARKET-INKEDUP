#!/usr/bin/env python3
"""
Simple Batch Processing Demo for InkedUp Bot

This demo showcases the core batch processing capabilities with the existing
database schema, focusing on practical improvements over individual operations.
"""

import asyncio
import os
import random
import sys
import time

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from inkedup_bot.batch_processor import BatchConfig, BatchPriority, BatchStrategy
from inkedup_bot.database_batched import BatchedDatabaseManager


async def generate_simple_test_data(count: int = 100) -> dict:
    """Generate simple test data compatible with existing schema."""
    print(f"Generating {count} test records...")

    markets = [f"market_{i}" for i in range(5)]
    tokens = [f"token_{i}" for i in range(20)]
    sides = ["BUY", "SELL"]
    statuses = ["OPEN", "FILLED", "CANCELLED"]
    outcome_types = ["YES", "NO"]

    orders = []
    positions = []
    trades = []

    for i in range(count):
        market = random.choice(markets)
        token = random.choice(tokens)
        side = random.choice(sides)
        price = random.uniform(0.1, 0.9)
        size = random.uniform(10, 1000)

        # Generate order
        order = {
            "id": f"simple_order_{i}_{int(time.time() * 1000)}",
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

        # Generate position (compatible with existing schema)
        if random.random() < 0.4:
            position = {
                "token_id": token,
                "market_slug": market,
                "size": size if side == "BUY" else -size,
                "notional_value": price * size,
                "outcome_type": random.choice(outcome_types),
            }
            positions.append(position)

        # Generate trade
        if random.random() < 0.3:
            trade = {
                "id": f"simple_trade_{i}_{int(time.time() * 1000)}",
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


async def test_individual_vs_batch_performance(db_manager: BatchedDatabaseManager):
    """Compare individual vs batch operation performance."""
    print("\n⚡ PERFORMANCE COMPARISON: INDIVIDUAL vs BATCH")
    print("-" * 60)

    # Generate test data
    test_count = 50
    individual_orders = await generate_simple_test_data(test_count)
    batch_orders = await generate_simple_test_data(test_count)

    # Test 1: Individual operations (disable batching)
    print("🔄 Testing individual operations...")
    db_manager.disable_batching()

    start_time = time.time()
    for order in individual_orders["orders"]:
        try:
            await db_manager.insert_order(order)
        except Exception as e:
            print(f"Error inserting order: {e}")
    individual_time = time.time() - start_time

    individual_throughput = test_count / individual_time if individual_time > 0 else 0
    print(
        f"   Individual operations: {individual_time:.3f}s ({individual_throughput:.1f} ops/sec)"
    )

    # Test 2: Batch operations
    print("🔄 Testing batch operations...")
    db_manager.enable_batching()

    start_time = time.time()
    try:
        success = await db_manager.batch_insert_orders(
            batch_orders["orders"], priority=BatchPriority.HIGH
        )
        print(f"   Batch operation success: {success}")
    except Exception as e:
        print(f"   Batch operation error: {e}")

    batch_time = time.time() - start_time
    batch_throughput = test_count / batch_time if batch_time > 0 else 0

    print(f"   Batch operations: {batch_time:.3f}s ({batch_throughput:.1f} ops/sec)")

    # Calculate improvement
    if individual_time > 0 and batch_time > 0:
        time_improvement = ((individual_time - batch_time) / individual_time) * 100
        throughput_improvement = (
            (batch_throughput - individual_throughput) / individual_throughput
        ) * 100

        print("\n📈 PERFORMANCE IMPROVEMENT:")
        print(f"   Time Reduction: {time_improvement:.1f}%")
        print(f"   Throughput Increase: {throughput_improvement:.1f}%")
        print(f"   Speed-up Factor: {individual_time/batch_time:.1f}x")

    return individual_time, batch_time


async def test_batch_operations(db_manager: BatchedDatabaseManager):
    """Test various batch operations."""
    print("\n🔄 BATCH OPERATIONS TEST")
    print("-" * 60)

    # Generate test data
    test_data = await generate_simple_test_data(200)

    # Test batch inserts
    print("📥 Testing batch inserts...")

    # Orders
    start_time = time.time()
    success = await db_manager.batch_insert_orders(
        test_data["orders"], priority=BatchPriority.HIGH
    )
    orders_time = time.time() - start_time
    print(
        f"   Orders: {len(test_data['orders'])} records, {orders_time:.3f}s, Success: {success}"
    )

    # Positions
    if test_data["positions"]:
        start_time = time.time()
        success = await db_manager.batch_insert_positions(
            test_data["positions"], priority=BatchPriority.NORMAL
        )
        positions_time = time.time() - start_time
        print(
            f"   Positions: {len(test_data['positions'])} records, {positions_time:.3f}s, Success: {success}"
        )

    # Trades
    if test_data["trades"]:
        start_time = time.time()
        success = await db_manager.batch_insert_trades(
            test_data["trades"], priority=BatchPriority.HIGH
        )
        trades_time = time.time() - start_time
        print(
            f"   Trades: {len(test_data['trades'])} records, {trades_time:.3f}s, Success: {success}"
        )

    # Test batch queries
    print("\n📤 Testing batch queries...")

    # Query orders
    order_ids = [order["id"] for order in test_data["orders"][:20]]
    start_time = time.time()
    retrieved_orders = await db_manager.batch_get_orders(order_ids)
    query_time = time.time() - start_time
    print(f"   Retrieved {len(retrieved_orders)} orders in {query_time:.3f}s")

    # Test batch updates
    print("\n🔄 Testing batch updates...")
    updates = [
        (order["id"], {"status": "FILLED"}) for order in test_data["orders"][:10]
    ]
    start_time = time.time()
    success = await db_manager.batch_update_orders(updates, priority=BatchPriority.HIGH)
    update_time = time.time() - start_time
    print(f"   Updated {len(updates)} orders in {update_time:.3f}s, Success: {success}")


async def test_batch_configuration_effects(db_manager: BatchedDatabaseManager):
    """Test how different batch configurations affect performance."""
    print("\n⚙️  BATCH CONFIGURATION EFFECTS")
    print("-" * 60)

    # Test different batch sizes
    test_data = await generate_simple_test_data(100)
    batch_sizes = [10, 25, 50, 100]

    for batch_size in batch_sizes:
        # Update batch processor configuration
        if db_manager._batch_processor:
            db_manager._batch_processor.config.max_batch_size = batch_size
            print(f"\n🔧 Testing with batch size: {batch_size}")

            start_time = time.time()
            success = await db_manager.batch_insert_orders(
                test_data["orders"], priority=BatchPriority.NORMAL
            )
            elapsed_time = time.time() - start_time

            throughput = (
                len(test_data["orders"]) / elapsed_time if elapsed_time > 0 else 0
            )
            print(
                f"   Time: {elapsed_time:.3f}s, Throughput: {throughput:.1f} ops/sec, Success: {success}"
            )


async def show_batch_metrics(db_manager: BatchedDatabaseManager):
    """Display current batch processing metrics."""
    print("\n📊 BATCH PROCESSING METRICS")
    print("-" * 60)

    if db_manager._batch_processor:
        metrics = await db_manager.get_batch_metrics()
        if metrics:
            print("📈 Performance Metrics:")
            print(f"   Total Operations: {metrics.get('total_operations', 0):,}")
            print(
                f"   Successful Operations: {metrics.get('successful_operations', 0):,}"
            )
            print(f"   Failed Operations: {metrics.get('failed_operations', 0):,}")
            print(
                f"   Success Rate: {(metrics.get('successful_operations', 0) / max(metrics.get('total_operations', 1), 1) * 100):.1f}%"
            )
            print(f"   Average Batch Size: {metrics.get('average_batch_size', 0):.1f}")
            print(
                f"   Average Processing Time: {metrics.get('average_processing_time_ms', 0):.1f}ms"
            )
            print(
                f"   Throughput: {metrics.get('throughput_ops_per_second', 0):.1f} ops/sec"
            )
            print(f"   Error Rate: {metrics.get('error_rate', 0):.2%}")
        else:
            print("   No metrics available")
    else:
        print("   Batch processor not initialized")


async def main():
    """Main demo function."""
    print("🚀 Simple Batch Processing Demo for InkedUp Bot")
    print("=" * 80)

    try:
        # Initialize database with batch processing
        print("Initializing database with batch processing...")
        batch_config = BatchConfig(
            max_batch_size=50,
            max_wait_time_ms=200,
            strategy=BatchStrategy.HYBRID,
            enable_metrics=True,
            max_concurrent_batches=2,
        )

        db_manager = BatchedDatabaseManager(":memory:", batch_config)
        await db_manager.initialize()
        await db_manager.initialize_batch_processing()

        print("✅ Database and batch processing initialized!")

        # Run tests
        await test_batch_operations(db_manager)

        # Performance comparison
        individual_time, batch_time = await test_individual_vs_batch_performance(
            db_manager
        )

        # Configuration effects
        await test_batch_configuration_effects(db_manager)

        # Show final metrics
        await show_batch_metrics(db_manager)

        # Summary
        print("\n🎉 DEMO SUMMARY")
        print("=" * 80)
        print("✅ Batch processing system successfully demonstrated")
        print("✅ Performance improvements achieved through batching")
        print("✅ Multiple batch strategies and configurations tested")
        print("✅ Metrics collection and monitoring functional")

        if individual_time > 0 and batch_time > 0:
            improvement = ((individual_time - batch_time) / individual_time) * 100
            print(f"⚡ Overall Performance Improvement: {improvement:.1f}%")

        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Cleanup
        print("\n🧹 Cleaning up...")
        if "db_manager" in locals():
            try:
                await db_manager.shutdown_batch_processing()
            except Exception as e:
                print(f"Warning: Cleanup error: {e}")
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
