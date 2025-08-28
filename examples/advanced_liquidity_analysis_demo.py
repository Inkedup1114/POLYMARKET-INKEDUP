#!/usr/bin/env python3
"""
Advanced Liquidity Analysis Demo.

This demonstration shows the advanced liquidity analysis system that replaces
any hardcoded liquidity values with real-time order book depth analysis,
providing sophisticated metrics for better market entry/exit decisions.

The system provides:
- Real-time order book depth analysis at multiple price levels
- Price impact calculations for various order sizes  
- Liquidity quality scoring and resilience metrics
- Slippage estimation for hypothetical orders
- Market microstructure analysis
- Execution quality recommendations

Key improvements over simple liquidity calculations:
- Considers order book shape and distribution, not just total volume
- Calculates actual price impact for different order sizes
- Identifies concentrated vs distributed liquidity
- Provides actionable execution recommendations
"""

import asyncio
import sys
import time
from typing import Any, Dict, List

sys.path.append("/home/ink/polymarket-inkedup")

from inkedup_bot.advanced_liquidity_analyzer import (
    AdvancedLiquidityAnalyzer,
    AdvancedLiquidityConfig,
    LiquidityQuality,
)


def create_mock_order_book(
    bid_price: float = 0.45,
    ask_price: float = 0.55,
    depth_profile: str = "balanced",
    total_liquidity: float = 5000.0,
) -> Dict[str, Any]:
    """Create a mock order book for demonstration."""

    spread = ask_price - bid_price
    mid_price = (bid_price + ask_price) / 2

    # Create bid levels
    bids = []
    if depth_profile == "balanced":
        # Even distribution
        for i in range(10):
            price = bid_price - i * 0.01
            size = total_liquidity / 20 / price  # Split liquidity evenly
            bids.append({"price": str(price), "size": str(size)})

    elif depth_profile == "top_heavy":
        # Concentrated at top
        for i in range(5):
            price = bid_price - i * 0.005
            size = (
                (total_liquidity * 0.8) / 5 / price
                if i < 3
                else (total_liquidity * 0.2) / 2 / price
            )
            bids.append({"price": str(price), "size": str(size)})

    elif depth_profile == "thin":
        # Limited liquidity
        for i in range(3):
            price = bid_price - i * 0.02
            size = total_liquidity / 6 / price
            bids.append({"price": str(price), "size": str(size)})

    # Create ask levels (mirror of bids)
    asks = []
    for i in range(len(bids)):
        price = ask_price + i * (ask_price - mid_price) / len(bids)
        size = bids[i]["size"]
        asks.append({"price": str(price), "size": size})

    return {"bids": bids, "asks": asks, "timestamp": time.time()}


async def demonstrate_advanced_liquidity_analysis():
    """Demonstrate the advanced liquidity analysis system."""

    print("📊 Advanced Liquidity Analysis Demo")
    print("=" * 50)

    try:
        # Create configuration
        config = AdvancedLiquidityConfig(
            depth_levels=[0.01, 0.02, 0.05, 0.10],
            low_impact_threshold=10.0,
            medium_impact_threshold=50.0,
            high_impact_threshold=100.0,
            benchmark_sizes=[100.0, 500.0, 1000.0, 5000.0],
            min_liquidity_usd=100.0,
            min_levels=3,
            max_spread_bps=500.0,
        )

        print("✅ Advanced liquidity analyzer configured:")
        print(f"   Depth levels: {[f'{d*100:.0f}%' for d in config.depth_levels]}")
        print(
            f"   Impact thresholds: Low<{config.low_impact_threshold}bps, Medium<{config.medium_impact_threshold}bps, High>{config.high_impact_threshold}bps"
        )
        print(f"   Benchmark order sizes: ${config.benchmark_sizes}")

        # Create analyzer
        analyzer = AdvancedLiquidityAnalyzer(config)

        print(f"\n🔍 Analyzing Different Market Conditions:")

        # Test scenarios
        scenarios = [
            {
                "name": "High Liquidity Balanced Market",
                "bid_price": 0.48,
                "ask_price": 0.52,
                "depth_profile": "balanced",
                "total_liquidity": 10000.0,
            },
            {
                "name": "Low Liquidity Top-Heavy Market",
                "bid_price": 0.35,
                "ask_price": 0.45,
                "depth_profile": "top_heavy",
                "total_liquidity": 1000.0,
            },
            {
                "name": "Thin Market with Wide Spread",
                "bid_price": 0.30,
                "ask_price": 0.50,
                "depth_profile": "thin",
                "total_liquidity": 500.0,
            },
            {
                "name": "Moderate Liquidity Balanced Market",
                "bid_price": 0.45,
                "ask_price": 0.55,
                "depth_profile": "balanced",
                "total_liquidity": 3000.0,
            },
        ]

        for i, scenario in enumerate(scenarios, 1):
            print(f"\n🎬 Scenario {i}: {scenario['name']}")
            print("-" * 45)

            # Create mock order book
            book_data = create_mock_order_book(
                bid_price=scenario["bid_price"],
                ask_price=scenario["ask_price"],
                depth_profile=scenario["depth_profile"],
                total_liquidity=scenario["total_liquidity"],
            )

            # Analyze order book
            market_slug = f"test-market-{i}"
            snapshot = analyzer.analyze_order_book(book_data, market_slug)

            # Display basic metrics
            print(
                f"   Bid/Ask: ${scenario['bid_price']:.2f} / ${scenario['ask_price']:.2f}"
            )
            print(f"   Spread: {snapshot.spread_bps:.0f} bps")
            print(
                f"   Total Liquidity: ${snapshot.total_bid_liquidity + snapshot.total_ask_liquidity:,.0f}"
            )
            print(f"   Bid/Ask Ratio: {snapshot.bid_ask_ratio:.2f}")

            # Display depth metrics
            print(f"\n   📊 Depth Analysis:")
            print(f"      Within 1% of mid: ${snapshot.depth_at_1pct:,.0f}")
            print(f"      Within 2% of mid: ${snapshot.depth_at_2pct:,.0f}")
            print(f"      Within 5% of mid: ${snapshot.depth_at_5pct:,.0f}")

            # Display quality metrics
            print(f"\n   ⭐ Quality Metrics:")
            print(
                f"      Liquidity Quality: {snapshot.liquidity_quality.value.upper()}"
            )
            print(f"      Depth Profile: {snapshot.depth_profile.value}")
            print(f"      Resilience Score: {snapshot.resilience_score:.1f}/100")
            print(
                f"      Concentration Score: {snapshot.concentration_score:.2f} (0=dispersed, 1=concentrated)"
            )

            # Display price impact estimates
            print(f"\n   💰 Price Impact Estimates (in bps):")
            print(f"      $100 order:  {snapshot.impact_100_usd:.1f} bps")
            print(f"      $500 order:  {snapshot.impact_500_usd:.1f} bps")
            print(f"      $1000 order: {snapshot.impact_1000_usd:.1f} bps")

            # Test slippage estimation
            print(f"\n   📈 Slippage Analysis for $500 Buy Order:")
            slippage = analyzer.estimate_slippage(book_data, 500.0, "buy")

            print(f"      Expected Price: ${slippage.expected_price:.4f}")
            print(f"      Avg Fill Price: ${slippage.average_fill_price:.4f}")
            print(f"      Slippage: {slippage.slippage_bps:.1f} bps")
            print(f"      Executable: {'✅ Yes' if slippage.executable else '❌ No'}")
            print(f"      Fill Percentage: {slippage.fill_percentage:.1f}%")
            print(f"      Levels Consumed: {slippage.levels_consumed}")

            # Generate execution recommendations
            print(f"\n   💡 Execution Recommendations:")
            if snapshot.liquidity_quality in [
                LiquidityQuality.EXCELLENT,
                LiquidityQuality.GOOD,
            ]:
                print(f"      ✅ Good liquidity - Market orders up to $1000 acceptable")
                print(f"      ✅ Low slippage expected for standard order sizes")
            elif snapshot.liquidity_quality == LiquidityQuality.MODERATE:
                print(
                    f"      ⚠️ Moderate liquidity - Use limit orders for orders > $500"
                )
                print(f"      ⚠️ Consider splitting large orders")
            else:
                print(f"      ❌ Poor liquidity - Avoid market orders")
                print(
                    f"      ❌ Use aggressive limit orders or wait for better liquidity"
                )

            if snapshot.depth_profile.value == "top_heavy":
                print(
                    f"      ⚠️ Liquidity concentrated at top - be careful with large orders"
                )
            elif snapshot.depth_profile.value == "thin":
                print(f"      ❌ Thin order book - high price impact for any size")

            if snapshot.spread_bps > 100:
                print(
                    f"      ⚠️ Wide spread ({snapshot.spread_bps:.0f} bps) - high transaction costs"
                )

        # Performance statistics
        print(f"\n⚡ Performance Statistics:")
        stats = analyzer.get_performance_stats()
        print(f"   Total analyses: {stats['total_analyses']}")
        print(f"   Average analysis time: {stats['average_analysis_time_ms']:.2f} ms")
        print(f"   Markets tracked: {stats['markets_tracked']}")

        # Compare with simple liquidity calculation
        print(f"\n📊 Comparison with Simple Liquidity Calculation:")
        print(f"   Simple approach: Sum all bid + ask volumes = single number")
        print(f"   Advanced approach:")
        print(f"      • Depth analysis at multiple price levels")
        print(f"      • Price impact calculations for actual execution quality")
        print(f"      • Liquidity distribution and concentration metrics")
        print(f"      • Resilience scoring for market stability")
        print(f"      • Slippage estimation for order planning")

        print(f"\n🎯 Key Advantages of Advanced Analysis:")
        print(f"   ✓ Identifies liquidity quality, not just quantity")
        print(f"   ✓ Calculates actual execution costs, not theoretical")
        print(f"   ✓ Detects concentrated vs distributed liquidity")
        print(f"   ✓ Provides actionable order sizing recommendations")
        print(f"   ✓ Enables better market entry/exit decisions")
        print(f"   ✓ Real-time analysis with sub-second performance")

        print(f"\n" + "=" * 50)
        print(f"✅ Advanced Liquidity Analysis Demo Complete!")

        print(f"\nImplementation Summary:")
        print(f"🔍 Real-time order book depth analysis at multiple levels")
        print(f"💰 Price impact calculations for various order sizes")
        print(f"⭐ Comprehensive liquidity quality scoring")
        print(f"📈 Slippage estimation for better execution planning")
        print(f"🎯 Market microstructure analysis for informed decisions")
        print(f"💡 Actionable execution recommendations")

        return True

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(demonstrate_advanced_liquidity_analysis())
    exit(0 if success else 1)
