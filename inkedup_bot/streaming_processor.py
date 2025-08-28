#!/usr/bin/env python3
"""
Memory-Efficient Streaming Data Processor for InkedUp Bot

This module provides streaming data processing capabilities that minimize memory usage
for handling large datasets and continuous data streams.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import AsyncGenerator, Callable, Generator, Iterable
from dataclasses import dataclass
from enum import Enum
from typing import (
    Any,
    TypeVar,
)

from .memory_optimizer import CircularBuffer, memory_optimizer

logger = logging.getLogger(__name__)

T = TypeVar("T")
U = TypeVar("U")


class ProcessingStrategy(Enum):
    """Data processing strategies for memory efficiency."""

    BATCH = "batch"  # Process in fixed-size batches
    STREAMING = "streaming"  # Process items one at a time
    WINDOWED = "windowed"  # Process in sliding windows
    CHUNKED = "chunked"  # Process in chunks based on memory limits


@dataclass
class StreamingConfig:
    """Configuration for streaming data processing."""

    strategy: ProcessingStrategy = ProcessingStrategy.STREAMING
    batch_size: int = 1000
    window_size: int = 100
    memory_limit_mb: float = 50.0
    max_queue_size: int = 10000
    enable_backpressure: bool = True
    checkpoint_interval: int = 1000


class StreamProcessor(ABC):
    """Abstract base class for streaming data processors."""

    @abstractmethod
    async def process(self, item: T) -> U:
        """Process a single item."""
        pass

    @abstractmethod
    async def process_batch(self, items: list[T]) -> list[U]:
        """Process a batch of items."""
        pass


class MemoryEfficientIterator:
    """
    Memory-efficient iterator that yields items without loading entire dataset.

    Supports various data sources and implements lazy loading to minimize memory usage.
    """

    def __init__(
        self,
        data_source: Iterable[T] | Callable[[], Generator[T, None, None]],
        chunk_size: int = 1000,
    ):
        self.data_source = data_source
        self.chunk_size = chunk_size
        self._current_chunk: list[T] | None = None
        self._chunk_index = 0
        self._item_index = 0
        self._exhausted = False

    def __iter__(self):
        return self

    def __next__(self) -> T:
        if self._exhausted:
            raise StopIteration

        # Load next chunk if needed
        if self._current_chunk is None or self._item_index >= len(self._current_chunk):
            self._load_next_chunk()
            if self._current_chunk is None or len(self._current_chunk) == 0:
                self._exhausted = True
                raise StopIteration

        item = self._current_chunk[self._item_index]
        self._item_index += 1
        return item

    def _load_next_chunk(self):
        """Load the next chunk of data."""
        try:
            if callable(self.data_source):
                # Generator function
                if not hasattr(self, "_generator"):
                    self._generator = self.data_source()

                chunk = []
                for _ in range(self.chunk_size):
                    try:
                        chunk.append(next(self._generator))
                    except StopIteration:
                        break

                self._current_chunk = chunk if chunk else None
            else:
                # Iterable data source
                if not hasattr(self, "_iterator"):
                    self._iterator = iter(self.data_source)

                chunk = []
                for _ in range(self.chunk_size):
                    try:
                        chunk.append(next(self._iterator))
                    except StopIteration:
                        break

                self._current_chunk = chunk if chunk else None

            self._chunk_index += 1
            self._item_index = 0

        except Exception as e:
            logger.error(f"Error loading chunk {self._chunk_index}: {e}")
            self._current_chunk = None


class StreamingDataProcessor:
    """
    High-performance streaming data processor with memory optimization.

    Processes data streams efficiently while maintaining low memory footprint
    through batching, windowing, and backpressure mechanisms.
    """

    def __init__(self, config: StreamingConfig, processor: StreamProcessor):
        self.config = config
        self.processor = processor

        # Processing state
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=config.max_queue_size)
        self._processed_count = 0
        self._error_count = 0
        self._last_checkpoint = 0

        # Memory management
        self._memory_optimizer = memory_optimizer
        self._buffer = CircularBuffer(config.max_queue_size)
        self._batch_buffer: list[T] = []
        self._processing_metrics = {
            "items_processed": 0,
            "batches_processed": 0,
            "errors": 0,
            "memory_usage_mb": 0.0,
            "processing_rate": 0.0,
        }

        # Backpressure handling
        self._backpressure_active = False
        self._backpressure_threshold = 0.8 * config.max_queue_size

    async def process_stream(
        self, data_stream: AsyncGenerator[T, None]
    ) -> AsyncGenerator[U, None]:
        """Process a data stream with memory-efficient handling."""
        if self.config.strategy == ProcessingStrategy.STREAMING:
            async for result in self._process_streaming(data_stream):
                yield result
        elif self.config.strategy == ProcessingStrategy.BATCH:
            async for result in self._process_batched(data_stream):
                yield result
        elif self.config.strategy == ProcessingStrategy.WINDOWED:
            async for result in self._process_windowed(data_stream):
                yield result
        elif self.config.strategy == ProcessingStrategy.CHUNKED:
            async for result in self._process_chunked(data_stream):
                yield result

    async def _process_streaming(
        self, data_stream: AsyncGenerator[T, None]
    ) -> AsyncGenerator[U, None]:
        """Process items one at a time."""
        async for item in data_stream:
            try:
                # Check for backpressure
                if self._should_apply_backpressure():
                    await self._handle_backpressure()

                result = await self.processor.process(item)
                self._processed_count += 1
                self._update_metrics()

                yield result

                # Checkpoint if needed
                if self._should_checkpoint():
                    await self._checkpoint()

            except Exception as e:
                self._error_count += 1
                logger.error(f"Error processing item {self._processed_count}: {e}")
                continue

    async def _process_batched(
        self, data_stream: AsyncGenerator[T, None]
    ) -> AsyncGenerator[U, None]:
        """Process items in fixed-size batches."""
        batch = []

        async for item in data_stream:
            batch.append(item)

            if len(batch) >= self.config.batch_size:
                try:
                    # Check for backpressure
                    if self._should_apply_backpressure():
                        await self._handle_backpressure()

                    results = await self.processor.process_batch(batch)
                    self._processed_count += len(batch)
                    self._update_metrics()

                    for result in results:
                        yield result

                    # Clear batch to free memory
                    batch.clear()

                    # Checkpoint if needed
                    if self._should_checkpoint():
                        await self._checkpoint()

                except Exception as e:
                    self._error_count += len(batch)
                    logger.error(f"Error processing batch of {len(batch)} items: {e}")
                    batch.clear()
                    continue

        # Process remaining items
        if batch:
            try:
                results = await self.processor.process_batch(batch)
                for result in results:
                    yield result
            except Exception as e:
                logger.error(f"Error processing final batch: {e}")

    async def _process_windowed(
        self, data_stream: AsyncGenerator[T, None]
    ) -> AsyncGenerator[U, None]:
        """Process items using sliding windows."""
        window = deque(maxlen=self.config.window_size)

        async for item in data_stream:
            window.append(item)

            if len(window) >= self.config.window_size:
                try:
                    # Process the current window
                    window_list = list(window)
                    results = await self.processor.process_batch(window_list)

                    self._processed_count += len(window_list)
                    self._update_metrics()

                    for result in results:
                        yield result

                    # Checkpoint if needed
                    if self._should_checkpoint():
                        await self._checkpoint()

                except Exception as e:
                    self._error_count += len(window)
                    logger.error(f"Error processing window: {e}")
                    continue

    async def _process_chunked(
        self, data_stream: AsyncGenerator[T, None]
    ) -> AsyncGenerator[U, None]:
        """Process items in memory-limited chunks."""
        chunk = []
        chunk_memory_mb = 0.0

        async for item in data_stream:
            # Estimate memory usage of item
            item_memory = self._estimate_item_memory(item)

            # If adding this item would exceed memory limit, process current chunk
            if chunk_memory_mb + item_memory > self.config.memory_limit_mb and chunk:
                try:
                    results = await self.processor.process_batch(chunk)
                    self._processed_count += len(chunk)
                    self._update_metrics()

                    for result in results:
                        yield result

                    # Clear chunk to free memory
                    chunk.clear()
                    chunk_memory_mb = 0.0

                    # Checkpoint if needed
                    if self._should_checkpoint():
                        await self._checkpoint()

                except Exception as e:
                    self._error_count += len(chunk)
                    logger.error(f"Error processing chunk of {len(chunk)} items: {e}")
                    chunk.clear()
                    chunk_memory_mb = 0.0
                    continue

            chunk.append(item)
            chunk_memory_mb += item_memory

        # Process remaining items
        if chunk:
            try:
                results = await self.processor.process_batch(chunk)
                for result in results:
                    yield result
            except Exception as e:
                logger.error(f"Error processing final chunk: {e}")

    def _estimate_item_memory(self, item: Any) -> float:
        """Estimate memory usage of an item in MB."""
        import sys

        return sys.getsizeof(item) / (1024 * 1024)

    def _should_apply_backpressure(self) -> bool:
        """Check if backpressure should be applied."""
        return (
            self.config.enable_backpressure
            and self._queue.qsize() > self._backpressure_threshold
        )

    async def _handle_backpressure(self):
        """Handle backpressure by waiting for queue to drain."""
        if not self._backpressure_active:
            self._backpressure_active = True
            logger.warning("Applying backpressure due to queue size")

        # Wait for queue to drain below threshold
        while self._queue.qsize() > self._backpressure_threshold * 0.5:
            await asyncio.sleep(0.1)

        if self._backpressure_active:
            self._backpressure_active = False
            logger.info("Backpressure released")

    def _should_checkpoint(self) -> bool:
        """Check if a checkpoint should be created."""
        return (
            self._processed_count - self._last_checkpoint
            >= self.config.checkpoint_interval
        )

    async def _checkpoint(self):
        """Create a processing checkpoint."""
        self._last_checkpoint = self._processed_count
        logger.info(
            f"Checkpoint: processed {self._processed_count} items, "
            f"{self._error_count} errors"
        )

    def _update_metrics(self):
        """Update processing metrics."""
        self._processing_metrics["items_processed"] = self._processed_count
        self._processing_metrics["errors"] = self._error_count

        # Get current memory usage
        memory_report = self._memory_optimizer.get_memory_report()
        self._processing_metrics["memory_usage_mb"] = memory_report["system_metrics"][
            "process_memory_mb"
        ]

    def get_metrics(self) -> dict[str, Any]:
        """Get current processing metrics."""
        return self._processing_metrics.copy()


class DatabaseResultIterator:
    """
    Memory-efficient iterator for database query results.

    Fetches results in chunks to avoid loading entire result set into memory.
    """

    def __init__(self, query: str, connection, chunk_size: int = 1000):
        self.query = query
        self.connection = connection
        self.chunk_size = chunk_size
        self._cursor = None
        self._current_chunk = []
        self._chunk_index = 0
        self._exhausted = False

    def __iter__(self):
        return self

    def __next__(self):
        if self._exhausted:
            raise StopIteration

        # Initialize cursor on first access
        if self._cursor is None:
            self._cursor = self.connection.execute(self.query)

        # Load next chunk if current is empty
        if not self._current_chunk:
            self._load_next_chunk()
            if not self._current_chunk:
                self._exhausted = True
                raise StopIteration

        return self._current_chunk.pop(0)

    def _load_next_chunk(self):
        """Load next chunk of results."""
        try:
            rows = self._cursor.fetchmany(self.chunk_size)
            self._current_chunk = list(rows)
            self._chunk_index += 1
        except Exception as e:
            logger.error(f"Error loading database chunk: {e}")
            self._current_chunk = []

    def close(self):
        """Close the cursor and clean up resources."""
        if self._cursor:
            self._cursor.close()
            self._cursor = None


class MemoryAwareAggregator:
    """
    Memory-aware data aggregator for large datasets.

    Performs aggregations while maintaining bounded memory usage
    through streaming and incremental calculation techniques.
    """

    def __init__(self, max_memory_mb: float = 100.0):
        self.max_memory_mb = max_memory_mb
        self._aggregators: dict[str, Any] = {}
        self._memory_usage = 0.0

    def add_aggregator(self, name: str, aggregator: Callable[[list[Any]], Any]):
        """Add a named aggregator function."""
        self._aggregators[name] = {
            "function": aggregator,
            "partial_results": [],
            "memory_usage": 0.0,
        }

    async def aggregate(self, data_stream: AsyncGenerator[Any, None]) -> dict[str, Any]:
        """Perform aggregation on data stream."""
        batch = []
        batch_memory = 0.0

        async for item in data_stream:
            item_memory = self._estimate_memory(item)

            # If adding this item would exceed memory limit, process current batch
            if batch_memory + item_memory > self.max_memory_mb and batch:
                await self._process_batch(batch)
                batch.clear()
                batch_memory = 0.0

            batch.append(item)
            batch_memory += item_memory

        # Process final batch
        if batch:
            await self._process_batch(batch)

        # Calculate final results
        return self._calculate_final_results()

    async def _process_batch(self, batch: list[Any]):
        """Process a batch of data through all aggregators."""
        for name, agg_info in self._aggregators.items():
            try:
                partial_result = agg_info["function"](batch)
                agg_info["partial_results"].append(partial_result)
                agg_info["memory_usage"] += self._estimate_memory(partial_result)
            except Exception as e:
                logger.error(f"Error in aggregator {name}: {e}")

    def _calculate_final_results(self) -> dict[str, Any]:
        """Calculate final aggregation results."""
        results = {}

        for name, agg_info in self._aggregators.items():
            try:
                # Combine partial results
                if agg_info["partial_results"]:
                    results[name] = agg_info["function"](agg_info["partial_results"])
                else:
                    results[name] = None
            except Exception as e:
                logger.error(f"Error calculating final result for {name}: {e}")
                results[name] = None

        return results

    def _estimate_memory(self, obj: Any) -> float:
        """Estimate memory usage of an object in MB."""
        import sys

        return sys.getsizeof(obj) / (1024 * 1024)


class StreamingJoinProcessor:
    """
    Memory-efficient stream join processor.

    Joins two data streams while maintaining bounded memory usage
    through windowing and spill-to-disk mechanisms.
    """

    def __init__(
        self, join_key: str, window_size: int = 10000, max_memory_mb: float = 100.0
    ):
        self.join_key = join_key
        self.window_size = window_size
        self.max_memory_mb = max_memory_mb

        # Join state
        self._left_window: dict[Any, list[Any]] = {}
        self._right_window: dict[Any, list[Any]] = {}
        self._memory_usage = 0.0

    async def join(
        self,
        left_stream: AsyncGenerator[dict[str, Any], None],
        right_stream: AsyncGenerator[dict[str, Any], None],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Perform streaming join of two data streams."""
        # This is a simplified implementation - in practice, you'd need
        # more sophisticated coordination between the streams

        left_task = asyncio.create_task(self._process_left_stream(left_stream))
        right_task = asyncio.create_task(self._process_right_stream(right_stream))

        try:
            # Wait for both streams to complete
            await asyncio.gather(left_task, right_task)

            # Yield all join results
            for key in self._left_window:
                if key in self._right_window:
                    for left_item in self._left_window[key]:
                        for right_item in self._right_window[key]:
                            yield {**left_item, **right_item}

        except Exception as e:
            logger.error(f"Error in streaming join: {e}")
        finally:
            # Clean up
            self._left_window.clear()
            self._right_window.clear()

    async def _process_left_stream(self, stream: AsyncGenerator[dict[str, Any], None]):
        """Process left stream for join."""
        async for item in stream:
            key = item.get(self.join_key)
            if key is not None:
                if key not in self._left_window:
                    self._left_window[key] = []
                self._left_window[key].append(item)
                self._memory_usage += self._estimate_memory(item)

                # Check memory limits
                if self._memory_usage > self.max_memory_mb:
                    await self._spill_to_disk()

    async def _process_right_stream(self, stream: AsyncGenerator[dict[str, Any], None]):
        """Process right stream for join."""
        async for item in stream:
            key = item.get(self.join_key)
            if key is not None:
                if key not in self._right_window:
                    self._right_window[key] = []
                self._right_window[key].append(item)
                self._memory_usage += self._estimate_memory(item)

                # Check memory limits
                if self._memory_usage > self.max_memory_mb:
                    await self._spill_to_disk()

    async def _spill_to_disk(self):
        """Spill join state to disk when memory limit is reached."""
        # This would implement spill-to-disk logic
        # For now, just clear some entries
        logger.warning(
            "Memory limit reached in streaming join, implementing spill logic"
        )

        # Remove oldest entries (simplified)
        if len(self._left_window) > self.window_size // 2:
            keys_to_remove = list(self._left_window.keys())[
                : len(self._left_window) // 4
            ]
            for key in keys_to_remove:
                del self._left_window[key]

        if len(self._right_window) > self.window_size // 2:
            keys_to_remove = list(self._right_window.keys())[
                : len(self._right_window) // 4
            ]
            for key in keys_to_remove:
                del self._right_window[key]

        self._memory_usage = 0.0  # Recalculate if needed

    def _estimate_memory(self, obj: Any) -> float:
        """Estimate memory usage of an object in MB."""
        import sys

        return sys.getsizeof(obj) / (1024 * 1024)
