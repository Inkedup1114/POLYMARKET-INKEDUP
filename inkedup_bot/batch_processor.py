#!/usr/bin/env python3
"""
Advanced Batch Processing System for InkedUp Bot Database Operations

This module provides comprehensive batch processing capabilities for database operations
including intelligent batching, transaction optimization, and performance monitoring.
"""

import asyncio
import logging
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BatchType(Enum):
    """Types of database batch operations."""

    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    SELECT = "select"
    UPSERT = "upsert"


class BatchPriority(Enum):
    """Priority levels for batch operations."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class BatchStrategy(Enum):
    """Batch processing strategies."""

    SIZE_BASED = "size_based"  # Batch when size threshold reached
    TIME_BASED = "time_based"  # Batch after time interval
    HYBRID = "hybrid"  # Combination of size and time
    IMMEDIATE = "immediate"  # Process immediately (no batching)
    ADAPTIVE = "adaptive"  # Dynamically adjust based on load


@dataclass
class BatchConfig:
    """Configuration for batch processing behavior."""

    max_batch_size: int = 1000  # Maximum items per batch
    max_wait_time_ms: int = 500  # Maximum wait time before processing
    min_batch_size: int = 10  # Minimum size to trigger batching
    max_concurrent_batches: int = 5  # Maximum concurrent batch operations
    enable_compression: bool = True  # Enable data compression for large batches
    enable_metrics: bool = True  # Enable performance metrics collection
    transaction_timeout_ms: int = 30000  # Transaction timeout in milliseconds
    retry_attempts: int = 3  # Number of retry attempts for failed batches
    strategy: BatchStrategy = BatchStrategy.HYBRID


@dataclass
class BatchOperation:
    """Individual operation within a batch."""

    operation_id: str
    batch_type: BatchType
    table_name: str
    data: dict[str, Any]
    sql_query: str | None = None
    parameters: tuple | None = None
    priority: BatchPriority = BatchPriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    retries: int = 0


@dataclass
class BatchMetrics:
    """Performance metrics for batch operations."""

    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    total_batches_processed: int = 0
    average_batch_size: float = 0.0
    average_processing_time_ms: float = 0.0
    throughput_ops_per_second: float = 0.0
    error_rate: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)


class BatchQueue:
    """Thread-safe queue for batch operations with priority handling."""

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._queues: dict[BatchPriority, deque] = {
            priority: deque() for priority in BatchPriority
        }
        self._lock = threading.RLock()
        self._not_empty = threading.Condition(self._lock)
        self._not_full = threading.Condition(self._lock)
        self._total_size = 0

    def put(self, operation: BatchOperation) -> bool:
        """Add operation to queue with priority handling."""
        with self._not_full:
            while self._total_size >= self.max_size:
                self._not_full.wait(timeout=1.0)
                if self._total_size >= self.max_size:
                    logger.warning(
                        "Batch queue is full, dropping low priority operations"
                    )
                    self._drop_low_priority_operations()

            self._queues[operation.priority].append(operation)
            self._total_size += 1
            self._not_empty.notify()
            return True

    def get(self, timeout: float | None = None) -> BatchOperation | None:
        """Get highest priority operation from queue."""
        with self._not_empty:
            deadline = time.time() + timeout if timeout else None

            while self._total_size == 0:
                if deadline and time.time() >= deadline:
                    return None
                remaining = deadline - time.time() if deadline else None
                self._not_empty.wait(timeout=remaining)

            # Get from highest priority queue first
            for priority in sorted(BatchPriority, key=lambda x: x.value, reverse=True):
                if self._queues[priority]:
                    operation = self._queues[priority].popleft()
                    self._total_size -= 1
                    self._not_full.notify()
                    return operation

            return None

    def get_batch(
        self, max_size: int, timeout: float | None = None
    ) -> list[BatchOperation]:
        """Get a batch of operations up to max_size."""
        operations = []
        deadline = time.time() + timeout if timeout else None

        while len(operations) < max_size:
            remaining_timeout = deadline - time.time() if deadline else 0.1
            if remaining_timeout <= 0:
                break

            operation = self.get(timeout=remaining_timeout)
            if operation is None:
                break
            operations.append(operation)

        return operations

    def size(self) -> int:
        """Get total number of operations in queue."""
        with self._lock:
            return self._total_size

    def _drop_low_priority_operations(self):
        """Drop low priority operations when queue is full."""
        dropped = 0
        for priority in [BatchPriority.LOW, BatchPriority.NORMAL]:
            while self._queues[priority] and dropped < 100:  # Drop max 100 operations
                self._queues[priority].popleft()
                self._total_size -= 1
                dropped += 1

        if dropped > 0:
            logger.warning(
                f"Dropped {dropped} low priority operations due to queue overflow"
            )


class BatchProcessor:
    """
    Advanced batch processor for database operations with intelligent batching,
    transaction optimization, and performance monitoring.
    """

    def __init__(self, database_manager, config: BatchConfig = None):
        self.db = database_manager
        self.config = config or BatchConfig()

        # Core components
        self.queue = BatchQueue(max_size=self.config.max_batch_size * 10)
        self.metrics = BatchMetrics()
        self._metrics_lock = threading.Lock()

        # Processing control
        self._running = False
        self._processing_tasks: list[asyncio.Task] = []
        self._worker_pool = ThreadPoolExecutor(
            max_workers=self.config.max_concurrent_batches
        )

        # Adaptive batching state
        self._last_batch_time = datetime.now()
        self._adaptive_batch_size = self.config.min_batch_size
        self._performance_history: deque = deque(maxlen=100)

        # Table-specific batch accumulators
        self._table_batches: dict[str, dict[BatchType, list[BatchOperation]]] = (
            defaultdict(lambda: defaultdict(list))
        )
        self._batch_timers: dict[str, datetime] = {}
        self._batch_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)

        logger.info(f"BatchProcessor initialized with config: {self.config}")

    async def start(self):
        """Start the batch processing system."""
        if self._running:
            return

        self._running = True

        # Start processing tasks
        for i in range(self.config.max_concurrent_batches):
            task = asyncio.create_task(self._processing_worker(f"worker-{i}"))
            self._processing_tasks.append(task)

        # Start batch timer task
        timer_task = asyncio.create_task(self._batch_timer_worker())
        self._processing_tasks.append(timer_task)

        # Start metrics collection task
        if self.config.enable_metrics:
            metrics_task = asyncio.create_task(self._metrics_worker())
            self._processing_tasks.append(metrics_task)

        logger.info("Batch processing system started")

    async def stop(self):
        """Stop the batch processing system and process remaining operations."""
        if not self._running:
            return

        logger.info("Stopping batch processing system...")
        self._running = False

        # Process remaining operations
        await self._flush_all_batches()

        # Cancel and wait for tasks
        for task in self._processing_tasks:
            task.cancel()

        await asyncio.gather(*self._processing_tasks, return_exceptions=True)

        # Shutdown worker pool
        self._worker_pool.shutdown(wait=True)

        logger.info("Batch processing system stopped")

    async def submit_operation(self, operation: BatchOperation) -> bool:
        """Submit an operation for batch processing."""
        if not self._running:
            logger.warning("Batch processor is not running, operation rejected")
            return False

        # Handle immediate operations
        if self.config.strategy == BatchStrategy.IMMEDIATE:
            await self._process_single_operation(operation)
            return True

        # Add to queue for batch processing
        success = self.queue.put(operation)

        if success and self.config.enable_metrics:
            with self._metrics_lock:
                self.metrics.total_operations += 1

        return success

    async def submit_batch_insert(
        self,
        table_name: str,
        records: list[dict[str, Any]],
        priority: BatchPriority = BatchPriority.NORMAL,
    ) -> bool:
        """Submit multiple records for batch insertion."""
        operations = []
        for i, record in enumerate(records):
            operation = BatchOperation(
                operation_id=f"{table_name}_insert_{i}_{int(time.time() * 1000)}",
                batch_type=BatchType.INSERT,
                table_name=table_name,
                data=record,
                priority=priority,
            )
            operations.append(operation)

        # Submit all operations
        success_count = 0
        for op in operations:
            if await self.submit_operation(op):
                success_count += 1

        return success_count == len(operations)

    async def submit_batch_update(
        self,
        table_name: str,
        updates: list[tuple[dict[str, Any], dict[str, Any]]],
        priority: BatchPriority = BatchPriority.NORMAL,
    ) -> bool:
        """Submit multiple updates for batch processing."""
        operations = []
        for i, (conditions, update_data) in enumerate(updates):
            operation = BatchOperation(
                operation_id=f"{table_name}_update_{i}_{int(time.time() * 1000)}",
                batch_type=BatchType.UPDATE,
                table_name=table_name,
                data=update_data,
                priority=priority,
                metadata={"conditions": conditions},
            )
            operations.append(operation)

        # Submit all operations
        success_count = 0
        for op in operations:
            if await self.submit_operation(op):
                success_count += 1

        return success_count == len(operations)

    async def force_flush(self, table_name: str | None = None):
        """Force flush all pending batches for a table or all tables."""
        if table_name:
            await self._flush_table_batches(table_name)
        else:
            await self._flush_all_batches()

    async def get_metrics(self) -> BatchMetrics:
        """Get current batch processing metrics."""
        with self._metrics_lock:
            # Update calculated metrics
            if self.metrics.total_operations > 0:
                self.metrics.error_rate = (
                    self.metrics.failed_operations / self.metrics.total_operations
                )

            if self.metrics.total_batches_processed > 0:
                self.metrics.average_batch_size = (
                    self.metrics.total_operations / self.metrics.total_batches_processed
                )

            return BatchMetrics(
                total_operations=self.metrics.total_operations,
                successful_operations=self.metrics.successful_operations,
                failed_operations=self.metrics.failed_operations,
                total_batches_processed=self.metrics.total_batches_processed,
                average_batch_size=self.metrics.average_batch_size,
                average_processing_time_ms=self.metrics.average_processing_time_ms,
                throughput_ops_per_second=self.metrics.throughput_ops_per_second,
                error_rate=self.metrics.error_rate,
                last_updated=datetime.now(),
            )

    async def _processing_worker(self, worker_id: str):
        """Main processing worker that handles batch operations."""
        logger.info(f"Processing worker {worker_id} started")

        while self._running:
            try:
                # Get batch of operations
                operations = self.queue.get_batch(
                    max_size=self._get_optimal_batch_size(),
                    timeout=self.config.max_wait_time_ms / 1000.0,
                )

                if not operations:
                    await asyncio.sleep(0.1)
                    continue

                # Process batch
                await self._process_batch(operations, worker_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in processing worker {worker_id}: {e}")
                await asyncio.sleep(1.0)

        logger.info(f"Processing worker {worker_id} stopped")

    async def _process_batch(self, operations: list[BatchOperation], worker_id: str):
        """Process a batch of operations with transaction optimization."""
        if not operations:
            return

        start_time = time.time()
        batch_id = f"batch_{worker_id}_{int(start_time * 1000)}"

        logger.debug(f"Processing batch {batch_id} with {len(operations)} operations")

        # Group operations by table and type for optimization
        grouped_ops = self._group_operations_for_processing(operations)

        success_count = 0
        failure_count = 0

        try:
            # Process each group in a transaction
            async with self.db.connection() as conn:
                for (table_name, batch_type), ops in grouped_ops.items():
                    try:
                        async with conn.execute("BEGIN TRANSACTION"):
                            if batch_type == BatchType.INSERT:
                                success_count += await self._process_insert_batch(
                                    conn, table_name, ops
                                )
                            elif batch_type == BatchType.UPDATE:
                                success_count += await self._process_update_batch(
                                    conn, table_name, ops
                                )
                            elif batch_type == BatchType.DELETE:
                                success_count += await self._process_delete_batch(
                                    conn, table_name, ops
                                )
                            elif batch_type == BatchType.UPSERT:
                                success_count += await self._process_upsert_batch(
                                    conn, table_name, ops
                                )

                            await conn.execute("COMMIT")

                    except Exception as e:
                        logger.error(
                            f"Error processing {table_name} {batch_type.value} batch: {e}"
                        )
                        await conn.execute("ROLLBACK")
                        failure_count += len(ops)

                        # Retry failed operations individually if configured
                        if self.config.retry_attempts > 0:
                            await self._retry_failed_operations(ops)

        except Exception as e:
            logger.error(f"Critical error processing batch {batch_id}: {e}")
            failure_count = len(operations)

        # Update metrics
        processing_time = (time.time() - start_time) * 1000
        await self._update_metrics(
            len(operations), success_count, failure_count, processing_time
        )

        logger.debug(
            f"Batch {batch_id} completed: {success_count} success, {failure_count} failed, "
            f"{processing_time:.2f}ms"
        )

    def _group_operations_for_processing(
        self, operations: list[BatchOperation]
    ) -> dict[tuple[str, BatchType], list[BatchOperation]]:
        """Group operations by table and type for optimized processing."""
        grouped = defaultdict(list)

        for op in operations:
            key = (op.table_name, op.batch_type)
            grouped[key].append(op)

        return dict(grouped)

    async def _process_insert_batch(
        self, conn, table_name: str, operations: list[BatchOperation]
    ) -> int:
        """Process a batch of insert operations."""
        if not operations:
            return 0

        # Build bulk insert query
        if table_name == "orders":
            return await self._process_orders_insert_batch(conn, operations)
        elif table_name == "positions":
            return await self._process_positions_insert_batch(conn, operations)
        elif table_name == "trades":
            return await self._process_trades_insert_batch(conn, operations)
        else:
            # Generic insert processing
            return await self._process_generic_insert_batch(
                conn, table_name, operations
            )

    async def _process_orders_insert_batch(
        self, conn, operations: list[BatchOperation]
    ) -> int:
        """Optimized batch insert for orders table."""
        if not operations:
            return 0

        # Prepare batch insert
        values = []
        for op in operations:
            data = op.data
            values.append(
                (
                    data.get("id"),
                    data.get("token_id"),
                    data.get("market_slug"),
                    data.get("side"),
                    data.get("price"),
                    data.get("size"),
                    data.get("status", "OPEN"),
                    data.get("notional_value", 0.0),
                    data.get("outcome_type"),
                )
            )

        # Execute batch insert
        await conn.executemany(
            """
            INSERT OR REPLACE INTO orders (
                id, token_id, market_slug, side, price, size, status,
                notional_value, outcome_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )

        return len(operations)

    async def _process_positions_insert_batch(
        self, conn, operations: list[BatchOperation]
    ) -> int:
        """Optimized batch insert for positions table."""
        if not operations:
            return 0

        values = []
        for op in operations:
            data = op.data
            values.append(
                (
                    data.get("token_id"),
                    data.get("market_slug"),
                    data.get("size", 0.0),
                    data.get("notional_value", 0.0),
                    data.get("outcome_type"),
                    data.get("side"),
                )
            )

        await conn.executemany(
            """
            INSERT OR REPLACE INTO positions (
                token_id, market_slug, size, notional_value, outcome_type, side
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            values,
        )

        return len(operations)

    async def _process_trades_insert_batch(
        self, conn, operations: list[BatchOperation]
    ) -> int:
        """Optimized batch insert for trades table."""
        if not operations:
            return 0

        values = []
        for op in operations:
            data = op.data
            values.append(
                (
                    data.get("id"),
                    data.get("order_id"),
                    data.get("token_id"),
                    data.get("market_slug"),
                    data.get("side"),
                    data.get("price", 0.0),
                    data.get("size", 0.0),
                    data.get("fee", 0.0),
                    data.get("outcome_type"),
                )
            )

        await conn.executemany(
            """
            INSERT OR REPLACE INTO trades (
                id, order_id, token_id, market_slug, side, price, size, fee, outcome_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )

        return len(operations)

    async def _process_generic_insert_batch(
        self, conn, table_name: str, operations: list[BatchOperation]
    ) -> int:
        """Generic batch insert for any table."""
        if not operations:
            return 0

        # This would need to be dynamically built based on table schema
        # For now, we'll process operations individually
        success_count = 0
        for op in operations:
            try:
                await self._process_single_operation_with_conn(conn, op)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to process operation {op.operation_id}: {e}")

        return success_count

    async def _process_update_batch(
        self, conn, table_name: str, operations: list[BatchOperation]
    ) -> int:
        """Process a batch of update operations."""
        success_count = 0
        for op in operations:
            try:
                await self._process_single_update_operation(conn, op)
                success_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to process update operation {op.operation_id}: {e}"
                )

        return success_count

    async def _process_delete_batch(
        self, conn, table_name: str, operations: list[BatchOperation]
    ) -> int:
        """Process a batch of delete operations."""
        success_count = 0
        for op in operations:
            try:
                await self._process_single_delete_operation(conn, op)
                success_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to process delete operation {op.operation_id}: {e}"
                )

        return success_count

    async def _process_upsert_batch(
        self, conn, table_name: str, operations: list[BatchOperation]
    ) -> int:
        """Process a batch of upsert operations."""
        success_count = 0
        for op in operations:
            try:
                await self._process_single_upsert_operation(conn, op)
                success_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to process upsert operation {op.operation_id}: {e}"
                )

        return success_count

    async def _process_single_operation(self, operation: BatchOperation):
        """Process a single operation immediately."""
        async with self.db.connection() as conn:
            await self._process_single_operation_with_conn(conn, operation)

    async def _process_single_operation_with_conn(
        self, conn, operation: BatchOperation
    ):
        """Process a single operation with existing connection."""
        if operation.batch_type == BatchType.INSERT:
            if operation.sql_query and operation.parameters:
                await conn.execute(operation.sql_query, operation.parameters)
            else:
                # Use existing database methods
                if operation.table_name == "orders":
                    await self.db.insert_order(operation.data)
                elif operation.table_name == "positions":
                    await self.db.upsert_position(operation.data)

        elif operation.batch_type == BatchType.UPDATE:
            await self._process_single_update_operation(conn, operation)

        elif operation.batch_type == BatchType.DELETE:
            await self._process_single_delete_operation(conn, operation)

    async def _process_single_update_operation(self, conn, operation: BatchOperation):
        """Process a single update operation."""
        if operation.sql_query and operation.parameters:
            await conn.execute(operation.sql_query, operation.parameters)
        else:
            # Use existing database methods or build update query
            conditions = operation.metadata.get("conditions", {})
            if conditions and operation.table_name == "orders":
                # Use existing update_order method
                order_id = conditions.get("id")
                if order_id:
                    await self.db.update_order(order_id, operation.data)

    async def _process_single_delete_operation(self, conn, operation: BatchOperation):
        """Process a single delete operation."""
        if operation.sql_query and operation.parameters:
            await conn.execute(operation.sql_query, operation.parameters)

    async def _process_single_upsert_operation(self, conn, operation: BatchOperation):
        """Process a single upsert operation."""
        if operation.sql_query and operation.parameters:
            await conn.execute(operation.sql_query, operation.parameters)
        else:
            # Try insert first, then update if needed
            try:
                await self._process_single_operation_with_conn(
                    conn,
                    BatchOperation(
                        operation_id=operation.operation_id + "_insert",
                        batch_type=BatchType.INSERT,
                        table_name=operation.table_name,
                        data=operation.data,
                    ),
                )
            except Exception:
                # If insert fails, try update
                await self._process_single_operation_with_conn(
                    conn,
                    BatchOperation(
                        operation_id=operation.operation_id + "_update",
                        batch_type=BatchType.UPDATE,
                        table_name=operation.table_name,
                        data=operation.data,
                        metadata=operation.metadata,
                    ),
                )

    async def _retry_failed_operations(self, operations: list[BatchOperation]):
        """Retry failed operations individually."""
        for op in operations:
            if op.retries < self.config.retry_attempts:
                op.retries += 1
                await self.submit_operation(op)

    async def _batch_timer_worker(self):
        """Worker that flushes batches based on time thresholds."""
        while self._running:
            try:
                await asyncio.sleep(self.config.max_wait_time_ms / 1000.0)
                await self._check_and_flush_timed_batches()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in batch timer worker: {e}")

    async def _check_and_flush_timed_batches(self):
        """Check and flush batches that have exceeded time threshold."""
        current_time = datetime.now()
        tables_to_flush = []

        for table_name, batch_time in self._batch_timers.items():
            if (
                current_time - batch_time
            ).total_seconds() * 1000 >= self.config.max_wait_time_ms:
                tables_to_flush.append(table_name)

        for table_name in tables_to_flush:
            await self._flush_table_batches(table_name)

    async def _flush_table_batches(self, table_name: str):
        """Flush all pending batches for a specific table."""
        with self._batch_locks[table_name]:
            if table_name in self._table_batches:
                table_batches = self._table_batches[table_name]
                for _batch_type, operations in table_batches.items():
                    if operations:
                        # Submit operations for processing
                        for op in operations:
                            self.queue.put(op)
                        operations.clear()

                # Reset batch timer
                if table_name in self._batch_timers:
                    del self._batch_timers[table_name]

    async def _flush_all_batches(self):
        """Flush all pending batches."""
        tables = list(self._table_batches.keys())
        for table_name in tables:
            await self._flush_table_batches(table_name)

    def _get_optimal_batch_size(self) -> int:
        """Calculate optimal batch size based on current performance."""
        if self.config.strategy == BatchStrategy.ADAPTIVE:
            # Adjust batch size based on recent performance
            if len(self._performance_history) > 10:
                recent_avg_time = sum(self._performance_history) / len(
                    self._performance_history
                )
                if recent_avg_time > 1000:  # If processing time > 1 second
                    self._adaptive_batch_size = max(
                        self.config.min_batch_size, self._adaptive_batch_size - 10
                    )
                elif recent_avg_time < 200:  # If processing time < 200ms
                    self._adaptive_batch_size = min(
                        self.config.max_batch_size, self._adaptive_batch_size + 10
                    )

            return self._adaptive_batch_size

        elif self.config.strategy == BatchStrategy.SIZE_BASED:
            return self.config.max_batch_size

        else:  # HYBRID or TIME_BASED
            return min(
                self.config.max_batch_size,
                max(self.config.min_batch_size, int(self.queue.size() * 0.1)),
            )

    async def _update_metrics(
        self,
        total_ops: int,
        success_ops: int,
        failed_ops: int,
        processing_time_ms: float,
    ):
        """Update batch processing metrics."""
        if not self.config.enable_metrics:
            return

        with self._metrics_lock:
            self.metrics.successful_operations += success_ops
            self.metrics.failed_operations += failed_ops
            self.metrics.total_batches_processed += 1

            # Update running averages
            if self.metrics.total_batches_processed > 1:
                alpha = 0.1  # Exponential moving average factor
                self.metrics.average_processing_time_ms = (
                    alpha * processing_time_ms
                    + (1 - alpha) * self.metrics.average_processing_time_ms
                )
            else:
                self.metrics.average_processing_time_ms = processing_time_ms

            # Update performance history for adaptive batching
            self._performance_history.append(processing_time_ms)

            # Calculate throughput
            if processing_time_ms > 0:
                batch_throughput = (success_ops * 1000.0) / processing_time_ms
                if self.metrics.throughput_ops_per_second > 0:
                    self.metrics.throughput_ops_per_second = (
                        0.1 * batch_throughput
                        + 0.9 * self.metrics.throughput_ops_per_second
                    )
                else:
                    self.metrics.throughput_ops_per_second = batch_throughput

            self.metrics.last_updated = datetime.now()

    async def _metrics_worker(self):
        """Worker that periodically logs performance metrics."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Log metrics every 30 seconds
                metrics = await self.get_metrics()

                logger.info(
                    f"Batch Metrics - Ops: {metrics.total_operations} "
                    f"(Success: {metrics.successful_operations}, Failed: {metrics.failed_operations}), "
                    f"Batches: {metrics.total_batches_processed}, "
                    f"Avg Size: {metrics.average_batch_size:.1f}, "
                    f"Avg Time: {metrics.average_processing_time_ms:.1f}ms, "
                    f"Throughput: {metrics.throughput_ops_per_second:.1f} ops/sec, "
                    f"Error Rate: {metrics.error_rate:.2%}"
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics worker: {e}")


# Global batch processor instance
_batch_processor: BatchProcessor | None = None


def get_batch_processor(
    database_manager=None, config: BatchConfig = None
) -> BatchProcessor:
    """Get or create the global batch processor instance."""
    global _batch_processor
    if _batch_processor is None and database_manager is not None:
        _batch_processor = BatchProcessor(database_manager, config)
    return _batch_processor


async def initialize_batch_processor(database_manager, config: BatchConfig = None):
    """Initialize and start the global batch processor."""
    global _batch_processor
    _batch_processor = BatchProcessor(database_manager, config)
    await _batch_processor.start()
    logger.info("Global batch processor initialized and started")


async def shutdown_batch_processor():
    """Shutdown the global batch processor."""
    global _batch_processor
    if _batch_processor:
        await _batch_processor.stop()
        _batch_processor = None
    logger.info("Global batch processor shutdown complete")
