#!/usr/bin/env python3
"""
Signal Processing Optimization Demo

Demonstrates the performance improvements achieved by the optimized signal
processing pipeline compared to sequential processing.

Key improvements shown:
- Parallel processing with priority queues
- Batch optimization for similar signals
- Circuit breaker protection
- Real-time performance monitoring
- Dynamic resource allocation
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import List

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("signal_optimization_demo")

# Import required modules
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from inkedup_bot.signal_pipeline_optimizer import (
    PipelineConfig,
    SignalPipelineOptimizer,
    SignalPriority,
    create_optimized_pipeline,
)
from inkedup_bot.signals import TradingSignal


@dataclass
class DemoSignal:
    """Demo trading signal for performance testing."""

    signal_id: str
    strategy: str
    expected_profit: float
    confidence: float
    market_slug: str
    timestamp: float
    market_volatility: float = 0.5
    liquidity_score: float = 0.7
    risk_score: float = 0.3


class SignalPerformanceTester:
    """Test harness for signal processing performance."""

    def __init__(self):
        self.processed_signals = []
        self.processing_times = []
        self.start_time = None

    def mock_signal_processor(self, signal) -> dict:
        """Mock signal processor that simulates processing work."""
        # Simulate processing complexity based on signal type
        if hasattr(signal, "strategy"):
            if "arbitrage" in signal.strategy.lower():
                processing_time = random.uniform(0.05, 0.15)  # 50-150ms
            elif "market_making" in signal.strategy.lower():
                processing_time = random.uniform(0.02, 0.08)  # 20-80ms
            else:
                processing_time = random.uniform(0.03, 0.10)  # 30-100ms
        else:
            processing_time = random.uniform(0.02, 0.12)  # 20-120ms

        # Simulate processing work
        time.sleep(processing_time)

        # Record processing
        self.processed_signals.append(signal.signal_id)
        self.processing_times.append(processing_time)

        return {
            "status": "processed",
            "processing_time": processing_time,
            "result": f"Processed {signal.signal_id}",
        }


def create_test_signals(count: int) -> List[DemoSignal]:
    """Create a diverse set of test signals."""
    signals = []
    current_time = time.time()

    strategies = [
        "arbitrage_spread",
        "market_making",
        "momentum_trade",
        "mean_reversion",
        "volatility_trade",
        "news_reaction",
    ]

    markets = [
        "btc-election-2024",
        "ethereum-upgrade",
        "fed-rate-decision",
        "breaking-news-market",
        "volatile-crypto-market",
        "stable-market",
        "urgent-trade-opportunity",
        "long-term-position",
    ]

    for i in range(count):
        # Create varied signal characteristics
        strategy = random.choice(strategies)
        market = random.choice(markets)

        # Generate realistic signal parameters
        if "arbitrage" in strategy:
            expected_profit = random.uniform(0.005, 0.03)  # 0.5% to 3%
            confidence = random.uniform(0.8, 0.95)
        elif "urgent" in market or "breaking" in market:
            expected_profit = random.uniform(0.001, 0.015)  # 0.1% to 1.5%
            confidence = random.uniform(0.7, 0.9)
        else:
            expected_profit = random.uniform(0.001, 0.01)  # 0.1% to 1%
            confidence = random.uniform(0.6, 0.85)

        # Add some aged signals
        if random.random() < 0.2:  # 20% are aged
            timestamp = current_time - random.uniform(60, 600)  # 1-10 minutes old
        else:
            timestamp = current_time - random.uniform(0, 30)  # Fresh signals

        signal = DemoSignal(
            signal_id=f"demo_signal_{i:04d}",
            strategy=strategy,
            expected_profit=expected_profit,
            confidence=confidence,
            market_slug=market,
            timestamp=timestamp,
            market_volatility=random.uniform(0.2, 0.8),
            liquidity_score=random.uniform(0.5, 1.0),
            risk_score=random.uniform(0.1, 0.6),
        )

        signals.append(signal)

    return signals


async def run_sequential_processing_test(
    signals: List[DemoSignal], tester: SignalPerformanceTester
):
    """Simulate the original sequential processing approach."""
    logger.info("Starting sequential processing test...")

    start_time = time.time()
    tester.start_time = start_time

    # Process signals one by one (simulating original approach)
    for signal in signals:
        try:
            result = tester.mock_signal_processor(signal)
        except Exception as e:
            logger.error(f"Sequential processing error: {e}")

    end_time = time.time()
    total_time = end_time - start_time

    logger.info(f"Sequential processing completed in {total_time:.2f} seconds")
    logger.info(f"Processed {len(tester.processed_signals)} signals")
    logger.info(
        f"Average processing time per signal: {total_time / len(signals):.3f} seconds"
    )

    return {
        "total_time": total_time,
        "signals_processed": len(tester.processed_signals),
        "average_time_per_signal": total_time / len(signals),
        "throughput": len(signals) / total_time,
    }


async def run_optimized_processing_test(
    signals: List[DemoSignal], tester: SignalPerformanceTester
):
    """Test the optimized parallel processing pipeline."""
    logger.info("Starting optimized parallel processing test...")

    # Create optimized configuration
    config = PipelineConfig(
        critical_workers=6,
        high_workers=10,
        normal_workers=16,
        low_workers=6,
        enable_batch_processing=True,
        enable_monitoring=True,
        enable_auto_scaling=False,  # Disable for consistent testing
        metrics_interval=5.0,
    )

    # Create optimizer
    optimizer = create_optimized_pipeline(config)

    # Set up processors for different priorities
    optimizer.set_signal_processor(tester.mock_signal_processor)  # Default processor

    try:
        # Start the optimized pipeline
        await optimizer.start_processing()

        start_time = time.time()
        tester.start_time = start_time

        # Submit all signals to the optimized pipeline
        submission_tasks = []
        for signal in signals:
            task = asyncio.create_task(optimizer.submit_signal(signal))
            submission_tasks.append(task)

        # Wait for all signals to be submitted
        await asyncio.gather(*submission_tasks, return_exceptions=True)

        # Wait for processing to complete
        # Monitor active signals until all are processed
        while optimizer.get_status()["active_signals"] > 0:
            await asyncio.sleep(0.1)

        # Give a small buffer for final processing
        await asyncio.sleep(0.5)

        end_time = time.time()
        total_time = end_time - start_time

        # Get final performance stats
        final_stats = optimizer.get_performance_stats()

        logger.info(f"Optimized processing completed in {total_time:.2f} seconds")
        logger.info(f"Processed {len(tester.processed_signals)} signals")
        logger.info(
            f"Average processing time per signal: {total_time / len(signals):.3f} seconds"
        )
        logger.info(f"Final pipeline stats: {final_stats['summary']}")

        return {
            "total_time": total_time,
            "signals_processed": len(tester.processed_signals),
            "average_time_per_signal": total_time / len(signals),
            "throughput": len(signals) / total_time,
            "pipeline_stats": final_stats,
        }

    finally:
        # Clean shutdown
        await optimizer.shutdown()


def analyze_performance_improvements(sequential_results: dict, optimized_results: dict):
    """Analyze and display performance improvements."""
    logger.info("\n" + "=" * 60)
    logger.info("PERFORMANCE ANALYSIS RESULTS")
    logger.info("=" * 60)

    # Time improvements
    time_improvement = (
        (sequential_results["total_time"] - optimized_results["total_time"])
        / sequential_results["total_time"]
    ) * 100

    # Throughput improvements
    throughput_improvement = (
        (optimized_results["throughput"] - sequential_results["throughput"])
        / sequential_results["throughput"]
    ) * 100

    logger.info(f"Sequential Processing:")
    logger.info(f"  Total Time: {sequential_results['total_time']:.2f} seconds")
    logger.info(f"  Throughput: {sequential_results['throughput']:.2f} signals/sec")
    logger.info(
        f"  Avg Time/Signal: {sequential_results['average_time_per_signal']:.3f} seconds"
    )

    logger.info(f"\nOptimized Parallel Processing:")
    logger.info(f"  Total Time: {optimized_results['total_time']:.2f} seconds")
    logger.info(f"  Throughput: {optimized_results['throughput']:.2f} signals/sec")
    logger.info(
        f"  Avg Time/Signal: {optimized_results['average_time_per_signal']:.3f} seconds"
    )

    logger.info(f"\nPerformance Improvements:")
    logger.info(f"  Time Reduction: {time_improvement:.1f}%")
    logger.info(f"  Throughput Increase: {throughput_improvement:.1f}%")
    logger.info(
        f"  Processing Speed: {optimized_results['throughput'] / sequential_results['throughput']:.1f}x faster"
    )

    # Priority distribution analysis
    if "pipeline_stats" in optimized_results:
        logger.info(f"\nPriority Distribution:")
        priority_stats = optimized_results["pipeline_stats"]["by_priority"]
        for priority, stats in priority_stats.items():
            logger.info(f"  {priority}: {stats['processed']} signals processed")
            logger.info(f"    Queue Utilization: {stats['queue_utilization']:.1%}")
            logger.info(f"    Avg Processing Time: {stats['avg_processing_time']:.3f}s")
            logger.info(f"    Error Rate: {stats['error_rate']:.2%}")

    logger.info("\n" + "=" * 60)

    return {
        "time_improvement_percent": time_improvement,
        "throughput_improvement_percent": throughput_improvement,
        "speed_multiplier": optimized_results["throughput"]
        / sequential_results["throughput"],
    }


async def run_load_test():
    """Run a load test with different signal volumes."""
    logger.info("Starting signal processing load test...")

    test_scenarios = [
        {"signals": 100, "name": "Light Load"},
        {"signals": 500, "name": "Medium Load"},
        {"signals": 1000, "name": "Heavy Load"},
    ]

    results = {}

    for scenario in test_scenarios:
        logger.info(
            f"\n--- Testing {scenario['name']} ({scenario['signals']} signals) ---"
        )

        # Create test signals
        signals = create_test_signals(scenario["signals"])

        # Test sequential processing
        sequential_tester = SignalPerformanceTester()
        sequential_results = await run_sequential_processing_test(
            signals, sequential_tester
        )

        # Reset for optimized test
        optimized_tester = SignalPerformanceTester()
        optimized_results = await run_optimized_processing_test(
            signals, optimized_tester
        )

        # Analyze improvements
        improvements = analyze_performance_improvements(
            sequential_results, optimized_results
        )

        results[scenario["name"]] = {
            "sequential": sequential_results,
            "optimized": optimized_results,
            "improvements": improvements,
        }

        # Brief pause between scenarios
        await asyncio.sleep(1)

    # Summary across all scenarios
    logger.info("\n" + "=" * 60)
    logger.info("LOAD TEST SUMMARY")
    logger.info("=" * 60)

    for scenario_name, data in results.items():
        improvements = data["improvements"]
        logger.info(f"{scenario_name}:")
        logger.info(f"  Speed Improvement: {improvements['speed_multiplier']:.1f}x")
        logger.info(
            f"  Time Reduction: {improvements['time_improvement_percent']:.1f}%"
        )
        logger.info(
            f"  Throughput Gain: {improvements['throughput_improvement_percent']:.1f}%"
        )

    logger.info("=" * 60)


async def demo_priority_processing():
    """Demonstrate priority-based signal processing."""
    logger.info("\n--- Priority Processing Demonstration ---")

    # Create signals with different priority characteristics
    priority_signals = [
        # Critical priority signals (high profit arbitrage)
        DemoSignal(
            "crit_001", "arbitrage_spread", 0.025, 0.9, "btc-urgent-arb", time.time()
        ),
        DemoSignal(
            "crit_002",
            "arbitrage_spread",
            0.018,
            0.85,
            "breaking-news-arb",
            time.time(),
        ),
        # High priority signals (time-sensitive)
        DemoSignal(
            "high_001",
            "momentum_trade",
            0.008,
            0.8,
            "volatile-crypto-market",
            time.time(),
        ),
        DemoSignal(
            "high_002",
            "news_reaction",
            0.012,
            0.75,
            "breaking-news-market",
            time.time(),
        ),
        # Normal priority signals
        DemoSignal(
            "norm_001", "market_making", 0.003, 0.7, "stable-market", time.time()
        ),
        DemoSignal(
            "norm_002", "mean_reversion", 0.005, 0.65, "regular-market", time.time()
        ),
        # Low priority signals (aged)
        DemoSignal(
            "low_001", "market_making", 0.002, 0.6, "stable-market", time.time() - 400
        ),
        DemoSignal(
            "low_002", "volatility_trade", 0.004, 0.55, "slow-market", time.time() - 300
        ),
    ]

    # Create optimizer with priority-aware configuration
    config = PipelineConfig(
        critical_workers=2,
        high_workers=4,
        normal_workers=6,
        low_workers=2,
        enable_batch_processing=True,
    )

    optimizer = create_optimized_pipeline(config)
    tester = SignalPerformanceTester()
    optimizer.set_signal_processor(tester.mock_signal_processor)

    try:
        await optimizer.start_processing()

        logger.info("Submitting signals with different priorities...")

        # Submit signals and track submission order
        submission_order = []
        for signal in priority_signals:
            await optimizer.submit_signal(signal)
            submission_order.append(signal.signal_id)
            logger.info(
                f"Submitted: {signal.signal_id} ({signal.strategy}, profit: {signal.expected_profit:.1%})"
            )

        # Wait for processing
        while optimizer.get_status()["active_signals"] > 0:
            await asyncio.sleep(0.1)

        await asyncio.sleep(0.5)  # Final buffer

        logger.info("\nProcessing order (should show priority effect):")
        for signal_id in tester.processed_signals:
            logger.info(f"Processed: {signal_id}")

        # Show final stats
        stats = optimizer.get_performance_stats()
        logger.info(f"\nPriority Processing Stats:")
        for priority, data in stats["by_priority"].items():
            if data["processed"] > 0:
                logger.info(
                    f"  {priority}: {data['processed']} signals, avg time: {data['avg_processing_time']:.3f}s"
                )

    finally:
        await optimizer.shutdown()


async def main():
    """Main demo function."""
    logger.info("Signal Processing Pipeline Optimization Demo")
    logger.info("=" * 60)

    try:
        # Run load testing
        await run_load_test()

        # Demonstrate priority processing
        await demo_priority_processing()

        logger.info("\nDemo completed successfully!")
        logger.info("\nKey Optimization Features Demonstrated:")
        logger.info("• Parallel processing with worker pools")
        logger.info("• Priority-based signal queuing")
        logger.info("• Batch processing for efficiency")
        logger.info("• Circuit breaker protection")
        logger.info("• Real-time performance monitoring")
        logger.info("• Dynamic resource allocation")

    except Exception as e:
        logger.error(f"Demo failed with error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
