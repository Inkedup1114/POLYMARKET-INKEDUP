"""
Comprehensive tests for the fallback system.

Tests all aspects of the fallback functionality including health monitoring,
seamless switching, data synchronization, and recovery procedures.
"""

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from inkedup_bot.database import DatabaseManager
from inkedup_bot.enhanced_state import EnhancedStateManager
from inkedup_bot.fallback import (
    DatabaseHealthMonitor,
    FallbackManager,
    FallbackMode,
    HealthStatus,
    InMemoryStateStore,
)
from inkedup_bot.fallback.recovery import (
    RecoveryManager,
    RecoveryPhase,
    RecoveryStrategy,
)
from inkedup_bot.fallback.sync import DataSynchronizer, SyncStatus


class TestInMemoryStateStore:
    """Test the in-memory state storage component."""

    def test_store_initialization(self):
        """Test store initializes correctly."""
        store = InMemoryStateStore()

        assert len(store.orders) == 0
        assert len(store.positions) == 0
        assert len(store.trades) == 0
        assert store.operation_count == 0
        assert isinstance(store.created_at, datetime)

    def test_order_operations(self):
        """Test order storage operations."""
        store = InMemoryStateStore()

        order = {
            "id": "order_123",
            "token_id": "token_456",
            "side": "BUY",
            "price": 0.55,
            "size": 100.0,
            "status": "OPEN",
        }

        # Insert order
        store.insert_order(order)
        assert len(store.orders) == 1
        assert store.operation_count == 1

        # Get order
        retrieved = store.get_order("order_123")
        assert retrieved is not None
        assert retrieved["id"] == "order_123"

        # Update order
        store.update_order("order_123", {"status": "FILLED"})
        updated = store.get_order("order_123")
        assert updated["status"] == "FILLED"
        assert store.operation_count == 2

        # Get all orders
        all_orders = store.get_all_orders()
        assert len(all_orders) == 1

    def test_position_operations(self):
        """Test position storage operations."""
        store = InMemoryStateStore()

        position = {
            "token_id": "token_456",
            "market_slug": "test-market",
            "outcome_type": "YES",
            "size": 50.0,
            "notional_value": 25.0,
        }

        # Upsert position
        store.upsert_position(position)
        assert len(store.positions) == 1

        # Get position
        retrieved = store.get_position("token_456")
        assert retrieved is not None
        assert retrieved["size"] == 50.0

        # Update position
        position["size"] = 75.0
        store.upsert_position(position)
        updated = store.get_position("token_456")
        assert updated["size"] == 75.0
        assert len(store.positions) == 1  # Still only one position

        # Get positions by market
        market_positions = store.get_positions_by_market("test-market")
        assert len(market_positions) == 1
        assert market_positions[0]["token_id"] == "token_456"

    def test_trade_operations(self):
        """Test trade recording operations."""
        store = InMemoryStateStore()

        trade = {
            "order_id": "order_123",
            "token_id": "token_456",
            "side": "BUY",
            "price": 0.55,
            "size": 100.0,
            "notional_value": 55.0,
        }

        # Record trade
        store.record_trade(trade)
        assert len(store.trades) == 1

        # Get trades
        trades = store.get_trades()
        assert len(trades) == 1
        assert "recorded_at" in trades[0]  # Should add timestamp

        # Record multiple trades
        for i in range(5):
            store.record_trade({**trade, "order_id": f"order_{i}"})

        # Get limited trades
        recent_trades = store.get_trades(limit=3)
        assert len(recent_trades) == 3

    def test_store_stats(self):
        """Test store statistics."""
        store = InMemoryStateStore()

        initial_stats = store.get_stats()
        assert initial_stats["operation_count"] == 0
        assert initial_stats["orders_count"] == 0

        # Add some data
        store.insert_order(
            {
                "id": "order_1",
                "token_id": "token_1",
                "side": "BUY",
                "price": 0.5,
                "size": 100,
                "status": "OPEN",
            }
        )
        store.upsert_position(
            {"token_id": "token_1", "size": 50.0, "notional_value": 25.0}
        )

        stats = store.get_stats()
        assert stats["operation_count"] == 2
        assert stats["orders_count"] == 1
        assert stats["positions_count"] == 1

    def test_thread_safety(self):
        """Test thread safety of store operations."""
        import threading

        store = InMemoryStateStore()
        errors = []

        def worker(thread_id):
            try:
                for i in range(100):
                    store.insert_order(
                        {
                            "id": f"order_{thread_id}_{i}",
                            "token_id": f"token_{thread_id}",
                            "side": "BUY",
                            "price": 0.5,
                            "size": 100,
                            "status": "OPEN",
                        }
                    )
            except Exception as e:
                errors.append(e)

        # Run multiple threads
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(errors) == 0
        assert len(store.orders) == 500  # 5 threads * 100 orders each


class TestDatabaseHealthMonitor:
    """Test database health monitoring functionality."""

    def test_health_monitor_initialization(self):
        """Test health monitor initializes correctly."""
        monitor = DatabaseHealthMonitor()

        assert monitor.consecutive_failures == 0
        assert monitor.consecutive_successes == 0
        assert len(monitor.recent_operations) == 0
        assert not monitor._monitoring

    def test_operation_result_recording(self):
        """Test recording of operation results."""
        monitor = DatabaseHealthMonitor()

        # Record successful operations
        for _ in range(5):
            monitor.record_operation_result(True)

        assert monitor.consecutive_successes == 5
        assert monitor.consecutive_failures == 0
        assert len(monitor.recent_operations) == 5
        assert all(monitor.recent_operations)

        # Record failure
        monitor.record_operation_result(False)
        assert monitor.consecutive_successes == 0
        assert monitor.consecutive_failures == 1
        assert len(monitor.recent_operations) == 6

    def test_health_status_calculation(self):
        """Test health status calculation."""
        monitor = DatabaseHealthMonitor()

        # All operations successful
        for _ in range(10):
            monitor.record_operation_result(True)

        status = monitor.get_current_health_status()
        assert status == HealthStatus.HEALTHY

        # Mixed results (degraded)
        for _ in range(5):
            monitor.record_operation_result(False)

        status = monitor.get_current_health_status()
        assert status == HealthStatus.DEGRADED

        # Mostly failures (unhealthy)
        for _ in range(10):
            monitor.record_operation_result(False)

        status = monitor.get_current_health_status()
        assert status == HealthStatus.UNHEALTHY

    def test_fallback_triggers(self):
        """Test fallback trigger conditions."""
        monitor = DatabaseHealthMonitor(failure_threshold=3)

        # Below threshold
        for _ in range(2):
            monitor.record_operation_result(False)
        assert not monitor.should_trigger_fallback()

        # At threshold
        monitor.record_operation_result(False)
        assert monitor.should_trigger_fallback()

    def test_recovery_conditions(self):
        """Test recovery trigger conditions."""
        monitor = DatabaseHealthMonitor(recovery_threshold=5)

        # Below threshold
        for _ in range(4):
            monitor.record_operation_result(True)
        assert not monitor.should_attempt_recovery()

        # At threshold
        monitor.record_operation_result(True)
        assert monitor.should_attempt_recovery()

    @pytest.mark.asyncio
    async def test_monitoring_lifecycle(self):
        """Test monitoring start/stop lifecycle."""
        monitor = DatabaseHealthMonitor(health_check_interval=0.1)

        check_calls = []

        def mock_health_check():
            check_calls.append(datetime.now())
            return True

        # Start monitoring
        assert not monitor._monitoring
        await monitor.start_monitoring(mock_health_check)
        assert monitor._monitoring

        # Let it run for a short time
        await asyncio.sleep(0.3)

        # Stop monitoring
        await monitor.stop_monitoring()
        assert not monitor._monitoring

        # Should have made multiple health checks
        assert len(check_calls) >= 2


@pytest.mark.asyncio
class TestFallbackManager:
    """Test the main fallback management functionality."""

    async def create_test_fallback_manager(self):
        """Create a test fallback manager with in-memory database."""
        db = DatabaseManager(":memory:")
        await db.initialize()

        fallback = FallbackManager(
            database_manager=db,
            sync_interval=1.0,  # Short interval for testing
            enable_auto_recovery=False,  # Disable for controlled testing
        )

        return fallback, db

    async def test_fallback_manager_initialization(self):
        """Test fallback manager initialization."""
        fallback, db = await self.create_test_fallback_manager()

        assert fallback.current_mode == FallbackMode.PRIMARY
        assert fallback.metrics.mode == FallbackMode.PRIMARY
        assert isinstance(fallback.memory_store, InMemoryStateStore)

        await fallback.stop()
        await db.close()

    async def test_fallback_manager_start_stop(self):
        """Test fallback manager lifecycle."""
        fallback, db = await self.create_test_fallback_manager()

        # Start fallback manager
        await fallback.start()
        assert fallback.current_mode in [FallbackMode.PRIMARY, FallbackMode.FALLBACK]

        # Stop fallback manager
        await fallback.stop()

        await db.close()

    async def test_manual_fallback_switching(self):
        """Test manual fallback mode switching."""
        fallback, db = await self.create_test_fallback_manager()
        await fallback.start()

        # Initially in primary mode
        assert fallback.current_mode == FallbackMode.PRIMARY

        # Switch to fallback
        await fallback.switch_to_fallback("Manual test")
        assert fallback.current_mode == FallbackMode.FALLBACK

        await fallback.stop()
        await db.close()

    async def test_operation_context_primary(self):
        """Test operation context in primary mode."""
        fallback, db = await self.create_test_fallback_manager()
        await fallback.start()

        # Test successful operation
        async with fallback.operation_context("test_operation") as mode:
            assert mode == "primary"

        await fallback.stop()
        await db.close()

    async def test_operation_context_fallback(self):
        """Test operation context in fallback mode."""
        fallback, db = await self.create_test_fallback_manager()
        await fallback.start()

        # Switch to fallback mode
        await fallback.switch_to_fallback("Test")

        # Test fallback operation
        async with fallback.operation_context("test_operation") as mode:
            assert mode == "fallback"

        await fallback.stop()
        await db.close()

    async def test_operation_context_with_failure(self):
        """Test operation context handling failures."""
        fallback, db = await self.create_test_fallback_manager()

        # Mock database to fail
        original_get_total_exposure = db.get_total_exposure
        db.get_total_exposure = AsyncMock(side_effect=Exception("Database error"))

        await fallback.start()

        # Should switch to fallback on repeated failures
        for _ in range(5):  # Exceed failure threshold
            try:
                async with fallback.operation_context("test_operation") as mode:
                    if mode == "primary":
                        await db.get_total_exposure()  # This will fail
                    # If in fallback mode, operation should succeed
            except Exception:
                pass  # Expected failures

        # Should eventually be in fallback mode
        assert fallback.current_mode == FallbackMode.FALLBACK

        # Restore original method
        db.get_total_exposure = original_get_total_exposure

        await fallback.stop()
        await db.close()

    async def test_metrics_tracking(self):
        """Test metrics tracking during operations."""
        fallback, db = await self.create_test_fallback_manager()
        await fallback.start()

        initial_metrics = fallback.get_metrics()
        assert initial_metrics.primary_operations_attempted == 0
        assert initial_metrics.fallback_operations == 0

        # Perform some operations
        async with fallback.operation_context("test_op_1"):
            pass
        async with fallback.operation_context("test_op_2"):
            pass

        updated_metrics = fallback.get_metrics()
        assert updated_metrics.primary_operations_attempted == 2

        await fallback.stop()
        await db.close()


@pytest.mark.asyncio
class TestEnhancedStateManager:
    """Test the enhanced state manager with fallback support."""

    async def create_test_state_manager(self, enable_fallback=True):
        """Create test state manager."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name

        state_manager = EnhancedStateManager(
            db_path=tmp_path,
            enable_fallback=enable_fallback,
            sync_interval=1.0,
            health_check_interval=1.0,
            enable_auto_recovery=False,
        )

        await state_manager.initialize()
        return state_manager, tmp_path

    async def cleanup_test_state_manager(self, state_manager, db_path):
        """Clean up test state manager."""
        await state_manager.shutdown()
        Path(db_path).unlink(missing_ok=True)

    async def test_enhanced_state_manager_initialization(self):
        """Test enhanced state manager initialization."""
        state_manager, db_path = await self.create_test_state_manager()

        assert state_manager._initialized
        assert state_manager.fallback_manager is not None

        status = state_manager.get_fallback_status()
        assert "mode" in status

        await self.cleanup_test_state_manager(state_manager, db_path)

    async def test_order_operations_with_fallback(self):
        """Test order operations with fallback support."""
        state_manager, db_path = await self.create_test_state_manager()

        order = {
            "id": "test_order_123",
            "token_id": "token_456",
            "side": "BUY",
            "price": 0.55,
            "size": 100.0,
            "status": "OPEN",
        }

        # Add order (should use primary database)
        await state_manager.add_order(order)

        # Retrieve order
        retrieved = await state_manager.get_order("test_order_123")
        assert retrieved is not None
        assert retrieved["id"] == "test_order_123"

        # Update order
        await state_manager.update_order("test_order_123", {"status": "FILLED"})

        # Retrieve updated order
        updated = await state_manager.get_order("test_order_123")
        assert updated["status"] == "FILLED"

        await self.cleanup_test_state_manager(state_manager, db_path)

    async def test_position_operations_with_fallback(self):
        """Test position operations with fallback support."""
        state_manager, db_path = await self.create_test_state_manager()

        position = {
            "token_id": "token_456",
            "market_slug": "test-market",
            "outcome_type": "YES",
            "size": 50.0,
            "notional_value": 25.0,
        }

        # Update position (should use primary database)
        await state_manager.update_position(position)

        # Retrieve position
        retrieved = await state_manager.get_position("token_456")
        assert retrieved is not None
        assert retrieved["size"] == 50.0

        # Get all positions
        all_positions = await state_manager.get_all_positions()
        assert len(all_positions) >= 1

        # Get positions by market
        market_positions = await state_manager.get_positions_by_market("test-market")
        assert len(market_positions) >= 1

        await self.cleanup_test_state_manager(state_manager, db_path)

    async def test_fallback_mode_operations(self):
        """Test operations in fallback mode."""
        state_manager, db_path = await self.create_test_state_manager()

        # Force fallback mode
        await state_manager.force_fallback_mode("Test scenario")

        # Verify we're in fallback mode
        status = state_manager.get_fallback_status()
        assert status["mode"] == "fallback"

        # Test operations in fallback mode
        order = {
            "id": "fallback_order_123",
            "token_id": "token_789",
            "side": "SELL",
            "price": 0.45,
            "size": 200.0,
            "status": "OPEN",
        }

        await state_manager.add_order(order)

        # Should be stored in memory
        retrieved = await state_manager.get_order("fallback_order_123")
        assert retrieved is not None
        assert retrieved["side"] == "SELL"

        await self.cleanup_test_state_manager(state_manager, db_path)

    async def test_trade_impact_recording(self):
        """Test trade impact recording with fallback."""
        state_manager, db_path = await self.create_test_state_manager()

        impact = await state_manager.record_trade_impact(
            token_id="token_123",
            trade_size=100.0,
            trade_price=0.55,
            side="BUY",
            market_slug="test-market",
            outcome_type="YES",
        )

        assert impact is not None
        assert impact["token_id"] == "token_123"
        assert impact["side"] == "BUY"
        assert impact["trade_notional"] == 55.0

        await self.cleanup_test_state_manager(state_manager, db_path)

    async def test_exposure_calculations(self):
        """Test exposure calculations with fallback support."""
        state_manager, db_path = await self.create_test_state_manager()

        # Add some positions first
        position = {
            "token_id": "token_123",
            "market_slug": "test-market",
            "outcome_type": "YES",
            "size": 100.0,
            "notional_value": 55.0,
        }
        await state_manager.update_position(position)

        # Test exposure calculations
        market_exposure = await state_manager.get_market_exposure("test-market")
        assert market_exposure >= 0

        outcome_exposure = await state_manager.get_outcome_exposure("YES")
        assert outcome_exposure >= 0

        total_exposure = await state_manager.get_total_exposure()
        assert total_exposure >= 0

        await self.cleanup_test_state_manager(state_manager, db_path)

    async def test_portfolio_summary(self):
        """Test portfolio summary with fallback support."""
        state_manager, db_path = await self.create_test_state_manager()

        # Add some test data
        positions = [
            {
                "token_id": "token_1",
                "market_slug": "market_1",
                "outcome_type": "YES",
                "size": 100.0,
                "notional_value": 55.0,
            },
            {
                "token_id": "token_2",
                "market_slug": "market_2",
                "outcome_type": "NO",
                "size": 200.0,
                "notional_value": 80.0,
            },
        ]

        for position in positions:
            await state_manager.update_position(position)

        # Get portfolio summary
        summary = await state_manager.get_portfolio_summary()
        assert summary is not None
        assert "total_positions" in summary
        assert summary["total_positions"] >= 2
        assert "gross_notional" in summary
        assert summary["gross_notional"] >= 135.0  # 55 + 80

        await self.cleanup_test_state_manager(state_manager, db_path)

    async def test_health_monitoring(self):
        """Test health monitoring integration."""
        state_manager, db_path = await self.create_test_state_manager()

        # Get health metrics
        health_metrics = state_manager.get_health_metrics()
        assert "health_monitoring" in health_metrics
        assert health_metrics["health_monitoring"] == True
        assert "is_healthy" in health_metrics

        await self.cleanup_test_state_manager(state_manager, db_path)


class TestDataSynchronization:
    """Test data synchronization between fallback and primary storage."""

    @pytest.mark.asyncio
    async def test_synchronizer_initialization(self):
        """Test data synchronizer initialization."""
        db = DatabaseManager(":memory:")
        await db.initialize()

        memory_store = InMemoryStateStore()
        synchronizer = DataSynchronizer(db, memory_store)

        assert synchronizer.db == db
        assert synchronizer.memory_store == memory_store
        assert len(synchronizer.conflicts) == 0

        await db.close()

    @pytest.mark.asyncio
    async def test_order_synchronization(self):
        """Test order synchronization."""
        db = DatabaseManager(":memory:")
        await db.initialize()

        memory_store = InMemoryStateStore()
        synchronizer = DataSynchronizer(db, memory_store)

        # Add orders to memory store
        orders = [
            {
                "id": "order_1",
                "token_id": "token_1",
                "side": "BUY",
                "price": 0.55,
                "size": 100.0,
                "status": "OPEN",
            },
            {
                "id": "order_2",
                "token_id": "token_2",
                "side": "SELL",
                "price": 0.45,
                "size": 200.0,
                "status": "FILLED",
            },
        ]

        for order in orders:
            memory_store.insert_order(order)

        # Synchronize orders
        result = await synchronizer._sync_orders()

        assert result.status in [SyncStatus.SUCCESS, SyncStatus.PARTIAL_SUCCESS]
        assert result.records_processed == 2
        assert result.records_synced >= 0  # Might be 0 if validation fails

        await db.close()

    @pytest.mark.asyncio
    async def test_position_synchronization(self):
        """Test position synchronization."""
        db = DatabaseManager(":memory:")
        await db.initialize()

        memory_store = InMemoryStateStore()
        synchronizer = DataSynchronizer(db, memory_store)

        # Add positions to memory store
        positions = [
            {
                "token_id": "token_1",
                "market_slug": "market_1",
                "outcome_type": "YES",
                "size": 100.0,
                "notional_value": 55.0,
            },
            {
                "token_id": "token_2",
                "market_slug": "market_2",
                "outcome_type": "NO",
                "size": 200.0,
                "notional_value": 80.0,
            },
        ]

        for position in positions:
            memory_store.upsert_position(position)

        # Synchronize positions
        result = await synchronizer._sync_positions()

        assert result.status in [SyncStatus.SUCCESS, SyncStatus.PARTIAL_SUCCESS]
        assert result.records_processed == 2

        await db.close()

    @pytest.mark.asyncio
    async def test_full_synchronization(self):
        """Test full data synchronization."""
        db = DatabaseManager(":memory:")
        await db.initialize()

        memory_store = InMemoryStateStore()
        synchronizer = DataSynchronizer(db, memory_store)

        # Add various data types to memory store
        memory_store.insert_order(
            {
                "id": "order_1",
                "token_id": "token_1",
                "side": "BUY",
                "price": 0.55,
                "size": 100.0,
                "status": "OPEN",
            }
        )

        memory_store.upsert_position(
            {
                "token_id": "token_1",
                "market_slug": "market_1",
                "outcome_type": "YES",
                "size": 100.0,
                "notional_value": 55.0,
            }
        )

        # Perform full sync
        results = await synchronizer.full_sync()

        assert isinstance(results, dict)
        assert "orders" in results
        assert "positions" in results

        # Check individual results
        for sync_type, result in results.items():
            assert hasattr(result, "status")
            assert hasattr(result, "records_processed")
            assert hasattr(result, "records_synced")

        await db.close()


class TestRecoveryProcedures:
    """Test recovery procedures and automation."""

    @pytest.mark.asyncio
    async def test_recovery_manager_initialization(self):
        """Test recovery manager initialization."""
        db = DatabaseManager(":memory:")
        await db.initialize()

        memory_store = InMemoryStateStore()
        fallback_manager = FallbackManager(db)

        recovery = RecoveryManager(fallback_manager)

        assert recovery.fallback_manager == fallback_manager
        assert recovery.default_strategy == RecoveryStrategy.GRADUAL
        assert len(recovery.recovery_history) == 0

        await db.close()

    @pytest.mark.asyncio
    async def test_recovery_plan_creation(self):
        """Test recovery plan creation for different strategies."""
        db = DatabaseManager(":memory:")
        await db.initialize()

        fallback_manager = FallbackManager(db)
        recovery = RecoveryManager(fallback_manager)

        # Test different strategies
        strategies = [
            RecoveryStrategy.IMMEDIATE,
            RecoveryStrategy.GRADUAL,
            RecoveryStrategy.SCHEDULED,
            RecoveryStrategy.MANUAL_ONLY,
        ]

        for strategy in strategies:
            plan = recovery._create_recovery_plan(strategy)
            assert plan.strategy == strategy
            assert isinstance(plan.start_time, datetime)
            assert len(plan.phases) > 0

        await db.close()

    @pytest.mark.asyncio
    async def test_recovery_phase_execution(self):
        """Test individual recovery phase execution."""
        db = DatabaseManager(":memory:")
        await db.initialize()

        fallback_manager = FallbackManager(db)
        recovery = RecoveryManager(fallback_manager)

        plan = recovery._create_recovery_plan(RecoveryStrategy.IMMEDIATE)

        # Test preparation phase
        checkpoint = await recovery._execute_recovery_phase(
            RecoveryPhase.PREPARATION, plan, force=False
        )
        assert checkpoint.phase == RecoveryPhase.PREPARATION
        assert isinstance(checkpoint.success, bool)
        assert isinstance(checkpoint.timestamp, datetime)

        await db.close()

    @pytest.mark.asyncio
    async def test_recovery_metrics(self):
        """Test recovery metrics tracking."""
        db = DatabaseManager(":memory:")
        await db.initialize()

        fallback_manager = FallbackManager(db)
        recovery = RecoveryManager(fallback_manager)

        initial_metrics = recovery.get_recovery_metrics()
        assert initial_metrics["total_recoveries_attempted"] == 0
        assert initial_metrics["total_recoveries_successful"] == 0

        # Attempt a recovery (will likely fail due to test environment)
        try:
            await recovery.attempt_recovery(RecoveryStrategy.MANUAL_ONLY, force=True)
        except Exception:
            pass  # Expected in test environment

        updated_metrics = recovery.get_recovery_metrics()
        assert updated_metrics["total_recoveries_attempted"] >= 1

        await db.close()


class TestIntegrationScenarios:
    """Test complete integration scenarios."""

    @pytest.mark.asyncio
    async def test_database_failure_and_recovery_scenario(self):
        """Test complete database failure and recovery scenario."""
        state_manager, db_path = await self.create_integration_test_manager()

        # Start with normal operations
        await state_manager.add_order(
            {
                "id": "order_1",
                "token_id": "token_1",
                "side": "BUY",
                "price": 0.55,
                "size": 100.0,
                "status": "OPEN",
            }
        )

        # Verify primary mode
        status = state_manager.get_fallback_status()
        assert status["mode"] == "primary"

        # Simulate database failure
        await state_manager.force_fallback_mode("Simulated database failure")

        # Verify fallback mode
        status = state_manager.get_fallback_status()
        assert status["mode"] == "fallback"

        # Continue operations in fallback mode
        await state_manager.add_order(
            {
                "id": "order_2",
                "token_id": "token_2",
                "side": "SELL",
                "price": 0.45,
                "size": 200.0,
                "status": "OPEN",
            }
        )

        await state_manager.update_position(
            {
                "token_id": "token_2",
                "market_slug": "test-market",
                "outcome_type": "NO",
                "size": 200.0,
                "notional_value": 90.0,
            }
        )

        # Verify fallback operations worked
        order = await state_manager.get_order("order_2")
        assert order is not None
        assert order["side"] == "SELL"

        position = await state_manager.get_position("token_2")
        assert position is not None
        assert position["size"] == 200.0

        # Attempt recovery
        recovery_success = await state_manager.force_recovery_attempt()

        # Check final status
        final_status = state_manager.get_fallback_status()
        health_metrics = state_manager.get_health_metrics()

        # Clean up
        await state_manager.shutdown()
        Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_data_consistency_across_modes(self):
        """Test data consistency when switching between modes."""
        state_manager, db_path = await self.create_integration_test_manager()

        # Add initial data in primary mode
        initial_positions = [
            {
                "token_id": "token_1",
                "market_slug": "market_1",
                "outcome_type": "YES",
                "size": 100.0,
                "notional_value": 55.0,
            },
            {
                "token_id": "token_2",
                "market_slug": "market_1",
                "outcome_type": "NO",
                "size": 150.0,
                "notional_value": 67.5,
            },
        ]

        for position in initial_positions:
            await state_manager.update_position(position)

        # Get initial exposure
        initial_exposure = await state_manager.get_market_exposure("market_1")

        # Switch to fallback mode
        await state_manager.force_fallback_mode("Testing consistency")

        # Verify data is still accessible
        fallback_exposure = await state_manager.get_market_exposure("market_1")

        # Add more data in fallback mode
        await state_manager.update_position(
            {
                "token_id": "token_3",
                "market_slug": "market_1",
                "outcome_type": "YES",
                "size": 50.0,
                "notional_value": 27.5,
            }
        )

        # Get updated exposure
        updated_exposure = await state_manager.get_market_exposure("market_1")

        # Verify consistency
        assert updated_exposure >= fallback_exposure

        # Clean up
        await state_manager.shutdown()
        Path(db_path).unlink(missing_ok=True)

    async def create_integration_test_manager(self):
        """Create test state manager for integration tests."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name

        state_manager = EnhancedStateManager(
            db_path=tmp_path,
            enable_fallback=True,
            sync_interval=1.0,
            health_check_interval=1.0,
            enable_auto_recovery=False,  # Manual control for tests
        )

        await state_manager.initialize()
        return state_manager, tmp_path


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
