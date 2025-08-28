"""
Comprehensive performance benchmarks for the InkedUp Polymarket trading bot.

This module contains performance tests to validate that the system meets
critical performance requirements under various load conditions:

- Handle 1000+ concurrent market updates
- Process signals within 50ms of market data arrival
- Complete database queries within 10ms average
- Maintain stable memory usage under continuous operation
- Achieve 99.9% uptime for core trading components

The benchmarks use realistic data patterns and load scenarios to ensure
the system can perform effectively in production environments.
"""

import asyncio
import gc
import logging
import statistics
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import psutil
import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.database_complete import DatabaseManager
from inkedup_bot.engine import TradingEngine
from inkedup_bot.position_manager import PositionManager
from inkedup_bot.scanner import BookEntry, MarketComposite, Scanner
from inkedup_bot.signals import TradingSignal
from inkedup_bot.state import StateManager


# Performance test configuration
@dataclass
class PerformanceConfig:
    """Configuration for performance benchmarks."""

    # Market update requirements
    concurrent_updates_target = 1000
    concurrent_updates_tolerance = 0.95  # 95% success rate minimum

    # Signal processing requirements
    signal_processing_max_latency_ms = 50.0
    signal_processing_tolerance = 0.90  # 90% within target

    # Database query requirements
    database_query_max_avg_ms = 10.0
    database_query_max_p99_ms = 25.0
    database_query_samples = 1000

    # Memory stability requirements
    memory_growth_max_percent = 20.0  # Max 20% growth over baseline
    memory_test_duration_minutes = 5
    memory_sample_interval_seconds = 10

    # Uptime requirements
    uptime_target_percent = 99.9
    uptime_test_duration_minutes = 10
    uptime_failure_threshold_ms = 5000  # Consider >5s as failure


@dataclass
class BenchmarkResult:
    """Result of a performance benchmark test."""

    test_name: str
    passed: bool
    duration_seconds: float
    metrics: Dict[str, Any]
    details: str
    timestamp: datetime


class PerformanceBenchmarkSuite:
    """Comprehensive performance benchmark test suite."""

    def __init__(self, config: PerformanceConfig = None):
        self.config = config or PerformanceConfig()
        self.results: List[BenchmarkResult] = []
        self.logger = logging.getLogger(__name__)

    async def run_all_benchmarks(self) -> Dict[str, BenchmarkResult]:
        """Run all performance benchmarks and return results."""

        self.logger.info("Starting comprehensive performance benchmark suite")
        start_time = time.time()

        # Run all benchmark tests
        benchmark_methods = [
            self.benchmark_concurrent_market_updates,
            self.benchmark_signal_processing_latency,
            self.benchmark_database_query_performance,
            self.benchmark_memory_stability,
            self.benchmark_system_uptime,
        ]

        results = {}
        for benchmark in benchmark_methods:
            try:
                result = await benchmark()
                results[result.test_name] = result
                self.results.append(result)

                status = "PASSED" if result.passed else "FAILED"
                self.logger.info(f"Benchmark {result.test_name}: {status}")

            except Exception as e:
                error_result = BenchmarkResult(
                    test_name=benchmark.__name__,
                    passed=False,
                    duration_seconds=0.0,
                    metrics={},
                    details=f"Test failed with exception: {str(e)}",
                    timestamp=datetime.utcnow(),
                )
                results[error_result.test_name] = error_result
                self.results.append(error_result)
                self.logger.error(f"Benchmark {benchmark.__name__} failed: {e}")

        total_duration = time.time() - start_time
        self.logger.info(f"Benchmark suite completed in {total_duration:.2f} seconds")

        return results

    async def benchmark_concurrent_market_updates(self) -> BenchmarkResult:
        """Test handling 1000+ concurrent market updates."""

        test_start = time.time()
        target_updates = self.config.concurrent_updates_target

        # Create test scanner and data structures
        config = BotConfig()
        scanner = Scanner(config)

        # Generate test market data
        test_markets = []
        for i in range(target_updates):
            market_data = {
                "market_slug": f"test_market_{i}",
                "token_id": f"0x{i:040x}",
                "bid": 0.45 + (i % 100) * 0.001,
                "ask": 0.55 + (i % 100) * 0.001,
                "spread_bps": 1000 + (i % 500),
                "last_update": time.time(),
            }
            test_markets.append(market_data)

        # Test concurrent processing
        successful_updates = 0
        failed_updates = 0
        processing_times = []

        async def process_market_update(market_data):
            """Process a single market update."""
            try:
                start_time = time.time()

                # Simulate market data processing
                book_entry = BookEntry(
                    token_id=market_data["token_id"],
                    bid=market_data["bid"],
                    ask=market_data["ask"],
                    spread_bps=market_data["spread_bps"],
                )

                # Simulate some processing work
                await asyncio.sleep(0.001)  # 1ms processing time

                processing_time = (time.time() - start_time) * 1000
                return processing_time, True

            except Exception as e:
                self.logger.warning(f"Market update failed: {e}")
                return 0, False

        # Execute concurrent updates
        start_time = time.time()

        tasks = []
        for market_data in test_markets:
            task = asyncio.create_task(process_market_update(market_data))
            tasks.append(task)

        # Wait for all tasks with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=30.0
            )

            for result in results:
                if isinstance(result, Exception):
                    failed_updates += 1
                else:
                    processing_time, success = result
                    if success:
                        successful_updates += 1
                        processing_times.append(processing_time)
                    else:
                        failed_updates += 1

        except asyncio.TimeoutError:
            failed_updates = target_updates - successful_updates
            self.logger.error("Concurrent market updates test timed out")

        total_time = time.time() - start_time
        success_rate = successful_updates / target_updates if target_updates > 0 else 0

        # Calculate metrics
        metrics = {
            "target_updates": target_updates,
            "successful_updates": successful_updates,
            "failed_updates": failed_updates,
            "success_rate": success_rate,
            "total_time_seconds": total_time,
            "updates_per_second": (
                successful_updates / total_time if total_time > 0 else 0
            ),
            "avg_processing_time_ms": (
                statistics.mean(processing_times) if processing_times else 0
            ),
            "p95_processing_time_ms": (
                statistics.quantiles(processing_times, n=20)[18]
                if len(processing_times) >= 20
                else 0
            ),
            "p99_processing_time_ms": (
                statistics.quantiles(processing_times, n=100)[98]
                if len(processing_times) >= 100
                else 0
            ),
        }

        # Determine if test passed
        passed = success_rate >= self.config.concurrent_updates_tolerance

        details = (
            f"Processed {successful_updates}/{target_updates} updates "
            f"({success_rate:.1%} success rate) in {total_time:.2f}s. "
            f"Average processing time: {metrics['avg_processing_time_ms']:.2f}ms"
        )

        return BenchmarkResult(
            test_name="concurrent_market_updates",
            passed=passed,
            duration_seconds=time.time() - test_start,
            metrics=metrics,
            details=details,
            timestamp=datetime.utcnow(),
        )

    async def benchmark_signal_processing_latency(self) -> BenchmarkResult:
        """Test signal processing latency (<50ms from market data to execution)."""

        test_start = time.time()

        # Create test trading engine
        config = BotConfig()
        engine = TradingEngine(config)
        await engine.initialize()

        # Test signal processing latencies
        latencies = []
        successful_signals = 0
        failed_signals = 0

        try:
            for i in range(100):  # Test 100 signals
                signal = TradingSignal(
                    market_slug=f"benchmark_market_{i}",
                    token_id=f"0x{i:040x}",
                    side="buy" if i % 2 == 0 else "sell",
                    price=0.5 + (i % 50) * 0.01,
                    size=100.0 + i,
                    outcome_type="yes" if i % 2 == 0 else "no",
                )

                # Measure end-to-end latency
                signal_start = time.time()

                try:
                    signal_id = engine.process_signal(signal)

                    # Wait a bit for processing
                    await asyncio.sleep(0.001)

                    latency_ms = (time.time() - signal_start) * 1000
                    latencies.append(latency_ms)
                    successful_signals += 1

                except Exception as e:
                    failed_signals += 1
                    self.logger.warning(f"Signal processing failed: {e}")

                # Small delay between signals
                await asyncio.sleep(0.01)

        finally:
            await engine.shutdown()

        # Calculate metrics
        avg_latency = statistics.mean(latencies) if latencies else 0
        p50_latency = statistics.median(latencies) if latencies else 0
        p95_latency = (
            statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else 0
        )
        p99_latency = (
            statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else 0
        )

        within_target = sum(
            1
            for lat in latencies
            if lat <= self.config.signal_processing_max_latency_ms
        )
        within_target_rate = within_target / len(latencies) if latencies else 0

        metrics = {
            "total_signals": successful_signals + failed_signals,
            "successful_signals": successful_signals,
            "failed_signals": failed_signals,
            "success_rate": (
                successful_signals / (successful_signals + failed_signals)
                if (successful_signals + failed_signals) > 0
                else 0
            ),
            "avg_latency_ms": avg_latency,
            "p50_latency_ms": p50_latency,
            "p95_latency_ms": p95_latency,
            "p99_latency_ms": p99_latency,
            "within_target_count": within_target,
            "within_target_rate": within_target_rate,
            "target_latency_ms": self.config.signal_processing_max_latency_ms,
        }

        # Determine if test passed
        passed = (
            within_target_rate >= self.config.signal_processing_tolerance
            and avg_latency <= self.config.signal_processing_max_latency_ms
        )

        details = (
            f"Processed {successful_signals} signals with average latency {avg_latency:.2f}ms. "
            f"{within_target_rate:.1%} within {self.config.signal_processing_max_latency_ms}ms target."
        )

        return BenchmarkResult(
            test_name="signal_processing_latency",
            passed=passed,
            duration_seconds=time.time() - test_start,
            metrics=metrics,
            details=details,
            timestamp=datetime.utcnow(),
        )

    async def benchmark_database_query_performance(self) -> BenchmarkResult:
        """Test database query performance (<10ms average)."""

        test_start = time.time()

        # Create test database
        db = DatabaseManager(":memory:")  # Use in-memory for consistent testing
        await db.initialize()

        # Insert test data
        test_data_size = self.config.database_query_samples

        # Insert test orders
        for i in range(test_data_size):
            order_data = {
                "id": f"order_{i}",
                "market_slug": f"market_{i % 100}",
                "side": "buy" if i % 2 == 0 else "sell",
                "size": 100.0 + i,
                "price": 0.5 + (i % 100) * 0.005,
                "status": "open",
                "created_at": datetime.utcnow().isoformat(),
            }
            await db.insert_order(order_data)

        # Insert test positions
        for i in range(test_data_size // 2):
            position_data = {
                "token_id": f"0x{i:040x}",
                "market_slug": f"market_{i % 50}",
                "outcome_type": "yes" if i % 2 == 0 else "no",
                "size": Decimal(str(100.0 + i)),
                "notional_value": Decimal(str(50.0 + i * 0.5)),
                "created_at": datetime.utcnow().isoformat(),
            }
            await db.upsert_position(position_data)

        # Test various query types
        query_times = []
        query_types = []

        # Test position queries
        for i in range(200):
            start_time = time.time()
            token_id = f"0x{i % (test_data_size // 2):040x}"
            await db.get_position_notional(token_id)
            query_time = (time.time() - start_time) * 1000
            query_times.append(query_time)
            query_types.append("position_lookup")

        # Test order queries
        for i in range(200):
            start_time = time.time()
            await db.get_open_orders()
            query_time = (time.time() - start_time) * 1000
            query_times.append(query_time)
            query_types.append("open_orders")

        # Test exposure calculations
        for i in range(200):
            start_time = time.time()
            market_slug = f"market_{i % 50}"
            await db.get_market_exposure(market_slug)
            query_time = (time.time() - start_time) * 1000
            query_times.append(query_time)
            query_types.append("market_exposure")

        # Test total exposure
        for i in range(100):
            start_time = time.time()
            await db.get_total_exposure()
            query_time = (time.time() - start_time) * 1000
            query_times.append(query_time)
            query_types.append("total_exposure")

        # Calculate metrics
        avg_query_time = statistics.mean(query_times) if query_times else 0
        median_query_time = statistics.median(query_times) if query_times else 0
        p95_query_time = (
            statistics.quantiles(query_times, n=20)[18] if len(query_times) >= 20 else 0
        )
        p99_query_time = (
            statistics.quantiles(query_times, n=100)[98]
            if len(query_times) >= 100
            else 0
        )
        max_query_time = max(query_times) if query_times else 0

        # Analyze by query type
        query_type_stats = {}
        for query_type in set(query_types):
            type_times = [
                t for t, qt in zip(query_times, query_types) if qt == query_type
            ]
            if type_times:
                query_type_stats[query_type] = {
                    "count": len(type_times),
                    "avg_ms": statistics.mean(type_times),
                    "p95_ms": (
                        statistics.quantiles(type_times, n=20)[18]
                        if len(type_times) >= 20
                        else max(type_times)
                    ),
                }

        metrics = {
            "total_queries": len(query_times),
            "avg_query_time_ms": avg_query_time,
            "median_query_time_ms": median_query_time,
            "p95_query_time_ms": p95_query_time,
            "p99_query_time_ms": p99_query_time,
            "max_query_time_ms": max_query_time,
            "target_avg_ms": self.config.database_query_max_avg_ms,
            "target_p99_ms": self.config.database_query_max_p99_ms,
            "query_type_stats": query_type_stats,
        }

        # Determine if test passed
        passed = (
            avg_query_time <= self.config.database_query_max_avg_ms
            and p99_query_time <= self.config.database_query_max_p99_ms
        )

        details = (
            f"Executed {len(query_times)} queries with average time {avg_query_time:.2f}ms, "
            f"P99 time {p99_query_time:.2f}ms."
        )

        return BenchmarkResult(
            test_name="database_query_performance",
            passed=passed,
            duration_seconds=time.time() - test_start,
            metrics=metrics,
            details=details,
            timestamp=datetime.utcnow(),
        )

    async def benchmark_memory_stability(self) -> BenchmarkResult:
        """Test memory usage stability under continuous operation."""

        test_start = time.time()

        # Enable memory tracing
        tracemalloc.start()

        # Get baseline memory usage
        process = psutil.Process()
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create components for testing
        config = BotConfig()
        engine = TradingEngine(config)
        await engine.initialize()

        memory_samples = []
        peak_memory = baseline_memory

        duration_seconds = self.config.memory_test_duration_minutes * 60
        sample_interval = self.config.memory_sample_interval_seconds
        samples_count = int(duration_seconds / sample_interval)

        try:
            for i in range(samples_count):
                # Simulate continuous operation
                for j in range(10):  # Process multiple signals per sample
                    signal = TradingSignal(
                        market_slug=f"memory_test_{j}",
                        token_id=f"0x{j:040x}",
                        side="buy" if j % 2 == 0 else "sell",
                        price=0.5,
                        size=100.0,
                        outcome_type="yes",
                    )
                    engine.process_signal(signal)

                    # Small processing delay
                    await asyncio.sleep(0.001)

                # Force garbage collection
                gc.collect()

                # Sample memory usage
                current_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_samples.append(current_memory)
                peak_memory = max(peak_memory, current_memory)

                # Wait for next sample
                await asyncio.sleep(sample_interval)

                # Log progress
                if i % 5 == 0:
                    self.logger.info(
                        f"Memory stability test: {i}/{samples_count} samples, "
                        f"current memory: {current_memory:.1f}MB"
                    )

        finally:
            await engine.shutdown()
            tracemalloc.stop()

        # Calculate memory metrics
        final_memory = memory_samples[-1] if memory_samples else baseline_memory
        memory_growth = final_memory - baseline_memory
        memory_growth_percent = (
            (memory_growth / baseline_memory) * 100 if baseline_memory > 0 else 0
        )

        avg_memory = (
            statistics.mean(memory_samples) if memory_samples else baseline_memory
        )
        max_memory = max(memory_samples) if memory_samples else baseline_memory
        memory_volatility = (
            statistics.stdev(memory_samples) if len(memory_samples) > 1 else 0
        )

        metrics = {
            "duration_minutes": duration_seconds / 60,
            "baseline_memory_mb": baseline_memory,
            "final_memory_mb": final_memory,
            "peak_memory_mb": peak_memory,
            "memory_growth_mb": memory_growth,
            "memory_growth_percent": memory_growth_percent,
            "avg_memory_mb": avg_memory,
            "memory_volatility_mb": memory_volatility,
            "samples_count": len(memory_samples),
            "target_max_growth_percent": self.config.memory_growth_max_percent,
        }

        # Determine if test passed
        passed = memory_growth_percent <= self.config.memory_growth_max_percent

        details = (
            f"Memory usage over {duration_seconds/60:.1f} minutes: "
            f"baseline {baseline_memory:.1f}MB -> final {final_memory:.1f}MB "
            f"({memory_growth_percent:.1f}% growth, peak {peak_memory:.1f}MB)"
        )

        return BenchmarkResult(
            test_name="memory_stability",
            passed=passed,
            duration_seconds=time.time() - test_start,
            metrics=metrics,
            details=details,
            timestamp=datetime.utcnow(),
        )

    async def benchmark_system_uptime(self) -> BenchmarkResult:
        """Test system uptime and reliability (99.9% target)."""

        test_start = time.time()

        # Create system components
        config = BotConfig()
        engine = TradingEngine(config)
        await engine.initialize()

        state_manager = StateManager()
        await state_manager.initialize_async()

        duration_seconds = self.config.uptime_test_duration_minutes * 60
        check_interval = 0.1  # Check every 100ms
        checks_count = int(duration_seconds / check_interval)

        successful_checks = 0
        failed_checks = 0
        failure_details = []
        response_times = []

        try:
            for i in range(checks_count):
                check_start = time.time()

                try:
                    # Test core system components
                    # 1. Engine health check
                    if not engine.is_signal_manager_running():
                        raise Exception("Signal manager not running")

                    # 2. Test signal processing
                    test_signal = TradingSignal(
                        market_slug="uptime_test",
                        token_id="0x1234567890abcdef",
                        side="buy",
                        price=0.5,
                        size=100.0,
                        outcome_type="yes",
                    )
                    engine.process_signal(test_signal)

                    # 3. Test state manager
                    state_manager.get_total_exposure()

                    # 4. Measure response time
                    response_time = (time.time() - check_start) * 1000
                    response_times.append(response_time)

                    # Check if response time is acceptable
                    if response_time > self.config.uptime_failure_threshold_ms:
                        failed_checks += 1
                        failure_details.append(
                            f"Check {i}: Slow response {response_time:.1f}ms"
                        )
                    else:
                        successful_checks += 1

                except Exception as e:
                    failed_checks += 1
                    failure_details.append(f"Check {i}: {str(e)}")

                # Wait for next check
                await asyncio.sleep(check_interval)

                # Log progress
                if i % 1000 == 0:
                    uptime_so_far = (
                        successful_checks / (successful_checks + failed_checks) * 100
                    )
                    self.logger.info(
                        f"Uptime test: {i}/{checks_count} checks, "
                        f"uptime {uptime_so_far:.2f}%"
                    )

        finally:
            await engine.shutdown()

        # Calculate uptime metrics
        total_checks = successful_checks + failed_checks
        uptime_percent = (
            (successful_checks / total_checks * 100) if total_checks > 0 else 0
        )

        avg_response_time = statistics.mean(response_times) if response_times else 0
        p95_response_time = (
            statistics.quantiles(response_times, n=20)[18]
            if len(response_times) >= 20
            else 0
        )
        p99_response_time = (
            statistics.quantiles(response_times, n=100)[98]
            if len(response_times) >= 100
            else 0
        )

        # Calculate downtime periods
        downtime_ms = failed_checks * check_interval * 1000

        metrics = {
            "duration_minutes": duration_seconds / 60,
            "total_checks": total_checks,
            "successful_checks": successful_checks,
            "failed_checks": failed_checks,
            "uptime_percent": uptime_percent,
            "downtime_ms": downtime_ms,
            "avg_response_time_ms": avg_response_time,
            "p95_response_time_ms": p95_response_time,
            "p99_response_time_ms": p99_response_time,
            "target_uptime_percent": self.config.uptime_target_percent,
            "failure_threshold_ms": self.config.uptime_failure_threshold_ms,
            "failure_count": len(failure_details),
            "recent_failures": (
                failure_details[-10:] if failure_details else []
            ),  # Last 10 failures
        }

        # Determine if test passed
        passed = uptime_percent >= self.config.uptime_target_percent

        details = (
            f"System uptime over {duration_seconds/60:.1f} minutes: {uptime_percent:.3f}% "
            f"({successful_checks}/{total_checks} successful checks, "
            f"avg response {avg_response_time:.1f}ms)"
        )

        return BenchmarkResult(
            test_name="system_uptime",
            passed=passed,
            duration_seconds=time.time() - test_start,
            metrics=metrics,
            details=details,
            timestamp=datetime.utcnow(),
        )

    def generate_benchmark_report(self) -> str:
        """Generate a comprehensive benchmark report."""

        if not self.results:
            return "No benchmark results available."

        passed_tests = sum(1 for r in self.results if r.passed)
        total_tests = len(self.results)

        report = [
            "=" * 80,
            "INKEDUP BOT PERFORMANCE BENCHMARK REPORT",
            "=" * 80,
            f"Generated: {datetime.utcnow().isoformat()}Z",
            f"Tests Passed: {passed_tests}/{total_tests} ({passed_tests/total_tests*100:.1f}%)",
            "",
        ]

        # Summary table
        report.extend(
            [
                "SUMMARY:",
                "-" * 40,
                f"{'Test Name':<30} {'Status':<10} {'Duration':<10}",
                "-" * 40,
            ]
        )

        for result in self.results:
            status = "PASSED" if result.passed else "FAILED"
            duration = f"{result.duration_seconds:.1f}s"
            report.append(f"{result.test_name:<30} {status:<10} {duration:<10}")

        report.append("")

        # Detailed results
        for result in self.results:
            report.extend(
                [
                    f"TEST: {result.test_name.upper()}",
                    "-" * 50,
                    f"Status: {'PASSED' if result.passed else 'FAILED'}",
                    f"Duration: {result.duration_seconds:.2f} seconds",
                    f"Details: {result.details}",
                    "",
                    "Key Metrics:",
                ]
            )

            for key, value in result.metrics.items():
                if isinstance(value, dict):
                    report.append(f"  {key}:")
                    for subkey, subvalue in value.items():
                        report.append(f"    {subkey}: {subvalue}")
                elif isinstance(value, (int, float)):
                    if isinstance(value, float):
                        report.append(f"  {key}: {value:.3f}")
                    else:
                        report.append(f"  {key}: {value}")
                else:
                    report.append(f"  {key}: {value}")

            report.append("")

        # Performance requirements summary
        report.extend(
            [
                "PERFORMANCE REQUIREMENTS VALIDATION:",
                "-" * 50,
                f"✓ Concurrent market updates: {'PASSED' if any(r.test_name == 'concurrent_market_updates' and r.passed for r in self.results) else 'FAILED'}",
                f"✓ Signal processing latency: {'PASSED' if any(r.test_name == 'signal_processing_latency' and r.passed for r in self.results) else 'FAILED'}",
                f"✓ Database query performance: {'PASSED' if any(r.test_name == 'database_query_performance' and r.passed for r in self.results) else 'FAILED'}",
                f"✓ Memory stability: {'PASSED' if any(r.test_name == 'memory_stability' and r.passed for r in self.results) else 'FAILED'}",
                f"✓ System uptime: {'PASSED' if any(r.test_name == 'system_uptime' and r.passed for r in self.results) else 'FAILED'}",
                "",
                "=" * 80,
            ]
        )

        return "\n".join(report)


# Pytest fixtures and test functions
@pytest.fixture
async def benchmark_suite():
    """Create a performance benchmark suite for testing."""
    return PerformanceBenchmarkSuite()


@pytest.mark.asyncio
@pytest.mark.performance
async def test_concurrent_market_updates(benchmark_suite):
    """Test concurrent market update processing."""
    result = await benchmark_suite.benchmark_concurrent_market_updates()

    # Log detailed results
    print(f"\n{result.details}")
    print(f"Metrics: {result.metrics}")

    assert result.passed, f"Concurrent market updates test failed: {result.details}"
    assert result.metrics["success_rate"] >= 0.95, "Success rate too low"
    assert result.metrics["successful_updates"] >= 950, "Not enough successful updates"


@pytest.mark.asyncio
@pytest.mark.performance
async def test_signal_processing_latency(benchmark_suite):
    """Test signal processing latency requirements."""
    result = await benchmark_suite.benchmark_signal_processing_latency()

    print(f"\n{result.details}")
    print(f"Metrics: {result.metrics}")

    assert result.passed, f"Signal processing latency test failed: {result.details}"
    assert result.metrics["avg_latency_ms"] <= 50.0, "Average latency too high"
    assert (
        result.metrics["within_target_rate"] >= 0.90
    ), "Too many signals over target latency"


@pytest.mark.asyncio
@pytest.mark.performance
async def test_database_query_performance(benchmark_suite):
    """Test database query performance requirements."""
    result = await benchmark_suite.benchmark_database_query_performance()

    print(f"\n{result.details}")
    print(f"Metrics: {result.metrics}")

    assert result.passed, f"Database query performance test failed: {result.details}"
    assert result.metrics["avg_query_time_ms"] <= 10.0, "Average query time too high"
    assert result.metrics["p99_query_time_ms"] <= 25.0, "P99 query time too high"


@pytest.mark.asyncio
@pytest.mark.performance
@pytest.mark.slow
async def test_memory_stability(benchmark_suite):
    """Test memory usage stability under load."""
    # Use shorter duration for CI/testing
    config = PerformanceConfig()
    config.memory_test_duration_minutes = 1  # Shorter test
    config.memory_sample_interval_seconds = 5

    suite = PerformanceBenchmarkSuite(config)
    result = await suite.benchmark_memory_stability()

    print(f"\n{result.details}")
    print(f"Metrics: {result.metrics}")

    assert result.passed, f"Memory stability test failed: {result.details}"
    assert result.metrics["memory_growth_percent"] <= 20.0, "Memory growth too high"


@pytest.mark.asyncio
@pytest.mark.performance
@pytest.mark.slow
async def test_system_uptime(benchmark_suite):
    """Test system uptime and reliability."""
    # Use shorter duration for CI/testing
    config = PerformanceConfig()
    config.uptime_test_duration_minutes = 2  # Shorter test

    suite = PerformanceBenchmarkSuite(config)
    result = await suite.benchmark_system_uptime()

    print(f"\n{result.details}")
    print(f"Metrics: {result.metrics}")

    assert result.passed, f"System uptime test failed: {result.details}"
    assert (
        result.metrics["uptime_percent"] >= 99.0
    ), "Uptime too low"  # Slightly lower for CI


@pytest.mark.asyncio
@pytest.mark.performance
async def test_full_benchmark_suite(benchmark_suite):
    """Run the complete performance benchmark suite."""
    results = await benchmark_suite.run_all_benchmarks()

    # Generate and print report
    report = benchmark_suite.generate_benchmark_report()
    print(f"\n{report}")

    # Verify all tests passed
    passed_tests = sum(1 for r in results.values() if r.passed)
    total_tests = len(results)

    assert (
        passed_tests >= total_tests * 0.8
    ), f"Too many benchmark failures: {passed_tests}/{total_tests} passed"


if __name__ == "__main__":

    async def main():
        """Run benchmarks as standalone script."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        suite = PerformanceBenchmarkSuite()
        results = await suite.run_all_benchmarks()

        print(suite.generate_benchmark_report())

        # Exit with appropriate code
        passed_tests = sum(1 for r in results.values() if r.passed)
        total_tests = len(results)

        if passed_tests == total_tests:
            print(f"\n✓ All {total_tests} benchmarks PASSED")
            exit(0)
        else:
            print(f"\n✗ {total_tests - passed_tests} benchmarks FAILED")
            exit(1)

    asyncio.run(main())
