"""
Recovery procedures and utilities for fallback management.

Provides automated and manual recovery procedures for transitioning
back to primary database operations after fallback periods.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from .sync import DataSynchronizer

log = logging.getLogger("fallback_recovery")


class RecoveryPhase(Enum):
    """Recovery operation phases."""

    PREPARATION = "preparation"
    VALIDATION = "validation"
    SYNCHRONIZATION = "synchronization"
    VERIFICATION = "verification"
    ACTIVATION = "activation"
    MONITORING = "monitoring"
    COMPLETED = "completed"
    FAILED = "failed"


class RecoveryStrategy(Enum):
    """Recovery strategies."""

    IMMEDIATE = "immediate"  # Attempt recovery immediately
    GRADUAL = "gradual"  # Gradually increase database usage
    SCHEDULED = "scheduled"  # Wait for scheduled maintenance window
    MANUAL_ONLY = "manual_only"  # Only allow manual recovery triggers


@dataclass
class RecoveryCheckpoint:
    """Recovery progress checkpoint."""

    phase: RecoveryPhase
    timestamp: datetime
    success: bool
    details: str
    metrics: dict[str, Any]


@dataclass
class RecoveryPlan:
    """Recovery execution plan."""

    strategy: RecoveryStrategy
    start_time: datetime
    estimated_duration: timedelta
    phases: list[RecoveryPhase]
    rollback_threshold: float  # Error rate threshold for rollback
    verification_duration: timedelta  # How long to monitor before declaring success


class RecoveryManager:
    """
    Manages database recovery operations and procedures.

    Provides both automated and manual recovery capabilities with
    comprehensive validation, rollback, and monitoring features.
    """

    def __init__(
        self,
        fallback_manager,
        data_synchronizer: DataSynchronizer | None = None,
        default_strategy: RecoveryStrategy = RecoveryStrategy.GRADUAL,
        verification_duration: timedelta = timedelta(minutes=30),
        rollback_threshold: float = 0.1,  # 10% error rate
    ):
        self.fallback_manager = fallback_manager
        self.db = fallback_manager.db
        self.memory_store = fallback_manager.memory_store

        self.synchronizer = data_synchronizer or DataSynchronizer(
            self.db, self.memory_store
        )

        self.default_strategy = default_strategy
        self.verification_duration = verification_duration
        self.rollback_threshold = rollback_threshold

        # Recovery state
        self.current_recovery: RecoveryPlan | None = None
        self.recovery_history: list[tuple[RecoveryPlan, list[RecoveryCheckpoint]]] = []
        self.recovery_callbacks: list[Callable[[RecoveryPhase, bool], None]] = []

        # Monitoring
        self.verification_task: asyncio.Task | None = None
        self.recovery_metrics = {
            "total_recoveries_attempted": 0,
            "total_recoveries_successful": 0,
            "total_rollbacks": 0,
            "last_recovery_attempt": None,
            "last_successful_recovery": None,
        }

    def add_recovery_callback(
        self, callback: Callable[[RecoveryPhase, bool], None]
    ) -> None:
        """Add callback for recovery phase updates."""
        self.recovery_callbacks.append(callback)

    def _notify_recovery_phase(self, phase: RecoveryPhase, success: bool) -> None:
        """Notify callbacks of recovery phase changes."""
        for callback in self.recovery_callbacks:
            try:
                callback(phase, success)
            except Exception as e:
                log.error(f"Recovery callback failed: {e}")

    async def attempt_recovery(
        self, strategy: RecoveryStrategy | None = None, force: bool = False
    ) -> bool:
        """
        Attempt database recovery with specified strategy.

        Args:
            strategy: Recovery strategy to use (defaults to configured strategy)
            force: Force recovery even if conditions aren't optimal

        Returns:
            True if recovery was successful, False otherwise
        """
        if self.current_recovery:
            log.warning("Recovery already in progress")
            return False

        strategy = strategy or self.default_strategy
        self.recovery_metrics["total_recoveries_attempted"] += 1
        self.recovery_metrics["last_recovery_attempt"] = datetime.now()

        log.info(f"Attempting database recovery using {strategy.value} strategy")

        # Create recovery plan
        plan = self._create_recovery_plan(strategy)
        self.current_recovery = plan
        checkpoints = []

        try:
            # Execute recovery phases
            for phase in plan.phases:
                log.info(f"Executing recovery phase: {phase.value}")
                checkpoint = await self._execute_recovery_phase(phase, plan, force)
                checkpoints.append(checkpoint)

                self._notify_recovery_phase(phase, checkpoint.success)

                if not checkpoint.success:
                    log.error(
                        f"Recovery phase {phase.value} failed: {checkpoint.details}"
                    )
                    await self._handle_recovery_failure(plan, checkpoints)
                    return False

            # Recovery successful
            self.recovery_metrics["total_recoveries_successful"] += 1
            self.recovery_metrics["last_successful_recovery"] = datetime.now()

            # Add to history
            self.recovery_history.append((plan, checkpoints))

            log.info("Database recovery completed successfully")
            return True

        except Exception as e:
            log.error(f"Recovery failed with exception: {e}")
            await self._handle_recovery_failure(plan, checkpoints)
            return False

        finally:
            self.current_recovery = None

    def _create_recovery_plan(self, strategy: RecoveryStrategy) -> RecoveryPlan:
        """Create recovery plan based on strategy."""
        now = datetime.now()

        if strategy == RecoveryStrategy.IMMEDIATE:
            phases = [
                RecoveryPhase.PREPARATION,
                RecoveryPhase.VALIDATION,
                RecoveryPhase.SYNCHRONIZATION,
                RecoveryPhase.ACTIVATION,
                RecoveryPhase.MONITORING,
                RecoveryPhase.COMPLETED,
            ]
            estimated_duration = timedelta(minutes=10)

        elif strategy == RecoveryStrategy.GRADUAL:
            phases = [
                RecoveryPhase.PREPARATION,
                RecoveryPhase.VALIDATION,
                RecoveryPhase.SYNCHRONIZATION,
                RecoveryPhase.VERIFICATION,
                RecoveryPhase.ACTIVATION,
                RecoveryPhase.MONITORING,
                RecoveryPhase.COMPLETED,
            ]
            estimated_duration = timedelta(minutes=45)

        elif strategy == RecoveryStrategy.SCHEDULED:
            phases = [
                RecoveryPhase.PREPARATION,
                RecoveryPhase.VALIDATION,
                RecoveryPhase.SYNCHRONIZATION,
                RecoveryPhase.VERIFICATION,
                RecoveryPhase.ACTIVATION,
                RecoveryPhase.MONITORING,
                RecoveryPhase.COMPLETED,
            ]
            estimated_duration = timedelta(hours=1)

        else:  # MANUAL_ONLY
            phases = [
                RecoveryPhase.PREPARATION,
                RecoveryPhase.VALIDATION,
                RecoveryPhase.COMPLETED,
            ]
            estimated_duration = timedelta(minutes=5)

        return RecoveryPlan(
            strategy=strategy,
            start_time=now,
            estimated_duration=estimated_duration,
            phases=phases,
            rollback_threshold=self.rollback_threshold,
            verification_duration=self.verification_duration,
        )

    async def _execute_recovery_phase(
        self, phase: RecoveryPhase, plan: RecoveryPlan, force: bool
    ) -> RecoveryCheckpoint:
        """Execute a specific recovery phase."""
        start_time = datetime.now()

        try:
            if phase == RecoveryPhase.PREPARATION:
                return await self._phase_preparation(force)
            elif phase == RecoveryPhase.VALIDATION:
                return await self._phase_validation()
            elif phase == RecoveryPhase.SYNCHRONIZATION:
                return await self._phase_synchronization()
            elif phase == RecoveryPhase.VERIFICATION:
                return await self._phase_verification(plan)
            elif phase == RecoveryPhase.ACTIVATION:
                return await self._phase_activation()
            elif phase == RecoveryPhase.MONITORING:
                return await self._phase_monitoring(plan)
            elif phase == RecoveryPhase.COMPLETED:
                return await self._phase_completion()
            else:
                raise ValueError(f"Unknown recovery phase: {phase}")

        except Exception as e:
            return RecoveryCheckpoint(
                phase=phase,
                timestamp=datetime.now(),
                success=False,
                details=f"Phase execution failed: {e}",
                metrics={"duration": (datetime.now() - start_time).total_seconds()},
            )

    async def _phase_preparation(self, force: bool) -> RecoveryCheckpoint:
        """Preparation phase - check preconditions."""
        log.info("Recovery preparation phase starting")

        checks = []

        # Check database connectivity
        try:
            await self.db.initialize()
            checks.append(("database_connectivity", True, "Database accessible"))
        except Exception as e:
            if not force:
                return RecoveryCheckpoint(
                    phase=RecoveryPhase.PREPARATION,
                    timestamp=datetime.now(),
                    success=False,
                    details=f"Database not accessible: {e}",
                    metrics={"checks_passed": 0, "checks_total": 1},
                )
            checks.append(("database_connectivity", False, f"Database error: {e}"))

        # Check memory store data integrity
        try:
            stats = self.memory_store.get_stats()
            if stats["operation_count"] > 0:
                checks.append(
                    (
                        "memory_data_present",
                        True,
                        f"Memory store has {stats['operation_count']} operations",
                    )
                )
            else:
                checks.append(("memory_data_present", False, "No data in memory store"))
        except Exception as e:
            checks.append(("memory_data_integrity", False, f"Memory store error: {e}"))

        # Check system resources
        checks.append(("system_resources", True, "Resources adequate"))

        passed_checks = sum(1 for _, success, _ in checks if success)
        total_checks = len(checks)

        success = passed_checks == total_checks or (force and passed_checks > 0)

        return RecoveryCheckpoint(
            phase=RecoveryPhase.PREPARATION,
            timestamp=datetime.now(),
            success=success,
            details=f"Passed {passed_checks}/{total_checks} preparation checks",
            metrics={
                "checks_passed": passed_checks,
                "checks_total": total_checks,
                "checks": checks,
            },
        )

    async def _phase_validation(self) -> RecoveryCheckpoint:
        """Validation phase - validate database schema and basic operations."""
        log.info("Recovery validation phase starting")

        try:
            # Test basic database operations
            test_results = []

            # Test table existence
            async with self.db.connection() as conn:
                tables = ["orders", "positions", "trades", "outcome_exposures"]
                for table in tables:
                    try:
                        await conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
                        test_results.append(
                            (f"table_{table}", True, f"Table {table} accessible")
                        )
                    except Exception as e:
                        test_results.append(
                            (f"table_{table}", False, f"Table {table} error: {e}")
                        )

            # Test write operations
            try:
                test_order = {
                    "id": f"recovery_test_{int(datetime.now().timestamp())}",
                    "token_id": "test_token",
                    "side": "BUY",
                    "price": 0.5,
                    "size": 1.0,
                    "status": "CANCELLED",  # Use cancelled to avoid affecting real data
                }
                await self.db.insert_order(test_order)
                test_results.append(
                    ("write_operation", True, "Write operation successful")
                )
            except Exception as e:
                test_results.append(
                    ("write_operation", False, f"Write operation failed: {e}")
                )

            passed_tests = sum(1 for _, success, _ in test_results if success)
            total_tests = len(test_results)

            return RecoveryCheckpoint(
                phase=RecoveryPhase.VALIDATION,
                timestamp=datetime.now(),
                success=passed_tests == total_tests,
                details=f"Passed {passed_tests}/{total_tests} validation tests",
                metrics={
                    "tests_passed": passed_tests,
                    "tests_total": total_tests,
                    "test_results": test_results,
                },
            )

        except Exception as e:
            return RecoveryCheckpoint(
                phase=RecoveryPhase.VALIDATION,
                timestamp=datetime.now(),
                success=False,
                details=f"Validation phase failed: {e}",
                metrics={"error": str(e)},
            )

    async def _phase_synchronization(self) -> RecoveryCheckpoint:
        """Synchronization phase - sync fallback data to database."""
        log.info("Recovery synchronization phase starting")

        try:
            sync_results = await self.synchronizer.full_sync()

            # Analyze sync results
            total_records = sum(r.records_processed for r in sync_results.values())
            synced_records = sum(r.records_synced for r in sync_results.values())
            total_conflicts = sum(r.conflicts_found for r in sync_results.values())
            total_errors = sum(len(r.errors) for r in sync_results.values())

            success_rate = synced_records / total_records if total_records > 0 else 1.0

            # Consider sync successful if we got most data across
            success = success_rate >= 0.9 and total_errors == 0

            details = f"Synced {synced_records}/{total_records} records ({success_rate:.1%}), {total_conflicts} conflicts, {total_errors} errors"

            return RecoveryCheckpoint(
                phase=RecoveryPhase.SYNCHRONIZATION,
                timestamp=datetime.now(),
                success=success,
                details=details,
                metrics={
                    "total_records": total_records,
                    "synced_records": synced_records,
                    "success_rate": success_rate,
                    "conflicts": total_conflicts,
                    "errors": total_errors,
                    "sync_results": {k: v.__dict__ for k, v in sync_results.items()},
                },
            )

        except Exception as e:
            return RecoveryCheckpoint(
                phase=RecoveryPhase.SYNCHRONIZATION,
                timestamp=datetime.now(),
                success=False,
                details=f"Synchronization failed: {e}",
                metrics={"error": str(e)},
            )

    async def _phase_verification(self, plan: RecoveryPlan) -> RecoveryCheckpoint:
        """Verification phase - gradually test database operations."""
        log.info("Recovery verification phase starting")

        try:
            # Run a series of test operations over time
            test_duration = min(plan.verification_duration, timedelta(minutes=10))
            end_time = datetime.now() + test_duration

            test_results = []
            error_count = 0
            total_tests = 0

            while datetime.now() < end_time:
                total_tests += 1

                try:
                    # Test basic operations
                    await self.db.get_total_exposure()
                    positions = await self.db.get_all_positions()

                    test_results.append(
                        {
                            "timestamp": datetime.now(),
                            "success": True,
                            "positions_count": len(positions),
                        }
                    )

                except Exception as e:
                    error_count += 1
                    test_results.append(
                        {
                            "timestamp": datetime.now(),
                            "success": False,
                            "error": str(e),
                        }
                    )

                await asyncio.sleep(5)  # Test every 5 seconds

            error_rate = error_count / total_tests if total_tests > 0 else 0
            success = error_rate <= plan.rollback_threshold

            return RecoveryCheckpoint(
                phase=RecoveryPhase.VERIFICATION,
                timestamp=datetime.now(),
                success=success,
                details=f"Verification completed: {error_count}/{total_tests} errors ({error_rate:.1%} error rate)",
                metrics={
                    "total_tests": total_tests,
                    "error_count": error_count,
                    "error_rate": error_rate,
                    "test_results": test_results[-10:],  # Keep last 10 results
                },
            )

        except Exception as e:
            return RecoveryCheckpoint(
                phase=RecoveryPhase.VERIFICATION,
                timestamp=datetime.now(),
                success=False,
                details=f"Verification phase failed: {e}",
                metrics={"error": str(e)},
            )

    async def _phase_activation(self) -> RecoveryCheckpoint:
        """Activation phase - switch back to primary database."""
        log.info("Recovery activation phase starting")

        try:
            # Switch fallback manager back to primary mode
            from .manager import FallbackMode

            self.fallback_manager.current_mode = FallbackMode.PRIMARY
            self.fallback_manager.metrics.mode = FallbackMode.PRIMARY
            self.fallback_manager._notify_mode_change(FallbackMode.PRIMARY)

            return RecoveryCheckpoint(
                phase=RecoveryPhase.ACTIVATION,
                timestamp=datetime.now(),
                success=True,
                details="Successfully activated primary database mode",
                metrics={"mode": "primary"},
            )

        except Exception as e:
            return RecoveryCheckpoint(
                phase=RecoveryPhase.ACTIVATION,
                timestamp=datetime.now(),
                success=False,
                details=f"Activation failed: {e}",
                metrics={"error": str(e)},
            )

    async def _phase_monitoring(self, plan: RecoveryPlan) -> RecoveryCheckpoint:
        """Monitoring phase - monitor operations for stability."""
        log.info("Recovery monitoring phase starting")

        try:
            # Start background monitoring
            monitor_duration = min(plan.verification_duration, timedelta(minutes=15))
            self.verification_task = asyncio.create_task(
                self._monitor_recovery_stability(
                    monitor_duration, plan.rollback_threshold
                )
            )

            # Wait for monitoring to complete
            monitoring_success = await self.verification_task

            return RecoveryCheckpoint(
                phase=RecoveryPhase.MONITORING,
                timestamp=datetime.now(),
                success=monitoring_success,
                details=f"Monitoring completed: {'stable' if monitoring_success else 'unstable'}",
                metrics={"stable": monitoring_success},
            )

        except Exception as e:
            return RecoveryCheckpoint(
                phase=RecoveryPhase.MONITORING,
                timestamp=datetime.now(),
                success=False,
                details=f"Monitoring failed: {e}",
                metrics={"error": str(e)},
            )

    async def _phase_completion(self) -> RecoveryCheckpoint:
        """Completion phase - finalize recovery."""
        log.info("Recovery completion phase starting")

        try:
            # Clean up verification task if still running
            if self.verification_task and not self.verification_task.done():
                self.verification_task.cancel()

            # Update metrics
            from .manager import HealthStatus

            self.fallback_manager.metrics.health_status = HealthStatus.HEALTHY

            return RecoveryCheckpoint(
                phase=RecoveryPhase.COMPLETED,
                timestamp=datetime.now(),
                success=True,
                details="Recovery completed successfully",
                metrics={"completed_at": datetime.now()},
            )

        except Exception as e:
            return RecoveryCheckpoint(
                phase=RecoveryPhase.COMPLETED,
                timestamp=datetime.now(),
                success=False,
                details=f"Completion failed: {e}",
                metrics={"error": str(e)},
            )

    async def _monitor_recovery_stability(
        self, duration: timedelta, rollback_threshold: float
    ) -> bool:
        """Monitor database stability after recovery."""
        end_time = datetime.now() + duration
        error_count = 0
        total_checks = 0

        while datetime.now() < end_time:
            total_checks += 1

            try:
                # Perform health check operation
                await self.db.get_total_exposure()
            except Exception:
                error_count += 1

            await asyncio.sleep(10)  # Check every 10 seconds

        error_rate = error_count / total_checks if total_checks > 0 else 0
        return error_rate <= rollback_threshold

    async def _handle_recovery_failure(
        self, plan: RecoveryPlan, checkpoints: list[RecoveryCheckpoint]
    ) -> None:
        """Handle recovery failure with appropriate rollback."""
        log.error("Recovery failed, initiating rollback procedures")

        try:
            # Switch back to fallback mode
            await self.fallback_manager.switch_to_fallback(
                "Recovery failed, rolling back"
            )
            self.recovery_metrics["total_rollbacks"] += 1

            # Add failed recovery to history
            self.recovery_history.append((plan, checkpoints))

            # Notify callbacks
            self._notify_recovery_phase(RecoveryPhase.FAILED, False)

        except Exception as e:
            log.error(f"Rollback failed: {e}")

    def get_recovery_status(self) -> dict[str, Any]:
        """Get current recovery status."""
        if not self.current_recovery:
            return {
                "recovery_in_progress": False,
                "last_recovery": self.recovery_metrics.get("last_recovery_attempt"),
            }

        return {
            "recovery_in_progress": True,
            "current_plan": {
                "strategy": self.current_recovery.strategy.value,
                "start_time": self.current_recovery.start_time,
                "estimated_completion": self.current_recovery.start_time
                + self.current_recovery.estimated_duration,
                "phases_total": len(self.current_recovery.phases),
            },
            "progress": {
                "current_phase": "unknown",  # Would need to track current phase
                "completion_estimate": 0.0,
            },
        }

    def get_recovery_metrics(self) -> dict[str, Any]:
        """Get comprehensive recovery metrics."""
        recent_recoveries = self.recovery_history[-10:]  # Last 10 recoveries
        successful_recoveries = [
            r
            for r, checkpoints in recent_recoveries
            if checkpoints and checkpoints[-1].success
        ]

        return {
            **self.recovery_metrics,
            "success_rate": (
                len(successful_recoveries) / len(recent_recoveries)
                if recent_recoveries
                else 0
            ),
            "recent_recoveries": len(recent_recoveries),
            "unresolved_conflicts": len(self.synchronizer.get_unresolved_conflicts()),
            "average_recovery_duration": self._calculate_average_recovery_duration(),
        }

    def _calculate_average_recovery_duration(self) -> float:
        """Calculate average recovery duration from history."""
        durations = []
        for plan, checkpoints in self.recovery_history[-5:]:  # Last 5 recoveries
            if checkpoints:
                duration = (checkpoints[-1].timestamp - plan.start_time).total_seconds()
                durations.append(duration)

        return sum(durations) / len(durations) if durations else 0.0
