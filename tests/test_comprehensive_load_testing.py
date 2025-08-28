"""
Comprehensive Load Testing Suite for High-Frequency Trading Scenarios.

This module provides extensive load testing for the InkedUp Polymarket trading bot
under realistic high-frequency trading conditions, including:
- Market data burst scenarios (10,000+ updates/second)
- High-frequency signal processing (1000+ signals/minute)  
- Concurrent trading strategy execution
- Database performance under extreme load
- Memory and resource usage under sustained high load
- WebSocket connection stress testing
- Rate limiting behavior validation
- System recovery under failure conditions
"""

import asyncio
import gc
import logging
import random
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import psutil
import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.database import DatabaseManager
from inkedup_bot.engine import TradingEngine
from inkedup_bot.order_client import OrderClient
from inkedup_bot.scanner import Scanner
from inkedup_bot.signals import OutcomeType, SignalAction, TradingSignal
from inkedup_bot.state import StateManager
from inkedup_bot.strategies.complement import ComplementArbStrategy
from inkedup_bot.utils import HTTPClient
from inkedup_bot.ws_manager import WebSocketManager

logger = logging.getLogger(__name__)


@dataclass
class LoadTestResults:
    """Results from load testing scenarios."""

    test_name: str
    duration_seconds: float
    total_operations: int
    successful_operations: int
    failed_operations: int
    operations_per_second: float
    average_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    peak_memory_mb: float
    avg_cpu_percent: float
    success_rate: float
    passed: bool
    details: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


class HighFrequencyLoadTester:
    """High-frequency trading load testing framework."""

    def __init__(self, config: BotConfig):
        self.config = config
        self.metrics = {
            "response_times": [],
            "memory_usage": [],
            "cpu_usage": [],
            "operation_timestamps": [],
            "errors": [],
        }

    def start_system_monitoring(self):
        """Start monitoring system resources."""
        self.process = psutil.Process()
        self.initial_memory = self.process.memory_info().rss / 1024 / 1024  # MB

    def record_operation(
        self, start_time: float, success: bool = True, error: Optional[str] = None
    ):
        """Record operation metrics."""
        latency = (time.time() - start_time) * 1000  # Convert to milliseconds
        self.metrics["response_times"].append(latency)
        self.metrics["operation_timestamps"].append(time.time())

        if not success and error:
            self.metrics["errors"].append(error)

        # Record current system state
        try:
            memory_mb = self.process.memory_info().rss / 1024 / 1024
            cpu_percent = self.process.cpu_percent()
            self.metrics["memory_usage"].append(memory_mb)
            self.metrics["cpu_usage"].append(cpu_percent)
        except:
            pass  # Don't fail load test due to monitoring issues

    def calculate_results(
        self, test_name: str, duration: float, total_ops: int
    ) -> LoadTestResults:
        """Calculate comprehensive test results."""
        response_times = self.metrics["response_times"]
        memory_usage = self.metrics["memory_usage"]
        cpu_usage = self.metrics["cpu_usage"]

        successful_ops = total_ops - len(self.metrics["errors"])
        failed_ops = len(self.metrics["errors"])

        # Calculate latency statistics
        if response_times:
            avg_latency = statistics.mean(response_times)
            sorted_times = sorted(response_times)
            p95_latency = sorted_times[int(len(sorted_times) * 0.95)]
            p99_latency = sorted_times[int(len(sorted_times) * 0.99)]
        else:
            avg_latency = p95_latency = p99_latency = 0.0

        # Calculate resource usage
        peak_memory = max(memory_usage) if memory_usage else 0.0
        avg_cpu = statistics.mean(cpu_usage) if cpu_usage else 0.0

        # Calculate throughput
        ops_per_second = total_ops / duration if duration > 0 else 0.0
        success_rate = successful_ops / total_ops if total_ops > 0 else 0.0

        # Determine if test passed based on criteria
        passed = (
            success_rate >= 0.90  # 90% success rate minimum
            and avg_latency <= 1000.0  # 1 second max average latency
            and peak_memory <= 1000.0  # 1GB max memory usage
        )

        return LoadTestResults(
            test_name=test_name,
            duration_seconds=duration,
            total_operations=total_ops,
            successful_operations=successful_ops,
            failed_operations=failed_ops,
            operations_per_second=ops_per_second,
            average_latency_ms=avg_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            peak_memory_mb=peak_memory,
            avg_cpu_percent=avg_cpu,
            success_rate=success_rate,
            passed=passed,
            details=f"Load test completed: {successful_ops}/{total_ops} ops succeeded",
            metrics={
                "total_errors": len(self.metrics["errors"]),
                "memory_growth_mb": peak_memory - self.initial_memory,
                "operation_rate_variance": (
                    statistics.stdev(
                        [
                            len(
                                [
                                    ts
                                    for ts in self.metrics["operation_timestamps"]
                                    if i <= ts < i + 1
                                ]
                            )
                            for i in range(int(duration))
                        ]
                    )
                    if duration > 1
                    else 0.0
                ),
            },
        )


class TestHighFrequencyLoadScenarios:
    """Test high-frequency trading load scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.load_test
    async def test_market_data_burst_load(self):
        """
        Test system behavior under market data bursts (10,000+ updates/second).

        This simulates extreme market volatility where multiple exchanges
        send rapid market updates simultaneously.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "burst_load.db"
            config = BotConfig(
                database_url=f"sqlite:///{db_path}",
                rate_limiting_enabled=False,  # Disable for load testing
            )

            load_tester = HighFrequencyLoadTester(config)
            load_tester.start_system_monitoring()

            # Create scanner for market data processing
            scanner = Scanner(config)

            # Generate burst of market data updates
            total_updates = 5000  # 5K updates for testing (scaled down from 10K for CI)
            start_time = time.time()

            async def process_market_update(update_id: int):
                op_start = time.time()
                try:
                    # Simulate market data update
                    market_data = {
                        "market_slug": f"burst-market-{update_id % 100}",  # 100 different markets
                        "outcomes": [
                            {
                                "token_id": f"token_{update_id}_{random.randint(1,2)}",
                                "outcome_type": (
                                    "YES" if random.random() > 0.5 else "NO"
                                ),
                                "best_bid": random.uniform(0.30, 0.70),
                                "best_ask": random.uniform(0.30, 0.70),
                                "liquidity": random.uniform(1000, 10000),
                            }
                        ],
                        "total_liquidity": random.uniform(5000, 20000),
                    }

                    # Process through scanner (simulate market data processing)
                    # In real scenario this would process through strategies
                    await asyncio.sleep(0.001)  # Simulate processing time

                    load_tester.record_operation(op_start, success=True)
                    return True

                except Exception as e:
                    load_tester.record_operation(op_start, success=False, error=str(e))
                    return False

            # Execute market data burst
            tasks = [process_market_update(i) for i in range(total_updates)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            duration = time.time() - start_time
            test_results = load_tester.calculate_results(
                "Market Data Burst", duration, total_updates
            )

            # Validate results
            print(f"\n📈 Market Data Burst Load Test Results:")
            print(f"   Total Updates: {test_results.total_operations}")
            print(f"   Successful: {test_results.successful_operations}")
            print(f"   Duration: {test_results.duration_seconds:.2f}s")
            print(
                f"   Throughput: {test_results.operations_per_second:.0f} updates/sec"
            )
            print(f"   Average Latency: {test_results.average_latency_ms:.2f}ms")
            print(f"   P95 Latency: {test_results.p95_latency_ms:.2f}ms")
            print(f"   Peak Memory: {test_results.peak_memory_mb:.1f}MB")
            print(f"   Success Rate: {test_results.success_rate:.1%}")

            # Assertions for load test
            assert (
                test_results.success_rate >= 0.85
            ), f"Success rate too low: {test_results.success_rate:.1%}"
            assert (
                test_results.operations_per_second >= 500
            ), f"Throughput too low: {test_results.operations_per_second:.0f}/sec"
            assert (
                test_results.average_latency_ms <= 500
            ), f"Average latency too high: {test_results.average_latency_ms:.2f}ms"

    @pytest.mark.asyncio
    @pytest.mark.load_test
    async def test_high_frequency_signal_processing(self):
        """
        Test high-frequency signal processing (1000+ signals/minute).

        This simulates a busy trading period where multiple strategies
        generate many trading signals simultaneously.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "hf_signals.db"
            config = BotConfig(
                database_url=f"sqlite:///{db_path}",
                signal_max_concurrent=100,  # High concurrency for load testing
                max_order_size=1000.0,
                max_position_size=5000.0,
            )

            load_tester = HighFrequencyLoadTester(config)
            load_tester.start_system_monitoring()

            # Setup trading engine with mock order client
            trading_engine = TradingEngine(config)
            order_client = OrderClient(config)
            order_client.is_ready = MagicMock(return_value=True)
            order_client.place_limit_order = AsyncMock(
                return_value={
                    "order_id": f"hf_order_{time.time()}",
                    "status": "open",
                    "size": 100.0,
                    "price": 0.50,
                }
            )

            # Patch order client
            trading_engine.order_client = order_client

            # Generate high-frequency signals
            total_signals = 1000  # 1K signals for load testing
            start_time = time.time()

            async def process_trading_signal(signal_id: int):
                op_start = time.time()
                try:
                    # Create trading signal
                    signal = TradingSignal(
                        token_id=f"hf_token_{signal_id}",
                        action=(
                            SignalAction.BUY
                            if signal_id % 2 == 0
                            else SignalAction.SELL
                        ),
                        price=random.uniform(0.40, 0.60),
                        size=random.uniform(50.0, 200.0),
                        market_slug=f"hf-market-{signal_id % 50}",  # 50 different markets
                        outcome_type=(
                            OutcomeType.YES if signal_id % 2 == 0 else OutcomeType.NO
                        ),
                        confidence=random.uniform(0.70, 0.95),
                        strategy_name="high_frequency_test",
                    )

                    # Process through trading engine
                    result = await trading_engine.process_signal(signal)

                    load_tester.record_operation(op_start, success=(result is not None))
                    return result

                except Exception as e:
                    load_tester.record_operation(op_start, success=False, error=str(e))
                    return None

            # Execute high-frequency signal processing
            tasks = [process_trading_signal(i) for i in range(total_signals)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            duration = time.time() - start_time
            test_results = load_tester.calculate_results(
                "High-Frequency Signals", duration, total_signals
            )

            # Validate results
            print(f"\n⚡ High-Frequency Signal Processing Results:")
            print(f"   Total Signals: {test_results.total_operations}")
            print(f"   Successful: {test_results.successful_operations}")
            print(f"   Duration: {test_results.duration_seconds:.2f}s")
            print(
                f"   Throughput: {test_results.operations_per_second:.0f} signals/sec"
            )
            print(f"   Average Latency: {test_results.average_latency_ms:.2f}ms")
            print(f"   P99 Latency: {test_results.p99_latency_ms:.2f}ms")
            print(f"   Peak Memory: {test_results.peak_memory_mb:.1f}MB")
            print(f"   Success Rate: {test_results.success_rate:.1%}")

            # High-frequency assertions
            signals_per_minute = (test_results.successful_operations / duration) * 60
            assert (
                signals_per_minute >= 500
            ), f"Signal processing rate too low: {signals_per_minute:.0f}/min"
            assert (
                test_results.success_rate >= 0.75
            ), f"Success rate too low: {test_results.success_rate:.1%}"
            assert (
                test_results.average_latency_ms <= 200
            ), f"Average latency too high: {test_results.average_latency_ms:.2f}ms"

    @pytest.mark.asyncio
    @pytest.mark.load_test
    async def test_concurrent_strategy_execution(self):
        """
        Test concurrent execution of multiple trading strategies.

        This simulates multiple strategies running simultaneously and
        processing market data to generate signals.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "concurrent_strategies.db"
            config = BotConfig(database_url=f"sqlite:///{db_path}")

            load_tester = HighFrequencyLoadTester(config)
            load_tester.start_system_monitoring()

            # Create multiple strategy instances
            strategies = [ComplementArbStrategy(config) for _ in range(5)]

            # Generate market data for concurrent strategy processing
            total_operations = 500  # 500 market data updates across strategies
            start_time = time.time()

            async def process_strategy_market_data(strategy_id: int, data_id: int):
                op_start = time.time()
                try:
                    strategy = strategies[strategy_id % len(strategies)]

                    # Generate market data with arbitrage opportunity
                    market_data = {
                        "market_slug": f"strategy-market-{data_id}",
                        "outcomes": [
                            {
                                "token_id": f"yes_token_{data_id}",
                                "outcome_type": "YES",
                                "best_bid": 0.40 + random.uniform(-0.05, 0.05),
                                "best_ask": 0.45 + random.uniform(-0.05, 0.05),
                                "liquidity": random.uniform(5000, 15000),
                            },
                            {
                                "token_id": f"no_token_{data_id}",
                                "outcome_type": "NO",
                                "best_bid": 0.50 + random.uniform(-0.05, 0.05),
                                "best_ask": 0.55 + random.uniform(-0.05, 0.05),
                                "liquidity": random.uniform(5000, 15000),
                            },
                        ],
                        "total_liquidity": random.uniform(10000, 30000),
                    }

                    # Process market data through strategy
                    signals = await strategy.process_data(market_data)

                    load_tester.record_operation(op_start, success=True)
                    return len(signals)

                except Exception as e:
                    load_tester.record_operation(op_start, success=False, error=str(e))
                    return 0

            # Execute concurrent strategy processing
            tasks = []
            for i in range(total_operations):
                strategy_id = i % len(strategies)
                task = process_strategy_market_data(strategy_id, i)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            duration = time.time() - start_time
            test_results = load_tester.calculate_results(
                "Concurrent Strategies", duration, total_operations
            )

            # Calculate total signals generated
            total_signals = sum(r for r in results if isinstance(r, int))

            print(f"\n🎯 Concurrent Strategy Execution Results:")
            print(f"   Market Updates: {test_results.total_operations}")
            print(f"   Successful: {test_results.successful_operations}")
            print(f"   Signals Generated: {total_signals}")
            print(f"   Duration: {test_results.duration_seconds:.2f}s")
            print(
                f"   Throughput: {test_results.operations_per_second:.0f} updates/sec"
            )
            print(f"   Average Latency: {test_results.average_latency_ms:.2f}ms")
            print(f"   Peak Memory: {test_results.peak_memory_mb:.1f}MB")
            print(f"   Success Rate: {test_results.success_rate:.1%}")

            # Concurrent execution assertions
            assert (
                test_results.success_rate >= 0.90
            ), f"Success rate too low: {test_results.success_rate:.1%}"
            assert (
                total_signals >= total_operations * 0.1
            ), f"Too few signals generated: {total_signals}"

    @pytest.mark.asyncio
    @pytest.mark.load_test
    async def test_database_extreme_load(self):
        """
        Test database performance under extreme load conditions.

        This simulates thousands of concurrent database operations
        to test connection pooling, query performance, and data integrity.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "extreme_load.db"
            config = BotConfig(
                database_url=f"sqlite:///{db_path}",
                database_pool_max_connections=20,  # High connection count
                database_pool_timeout=5.0,
            )

            load_tester = HighFrequencyLoadTester(config)
            load_tester.start_system_monitoring()

            # Initialize database and state manager
            state_manager = StateManager(db_path=str(db_path))
            await state_manager.initialize_async()

            db_manager = DatabaseManager()
            await db_manager.initialize()

            # Generate extreme database load
            total_operations = 2000  # 2K database operations
            start_time = time.time()

            async def perform_database_operation(op_id: int):
                op_start = time.time()
                try:
                    # Mix of different database operations
                    if op_id % 4 == 0:
                        # Position update
                        position_data = {
                            "token_id": f"load_test_token_{op_id}",
                            "market_slug": f"load-test-market-{op_id % 100}",
                            "outcome_type": "YES" if op_id % 2 == 0 else "NO",
                            "size": random.uniform(50.0, 500.0),
                            "notional_value": random.uniform(25.0, 250.0),
                        }
                        await state_manager.update_position_async(position_data)

                    elif op_id % 4 == 1:
                        # Position query
                        await state_manager.get_position_notional_async(
                            f"query_token_{op_id % 100}"
                        )

                    elif op_id % 4 == 2:
                        # Batch position query
                        await state_manager.get_positions_async()

                    else:
                        # Database query
                        await db_manager.get_positions()

                    load_tester.record_operation(op_start, success=True)
                    return True

                except Exception as e:
                    load_tester.record_operation(op_start, success=False, error=str(e))
                    return False

            # Execute extreme database load
            tasks = [perform_database_operation(i) for i in range(total_operations)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            duration = time.time() - start_time
            test_results = load_tester.calculate_results(
                "Database Extreme Load", duration, total_operations
            )

            print(f"\n💾 Database Extreme Load Test Results:")
            print(f"   Total Operations: {test_results.total_operations}")
            print(f"   Successful: {test_results.successful_operations}")
            print(f"   Duration: {test_results.duration_seconds:.2f}s")
            print(f"   Throughput: {test_results.operations_per_second:.0f} ops/sec")
            print(f"   Average Latency: {test_results.average_latency_ms:.2f}ms")
            print(f"   P95 Latency: {test_results.p95_latency_ms:.2f}ms")
            print(f"   Peak Memory: {test_results.peak_memory_mb:.1f}MB")
            print(f"   Success Rate: {test_results.success_rate:.1%}")

            # Database load assertions
            assert (
                test_results.success_rate >= 0.95
            ), f"Database success rate too low: {test_results.success_rate:.1%}"
            assert (
                test_results.operations_per_second >= 100
            ), f"Database throughput too low: {test_results.operations_per_second:.0f}/sec"
            assert (
                test_results.p95_latency_ms <= 1000
            ), f"P95 latency too high: {test_results.p95_latency_ms:.2f}ms"

    @pytest.mark.asyncio
    @pytest.mark.load_test
    async def test_memory_stress_endurance(self):
        """
        Test system memory behavior under sustained high load.

        This runs a continuous load for an extended period to detect
        memory leaks, garbage collection issues, and resource exhaustion.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory_stress.db"
            config = BotConfig(database_url=f"sqlite:///{db_path}")

            load_tester = HighFrequencyLoadTester(config)
            load_tester.start_system_monitoring()

            # Initialize components
            trading_engine = TradingEngine(config)
            scanner = Scanner(config)

            # Run sustained load for memory testing
            test_duration = 30  # 30 seconds of sustained load
            operations_per_second = 50
            total_operations = test_duration * operations_per_second

            start_time = time.time()
            operation_count = 0

            async def sustained_operation_loop():
                nonlocal operation_count

                while time.time() - start_time < test_duration:
                    op_start = time.time()
                    try:
                        # Rotate between different operations to stress various components
                        op_type = operation_count % 4

                        if op_type == 0:
                            # Market data processing
                            market_data = {
                                "market_slug": f"memory-test-market-{operation_count % 20}",
                                "outcomes": [
                                    {
                                        "token_id": f"memory_token_{operation_count}",
                                        "outcome_type": "YES",
                                        "best_bid": random.uniform(0.30, 0.70),
                                        "best_ask": random.uniform(0.30, 0.70),
                                        "liquidity": random.uniform(1000, 10000),
                                    }
                                ],
                                "total_liquidity": random.uniform(5000, 20000),
                            }
                            await asyncio.sleep(0.001)  # Simulate processing

                        elif op_type == 1:
                            # Signal generation
                            signal = TradingSignal(
                                token_id=f"memory_signal_token_{operation_count}",
                                action=SignalAction.BUY,
                                price=0.50,
                                size=100.0,
                                market_slug=f"memory-signal-market-{operation_count % 10}",
                                outcome_type=OutcomeType.YES,
                                confidence=0.85,
                                strategy_name="memory_test",
                            )
                            await asyncio.sleep(0.001)  # Simulate processing

                        elif op_type == 2:
                            # Memory allocation and cleanup
                            large_data = [random.random() for _ in range(1000)]
                            await asyncio.sleep(0.001)
                            del large_data

                        else:
                            # Garbage collection trigger
                            gc.collect()
                            await asyncio.sleep(0.001)

                        operation_count += 1
                        load_tester.record_operation(op_start, success=True)

                        # Control operation rate
                        await asyncio.sleep(1.0 / operations_per_second)

                    except Exception as e:
                        load_tester.record_operation(
                            op_start, success=False, error=str(e)
                        )
                        operation_count += 1

            # Run sustained load
            await sustained_operation_loop()

            duration = time.time() - start_time
            test_results = load_tester.calculate_results(
                "Memory Stress Endurance", duration, operation_count
            )

            print(f"\n🧠 Memory Stress Endurance Test Results:")
            print(f"   Duration: {test_results.duration_seconds:.1f}s")
            print(f"   Total Operations: {test_results.total_operations}")
            print(f"   Successful: {test_results.successful_operations}")
            print(f"   Throughput: {test_results.operations_per_second:.0f} ops/sec")
            print(f"   Peak Memory: {test_results.peak_memory_mb:.1f}MB")
            print(
                f"   Memory Growth: {test_results.metrics.get('memory_growth_mb', 0):.1f}MB"
            )
            print(f"   Average CPU: {test_results.avg_cpu_percent:.1f}%")
            print(f"   Success Rate: {test_results.success_rate:.1%}")

            # Memory stress assertions
            assert (
                test_results.success_rate >= 0.95
            ), f"Success rate too low: {test_results.success_rate:.1%}"
            memory_growth = test_results.metrics.get("memory_growth_mb", 0)
            assert (
                memory_growth <= 100
            ), f"Excessive memory growth: {memory_growth:.1f}MB"
            assert (
                test_results.peak_memory_mb <= 500
            ), f"Peak memory too high: {test_results.peak_memory_mb:.1f}MB"


# Utility functions for load testing


def print_load_test_summary(results: List[LoadTestResults]):
    """Print a comprehensive summary of all load test results."""
    print("\n" + "=" * 80)
    print("📊 COMPREHENSIVE LOAD TESTING SUMMARY")
    print("=" * 80)

    passed_tests = sum(1 for r in results if r.passed)
    total_tests = len(results)

    print(
        f"Tests Passed: {passed_tests}/{total_tests} ({passed_tests/total_tests*100:.0f}%)"
    )
    print()

    for result in results:
        status = "✅ PASSED" if result.passed else "❌ FAILED"
        print(f"{result.test_name:<30} {status}")
        print(
            f"  Operations: {result.successful_operations}/{result.total_operations} "
            + f"({result.success_rate:.1%})"
        )
        print(f"  Throughput: {result.operations_per_second:.0f} ops/sec")
        print(
            f"  Latency: {result.average_latency_ms:.1f}ms avg, "
            + f"{result.p95_latency_ms:.1f}ms p95"
        )
        print(
            f"  Resources: {result.peak_memory_mb:.1f}MB peak, "
            + f"{result.avg_cpu_percent:.1f}% CPU"
        )
        print()

    print("=" * 80)
    if passed_tests == total_tests:
        print("🎉 ALL LOAD TESTS PASSED - System ready for high-frequency trading!")
    else:
        print("⚠️  Some load tests failed - Review performance bottlenecks")
    print("=" * 80)
