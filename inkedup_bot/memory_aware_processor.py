#!/usr/bin/env python3
"""
Memory-Aware Data Processor for InkedUp Bot

This module extends the existing batch processing system with advanced memory optimization
capabilities, ensuring efficient processing of large datasets without memory issues.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .batch_processor import BatchConfig, BatchOperation, BatchPriority, BatchProcessor
from .database_batched import BatchedDatabaseManager
from .memory_optimizer import CircularBuffer, MemoryThresholdLevel, memory_optimizer
from .streaming_processor import (
    ProcessingStrategy,
    StreamingConfig,
    StreamingDataProcessor,
)

logger = logging.getLogger(__name__)


class MemoryStrategy(Enum):
    """Memory management strategies for processing."""

    CONSERVATIVE = "conservative"  # Minimize memory usage at cost of speed
    BALANCED = "balanced"  # Balance memory usage and performance
    AGGRESSIVE = "aggressive"  # Maximize speed with higher memory usage
    ADAPTIVE = "adaptive"  # Dynamically adjust based on available memory


@dataclass
class MemoryAwareConfig:
    """Configuration for memory-aware processing."""

    max_memory_mb: float = 512.0  # Maximum memory to use
    memory_threshold: float = 0.8  # Threshold to trigger memory management
    enable_gc_optimization: bool = True  # Enable garbage collection optimization
    use_object_pooling: bool = True  # Use object pooling for frequent allocations
    cache_size_mb: float = 64.0  # Size of memory cache in MB
    streaming_chunk_size: int = 1000  # Size of streaming chunks
    spill_to_disk_threshold: float = 0.9  # Threshold to spill data to disk
    memory_strategy: MemoryStrategy = MemoryStrategy.BALANCED


class MemoryAwareBatchProcessor(BatchProcessor):
    """
    Enhanced batch processor with sophisticated memory management.

    Extends the base BatchProcessor with memory optimization features including:
    - Dynamic batch size adjustment based on memory pressure
    - Memory-efficient data structures
    - Automatic spill-to-disk for large datasets
    - Memory monitoring and alerting
    """

    def __init__(self, config: BatchConfig, memory_config: MemoryAwareConfig):
        super().__init__(config)
        self.memory_config = memory_config

        # Memory management components
        self._memory_optimizer = memory_optimizer
        self._memory_cache = self._memory_optimizer.create_cache(
            "batch_processor", max_memory_mb=memory_config.cache_size_mb
        )

        # Object pools for common data types
        if memory_config.use_object_pooling:
            self._operation_pool = self._memory_optimizer.create_pool(
                "batch_operations",
                factory=lambda: {"data": {}, "metadata": {}},
                max_size=1000,
            )
        else:
            self._operation_pool = None

        # Memory tracking
        self._memory_usage_history = CircularBuffer(1000)
        self._current_memory_usage = 0.0
        self._peak_memory_usage = 0.0

        # Dynamic batch size adjustment
        self._adaptive_batch_sizes: dict[str, int] = defaultdict(
            lambda: config.max_batch_size
        )
        self._batch_performance_history: dict[str, CircularBuffer] = defaultdict(
            lambda: CircularBuffer(100)
        )

        # Initialize memory optimization
        if not self._memory_optimizer._initialized:
            self._memory_optimizer.initialize()

        # Register cleanup callback
        self._memory_optimizer.monitor.add_cleanup_callback(
            self._handle_memory_pressure
        )

    async def submit_batch_operation(
        self,
        table_name: str,
        operations: list[BatchOperation],
        priority: BatchPriority = BatchPriority.NORMAL,
    ) -> bool:
        """Submit batch operation with memory-aware processing."""

        # Check memory usage before processing
        current_memory = self._get_current_memory_usage()

        if current_memory > self.memory_config.memory_threshold:
            await self._apply_memory_pressure_handling(operations)

        # Adjust batch size based on memory pressure and strategy
        adjusted_operations = await self._adjust_batch_for_memory(
            table_name, operations
        )

        # Use base class processing with memory tracking
        start_memory = current_memory
        result = await super().submit_batch_operation(
            table_name, adjusted_operations, priority
        )
        end_memory = self._get_current_memory_usage()

        # Track memory usage
        self._track_memory_usage(table_name, start_memory, end_memory, len(operations))

        return result

    async def _adjust_batch_for_memory(
        self, table_name: str, operations: list[BatchOperation]
    ) -> list[BatchOperation]:
        """Adjust batch size and strategy based on available memory."""

        if self.memory_config.memory_strategy == MemoryStrategy.CONSERVATIVE:
            return await self._conservative_adjustment(table_name, operations)
        elif self.memory_config.memory_strategy == MemoryStrategy.AGGRESSIVE:
            return operations  # No adjustment needed
        elif self.memory_config.memory_strategy == MemoryStrategy.ADAPTIVE:
            return await self._adaptive_adjustment(table_name, operations)
        else:  # BALANCED
            return await self._balanced_adjustment(table_name, operations)

    async def _conservative_adjustment(
        self, table_name: str, operations: list[BatchOperation]
    ) -> list[BatchOperation]:
        """Conservative memory adjustment - minimize memory usage."""
        max_size = min(100, len(operations))  # Very small batches

        if len(operations) > max_size:
            # Process in smaller chunks
            return operations[:max_size]
        return operations

    async def _adaptive_adjustment(
        self, table_name: str, operations: list[BatchOperation]
    ) -> list[BatchOperation]:
        """Adaptive adjustment based on current memory pressure and performance history."""

        current_memory = self._get_current_memory_usage()
        memory_pressure = current_memory / self.memory_config.max_memory_mb

        # Get current adaptive batch size
        current_batch_size = self._adaptive_batch_sizes[table_name]

        # Adjust based on memory pressure
        if memory_pressure > 0.9:
            # High pressure - reduce batch size significantly
            new_batch_size = max(10, current_batch_size // 4)
        elif memory_pressure > 0.7:
            # Medium pressure - reduce batch size moderately
            new_batch_size = max(50, current_batch_size // 2)
        elif memory_pressure < 0.5:
            # Low pressure - can increase batch size
            new_batch_size = min(self.config.max_batch_size, current_batch_size * 1.2)
        else:
            new_batch_size = current_batch_size

        # Update adaptive batch size
        self._adaptive_batch_sizes[table_name] = int(new_batch_size)

        # Return appropriate number of operations
        return operations[: int(new_batch_size)]

    async def _balanced_adjustment(
        self, table_name: str, operations: list[BatchOperation]
    ) -> list[BatchOperation]:
        """Balanced adjustment - optimize for both memory and performance."""

        current_memory = self._get_current_memory_usage()
        memory_pressure = current_memory / self.memory_config.max_memory_mb

        if memory_pressure > 0.8:
            # Reduce batch size when memory pressure is high
            max_size = min(500, len(operations))
            return operations[:max_size]
        else:
            # Use full batch when memory allows
            return operations

    async def _apply_memory_pressure_handling(self, operations: list[BatchOperation]):
        """Apply memory pressure handling strategies."""

        logger.warning("High memory usage detected, applying memory pressure handling")

        # Force garbage collection if enabled
        if self.memory_config.enable_gc_optimization:
            import gc

            collected = gc.collect()
            logger.info(f"Garbage collection freed {collected} objects")

        # Clear cache entries if memory is critically low
        current_memory = self._get_current_memory_usage()
        if current_memory > 0.9:
            self._memory_cache.clear()
            logger.info("Cleared memory cache due to high memory pressure")

        # Implement spill-to-disk if threshold exceeded
        if current_memory > self.memory_config.spill_to_disk_threshold:
            await self._spill_operations_to_disk(operations)

    async def _spill_operations_to_disk(self, operations: list[BatchOperation]):
        """Spill batch operations to disk to free memory."""
        # This is a simplified implementation - in production you'd want
        # more sophisticated disk-based buffering

        import pickle
        import tempfile

        try:
            with tempfile.NamedTemporaryFile(mode="wb", delete=False) as temp_file:
                pickle.dump(operations, temp_file)
                logger.info(
                    f"Spilled {len(operations)} operations to disk: {temp_file.name}"
                )

                # In a real implementation, you'd track these files and
                # reload them when memory becomes available

        except Exception as e:
            logger.error(f"Error spilling operations to disk: {e}")

    def _get_current_memory_usage(self) -> float:
        """Get current memory usage as percentage of maximum."""
        try:
            metrics = self._memory_optimizer.monitor.get_current_metrics()
            return metrics.process_memory_mb / self.memory_config.max_memory_mb
        except Exception:
            return 0.0

    def _track_memory_usage(
        self,
        table_name: str,
        start_memory: float,
        end_memory: float,
        operation_count: int,
    ):
        """Track memory usage for performance optimization."""

        memory_delta = end_memory - start_memory

        # Store in history
        usage_record = {
            "timestamp": datetime.now(),
            "table_name": table_name,
            "memory_delta": memory_delta,
            "operation_count": operation_count,
            "memory_per_operation": (
                memory_delta / operation_count if operation_count > 0 else 0
            ),
        }

        self._memory_usage_history.append(usage_record)

        # Update peak usage
        if end_memory > self._peak_memory_usage:
            self._peak_memory_usage = end_memory

        # Track performance history for adaptive sizing
        performance_record = {
            "memory_usage": end_memory,
            "throughput": operation_count / max(memory_delta, 0.001),
            "efficiency": operation_count / max(memory_delta, 0.001),
        }

        self._batch_performance_history[table_name].append(performance_record)

    def _handle_memory_pressure(self, threshold_level: MemoryThresholdLevel):
        """Handle memory pressure events."""

        logger.warning(f"Memory pressure detected: {threshold_level.value}")

        if threshold_level == MemoryThresholdLevel.CRITICAL:
            # Reduce all adaptive batch sizes
            for table_name in self._adaptive_batch_sizes:
                self._adaptive_batch_sizes[table_name] = max(
                    10, self._adaptive_batch_sizes[table_name] // 2
                )

            # Clear performance history to free memory
            for history in self._batch_performance_history.values():
                history.clear()

        elif threshold_level == MemoryThresholdLevel.EMERGENCY:
            # Emergency measures
            for table_name in self._adaptive_batch_sizes:
                self._adaptive_batch_sizes[table_name] = 10  # Minimum batch size

            # Clear all caches and histories
            self._memory_cache.clear()
            self._memory_usage_history.clear()
            for history in self._batch_performance_history.values():
                history.clear()

    def get_memory_statistics(self) -> dict[str, Any]:
        """Get comprehensive memory usage statistics."""

        current_metrics = self._memory_optimizer.monitor.get_current_metrics()
        cache_info = self._memory_cache.get_memory_info()

        # Calculate average memory usage
        recent_usage = [record["memory_delta"] for record in self._memory_usage_history]
        avg_usage = sum(recent_usage) / len(recent_usage) if recent_usage else 0.0

        # Pool statistics if available
        pool_stats = {}
        if self._operation_pool:
            pool_stats = self._operation_pool.get_stats()

        return {
            "current_memory_mb": current_metrics.process_memory_mb,
            "peak_memory_mb": self._peak_memory_usage
            * self.memory_config.max_memory_mb,
            "memory_threshold": self.memory_config.memory_threshold,
            "memory_utilization": current_metrics.process_memory_mb
            / self.memory_config.max_memory_mb,
            "average_memory_delta": avg_usage,
            "cache_info": cache_info,
            "pool_stats": pool_stats,
            "adaptive_batch_sizes": dict(self._adaptive_batch_sizes),
            "memory_strategy": self.memory_config.memory_strategy.value,
            "operations_processed": len(self._memory_usage_history),
        }


class MemoryOptimizedDatabaseManager(BatchedDatabaseManager):
    """
    Memory-optimized database manager that extends BatchedDatabaseManager
    with advanced memory management capabilities.
    """

    def __init__(self, db_path: str, memory_config: MemoryAwareConfig):
        super().__init__(db_path)
        self.memory_config = memory_config

        # Initialize memory-aware batch processor
        batch_config = BatchConfig(
            max_batch_size=min(
                1000, int(memory_config.max_memory_mb / 4)
            ),  # Adjust based on memory
            memory_threshold_mb=memory_config.max_memory_mb * 0.8,
        )

        self.memory_batch_processor = MemoryAwareBatchProcessor(
            batch_config, memory_config
        )

        # Memory-efficient result caching
        self._result_cache = memory_optimizer.create_cache(
            "db_results", max_memory_mb=memory_config.cache_size_mb / 2
        )

        # Query result streaming for large datasets
        self._streaming_threshold = 10000  # Switch to streaming for results > 10k rows

    async def batch_insert_orders_memory_optimized(
        self,
        orders: list[dict[str, Any]],
        priority: BatchPriority = BatchPriority.NORMAL,
    ) -> bool:
        """Memory-optimized batch insert for orders."""

        # Check if we should use streaming processing for very large batches
        if len(orders) > self._streaming_threshold:
            return await self._stream_insert_orders(orders, priority)
        else:
            return await self.batch_insert_orders(orders, priority)

    async def _stream_insert_orders(
        self, orders: list[dict[str, Any]], priority: BatchPriority
    ) -> bool:
        """Stream insert orders for memory efficiency."""

        # Configure streaming processor
        streaming_config = StreamingConfig(
            strategy=ProcessingStrategy.BATCH,
            batch_size=min(1000, len(orders) // 10),
            memory_limit_mb=self.memory_config.max_memory_mb * 0.3,
        )

        # Create a simple stream processor
        class OrderInsertProcessor:
            def __init__(self, db_manager):
                self.db_manager = db_manager

            async def process_batch(self, items: list[dict[str, Any]]) -> list[bool]:
                success = await self.db_manager.batch_insert_orders(items, priority)
                return [success] * len(items)

            async def process(self, item: dict[str, Any]) -> bool:
                return await self.process_batch([item])

        processor = OrderInsertProcessor(self)
        streaming_processor = StreamingDataProcessor(streaming_config, processor)

        # Convert list to async generator
        async def order_generator():
            for order in orders:
                yield order

        # Process stream
        results = []
        async for result in streaming_processor.process_stream(order_generator()):
            results.extend(result if isinstance(result, list) else [result])

        return all(results) if results else False

    async def get_large_dataset_stream(self, query: str, chunk_size: int = 1000):
        """Get large dataset as a memory-efficient stream."""

        try:
            conn = await self.get_connection()
            cursor = conn.execute(query)

            while True:
                chunk = cursor.fetchmany(chunk_size)
                if not chunk:
                    break

                # Yield chunk and allow memory cleanup
                yield chunk

                # Check memory pressure
                current_memory = memory_optimizer.monitor.get_current_metrics()
                if current_memory.memory_percent > 85:
                    logger.warning(
                        "High memory usage during stream processing, reducing chunk size"
                    )
                    chunk_size = max(100, chunk_size // 2)

            cursor.close()

        except Exception as e:
            logger.error(f"Error in streaming query: {e}")
            raise

    async def execute_memory_efficient_query(
        self, query: str, params: tuple | None = None
    ) -> Any:
        """Execute query with memory efficiency optimizations."""

        # Check cache first
        cache_key = f"{query}:{str(params)}" if params else query
        cached_result = self._result_cache.get(cache_key)

        if cached_result is not None:
            return cached_result

        try:
            result = await self.execute_query(query, params)

            # Cache result if it's not too large
            if result and len(str(result)) < 1024 * 1024:  # 1MB limit
                self._result_cache.put(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"Error in memory-efficient query: {e}")
            raise

    def get_memory_usage_report(self) -> dict[str, Any]:
        """Get comprehensive memory usage report for database operations."""

        base_report = memory_optimizer.get_memory_report()

        # Add database-specific metrics
        db_metrics = {
            "result_cache_info": self._result_cache.get_memory_info(),
            "streaming_threshold": self._streaming_threshold,
            "memory_config": {
                "max_memory_mb": self.memory_config.max_memory_mb,
                "cache_size_mb": self.memory_config.cache_size_mb,
                "memory_strategy": self.memory_config.memory_strategy.value,
            },
        }

        # Add batch processor metrics if available
        if hasattr(self, "memory_batch_processor"):
            db_metrics["batch_processor"] = (
                self.memory_batch_processor.get_memory_statistics()
            )

        return {**base_report, "database_metrics": db_metrics}


class MemoryProfiler:
    """
    Memory profiler for analyzing memory usage patterns in the InkedUp bot.

    Provides detailed analysis of memory allocation, peak usage, and optimization opportunities.
    """

    def __init__(self):
        self.profiling_active = False
        self.profile_data = []
        self._start_time = None
        self._baseline_memory = None

    def start_profiling(self, label: str = "default"):
        """Start memory profiling session."""
        if not self.profiling_active:
            self.profiling_active = True
            self._start_time = time.time()
            self._baseline_memory = memory_optimizer.monitor.get_current_metrics()

            logger.info(f"Started memory profiling session: {label}")

    def stop_profiling(self) -> dict[str, Any]:
        """Stop profiling and return analysis."""
        if not self.profiling_active:
            return {}

        self.profiling_active = False
        end_time = time.time()
        end_memory = memory_optimizer.monitor.get_current_metrics()

        # Calculate statistics
        duration = end_time - self._start_time
        memory_delta = (
            end_memory.process_memory_mb - self._baseline_memory.process_memory_mb
        )

        analysis = {
            "duration_seconds": duration,
            "baseline_memory_mb": self._baseline_memory.process_memory_mb,
            "final_memory_mb": end_memory.process_memory_mb,
            "memory_delta_mb": memory_delta,
            "peak_memory_mb": (
                max(record.get("memory_mb", 0) for record in self.profile_data)
                if self.profile_data
                else end_memory.process_memory_mb
            ),
            "memory_efficiency": memory_delta / duration if duration > 0 else 0,
            "profile_points": len(self.profile_data),
        }

        # Clear profile data
        self.profile_data.clear()

        logger.info(
            f"Memory profiling completed: {memory_delta:.2f} MB delta over {duration:.2f}s"
        )
        return analysis

    def record_point(self, label: str, metadata: dict | None = None):
        """Record a profiling point."""
        if self.profiling_active:
            current_memory = memory_optimizer.monitor.get_current_metrics()

            point = {
                "timestamp": time.time(),
                "label": label,
                "memory_mb": current_memory.process_memory_mb,
                "memory_percent": current_memory.memory_percent,
                "metadata": metadata or {},
            }

            self.profile_data.append(point)


# Global memory profiler instance
memory_profiler = MemoryProfiler()
