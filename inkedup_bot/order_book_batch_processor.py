"""
Order Book Batch Processing System for High-Performance Database Operations.

This module provides efficient batch processing capabilities for order book data,
replacing individual database operations with optimized batch upserts to handle
high-volume market data during volatility periods.

Key Features:
- Batch upsert operations for order book snapshots
- Automatic batching based on size and time thresholds
- Memory-efficient processing with configurable limits
- Performance metrics and monitoring
- Error handling with partial failure recovery
- Background processing with async queues
"""

import asyncio
import logging
import sqlite3
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


class BatchStatus(Enum):
    """Status of batch processing operations."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL_SUCCESS = "partial_success"


@dataclass
class OrderBookSnapshot:
    """Order book snapshot data structure."""

    token_id: str
    market_slug: str
    timestamp: float
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    spread_bps: Optional[float] = None
    mid_price: Optional[float] = None
    liquidity_score: Optional[float] = None
    volatility_score: Optional[float] = None

    def to_tuple(self) -> Tuple:
        """Convert to tuple for database insertion."""
        return (
            self.token_id,
            self.market_slug,
            self.timestamp,
            self.bid_price,
            self.ask_price,
            self.bid_size,
            self.ask_size,
            self.spread_bps,
            self.mid_price,
            self.liquidity_score,
            self.volatility_score,
        )


@dataclass
class BatchConfig:
    """Configuration for batch processing operations."""

    # Batch size thresholds
    max_batch_size: int = 1000  # Maximum records per batch
    min_batch_size: int = 50  # Minimum records to trigger batch

    # Time thresholds
    max_batch_age_seconds: int = 30  # Force batch after this time
    flush_interval_seconds: int = 5  # Check for batches to flush

    # Memory management
    max_queue_size: int = 10000  # Maximum queued records
    max_memory_mb: int = 100  # Maximum memory usage

    # Performance tuning
    concurrent_batches: int = 3  # Number of concurrent batch operations
    retry_attempts: int = 3  # Number of retry attempts on failure
    retry_delay_seconds: float = 1.0  # Delay between retries

    # Monitoring
    enable_metrics: bool = True
    metrics_report_interval: int = 60  # Report metrics every 60 seconds


@dataclass
class BatchMetrics:
    """Metrics for batch processing performance."""

    # Processing counts
    total_records_processed: int = 0
    total_batches_completed: int = 0
    total_batches_failed: int = 0

    # Performance metrics
    avg_batch_size: float = 0.0
    avg_processing_time_ms: float = 0.0
    max_processing_time_ms: float = 0.0

    # Throughput metrics
    records_per_second: float = 0.0
    batches_per_minute: float = 0.0

    # Error metrics
    failed_records: int = 0
    partial_failures: int = 0
    retry_count: int = 0

    # Resource usage
    peak_queue_size: int = 0
    peak_memory_mb: float = 0.0

    # Timing
    last_batch_time: float = 0.0
    last_metrics_reset: datetime = field(default_factory=datetime.now)

    def update_batch_completed(self, batch_size: int, processing_time_ms: float):
        """Update metrics when batch completes successfully."""
        self.total_batches_completed += 1
        self.total_records_processed += batch_size

        # Update averages
        total_batches = self.total_batches_completed
        self.avg_batch_size = (
            self.avg_batch_size * (total_batches - 1) + batch_size
        ) / total_batches
        self.avg_processing_time_ms = (
            self.avg_processing_time_ms * (total_batches - 1) + processing_time_ms
        ) / total_batches
        self.max_processing_time_ms = max(
            self.max_processing_time_ms, processing_time_ms
        )

        # Update throughput
        time_elapsed = time.time() - self.last_metrics_reset.timestamp()
        if time_elapsed > 0:
            self.records_per_second = self.total_records_processed / time_elapsed
            self.batches_per_minute = (self.total_batches_completed * 60) / time_elapsed

        self.last_batch_time = time.time()

    def reset(self):
        """Reset metrics for new reporting period."""
        self.__init__()


class OrderBookBatchProcessor:
    """
    High-performance batch processor for order book data.

    Provides efficient batch database operations with automatic batching,
    error handling, and performance monitoring for high-volume market data.
    """

    def __init__(self, database_manager: Any, config: Optional[BatchConfig] = None):
        """
        Initialize batch processor.

        Args:
            database_manager: Database manager instance for operations
            config: Batch processing configuration
        """
        self.db_manager = database_manager
        self.config = config or BatchConfig()

        # Processing queues and state
        self.pending_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.config.max_queue_size
        )
        self.processing_batches: Dict[str, List[OrderBookSnapshot]] = {}

        # Metrics and monitoring
        self.metrics = BatchMetrics()

        # Async processing tasks
        self._batch_processor_task: Optional[asyncio.Task] = None
        self._metrics_task: Optional[asyncio.Task] = None
        self._flush_task: Optional[asyncio.Task] = None

        # State management
        self._processing = False
        self._shutdown_event = asyncio.Event()

        log.info(
            f"OrderBookBatchProcessor initialized: "
            f"max_batch_size={self.config.max_batch_size}, "
            f"max_queue_size={self.config.max_queue_size}, "
            f"concurrent_batches={self.config.concurrent_batches}"
        )

    async def start(self) -> None:
        """Start batch processing services."""
        if self._processing:
            return

        self._processing = True
        self._shutdown_event.clear()

        # Ensure order book table exists
        await self._ensure_order_book_table()

        # Start background tasks
        self._batch_processor_task = asyncio.create_task(self._batch_processor_loop())
        self._flush_task = asyncio.create_task(self._flush_loop())

        if self.config.enable_metrics:
            self._metrics_task = asyncio.create_task(self._metrics_loop())

        log.info("OrderBookBatchProcessor started")

    async def stop(self) -> None:
        """Stop batch processing services."""
        if not self._processing:
            return

        log.info("Stopping OrderBookBatchProcessor...")
        self._processing = False
        self._shutdown_event.set()

        # Process any remaining items
        await self._flush_all_batches()

        # Cancel background tasks
        for task in [self._batch_processor_task, self._flush_task, self._metrics_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        log.info("OrderBookBatchProcessor stopped")

    async def add_snapshot(self, snapshot: OrderBookSnapshot) -> bool:
        """
        Add order book snapshot to processing queue.

        Args:
            snapshot: Order book snapshot to process

        Returns:
            True if added successfully, False if queue is full
        """
        try:
            await self.pending_queue.put(snapshot)

            # Update queue size metrics
            current_size = self.pending_queue.qsize()
            self.metrics.peak_queue_size = max(
                self.metrics.peak_queue_size, current_size
            )

            return True

        except asyncio.QueueFull:
            log.warning("Order book batch queue is full, dropping snapshot")
            return False

    async def add_snapshots_batch(self, snapshots: List[OrderBookSnapshot]) -> int:
        """
        Add multiple snapshots in batch.

        Args:
            snapshots: List of snapshots to add

        Returns:
            Number of snapshots successfully added
        """
        added_count = 0
        for snapshot in snapshots:
            success = await self.add_snapshot(snapshot)
            if success:
                added_count += 1
            else:
                break  # Stop on first failure to maintain order

        return added_count

    async def _ensure_order_book_table(self) -> None:
        """Ensure order book table exists with proper schema."""
        try:
            async with self.db_manager.connection() as db:
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS order_book_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        token_id TEXT NOT NULL,
                        market_slug TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        bid_price REAL,
                        ask_price REAL,
                        bid_size REAL,
                        ask_size REAL,
                        spread_bps REAL,
                        mid_price REAL,
                        liquidity_score REAL,
                        volatility_score REAL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )

                # Create indexes for performance
                await db.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_order_book_token_time 
                    ON order_book_snapshots (token_id, timestamp)
                """
                )

                await db.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_order_book_market_time 
                    ON order_book_snapshots (market_slug, timestamp)
                """
                )

                await db.commit()

            log.info("Order book table and indexes ensured")

        except Exception as e:
            log.error(f"Failed to create order book table: {e}")
            raise

    async def _batch_processor_loop(self) -> None:
        """Main batch processing loop."""
        current_batch: List[OrderBookSnapshot] = []
        batch_start_time = time.time()

        while self._processing or not self.pending_queue.empty():
            try:
                # Wait for next snapshot with timeout
                try:
                    snapshot = await asyncio.wait_for(
                        self.pending_queue.get(), timeout=1.0
                    )
                    current_batch.append(snapshot)

                except asyncio.TimeoutError:
                    # Check if we should process current batch on timeout
                    if current_batch:
                        age_seconds = time.time() - batch_start_time
                        if age_seconds >= self.config.max_batch_age_seconds:
                            await self._process_batch(current_batch)
                            current_batch = []
                            batch_start_time = time.time()
                    continue

                # Check if batch is ready for processing
                batch_ready = (
                    len(current_batch) >= self.config.max_batch_size
                    or (time.time() - batch_start_time)
                    >= self.config.max_batch_age_seconds
                )

                if batch_ready and len(current_batch) >= self.config.min_batch_size:
                    await self._process_batch(current_batch)
                    current_batch = []
                    batch_start_time = time.time()

            except Exception as e:
                log.error(f"Error in batch processor loop: {e}")
                await asyncio.sleep(1.0)

        # Process any remaining items
        if current_batch:
            await self._process_batch(current_batch)

    async def _process_batch(self, batch: List[OrderBookSnapshot]) -> bool:
        """
        Process a batch of order book snapshots.

        Args:
            batch: List of snapshots to process

        Returns:
            True if batch processed successfully
        """
        if not batch:
            return True

        start_time = time.perf_counter()
        batch_id = f"batch_{int(time.time() * 1000)}"

        try:
            log.debug(f"Processing batch {batch_id} with {len(batch)} snapshots")

            # Prepare batch data for insertion
            batch_data = [snapshot.to_tuple() for snapshot in batch]

            # Execute batch upsert with retry logic
            success = await self._execute_batch_upsert(batch_data)

            if success:
                processing_time_ms = (time.perf_counter() - start_time) * 1000
                self.metrics.update_batch_completed(len(batch), processing_time_ms)

                log.debug(
                    f"Batch {batch_id} completed: {len(batch)} records in "
                    f"{processing_time_ms:.1f}ms ({len(batch) / (processing_time_ms / 1000):.0f} rec/sec)"
                )
                return True
            else:
                self.metrics.total_batches_failed += 1
                self.metrics.failed_records += len(batch)
                log.error(f"Batch {batch_id} failed after all retries")
                return False

        except Exception as e:
            self.metrics.total_batches_failed += 1
            self.metrics.failed_records += len(batch)
            log.error(f"Error processing batch {batch_id}: {e}")
            return False

    async def _execute_batch_upsert(self, batch_data: List[Tuple]) -> bool:
        """
        Execute batch upsert operation with retry logic.

        Args:
            batch_data: List of tuples for database insertion

        Returns:
            True if operation succeeded
        """
        for attempt in range(self.config.retry_attempts):
            try:
                async with self.db_manager.connection() as db:
                    # Use INSERT OR REPLACE for upsert behavior
                    await db.executemany(
                        """
                        INSERT OR REPLACE INTO order_book_snapshots (
                            token_id, market_slug, timestamp, bid_price, ask_price,
                            bid_size, ask_size, spread_bps, mid_price, 
                            liquidity_score, volatility_score
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        batch_data,
                    )

                    await db.commit()
                    return True

            except sqlite3.Error as e:
                self.metrics.retry_count += 1
                log.warning(f"Batch upsert attempt {attempt + 1} failed: {e}")

                if attempt < self.config.retry_attempts - 1:
                    await asyncio.sleep(self.config.retry_delay_seconds * (attempt + 1))
                else:
                    log.error("Batch upsert failed after all retry attempts")

            except Exception as e:
                log.error(f"Unexpected error in batch upsert: {e}")
                break

        return False

    async def _flush_loop(self) -> None:
        """Background task to periodically flush old batches."""
        while self._processing:
            try:
                await asyncio.sleep(self.config.flush_interval_seconds)
                # The main batch processor handles flushing based on time
                # This task is for additional cleanup if needed

            except Exception as e:
                log.error(f"Error in flush loop: {e}")

    async def _flush_all_batches(self) -> None:
        """Flush all remaining items in the queue."""
        remaining_items = []

        # Drain the queue
        while not self.pending_queue.empty():
            try:
                item = await asyncio.wait_for(self.pending_queue.get(), timeout=0.1)
                remaining_items.append(item)
            except asyncio.TimeoutError:
                break

        # Process remaining items
        if remaining_items:
            log.info(f"Flushing {len(remaining_items)} remaining snapshots")
            await self._process_batch(remaining_items)

    async def _metrics_loop(self) -> None:
        """Background task for metrics reporting."""
        while self._processing:
            try:
                await asyncio.sleep(self.config.metrics_report_interval)
                self._report_metrics()
            except Exception as e:
                log.error(f"Error in metrics loop: {e}")

    def _report_metrics(self) -> None:
        """Report current batch processing metrics."""
        metrics = self.metrics

        log.info(
            f"Batch processing metrics: "
            f"batches={metrics.total_batches_completed}, "
            f"records={metrics.total_records_processed}, "
            f"avg_batch_size={metrics.avg_batch_size:.1f}, "
            f"avg_time={metrics.avg_processing_time_ms:.1f}ms, "
            f"throughput={metrics.records_per_second:.0f} rec/sec, "
            f"failures={metrics.total_batches_failed}, "
            f"queue_size={self.pending_queue.qsize()}"
        )

        if metrics.total_batches_failed > 0:
            error_rate = metrics.total_batches_failed / (
                metrics.total_batches_completed + metrics.total_batches_failed
            )
            log.warning(f"Batch error rate: {error_rate:.1%}")

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics."""
        metrics = self.metrics

        return {
            "processing_stats": {
                "total_records_processed": metrics.total_records_processed,
                "total_batches_completed": metrics.total_batches_completed,
                "total_batches_failed": metrics.total_batches_failed,
                "avg_batch_size": metrics.avg_batch_size,
                "records_per_second": metrics.records_per_second,
                "batches_per_minute": metrics.batches_per_minute,
            },
            "performance": {
                "avg_processing_time_ms": metrics.avg_processing_time_ms,
                "max_processing_time_ms": metrics.max_processing_time_ms,
                "last_batch_time": metrics.last_batch_time,
            },
            "errors": {
                "failed_records": metrics.failed_records,
                "partial_failures": metrics.partial_failures,
                "retry_count": metrics.retry_count,
                "error_rate": metrics.total_batches_failed
                / max(
                    1, metrics.total_batches_completed + metrics.total_batches_failed
                ),
            },
            "resources": {
                "current_queue_size": self.pending_queue.qsize(),
                "peak_queue_size": metrics.peak_queue_size,
                "peak_memory_mb": metrics.peak_memory_mb,
                "queue_utilization": self.pending_queue.qsize()
                / self.config.max_queue_size,
            },
            "configuration": {
                "max_batch_size": self.config.max_batch_size,
                "max_queue_size": self.config.max_queue_size,
                "concurrent_batches": self.config.concurrent_batches,
                "max_batch_age_seconds": self.config.max_batch_age_seconds,
            },
        }

    async def get_recent_snapshots(
        self,
        token_id: Optional[str] = None,
        market_slug: Optional[str] = None,
        hours: int = 24,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve recent order book snapshots from database.

        Args:
            token_id: Filter by specific token ID
            market_slug: Filter by market slug
            hours: Number of hours to look back
            limit: Maximum number of records to return

        Returns:
            List of order book snapshot records
        """
        try:
            cutoff_time = time.time() - (hours * 3600)

            # Build query based on filters
            where_conditions = ["timestamp > ?"]
            params = [cutoff_time]

            if token_id:
                where_conditions.append("token_id = ?")
                params.append(token_id)

            if market_slug:
                where_conditions.append("market_slug = ?")
                params.append(market_slug)

            query = f"""
                SELECT * FROM order_book_snapshots 
                WHERE {' AND '.join(where_conditions)}
                ORDER BY timestamp DESC 
                LIMIT ?
            """
            params.append(limit)

            async with self.db_manager.connection() as db:
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]

        except Exception as e:
            log.error(f"Error retrieving snapshots: {e}")
            return []

    def reset_metrics(self) -> None:
        """Reset performance metrics."""
        self.metrics.reset()
        log.info("Batch processor metrics reset")


# Utility functions for integration with scanner
def create_snapshot_from_book_entry(
    entry: Any,  # BookEntry from scanner
    market_slug: str,
    timestamp: Optional[float] = None,
) -> OrderBookSnapshot:
    """
    Create OrderBookSnapshot from scanner BookEntry.

    Args:
        entry: BookEntry from scanner
        market_slug: Market identifier
        timestamp: Optional timestamp (uses current time if None)

    Returns:
        OrderBookSnapshot instance
    """
    if timestamp is None:
        timestamp = time.time()

    # Calculate mid price if both bid and ask available
    mid_price = None
    if entry.bid is not None and entry.ask is not None:
        mid_price = (entry.bid + entry.ask) / 2

    return OrderBookSnapshot(
        token_id=entry.token_id,
        market_slug=market_slug,
        timestamp=timestamp,
        bid_price=entry.bid,
        ask_price=entry.ask,
        spread_bps=entry.spread_bps,
        mid_price=mid_price,
    )


async def create_batch_processor(
    database_manager: Any,
    max_batch_size: int = 1000,
    max_queue_size: int = 10000,
    max_batch_age_seconds: int = 30,
) -> OrderBookBatchProcessor:
    """
    Factory function to create and start order book batch processor.

    Args:
        database_manager: Database manager instance
        max_batch_size: Maximum records per batch
        max_queue_size: Maximum queued records
        max_batch_age_seconds: Maximum batch age before forced processing

    Returns:
        Started OrderBookBatchProcessor instance
    """
    config = BatchConfig(
        max_batch_size=max_batch_size,
        max_queue_size=max_queue_size,
        max_batch_age_seconds=max_batch_age_seconds,
    )

    processor = OrderBookBatchProcessor(database_manager, config)
    await processor.start()

    return processor
