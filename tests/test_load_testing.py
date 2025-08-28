"""
Load testing utilities for stress testing the InkedUp trading bot under extreme conditions.

This module provides additional load testing capabilities beyond the core performance
benchmarks, including stress testing, spike testing, volume testing, and endurance
testing to validate system behavior under various extreme conditions.
"""

import asyncio
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.database_complete import DatabaseManager
from inkedup_bot.engine import TradingEngine
from inkedup_bot.scanner import BookEntry
from inkedup_bot.signals import ComplementSignal, SpreadSignal, TradingSignal
from inkedup_bot.state import StateManager


@dataclass
class LoadTestConfig:
    """Configuration for load testing scenarios."""

    # Stress test configuration
    stress_test_duration_minutes: int = 10
    stress_test_max_concurrent_signals: int = 2000
    stress_test_signal_rate_per_second: int = 500

    # Spike test configuration
    spike_test_duration_minutes: int = 5
    spike_test_baseline_rate: int = 50
    spike_test_peak_rate: int = 1000
    spike_test_ramp_time_seconds: int = 10

    # Volume test configuration
    volume_test_duration_minutes: int = 30
    volume_test_steady_rate: int = 200
    volume_test_market_count: int = 500

    # Endurance test configuration
    endurance_test_duration_minutes: int = 60
    endurance_test_signal_rate: int = 100
    endurance_test_memory_check_interval: int = 300  # 5 minutes


@dataclass
class LoadTestResult:
    """Result of a load test."""

    test_name: str
    passed: bool
    duration_seconds: float
    total_operations: int
    successful_operations: int
    failed_operations: int
    average_response_time_ms: float
    peak_response_time_ms: float
    throughput_ops_per_second: float
    error_rate: float
    memory_peak_mb: float
    cpu_peak_percent: float
    details: Dict[str, Any]
    timestamp: datetime


class LoadTestSuite:
    """Comprehensive load testing suite for the InkedUp trading bot."""

    def __init__(self, config: LoadTestConfig = None):
        self.config = config or LoadTestConfig()
        self.logger = logging.getLogger(__name__)
        self.results: List[LoadTestResult] = []

    async def run_stress_test(self) -> LoadTestResult:
        """
        Run stress test with high concurrent load to find breaking point.

        This test gradually increases load until system performance degrades
        or failures occur, helping identify system limits and bottlenecks.
        """

        test_start = time.time()
        self.logger.info("Starting stress test - finding system breaking point")

        # Initialize system components
        config = BotConfig()
        engine = TradingEngine(config)
        await engine.initialize()

        total_operations = 0
        successful_operations = 0
        failed_operations = 0
        response_times = []
        error_details = []

        duration_seconds = self.config.stress_test_duration_minutes * 60
        end_time = time.time() + duration_seconds

        try:
            # Gradually increase load
            current_rate = 50  # Start with moderate load
            max_rate = self.config.stress_test_max_concurrent_signals
            rate_increase_interval = 30  # Increase every 30 seconds
            last_rate_increase = time.time()

            active_tasks = []

            while time.time() < end_time:
                # Increase load if interval passed
                if time.time() - last_rate_increase > rate_increase_interval:
                    current_rate = min(current_rate * 1.2, max_rate)  # 20% increase
                    last_rate_increase = time.time()
                    self.logger.info(
                        f"Increased load to {current_rate:.0f} signals/sec"
                    )

                # Generate signals at current rate
                signals_this_batch = int(current_rate / 10)  # 100ms batches

                for i in range(signals_this_batch):
                    signal = self._generate_test_signal(total_operations + i)
                    task = asyncio.create_task(
                        self._process_signal_with_timing(engine, signal)
                    )
                    active_tasks.append(task)
                    total_operations += 1

                # Clean up completed tasks
                if len(active_tasks) > current_rate * 2:  # Prevent unbounded growth
                    completed_tasks = [task for task in active_tasks if task.done()]

                    for task in completed_tasks:
                        try:
                            response_time, success, error = await task
                            if success:
                                successful_operations += 1
                                response_times.append(response_time)
                            else:
                                failed_operations += 1
                                if error:
                                    error_details.append(error)
                        except Exception as e:
                            failed_operations += 1
                            error_details.append(str(e))

                    # Remove completed tasks
                    active_tasks = [task for task in active_tasks if not task.done()]

                # Brief pause to control rate
                await asyncio.sleep(0.1)

            # Wait for remaining tasks to complete
            if active_tasks:
                self.logger.info(f"Waiting for {len(active_tasks)} remaining tasks...")
                remaining_results = await asyncio.gather(
                    *active_tasks, return_exceptions=True
                )

                for result in remaining_results:
                    if isinstance(result, Exception):
                        failed_operations += 1
                        error_details.append(str(result))
                    else:
                        response_time, success, error = result
                        if success:
                            successful_operations += 1
                            response_times.append(response_time)
                        else:
                            failed_operations += 1
                            if error:
                                error_details.append(error)

        finally:
            await engine.shutdown()

        # Calculate metrics
        total_time = time.time() - test_start
        error_rate = failed_operations / total_operations if total_operations > 0 else 0
        throughput = successful_operations / total_time if total_time > 0 else 0
        avg_response_time = (
            sum(response_times) / len(response_times) if response_times else 0
        )
        peak_response_time = max(response_times) if response_times else 0

        # Determine if test passed (stress tests are exploratory, so we're lenient)
        passed = error_rate < 0.5  # Allow up to 50% errors under extreme stress

        return LoadTestResult(
            test_name="stress_test",
            passed=passed,
            duration_seconds=total_time,
            total_operations=total_operations,
            successful_operations=successful_operations,
            failed_operations=failed_operations,
            average_response_time_ms=avg_response_time,
            peak_response_time_ms=peak_response_time,
            throughput_ops_per_second=throughput,
            error_rate=error_rate,
            memory_peak_mb=0.0,  # Would need process monitoring for this
            cpu_peak_percent=0.0,  # Would need process monitoring for this
            details={
                "final_rate": current_rate,
                "error_samples": error_details[:10],  # First 10 errors
                "duration_minutes": total_time / 60,
            },
            timestamp=datetime.utcnow(),
        )

    async def run_spike_test(self) -> LoadTestResult:
        """
        Run spike test with sudden load increases to test system resilience.

        This test simulates sudden traffic spikes to verify the system can
        handle rapid load changes without failing or degrading significantly.
        """

        test_start = time.time()
        self.logger.info("Starting spike test - testing resilience to traffic spikes")

        # Initialize system
        config = BotConfig()
        engine = TradingEngine(config)
        await engine.initialize()

        total_operations = 0
        successful_operations = 0
        failed_operations = 0
        response_times = []

        baseline_rate = self.config.spike_test_baseline_rate
        peak_rate = self.config.spike_test_peak_rate
        ramp_time = self.config.spike_test_ramp_time_seconds

        try:
            # Phase 1: Baseline load
            self.logger.info(f"Phase 1: Baseline load at {baseline_rate} signals/sec")
            await self._run_constant_load(engine, baseline_rate, 60, response_times)

            # Phase 2: Ramp up to spike
            self.logger.info(
                f"Phase 2: Ramping up to {peak_rate} signals/sec over {ramp_time}s"
            )
            await self._run_ramping_load(
                engine, baseline_rate, peak_rate, ramp_time, response_times
            )

            # Phase 3: Peak load
            self.logger.info(f"Phase 3: Peak load at {peak_rate} signals/sec")
            await self._run_constant_load(engine, peak_rate, 60, response_times)

            # Phase 4: Ramp down
            self.logger.info(f"Phase 4: Ramping down to {baseline_rate} signals/sec")
            await self._run_ramping_load(
                engine, peak_rate, baseline_rate, ramp_time, response_times
            )

            # Phase 5: Recovery verification
            self.logger.info(
                f"Phase 5: Recovery verification at {baseline_rate} signals/sec"
            )
            await self._run_constant_load(engine, baseline_rate, 60, response_times)

        finally:
            await engine.shutdown()

        # Calculate metrics
        total_time = time.time() - test_start
        total_operations = len(response_times)
        successful_operations = len([rt for rt in response_times if rt > 0])
        failed_operations = len([rt for rt in response_times if rt <= 0])

        error_rate = failed_operations / total_operations if total_operations > 0 else 0
        throughput = successful_operations / total_time if total_time > 0 else 0
        avg_response_time = (
            sum(rt for rt in response_times if rt > 0) / successful_operations
            if successful_operations > 0
            else 0
        )
        peak_response_time = max(response_times) if response_times else 0

        passed = (
            error_rate < 0.1 and avg_response_time < 100
        )  # 10% error rate, <100ms avg

        return LoadTestResult(
            test_name="spike_test",
            passed=passed,
            duration_seconds=total_time,
            total_operations=total_operations,
            successful_operations=successful_operations,
            failed_operations=failed_operations,
            average_response_time_ms=avg_response_time,
            peak_response_time_ms=peak_response_time,
            throughput_ops_per_second=throughput,
            error_rate=error_rate,
            memory_peak_mb=0.0,
            cpu_peak_percent=0.0,
            details={
                "baseline_rate": baseline_rate,
                "peak_rate": peak_rate,
                "phases_completed": 5,
            },
            timestamp=datetime.utcnow(),
        )

    async def run_volume_test(self) -> LoadTestResult:
        """
        Run volume test with large amounts of data to test system capacity.

        This test processes large volumes of market data and trading signals
        to verify the system can handle realistic production data volumes.
        """

        test_start = time.time()
        self.logger.info("Starting volume test - testing large data volumes")

        # Initialize system with larger data set
        config = BotConfig()
        engine = TradingEngine(config)
        await engine.initialize()

        db = DatabaseManager(":memory:")
        await db.initialize()

        total_operations = 0
        successful_operations = 0
        failed_operations = 0
        response_times = []

        market_count = self.config.volume_test_market_count
        duration_minutes = self.config.volume_test_duration_minutes
        steady_rate = self.config.volume_test_steady_rate

        try:
            # Pre-populate database with large dataset
            self.logger.info(
                f"Pre-populating database with data for {market_count} markets"
            )

            # Create orders
            for i in range(market_count * 20):  # 20 orders per market
                order_data = {
                    "id": f"volume_order_{i}",
                    "market_slug": f"volume_market_{i % market_count}",
                    "side": "buy" if i % 2 == 0 else "sell",
                    "size": 100.0 + random.uniform(-50, 50),
                    "price": 0.5 + random.uniform(-0.3, 0.3),
                    "status": "open" if i % 10 < 7 else "filled",
                    "created_at": datetime.utcnow().isoformat(),
                }
                await db.insert_order(order_data)

            # Create positions
            for i in range(market_count * 5):  # 5 positions per market
                position_data = {
                    "token_id": f"0x{i:040x}",
                    "market_slug": f"volume_market_{i % market_count}",
                    "outcome_type": "yes" if i % 2 == 0 else "no",
                    "size": 100.0 + random.uniform(-30, 30),
                    "notional_value": 50.0 + random.uniform(-20, 20),
                    "created_at": datetime.utcnow().isoformat(),
                }
                await db.upsert_position(position_data)

            self.logger.info("Database populated, starting volume processing")

            # Run steady load with diverse operations
            end_time = time.time() + (duration_minutes * 60)

            while time.time() < end_time:
                batch_start = time.time()

                # Mix of operations
                for i in range(steady_rate // 10):  # 100ms batches
                    operation_type = random.choice(
                        [
                            "signal_processing",
                            "database_query",
                            "market_scan",
                            "position_update",
                        ]
                    )

                    op_start = time.time()
                    success = True

                    try:
                        if operation_type == "signal_processing":
                            signal = self._generate_test_signal(total_operations)
                            engine.process_signal(signal)

                        elif operation_type == "database_query":
                            # Random database operations
                            query_type = random.choice(
                                [
                                    "get_total_exposure",
                                    "get_market_exposure",
                                    "get_position_notional",
                                    "get_open_orders",
                                ]
                            )

                            if query_type == "get_total_exposure":
                                await db.get_total_exposure()
                            elif query_type == "get_market_exposure":
                                market = (
                                    f"volume_market_{random.randint(0, market_count-1)}"
                                )
                                await db.get_market_exposure(market)
                            elif query_type == "get_position_notional":
                                token_id = (
                                    f"0x{random.randint(0, market_count*5-1):040x}"
                                )
                                await db.get_position_notional(token_id)
                            else:  # get_open_orders
                                await db.get_open_orders()

                        elif operation_type == "market_scan":
                            # Simulate market scanning
                            market_data = []
                            for j in range(10):
                                market_data.append(
                                    {
                                        "market_slug": f"volume_market_{random.randint(0, market_count-1)}",
                                        "token_id": f"0x{random.randint(0, 999999):040x}",
                                        "bid": 0.3 + random.uniform(0, 0.4),
                                        "ask": 0.5 + random.uniform(0, 0.4),
                                        "spread_bps": random.randint(100, 2000),
                                    }
                                )

                        else:  # position_update
                            # Simulate position update
                            await asyncio.sleep(0.001)  # Small processing delay

                        response_time = (time.time() - op_start) * 1000
                        response_times.append(response_time)
                        successful_operations += 1

                    except Exception as e:
                        failed_operations += 1
                        success = False

                    total_operations += 1

                # Control rate
                batch_time = time.time() - batch_start
                if batch_time < 0.1:
                    await asyncio.sleep(0.1 - batch_time)

        finally:
            await engine.shutdown()

        # Calculate metrics
        total_time = time.time() - test_start
        error_rate = failed_operations / total_operations if total_operations > 0 else 0
        throughput = successful_operations / total_time if total_time > 0 else 0
        avg_response_time = (
            sum(response_times) / len(response_times) if response_times else 0
        )
        peak_response_time = max(response_times) if response_times else 0

        passed = (
            error_rate < 0.05 and avg_response_time < 20
        )  # 5% error rate, <20ms avg

        return LoadTestResult(
            test_name="volume_test",
            passed=passed,
            duration_seconds=total_time,
            total_operations=total_operations,
            successful_operations=successful_operations,
            failed_operations=failed_operations,
            average_response_time_ms=avg_response_time,
            peak_response_time_ms=peak_response_time,
            throughput_ops_per_second=throughput,
            error_rate=error_rate,
            memory_peak_mb=0.0,
            cpu_peak_percent=0.0,
            details={
                "market_count": market_count,
                "duration_minutes": total_time / 60,
                "steady_rate": steady_rate,
            },
            timestamp=datetime.utcnow(),
        )

    async def run_endurance_test(self) -> LoadTestResult:
        """
        Run endurance test for extended periods to test long-term stability.

        This test runs the system under moderate load for extended periods
        to identify memory leaks, resource exhaustion, and other issues
        that only manifest over time.
        """

        test_start = time.time()
        self.logger.info(
            f"Starting endurance test - {self.config.endurance_test_duration_minutes} minutes"
        )

        config = BotConfig()
        engine = TradingEngine(config)
        await engine.initialize()

        total_operations = 0
        successful_operations = 0
        failed_operations = 0
        response_times = []
        memory_samples = []

        duration_seconds = self.config.endurance_test_duration_minutes * 60
        signal_rate = self.config.endurance_test_signal_rate
        memory_check_interval = self.config.endurance_test_memory_check_interval

        end_time = time.time() + duration_seconds
        last_memory_check = time.time()

        try:
            while time.time() < end_time:
                batch_start = time.time()

                # Process signals at steady rate
                batch_size = signal_rate // 10  # 100ms batches

                for i in range(batch_size):
                    signal = self._generate_test_signal(total_operations + i)

                    op_start = time.time()
                    try:
                        engine.process_signal(signal)
                        response_time = (time.time() - op_start) * 1000
                        response_times.append(response_time)
                        successful_operations += 1
                    except Exception as e:
                        failed_operations += 1

                    total_operations += 1

                # Periodic memory check
                if time.time() - last_memory_check > memory_check_interval:
                    try:
                        import psutil

                        process = psutil.Process()
                        memory_mb = process.memory_info().rss / 1024 / 1024
                        memory_samples.append(memory_mb)
                        last_memory_check = time.time()

                        if len(memory_samples) % 5 == 0:
                            elapsed_minutes = (time.time() - test_start) / 60
                            self.logger.info(
                                f"Endurance test: {elapsed_minutes:.1f}min elapsed, "
                                f"memory: {memory_mb:.1f}MB, "
                                f"ops: {total_operations}"
                            )
                    except ImportError:
                        pass  # psutil not available

                # Control rate
                batch_time = time.time() - batch_start
                if batch_time < 0.1:
                    await asyncio.sleep(0.1 - batch_time)

        finally:
            await engine.shutdown()

        # Calculate metrics
        total_time = time.time() - test_start
        error_rate = failed_operations / total_operations if total_operations > 0 else 0
        throughput = successful_operations / total_time if total_time > 0 else 0
        avg_response_time = (
            sum(response_times) / len(response_times) if response_times else 0
        )
        peak_response_time = max(response_times) if response_times else 0
        peak_memory = max(memory_samples) if memory_samples else 0

        # Check for memory growth
        memory_growth = 0
        if len(memory_samples) >= 2:
            initial_memory = sum(memory_samples[:3]) / min(3, len(memory_samples))
            final_memory = sum(memory_samples[-3:]) / min(3, len(memory_samples))
            memory_growth = (
                ((final_memory - initial_memory) / initial_memory) * 100
                if initial_memory > 0
                else 0
            )

        passed = (
            error_rate < 0.01  # 1% error rate
            and avg_response_time < 10  # <10ms average
            and memory_growth < 50
        )  # <50% memory growth

        return LoadTestResult(
            test_name="endurance_test",
            passed=passed,
            duration_seconds=total_time,
            total_operations=total_operations,
            successful_operations=successful_operations,
            failed_operations=failed_operations,
            average_response_time_ms=avg_response_time,
            peak_response_time_ms=peak_response_time,
            throughput_ops_per_second=throughput,
            error_rate=error_rate,
            memory_peak_mb=peak_memory,
            cpu_peak_percent=0.0,
            details={
                "duration_minutes": total_time / 60,
                "memory_growth_percent": memory_growth,
                "memory_samples_count": len(memory_samples),
            },
            timestamp=datetime.utcnow(),
        )

    def _generate_test_signal(self, sequence_id: int) -> TradingSignal:
        """Generate a test trading signal."""
        return TradingSignal(
            market_slug=f"load_test_market_{sequence_id % 100}",
            token_id=f"0x{sequence_id:040x}",
            side="buy" if sequence_id % 2 == 0 else "sell",
            price=0.3 + random.uniform(0, 0.4),
            size=50.0 + random.uniform(0, 100),
            outcome_type="yes" if sequence_id % 3 == 0 else "no",
            signal_id=f"load_test_signal_{sequence_id}",
        )

    async def _process_signal_with_timing(
        self, engine: TradingEngine, signal: TradingSignal
    ) -> tuple:
        """Process a signal and return timing information."""
        start_time = time.time()

        try:
            engine.process_signal(signal)
            response_time = (time.time() - start_time) * 1000
            return response_time, True, None
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return response_time, False, str(e)

    async def _run_constant_load(
        self,
        engine: TradingEngine,
        rate: int,
        duration_seconds: int,
        response_times: List[float],
    ) -> None:
        """Run constant load at specified rate."""
        end_time = time.time() + duration_seconds
        operation_count = 0

        while time.time() < end_time:
            batch_start = time.time()
            batch_size = rate // 10  # 100ms batches

            for i in range(batch_size):
                signal = self._generate_test_signal(operation_count + i)
                response_time, success, error = await self._process_signal_with_timing(
                    engine, signal
                )

                if success:
                    response_times.append(response_time)
                else:
                    response_times.append(-1)  # Mark as failed

                operation_count += 1

            # Control rate
            batch_time = time.time() - batch_start
            if batch_time < 0.1:
                await asyncio.sleep(0.1 - batch_time)

    async def _run_ramping_load(
        self,
        engine: TradingEngine,
        start_rate: int,
        end_rate: int,
        ramp_duration_seconds: int,
        response_times: List[float],
    ) -> None:
        """Run ramping load from start_rate to end_rate over specified duration."""
        ramp_start = time.time()
        ramp_end = ramp_start + ramp_duration_seconds
        operation_count = 0

        while time.time() < ramp_end:
            # Calculate current rate based on progress through ramp
            progress = (time.time() - ramp_start) / ramp_duration_seconds
            current_rate = start_rate + (end_rate - start_rate) * progress

            batch_start = time.time()
            batch_size = max(1, int(current_rate // 10))  # 100ms batches

            for i in range(batch_size):
                signal = self._generate_test_signal(operation_count + i)
                response_time, success, error = await self._process_signal_with_timing(
                    engine, signal
                )

                if success:
                    response_times.append(response_time)
                else:
                    response_times.append(-1)  # Mark as failed

                operation_count += 1

            # Control rate
            batch_time = time.time() - batch_start
            if batch_time < 0.1:
                await asyncio.sleep(0.1 - batch_time)


# Pytest fixtures and tests
@pytest.fixture
def load_test_suite():
    """Create a load test suite."""
    # Use shorter durations for CI/testing
    config = LoadTestConfig()
    config.stress_test_duration_minutes = 2
    config.spike_test_duration_minutes = 2
    config.volume_test_duration_minutes = 3
    config.endurance_test_duration_minutes = 5

    return LoadTestSuite(config)


@pytest.mark.asyncio
@pytest.mark.load_test
@pytest.mark.slow
async def test_stress_test(load_test_suite):
    """Test system under extreme stress conditions."""
    result = await load_test_suite.run_stress_test()

    print(f"\nStress Test Results:")
    print(f"Total operations: {result.total_operations}")
    print(f"Success rate: {(1 - result.error_rate):.1%}")
    print(f"Throughput: {result.throughput_ops_per_second:.1f} ops/sec")
    print(f"Average response time: {result.average_response_time_ms:.2f}ms")

    assert (
        result.passed
    ), f"Stress test failed: error rate {result.error_rate:.1%} too high"


@pytest.mark.asyncio
@pytest.mark.load_test
@pytest.mark.slow
async def test_spike_test(load_test_suite):
    """Test system resilience to traffic spikes."""
    result = await load_test_suite.run_spike_test()

    print(f"\nSpike Test Results:")
    print(f"Total operations: {result.total_operations}")
    print(f"Success rate: {(1 - result.error_rate):.1%}")
    print(f"Average response time: {result.average_response_time_ms:.2f}ms")
    print(f"Peak response time: {result.peak_response_time_ms:.2f}ms")

    assert (
        result.passed
    ), f"Spike test failed: {result.error_rate:.1%} error rate or {result.average_response_time_ms:.1f}ms avg response"


@pytest.mark.asyncio
@pytest.mark.load_test
@pytest.mark.slow
async def test_volume_test(load_test_suite):
    """Test system with large data volumes."""
    result = await load_test_suite.run_volume_test()

    print(f"\nVolume Test Results:")
    print(f"Total operations: {result.total_operations}")
    print(f"Success rate: {(1 - result.error_rate):.1%}")
    print(f"Throughput: {result.throughput_ops_per_second:.1f} ops/sec")
    print(f"Average response time: {result.average_response_time_ms:.2f}ms")

    assert (
        result.passed
    ), f"Volume test failed: {result.error_rate:.1%} error rate or {result.average_response_time_ms:.1f}ms avg response"


@pytest.mark.asyncio
@pytest.mark.load_test
@pytest.mark.slow
async def test_endurance_test(load_test_suite):
    """Test long-term system stability."""
    result = await load_test_suite.run_endurance_test()

    print(f"\nEndurance Test Results:")
    print(f"Duration: {result.details['duration_minutes']:.1f} minutes")
    print(f"Total operations: {result.total_operations}")
    print(f"Success rate: {(1 - result.error_rate):.1%}")
    print(f"Memory peak: {result.memory_peak_mb:.1f}MB")
    print(f"Memory growth: {result.details['memory_growth_percent']:.1f}%")

    assert (
        result.passed
    ), f"Endurance test failed: memory or performance issues detected"


if __name__ == "__main__":

    async def main():
        """Run load tests as standalone script."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        suite = LoadTestSuite()

        print("Running comprehensive load tests...")
        print("=" * 60)

        tests = [
            ("Stress Test", suite.run_stress_test),
            ("Spike Test", suite.run_spike_test),
            ("Volume Test", suite.run_volume_test),
            ("Endurance Test", suite.run_endurance_test),
        ]

        results = {}
        for test_name, test_func in tests:
            print(f"\nRunning {test_name}...")
            try:
                result = await test_func()
                results[test_name] = result
                status = "PASSED" if result.passed else "FAILED"
                print(f"{test_name}: {status}")
                print(f"  Operations: {result.total_operations}")
                print(f"  Success Rate: {(1-result.error_rate):.1%}")
                print(f"  Avg Response: {result.average_response_time_ms:.2f}ms")
                print(f"  Throughput: {result.throughput_ops_per_second:.1f} ops/sec")
            except Exception as e:
                print(f"{test_name}: ERROR - {e}")
                results[test_name] = None

        # Summary
        passed_tests = sum(1 for r in results.values() if r and r.passed)
        total_tests = len(results)

        print("\n" + "=" * 60)
        print(f"LOAD TEST SUMMARY: {passed_tests}/{total_tests} tests passed")

        if passed_tests == total_tests:
            print("✓ All load tests PASSED")
            exit(0)
        else:
            print("✗ Some load tests FAILED")
            exit(1)

    asyncio.run(main())
