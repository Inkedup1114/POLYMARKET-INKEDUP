#!/usr/bin/env python3
"""
Comprehensive Test Suite for Memory Optimization System

This module tests all memory optimization components including:
- Memory-efficient data structures
- Memory monitoring and profiling
- Memory-aware batch processing
- Streaming data processors
- Memory optimization recommendations
"""

import gc
import os
import sys
from datetime import datetime

import pytest

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from inkedup_bot.memory_aware_processor import (
    MemoryAwareBatchProcessor,
    MemoryAwareConfig,
    MemoryStrategy,
    memory_profiler,
)
from inkedup_bot.memory_optimizer import (
    CircularBuffer,
    MemoryEfficientCache,
    MemoryPool,
    MemoryPriority,
    memory_optimizer,
)
from inkedup_bot.streaming_processor import (
    MemoryAwareAggregator,
    MemoryEfficientIterator,
    ProcessingStrategy,
    StreamingConfig,
    StreamingDataProcessor,
)


class TestMemoryEfficientDataStructures:
    """Test memory-efficient data structures."""

    def test_memory_efficient_cache_basic_operations(self):
        """Test basic cache operations."""
        cache = MemoryEfficientCache(max_size=100, max_memory_mb=10.0)

        # Test put and get
        assert cache.put("key1", "value1", MemoryPriority.NORMAL)
        assert cache.get("key1") == "value1"

        # Test cache miss
        assert cache.get("nonexistent") is None

        # Test memory info
        info = cache.get_memory_info()
        assert info["total_items"] == 1
        assert info["total_memory_mb"] > 0

    def test_memory_efficient_cache_eviction(self):
        """Test LRU eviction with priority consideration."""
        cache = MemoryEfficientCache(max_size=3, max_memory_mb=1.0)

        # Fill cache
        cache.put("low1", "value1", MemoryPriority.LOW)
        cache.put("normal1", "value2", MemoryPriority.NORMAL)
        cache.put("high1", "value3", MemoryPriority.HIGH)

        # Add one more item - should evict lowest priority item
        cache.put("normal2", "value4", MemoryPriority.NORMAL)

        # Low priority item should be evicted
        assert cache.get("low1") is None
        assert cache.get("normal1") == "value2"
        assert cache.get("high1") == "value3"
        assert cache.get("normal2") == "value4"

    def test_circular_buffer_operations(self):
        """Test circular buffer functionality."""
        buffer = CircularBuffer(3)

        # Test append and iteration
        buffer.append("item1")
        buffer.append("item2")
        buffer.append("item3")

        items = list(buffer)
        assert items == ["item1", "item2", "item3"]
        assert len(buffer) == 3

        # Test overwrite when full
        buffer.append("item4")
        items = list(buffer)
        assert items == ["item2", "item3", "item4"]
        assert len(buffer) == 3

    def test_circular_buffer_recent_items(self):
        """Test getting recent items from circular buffer."""
        buffer = CircularBuffer(5)

        for i in range(7):
            buffer.append(f"item{i}")

        # Get recent items
        recent = buffer.get_recent(3)
        assert recent == ["item4", "item5", "item6"]

        # Get more items than available
        all_items = buffer.get_recent(10)
        assert len(all_items) == 5
        assert all_items == ["item2", "item3", "item4", "item5", "item6"]

    def test_memory_pool_reuse(self):
        """Test memory pool object reuse."""

        def create_dict():
            return {"data": None, "processed": False}

        pool = MemoryPool(create_dict, max_size=5)

        # Get objects from pool
        obj1 = pool.get()
        obj2 = pool.get()

        # Modify objects
        obj1["data"] = "test1"
        obj2["data"] = "test2"

        # Return to pool
        pool.put(obj1)
        pool.put(obj2)

        # Get objects again - should be reused
        obj3 = pool.get()
        obj4 = pool.get()

        # Check stats
        stats = pool.get_stats()
        assert stats["reused_count"] == 2
        assert stats["created_count"] == 2
        assert stats["reuse_rate"] > 0


class TestMemoryMonitoring:
    """Test memory monitoring and alerting system."""

    def setup_method(self):
        """Setup test fixtures."""
        if not memory_optimizer._initialized:
            memory_optimizer.initialize()

    def teardown_method(self):
        """Cleanup after tests."""
        # Don't shutdown as other tests might need it
        pass

    def test_memory_monitor_initialization(self):
        """Test memory monitor initialization."""
        monitor = memory_optimizer.monitor

        # Should be initialized
        assert monitor is not None

        # Get current metrics
        metrics = monitor.get_current_metrics()
        assert metrics.total_memory_mb > 0
        assert metrics.process_memory_mb > 0
        assert 0 <= metrics.memory_percent <= 100

    def test_memory_optimizer_cache_creation(self):
        """Test cache creation and management."""
        cache = memory_optimizer.create_cache("test_cache", max_size=100)

        assert "test_cache" in memory_optimizer.caches
        assert cache is not None

        # Test cache operations
        cache.put("test_key", "test_value")
        assert cache.get("test_key") == "test_value"

    def test_memory_optimizer_pool_creation(self):
        """Test memory pool creation."""
        pool = memory_optimizer.create_pool(
            "test_pool", factory=lambda: {"test": True}, max_size=50
        )

        assert "test_pool" in memory_optimizer.pools
        assert pool is not None

        # Test pool operations
        obj = pool.get()
        assert obj["test"] is True
        pool.put(obj)

    def test_memory_report_generation(self):
        """Test memory report generation."""
        report = memory_optimizer.get_memory_report()

        assert "timestamp" in report
        assert "system_metrics" in report
        assert "caches" in report
        assert "pools" in report
        assert "gc_stats" in report

        # Check system metrics
        system_metrics = report["system_metrics"]
        assert system_metrics["total_memory_mb"] > 0
        assert system_metrics["process_memory_mb"] > 0


class TestStreamingProcessors:
    """Test streaming data processors for memory efficiency."""

    @pytest.mark.asyncio
    async def test_streaming_data_processor_streaming_mode(self):
        """Test streaming mode processing."""

        class MockProcessor:
            async def process(self, item):
                return item * 2

            async def process_batch(self, items):
                return [item * 2 for item in items]

        config = StreamingConfig(
            strategy=ProcessingStrategy.STREAMING, memory_limit_mb=10.0
        )

        processor = StreamingDataProcessor(config, MockProcessor())

        # Create test data stream
        async def data_generator():
            for i in range(10):
                yield i

        # Process stream
        results = []
        async for result in processor.process_stream(data_generator()):
            results.append(result)

        assert results == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]

        # Check metrics
        metrics = processor.get_metrics()
        assert metrics["items_processed"] == 10
        assert metrics["errors"] == 0

    @pytest.mark.asyncio
    async def test_streaming_data_processor_batch_mode(self):
        """Test batch mode processing."""

        class MockProcessor:
            async def process(self, item):
                return item * 2

            async def process_batch(self, items):
                return [item * 2 for item in items]

        config = StreamingConfig(
            strategy=ProcessingStrategy.BATCH, batch_size=3, memory_limit_mb=10.0
        )

        processor = StreamingDataProcessor(config, MockProcessor())

        # Create test data stream
        async def data_generator():
            for i in range(7):
                yield i

        # Process stream
        results = []
        async for batch_result in processor.process_stream(data_generator()):
            results.extend(batch_result)

        assert results == [0, 2, 4, 6, 8, 10, 12]

    def test_memory_efficient_iterator(self):
        """Test memory-efficient iterator."""

        # Test with list data source
        data = list(range(100))
        iterator = MemoryEfficientIterator(data, chunk_size=10)

        # Consume iterator
        results = list(iterator)
        assert results == data

        # Test with generator function
        def data_generator():
            for i in range(50):
                yield i * 2

        iterator = MemoryEfficientIterator(data_generator, chunk_size=5)
        results = list(iterator)
        expected = [i * 2 for i in range(50)]
        assert results == expected

    @pytest.mark.asyncio
    async def test_memory_aware_aggregator(self):
        """Test memory-aware aggregation."""
        aggregator = MemoryAwareAggregator(max_memory_mb=1.0)

        # Add aggregator functions
        aggregator.add_aggregator("sum", sum)
        aggregator.add_aggregator("count", len)
        aggregator.add_aggregator("max", max)

        # Create data stream
        async def data_generator():
            for i in range(100):
                yield i

        # Perform aggregation
        results = await aggregator.aggregate(data_generator())

        # Note: These are partial results that need to be combined
        assert "sum" in results
        assert "count" in results
        assert "max" in results


class TestMemoryAwareProcessing:
    """Test memory-aware batch processing."""

    def setup_method(self):
        """Setup test fixtures."""
        if not memory_optimizer._initialized:
            memory_optimizer.initialize()

    def test_memory_aware_config(self):
        """Test memory-aware configuration."""
        config = MemoryAwareConfig(
            max_memory_mb=256.0,
            memory_threshold=0.7,
            memory_strategy=MemoryStrategy.BALANCED,
        )

        assert config.max_memory_mb == 256.0
        assert config.memory_threshold == 0.7
        assert config.memory_strategy == MemoryStrategy.BALANCED

    @pytest.mark.asyncio
    async def test_memory_profiler_basic_usage(self):
        """Test basic memory profiler usage."""
        profiler = memory_profiler

        # Start profiling
        profiler.start_profiling("test_session")

        # Simulate some memory usage
        data = [i for i in range(10000)]

        # Take a snapshot
        snapshot = profiler.take_snapshot(
            "after_allocation", {"operation": "list_creation"}
        )

        assert snapshot.label == "after_allocation"
        assert snapshot.process_memory_mb > 0
        assert snapshot.metadata["operation"] == "list_creation"

        # Clean up
        del data
        gc.collect()

        # Stop profiling
        analysis = profiler.stop_profiling()

        assert "duration_seconds" in analysis
        assert analysis["duration_seconds"] > 0


class TestMemoryProfiling:
    """Test advanced memory profiling capabilities."""

    def test_advanced_memory_profiler_initialization(self):
        """Test advanced profiler initialization."""
        from inkedup_bot.memory_profiler import AdvancedMemoryProfiler, ProfileMode

        profiler = AdvancedMemoryProfiler(ProfileMode.STANDARD)
        assert profiler.mode == ProfileMode.STANDARD
        assert not profiler.profiling_active

    def test_memory_snapshot_creation(self):
        """Test memory snapshot creation."""
        from inkedup_bot.memory_profiler import AdvancedMemoryProfiler

        profiler = AdvancedMemoryProfiler()
        snapshot = profiler.take_snapshot("test_snapshot")

        assert snapshot.label == "test_snapshot"
        assert snapshot.process_memory_mb > 0
        assert snapshot.objects_count > 0
        assert isinstance(snapshot.timestamp, datetime)

    def test_memory_optimization_recommendations(self):
        """Test optimization recommendation generation."""
        from inkedup_bot.memory_profiler import AdvancedMemoryProfiler

        profiler = AdvancedMemoryProfiler()
        profiler.start_profiling("recommendation_test")

        # Simulate memory usage patterns
        for i in range(5):
            data = [j for j in range(1000)]  # Create some objects
            profiler.take_snapshot(f"iteration_{i}")
            del data

        analysis = profiler.stop_profiling()

        assert "optimization_recommendations" in analysis
        recommendations = analysis["optimization_recommendations"]

        # Should have some recommendations
        assert isinstance(recommendations, list)

        # Check recommendation structure
        if recommendations:
            rec = recommendations[0]
            assert "category" in rec
            assert "priority" in rec
            assert "description" in rec


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple memory optimization features."""

    def setup_method(self):
        """Setup test fixtures."""
        if not memory_optimizer._initialized:
            memory_optimizer.initialize()

    @pytest.mark.asyncio
    async def test_memory_optimized_batch_processing(self):
        """Test complete memory-optimized batch processing workflow."""
        from inkedup_bot.batch_processor import BatchConfig

        # Create memory-aware configuration
        memory_config = MemoryAwareConfig(
            max_memory_mb=128.0,
            memory_strategy=MemoryStrategy.ADAPTIVE,
            use_object_pooling=True,
        )

        batch_config = BatchConfig(max_batch_size=1000)

        # Create memory-aware batch processor
        processor = MemoryAwareBatchProcessor(batch_config, memory_config)

        # Test memory statistics
        stats = processor.get_memory_statistics()

        assert "current_memory_mb" in stats
        assert "memory_strategy" in stats
        assert stats["memory_strategy"] == "adaptive"

        # Test adaptive batch sizing
        assert "adaptive_batch_sizes" in stats

    def test_memory_pressure_simulation(self):
        """Test system behavior under memory pressure."""

        # Create a cache that will trigger memory pressure
        cache = memory_optimizer.create_cache("pressure_test", max_memory_mb=1.0)

        # Fill cache with data to simulate memory pressure
        for i in range(100):
            large_data = "x" * 10000  # 10KB string
            cache.put(f"key_{i}", large_data, MemoryPriority.LOW)

        # Cache should have evicted items due to memory limits
        cache_info = cache.get_memory_info()
        assert cache_info["total_items"] < 100  # Some items should be evicted

    @pytest.mark.asyncio
    async def test_streaming_with_memory_monitoring(self):
        """Test streaming processing with memory monitoring."""

        class MemoryTrackingProcessor:
            def __init__(self):
                self.memory_snapshots = []

            async def process(self, item):
                # Take memory snapshot during processing
                metrics = memory_optimizer.monitor.get_current_metrics()
                self.memory_snapshots.append(metrics.process_memory_mb)
                return item * 2

            async def process_batch(self, items):
                results = []
                for item in items:
                    result = await self.process(item)
                    results.append(result)
                return results

        config = StreamingConfig(
            strategy=ProcessingStrategy.STREAMING, memory_limit_mb=50.0
        )

        tracking_processor = MemoryTrackingProcessor()
        processor = StreamingDataProcessor(config, tracking_processor)

        # Create data stream
        async def data_generator():
            for i in range(10):
                yield i

        # Process with memory tracking
        results = []
        async for result in processor.process_stream(data_generator()):
            results.append(result)

        assert len(results) == 10
        assert len(tracking_processor.memory_snapshots) == 10

        # Verify memory was tracked during processing
        assert all(mem > 0 for mem in tracking_processor.memory_snapshots)

    def test_end_to_end_memory_optimization_workflow(self):
        """Test complete end-to-end memory optimization workflow."""
        from inkedup_bot.memory_profiler import AdvancedMemoryProfiler, ProfileMode

        # 1. Start advanced profiling
        profiler = AdvancedMemoryProfiler(ProfileMode.STANDARD)
        profiler.start_profiling("e2e_test")

        # 2. Create memory-optimized components
        cache = memory_optimizer.create_cache("e2e_cache", max_memory_mb=10.0)
        pool = memory_optimizer.create_pool("e2e_pool", lambda: {"data": None})

        # 3. Simulate typical operations
        profiler.take_snapshot("after_initialization")

        # Cache operations
        for i in range(100):
            cache.put(f"key_{i}", f"value_{i}", MemoryPriority.NORMAL)

        profiler.take_snapshot("after_cache_operations")

        # Pool operations
        objects = []
        for i in range(50):
            obj = pool.get()
            obj["data"] = f"data_{i}"
            objects.append(obj)

        profiler.take_snapshot("after_pool_allocation")

        # Return objects to pool
        for obj in objects:
            pool.put(obj)
        objects.clear()

        profiler.take_snapshot("after_pool_cleanup")

        # 4. Stop profiling and analyze
        analysis = profiler.stop_profiling()

        # Verify analysis contains expected components
        assert "session_summary" in analysis
        assert "memory_trend" in analysis
        assert "optimization_recommendations" in analysis

        # Verify we have multiple snapshots
        session_summary = analysis["session_summary"]
        assert session_summary["snapshots_taken"] >= 4

        # 5. Generate memory report
        memory_report = memory_optimizer.get_memory_report()

        assert "e2e_cache" in memory_report["caches"]
        assert "e2e_pool" in memory_report["pools"]

        # 6. Verify pool reuse efficiency
        pool_stats = pool.get_stats()
        assert pool_stats["reused_count"] > 0
        assert pool_stats["reuse_rate"] > 0

        print("E2E Test Results:")
        print(f"  - Snapshots taken: {session_summary['snapshots_taken']}")
        print(f"  - Memory delta: {session_summary['memory_delta_mb']:.2f} MB")
        print(f"  - Pool reuse rate: {pool_stats['reuse_rate']:.2%}")
        print(f"  - Cache items: {cache.get_memory_info()['total_items']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
