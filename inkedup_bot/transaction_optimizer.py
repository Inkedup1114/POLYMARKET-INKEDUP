#!/usr/bin/env python3
"""
Advanced Transaction Optimizer for Database Batch Operations

This module provides intelligent transaction management, deadlock prevention,
and transaction batching optimization for high-volume database operations.
"""

import asyncio
import logging
import threading
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TransactionType(Enum):
    """Types of database transactions."""

    READ_ONLY = "read_only"
    WRITE_ONLY = "write_only"
    READ_WRITE = "read_write"
    BATCH_INSERT = "batch_insert"
    BATCH_UPDATE = "batch_update"
    MIXED_BATCH = "mixed_batch"


class TransactionPriority(Enum):
    """Transaction priority levels."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class IsolationLevel(Enum):
    """Transaction isolation levels."""

    READ_UNCOMMITTED = "READ UNCOMMITTED"
    READ_COMMITTED = "READ COMMITTED"
    REPEATABLE_READ = "REPEATABLE READ"
    SERIALIZABLE = "SERIALIZABLE"


@dataclass
class TransactionOperation:
    """Individual operation within a transaction."""

    operation_id: str
    operation_type: str  # 'insert', 'update', 'delete', 'select'
    table_name: str
    sql_query: str
    parameters: tuple | None = None
    expected_rows: int = 1
    timeout_ms: int = 30000
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class TransactionPlan:
    """Optimized execution plan for a transaction."""

    transaction_id: str
    transaction_type: TransactionType
    priority: TransactionPriority
    isolation_level: IsolationLevel
    operations: list[TransactionOperation]
    estimated_duration_ms: float
    tables_involved: set[str]
    can_batch: bool = True
    requires_immediate_commit: bool = False
    deadlock_risk_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class TransactionResult:
    """Result of transaction execution."""

    transaction_id: str
    success: bool
    operations_completed: int
    total_operations: int
    execution_time_ms: float
    rows_affected: int
    error_message: str | None = None
    retry_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TransactionMetrics:
    """Performance metrics for transaction processing."""

    total_transactions: int = 0
    successful_transactions: int = 0
    failed_transactions: int = 0
    retried_transactions: int = 0
    deadlocks_detected: int = 0
    average_transaction_time_ms: float = 0.0
    longest_transaction_time_ms: float = 0.0
    transactions_by_type: dict[TransactionType, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    batched_transactions: int = 0
    batch_efficiency_ratio: float = 0.0


class DeadlockDetector:
    """Deadlock detection and prevention system."""

    def __init__(self):
        self._lock_graph: dict[str, set[str]] = defaultdict(set)
        self._transaction_locks: dict[str, set[str]] = defaultdict(set)
        self._table_lock_holders: dict[str, set[str]] = defaultdict(set)
        self._lock_requests: dict[str, datetime] = {}
        self._lock = threading.RLock()

    def request_locks(self, transaction_id: str, tables: set[str]) -> bool:
        """Request locks on tables for a transaction."""
        with self._lock:
            # Check for potential deadlocks
            if self._would_cause_deadlock(transaction_id, tables):
                logger.warning(
                    f"Potential deadlock detected for transaction {transaction_id}"
                )
                return False

            # Grant locks
            for table in tables:
                self._table_lock_holders[table].add(transaction_id)
                self._transaction_locks[transaction_id].add(table)
                self._lock_requests[f"{transaction_id}_{table}"] = datetime.now()

            return True

    def release_locks(self, transaction_id: str):
        """Release all locks held by a transaction."""
        with self._lock:
            tables_to_release = self._transaction_locks.get(
                transaction_id, set()
            ).copy()

            for table in tables_to_release:
                self._table_lock_holders[table].discard(transaction_id)
                # Clean up empty sets
                if not self._table_lock_holders[table]:
                    del self._table_lock_holders[table]

                # Remove lock request tracking
                lock_key = f"{transaction_id}_{table}"
                self._lock_requests.pop(lock_key, None)

            # Clean up transaction lock tracking
            if transaction_id in self._transaction_locks:
                del self._transaction_locks[transaction_id]

    def _would_cause_deadlock(
        self, transaction_id: str, requested_tables: set[str]
    ) -> bool:
        """Check if granting locks would cause a deadlock."""
        # Build wait-for graph
        wait_for = defaultdict(set)

        for table in requested_tables:
            current_holders = self._table_lock_holders.get(table, set())
            if current_holders:
                for holder in current_holders:
                    if holder != transaction_id:
                        wait_for[transaction_id].add(holder)

        # Check for cycles using DFS
        visited = set()
        rec_stack = set()

        def has_cycle(node):
            if node in rec_stack:
                return True
            if node in visited:
                return False

            visited.add(node)
            rec_stack.add(node)

            for neighbor in wait_for.get(node, set()):
                if has_cycle(neighbor):
                    return True

            rec_stack.remove(node)
            return False

        return has_cycle(transaction_id)

    def get_lock_statistics(self) -> dict[str, Any]:
        """Get lock statistics and potential issues."""
        with self._lock:
            now = datetime.now()
            long_held_locks = []

            for lock_key, request_time in self._lock_requests.items():
                duration = (now - request_time).total_seconds()
                if duration > 10:  # Locks held for more than 10 seconds
                    long_held_locks.append(
                        {"lock": lock_key, "duration_seconds": duration}
                    )

            return {
                "active_transactions": len(self._transaction_locks),
                "locked_tables": len(self._table_lock_holders),
                "total_locks": sum(
                    len(locks) for locks in self._transaction_locks.values()
                ),
                "long_held_locks": long_held_locks,
            }


class TransactionOptimizer:
    """
    Advanced transaction optimizer with intelligent batching, deadlock prevention,
    and performance optimization capabilities.
    """

    def __init__(self, max_batch_size: int = 100, batch_timeout_ms: int = 1000):
        self.max_batch_size = max_batch_size
        self.batch_timeout_ms = batch_timeout_ms

        # Core components
        self.deadlock_detector = DeadlockDetector()
        self.metrics = TransactionMetrics()
        self._metrics_lock = threading.Lock()

        # Transaction batching
        self._pending_transactions: dict[str, list[TransactionPlan]] = defaultdict(list)
        self._batch_timers: dict[str, datetime] = {}
        self._batch_lock = threading.RLock()

        # Active transaction tracking
        self._active_transactions: dict[str, TransactionPlan] = {}
        self._transaction_start_times: dict[str, datetime] = {}

        # Performance optimization
        self._table_contention_scores: dict[str, float] = defaultdict(float)
        self._optimal_batch_sizes: dict[str, int] = defaultdict(lambda: 50)

        logger.info("TransactionOptimizer initialized")

    def create_transaction_plan(
        self,
        operations: list[TransactionOperation],
        priority: TransactionPriority = TransactionPriority.NORMAL,
        isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED,
    ) -> TransactionPlan:
        """Create an optimized transaction plan."""
        transaction_id = str(uuid.uuid4())

        # Analyze operations
        transaction_type = self._analyze_transaction_type(operations)
        tables_involved = {op.table_name for op in operations}
        estimated_duration = self._estimate_transaction_duration(operations)
        deadlock_risk = self._calculate_deadlock_risk(tables_involved)

        # Determine batching strategy
        can_batch = self._can_batch_transaction(operations, transaction_type)
        requires_immediate = priority == TransactionPriority.CRITICAL

        plan = TransactionPlan(
            transaction_id=transaction_id,
            transaction_type=transaction_type,
            priority=priority,
            isolation_level=isolation_level,
            operations=operations,
            estimated_duration_ms=estimated_duration,
            tables_involved=tables_involved,
            can_batch=can_batch,
            requires_immediate_commit=requires_immediate,
            deadlock_risk_score=deadlock_risk,
        )

        return plan

    async def execute_transaction(
        self, db_connection, plan: TransactionPlan
    ) -> TransactionResult:
        """Execute a transaction with optimization and monitoring."""
        start_time = time.time()

        # Request locks to prevent deadlocks
        if not self.deadlock_detector.request_locks(
            plan.transaction_id, plan.tables_involved
        ):
            return TransactionResult(
                transaction_id=plan.transaction_id,
                success=False,
                operations_completed=0,
                total_operations=len(plan.operations),
                execution_time_ms=0,
                rows_affected=0,
                error_message="Deadlock prevention: transaction rejected",
            )

        try:
            # Track active transaction
            self._active_transactions[plan.transaction_id] = plan
            self._transaction_start_times[plan.transaction_id] = datetime.now()

            # Execute transaction with appropriate isolation level
            async with self._transaction_context(db_connection, plan.isolation_level):
                operations_completed = 0
                total_rows_affected = 0

                for operation in plan.operations:
                    try:
                        cursor = await db_connection.execute(
                            operation.sql_query, operation.parameters or ()
                        )

                        if operation.operation_type.lower() in [
                            "insert",
                            "update",
                            "delete",
                        ]:
                            rows_affected = cursor.rowcount
                            total_rows_affected += rows_affected
                        else:
                            # For SELECT operations, we don't count rows affected
                            pass

                        operations_completed += 1

                    except Exception as e:
                        logger.error(f"Operation {operation.operation_id} failed: {e}")
                        # Decide whether to continue or abort based on operation criticality
                        if operation.operation_type.lower() in [
                            "insert",
                            "update",
                            "delete",
                        ]:
                            raise  # Abort transaction for modification operations
                        # Continue for read operations

                execution_time = (time.time() - start_time) * 1000

                result = TransactionResult(
                    transaction_id=plan.transaction_id,
                    success=True,
                    operations_completed=operations_completed,
                    total_operations=len(plan.operations),
                    execution_time_ms=execution_time,
                    rows_affected=total_rows_affected,
                )

                # Update metrics
                await self._update_transaction_metrics(plan, result, success=True)

                return result

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000

            result = TransactionResult(
                transaction_id=plan.transaction_id,
                success=False,
                operations_completed=0,
                total_operations=len(plan.operations),
                execution_time_ms=execution_time,
                rows_affected=0,
                error_message=str(e),
            )

            # Update metrics for failure
            await self._update_transaction_metrics(plan, result, success=False)

            logger.error(f"Transaction {plan.transaction_id} failed: {e}")
            return result

        finally:
            # Clean up tracking
            self._active_transactions.pop(plan.transaction_id, None)
            self._transaction_start_times.pop(plan.transaction_id, None)

            # Release locks
            self.deadlock_detector.release_locks(plan.transaction_id)

    async def execute_batch_transactions(
        self, db_connection, plans: list[TransactionPlan]
    ) -> list[TransactionResult]:
        """Execute multiple transactions with intelligent batching."""
        if not plans:
            return []

        # Group transactions for optimal batching
        batched_groups = self._group_transactions_for_batching(plans)
        results = []

        for group_type, group_plans in batched_groups.items():
            if group_type == "batchable" and len(group_plans) > 1:
                # Execute as a single batch transaction
                batch_result = await self._execute_batched_transactions(
                    db_connection, group_plans
                )
                results.extend(batch_result)
            else:
                # Execute individually
                for plan in group_plans:
                    result = await self.execute_transaction(db_connection, plan)
                    results.append(result)

        return results

    async def submit_for_batching(self, plan: TransactionPlan) -> bool:
        """Submit a transaction for potential batching."""
        if not plan.can_batch or plan.requires_immediate_commit:
            return False

        batch_key = self._get_batch_key(plan)

        with self._batch_lock:
            self._pending_transactions[batch_key].append(plan)

            # Set timer for first transaction in batch
            if batch_key not in self._batch_timers:
                self._batch_timers[batch_key] = datetime.now()

            # Check if batch is ready for execution
            batch = self._pending_transactions[batch_key]

            # Execute batch if size threshold reached or timeout exceeded
            if len(batch) >= self._optimal_batch_sizes[
                batch_key
            ] or self._is_batch_timeout_exceeded(batch_key):
                # Remove from pending
                batch_to_execute = self._pending_transactions.pop(batch_key)
                self._batch_timers.pop(batch_key, None)

                # Execute batch asynchronously
                asyncio.create_task(
                    self._execute_pending_batch(batch_key, batch_to_execute)
                )

        return True

    async def _execute_pending_batch(
        self, batch_key: str, plans: list[TransactionPlan]
    ):
        """Execute a batch of pending transactions."""
        # This would require access to a database connection
        # In practice, this would be called by a background worker with a connection pool
        logger.info(f"Executing batch {batch_key} with {len(plans)} transactions")

        with self._metrics_lock:
            self.metrics.batched_transactions += len(plans)

    def _group_transactions_for_batching(
        self, plans: list[TransactionPlan]
    ) -> dict[str, list[TransactionPlan]]:
        """Group transactions for optimal batching."""
        groups = {"batchable": [], "immediate": [], "high_contention": []}

        for plan in plans:
            if (
                plan.requires_immediate_commit
                or plan.priority == TransactionPriority.CRITICAL
            ):
                groups["immediate"].append(plan)
            elif plan.deadlock_risk_score > 0.7:
                groups["high_contention"].append(plan)
            elif plan.can_batch:
                groups["batchable"].append(plan)
            else:
                groups["immediate"].append(plan)

        return {k: v for k, v in groups.items() if v}

    async def _execute_batched_transactions(
        self, db_connection, plans: list[TransactionPlan]
    ) -> list[TransactionResult]:
        """Execute multiple transactions as a single batch."""
        batch_id = f"batch_{int(time.time() * 1000)}"
        logger.info(
            f"Executing batched transaction {batch_id} with {len(plans)} sub-transactions"
        )

        start_time = time.time()
        results = []

        # Collect all tables involved for lock management
        all_tables = set()
        for plan in plans:
            all_tables.update(plan.tables_involved)

        # Request locks for the entire batch
        if not self.deadlock_detector.request_locks(batch_id, all_tables):
            # Return failure results for all plans
            for plan in plans:
                results.append(
                    TransactionResult(
                        transaction_id=plan.transaction_id,
                        success=False,
                        operations_completed=0,
                        total_operations=len(plan.operations),
                        execution_time_ms=0,
                        rows_affected=0,
                        error_message="Batch deadlock prevention: rejected",
                    )
                )
            return results

        try:
            async with self._transaction_context(
                db_connection, IsolationLevel.READ_COMMITTED
            ):
                for plan in plans:
                    plan_start_time = time.time()
                    operations_completed = 0
                    total_rows_affected = 0

                    try:
                        for operation in plan.operations:
                            cursor = await db_connection.execute(
                                operation.sql_query, operation.parameters or ()
                            )

                            if operation.operation_type.lower() in [
                                "insert",
                                "update",
                                "delete",
                            ]:
                                total_rows_affected += cursor.rowcount

                            operations_completed += 1

                        execution_time = (time.time() - plan_start_time) * 1000

                        result = TransactionResult(
                            transaction_id=plan.transaction_id,
                            success=True,
                            operations_completed=operations_completed,
                            total_operations=len(plan.operations),
                            execution_time_ms=execution_time,
                            rows_affected=total_rows_affected,
                        )

                        results.append(result)

                    except Exception as e:
                        execution_time = (time.time() - plan_start_time) * 1000

                        result = TransactionResult(
                            transaction_id=plan.transaction_id,
                            success=False,
                            operations_completed=operations_completed,
                            total_operations=len(plan.operations),
                            execution_time_ms=execution_time,
                            rows_affected=0,
                            error_message=str(e),
                        )

                        results.append(result)
                        logger.error(
                            f"Transaction {plan.transaction_id} failed in batch: {e}"
                        )

        except Exception as e:
            logger.error(f"Batch transaction {batch_id} failed: {e}")
            # Return failure results for remaining plans
            for plan in plans[len(results) :]:
                results.append(
                    TransactionResult(
                        transaction_id=plan.transaction_id,
                        success=False,
                        operations_completed=0,
                        total_operations=len(plan.operations),
                        execution_time_ms=0,
                        rows_affected=0,
                        error_message=f"Batch failure: {str(e)}",
                    )
                )

        finally:
            self.deadlock_detector.release_locks(batch_id)

        total_execution_time = (time.time() - start_time) * 1000
        logger.info(f"Batch {batch_id} completed in {total_execution_time:.2f}ms")

        return results

    @asynccontextmanager
    async def _transaction_context(
        self, db_connection, isolation_level: IsolationLevel
    ):
        """Context manager for transaction execution with proper isolation."""
        try:
            # Set isolation level if supported
            if isolation_level != IsolationLevel.READ_COMMITTED:
                await db_connection.execute(
                    f"PRAGMA read_uncommitted = {isolation_level == IsolationLevel.READ_UNCOMMITTED}"
                )

            await db_connection.execute("BEGIN TRANSACTION")
            yield
            await db_connection.execute("COMMIT")

        except Exception as e:
            await db_connection.execute("ROLLBACK")
            raise e

    def _analyze_transaction_type(
        self, operations: list[TransactionOperation]
    ) -> TransactionType:
        """Analyze operations to determine transaction type."""
        read_ops = sum(1 for op in operations if op.operation_type.lower() == "select")
        write_ops = sum(
            1
            for op in operations
            if op.operation_type.lower() in ["insert", "update", "delete"]
        )
        insert_ops = sum(
            1 for op in operations if op.operation_type.lower() == "insert"
        )
        update_ops = sum(
            1 for op in operations if op.operation_type.lower() == "update"
        )
        delete_ops = sum(
            1 for op in operations if op.operation_type.lower() == "delete"
        )

        if write_ops == 0:
            return TransactionType.READ_ONLY
        elif read_ops == 0:
            if insert_ops > 0 and update_ops == 0 and delete_ops == 0:
                return TransactionType.BATCH_INSERT
            elif update_ops > 0 and insert_ops == 0 and delete_ops == 0:
                return TransactionType.BATCH_UPDATE
            else:
                return TransactionType.WRITE_ONLY
        else:
            # Has both read and write operations
            if insert_ops > 0 or update_ops > 0:
                return TransactionType.MIXED_BATCH
            else:
                return TransactionType.READ_WRITE

    def _estimate_transaction_duration(
        self, operations: list[TransactionOperation]
    ) -> float:
        """Estimate transaction execution duration in milliseconds."""
        base_time_per_op = 5.0  # Base 5ms per operation

        total_time = 0.0
        for operation in operations:
            op_time = base_time_per_op

            # Adjust based on operation type
            if operation.operation_type.lower() == "insert":
                op_time *= 1.2
            elif operation.operation_type.lower() == "update":
                op_time *= 1.5
            elif operation.operation_type.lower() == "delete":
                op_time *= 1.3
            elif operation.operation_type.lower() == "select":
                op_time *= 0.8

            # Adjust based on expected rows
            if operation.expected_rows > 100:
                op_time *= 1.5
            elif operation.expected_rows > 1000:
                op_time *= 2.0

            total_time += op_time

        return total_time

    def _calculate_deadlock_risk(self, tables_involved: set[str]) -> float:
        """Calculate deadlock risk score for a transaction."""
        risk_score = 0.0

        # Base risk increases with number of tables
        risk_score += len(tables_involved) * 0.1

        # Higher risk for tables with known contention
        for table in tables_involved:
            contention = self._table_contention_scores.get(table, 0.0)
            risk_score += contention * 0.3

        # Cap at 1.0
        return min(risk_score, 1.0)

    def _can_batch_transaction(
        self, operations: list[TransactionOperation], tx_type: TransactionType
    ) -> bool:
        """Determine if a transaction can be batched."""
        # Read-only transactions are always batchable
        if tx_type == TransactionType.READ_ONLY:
            return True

        # Batch inserts and updates are good for batching
        if tx_type in [TransactionType.BATCH_INSERT, TransactionType.BATCH_UPDATE]:
            return True

        # Mixed transactions with low complexity can be batched
        if tx_type == TransactionType.MIXED_BATCH and len(operations) <= 10:
            return True

        # Other types require individual processing
        return False

    def _get_batch_key(self, plan: TransactionPlan) -> str:
        """Generate a key for batching similar transactions."""
        # Group by transaction type and tables involved
        tables_hash = hash(frozenset(plan.tables_involved))
        return f"{plan.transaction_type.value}_{tables_hash}_{plan.priority.value}"

    def _is_batch_timeout_exceeded(self, batch_key: str) -> bool:
        """Check if batch timeout has been exceeded."""
        if batch_key not in self._batch_timers:
            return False

        elapsed_ms = (
            datetime.now() - self._batch_timers[batch_key]
        ).total_seconds() * 1000
        return elapsed_ms >= self.batch_timeout_ms

    async def _update_transaction_metrics(
        self, plan: TransactionPlan, result: TransactionResult, success: bool
    ):
        """Update transaction performance metrics."""
        with self._metrics_lock:
            self.metrics.total_transactions += 1
            self.metrics.transactions_by_type[plan.transaction_type] += 1

            if success:
                self.metrics.successful_transactions += 1
            else:
                self.metrics.failed_transactions += 1

            if result.retry_count > 0:
                self.metrics.retried_transactions += 1

            # Update timing metrics
            if result.execution_time_ms > self.metrics.longest_transaction_time_ms:
                self.metrics.longest_transaction_time_ms = result.execution_time_ms

            # Update average (exponential moving average)
            if self.metrics.total_transactions == 1:
                self.metrics.average_transaction_time_ms = result.execution_time_ms
            else:
                alpha = 0.1
                self.metrics.average_transaction_time_ms = (
                    alpha * result.execution_time_ms
                    + (1 - alpha) * self.metrics.average_transaction_time_ms
                )

            # Update table contention scores
            execution_factor = min(result.execution_time_ms / 1000, 2.0)  # Cap at 2x
            for table in plan.tables_involved:
                current_score = self._table_contention_scores[table]
                self._table_contention_scores[table] = (
                    0.9 * current_score + 0.1 * execution_factor
                )

    def get_metrics(self) -> TransactionMetrics:
        """Get current transaction optimization metrics."""
        with self._metrics_lock:
            # Calculate batch efficiency
            if self.metrics.total_transactions > 0:
                batch_ratio = (
                    self.metrics.batched_transactions / self.metrics.total_transactions
                )
                self.metrics.batch_efficiency_ratio = batch_ratio

            return TransactionMetrics(
                total_transactions=self.metrics.total_transactions,
                successful_transactions=self.metrics.successful_transactions,
                failed_transactions=self.metrics.failed_transactions,
                retried_transactions=self.metrics.retried_transactions,
                deadlocks_detected=self.metrics.deadlocks_detected,
                average_transaction_time_ms=self.metrics.average_transaction_time_ms,
                longest_transaction_time_ms=self.metrics.longest_transaction_time_ms,
                transactions_by_type=dict(self.metrics.transactions_by_type),
                batched_transactions=self.metrics.batched_transactions,
                batch_efficiency_ratio=self.metrics.batch_efficiency_ratio,
            )

    def get_active_transactions(self) -> list[dict[str, Any]]:
        """Get information about currently active transactions."""
        active = []
        now = datetime.now()

        for tx_id, plan in self._active_transactions.items():
            start_time = self._transaction_start_times.get(tx_id)
            duration = (now - start_time).total_seconds() if start_time else 0

            active.append(
                {
                    "transaction_id": tx_id,
                    "type": plan.transaction_type.value,
                    "priority": plan.priority.value,
                    "tables": list(plan.tables_involved),
                    "operations_count": len(plan.operations),
                    "duration_seconds": duration,
                    "deadlock_risk": plan.deadlock_risk_score,
                }
            )

        return active

    def get_recommendations(self) -> dict[str, Any]:
        """Get optimization recommendations."""
        lock_stats = self.deadlock_detector.get_lock_statistics()

        # Identify high contention tables
        high_contention = [
            {"table": table, "score": score}
            for table, score in self._table_contention_scores.items()
            if score > 0.5
        ]
        high_contention.sort(key=lambda x: x["score"], reverse=True)

        # Optimal batch sizes
        batch_recommendations = dict(self._optimal_batch_sizes)

        return {
            "high_contention_tables": high_contention[:10],
            "optimal_batch_sizes": batch_recommendations,
            "lock_statistics": lock_stats,
            "pending_batches": len(self._pending_transactions),
            "active_transactions": len(self._active_transactions),
        }

    async def optimize_batch_sizes(self):
        """Dynamically optimize batch sizes based on performance."""
        # This would analyze recent performance and adjust optimal batch sizes
        for batch_key in self._optimal_batch_sizes:
            current_size = self._optimal_batch_sizes[batch_key]

            # Simple adjustment based on contention (simplified logic)
            _ = batch_key.split("_")[1]  # Simplified extraction
            avg_contention = (
                sum(self._table_contention_scores.values())
                / len(self._table_contention_scores)
                if self._table_contention_scores
                else 0
            )

            if avg_contention > 0.7:
                self._optimal_batch_sizes[batch_key] = max(10, current_size - 10)
            elif avg_contention < 0.3:
                self._optimal_batch_sizes[batch_key] = min(
                    self.max_batch_size, current_size + 10
                )

        logger.debug("Batch sizes optimized based on performance metrics")
