"""
Simple connection pool demonstration.
"""

import asyncio
import time

from inkedup_bot.connection_pool import ConnectionPoolManager
from inkedup_bot.database_pooled import PooledDatabaseManager


async def simple_demo():
    """Simple demonstration of connection pooling."""
    print("Connection Pool Demonstration")
    print("=" * 40)

    # Create pooled database manager
    db = PooledDatabaseManager(":memory:", pool_size=3, max_pool_size=5)

    print("1. Initializing database with connection pool...")
    await db.initialize()

    print(f"2. Database type: {db._db_type}")

    # Test basic operations
    print("3. Testing basic operations...")

    # Insert some test data
    for i in range(5):
        order_data = {
            "id": f"test_order_{i}",
            "token_id": f"test_token_{i}",
            "market_slug": "test_market",
            "side": "BUY",
            "price": 0.5 + (i * 0.1),
            "size": 10.0,
            "status": "OPEN",
            "notional_value": 5.0 + i,
            "outcome_type": "YES",
        }
        await db.insert_order(order_data)
        print(f"   Inserted order {i+1}/5")

    # Test concurrent operations
    print("4. Testing concurrent operations...")

    async def concurrent_worker(worker_id: int):
        # Query total exposure
        exposure = await db.get_total_exposure()

        # Get an order
        order = await db.get_order(f"test_order_{worker_id % 5}")

        return exposure, order is not None

    # Run 10 concurrent workers
    start_time = time.time()
    tasks = [concurrent_worker(i) for i in range(10)]
    results = await asyncio.gather(*tasks)
    concurrent_time = time.time() - start_time

    print(f"   Completed 10 concurrent operations in {concurrent_time:.3f}s")
    print(f"   All operations successful: {all(r[1] for r in results)}")

    # Get pool status
    print("5. Pool status:")
    status = await db.get_pool_status()
    print(f"   Pool type: {status['pool_type']}")
    print(f"   Pool size: {status['pool_size']}")
    print(f"   Initialized: {status['initialized']}")

    stats = status.get("stats", {})
    print(f"   Total queries: {stats.get('total_queries_executed', 0)}")
    print(f"   Connections created: {stats.get('total_connections_created', 0)}")
    print(
        f"   Current connections in use: {stats.get('current_connections_in_use', 0)}"
    )

    await db.close()
    print("6. Database closed successfully")

    print("\nConnection pooling demo completed!")


async def test_pool_creation():
    """Test connection pool creation for different database types."""
    print("\nTesting Connection Pool Creation")
    print("=" * 40)

    # Test SQLite pool creation
    sqlite_pool = ConnectionPoolManager.create_pool(":memory:", pool_size=3)
    print(f"SQLite pool type: {type(sqlite_pool).__name__}")

    # Test PostgreSQL pool creation (without actual connection)
    try:
        pg_pool = ConnectionPoolManager.create_pool(
            "postgresql://user:pass@localhost/testdb", pool_size=5
        )
        print(f"PostgreSQL pool type: {type(pg_pool).__name__}")
    except Exception as e:
        print(f"PostgreSQL pool creation: {e}")

    # Test pool functionality
    print("Testing SQLite pool functionality...")
    await sqlite_pool.initialize()

    # Test basic query
    try:
        result = await sqlite_pool.fetch_one("SELECT 1 as test")
        print(f"Basic query result: {dict(result) if result else None}")
    except Exception as e:
        print(f"Query error: {e}")

    await sqlite_pool.close()
    print("SQLite pool test completed")


if __name__ == "__main__":
    asyncio.run(simple_demo())
    asyncio.run(test_pool_creation())
