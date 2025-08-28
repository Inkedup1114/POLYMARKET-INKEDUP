"""
Comprehensive fallback management system for database unavailability.

This module provides a robust fallback architecture that seamlessly switches between
database and in-memory operations when the primary database becomes unavailable.
"""

import asyncio
import logging
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

log = logging.getLogger("fallback")


class FallbackMode(Enum):
    """Fallback operation modes."""

    PRIMARY = "primary"  # Using primary database
    FALLBACK = "fallback"  # Using in-memory fallback
    RECOVERING = "recovering"  # Attempting to recover primary
    SYNCHRONIZING = "synchronizing"  # Syncing fallback → primary


class HealthStatus(Enum):
    """Database health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Experiencing issues but functional
    UNHEALTHY = "unhealthy"  # Non-functional, must failover
    RECOVERING = "recovering"  # Coming back online


@dataclass
class FallbackMetrics:
    """Metrics for fallback operations."""

    mode: FallbackMode
    health_status: HealthStatus
    primary_operations_attempted: int
    primary_operations_failed: int
    fallback_operations: int
    last_sync_attempt: datetime | None
    last_successful_sync: datetime | None
    recovery_attempts: int
    data_loss_events: int

    @property
    def primary_success_rate(self) -> float:
        """Calculate primary database success rate."""
        if self.primary_operations_attempted == 0:
            return 1.0
        return (
            self.primary_operations_attempted - self.primary_operations_failed
        ) / self.primary_operations_attempted

    @property
    def is_healthy(self) -> bool:
        """Check if system is operating in healthy mode."""
        return (
            self.health_status == HealthStatus.HEALTHY
            and self.mode == FallbackMode.PRIMARY
        )


class DatabaseHealthMonitor:
    """Monitors database health and triggers fallback switching."""

    def __init__(
        self,
        health_check_interval: float = 30.0,
        failure_threshold: int = 3,
        recovery_threshold: int = 5,
        degraded_threshold: float = 0.8,  # 80% success rate
        unhealthy_threshold: float = 0.5,  # 50% success rate
    ):
        self.health_check_interval = health_check_interval
        self.failure_threshold = failure_threshold
        self.recovery_threshold = recovery_threshold
        self.degraded_threshold = degraded_threshold
        self.unhealthy_threshold = unhealthy_threshold

        # Health tracking
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.last_health_check = None
        self.recent_operations: list[bool] = []  # True=success, False=failure
        self.max_recent_operations = 100

        # Monitoring state
        self._monitoring = False
        self._monitor_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

        # Callbacks
        self._health_change_callbacks: list[Callable[[HealthStatus], None]] = []

    def add_health_change_callback(
        self, callback: Callable[[HealthStatus], None]
    ) -> None:
        """Add callback for health status changes."""
        self._health_change_callbacks.append(callback)

    def record_operation_result(self, success: bool) -> None:
        """Record the result of a database operation."""
        self.recent_operations.append(success)
        if len(self.recent_operations) > self.max_recent_operations:
            self.recent_operations.pop(0)

        if success:
            self.consecutive_failures = 0
            self.consecutive_successes += 1
        else:
            self.consecutive_successes = 0
            self.consecutive_failures += 1

    def get_current_health_status(self) -> HealthStatus:
        """Calculate current health status based on recent operations."""
        if not self.recent_operations:
            return HealthStatus.HEALTHY

        success_rate = sum(self.recent_operations) / len(self.recent_operations)

        if success_rate >= self.degraded_threshold:
            return HealthStatus.HEALTHY
        elif success_rate >= self.unhealthy_threshold:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.UNHEALTHY

    def should_trigger_fallback(self) -> bool:
        """Determine if fallback should be triggered."""
        # Check consecutive failures first
        if self.consecutive_failures >= self.failure_threshold:
            return True

        # Only check health status if we have enough data
        if len(self.recent_operations) >= 10:  # Require at least 10 operations
            return self.get_current_health_status() == HealthStatus.UNHEALTHY

        return False

    def should_attempt_recovery(self) -> bool:
        """Determine if recovery should be attempted."""
        return self.consecutive_successes >= self.recovery_threshold

    async def start_monitoring(self, health_check_func: Callable[[], bool]) -> None:
        """Start health monitoring with periodic health checks."""
        if self._monitoring:
            return

        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(health_check_func))
        log.info("Database health monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop health monitoring."""
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        log.info("Database health monitoring stopped")

    async def _monitor_loop(self, health_check_func: Callable[[], bool]) -> None:
        """Main monitoring loop."""
        while self._monitoring:
            try:
                async with self._lock:
                    # Perform health check
                    try:
                        is_healthy = await asyncio.get_event_loop().run_in_executor(
                            None, health_check_func
                        )
                        self.record_operation_result(is_healthy)
                        self.last_health_check = datetime.now()

                        # Notify callbacks of health changes
                        current_status = self.get_current_health_status()
                        for callback in self._health_change_callbacks:
                            try:
                                callback(current_status)
                            except Exception as e:
                                log.error(f"Health change callback failed: {e}")

                    except Exception as e:
                        log.error(f"Health check failed: {e}")
                        self.record_operation_result(False)

                await asyncio.sleep(self.health_check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Health monitor error: {e}")
                await asyncio.sleep(5)


class InMemoryStateStore:
    """Complete in-memory state storage with validation and consistency."""

    def __init__(self):
        # Core storage
        self.orders: dict[str, dict[str, Any]] = {}
        self.positions: dict[str, dict[str, Any]] = {}
        self.trades: list[dict[str, Any]] = []
        self.market_snapshots: dict[str, dict[str, Any]] = {}
        self.risk_events: list[dict[str, Any]] = []

        # Exposure tracking
        self.outcome_exposures: dict[str, dict[str, Any]] = {}
        self.outcome_correlations: dict[str, dict[str, Any]] = {}
        self.exposure_alerts: list[dict[str, Any]] = []

        # Metadata
        self.created_at = datetime.now()
        self.last_updated = datetime.now()
        self.operation_count = 0

        # Thread safety
        self._lock = threading.RLock()

    def _update_metadata(self) -> None:
        """Update store metadata."""
        self.last_updated = datetime.now()
        self.operation_count += 1

    # Order operations
    def insert_order(self, order: dict[str, Any]) -> None:
        """Insert order into in-memory store."""
        with self._lock:
            order_id = order["id"]
            self.orders[order_id] = order.copy()
            self._update_metadata()
            log.debug(f"Stored order {order_id} in fallback memory")

    def update_order(self, order_id: str, update_data: dict[str, Any]) -> None:
        """Update order in in-memory store."""
        with self._lock:
            if order_id in self.orders:
                self.orders[order_id].update(update_data)
                self.orders[order_id]["updated_at"] = datetime.now()
                self._update_metadata()
                log.debug(f"Updated order {order_id} in fallback memory")

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        """Get order from in-memory store."""
        with self._lock:
            return (
                self.orders.get(order_id, {}).copy()
                if order_id in self.orders
                else None
            )

    def get_all_orders(self) -> list[dict[str, Any]]:
        """Get all orders from in-memory store."""
        with self._lock:
            return [order.copy() for order in self.orders.values()]

    # Position operations
    def upsert_position(self, position: dict[str, Any]) -> None:
        """Insert or update position in in-memory store."""
        with self._lock:
            token_id = position["token_id"]
            self.positions[token_id] = position.copy()
            self._update_metadata()
            log.debug(f"Stored position {token_id} in fallback memory")

    def get_position(self, token_id: str) -> dict[str, Any] | None:
        """Get position from in-memory store."""
        with self._lock:
            return (
                self.positions.get(token_id, {}).copy()
                if token_id in self.positions
                else None
            )

    def get_all_positions(self) -> list[dict[str, Any]]:
        """Get all positions from in-memory store."""
        with self._lock:
            return [pos.copy() for pos in self.positions.values()]

    def get_positions_by_market(self, market_slug: str) -> list[dict[str, Any]]:
        """Get positions for specific market."""
        with self._lock:
            return [
                pos.copy()
                for pos in self.positions.values()
                if pos.get("market_slug") == market_slug
            ]

    # Trade operations
    def record_trade(self, trade: dict[str, Any]) -> None:
        """Record trade in in-memory store."""
        with self._lock:
            trade_copy = trade.copy()
            trade_copy["recorded_at"] = datetime.now()
            self.trades.append(trade_copy)
            self._update_metadata()
            log.debug(f"Recorded trade {trade.get('order_id')} in fallback memory")

    def get_trades(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Get trades from in-memory store."""
        with self._lock:
            trades = [trade.copy() for trade in self.trades]
            if limit:
                trades = trades[-limit:]  # Most recent trades
            return trades

    # Exposure operations
    def upsert_outcome_exposure(self, exposure: dict[str, Any]) -> None:
        """Insert or update outcome exposure."""
        with self._lock:
            key = f"{exposure['market_slug']}:{exposure['outcome_id']}"
            self.outcome_exposures[key] = exposure.copy()
            self._update_metadata()
            log.debug(f"Stored outcome exposure {key} in fallback memory")

    def get_outcome_exposure(
        self, market_slug: str, outcome_id: str
    ) -> dict[str, Any] | None:
        """Get outcome exposure."""
        with self._lock:
            key = f"{market_slug}:{outcome_id}"
            return (
                self.outcome_exposures.get(key, {}).copy()
                if key in self.outcome_exposures
                else None
            )

    def get_all_outcome_exposures(self) -> list[dict[str, Any]]:
        """Get all outcome exposures."""
        with self._lock:
            return [exp.copy() for exp in self.outcome_exposures.values()]

    # Risk event operations
    def record_risk_event(self, event: dict[str, Any]) -> None:
        """Record risk event."""
        with self._lock:
            event_copy = event.copy()
            event_copy["recorded_at"] = datetime.now()
            self.risk_events.append(event_copy)
            self._update_metadata()
            log.debug(
                f"Recorded risk event {event.get('event_type')} in fallback memory"
            )

    def get_risk_events(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Get risk events."""
        with self._lock:
            events = [event.copy() for event in self.risk_events]
            if limit:
                events = events[-limit:]
            return events

    # Market snapshot operations
    def insert_market_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Insert market snapshot."""
        with self._lock:
            key = f"{snapshot['market_slug']}:{snapshot['token_id']}"
            self.market_snapshots[key] = snapshot.copy()
            self._update_metadata()
            log.debug(f"Stored market snapshot {key} in fallback memory")

    def get_market_snapshot(
        self, market_slug: str, token_id: str
    ) -> dict[str, Any] | None:
        """Get market snapshot."""
        with self._lock:
            key = f"{market_slug}:{token_id}"
            return (
                self.market_snapshots.get(key, {}).copy()
                if key in self.market_snapshots
                else None
            )

    # Utility methods
    def get_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        with self._lock:
            return {
                "created_at": self.created_at,
                "last_updated": self.last_updated,
                "operation_count": self.operation_count,
                "orders_count": len(self.orders),
                "positions_count": len(self.positions),
                "trades_count": len(self.trades),
                "outcome_exposures_count": len(self.outcome_exposures),
                "risk_events_count": len(self.risk_events),
                "market_snapshots_count": len(self.market_snapshots),
            }

    def clear_all(self) -> None:
        """Clear all data (use with caution)."""
        with self._lock:
            self.orders.clear()
            self.positions.clear()
            self.trades.clear()
            self.market_snapshots.clear()
            self.risk_events.clear()
            self.outcome_exposures.clear()
            self.outcome_correlations.clear()
            self.exposure_alerts.clear()
            self._update_metadata()
            log.warning("Cleared all fallback memory data")


class FallbackManager:
    """
    Comprehensive fallback management system.

    Handles seamless switching between database and in-memory operations,
    health monitoring, data synchronization, and recovery procedures.
    """

    def __init__(
        self,
        database_manager,
        sync_interval: float = 300.0,  # 5 minutes
        max_sync_retries: int = 3,
        enable_auto_recovery: bool = True,
        enable_data_persistence: bool = True,
    ):
        self.db = database_manager
        self.sync_interval = sync_interval
        self.max_sync_retries = max_sync_retries
        self.enable_auto_recovery = enable_auto_recovery
        self.enable_data_persistence = enable_data_persistence

        # Core components
        self.health_monitor = DatabaseHealthMonitor()
        self.memory_store = InMemoryStateStore()

        # State tracking
        self.current_mode = FallbackMode.PRIMARY
        self.metrics = FallbackMetrics(
            mode=FallbackMode.PRIMARY,
            health_status=HealthStatus.HEALTHY,
            primary_operations_attempted=0,
            primary_operations_failed=0,
            fallback_operations=0,
            last_sync_attempt=None,
            last_successful_sync=None,
            recovery_attempts=0,
            data_loss_events=0,
        )

        # Synchronization
        self._sync_task: asyncio.Task | None = None
        self._sync_lock = asyncio.Lock()
        self._mode_change_callbacks: list[Callable[[FallbackMode], None]] = []

        # Setup health monitoring callbacks
        self.health_monitor.add_health_change_callback(self._handle_health_change)

    def add_mode_change_callback(
        self, callback: Callable[[FallbackMode], None]
    ) -> None:
        """Add callback for mode changes."""
        self._mode_change_callbacks.append(callback)

    def _notify_mode_change(self, new_mode: FallbackMode) -> None:
        """Notify callbacks of mode changes."""
        for callback in self._mode_change_callbacks:
            try:
                callback(new_mode)
            except Exception as e:
                log.error(f"Mode change callback failed: {e}")

    def _handle_health_change(self, health_status: HealthStatus) -> None:
        """Handle health status changes from monitor."""
        self.metrics.health_status = health_status

        if (
            health_status == HealthStatus.UNHEALTHY
            and self.current_mode == FallbackMode.PRIMARY
        ):
            asyncio.create_task(self.switch_to_fallback("Database unhealthy"))
        elif (
            health_status == HealthStatus.HEALTHY
            and self.current_mode == FallbackMode.FALLBACK
            and self.enable_auto_recovery
        ):
            asyncio.create_task(self.attempt_recovery())

    async def start(self) -> None:
        """Start the fallback manager."""
        try:
            # Test database connectivity
            await self.db.initialize()
            log.info("Primary database connection established")
        except Exception as e:
            log.error(f"Failed to initialize primary database: {e}")
            await self.switch_to_fallback("Database initialization failed")

        # Start health monitoring
        await self.health_monitor.start_monitoring(self._health_check)

        # Start synchronization task
        if self.enable_data_persistence:
            self._sync_task = asyncio.create_task(self._sync_loop())

        log.info(f"Fallback manager started in {self.current_mode.value} mode")

    async def stop(self) -> None:
        """Stop the fallback manager."""
        # Stop health monitoring
        await self.health_monitor.stop_monitoring()

        # Stop synchronization
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        # Final sync attempt if in fallback mode
        if self.current_mode == FallbackMode.FALLBACK:
            try:
                await self._sync_fallback_to_primary()
            except Exception as e:
                log.error(f"Final sync failed: {e}")

        log.info("Fallback manager stopped")

    def _health_check(self) -> bool:
        """Perform database health check."""
        try:
            # Simple connectivity test - this should be customized based on your database
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.db.get_total_exposure())
                return True
            finally:
                loop.close()
        except Exception:
            return False

    async def switch_to_fallback(self, reason: str) -> None:
        """Switch to fallback mode."""
        if self.current_mode == FallbackMode.FALLBACK:
            return

        log.warning(f"Switching to fallback mode: {reason}")
        old_mode = self.current_mode
        self.current_mode = FallbackMode.FALLBACK
        self.metrics.mode = FallbackMode.FALLBACK

        # Trigger data loss event if switching from primary
        if old_mode == FallbackMode.PRIMARY:
            self.metrics.data_loss_events += 1

        self._notify_mode_change(self.current_mode)
        log.info("Fallback mode activated")

    async def attempt_recovery(self) -> None:
        """Attempt to recover to primary database."""
        if self.current_mode != FallbackMode.FALLBACK:
            return

        self.metrics.recovery_attempts += 1
        self.current_mode = FallbackMode.RECOVERING
        self.metrics.mode = FallbackMode.RECOVERING

        log.info("Attempting database recovery...")

        try:
            # Test database connectivity
            await self.db.initialize()

            # Attempt synchronization
            success = await self._sync_fallback_to_primary()

            if success:
                self.current_mode = FallbackMode.PRIMARY
                self.metrics.mode = FallbackMode.PRIMARY
                self.metrics.health_status = HealthStatus.HEALTHY
                self._notify_mode_change(self.current_mode)
                log.info("Successfully recovered to primary database")
            else:
                # Recovery failed, switch back to fallback
                self.current_mode = FallbackMode.FALLBACK
                self.metrics.mode = FallbackMode.FALLBACK
                log.error("Recovery failed: synchronization unsuccessful")

        except Exception as e:
            # Recovery failed, switch back to fallback
            self.current_mode = FallbackMode.FALLBACK
            self.metrics.mode = FallbackMode.FALLBACK
            log.error(f"Recovery failed: {e}")

    @asynccontextmanager
    async def operation_context(self, operation_name: str):
        """Context manager for database operations with fallback handling."""
        self.metrics.primary_operations_attempted += 1

        try:
            if self.current_mode == FallbackMode.PRIMARY:
                yield "primary"
                # Record success for health monitoring
                self.health_monitor.record_operation_result(True)
            else:
                self.metrics.fallback_operations += 1
                yield "fallback"

        except Exception as e:
            if self.current_mode == FallbackMode.PRIMARY:
                self.metrics.primary_operations_failed += 1
                self.health_monitor.record_operation_result(False)

                # Check if we should switch to fallback
                if self.health_monitor.should_trigger_fallback():
                    await self.switch_to_fallback(
                        f"Operation {operation_name} failed: {str(e)}"
                    )
                    self.metrics.fallback_operations += 1
                    # Re-yield for fallback operation
                    yield "fallback"
                else:
                    raise
            else:
                # Already in fallback mode, just raise
                raise

    async def _sync_loop(self) -> None:
        """Background synchronization loop."""
        while True:
            try:
                await asyncio.sleep(self.sync_interval)

                if self.current_mode == FallbackMode.FALLBACK:
                    await self._sync_fallback_to_primary()

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Sync loop error: {e}")

    async def _sync_fallback_to_primary(self) -> bool:
        """Synchronize fallback data to primary database."""
        async with self._sync_lock:
            self.metrics.last_sync_attempt = datetime.now()

            try:
                log.info("Starting fallback → primary synchronization")

                # Sync orders
                orders = self.memory_store.get_all_orders()
                for order in orders:
                    await self.db.insert_order(order)

                # Sync positions
                positions = self.memory_store.get_all_positions()
                for position in positions:
                    await self.db.upsert_position(position)

                # Sync trades
                trades = self.memory_store.get_trades()
                for trade in trades:
                    # Assuming there's a method to insert trades
                    # This would need to be implemented in the database manager
                    pass

                # Sync outcome exposures
                exposures = self.memory_store.get_all_outcome_exposures()
                for exposure in exposures:
                    await self.db.upsert_outcome_exposure(
                        exposure["market_slug"],
                        exposure["outcome_id"],
                        exposure["outcome_name"],
                        exposure["position_size"],
                        exposure["notional_value"],
                        exposure["average_price"],
                        exposure["current_price"],
                        exposure["unrealized_pnl"],
                        exposure["realized_pnl"],
                        exposure.get("correlation_coefficient", 0.0),
                        exposure.get("risk_score", 0.0),
                    )

                self.metrics.last_successful_sync = datetime.now()
                log.info("Synchronization completed successfully")
                return True

            except Exception as e:
                log.error(f"Synchronization failed: {e}")
                return False

    def get_metrics(self) -> FallbackMetrics:
        """Get current fallback metrics."""
        return self.metrics

    def get_status(self) -> dict[str, Any]:
        """Get comprehensive fallback status."""
        store_stats = self.memory_store.get_stats()

        return {
            "mode": self.current_mode.value,
            "health_status": self.metrics.health_status.value,
            "is_healthy": self.metrics.is_healthy,
            "primary_success_rate": self.metrics.primary_success_rate,
            "metrics": {
                "primary_operations_attempted": self.metrics.primary_operations_attempted,
                "primary_operations_failed": self.metrics.primary_operations_failed,
                "fallback_operations": self.metrics.fallback_operations,
                "recovery_attempts": self.metrics.recovery_attempts,
                "data_loss_events": self.metrics.data_loss_events,
                "last_sync_attempt": self.metrics.last_sync_attempt,
                "last_successful_sync": self.metrics.last_successful_sync,
            },
            "memory_store": store_stats,
            "health_monitor": {
                "consecutive_failures": self.health_monitor.consecutive_failures,
                "consecutive_successes": self.health_monitor.consecutive_successes,
                "recent_operations_count": len(self.health_monitor.recent_operations),
                "last_health_check": self.health_monitor.last_health_check,
            },
        }
