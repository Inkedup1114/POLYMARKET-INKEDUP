#!/usr/bin/env python3
"""
Correlation-Based Risk Management Demo.

This demonstration shows the advanced correlation analysis system for position
risk management, accounting for market correlations when calculating position
limits and risk adjustments.

The system provides:
- Real-time correlation matrix calculation between markets and outcomes
- Dynamic position limit adjustments based on correlation strength
- Market sector correlation analysis (politics, sports, crypto, etc.)
- Portfolio-wide correlation risk assessment
- Automatic risk limit reduction for highly correlated positions

Key Benefits:
- More accurate risk assessment considering position interdependencies
- Better risk management during correlated market movements
- Improved portfolio diversification guidance
- Automated position limit adjustments based on correlation patterns
"""

import asyncio
import random
import sys
import time

import numpy as np

sys.path.append("/home/ink/polymarket-inkedup")

from inkedup_bot.risk.correlation_risk_manager import (
    CorrelationRiskConfig,
    CorrelationRiskManager,
    CorrelationStrength,
)


async def demonstrate_correlation_risk_management():
    """Demonstrate the correlation-based risk management system."""

    print("📊 Correlation-Based Risk Management Demo")
    print("=" * 50)

    try:
        # Create configuration
        config = CorrelationRiskConfig(
            high_correlation_threshold=0.6,
            moderate_correlation_threshold=0.4,
            low_correlation_threshold=0.2,
            high_correlation_penalty=0.5,  # 50% limit reduction
            moderate_correlation_penalty=0.7,  # 30% limit reduction
            low_correlation_penalty=0.9,  # 10% limit reduction
            min_data_points=10,
            lookback_hours=24,
            correlation_update_interval=60.0,
        )

        print("✅ Correlation risk configuration created:")
        print(f"   High correlation threshold: {config.high_correlation_threshold}")
        print(
            f"   High correlation penalty: {(1-config.high_correlation_penalty)*100:.0f}% limit reduction"
        )
        print(
            f"   Moderate correlation penalty: {(1-config.moderate_correlation_penalty)*100:.0f}% limit reduction"
        )
        print(
            f"   Low correlation penalty: {(1-config.low_correlation_penalty)*100:.0f}% limit reduction"
        )

        # Create correlation risk manager
        risk_manager = CorrelationRiskManager(config)

        print(f"\n🚀 Starting correlation risk management system...")
        await risk_manager.start()

        # Simulate market data for different sectors
        markets = {
            "election-2024-president": {"sector": "politics", "base_price": 0.55},
            "congress-control-2024": {"sector": "politics", "base_price": 0.48},
            "nfl-superbowl-2024": {"sector": "sports", "base_price": 0.35},
            "nba-championship-2024": {"sector": "sports", "base_price": 0.42},
            "bitcoin-100k-2024": {"sector": "crypto", "base_price": 0.65},
            "ethereum-5k-2024": {"sector": "crypto", "base_price": 0.58},
            "recession-2024": {"sector": "economics", "base_price": 0.25},
            "fed-rate-cut-2024": {"sector": "economics", "base_price": 0.72},
        }

        print(f"\n📈 Simulating market data for correlation analysis...")

        # Generate correlated market data over time
        for time_step in range(50):  # 50 time steps
            timestamp = time.time() - (50 - time_step) * 3600  # Historical hourly data

            # Generate correlated price movements within sectors
            sector_shocks = {
                "politics": random.normalvariate(0, 0.05),
                "sports": random.normalvariate(0, 0.03),
                "crypto": random.normalvariate(0, 0.08),
                "economics": random.normalvariate(0, 0.04),
            }

            for market_slug, market_info in markets.items():
                sector = market_info["sector"]
                base_price = market_info["base_price"]

                # Price influenced by sector shock + individual noise
                sector_influence = sector_shocks[sector] * 0.7
                individual_noise = random.normalvariate(0, 0.02) * 0.3
                price_change = sector_influence + individual_noise

                new_price = max(0.01, min(0.99, base_price + price_change))
                exposure = random.uniform(100, 2000)  # Random exposure for simulation

                risk_manager.add_market_data(
                    market_slug, new_price, exposure, {"sector": sector}
                )

        print(f"   Generated correlated market data for {len(markets)} markets")

        # Allow time for correlation calculation
        await asyncio.sleep(2)

        # Calculate and display correlation matrix
        print(f"\n🔍 Calculating market correlation matrix...")
        correlation_matrix = await risk_manager.calculate_market_correlations()

        print(f"   Correlation matrix calculated for {len(correlation_matrix)} markets")

        # Display key correlations
        print(f"\n📊 Key Market Correlations:")
        print(f"{'Market A':<25} {'Market B':<25} {'Correlation':<12} {'Strength':<12}")
        print("-" * 75)

        correlation_pairs = []
        for market_a, correlations in correlation_matrix.items():
            for market_b, corr_metrics in correlations.items():
                if market_a < market_b:  # Avoid duplicates
                    correlation_pairs.append((market_a, market_b, corr_metrics))

        # Sort by absolute correlation strength
        correlation_pairs.sort(
            key=lambda x: abs(x[2].correlation_coefficient), reverse=True
        )

        for market_a, market_b, corr_metrics in correlation_pairs[:8]:  # Show top 8
            corr_val = corr_metrics.correlation_coefficient
            strength = corr_metrics.strength.value
            print(
                f"{market_a[:24]:<25} {market_b[:24]:<25} {corr_val:>+8.3f}    {strength:<12}"
            )

        # Test correlation-based risk adjustments
        print(f"\n🧪 Testing Correlation-Based Risk Adjustments:")

        test_scenarios = [
            {
                "name": "Low Correlation Portfolio",
                "existing_positions": {
                    "election-2024-president": 1000.0,
                    "nfl-superbowl-2024": 800.0,
                    "bitcoin-100k-2024": 1200.0,
                },
                "new_position": ("recession-2024", 600.0),
            },
            {
                "name": "High Correlation Portfolio (Politics)",
                "existing_positions": {
                    "election-2024-president": 1500.0,
                    "congress-control-2024": 1200.0,
                },
                "new_position": (
                    "fed-rate-cut-2024",
                    800.0,
                ),  # Economics correlated with politics
            },
            {
                "name": "Crypto Concentration",
                "existing_positions": {
                    "bitcoin-100k-2024": 2000.0,
                    "ethereum-5k-2024": 1800.0,
                },
                "new_position": (
                    "recession-2024",
                    1000.0,
                ),  # Economics has some crypto correlation
            },
        ]

        for i, scenario in enumerate(test_scenarios, 1):
            print(f"\n🎬 Scenario {i}: {scenario['name']}")

            existing_positions = scenario["existing_positions"]
            new_market, new_exposure = scenario["new_position"]

            # Calculate risk adjustment
            risk_adjustment = await risk_manager.assess_position_correlation_risk(
                new_market, new_exposure, existing_positions
            )

            print(f"   New position: {new_market} - ${new_exposure:.0f}")
            print(f"   Original limit: ${risk_adjustment.original_limit:.0f}")
            print(f"   Adjusted limit: ${risk_adjustment.adjusted_limit:.0f}")
            print(f"   Adjustment factor: {risk_adjustment.adjustment_factor:.2f}")
            print(f"   Correlation score: {risk_adjustment.correlation_score:.3f}")
            print(f"   Reason: {risk_adjustment.reason}")

            if risk_adjustment.affected_positions:
                print(
                    f"   Correlated positions: {', '.join(risk_adjustment.affected_positions[:3])}"
                )

            # Show impact
            limit_reduction = (1 - risk_adjustment.adjustment_factor) * 100
            if limit_reduction > 0:
                print(
                    f"   ⚠️  Risk limit reduced by {limit_reduction:.0f}% due to correlation"
                )
            else:
                print(f"   ✅ No correlation penalty applied")

        # Portfolio-wide correlation analysis
        print(f"\n📊 Portfolio-Wide Correlation Analysis:")

        sample_portfolio = {
            "election-2024-president": 1200.0,
            "congress-control-2024": 800.0,
            "nfl-superbowl-2024": 600.0,
            "bitcoin-100k-2024": 1500.0,
            "ethereum-5k-2024": 1000.0,
            "recession-2024": 400.0,
        }

        portfolio_metrics = await risk_manager.get_portfolio_correlation_metrics(
            sample_portfolio
        )

        print(f"   Total positions: {portfolio_metrics['total_positions']}")
        print(f"   Average correlation: {portfolio_metrics['avg_correlation']:.3f}")
        print(
            f"   Max pairwise correlation: {portfolio_metrics['max_pairwise_correlation']:.3f}"
        )
        print(
            f"   Diversification score: {portfolio_metrics['diversification_score']:.3f}"
        )
        print(
            f"   Highly correlated pairs: {portfolio_metrics['highly_correlated_pairs']}"
        )

        if portfolio_metrics["highly_correlated_groups"]:
            print(f"\n   🔗 Correlated Position Groups:")
            for group in portfolio_metrics["highly_correlated_groups"][:3]:
                markets_str = ", ".join(group["markets"][:3])
                print(
                    f"      Group: {markets_str} (${group['total_exposure']:.0f}, {group['exposure_pct']:.1%})"
                )

        print(f"\n   💡 Recommendations:")
        for rec in portfolio_metrics["recommendations"]:
            print(f"      • {rec}")

        # Show sector correlation matrix
        print(f"\n🏢 Sector Correlation Matrix:")
        sectors = ["politics", "sports", "crypto", "economics"]

        print(f"{'Sector':<12}", end="")
        for sector in sectors:
            print(f"{sector[:10]:>10}", end="")
        print()

        print("-" * (12 + 10 * len(sectors)))

        for sector_a in sectors:
            print(f"{sector_a:<12}", end="")
            for sector_b in sectors:
                if sector_a == sector_b:
                    corr = 1.0
                else:
                    corr = config.sector_correlations.get(sector_a, {}).get(
                        sector_b, 0.0
                    )
                print(f"{corr:>10.2f}", end="")
            print()

        # Performance and efficiency metrics
        print(f"\n⚡ System Performance:")
        summary = risk_manager.get_correlation_summary()

        print(f"   Markets tracked: {summary['markets_tracked']}")
        print(f"   Correlation matrices: {summary['correlation_matrices']}")
        print(f"   Active adjustments: {summary['active_adjustments']}")
        print(f"   System status: {'Running' if summary['running'] else 'Stopped'}")

        config_info = summary["config"]
        print(f"   Configuration:")
        print(
            f"      High correlation threshold: {config_info['high_correlation_threshold']}"
        )
        print(
            f"      Correlation penalty: {(1-config_info['correlation_penalty'])*100:.0f}%"
        )
        print(f"      Lookback period: {config_info['lookback_hours']} hours")
        print(f"      Update interval: {config_info['update_interval']:.0f} seconds")

        # Calculate efficiency improvements
        print(f"\n💰 Risk Management Improvements:")

        # Simulate traditional vs correlation-based limits
        traditional_limit = 2000.0
        high_corr_adjusted = traditional_limit * config.high_correlation_penalty
        moderate_corr_adjusted = traditional_limit * config.moderate_correlation_penalty

        print(f"   Traditional position limit: ${traditional_limit:.0f}")
        print(
            f"   High correlation adjusted: ${high_corr_adjusted:.0f} ({(1-config.high_correlation_penalty)*100:.0f}% reduction)"
        )
        print(
            f"   Moderate correlation adjusted: ${moderate_corr_adjusted:.0f} ({(1-config.moderate_correlation_penalty)*100:.0f}% reduction)"
        )

        risk_reduction = (traditional_limit - high_corr_adjusted) / traditional_limit
        print(f"   Risk reduction for correlated positions: {risk_reduction:.1%}")

        print(f"\n🎯 Key Features Demonstrated:")
        print(f"   ✓ Real-time correlation matrix calculation")
        print(f"   ✓ Dynamic position limit adjustments based on correlation")
        print(f"   ✓ Market sector correlation analysis")
        print(f"   ✓ Portfolio-wide correlation risk assessment")
        print(f"   ✓ Automatic risk limit reduction for correlated positions")
        print(f"   ✓ Diversification guidance and recommendations")

        # Stop the system
        print(f"\n🛑 Stopping correlation risk management system...")
        await risk_manager.stop()

        print(f"\n" + "=" * 50)
        print(f"✅ Correlation-Based Risk Management Demo Complete!")

        print(f"\nImplementation Summary:")
        print(f"🧠 Advanced correlation analysis with statistical significance testing")
        print(f"📊 Real-time correlation matrices for markets and sectors")
        print(f"⚖️ Dynamic position limit adjustments based on correlation strength")
        print(f"🎯 Portfolio diversification optimization with correlation groups")
        print(f"🛡️ Enhanced risk management considering position interdependencies")
        print(
            f"📈 Better risk-adjusted returns through correlation-aware position sizing"
        )

        return True

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(demonstrate_correlation_risk_management())
    exit(0 if success else 1)
