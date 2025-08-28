#!/usr/bin/env python3
"""
Performance Benchmarking Suite for InkedUp Bot

This module provides comprehensive performance benchmarking including:
- Memory usage profiling and leak detection
- CPU performance under load
- Response time analysis with percentiles
- Throughput measurements
- Resource utilization monitoring
- Performance regression testing
"""

import asyncio
import json
import logging
import statistics
import threading
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import psutil

logger = logging.getLogger("performance_benchmarks")


@dataclass
class BenchmarkResult:
    """Container for benchmark test results."""

    test_name: str
    start_time: float
    end_time: float
    duration_seconds: float

    # Performance metrics
    response_times_ms: list[float] = field(default_factory=list)
    throughput_ops_per_second: float = 0.0

    # Resource metrics
    memory_usage_mb: list[float] = field(default_factory=list)
    cpu_usage_percent: list[float] = field(default_factory=list)

    # Memory profiling
    memory_peak_mb: float = 0.0
    memory_growth_mb: float = 0.0
    memory_allocations: int = 0
    memory_deallocations: int = 0

    # Error tracking
    error_count: int = 0
    success_count: int = 0

    # Custom metrics
    custom_metrics: dict[str, Any] = field(default_factory=dict)

    def add_response_time(self, time_ms: float):
        """Add a response time measurement."""
        self.response_times_ms.append(time_ms)

    def record_success(self):
        """Record a successful operation."""
        self.success_count += 1

    def record_error(self):
        """Record a failed operation."""
        self.error_count += 1

    def set_custom_metric(self, key: str, value: Any):
        """Set a custom metric value."""
        self.custom_metrics[key] = value

    def get_summary(self) -> dict[str, Any]:
        """Generate comprehensive benchmark summary."""
        total_operations = self.success_count + self.error_count

        return {
            "test_info": {
                "name": self.test_name,
                "duration_seconds": self.duration_seconds,
                "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
                "end_time": datetime.fromtimestamp(self.end_time).isoformat(),
            },
            "performance": {
                "total_operations": total_operations,
                "success_rate_percent": (
                    (self.success_count / total_operations * 100)
                    if total_operations > 0
                    else 0
                ),
                "error_rate_percent": (
                    (self.error_count / total_operations * 100)
                    if total_operations > 0
                    else 0
                ),
                "throughput_ops_per_second": self.throughput_ops_per_second,
                "response_times": {
                    "count": len(self.response_times_ms),
                    "avg_ms": (
                        statistics.mean(self.response_times_ms)
                        if self.response_times_ms
                        else 0
                    ),
                    "median_ms": (
                        statistics.median(self.response_times_ms)
                        if self.response_times_ms
                        else 0
                    ),
                    "p95_ms": self._percentile(self.response_times_ms, 95),
                    "p99_ms": self._percentile(self.response_times_ms, 99),
                    "min_ms": (
                        min(self.response_times_ms) if self.response_times_ms else 0
                    ),
                    "max_ms": (
                        max(self.response_times_ms) if self.response_times_ms else 0
                    ),
                    "std_dev_ms": (
                        statistics.stdev(self.response_times_ms)
                        if len(self.response_times_ms) > 1
                        else 0
                    ),
                },
            },
            "resources": {
                "memory": {
                    "peak_mb": self.memory_peak_mb,
                    "growth_mb": self.memory_growth_mb,
                    "avg_usage_mb": (
                        statistics.mean(self.memory_usage_mb)
                        if self.memory_usage_mb
                        else 0
                    ),
                    "allocations": self.memory_allocations,
                    "deallocations": self.memory_deallocations,
                },
                "cpu": {
                    "avg_percent": (
                        statistics.mean(self.cpu_usage_percent)
                        if self.cpu_usage_percent
                        else 0
                    ),
                    "peak_percent": (
                        max(self.cpu_usage_percent) if self.cpu_usage_percent else 0
                    ),
                },
            },
            "custom_metrics": self.custom_metrics,
        }

    def _percentile(self, data: list[float], percentile: float) -> float:
        """Calculate percentile value."""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]


class PerformanceProfiler:
    """Comprehensive performance profiling utility."""

    def __init__(self):
        self.monitoring_active = False
        self.monitor_thread = None
        self.results = []

    def start_monitoring(self, interval_seconds: float = 0.1) -> None:
        """Start background performance monitoring."""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, args=(interval_seconds,), daemon=True
        )
        self.monitor_thread.start()
        logger.debug("Performance monitoring started")

    def stop_monitoring(self) -> None:
        """Stop background performance monitoring."""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)
        logger.debug("Performance monitoring stopped")

    def _monitor_loop(self, interval: float):
        """Background monitoring loop."""
        process = psutil.Process()

        while self.monitoring_active:
            try:
                # Record system metrics
                memory_mb = process.memory_info().rss / 1024 / 1024
                cpu_percent = process.cpu_percent()

                # Store in results if we have an active benchmark
                if self.results and len(self.results) > 0:
                    current_result = self.results[-1]
                    current_result.memory_usage_mb.append(memory_mb)
                    current_result.cpu_usage_percent.append(cpu_percent)

                time.sleep(interval)

            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                break

    async def benchmark(
        self,
        test_name: str,
        test_function: Callable,
        *args,
        duration_seconds: float | None = None,
        iterations: int | None = None,
        warmup_iterations: int = 0,
        **kwargs,
    ) -> BenchmarkResult:
        """
        Run a comprehensive benchmark of a function.

        Args:
            test_name: Name of the test for reporting
            test_function: Function to benchmark (can be sync or async)
            duration_seconds: Run for specified duration (mutually exclusive with iterations)
            iterations: Run for specified number of iterations
            warmup_iterations: Number of warmup iterations before timing
            *args, **kwargs: Arguments to pass to test_function
        """
        logger.info(f"🔬 Starting benchmark: {test_name}")

        if duration_seconds is None and iterations is None:
            raise ValueError("Must specify either duration_seconds or iterations")

        # Initialize benchmark result
        result = BenchmarkResult(
            test_name=test_name, start_time=time.time(), end_time=0, duration_seconds=0
        )
        self.results.append(result)

        # Start memory profiling
        tracemalloc.start()
        initial_memory_snapshot = tracemalloc.take_snapshot()
        initial_memory_mb = psutil.Process().memory_info().rss / 1024 / 1024

        # Start performance monitoring
        self.start_monitoring()

        try:
            # Warmup phase
            if warmup_iterations > 0:
                logger.debug(f"Running {warmup_iterations} warmup iterations...")
                for i in range(warmup_iterations):
                    if asyncio.iscoroutinefunction(test_function):
                        await test_function(*args, **kwargs)
                    else:
                        test_function(*args, **kwargs)

            # Main benchmark phase
            start_time = time.time()
            operations_completed = 0

            if duration_seconds:
                # Duration-based benchmark
                end_time = start_time + duration_seconds

                while time.time() < end_time:
                    op_start = time.time()

                    try:
                        if asyncio.iscoroutinefunction(test_function):
                            await test_function(*args, **kwargs)
                        else:
                            test_function(*args, **kwargs)

                        op_time = (time.time() - op_start) * 1000
                        result.add_response_time(op_time)
                        result.record_success()

                    except Exception as e:
                        logger.error(f"Benchmark operation failed: {e}")
                        result.record_error()

                    operations_completed += 1

            else:
                # Iteration-based benchmark
                for i in range(iterations):
                    op_start = time.time()

                    try:
                        if asyncio.iscoroutinefunction(test_function):
                            await test_function(*args, **kwargs)
                        else:
                            test_function(*args, **kwargs)

                        op_time = (time.time() - op_start) * 1000
                        result.add_response_time(op_time)
                        result.record_success()

                    except Exception as e:
                        logger.error(f"Benchmark operation failed: {e}")
                        result.record_error()

                    operations_completed += 1

            # Calculate final metrics
            actual_duration = time.time() - start_time
            result.end_time = time.time()
            result.duration_seconds = actual_duration
            result.throughput_ops_per_second = (
                operations_completed / actual_duration if actual_duration > 0 else 0
            )

            # Memory profiling results
            final_memory_snapshot = tracemalloc.take_snapshot()
            final_memory_mb = psutil.Process().memory_info().rss / 1024 / 1024

            result.memory_peak_mb = (
                max(result.memory_usage_mb)
                if result.memory_usage_mb
                else final_memory_mb
            )
            result.memory_growth_mb = final_memory_mb - initial_memory_mb

            # Memory allocation statistics
            top_stats = final_memory_snapshot.compare_to(
                initial_memory_snapshot, "lineno"
            )
            result.memory_allocations = len(
                [stat for stat in top_stats if stat.size_diff > 0]
            )
            result.memory_deallocations = len(
                [stat for stat in top_stats if stat.size_diff < 0]
            )

        finally:
            self.stop_monitoring()
            tracemalloc.stop()

        logger.info(
            f"✅ Benchmark completed: {test_name} - "
            f"{result.success_count} ops in {result.duration_seconds:.2f}s "
            f"({result.throughput_ops_per_second:.2f} ops/s)"
        )

        return result


class MemoryLeakDetector:
    """Utility for detecting memory leaks during load testing."""

    def __init__(self):
        self.snapshots = []
        self.monitoring = False

    def start_monitoring(self, interval_seconds: float = 10.0):
        """Start memory leak monitoring."""
        if not self.monitoring:
            tracemalloc.start()
            self.monitoring = True
            asyncio.create_task(self._monitoring_loop(interval_seconds))
            logger.info("Memory leak monitoring started")

    def stop_monitoring(self):
        """Stop memory leak monitoring."""
        if self.monitoring:
            self.monitoring = False
            tracemalloc.stop()
            logger.info("Memory leak monitoring stopped")

    async def _monitoring_loop(self, interval: float):
        """Background memory monitoring loop."""
        while self.monitoring:
            try:
                snapshot = tracemalloc.take_snapshot()
                self.snapshots.append(
                    {
                        "timestamp": time.time(),
                        "snapshot": snapshot,
                        "memory_mb": psutil.Process().memory_info().rss / 1024 / 1024,
                    }
                )

                # Keep only last 20 snapshots to avoid memory issues
                if len(self.snapshots) > 20:
                    self.snapshots.pop(0)

                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Memory monitoring error: {e}")
                break

    def analyze_leaks(self) -> dict[str, Any]:
        """Analyze collected snapshots for memory leaks."""
        if len(self.snapshots) < 2:
            return {"error": "Need at least 2 snapshots for leak analysis"}

        # Compare first and last snapshots
        first_snapshot = self.snapshots[0]["snapshot"]
        last_snapshot = self.snapshots[-1]["snapshot"]

        # Calculate memory growth
        first_memory = self.snapshots[0]["memory_mb"]
        last_memory = self.snapshots[-1]["memory_mb"]
        memory_growth = last_memory - first_memory

        # Analyze top memory differences
        top_stats = last_snapshot.compare_to(first_snapshot, "lineno")

        # Find potential leaks (allocations that grew significantly)
        potential_leaks = []
        for stat in top_stats[:10]:  # Top 10 differences
            if stat.size_diff > 1024 * 1024:  # More than 1MB growth
                potential_leaks.append(
                    {
                        "traceback": str(stat.traceback),
                        "size_diff_mb": stat.size_diff / 1024 / 1024,
                        "count_diff": stat.count_diff,
                    }
                )

        return {
            "analysis_period_seconds": self.snapshots[-1]["timestamp"]
            - self.snapshots[0]["timestamp"],
            "memory_growth_mb": memory_growth,
            "snapshots_analyzed": len(self.snapshots),
            "potential_leaks": potential_leaks,
            "memory_trend": [s["memory_mb"] for s in self.snapshots],
        }


class ComprehensiveBenchmarkSuite:
    """Main benchmark suite orchestrator."""

    def __init__(self):
        self.profiler = PerformanceProfiler()
        self.leak_detector = MemoryLeakDetector()
        self.results = []

    async def run_comprehensive_benchmarks(self) -> dict[str, Any]:
        """Run complete benchmark suite."""
        logger.info("🚀 Starting Comprehensive Performance Benchmarks")
        logger.info("=" * 70)

        # Start memory leak monitoring
        self.leak_detector.start_monitoring(interval_seconds=5.0)

        suite_start = time.time()

        try:
            # Benchmark 1: Basic Operations Performance
            await self._benchmark_basic_operations()

            # Benchmark 2: High-Frequency Operations
            await self._benchmark_high_frequency_operations()

            # Benchmark 3: Memory Intensive Operations
            await self._benchmark_memory_operations()

            # Benchmark 4: CPU Intensive Operations
            await self._benchmark_cpu_operations()

            # Benchmark 5: Concurrent Operations
            await self._benchmark_concurrent_operations()

            # Benchmark 6: Stress Testing
            await self._benchmark_stress_scenarios()

        finally:
            self.leak_detector.stop_monitoring()

        suite_duration = time.time() - suite_start

        # Analyze memory leaks
        leak_analysis = self.leak_detector.analyze_leaks()

        # Compile comprehensive results
        comprehensive_results = {
            "suite_info": {
                "duration_seconds": suite_duration,
                "timestamp": datetime.now().isoformat(),
                "benchmarks_run": len(self.results),
            },
            "individual_benchmarks": {
                result.test_name: result.get_summary() for result in self.results
            },
            "memory_leak_analysis": leak_analysis,
            "overall_performance": self._calculate_overall_metrics(),
            "recommendations": self._generate_recommendations(),
        }

        logger.info(f"✅ Comprehensive benchmarks completed in {suite_duration:.2f}s")

        return comprehensive_results

    async def _benchmark_basic_operations(self):
        """Benchmark basic system operations."""
        logger.info("📊 Benchmarking basic operations...")

        # Test dictionary operations (common in trading)
        async def dict_operations():
            data = {}
            for i in range(1000):
                data[f"market_{i}"] = {"price": 0.5, "volume": 1000 + i}

            # Simulate lookups and updates
            for i in range(500):
                key = f"market_{i}"
                if key in data:
                    data[key]["price"] += 0.001

        result = await self.profiler.benchmark(
            "basic_dict_operations",
            dict_operations,
            iterations=100,
            warmup_iterations=10,
        )
        self.results.append(result)

        # Test JSON serialization (API responses)
        async def json_operations():
            data = {
                "markets": [
                    {"id": f"m_{i}", "price": 0.5 + i * 0.001, "volume": 1000 + i}
                    for i in range(100)
                ]
            }
            json_str = json.dumps(data)
            parsed = json.loads(json_str)
            return len(parsed["markets"])

        result = await self.profiler.benchmark(
            "json_serialization", json_operations, iterations=1000, warmup_iterations=50
        )
        self.results.append(result)

    async def _benchmark_high_frequency_operations(self):
        """Benchmark operations at high frequency."""
        logger.info("⚡ Benchmarking high-frequency operations...")

        # Simulate price update processing
        prices = {}

        async def price_update():
            market_id = f"market_{len(prices) % 100}"
            new_price = 0.5 + (len(prices) * 0.0001) % 0.4
            prices[market_id] = {
                "yes_price": new_price,
                "no_price": 1.0 - new_price,
                "timestamp": time.time(),
                "volume": len(prices) * 100,
            }

        result = await self.profiler.benchmark(
            "high_frequency_price_updates",
            price_update,
            duration_seconds=10.0,
            warmup_iterations=100,
        )
        result.set_custom_metric("unique_markets_updated", len(set(prices.keys())))
        self.results.append(result)

        # Simulate order processing
        orders = []

        async def order_processing():
            order = {
                "id": f"order_{len(orders)}",
                "market_id": f"market_{len(orders) % 50}",
                "side": "buy" if len(orders) % 2 == 0 else "sell",
                "price": 0.5 + (len(orders) * 0.001) % 0.3,
                "size": 100 + (len(orders) * 10) % 1000,
                "timestamp": time.time(),
            }
            orders.append(order)

            # Simulate order matching logic
            if len(orders) > 10:
                orders.sort(key=lambda x: x["price"], reverse=True)

        result = await self.profiler.benchmark(
            "order_processing_simulation", order_processing, duration_seconds=5.0
        )
        result.set_custom_metric("orders_processed", len(orders))
        self.results.append(result)

    async def _benchmark_memory_operations(self):
        """Benchmark memory-intensive operations."""
        logger.info("🧠 Benchmarking memory operations...")

        # Test large data structure handling
        large_datasets = []

        async def memory_intensive_task():
            # Create market data snapshot (simulating real trading data)
            snapshot = {"timestamp": time.time(), "markets": {}}

            for i in range(1000):
                market_data = {
                    "id": f"market_{i}",
                    "prices": [0.5 + j * 0.001 for j in range(100)],  # Price history
                    "volumes": [1000 + j * 10 for j in range(100)],  # Volume history
                    "orders": [
                        {"price": 0.5 + k * 0.01, "size": 100 + k * 5}
                        for k in range(20)
                    ],
                }
                snapshot["markets"][f"market_{i}"] = market_data

            large_datasets.append(snapshot)

            # Simulate processing - keep only last 10 snapshots
            if len(large_datasets) > 10:
                large_datasets.pop(0)

        result = await self.profiler.benchmark(
            "memory_intensive_snapshots",
            memory_intensive_task,
            iterations=50,
            warmup_iterations=5,
        )
        result.set_custom_metric("snapshots_retained", len(large_datasets))
        self.results.append(result)

    async def _benchmark_cpu_operations(self):
        """Benchmark CPU-intensive operations."""
        logger.info("⚙️ Benchmarking CPU operations...")

        # Simulate risk calculation (CPU intensive)
        async def risk_calculation():
            portfolio = {}

            # Calculate position values
            for i in range(100):
                market_id = f"market_{i}"
                yes_price = 0.3 + (i * 0.003) % 0.4
                no_price = 1.0 - yes_price
                position_size = 1000 + i * 10

                portfolio[market_id] = {
                    "yes_position": position_size if i % 2 == 0 else 0,
                    "no_position": position_size if i % 2 == 1 else 0,
                    "yes_price": yes_price,
                    "no_price": no_price,
                }

            # Calculate total exposure and risk metrics
            total_exposure = 0
            max_loss = 0

            for market_id, position in portfolio.items():
                yes_exposure = position["yes_position"] * position["yes_price"]
                no_exposure = position["no_position"] * position["no_price"]
                total_exposure += yes_exposure + no_exposure

                # Simulate worst-case scenario calculation
                yes_loss = position["yes_position"] * (1.0 - position["yes_price"])
                no_loss = position["no_position"] * position["no_price"]
                market_max_loss = max(yes_loss, no_loss)
                max_loss += market_max_loss

            return {"total_exposure": total_exposure, "max_loss": max_loss}

        result = await self.profiler.benchmark(
            "risk_calculation_simulation",
            risk_calculation,
            iterations=500,
            warmup_iterations=20,
        )
        self.results.append(result)

    async def _benchmark_concurrent_operations(self):
        """Benchmark concurrent operation handling."""
        logger.info("🔀 Benchmarking concurrent operations...")

        shared_state = {"counter": 0, "markets": {}}

        async def concurrent_market_update(worker_id: int):
            # Simulate concurrent market updates
            for i in range(10):
                market_id = f"market_{worker_id}_{i}"
                shared_state["markets"][market_id] = {
                    "worker": worker_id,
                    "price": 0.5 + (worker_id * 0.01),
                    "timestamp": time.time(),
                    "update_count": shared_state["counter"],
                }
                shared_state["counter"] += 1

                # Small delay to simulate processing
                await asyncio.sleep(0.001)

        async def concurrent_benchmark():
            # Run multiple concurrent workers
            tasks = [concurrent_market_update(worker_id) for worker_id in range(20)]
            await asyncio.gather(*tasks)
            return len(shared_state["markets"])

        result = await self.profiler.benchmark(
            "concurrent_market_updates",
            concurrent_benchmark,
            iterations=10,
            warmup_iterations=2,
        )
        result.set_custom_metric("markets_updated", len(shared_state["markets"]))
        result.set_custom_metric("total_updates", shared_state["counter"])
        self.results.append(result)

    async def _benchmark_stress_scenarios(self):
        """Benchmark system under stress conditions."""
        logger.info("🔥 Benchmarking stress scenarios...")

        # Simulate system under extreme load
        stress_data = []

        async def stress_scenario():
            # Simulate burst of activity (like market volatility)
            burst_data = []

            for i in range(1000):
                # Create multiple data structures simultaneously
                market_update = {
                    "timestamp": time.time(),
                    "market_id": f"market_{i % 100}",
                    "price_data": [random() for _ in range(50)],
                    "order_book": {
                        "bids": [(0.5 - j * 0.01, 100 + j * 10) for j in range(10)],
                        "asks": [(0.5 + j * 0.01, 100 + j * 10) for j in range(10)],
                    },
                }
                burst_data.append(market_update)

                # Simulate processing every 50 items
                if len(burst_data) % 50 == 0:
                    # Sort by timestamp (CPU intensive)
                    burst_data.sort(key=lambda x: x["timestamp"])

                    # Calculate some metrics (CPU intensive)
                    avg_price = sum(
                        sum(item["price_data"]) / len(item["price_data"])
                        for item in burst_data
                    ) / len(burst_data)

                    # Store result
                    stress_data.append(
                        {
                            "batch_size": len(burst_data),
                            "avg_price": avg_price,
                            "processed_at": time.time(),
                        }
                    )

                    # Keep memory usage controlled
                    if len(stress_data) > 20:
                        stress_data.pop(0)

        # Import random function
        def random():
            import random as r

            return r.random()

        result = await self.profiler.benchmark(
            "stress_scenario_burst_processing",
            stress_scenario,
            iterations=5,
            warmup_iterations=1,
        )
        result.set_custom_metric("stress_batches_processed", len(stress_data))
        self.results.append(result)

    def _calculate_overall_metrics(self) -> dict[str, Any]:
        """Calculate overall performance metrics across all benchmarks."""
        if not self.results:
            return {}

        all_response_times = []
        total_operations = 0
        total_errors = 0

        for result in self.results:
            all_response_times.extend(result.response_times_ms)
            total_operations += result.success_count
            total_errors += result.error_count

        memory_peaks = [r.memory_peak_mb for r in self.results if r.memory_peak_mb > 0]
        cpu_averages = [
            statistics.mean(r.cpu_usage_percent)
            for r in self.results
            if r.cpu_usage_percent
        ]

        return {
            "total_operations": total_operations,
            "total_errors": total_errors,
            "overall_error_rate": (
                (total_errors / (total_operations + total_errors) * 100)
                if (total_operations + total_errors) > 0
                else 0
            ),
            "response_time_summary": {
                "avg_ms": (
                    statistics.mean(all_response_times) if all_response_times else 0
                ),
                "p95_ms": self._percentile(all_response_times, 95),
                "p99_ms": self._percentile(all_response_times, 99),
                "max_ms": max(all_response_times) if all_response_times else 0,
            },
            "memory_summary": {
                "peak_usage_mb": max(memory_peaks) if memory_peaks else 0,
                "avg_peak_mb": statistics.mean(memory_peaks) if memory_peaks else 0,
            },
            "cpu_summary": {
                "avg_utilization_percent": (
                    statistics.mean(cpu_averages) if cpu_averages else 0
                ),
                "peak_utilization_percent": max(cpu_averages) if cpu_averages else 0,
            },
        }

    def _generate_recommendations(self) -> list[str]:
        """Generate performance recommendations based on benchmark results."""
        recommendations = []

        if not self.results:
            return ["No benchmark results available for analysis"]

        overall_metrics = self._calculate_overall_metrics()

        # Response time recommendations
        if overall_metrics.get("response_time_summary", {}).get("p99_ms", 0) > 100:
            recommendations.append(
                "⚠️  P99 response times exceed 100ms - consider optimizing critical path operations"
            )

        if overall_metrics.get("response_time_summary", {}).get("avg_ms", 0) > 10:
            recommendations.append(
                "💡 Average response times could be improved - profile individual operations"
            )

        # Memory recommendations
        peak_memory = overall_metrics.get("memory_summary", {}).get("peak_usage_mb", 0)
        if peak_memory > 1000:  # 1GB
            recommendations.append(
                "🧠 High memory usage detected - consider implementing memory pooling or data streaming"
            )

        # CPU recommendations
        avg_cpu = overall_metrics.get("cpu_summary", {}).get(
            "avg_utilization_percent", 0
        )
        if avg_cpu > 80:
            recommendations.append(
                "⚙️  High CPU utilization - consider async processing or operation batching"
            )

        # Error rate recommendations
        error_rate = overall_metrics.get("overall_error_rate", 0)
        if error_rate > 1:
            recommendations.append(
                f"❌ Error rate of {error_rate:.2f}% detected - implement better error handling"
            )

        # Memory leak recommendations
        if any(r.memory_growth_mb > 100 for r in self.results):
            recommendations.append(
                "💧 Potential memory leaks detected - review object lifecycle management"
            )

        if not recommendations:
            recommendations.append(
                "✅ Performance metrics look healthy - no major issues detected"
            )

        return recommendations

    def _percentile(self, data: list[float], percentile: float) -> float:
        """Calculate percentile value."""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]


async def run_performance_benchmarks():
    """Run comprehensive performance benchmark suite."""
    suite = ComprehensiveBenchmarkSuite()

    try:
        results = await suite.run_comprehensive_benchmarks()

        # Generate detailed report
        report = generate_benchmark_report(results)
        print(report)

        # Save results to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"performance_benchmarks_{timestamp}.json"

        with open(filename, "w") as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\n📁 Detailed results saved to: {filename}")

        return results

    except KeyboardInterrupt:
        logger.info("Benchmarking interrupted by user")
        return None
    except Exception as e:
        logger.error(f"Benchmarking failed: {e}")
        import traceback

        traceback.print_exc()
        return None


def generate_benchmark_report(results: dict[str, Any]) -> str:
    """Generate human-readable benchmark report."""
    if not results:
        return "No benchmark results available."

    report = []
    report.append("🔬 PERFORMANCE BENCHMARK REPORT")
    report.append("=" * 70)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")

    # Suite summary
    suite_info = results.get("suite_info", {})
    report.append("📋 SUITE SUMMARY")
    report.append("-" * 30)
    report.append(f"Duration: {suite_info.get('duration_seconds', 0):.2f} seconds")
    report.append(f"Benchmarks Run: {suite_info.get('benchmarks_run', 0)}")
    report.append("")

    # Overall performance
    overall = results.get("overall_performance", {})
    if overall:
        report.append("🎯 OVERALL PERFORMANCE")
        report.append("-" * 30)
        report.append(f"Total Operations: {overall.get('total_operations', 0):,}")
        report.append(f"Error Rate: {overall.get('overall_error_rate', 0):.2f}%")

        rt_summary = overall.get("response_time_summary", {})
        report.append(f"Avg Response Time: {rt_summary.get('avg_ms', 0):.2f}ms")
        report.append(f"P95 Response Time: {rt_summary.get('p95_ms', 0):.2f}ms")
        report.append(f"P99 Response Time: {rt_summary.get('p99_ms', 0):.2f}ms")

        mem_summary = overall.get("memory_summary", {})
        report.append(f"Peak Memory Usage: {mem_summary.get('peak_usage_mb', 0):.1f}MB")

        cpu_summary = overall.get("cpu_summary", {})
        report.append(
            f"Avg CPU Utilization: {cpu_summary.get('avg_utilization_percent', 0):.1f}%"
        )
        report.append("")

    # Individual benchmark results
    benchmarks = results.get("individual_benchmarks", {})
    if benchmarks:
        report.append("📊 INDIVIDUAL BENCHMARK RESULTS")
        report.append("-" * 50)

        for bench_name, bench_data in benchmarks.items():
            report.append(f"\n🔍 {bench_name.upper().replace('_', ' ')}")

            perf = bench_data.get("performance", {})
            report.append(f"  Operations: {perf.get('total_operations', 0):,}")
            report.append(f"  Success Rate: {perf.get('success_rate_percent', 0):.1f}%")
            report.append(
                f"  Throughput: {perf.get('throughput_ops_per_second', 0):.1f} ops/s"
            )

            rt = perf.get("response_times", {})
            report.append(f"  Avg Response: {rt.get('avg_ms', 0):.2f}ms")
            report.append(f"  P99 Response: {rt.get('p99_ms', 0):.2f}ms")

            resources = bench_data.get("resources", {})
            memory = resources.get("memory", {})
            cpu = resources.get("cpu", {})
            report.append(f"  Peak Memory: {memory.get('peak_mb', 0):.1f}MB")
            report.append(f"  Avg CPU: {cpu.get('avg_percent', 0):.1f}%")

            # Custom metrics
            custom = bench_data.get("custom_metrics", {})
            if custom:
                for key, value in custom.items():
                    report.append(f"  {key.replace('_', ' ').title()}: {value}")

    # Memory leak analysis
    leak_analysis = results.get("memory_leak_analysis", {})
    if leak_analysis and not leak_analysis.get("error"):
        report.append("\n💧 MEMORY LEAK ANALYSIS")
        report.append("-" * 30)
        report.append(
            f"Analysis Period: {leak_analysis.get('analysis_period_seconds', 0):.1f}s"
        )
        report.append(
            f"Memory Growth: {leak_analysis.get('memory_growth_mb', 0):.2f}MB"
        )
        report.append(
            f"Potential Leaks: {len(leak_analysis.get('potential_leaks', []))}"
        )

        if leak_analysis.get("potential_leaks"):
            report.append("\nTop Memory Growth Areas:")
            for i, leak in enumerate(leak_analysis["potential_leaks"][:3]):
                report.append(f"  {i+1}. {leak['size_diff_mb']:.2f}MB growth")

    # Recommendations
    recommendations = results.get("recommendations", [])
    if recommendations:
        report.append("\n💡 RECOMMENDATIONS")
        report.append("-" * 30)
        for rec in recommendations:
            report.append(f"  {rec}")

    report.append("\n" + "=" * 70)

    return "\n".join(report)


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # Run benchmarks
    results = asyncio.run(run_performance_benchmarks())

    if results:
        print("\n✅ Performance benchmarking completed successfully!")
    else:
        print("\n❌ Performance benchmarking failed or was interrupted")
        exit(1)
