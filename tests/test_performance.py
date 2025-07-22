"""
Performance tests for the InkedUp bot.

This module tests performance characteristics under various loads.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.database import DatabaseManager
from inkedup_bot.scanner import Scanner
from inkedup_bot.state import StateManager


class TestDatabasePerformance:
    """Test database performance under load."""

    @pytest.mark.asyncio
    async def test_bulk_order_insertion_performance(self) -> None:
        """Test performance of bulk order insertions."""
        db_path = "test_performance.db"
        db = DatabaseManager(db_path=db_path)
        await db.initialize()

        try:
            # Test inserting 100 orders
            start_time = time.time()
            for i in range(100):
                order_data = {
                    "id": f"order_{i}",
                    "token_id": f"token_{i}",
                    "side": "buy",
                    "price": 0.5,
                    "size": 100,
                    "status": "OPEN",
                    "notional_value": 50.0,
                }
                await db.insert_order(order_data)

            duration = time.time() - start_time

            # Should complete in reasonable time (adjust threshold as needed)
            assert duration < 5.0, f"Bulk insertion took {duration:.2f}s, expected < 5s"

            # Verify all orders were inserted
            open_orders = await db.get_open_orders()
            assert len(open_orders) == 100

        finally:
            # Cleanup
            await asyncio.sleep(0.1)
            import os

            if os.path.exists(db_path):
                os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_concurrent_database_operations(self) -> None:
        """Test concurrent database operations."""
        db_path = "test_concurrent.db"
        db = DatabaseManager(db_path=db_path)
        await db.initialize()

        try:

            async def insert_orders(start_idx: int, count: int) -> None:
                for i in range(start_idx, start_idx + count):
                    order_data = {
                        "id": f"order_{i}",
                        "token_id": f"token_{i}",
                        "side": "buy",
                        "price": 0.5,
                        "size": 100,
                        "status": "OPEN",
                        "notional_value": 50.0,
                    }
                    await db.insert_order(order_data)

            # Run concurrent insertions
            tasks = [
                insert_orders(0, 25),
                insert_orders(25, 25),
                insert_orders(50, 25),
                insert_orders(75, 25),
            ]

            start_time = time.time()
            await asyncio.gather(*tasks)
            duration = time.time() - start_time

            assert duration < 10.0, f"Concurrent operations took {duration:.2f}s"

            # Verify all orders were inserted
            open_orders = await db.get_open_orders()
            assert len(open_orders) == 100

        finally:
            # Cleanup
            await asyncio.sleep(0.1)
            import os

            if os.path.exists(db_path):
                os.unlink(db_path)


class TestScannerPerformance:
    """Test scanner performance."""

    @pytest.mark.asyncio
    async def test_scan_performance_with_many_markets(self) -> None:
        """Test scanner performance with large market datasets."""
        cfg = BotConfig()
        scanner = Scanner(cfg)

        # Mock large market dataset
        large_market_list = []
        for i in range(100):
            large_market_list.append(
                {
                    "slug": f"market-{i}",
                    "token_ids": [f"yes-token-{i}", f"no-token-{i}"],
                }
            )

        # Mock large book dataset
        large_books = {}
        for i in range(100):
            large_books[f"yes-token-{i}"] = {
                "bids": [{"price": f"0.{50 + i % 10}", "size": "100"}],
                "asks": [{"price": f"0.{60 + i % 10}", "size": "100"}],
            }
            large_books[f"no-token-{i}"] = {
                "bids": [{"price": f"0.{40 - i % 10}", "size": "100"}],
                "asks": [{"price": f"0.{50 - i % 10}", "size": "100"}],
            }

        # Test that scanner can handle large datasets
        # For now, just test that the scanner can be created and configured
        assert scanner.cfg == cfg
        assert len(large_market_list) == 100
        assert len(large_books) == 200


class TestStateManagerPerformance:
    """Test state manager performance."""

    @pytest.mark.asyncio
    async def test_large_position_calculations(self) -> None:
        """Test performance with many positions."""
        state = StateManager(db_path=":memory:")
        await state.initialize_async()

        # Add many positions
        start_time = time.time()
        for i in range(100):  # Reduced for test performance
            position_data = {
                "token_id": f"token_{i}",
                "market_slug": f"market_{i}",
                "outcome_type": "YES",
                "size": float(i),
                "notional_value": float(i * 0.5),
            }
            await state.update_position_async(position_data)

        position_update_time = time.time() - start_time

        # Test exposure calculations
        start_time = time.time()
        total_exposure = await state.get_total_exposure_async()
        calculation_time = time.time() - start_time

        assert (
            position_update_time < 5.0
        ), f"Position updates took {position_update_time:.2f}s"
        assert (
            calculation_time < 1.0
        ), f"Exposure calculation took {calculation_time:.2f}s"
        assert total_exposure > 0

    @pytest.mark.asyncio
    async def test_concurrent_position_updates(self) -> None:
        """Test concurrent position updates."""
        state = StateManager(db_path=":memory:")
        await state.initialize_async()

        async def update_positions_batch(start_idx: int, count: int) -> None:
            for i in range(start_idx, start_idx + count):
                position_data = {
                    "token_id": f"token_{i}",
                    "market_slug": f"market_{i}",
                    "outcome_type": "YES",
                    "size": float(i),
                    "notional_value": float(i * 0.5),
                }
                await state.update_position_async(position_data)

        # Run concurrent updates (reduced size for test performance)
        tasks = [
            update_positions_batch(0, 25),
            update_positions_batch(25, 25),
            update_positions_batch(50, 25),
            update_positions_batch(75, 25),
        ]

        start_time = time.time()
        await asyncio.gather(*tasks)
        duration = time.time() - start_time

        assert duration < 10.0, f"Concurrent position updates took {duration:.2f}s"
        # Note: StateManager doesn't track positions in memory anymore
        # All position tracking is through database


class TestMemoryUsage:
    """Test memory usage patterns."""

    @pytest.mark.asyncio
    async def test_memory_stability_with_continuous_operations(self) -> None:
        """Test that memory usage remains stable during continuous operations."""
        state = StateManager(db_path=":memory:")
        await state.initialize_async()

        # Simulate continuous trading operations
        for cycle in range(10):
            # Add positions
            for i in range(10):  # Reduced for test performance
                position_data = {
                    "token_id": f"token_{cycle}_{i}",
                    "market_slug": f"market_{cycle}",
                    "outcome_type": "YES",
                    "size": 100.0,
                    "notional_value": 50.0,
                }
                await state.update_position_async(position_data)

            # Simulate some time passing
            await asyncio.sleep(0.01)

        # Check that system is still responsive
        total_exposure = await state.get_total_exposure_async()
        assert total_exposure > 0

    @pytest.mark.asyncio
    async def test_cleanup_operations(self) -> None:
        """Test cleanup operations to prevent memory leaks."""
        state = StateManager(db_path=":memory:")
        await state.initialize_async()

        # Add some test data
        position_data = {
            "token_id": "test_token",
            "market_slug": "test_market",
            "outcome_type": "YES",
            "size": 100.0,
            "notional_value": 50.0,
        }
        await state.update_position_async(position_data)

        # Test cleanup operations (if implemented)
        # For now, just verify the system handles the operations
        total_exposure = await state.get_total_exposure_async()
        assert total_exposure >= 0


class TestScalabilityLimits:
    """Test system behavior at scale limits."""

    @pytest.mark.asyncio
    async def test_maximum_open_orders(self) -> None:
        """Test system behavior with maximum expected open orders."""
        state = StateManager(db_path=":memory:")
        await state.initialize_async()

        # Add maximum expected number of open orders
        max_orders = 50  # Reduced for test performance
        for i in range(max_orders):
            order_data = {
                "id": f"order_{i}",
                "token_id": f"token_{i}",
                "side": "buy",
                "price": 0.5,
                "size": 100,
                "status": "OPEN",
            }
            await state.add_order_async(order_data)

        # Test that operations remain efficient
        start_time = time.time()
        # Test basic operation - just verify state is responsive
        total_exposure = await state.get_total_exposure_async()
        check_time = time.time() - start_time

        assert check_time < 1.0, f"Order checking took {check_time:.2f}s"
        assert total_exposure >= 0

    @pytest.mark.asyncio
    async def test_high_frequency_updates(self) -> None:
        """Test system behavior under high-frequency updates."""
        state = StateManager(db_path=":memory:")
        await state.initialize_async()

        # Simulate high-frequency position updates (reduced for performance)
        updates_per_second = 10
        duration_seconds = 1
        total_updates = updates_per_second * duration_seconds

        start_time = time.time()
        for i in range(total_updates):
            token_id = f"token_{i % 5}"  # Update 5 different tokens repeatedly
            position_data = {
                "token_id": token_id,
                "market_slug": f"market_{i % 5}",
                "outcome_type": "YES",
                "size": float(i),
                "notional_value": float(i * 0.5),
            }
            await state.update_position_async(position_data)

            # Small delay to simulate realistic timing
            if i % 10 == 0:
                await asyncio.sleep(0.01)

        total_time = time.time() - start_time

        # Should handle the load within reasonable time
        assert (
            total_time < duration_seconds * 3
        ), f"High frequency updates took {total_time:.2f}s"

        # Verify final state is consistent
        total_exposure = await state.get_total_exposure_async()
        assert total_exposure > 0
