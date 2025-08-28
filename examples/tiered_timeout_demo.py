#!/usr/bin/env python3
"""
Demonstration of the tiered timeout system in the Enhanced Signal Processor.

This example shows how different types of signals get different processing timeouts
based on their urgency characteristics.
"""

import asyncio

# Import the signal processor components
import sys
import time
from dataclasses import dataclass

sys.path.append("/home/ink/polymarket-inkedup")

from inkedup_bot.enhanced_signal_processor import (
    EnhancedSignalProcessor,
    ProcessingConfig,
    ProcessingResult,
)


@dataclass
class MockTradingSignal:
    """Mock trading signal for demonstration."""

    signal_id: str = None
    market_slug: str = "test-market"
    token_id: str = "test-token"
    side: str = "BUY"
    size: float = 10.0
    price: float = 0.5
    outcome_type: str = "YES"
    created_at: float = None

    # Urgency indicators for demonstration
    signal_type: str = None
    complement_deviation: float = None
    market_volatility: float = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()


async def demonstrate_tiered_timeouts():
    """Demonstrate how different signals get different timeout tiers."""

    print("🚀 Enhanced Signal Processor - Tiered Timeout System Demo")
    print("=" * 60)

    # Create processor with tiered timeouts
    config = ProcessingConfig(
        critical_timeout=5,
        high_timeout=15,
        normal_timeout=30,
        low_timeout=45,
        # Disable market assessment for demo
        require_market_assessment=False,
        min_quality_score=0.0,  # Lower for demo
        min_acceptable_score=0.0,
    )

    processor = EnhancedSignalProcessor(config)

    print(f"Timeout Configuration:")
    timeout_config = processor.get_timeout_configuration()
    for tier, timeout in timeout_config.items():
        print(f"  {tier}: {timeout}s")
    print()

    # Test signals with different urgency characteristics
    test_signals = [
        # CRITICAL: Large arbitrage opportunity
        MockTradingSignal(
            signal_id="critical_arb_001",
            signal_type="complement_arb",
            complement_deviation=0.025,  # 2.5% deviation - very urgent
            price=0.05,  # Near extreme - time sensitive
            size=150.0,  # Large size
        ),
        # HIGH: Arbitrage with medium deviation
        MockTradingSignal(
            signal_id="high_arb_002",
            signal_type="arbitrage",
            complement_deviation=0.015,  # 1.5% deviation
            market_volatility=0.9,  # High volatility
            size=75.0,
        ),
        # NORMAL: Regular trading signal
        MockTradingSignal(
            signal_id="normal_signal_003",
            signal_type="trend_following",
            complement_deviation=0.008,  # Small deviation
            market_volatility=0.4,
            size=25.0,
        ),
        # LOW: Low urgency signal
        MockTradingSignal(
            signal_id="low_priority_004",
            signal_type="mean_reversion",
            complement_deviation=0.003,  # Very small deviation
            market_volatility=0.2,
            size=10.0,
            created_at=time.time() - 120,  # Old signal (2 minutes)
        ),
    ]

    print("Processing signals with urgency-based timeouts...\n")

    # Process each signal and show timeout determination
    results = []
    for signal in test_signals:
        print(f"Signal: {signal.signal_id}")
        print(f"  Type: {signal.signal_type}")
        print(
            f"  Deviation: {signal.complement_deviation:.1%}"
            if signal.complement_deviation
            else "  Deviation: N/A"
        )
        print(
            f"  Volatility: {signal.market_volatility:.1f}"
            if signal.market_volatility
            else "  Volatility: N/A"
        )
        print(f"  Size: ${signal.size:.0f}")
        print(f"  Age: {time.time() - signal.created_at:.1f}s")

        # Determine timeout (we'll call the internal method for demo)
        timeout = processor._determine_processing_timeout(signal)
        print(f"  → Assigned timeout: {timeout}s")

        # Process the signal
        start_time = time.time()
        result = await processor.process_signal(signal)
        processing_time = time.time() - start_time

        print(f"  → Processing time: {processing_time:.3f}s")
        print(f"  → Status: {result.status}")
        print(f"  → Priority: {result.priority}")
        print()

        results.append(result)

    # Show processing statistics
    print("Processing Statistics:")
    stats = processor.get_processing_stats()

    print(f"  Total processed: {stats['total_processed']}")
    print(f"  Approval rate: {stats.get('approval_rate', 0):.1%}")
    print(f"  Average processing time: {stats['avg_processing_time']:.3f}s")
    print()

    print("Timeout Tier Usage:")
    print(f"  Critical (5s): {stats['critical_timeouts_used']}")
    print(f"  High (15s): {stats['high_timeouts_used']}")
    print(f"  Normal (30s): {stats['normal_timeouts_used']}")
    print(f"  Low (45s): {stats['low_timeouts_used']}")

    if stats.get("avg_timeout_saved"):
        print(f"  Average timeout saved: {stats['avg_timeout_saved']:.1f}s per signal")

    print("\n✅ Demo completed successfully!")

    return results


async def demonstrate_timeout_under_load():
    """Demonstrate timeout behavior under load."""

    print("\n🔥 Load Testing - Timeout Behavior Under Pressure")
    print("=" * 50)

    config = ProcessingConfig(
        critical_timeout=5,
        high_timeout=15,
        normal_timeout=30,
        low_timeout=45,
        max_concurrent_signals=5,  # Limit concurrency for demo
        require_market_assessment=False,
        min_quality_score=0.0,
        min_acceptable_score=0.0,
    )

    processor = EnhancedSignalProcessor(config)

    # Create a mix of urgent and non-urgent signals
    signals = []
    for i in range(20):
        if i % 4 == 0:  # Every 4th signal is urgent
            signal = MockTradingSignal(
                signal_id=f"urgent_{i:03d}",
                signal_type="complement_arb",
                complement_deviation=0.02,  # Urgent
                size=100.0,
            )
        else:
            signal = MockTradingSignal(
                signal_id=f"normal_{i:03d}",
                signal_type="regular",
                complement_deviation=0.005,  # Normal
                size=20.0,
            )
        signals.append(signal)

    print(f"Processing {len(signals)} signals concurrently...")

    start_time = time.time()
    results = await processor.process_batch(signals)
    total_time = time.time() - start_time

    print(f"Batch processing completed in {total_time:.2f}s")

    # Analyze results
    urgent_count = len([r for r in results if "urgent" in r.signal.signal_id])
    urgent_approved = len(
        [
            r
            for r in results
            if "urgent" in r.signal.signal_id
            and r.status.value in ["approved", "warning"]
        ]
    )

    print(f"Urgent signals: {urgent_count}, Approved: {urgent_approved}")

    stats = processor.get_processing_stats()
    print(f"Total timeout errors: {stats['timeout_errors']}")
    print(f"Critical timeouts used: {stats['critical_timeouts_used']}")

    return results


async def main():
    """Run all demonstrations."""
    try:
        # Basic tiered timeout demonstration
        await demonstrate_tiered_timeouts()

        # Load testing demonstration
        await demonstrate_timeout_under_load()

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
