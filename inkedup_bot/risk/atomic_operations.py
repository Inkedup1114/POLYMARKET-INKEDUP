"""
Atomic operations manager for race condition prevention in position validation.

This module provides mechanisms to ensure that position validation and updates
are performed atomically to prevent race conditions in concurrent trading environments.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class LockType(Enum):
    """Types of locks available for atomic operations."""

    POSITION = "position"
    MARKET = "market"
    GLOBAL = "global"
    VALIDATION = "validation"


@dataclass
class LockInfo:
    """Information about an active lock."""

    lock_id: str
    lock_type: LockType
    acquired_at: float
    holder: str
    timeout: float
    metadata: dict[str, Any]


class AtomicOperationManager:
    """
    Manages atomic operations to prevent race conditions in position validation and updates.

    Features:
    - Hierarchical locking (position -> market -> global)
    - Deadlock prevention through ordered lock acquisition
    - Timeout handling for stale locks
    - Lock monitoring and metrics
    - Concurrent operation limiting
    """

    def __init__(
        self, default_timeout: float = 30.0, max_concurrent_operations: int = 100
    ):
        self.default_timeout = default_timeout
        self.max_concurrent_operations = max_concurrent_operations

        # Lock storage
        self._position_locks: dict[str, asyncio.Lock] = {}
        self._market_locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._validation_lock = asyncio.Lock()

        # Lock metadata tracking
        self._active_locks: dict[str, LockInfo] = {}
        self._lock_acquisition_times: dict[str, float] = {}
        self._lock_metrics: dict[str, Any] = {
            "total_acquisitions": 0,
            "total_timeouts": 0,
            "average_hold_time": 0.0,
            "max_hold_time": 0.0,
            "current_active": 0,
            "deadlock_detections": 0,
        }

        # Operation tracking
        self._pending_operations: set[str] = set()
        self._operation_queue: asyncio.Queue = asyncio.Queue()

        # Cleanup task (initialized lazily)
        self._cleanup_task: asyncio.Task | None = None
        self._cleanup_started = False

    def _ensure_cleanup_task(self):
        """Ensure the background cleanup task is started."""
        if not self._cleanup_started:
            try:
                if self._cleanup_task is None or self._cleanup_task.done():
                    self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
                    self._cleanup_started = True
            except RuntimeError:
                # No event loop running, will start later when needed
                pass

    async def _periodic_cleanup(self):
        """Periodically clean up stale locks."""
        while True:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                await self._cleanup_stale_locks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")

    async def _cleanup_stale_locks(self):
        """Clean up locks that have exceeded their timeout."""
        current_time = time.time()
        stale_locks = []

        for lock_id, lock_info in self._active_locks.items():
            if current_time - lock_info.acquired_at > lock_info.timeout:
                stale_locks.append(lock_id)

        for lock_id in stale_locks:
            lock_info = self._active_locks.pop(lock_id, None)
            if lock_info:
                logger.warning(
                    f"Cleaned up stale lock: {lock_id} (held for {current_time - lock_info.acquired_at:.2f}s)"
                )
                self._lock_metrics["total_timeouts"] += 1

    def _get_position_lock(self, token_id: str) -> asyncio.Lock:
        """Get or create a lock for a specific position."""
        if token_id not in self._position_locks:
            self._position_locks[token_id] = asyncio.Lock()
        return self._position_locks[token_id]

    def _get_market_lock(self, market_slug: str) -> asyncio.Lock:
        """Get or create a lock for a specific market."""
        if market_slug not in self._market_locks:
            self._market_locks[market_slug] = asyncio.Lock()
        return self._market_locks[market_slug]

    @asynccontextmanager
    async def atomic_position_validation(
        self,
        token_id: str,
        market_slug: str,
        operation_id: str,
        timeout: float | None = None,
    ):
        """
        Context manager for atomic position validation and update operations.

        Acquires locks in the correct order to prevent deadlocks:
        1. Global validation lock (if needed)
        2. Market lock
        3. Position lock

        Args:
            token_id: Token identifier
            market_slug: Market identifier
            operation_id: Unique identifier for this operation
            timeout: Timeout in seconds (uses default if None)
        """
        timeout = timeout or self.default_timeout
        start_time = time.time()
        acquired_locks = []

        # Ensure cleanup task is running
        self._ensure_cleanup_task()

        # Check if we've exceeded max concurrent operations
        if len(self._pending_operations) >= self.max_concurrent_operations:
            raise RuntimeError("Maximum concurrent operations exceeded")

        self._pending_operations.add(operation_id)

        try:
            # Acquire locks in hierarchical order to prevent deadlocks

            # 1. Market lock
            market_lock = self._get_market_lock(market_slug)
            lock_acquired = await asyncio.wait_for(
                market_lock.acquire(), timeout=timeout
            )
            if lock_acquired is False:
                raise TimeoutError(f"Failed to acquire market lock for {market_slug}")

            market_lock_id = f"market_{market_slug}_{operation_id}"
            self._track_lock_acquisition(
                market_lock_id, LockType.MARKET, operation_id, timeout
            )
            acquired_locks.append((market_lock, market_lock_id))

            # 2. Position lock
            position_lock = self._get_position_lock(token_id)
            lock_acquired = await asyncio.wait_for(
                position_lock.acquire(), timeout=timeout
            )
            if lock_acquired is False:
                raise TimeoutError(f"Failed to acquire position lock for {token_id}")

            position_lock_id = f"position_{token_id}_{operation_id}"
            self._track_lock_acquisition(
                position_lock_id, LockType.POSITION, operation_id, timeout
            )
            acquired_locks.append((position_lock, position_lock_id))

            # Track successful acquisition
            self._lock_metrics["total_acquisitions"] += 1
            self._lock_metrics["current_active"] += 1

            logger.debug(
                f"Acquired atomic locks for operation {operation_id}: {token_id} @ {market_slug}"
            )

            yield operation_id

        except TimeoutError:
            self._lock_metrics["total_timeouts"] += 1
            logger.error(f"Timeout acquiring locks for operation {operation_id}")
            raise

        except Exception as e:
            logger.error(f"Error in atomic operation {operation_id}: {e}")
            raise

        finally:
            # Release locks in reverse order
            for lock, lock_id in reversed(acquired_locks):
                try:
                    lock.release()
                    self._track_lock_release(lock_id, start_time)
                except Exception as e:
                    logger.error(f"Error releasing lock {lock_id}: {e}")

            self._pending_operations.discard(operation_id)
            if acquired_locks:
                self._lock_metrics["current_active"] -= 1

            logger.debug(f"Released atomic locks for operation {operation_id}")

    @asynccontextmanager
    async def atomic_global_operation(
        self, operation_id: str, timeout: float | None = None
    ):
        """
        Context manager for global atomic operations (e.g., portfolio rebalancing).

        Args:
            operation_id: Unique identifier for this operation
            timeout: Timeout in seconds
        """
        timeout = timeout or self.default_timeout
        start_time = time.time()

        # Ensure cleanup task is running
        self._ensure_cleanup_task()

        try:
            # Acquire global lock
            await asyncio.wait_for(self._global_lock.acquire(), timeout=timeout)

            global_lock_id = f"global_{operation_id}"
            self._track_lock_acquisition(
                global_lock_id, LockType.GLOBAL, operation_id, timeout
            )

            self._lock_metrics["total_acquisitions"] += 1
            self._lock_metrics["current_active"] += 1

            logger.debug(f"Acquired global lock for operation {operation_id}")

            yield operation_id

        except TimeoutError:
            self._lock_metrics["total_timeouts"] += 1
            logger.error(f"Timeout acquiring global lock for operation {operation_id}")
            raise

        finally:
            try:
                self._global_lock.release()
                self._track_lock_release(global_lock_id, start_time)
                self._lock_metrics["current_active"] -= 1
                logger.debug(f"Released global lock for operation {operation_id}")
            except Exception as e:
                logger.error(f"Error releasing global lock: {e}")

    async def validate_operation_safety(
        self, token_id: str, market_slug: str, operation_type: str
    ) -> dict[str, Any]:
        """
        Validate if an operation can be performed safely without race conditions.

        Returns:
            Dictionary with safety assessment and recommendations
        """
        current_time = time.time()
        safety_report = {
            "is_safe": True,
            "warnings": [],
            "recommendations": [],
            "lock_status": {},
            "operation_metrics": {},
        }

        # Check for existing locks
        position_lock_active = any(
            lock_info.lock_type == LockType.POSITION and token_id in lock_info.lock_id
            for lock_info in self._active_locks.values()
        )

        market_lock_active = any(
            lock_info.lock_type == LockType.MARKET and market_slug in lock_info.lock_id
            for lock_info in self._active_locks.values()
        )

        global_lock_active = any(
            lock_info.lock_type == LockType.GLOBAL
            for lock_info in self._active_locks.values()
        )

        safety_report["lock_status"] = {
            "position_locked": position_lock_active,
            "market_locked": market_lock_active,
            "global_locked": global_lock_active,
        }

        # Assess safety
        if position_lock_active:
            safety_report["warnings"].append(
                f"Position {token_id} currently locked by another operation"
            )
            safety_report["is_safe"] = False

        if market_lock_active:
            safety_report["warnings"].append(
                f"Market {market_slug} currently locked by another operation"
            )
            safety_report["is_safe"] = False

        if global_lock_active:
            safety_report["warnings"].append(
                "Global lock active - system-wide operation in progress"
            )
            safety_report["is_safe"] = False

        # Check concurrent operation limits
        current_operations = len(self._pending_operations)
        if current_operations >= self.max_concurrent_operations * 0.8:  # 80% threshold
            safety_report["warnings"].append(
                f"High concurrent operation load: {current_operations}/{self.max_concurrent_operations}"
            )
            if current_operations >= self.max_concurrent_operations:
                safety_report["is_safe"] = False

        # Add operation metrics
        safety_report["operation_metrics"] = {
            "current_operations": current_operations,
            "max_operations": self.max_concurrent_operations,
            "active_locks": len(self._active_locks),
            "average_hold_time": self._lock_metrics.get("average_hold_time", 0.0),
        }

        # Recommendations
        if not safety_report["is_safe"]:
            safety_report["recommendations"].append(
                "Wait for current operations to complete"
            )
            safety_report["recommendations"].append(
                "Consider reducing operation frequency"
            )

        return safety_report

    def _track_lock_acquisition(
        self, lock_id: str, lock_type: LockType, holder: str, timeout: float
    ):
        """Track lock acquisition for monitoring."""
        current_time = time.time()

        self._active_locks[lock_id] = LockInfo(
            lock_id=lock_id,
            lock_type=lock_type,
            acquired_at=current_time,
            holder=holder,
            timeout=timeout,
            metadata={},
        )

        self._lock_acquisition_times[lock_id] = current_time

    def _track_lock_release(self, lock_id: str, operation_start_time: float):
        """Track lock release and update metrics."""
        current_time = time.time()

        # Remove from active locks
        lock_info = self._active_locks.pop(lock_id, None)
        acquisition_time = self._lock_acquisition_times.pop(lock_id, None)

        if lock_info and acquisition_time:
            hold_time = current_time - acquisition_time

            # Update hold time metrics
            current_avg = self._lock_metrics.get("average_hold_time", 0.0)
            total_acquisitions = self._lock_metrics.get("total_acquisitions", 1)
            new_avg = (
                current_avg * (total_acquisitions - 1) + hold_time
            ) / total_acquisitions

            self._lock_metrics["average_hold_time"] = new_avg
            self._lock_metrics["max_hold_time"] = max(
                self._lock_metrics.get("max_hold_time", 0.0), hold_time
            )

    def get_lock_metrics(self) -> dict[str, Any]:
        """Get current lock and operation metrics."""
        return {
            **self._lock_metrics,
            "active_locks": len(self._active_locks),
            "pending_operations": len(self._pending_operations),
            "position_locks": len(self._position_locks),
            "market_locks": len(self._market_locks),
        }

    async def force_release_stale_locks(self, max_age_seconds: float = 300.0) -> int:
        """Force release locks older than specified age. Returns count of released locks."""
        current_time = time.time()
        released_count = 0

        stale_locks = [
            lock_id
            for lock_id, lock_info in self._active_locks.items()
            if current_time - lock_info.acquired_at > max_age_seconds
        ]

        for lock_id in stale_locks:
            lock_info = self._active_locks.pop(lock_id, None)
            if lock_info:
                released_count += 1
                logger.warning(f"Force released stale lock: {lock_id}")

        return released_count

    async def shutdown(self):
        """Shutdown the atomic operations manager and cleanup resources."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Force release all remaining locks
        released_count = await self.force_release_stale_locks(0.0)
        if released_count > 0:
            logger.info(f"Released {released_count} locks during shutdown")

        logger.info("Atomic operations manager shutdown complete")


# Global instance for shared use
_global_atomic_manager: AtomicOperationManager | None = None


def get_atomic_manager() -> AtomicOperationManager:
    """Get the global atomic operations manager instance."""
    global _global_atomic_manager
    if _global_atomic_manager is None:
        _global_atomic_manager = AtomicOperationManager()
    return _global_atomic_manager


async def shutdown_atomic_manager():
    """Shutdown the global atomic operations manager."""
    global _global_atomic_manager
    if _global_atomic_manager is not None:
        await _global_atomic_manager.shutdown()
        _global_atomic_manager = None
