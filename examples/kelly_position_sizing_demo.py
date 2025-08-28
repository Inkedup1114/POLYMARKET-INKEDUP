#!/usr/bin/env python3
"""
Demonstration of Kelly Criterion position sizing integration with complement arbitrage strategies.

This example shows how the Kelly Criterion optimizes position sizes based on:
- Historical win rates and profit/loss ratios
- Signal confidence and deviation magnitude  
- Available capital and risk management
- Strategy-specific performance tracking

The system automatically adapts position sizes as it learns from trade outcomes,
leading to more optimal capital allocation over time.
"""

import sys
import time

sys.path.append("/home/ink/polymarket-inkedup")

from inkedup_bot.signals import ComplementSignal
from inkedup_bot.strategies.complement import ComplementArbStrategy
from inkedup_bot.strategies.complement_enhanced import EnhancedComplementArbStrategy


def create_mock_signals():
    """Create mock complement signals for demonstration."""
    return [
        # Strong arbitrage opportunity - high confidence
        ComplementSignal(
            market_slug="election-2024-winner",
            yes_token_id="yes_token_123",
            no_token_id="no_token_124",
            yes_price=0.55,
            no_price=0.50,
            complement_deviation=0.05,  # 5% over-pricing
        ),
        # Moderate opportunity - medium confidence
        ComplementSignal(
            market_slug="crypto-btc-100k",
            yes_token_id="yes_token_125",
            no_token_id="no_token_126",
            yes_price=0.48,
            no_price=0.50,
            complement_deviation=-0.02,  # 2% under-pricing
        ),
        # Weak opportunity - low confidence
        ComplementSignal(
            market_slug="weather-sunny-tomorrow",
            yes_token_id="yes_token_127",
            no_token_id="no_token_128",
            yes_price=0.51,
            no_price=0.49,
            complement_deviation=0.00,  # No deviation, should be filtered out
        ),
        # Very strong opportunity - maximum confidence
        ComplementSignal(
            market_slug="sports-championship-final",
            yes_token_id="yes_token_129",
            no_token_id="no_token_130",
            yes_price=0.65,
            no_price=0.45,
            complement_deviation=0.10,  # 10% over-pricing - very strong signal
        ),
    ]


def demonstrate_basic_kelly_integration():
    """Demonstrate Kelly Criterion integration with basic complement strategy."""
    print("🎯 Basic Complement Strategy with Kelly Criterion")
    print("=" * 55)

    # Initialize strategy with Kelly Criterion
    strategy = ComplementArbStrategy(
        min_deviation_threshold=0.01,  # 1% minimum
        max_deviation_threshold=0.15,  # 15% maximum
        base_trade_size=20.0,  # Base $20 trades
        max_trade_size=200.0,  # Max $200 trades
        size_scaling_factor=100.0,  # Scale with deviation
    )

    # Set available capital for Kelly calculations
    strategy.set_available_capital(5000.0)  # $5k available

    print(f"Strategy Configuration:")
    print(f"  Available capital: ${strategy.available_capital:,.2f}")
    print(
        f"  Min/Max trade size: ${strategy.base_trade_size}/${strategy.max_trade_size}"
    )
    print(f"  Kelly multiplier: {strategy.kelly_sizer.kelly_multiplier}")
    print()

    # Test signals and show position sizing
    signals = create_mock_signals()

    for i, signal in enumerate(signals, 1):
        print(f"Signal {i}: {signal.market_slug}")
        print(
            f"  Deviation: {signal.complement_deviation:+.3f} ({signal.complement_deviation * 100:+.1f}%)"
        )

        # Generate trading signals
        trading_signals = strategy.on_complement(signal)

        if trading_signals:
            total_position = sum(ts.size * ts.price for ts in trading_signals)
            print(f"  ✅ Generated {len(trading_signals)} trading signals")
            print(f"  📊 Total position value: ${total_position:.2f}")

            for ts in trading_signals:
                print(
                    f"     {ts.side.upper()} {ts.outcome_type} @ ${ts.price:.3f}: {ts.size:.2f} shares"
                )
        else:
            print(f"  ❌ No signals generated (below threshold or filtered)")

        print()

    # Show Kelly statistics
    kelly_stats = strategy.get_kelly_statistics()
    print("Kelly Criterion Statistics:")
    if kelly_stats.get("total_trades", 0) > 0:
        print(f"  Total trades tracked: {kelly_stats['total_trades']}")
        print(f"  Win rate: {kelly_stats['win_rate']:.1%}")
        print(f"  Avg profit/loss ratio: {kelly_stats['avg_profit_loss_ratio']:.2f}")
        print(f"  Kelly fraction: {kelly_stats['kelly_fraction']:.3f}")
    else:
        print("  No historical trades yet - using default parameters")
    print()


def demonstrate_enhanced_kelly_integration():
    """Demonstrate Kelly Criterion with enhanced strategy and dynamic thresholds."""
    print("🚀 Enhanced Strategy with Kelly Criterion & Dynamic Thresholds")
    print("=" * 65)

    # Initialize enhanced strategy
    strategy = EnhancedComplementArbStrategy(
        base_min_threshold=0.005,  # More aggressive 0.5% base
        base_max_threshold=0.20,  # 20% maximum
        base_trade_size=25.0,  # Higher base $25
        max_trade_size=300.0,  # Higher max $300
        volatility_sensitivity=0.7,  # High sensitivity to volatility
        dynamic_thresholds_enabled=True,  # Enable dynamic adjustments
        min_confidence_threshold=0.5,  # Require 50% confidence
    )

    # Set higher capital allocation for enhanced strategy
    strategy.set_available_capital(10000.0)  # $10k available

    print(f"Enhanced Strategy Configuration:")
    print(f"  Available capital: ${strategy.available_capital:,.2f}")
    print(f"  Dynamic thresholds: {strategy.dynamic_thresholds_enabled}")
    print(f"  Volatility sensitivity: {strategy.volatility_sensitivity}")
    print(f"  Min confidence threshold: {strategy.min_confidence_threshold}")
    print()

    # Process signals with enhanced analysis
    signals = create_mock_signals()

    for i, signal in enumerate(signals, 1):
        print(f"Enhanced Signal {i}: {signal.market_slug}")
        print(
            f"  Deviation: {signal.complement_deviation:+.3f} ({signal.complement_deviation * 100:+.1f}%)"
        )

        # Generate trading signals with dynamic thresholds
        trading_signals = strategy.on_complement(signal)

        if trading_signals:
            total_position = sum(ts.size * ts.price for ts in trading_signals)
            print(f"  ✅ Generated {len(trading_signals)} enhanced trading signals")
            print(f"  💰 Total position value: ${total_position:.2f}")

            for ts in trading_signals:
                print(
                    f"     {ts.side.upper()} {ts.outcome_type} @ ${ts.price:.3f}: {ts.size:.2f} shares"
                )

            # Show market analysis if available
            market_analysis = strategy.get_market_analysis(signal.market_slug)
            if market_analysis:
                print(
                    f"  📈 Market analysis: volatility={market_analysis['recent_volatility']:.3f}, "
                    f"stability={market_analysis['price_stability']:.3f}"
                )
        else:
            print(
                f"  ❌ No signals generated (filtered by dynamic thresholds or confidence)"
            )

        print()

    # Show comprehensive metrics
    metrics = strategy.get_strategy_metrics()
    print("Enhanced Strategy Metrics:")
    print(f"  Markets tracked: {metrics['markets_tracked']}")
    print(f"  Threshold adjustments: {metrics['threshold_adjustments_made']}")
    print(f"  Active positions: {metrics['active_positions_count']}")
    print(f"  Current exposure: ${metrics['current_exposure']:.2f}")

    kelly_stats = metrics["kelly_statistics"]
    if kelly_stats.get("total_trades", 0) > 0:
        print(f"  Kelly trades tracked: {kelly_stats['total_trades']}")
        print(f"  Kelly win rate: {kelly_stats['win_rate']:.1%}")
        print(f"  Kelly fraction: {kelly_stats['kelly_fraction']:.3f}")
    else:
        print(f"  Kelly status: Learning phase (no historical trades)")
    print()


def simulate_learning_process():
    """Simulate the Kelly Criterion learning from trade outcomes."""
    print("🧠 Kelly Criterion Learning Simulation")
    print("=" * 40)

    strategy = ComplementArbStrategy(min_deviation_threshold=0.01)
    strategy.set_available_capital(5000.0)

    # Simulate successful and unsuccessful trades over time
    trade_scenarios = [
        # Early trades - mixed results as system learns
        ("election-market-1", "sell_both", 15.50, 100.0),  # Profit
        ("crypto-market-1", "buy_both", -8.25, 75.0),  # Loss
        ("sports-market-1", "sell_both", 22.10, 125.0),  # Profit
        ("election-market-2", "sell_both", 18.75, 95.0),  # Profit
        ("crypto-market-2", "buy_both", -12.40, 80.0),  # Loss
        # Later trades - system has learned, better sizing
        ("sports-market-2", "sell_both", 45.30, 200.0),  # Large profit
        ("election-market-3", "sell_both", 28.60, 150.0),  # Good profit
        ("crypto-market-3", "buy_both", 12.80, 90.0),  # Small profit (learned!)
    ]

    print("Simulating trade history and Kelly learning...")
    print()

    for i, (market, trade_type, pnl, size) in enumerate(trade_scenarios, 1):
        # Record the trade outcome
        strategy.record_trade_outcome(market, trade_type, pnl, size)

        # Get updated Kelly stats
        kelly_stats = strategy.get_kelly_statistics()

        print(f"Trade {i}: {market}")
        print(f"  P&L: ${pnl:+.2f}, Size: ${size:.0f}, Type: {trade_type}")
        print(f"  Updated Win Rate: {kelly_stats.get('win_rate', 0):.1%}")
        print(f"  Kelly Fraction: {kelly_stats.get('kelly_fraction', 0):.3f}")
        print(f"  Trades Tracked: {kelly_stats.get('total_trades', 0)}")
        print()

        # Update available capital based on P&L
        strategy.available_capital += pnl

    print("Final Kelly Statistics:")
    final_stats = strategy.get_kelly_statistics()
    print(f"  Total Trades: {final_stats.get('total_trades', 0)}")
    print(f"  Win Rate: {final_stats.get('win_rate', 0):.1%}")
    print(f"  Avg P&L Ratio: {final_stats.get('avg_profit_loss_ratio', 0):.2f}")
    print(f"  Kelly Fraction: {final_stats.get('kelly_fraction', 0):.3f}")
    print(f"  Final Capital: ${strategy.available_capital:,.2f}")

    # Test position sizing with learned parameters
    print(f"\nTesting position sizing with learned Kelly parameters:")
    test_signal = ComplementSignal(
        market_slug="new-opportunity",
        yes_token_id="test_yes",
        no_token_id="test_no",
        yes_price=0.58,
        no_price=0.45,
        complement_deviation=0.03,  # 3% opportunity
    )

    test_signals = strategy.on_complement(test_signal)
    if test_signals:
        total_position = sum(ts.size * ts.price for ts in test_signals)
        print(f"  Kelly-optimized position: ${total_position:.2f}")
        print(f"  Signals generated: {len(test_signals)}")
    else:
        print(f"  No signals generated")


def main():
    """Run all Kelly Criterion demonstrations."""
    try:
        # Basic strategy integration
        demonstrate_basic_kelly_integration()

        # Enhanced strategy with dynamic thresholds
        demonstrate_enhanced_kelly_integration()

        # Learning simulation
        simulate_learning_process()

        print("✅ Kelly Criterion position sizing demo completed successfully!")
        print("\nKey Benefits:")
        print("• Optimal capital allocation based on historical performance")
        print("• Automatic position sizing that adapts to win rates")
        print("• Risk management through Kelly fraction constraints")
        print("• Strategy-specific learning and optimization")
        print("• Integration with dynamic threshold systems")

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
