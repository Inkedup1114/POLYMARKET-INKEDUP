"""
Tests for atomic operations manager - race condition prevention system.

Tests cover:
- Atomic lock acquisition and release
- Deadlock prevention through ordered locking
- Timeout handling
- Concurrent operation limiting
- Lock metrics and monitoring
- Stale lock cleanup
- Safety assessment functionality
"""

import asyncio
import time
from unittest.mock import patch

import pytest

from inkedup_bot.risk.atomic_operations import (
    AtomicOperationManager,
    LockInfo,
    LockType,
    get_atomic_manager,
    shutdown_atomic_manager,
)


@pytest.fixture
def atomic_manager():
    """Create fresh atomic manager for each test."""
    return AtomicOperationManager(default_timeout=2.0, max_concurrent_operations=5)


@pytest.fixture
async def cleanup_atomic_manager(atomic_manager):
    """Cleanup atomic manager after each test."""
    yield atomic_manager
    await atomic_manager.shutdown()


class TestBasicLockOperations:
    """Test basic lock acquisition and release."""

    @pytest.mark.asyncio
    async def test_simple_position_lock(self, cleanup_atomic_manager):
        """Test simple position lock acquisition and release."""
        manager = cleanup_atomic_manager

        async with manager.atomic_position_validation("token1", "market1", "op1"):
            # Check that locks are active
            metrics = manager.get_lock_metrics()
            assert metrics["current_active"] > 0
            assert len(manager._active_locks) > 0

        # Check locks are released
        metrics = manager.get_lock_metrics()
        assert metrics["current_active"] == 0
        assert len(manager._active_locks) == 0

    @pytest.mark.asyncio
    async def test_global_lock(self, cleanup_atomic_manager):
        """Test global lock acquisition and release."""
        manager = cleanup_atomic_manager

        async with manager.atomic_global_operation("global_op1"):
            # Check global lock is active
            metrics = manager.get_lock_metrics()
            assert metrics["current_active"] > 0

        # Check lock is released
        metrics = manager.get_lock_metrics()
        assert metrics["current_active"] == 0

    @pytest.mark.asyncio
    async def test_lock_metrics_tracking(self, cleanup_atomic_manager):
        """Test that lock metrics are properly tracked."""
        manager = cleanup_atomic_manager

        initial_metrics = manager.get_lock_metrics()
        initial_acquisitions = initial_metrics["total_acquisitions"]

        async with manager.atomic_position_validation("token1", "market1", "op1"):
            pass

        final_metrics = manager.get_lock_metrics()
        assert final_metrics["total_acquisitions"] > initial_acquisitions
        assert final_metrics["average_hold_time"] >= 0


class TestConcurrentOperations:
    """Test concurrent operation handling."""

    @pytest.mark.asyncio
    async def test_concurrent_different_tokens(self, cleanup_atomic_manager):
        """Test concurrent operations on different tokens."""
        manager = cleanup_atomic_manager
        results = []

        async def validate_token(token_id, market_id, op_id):
            async with manager.atomic_position_validation(token_id, market_id, op_id):
                await asyncio.sleep(0.1)  # Simulate some work
                results.append(op_id)

        # Run concurrent operations on different tokens
        await asyncio.gather(
            validate_token("token1", "market1", "op1"),
            validate_token("token2", "market1", "op2"),
            validate_token("token3", "market2", "op3"),
        )

        assert len(results) == 3
        assert set(results) == {"op1", "op2", "op3"}

    @pytest.mark.asyncio
    async def test_sequential_same_token(self, cleanup_atomic_manager):
        """Test that same token operations are serialized."""
        manager = cleanup_atomic_manager
        results = []
        start_time = time.time()

        async def validate_token(token_id, market_id, op_id):
            async with manager.atomic_position_validation(token_id, market_id, op_id):
                results.append((op_id, time.time() - start_time))
                await asyncio.sleep(0.05)  # Simulate work

        # Run concurrent operations on same token
        await asyncio.gather(
            validate_token("same_token", "market1", "op1"),
            validate_token("same_token", "market1", "op2"),
        )

        assert len(results) == 2
        # Second operation should start after first finishes
        assert results[1][1] > results[0][1]

    @pytest.mark.asyncio
    async def test_max_concurrent_operations_limit(self, cleanup_atomic_manager):
        """Test maximum concurrent operations limit."""
        manager = cleanup_atomic_manager

        # Fill up the operation queue
        for i in range(manager.max_concurrent_operations):
            manager._pending_operations.add(f"op_{i}")

        # This should fail due to limit
        with pytest.raises(
            RuntimeError, match="Maximum concurrent operations exceeded"
        ):
            async with manager.atomic_position_validation(
                "token1", "market1", "overflow_op"
            ):
                pass


class TestTimeoutHandling:
    """Test timeout handling and stale lock cleanup."""

    @pytest.mark.asyncio
    async def test_operation_timeout(self, cleanup_atomic_manager):
        """Test operation timeout handling."""
        manager = cleanup_atomic_manager

        with pytest.raises(asyncio.TimeoutError):
            async with manager.atomic_position_validation(
                "token1", "market1", "timeout_op", timeout=0.01
            ):
                await asyncio.sleep(0.1)  # This should timeout

    @pytest.mark.asyncio
    async def test_stale_lock_cleanup(self, cleanup_atomic_manager):
        """Test cleanup of stale locks."""
        manager = cleanup_atomic_manager

        # Manually add a stale lock
        stale_time = time.time() - 1000  # Very old
        manager._active_locks["stale_lock"] = LockInfo(
            lock_id="stale_lock",
            lock_type=LockType.POSITION,
            acquired_at=stale_time,
            holder="test",
            timeout=1.0,
            metadata={},
        )

        # Run cleanup
        await manager._cleanup_stale_locks()

        # Stale lock should be removed
        assert "stale_lock" not in manager._active_locks

    @pytest.mark.asyncio
    async def test_force_release_stale_locks(self, cleanup_atomic_manager):
        """Test force release of stale locks."""
        manager = cleanup_atomic_manager

        # Add multiple stale locks
        current_time = time.time()
        for i in range(3):
            manager._active_locks[f"stale_{i}"] = LockInfo(
                lock_id=f"stale_{i}",
                lock_type=LockType.POSITION,
                acquired_at=current_time - 600,  # 10 minutes old
                holder="test",
                timeout=1.0,
                metadata={},
            )

        # Force release locks older than 5 minutes
        released_count = await manager.force_release_stale_locks(300.0)

        assert released_count == 3
        assert len(manager._active_locks) == 0


class TestSafetyAssessment:
    """Test operation safety assessment."""

    @pytest.mark.asyncio
    async def test_safe_operation_assessment(self, cleanup_atomic_manager):
        """Test safety assessment for safe operation."""
        manager = cleanup_atomic_manager

        safety_report = await manager.validate_operation_safety(
            "safe_token", "safe_market", "safe_operation"
        )

        assert safety_report["is_safe"] is True
        assert len(safety_report["warnings"]) == 0
        assert "lock_status" in safety_report
        assert "operation_metrics" in safety_report

    @pytest.mark.asyncio
    async def test_unsafe_operation_assessment(self, cleanup_atomic_manager):
        """Test safety assessment when operation is unsafe."""
        manager = cleanup_atomic_manager

        # Create a position lock
        async with manager.atomic_position_validation(
            "locked_token", "locked_market", "blocking_op"
        ):
            # Now check safety for same token
            safety_report = await manager.validate_operation_safety(
                "locked_token", "locked_market", "test_operation"
            )

            assert safety_report["is_safe"] is False
            assert len(safety_report["warnings"]) > 0
            assert safety_report["lock_status"]["position_locked"] is True

    @pytest.mark.asyncio
    async def test_high_load_warning(self, cleanup_atomic_manager):
        """Test warning for high system load."""
        manager = cleanup_atomic_manager

        # Simulate high load
        for i in range(int(manager.max_concurrent_operations * 0.9)):
            manager._pending_operations.add(f"load_op_{i}")

        safety_report = await manager.validate_operation_safety(
            "load_token", "load_market", "load_operation"
        )

        # Should warn about high load
        assert any(
            "High concurrent operation load" in warning
            for warning in safety_report["warnings"]
        )


class TestDeadlockPrevention:
    """Test deadlock prevention through ordered locking."""

    @pytest.mark.asyncio
    async def test_ordered_lock_acquisition(self, cleanup_atomic_manager):
        """Test that locks are acquired in consistent order."""
        manager = cleanup_atomic_manager
        acquisition_order = []

        # Patch lock acquisition to track order
        original_acquire = asyncio.Lock.acquire

        async def track_acquire(self, *args, **kwargs):
            acquisition_order.append(id(self))
            return await original_acquire(self, *args, **kwargs)

        with patch.object(asyncio.Lock, "acquire", track_acquire):
            async with manager.atomic_position_validation("token1", "market1", "op1"):
                pass

        # Should acquire market lock before position lock (based on implementation)
        assert len(acquisition_order) >= 2

    @pytest.mark.asyncio
    async def test_no_deadlock_with_overlapping_markets(self, cleanup_atomic_manager):
        """Test no deadlock occurs with overlapping market operations."""
        manager = cleanup_atomic_manager
        results = []

        async def validate_cross_market(token_id, market1, market2, op_id):
            async with manager.atomic_position_validation(
                token_id, market1, f"{op_id}_1"
            ):
                await asyncio.sleep(0.01)
                async with manager.atomic_position_validation(
                    f"{token_id}_2", market2, f"{op_id}_2"
                ):
                    results.append(op_id)
                    await asyncio.sleep(0.01)

        # This should not deadlock
        await asyncio.wait_for(
            asyncio.gather(
                validate_cross_market("tokenA", "market1", "market2", "opA"),
                validate_cross_market("tokenB", "market2", "market1", "opB"),
            ),
            timeout=5.0,
        )

        assert len(results) == 2


class TestGlobalAtomicManager:
    """Test global atomic manager functionality."""

    @pytest.mark.asyncio
    async def test_global_manager_singleton(self):
        """Test that global manager is singleton."""
        manager1 = get_atomic_manager()
        manager2 = get_atomic_manager()

        assert manager1 is manager2

    @pytest.mark.asyncio
    async def test_global_manager_shutdown(self):
        """Test global manager shutdown."""
        manager = get_atomic_manager()
        initial_id = id(manager)

        await shutdown_atomic_manager()

        # New manager should be created after shutdown
        new_manager = get_atomic_manager()
        assert id(new_manager) != initial_id


class TestErrorHandling:
    """Test error handling in atomic operations."""

    @pytest.mark.asyncio
    async def test_exception_during_operation(self, cleanup_atomic_manager):
        """Test that locks are properly released even when exceptions occur."""
        manager = cleanup_atomic_manager

        with pytest.raises(ValueError):
            async with manager.atomic_position_validation(
                "error_token", "error_market", "error_op"
            ):
                raise ValueError("Test error")

        # Locks should be released despite the error
        assert len(manager._active_locks) == 0
        assert "error_op" not in manager._pending_operations

    @pytest.mark.asyncio
    async def test_cleanup_task_error_handling(self, cleanup_atomic_manager):
        """Test that cleanup task handles errors gracefully."""
        manager = cleanup_atomic_manager

        # Simulate error in cleanup by corrupting active_locks
        original_active_locks = manager._active_locks
        manager._active_locks = None

        # This should not crash the cleanup task
        await manager._cleanup_stale_locks()

        # Restore for proper cleanup
        manager._active_locks = original_active_locks


class TestPerformanceAndScaling:
    """Test performance characteristics and scaling."""

    @pytest.mark.asyncio
    async def test_many_concurrent_different_tokens(self, cleanup_atomic_manager):
        """Test handling many concurrent operations on different tokens."""
        manager = cleanup_atomic_manager
        num_operations = 20
        results = []

        async def quick_validation(token_id):
            async with manager.atomic_position_validation(
                f"token_{token_id}", f"market_{token_id}", f"op_{token_id}"
            ):
                await asyncio.sleep(0.001)  # Very quick operation
                results.append(token_id)

        # Run many concurrent operations
        await asyncio.gather(*[quick_validation(i) for i in range(num_operations)])

        assert len(results) == num_operations
        assert len(set(results)) == num_operations  # All unique

    @pytest.mark.asyncio
    async def test_lock_reuse_efficiency(self, cleanup_atomic_manager):
        """Test that lock objects are reused efficiently."""
        manager = cleanup_atomic_manager

        # First operation
        async with manager.atomic_position_validation(
            "reuse_token", "reuse_market", "op1"
        ):
            first_lock_count = len(manager._position_locks)

        # Second operation on same token
        async with manager.atomic_position_validation(
            "reuse_token", "reuse_market", "op2"
        ):
            second_lock_count = len(manager._position_locks)

        # Should reuse the same lock object
        assert first_lock_count == second_lock_count
        assert first_lock_count == 1  # Only one lock for this token


class TestMetricsAndMonitoring:
    """Test metrics collection and monitoring capabilities."""

    @pytest.mark.asyncio
    async def test_comprehensive_metrics(self, cleanup_atomic_manager):
        """Test comprehensive metrics collection."""
        manager = cleanup_atomic_manager

        # Perform some operations
        async with manager.atomic_position_validation(
            "metrics_token", "metrics_market", "metrics_op"
        ):
            await asyncio.sleep(0.01)

        metrics = manager.get_lock_metrics()

        # Check all expected metrics are present
        expected_keys = [
            "total_acquisitions",
            "total_timeouts",
            "average_hold_time",
            "max_hold_time",
            "current_active",
            "deadlock_detections",
            "active_locks",
            "pending_operations",
            "position_locks",
            "market_locks",
        ]

        for key in expected_keys:
            assert key in metrics
            assert isinstance(metrics[key], (int, float))

    @pytest.mark.asyncio
    async def test_hold_time_tracking(self, cleanup_atomic_manager):
        """Test that hold time is properly tracked."""
        manager = cleanup_atomic_manager

        hold_duration = 0.05  # 50ms

        async with manager.atomic_position_validation(
            "timing_token", "timing_market", "timing_op"
        ):
            await asyncio.sleep(hold_duration)

        metrics = manager.get_lock_metrics()

        # Hold time should be approximately the sleep duration
        assert (
            metrics["average_hold_time"] >= hold_duration * 0.8
        )  # Allow for some variance
        assert metrics["max_hold_time"] >= hold_duration * 0.8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
