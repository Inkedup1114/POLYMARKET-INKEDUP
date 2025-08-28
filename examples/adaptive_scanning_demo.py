#!/usr/bin/env python3
"""
Demonstration of the adaptive market scanning system.

This example shows how the scanner adjusts scanning frequency based on market volatility:
- High volatility (>0.7): 5-second intervals for rapid opportunity capture
- Normal volatility (0.2-0.7): 30-second intervals for standard monitoring  
- Low volatility (<0.2): 60-second intervals to conserve resources

The system tracks complement deviations, spread changes, and market volatility
to automatically optimize scanning frequency for maximum efficiency.
"""

import asyncio

# Import the scanner components
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List

sys.path.append("/home/ink/polymarket-inkedup")

from inkedup_bot.config import BotConfig
from inkedup_bot.scanner import BookEntry, MarketComposite, Scanner


@dataclass
class MockMarketData:
    """Mock market data for demonstration."""

    slug: str
    volatility_level: str  # "low", "normal", "high"
    complement_deviation: float
    max_spread_bps: float


def create_mock_scanner() -> Scanner:
    """Create scanner with demo configuration."""
    config = BotConfig(
        # Disable actual API calls for demo
        api_base="http://localhost:9999",  # Will fail but that's ok for demo
        market_cache_ttl=300,
        book_batch_size=50,
        # Strategy configuration for demo
        complement_arb_min_deviation=0.01,
        spread_alert_bps=100,
    )

    scanner = Scanner(config)

    # Override adaptive scanning parameters for demo
    scanner.fast_scan_interval = 2.0  # Very fast for demo
    scanner.base_scan_interval = 5.0  # Normal for demo
    scanner.slow_scan_interval = 10.0  # Slow for demo
    scanner.high_volatility_threshold = 0.6
    scanner.low_volatility_threshold = 0.3

    return scanner


def simulate_market_conditions() -> List[MockMarketData]:
    """Create mock market scenarios with different volatility levels."""
    return [
        # Low volatility scenario
        MockMarketData(
            "quiet-market-1", "low", 0.005, 200
        ),  # 0.5% deviation, 2% spread
        MockMarketData(
            "stable-market-2", "low", 0.003, 150
        ),  # 0.3% deviation, 1.5% spread
        # Normal volatility scenario
        MockMarketData(
            "active-market-3", "normal", 0.015, 400
        ),  # 1.5% deviation, 4% spread
        MockMarketData(
            "regular-market-4", "normal", 0.012, 350
        ),  # 1.2% deviation, 3.5% spread
        # High volatility scenario
        MockMarketData(
            "volatile-market-5", "high", 0.035, 800
        ),  # 3.5% deviation, 8% spread
        MockMarketData(
            "flash-market-6", "high", 0.045, 1200
        ),  # 4.5% deviation, 12% spread
    ]


def create_mock_composites(scenario: List[MockMarketData]) -> List[MarketComposite]:
    """Create mock MarketComposite objects from scenario data."""
    composites = []

    for market_data in scenario:
        # Create mock book entries
        yes_price = 0.5 + (market_data.complement_deviation / 2)
        no_price = 0.5 - (market_data.complement_deviation / 2)

        spread_bps = market_data.max_spread_bps

        tokens = [
            BookEntry(
                token_id=f"{market_data.slug}-yes",
                bid=yes_price - (spread_bps / 20000),  # Bid slightly below
                ask=yes_price + (spread_bps / 20000),  # Ask slightly above
                spread_bps=spread_bps,
            ),
            BookEntry(
                token_id=f"{market_data.slug}-no",
                bid=no_price - (spread_bps / 20000),
                ask=no_price + (spread_bps / 20000),
                spread_bps=spread_bps,
            ),
        ]

        composite = MarketComposite(
            slug=market_data.slug,
            tokens=tokens,
            complement_deviation=market_data.complement_deviation,
            max_spread_bps=market_data.max_spread_bps,
            avg_spread_bps=market_data.max_spread_bps * 0.8,
            volatility_score=None,  # Will be calculated by scanner
            last_updated=time.time(),
        )

        composites.append(composite)

    return composites


async def demonstrate_adaptive_scanning():
    """Demonstrate adaptive scanning with different market scenarios."""

    print("🔄 Adaptive Market Scanning Demo")
    print("=" * 50)

    scanner = create_mock_scanner()

    print("Configuration:")
    print(f"  Fast scanning: {scanner.fast_scan_interval}s (high volatility)")
    print(f"  Normal scanning: {scanner.base_scan_interval}s (normal volatility)")
    print(f"  Slow scanning: {scanner.slow_scan_interval}s (low volatility)")
    print(f"  High volatility threshold: {scanner.high_volatility_threshold}")
    print(f"  Low volatility threshold: {scanner.low_volatility_threshold}")
    print()

    # Test scenarios with increasing volatility
    scenarios = [
        ("Low Volatility Markets", simulate_market_conditions()[:2]),
        ("Normal Volatility Markets", simulate_market_conditions()[2:4]),
        ("High Volatility Markets", simulate_market_conditions()[4:6]),
        ("Mixed Volatility Markets", simulate_market_conditions()),
    ]

    for scenario_name, market_data in scenarios:
        print(f"📊 Testing: {scenario_name}")
        print("-" * 30)

        # Create mock composites
        mock_composites = create_mock_composites(market_data)

        # Calculate volatility for each market (simulate scanner's internal process)
        for i, composite in enumerate(mock_composites):
            market_data_item = market_data[i]
            volatility_score = scanner._calculate_market_volatility(
                composite.slug, composite.complement_deviation, composite.max_spread_bps
            )
            composite.volatility_score = volatility_score

            print(f"  {composite.slug}:")
            print(f"    Complement deviation: {composite.complement_deviation:.3f}")
            print(f"    Max spread: {composite.max_spread_bps:.0f} bps")
            print(f"    Volatility score: {volatility_score:.3f}")

        # Update global volatility and determine interval
        scanner._update_global_volatility(mock_composites)
        adaptive_interval = scanner._determine_adaptive_interval()

        print(f"  → Global volatility: {scanner.global_volatility_score:.3f}")
        print(f"  → Recommended interval: {adaptive_interval}s")

        # Show which scanning mode would be used
        if adaptive_interval == scanner.fast_scan_interval:
            mode = "FAST"
        elif adaptive_interval == scanner.slow_scan_interval:
            mode = "SLOW"
        else:
            mode = "NORMAL"
        print(f"  → Scanning mode: {mode}")
        print()

    # Show final adaptive stats
    stats = scanner.get_adaptive_stats()
    print("📈 Adaptive Scanning Statistics:")
    print(f"  Markets tracked: {stats['markets_tracked']}")
    print(f"  Current global volatility: {stats['current_global_volatility']:.3f}")
    print(f"  Fast scans: {stats['fast_scans']}")
    print(f"  Normal scans: {stats['normal_scans']}")
    print(f"  Slow scans: {stats['slow_scans']}")
    print(f"  Interval adjustments: {stats['interval_adjustments']}")
    print(f"  Volatility detections: {stats['volatility_detections']}")


async def demonstrate_volatility_trend_detection():
    """Demonstrate volatility trend detection that triggers fast scanning."""

    print("\n🚨 Volatility Trend Detection Demo")
    print("=" * 40)

    scanner = create_mock_scanner()

    print("Simulating gradual volatility increase...")

    # Simulate increasing volatility over time
    base_deviation = 0.005  # Start low
    volatility_increases = [0.005, 0.015, 0.035, 0.055]  # Gradual increase

    for i, deviation in enumerate(volatility_increases):
        print(f"\nScan {i+1}:")

        # Create market with increasing deviation
        mock_market = MockMarketData(
            "trending-market", "increasing", deviation, 400 + (i * 200)
        )
        composites = create_mock_composites([mock_market])

        # Calculate volatility
        composite = composites[0]
        volatility_score = scanner._calculate_market_volatility(
            composite.slug, composite.complement_deviation, composite.max_spread_bps
        )
        composite.volatility_score = volatility_score

        # Update global state
        scanner._update_global_volatility(composites)
        interval = scanner._determine_adaptive_interval()

        print(f"  Complement deviation: {deviation:.3f}")
        print(f"  Volatility score: {volatility_score:.3f}")
        print(f"  Global volatility: {scanner.global_volatility_score:.3f}")
        print(f"  Recommended interval: {interval}s")

        # Check for trend detection
        if len(scanner.scan_history) >= 3:
            recent_volatilities = [v for _, v in scanner.scan_history[-3:]]
            trend = recent_volatilities[-1] - recent_volatilities[0]
            print(f"  Volatility trend: {trend:+.3f}")

            if trend > 0.2:
                print(
                    "  🚨 RAPID VOLATILITY INCREASE DETECTED - Fast scanning triggered!"
                )

    print(f"\nFinal statistics:")
    stats = scanner.get_adaptive_stats()
    print(f"  Volatility detections: {stats['volatility_detections']}")
    print(f"  Interval adjustments: {stats['interval_adjustments']}")


async def benchmark_adaptive_vs_fixed():
    """Benchmark adaptive scanning efficiency vs fixed interval."""

    print("\n⚡ Adaptive vs Fixed Scanning Benchmark")
    print("=" * 45)

    # Simulate 100 scans with mixed volatility
    mixed_scenarios = []

    # 70% normal, 20% high volatility, 10% low volatility (realistic distribution)
    for i in range(100):
        if i < 70:  # Normal volatility
            deviation = 0.008 + (0.012 * (i % 5) / 5)  # 0.8% to 2.0%
            spread = 300 + (200 * (i % 3))
            volatility = "normal"
        elif i < 90:  # High volatility
            deviation = 0.025 + (0.020 * (i % 4) / 4)  # 2.5% to 4.5%
            spread = 600 + (400 * (i % 3))
            volatility = "high"
        else:  # Low volatility
            deviation = 0.002 + (0.003 * (i % 3) / 3)  # 0.2% to 0.5%
            spread = 100 + (50 * (i % 2))
            volatility = "low"

        mixed_scenarios.append(
            MockMarketData(f"market-{i}", volatility, deviation, spread)
        )

    # Test adaptive scanning
    scanner = create_mock_scanner()
    adaptive_total_time = 0.0
    adaptive_fast_count = 0

    print("Simulating 100 scans with adaptive intervals...")
    for scenario in mixed_scenarios:
        composites = create_mock_composites([scenario])
        composite = composites[0]

        # Calculate volatility and update scanner
        volatility_score = scanner._calculate_market_volatility(
            composite.slug, composite.complement_deviation, composite.max_spread_bps
        )
        composite.volatility_score = volatility_score

        scanner._update_global_volatility(composites)
        interval = scanner._determine_adaptive_interval()
        adaptive_total_time += interval

        if interval == scanner.fast_scan_interval:
            adaptive_fast_count += 1

    # Calculate fixed scanning time (always 30s)
    fixed_total_time = 100 * 30.0  # 100 scans * 30 seconds each

    # Results
    print(f"\nResults:")
    print(f"  Fixed interval (30s): {fixed_total_time:,.0f} seconds total")
    print(f"  Adaptive intervals: {adaptive_total_time:,.1f} seconds total")
    print(
        f"  Time savings: {fixed_total_time - adaptive_total_time:,.1f} seconds ({((fixed_total_time - adaptive_total_time) / fixed_total_time * 100):.1f}%)"
    )
    print(f"  Fast scans triggered: {adaptive_fast_count}/100 ({adaptive_fast_count}%)")

    stats = scanner.get_adaptive_stats()
    print(f"  Average volatility: {stats['avg_volatility']:.3f}")
    print(f"  Interval adjustments: {stats['interval_adjustments']}")


async def main():
    """Run all demonstrations."""
    try:
        # Basic adaptive scanning demonstration
        await demonstrate_adaptive_scanning()

        # Volatility trend detection
        await demonstrate_volatility_trend_detection()

        # Performance benchmark
        await benchmark_adaptive_vs_fixed()

        print("\n✅ Adaptive scanning demo completed successfully!")

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
