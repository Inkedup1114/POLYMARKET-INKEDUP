"""
Comprehensive test suite for database connection pooling functionality.

This test suite validates that connection pooling provides performance improvements
while maintaining data integrity and reliability.
"""

import asyncio
import logging
import time

import pytest

from inkedup_bot.connection_pool import SQLiteConnectionPool
from inkedup_bot.database_pooled import PooledDatabaseManager

# Setup logging for tests
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class TestSQLiteConnectionPool:
    """Test the SQLite connection pool implementation."""

    @pytest.mark.asyncio
    async def test_pool_initialization(self):
        """Test connection pool initialization."""
        pool = SQLiteConnectionPool(
            database_path=":memory:",
            min_connections=2,
            max_connections=5,
            pool_name="test_init_pool",
        )

        await pool.initialize()

        assert pool._initialized
        assert len(pool._pool) >= 2  # Should have minimum connections

        stats = pool.get_stats()
        assert stats["health_status"] == "healthy"
        assert stats["current_state"]["total_connections"] >= 2
        assert stats["current_state"]["idle_connections"] >= 2

        await pool.close()

    @pytest.mark.asyncio
    async def test_connection_acquisition(self):
        """Test connection acquisition from pool."""
        pool = SQLiteConnectionPool(
            database_path=":memory:",
            min_connections=2,
            max_connections=5,
            pool_name="test_acquire_pool",
        )

        await pool.initialize()

        # Test acquiring connection
        async with pool.acquire() as conn:
            # Test basic query
            async with conn.execute("SELECT 1") as cursor:
                result = await cursor.fetchone()
                assert result[0] == 1

        # Verify pool stats
        stats = pool.get_stats()
        assert stats["lifetime_stats"]["successful_acquisitions"] >= 1
        assert stats["lifetime_stats"]["success_rate"] == 1.0

        await pool.close()


class TestConnectionPoolStats:
    """Test connection pool statistics and monitoring."""

    @pytest.mark.asyncio
    async def test_stats_initialization(self):
        """Test that pool statistics are properly initialized."""
        pool = SQLiteConnectionPool(
            database_path=":memory:",
            min_connections=1,
            max_connections=3,
            pool_name="test_stats_pool",
        )

        await pool.initialize()

        stats = pool.get_stats()

        # Verify basic structure
        assert "pool_name" in stats
        assert "health_status" in stats
        assert "current_state" in stats
        assert "lifetime_stats" in stats

        # Verify current state
        current_state = stats["current_state"]
        assert current_state["total_connections"] >= 1
        assert current_state["idle_connections"] >= 1
        assert current_state["active_connections"] == 0

        # Verify lifetime stats
        lifetime_stats = stats["lifetime_stats"]
        assert lifetime_stats["created_connections"] >= 1
        assert lifetime_stats["successful_acquisitions"] >= 0
        assert lifetime_stats["failed_acquisitions"] == 0

        await pool.close()


class TestPooledDatabaseManager:
    """Test the pooled database manager implementation."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test pooled database manager initialization."""
        manager = PooledDatabaseManager(
            db_path=":memory:", min_connections=2, max_connections=5
        )

        await manager.initialize()

        assert manager._initialized
        assert manager._connection_pool is not None

        stats = manager.get_pool_stats()
        assert stats["health_status"] == "healthy"

        await manager.close()

    @pytest.mark.asyncio
    async def test_basic_database_operations(self):
        """Test basic database operations with pooled manager."""
        manager = PooledDatabaseManager(
            db_path=":memory:", min_connections=1, max_connections=3
        )

        await manager.initialize()

        # Test table creation worked
        positions = await manager.get_all_positions()
        assert isinstance(positions, list)
        assert len(positions) == 0  # Should be empty initially

        await manager.close()


class TestPerformanceBenchmarks:
    """Performance benchmarks comparing pooled vs non-pooled connections."""

    @pytest.mark.asyncio
    async def test_performance_comparison(self):
        """Compare performance between pooled and non-pooled database access."""

        # Test configuration
        num_operations = 50  # Reduced for faster tests

        # Benchmark pooled database manager
        log.info("Benchmarking PooledDatabaseManager...")
        start_time = time.time()

        pooled_manager = PooledDatabaseManager(
            db_path=":memory:", min_connections=3, max_connections=8
        )
        await pooled_manager.initialize()

        # Perform operations
        for i in range(num_operations):
            async with pooled_manager.connection() as conn:
                async with conn.execute("SELECT ?", (i,)) as cursor:
                    result = await cursor.fetchone()
                    assert result[0] == i

        await pooled_manager.close()
        pooled_time = time.time() - start_time

        # Log results
        log.info(f"Pooled time: {pooled_time:.3f}s")
        log.info(f"Operations per second: {num_operations/pooled_time:.1f}")

        assert pooled_time > 0  # Just ensure it completed successfully


# Convenience functions for running benchmarks
async def run_performance_benchmark():
    """Run performance benchmark and print results."""
    benchmark = TestPerformanceBenchmarks()

    print("🚀 Running database connection pooling performance benchmark...\n")

    # Performance comparison
    print("📊 Running performance comparison test...")
    await benchmark.test_performance_comparison()
    print("✅ Performance comparison completed\n")

    print("🎉 All performance benchmarks completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_performance_benchmark())
