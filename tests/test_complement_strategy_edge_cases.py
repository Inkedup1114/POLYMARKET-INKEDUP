"""
Additional tests for the Enhanced Complement Arbitrage Strategy, focusing on edge cases.
"""

import time

from inkedup_bot.signals import ComplementSignal
from inkedup_bot.strategies.complement_enhanced import EnhancedComplementArbStrategy


class TestRiskAdjustmentEdgeCases:
    """Test edge cases in risk adjustment logic."""

    def test_risk_adjustment_at_exposure_threshold(self):
        """Test risk adjustment when total exposure is exactly at 50%."""
        strategy = EnhancedComplementArbStrategy(
            base_trade_size=10.0, max_total_exposure=200.0, risk_adjustment_enabled=True
        )
        strategy.active_positions = {
            "pos1": {"total_size": 100.0, "timestamp": time.time()}
        }
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.5, 0.1)

        # At exactly 50% exposure, no size reduction should occur yet.
        size = strategy._calculate_position_size_with_risk(signal)
        assert size > strategy.base_trade_size

    def test_risk_adjustment_just_above_exposure_threshold(self):
        """Test risk adjustment when total exposure is just above 50%."""
        strategy = EnhancedComplementArbStrategy(
            base_trade_size=10.0, max_total_exposure=200.0, risk_adjustment_enabled=True
        )
        strategy.active_positions = {
            "pos1": {"total_size": 101.0, "timestamp": time.time()}
        }
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.5, 0.1)

        # Just above 50% exposure, a small size reduction should be applied.
        size = strategy._calculate_position_size_with_risk(signal)
        base_size = strategy.base_trade_size + (0.1 * strategy.size_scaling_factor)
        assert size < base_size

    def test_strong_signal_adjustment(self):
        """Test the size increase for a strong signal."""
        strategy = EnhancedComplementArbStrategy(
            min_deviation_threshold=0.01, risk_adjustment_enabled=True
        )
        # A deviation 3x the min_deviation_threshold
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.43, 0.03)

        size = strategy._calculate_position_size_with_risk(signal)
        base_size = strategy.base_trade_size + (0.03 * strategy.size_scaling_factor)

        # Size should be increased due to the strong signal
        assert size > base_size

    def test_existing_market_position_adjustment(self):
        """Test the size reduction when a position already exists in the market."""
        strategy = EnhancedComplementArbStrategy(risk_adjustment_enabled=True)
        strategy.active_positions = {
            "pos1": {
                "market_slug": "test-market",
                "total_size": 50.0,
                "timestamp": time.time(),
            }
        }
        signal = ComplementSignal("test-market", "yes", "no", 0.6, 0.5, 0.1)

        size = strategy._calculate_position_size_with_risk(signal)
        base_size = strategy.base_trade_size + (0.1 * strategy.size_scaling_factor)

        # Size should be reduced due to the existing position in the same market
        assert size < base_size


class TestLiquidityCheckEdgeCases:
    """Test edge cases in the liquidity check logic."""

    def test_liquidity_at_threshold(self):
        """Test liquidity check when implied liquidity is exactly at the threshold."""
        strategy = EnhancedComplementArbStrategy(min_liquidity_usd=600)
        # This will result in an implied liquidity of 600 for the yes price
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.7, 0.3)

        # Should be considered sufficient
        assert strategy._check_liquidity_requirements(signal) is True

    def test_liquidity_just_below_threshold(self):
        """Test liquidity check when implied liquidity is just below the threshold."""
        strategy = EnhancedComplementArbStrategy(min_liquidity_usd=600)
        # This will result in an implied liquidity of 599 for the yes price
        signal = ComplementSignal("market", "yes", "no", 0.599, 0.7, 0.299)

        # Should be considered insufficient
        assert strategy._check_liquidity_requirements(signal) is False
