#!/usr/bin/env python3
"""
Memory Optimization Demonstration for InkedUp Bot

This demonstration showcases the memory optimization capabilities including:
- Memory-efficient data structures
- Memory monitoring and profiling
- Memory-aware batch processing
- Performance comparisons between optimized and standard approaches
"""

import asyncio
import gc
import logging
import os
import random
import sys
import time
from datetime import datetime
from typing import Any

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inkedup_bot.memory_aware_processor import (
    MemoryAwareBatchProcessor,
    MemoryAwareConfig,
    MemoryStrategy,
)
from inkedup_bot.memory_optimizer import (
    CircularBuffer,
    MemoryEfficientCache,
    MemoryPool,
    MemoryPriority,
    memory_optimizer,
)
from inkedup_bot.memory_profiler import AdvancedMemoryProfiler, ProfileMode
from inkedup_bot.streaming_processor import (
    MemoryEfficientIterator,
    ProcessingStrategy,
    StreamingConfig,
    StreamingDataProcessor,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MemoryOptimizationDemo:
    """Comprehensive memory optimization demonstration."""

    def __init__(self):
        self.results = {}
        self.profiler = AdvancedMemoryProfiler(ProfileMode.STANDARD)

        # Initialize memory optimizer
        if not memory_optimizer._initialized:
            memory_optimizer.initialize()

    async def run_complete_demo(self) -> dict[str, Any]:
        """Run complete memory optimization demonstration."""

        print("🚀 MEMORY OPTIMIZATION DEMONSTRATION")
        print("=" * 60)

        # Start comprehensive profiling
        self.profiler.start_profiling("complete_demo")

        try:
            # 1. Data Structure Efficiency Demo
            print("\n1️⃣  MEMORY-EFFICIENT DATA STRUCTURES")
            print("-" * 50)
            await self._demo_data_structures()

            # 2. Memory Monitoring Demo
            print("\n2️⃣  MEMORY MONITORING AND ALERTING")
            print("-" * 50)
            await self._demo_memory_monitoring()

            # 3. Streaming Processing Demo
            print("\n3️⃣  MEMORY-EFFICIENT STREAMING PROCESSING")
            print("-" * 50)
            await self._demo_streaming_processing()

            # 4. Memory-Aware Batch Processing Demo
            print("\n4️⃣  MEMORY-AWARE BATCH PROCESSING")
            print("-" * 50)
            await self._demo_memory_aware_batching()

            # 5. Performance Comparison
            print("\n5️⃣  PERFORMANCE COMPARISON")
            print("-" * 50)
            await self._demo_performance_comparison()

            # 6. Memory Leak Detection Demo
            print("\n6️⃣  MEMORY LEAK DETECTION")
            print("-" * 50)
            await self._demo_leak_detection()

        except Exception as e:
            logger.error(f"Demo error: {e}")

        finally:
            # Stop profiling and get analysis
            analysis = self.profiler.stop_profiling()
            self.results["profiling_analysis"] = analysis

            # Generate final report
            await self._generate_final_report()

        return self.results

    async def _demo_data_structures(self):
        """Demonstrate memory-efficient data structures."""

        print("Testing Memory-Efficient Cache...")

        # Standard dictionary vs Memory-Efficient Cache comparison
        start_memory = self._get_memory_mb()

        # Create standard dictionary
        standard_dict = {}
        for i in range(10000):
            standard_dict[f"key_{i}"] = f"value_{i}" * 10  # ~100 chars per value

        dict_memory = self._get_memory_mb() - start_memory
        print(f"  Standard dict: {dict_memory:.2f} MB, {len(standard_dict)} items")

        # Clear for fair comparison
        del standard_dict
        gc.collect()

        start_memory = self._get_memory_mb()

        # Create memory-efficient cache
        cache = MemoryEfficientCache(max_size=10000, max_memory_mb=50.0)
        cache_items = 0

        for i in range(10000):
            if cache.put(f"key_{i}", f"value_{i}" * 10, MemoryPriority.NORMAL):
                cache_items += 1

        cache_memory = self._get_memory_mb() - start_memory
        cache_info = cache.get_memory_info()

        print(
            f"  Memory cache: {cache_memory:.2f} MB, {cache_info['total_items']} items"
        )
        print(f"  Memory efficiency: {cache_items / cache_memory:.1f} items/MB")

        self.results["data_structures"] = {
            "standard_dict_memory_mb": dict_memory,
            "cache_memory_mb": cache_memory,
            "cache_items": cache_info["total_items"],
            "memory_efficiency": cache_items / cache_memory if cache_memory > 0 else 0,
        }

        print("\nTesting Circular Buffer...")

        # Standard list vs Circular Buffer
        standard_list = []
        for i in range(100000):
            standard_list.append(f"item_{i}")
            if len(standard_list) > 1000:  # Keep only last 1000
                standard_list.pop(0)

        list_memory = self._get_memory_mb() - cache_memory

        # Circular buffer
        buffer = CircularBuffer(1000)
        for i in range(100000):
            buffer.append(f"item_{i}")

        buffer_memory = self._get_memory_mb() - list_memory - cache_memory

        print(f"  Standard list (manual truncation): {list_memory:.2f} MB")
        print(f"  Circular buffer: {buffer_memory:.2f} MB")
        print(
            f"  Memory savings: {((list_memory - buffer_memory) / list_memory * 100):.1f}%"
        )

        # Test object pool
        print("\nTesting Object Pool...")

        def create_order_dict():
            return {
                "id": None,
                "price": 0.0,
                "size": 0.0,
                "side": "buy",
                "status": "pending",
                "metadata": {},
            }

        pool = MemoryPool(create_order_dict, max_size=1000)

        # Simulate object usage
        objects = []
        for i in range(2000):
            obj = pool.get()
            obj["id"] = i
            obj["price"] = random.uniform(0.1, 1.0)
            objects.append(obj)

            # Return half the objects back to pool
            if len(objects) > 1000:
                returned_obj = objects.pop(0)
                returned_obj["id"] = None  # Reset
                pool.put(returned_obj)

        pool_stats = pool.get_stats()
        print(f"  Objects created: {pool_stats['created_count']}")
        print(f"  Objects reused: {pool_stats['reused_count']}")
        print(f"  Reuse efficiency: {pool_stats['reuse_rate']:.1%}")

        self.results["data_structures"]["pool_reuse_rate"] = pool_stats["reuse_rate"]

    async def _demo_memory_monitoring(self):
        """Demonstrate memory monitoring capabilities."""

        print("Starting Memory Monitor...")

        # Get current memory status
        metrics = memory_optimizer.monitor.get_current_metrics()
        print(f"  Current process memory: {metrics.process_memory_mb:.2f} MB")
        print(f"  System memory usage: {metrics.memory_percent:.1f}%")
        print(f"  Memory threshold level: {metrics.threshold_level.value}")
        print(f"  Python objects: {metrics.objects_count:,}")

        # Simulate memory pressure
        print("\nSimulating memory pressure...")

        large_objects = []
        for i in range(5):
            # Create large object
            large_obj = ["x" * 1000] * 1000  # ~1MB object
            large_objects.append(large_obj)

            # Take snapshot
            new_metrics = memory_optimizer.monitor.get_current_metrics()
            print(
                f"  Step {i+1}: {new_metrics.process_memory_mb:.2f} MB "
                f"(+{new_metrics.process_memory_mb - metrics.process_memory_mb:.2f} MB)"
            )

        # Clean up
        del large_objects
        gc.collect()

        final_metrics = memory_optimizer.monitor.get_current_metrics()
        print(f"  After cleanup: {final_metrics.process_memory_mb:.2f} MB")

        self.results["memory_monitoring"] = {
            "initial_memory_mb": metrics.process_memory_mb,
            "peak_memory_mb": new_metrics.process_memory_mb,
            "final_memory_mb": final_metrics.process_memory_mb,
            "gc_effectiveness": new_metrics.process_memory_mb
            - final_metrics.process_memory_mb,
        }

    async def _demo_streaming_processing(self):
        """Demonstrate streaming processing for memory efficiency."""

        print("Testing Streaming Data Processor...")

        class DataProcessor:
            def __init__(self):
                self.processed_count = 0

            async def process(self, item):
                self.processed_count += 1
                # Simulate processing
                return {
                    "id": item["id"],
                    "result": item["value"] * 2,
                    "processed_at": datetime.now(),
                }

            async def process_batch(self, items):
                results = []
                for item in items:
                    result = await self.process(item)
                    results.append(result)
                return results

        # Test different processing strategies
        strategies = [
            (ProcessingStrategy.STREAMING, "One-by-one processing"),
            (ProcessingStrategy.BATCH, "Batch processing"),
            (ProcessingStrategy.CHUNKED, "Memory-limited chunks"),
        ]

        for strategy, description in strategies:
            print(f"\n  Testing {description}...")

            config = StreamingConfig(
                strategy=strategy, batch_size=1000, memory_limit_mb=10.0
            )

            processor_impl = DataProcessor()
            streaming_processor = StreamingDataProcessor(config, processor_impl)

            # Generate large dataset
            async def data_generator():
                for i in range(10000):
                    yield {"id": i, "value": random.randint(1, 100)}

            start_memory = self._get_memory_mb()
            start_time = time.time()

            results = []
            async for result in streaming_processor.process_stream(data_generator()):
                if isinstance(result, list):
                    results.extend(result)
                else:
                    results.append(result)

            end_time = time.time()
            end_memory = self._get_memory_mb()

            metrics = streaming_processor.get_metrics()

            print(f"    Processed {len(results)} items in {end_time - start_time:.2f}s")
            print(f"    Memory usage: {end_memory - start_memory:.2f} MB")
            print(
                f"    Throughput: {len(results) / (end_time - start_time):.0f} items/sec"
            )

            if strategy.value not in self.results:
                self.results[strategy.value] = {}

            self.results[strategy.value].update(
                {
                    "items_processed": len(results),
                    "processing_time_sec": end_time - start_time,
                    "memory_usage_mb": end_memory - start_memory,
                    "throughput": len(results) / (end_time - start_time),
                }
            )

    async def _demo_memory_aware_batching(self):
        """Demonstrate memory-aware batch processing."""

        print("Testing Memory-Aware Batch Processing...")

        from inkedup_bot.batch_processor import BatchConfig

        # Create different memory strategies
        strategies = [
            (MemoryStrategy.CONSERVATIVE, "Conservative (minimize memory)"),
            (MemoryStrategy.BALANCED, "Balanced (memory vs performance)"),
            (MemoryStrategy.ADAPTIVE, "Adaptive (adjust to conditions)"),
        ]

        for strategy, description in strategies:
            print(f"\n  Testing {description}...")

            memory_config = MemoryAwareConfig(
                max_memory_mb=64.0, memory_strategy=strategy, use_object_pooling=True
            )

            batch_config = BatchConfig(max_batch_size=2000)

            processor = MemoryAwareBatchProcessor(batch_config, memory_config)

            # Get initial statistics
            initial_stats = processor.get_memory_statistics()
            print(f"    Initial memory: {initial_stats['current_memory_mb']:.2f} MB")
            print(f"    Memory utilization: {initial_stats['memory_utilization']:.1%}")

            # Simulate batch operations
            start_time = time.time()

            for i in range(5):
                # Create batch operations (simulate order data)
                operations = []
                for j in range(1000):
                    op_data = {
                        "id": f"order_{i}_{j}",
                        "price": random.uniform(0.1, 1.0),
                        "size": random.uniform(10, 1000),
                        "side": random.choice(["buy", "sell"]),
                        "timestamp": datetime.now().isoformat(),
                    }
                    operations.append(op_data)

                # Process batch (simulated)
                await asyncio.sleep(0.01)  # Simulate processing time

            end_time = time.time()
            final_stats = processor.get_memory_statistics()

            print(f"    Processing time: {end_time - start_time:.2f}s")
            print(f"    Final memory: {final_stats['current_memory_mb']:.2f} MB")
            print(
                f"    Memory delta: {final_stats['current_memory_mb'] - initial_stats['current_memory_mb']:+.2f} MB"
            )

            # Check adaptive batch sizes
            if "adaptive_batch_sizes" in final_stats:
                print(
                    f"    Adaptive batch sizes: {final_stats['adaptive_batch_sizes']}"
                )

            self.results[f"batch_{strategy.value}"] = {
                "processing_time_sec": end_time - start_time,
                "memory_delta_mb": final_stats["current_memory_mb"]
                - initial_stats["current_memory_mb"],
                "final_memory_utilization": final_stats["memory_utilization"],
            }

    async def _demo_performance_comparison(self):
        """Compare performance between optimized and standard approaches."""

        print("Performance Comparison: Optimized vs Standard...")

        # Test 1: Large dataset processing
        print("\n  Test 1: Large Dataset Processing")

        dataset_size = 50000

        # Standard approach: Load all data into memory
        print("    Standard approach...")
        start_memory = self._get_memory_mb()
        start_time = time.time()

        standard_data = []
        for i in range(dataset_size):
            item = {"id": i, "data": f"item_{i}" * 10, "processed": False}  # ~100 chars
            standard_data.append(item)

        # Process all at once
        for item in standard_data:
            item["processed"] = True
            item["result"] = len(item["data"])

        standard_time = time.time() - start_time
        standard_memory = self._get_memory_mb() - start_memory

        print(f"      Time: {standard_time:.2f}s, Memory: {standard_memory:.2f} MB")

        # Clean up
        del standard_data
        gc.collect()

        # Optimized approach: Streaming with memory limits
        print("    Optimized approach...")
        start_memory = self._get_memory_mb()
        start_time = time.time()

        def data_generator():
            for i in range(dataset_size):
                yield {"id": i, "data": f"item_{i}" * 10, "processed": False}

        iterator = MemoryEfficientIterator(data_generator, chunk_size=1000)
        processed_count = 0

        for item in iterator:
            item["processed"] = True
            item["result"] = len(item["data"])
            processed_count += 1

        optimized_time = time.time() - start_time
        optimized_memory = self._get_memory_mb() - start_memory

        print(f"      Time: {optimized_time:.2f}s, Memory: {optimized_memory:.2f} MB")

        # Calculate improvements
        time_improvement = (standard_time - optimized_time) / standard_time * 100
        memory_improvement = (
            (standard_memory - optimized_memory) / standard_memory * 100
        )

        print("\n    Performance Improvement:")
        print(
            f"      Time: {time_improvement:+.1f}% ({'faster' if time_improvement > 0 else 'slower'})"
        )
        print(
            f"      Memory: {memory_improvement:+.1f}% ({'less' if memory_improvement > 0 else 'more'})"
        )

        self.results["performance_comparison"] = {
            "dataset_size": dataset_size,
            "standard_time_sec": standard_time,
            "standard_memory_mb": standard_memory,
            "optimized_time_sec": optimized_time,
            "optimized_memory_mb": optimized_memory,
            "time_improvement_percent": time_improvement,
            "memory_improvement_percent": memory_improvement,
        }

    async def _demo_leak_detection(self):
        """Demonstrate memory leak detection capabilities."""

        print("Memory Leak Detection Demo...")

        # Start detailed profiling for leak detection
        leak_profiler = AdvancedMemoryProfiler(ProfileMode.DETAILED)
        leak_profiler.start_profiling("leak_detection")

        # Simulate potential memory leak
        print("  Simulating potential memory leak...")

        # Create objects that might leak
        potential_leak_objects = []

        for i in range(10):
            leak_profiler.take_snapshot(f"iteration_{i}")

            # Create objects that grow over time
            batch = []
            for j in range(1000):
                obj = {"id": f"leak_{i}_{j}", "data": "x" * 100, "references": []}
                batch.append(obj)

            potential_leak_objects.append(batch)

            # Only clean up some objects (simulating leak)
            if i > 5 and len(potential_leak_objects) > 3:
                potential_leak_objects.pop(0)

        # Analyze for leaks
        analysis = leak_profiler.stop_profiling()

        print("  Analysis completed:")
        print(f"    Duration: {analysis['session_summary']['duration_seconds']:.1f}s")
        print(f"    Memory trend: {analysis['memory_trend']['trend']}")
        print(
            f"    Potential leaks found: {analysis['leak_analysis']['potential_leaks_found']}"
        )

        # Check for recommendations
        recommendations = analysis.get("optimization_recommendations", [])
        if recommendations:
            print("  Top recommendations:")
            for i, rec in enumerate(recommendations[:2], 1):
                print(f"    {i}. {rec['category']}: {rec['description'][:80]}...")

        # Clean up
        del potential_leak_objects
        gc.collect()

        self.results["leak_detection"] = {
            "potential_leaks": analysis["leak_analysis"]["potential_leaks_found"],
            "memory_trend": analysis["memory_trend"]["trend"],
            "recommendations_count": len(recommendations),
        }

    def _get_memory_mb(self) -> float:
        """Get current process memory usage in MB."""
        metrics = memory_optimizer.monitor.get_current_metrics()
        return metrics.process_memory_mb

    async def _generate_final_report(self):
        """Generate comprehensive final report."""

        print("\n📊 FINAL MEMORY OPTIMIZATION REPORT")
        print("=" * 60)

        # Memory usage summary
        profiling_analysis = self.results.get("profiling_analysis", {})
        session_summary = profiling_analysis.get("session_summary", {})

        print("\n🔍 PROFILING SUMMARY")
        print(
            f"  Total duration: {session_summary.get('duration_seconds', 0):.1f} seconds"
        )
        print(f"  Memory delta: {session_summary.get('memory_delta_mb', 0):+.2f} MB")
        print(f"  Peak memory: {session_summary.get('peak_memory_mb', 0):.2f} MB")
        print(f"  Snapshots taken: {session_summary.get('snapshots_taken', 0)}")

        # Data structure efficiency
        data_structures = self.results.get("data_structures", {})
        if data_structures:
            print("\n🏗️  DATA STRUCTURE EFFICIENCY")
            print(
                f"  Memory efficiency: {data_structures.get('memory_efficiency', 0):.1f} items/MB"
            )
            print(f"  Pool reuse rate: {data_structures.get('pool_reuse_rate', 0):.1%}")

        # Performance improvements
        perf_comparison = self.results.get("performance_comparison", {})
        if perf_comparison:
            print("\n⚡ PERFORMANCE IMPROVEMENTS")
            print(
                f"  Time improvement: {perf_comparison.get('time_improvement_percent', 0):+.1f}%"
            )
            print(
                f"  Memory improvement: {perf_comparison.get('memory_improvement_percent', 0):+.1f}%"
            )
            print(f"  Dataset size: {perf_comparison.get('dataset_size', 0):,} items")

        # Memory monitoring effectiveness
        monitoring = self.results.get("memory_monitoring", {})
        if monitoring:
            print("\n📈 MEMORY MONITORING")
            print(
                f"  GC effectiveness: {monitoring.get('gc_effectiveness', 0):.2f} MB freed"
            )
            print(
                f"  Peak memory reached: {monitoring.get('peak_memory_mb', 0):.2f} MB"
            )

        # Leak detection results
        leak_detection = self.results.get("leak_detection", {})
        if leak_detection:
            print("\n🔍 LEAK DETECTION")
            print(
                f"  Potential leaks found: {leak_detection.get('potential_leaks', 0)}"
            )
            print(f"  Memory trend: {leak_detection.get('memory_trend', 'unknown')}")
            print(
                f"  Optimization recommendations: {leak_detection.get('recommendations_count', 0)}"
            )

        # Generate comprehensive memory report
        memory_report = memory_optimizer.get_memory_report()

        print("\n🎯 SYSTEM MEMORY STATUS")
        system_metrics = memory_report["system_metrics"]
        print(f"  Process memory: {system_metrics['process_memory_mb']:.2f} MB")
        print(f"  Memory utilization: {system_metrics['memory_percent']:.1f}%")
        print(f"  Threshold level: {system_metrics['threshold_level']}")

        print("\n🗂️  MANAGED RESOURCES")
        print(f"  Active caches: {len(memory_report['caches'])}")
        print(f"  Active pools: {len(memory_report['pools'])}")

        # Optimization recommendations from profiling
        recommendations = profiling_analysis.get("optimization_recommendations", [])
        if recommendations:
            print("\n💡 OPTIMIZATION RECOMMENDATIONS")
            for i, rec in enumerate(recommendations[:3], 1):
                print(f"  {i}. {rec['category']} (Priority {rec['priority']})")
                print(f"     {rec['description']}")
                print(f"     Impact: {rec['impact_estimate']}")
                print()

        print("✅ Memory optimization demonstration completed successfully!")

        # Save detailed results
        self.results["final_memory_report"] = memory_report
        self.results["timestamp"] = datetime.now().isoformat()


async def main():
    """Main demonstration function."""

    print("Initializing Memory Optimization Demo...")

    demo = MemoryOptimizationDemo()

    try:
        results = await demo.run_complete_demo()

        print("\n🎉 DEMONSTRATION COMPLETED")
        print(f"Results saved with {len(results)} components analyzed")

        return results

    except KeyboardInterrupt:
        print("\n⏹️  Demo interrupted by user")
        return {}
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback

        traceback.print_exc()
        return {}
    finally:
        # Cleanup
        if memory_optimizer._initialized:
            print("\n🧹 Cleaning up memory optimizer...")
            # Don't shutdown completely as it may be used elsewhere


if __name__ == "__main__":
    asyncio.run(main())
