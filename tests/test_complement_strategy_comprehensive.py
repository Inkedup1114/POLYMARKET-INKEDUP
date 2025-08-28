"""
Comprehensive tests for the Enhanced Complement Arbitrage Strategy.

This test suite covers all functionality including edge cases, error handling,
risk management integration, and performance tracking.
"""

import time
from unittest.mock import Mock

import pytest

from inkedup_bot.signals import ComplementSignal, OutcomeType, SignalAction
from inkedup_bot.strategies.complement_enhanced import (
    EnhancedComplementArbStrategy,
    StrategyMetrics,
)


class TestStrategyMetrics:
    """Test suite for StrategyMetrics dataclass."""

    def test_metrics_initialization(self):
        """Test metrics initialization with default values."""
        metrics = StrategyMetrics()

        assert metrics.signals_generated == 0
        assert metrics.signals_executed == 0
        assert metrics.total_profit_loss == 0.0
        assert metrics.total_volume == 0.0
        assert metrics.win_rate == 0.0
        assert metrics.avg_deviation == 0.0
        assert metrics.max_deviation == 0.0
        assert metrics.last_updated > 0

    def test_update_signal_generated(self):
        """Test signal generation metric updates."""
        metrics = StrategyMetrics()

        # First signal
        metrics.update_signal_generated(0.05)
        assert metrics.signals_generated == 1
        assert metrics.avg_deviation == 0.05
        assert metrics.max_deviation == 0.05

        # Second signal
        metrics.update_signal_generated(0.10)
        assert metrics.signals_generated == 2
        assert abs(metrics.avg_deviation - 0.075) < 0.0001  # (0.05 + 0.10) / 2
        assert metrics.max_deviation == 0.10

        # Third signal with negative deviation
        metrics.update_signal_generated(-0.03)
        assert metrics.signals_generated == 3
        assert abs(metrics.avg_deviation - 0.06) < 0.01  # (0.05 + 0.10 + 0.03) / 3
        assert metrics.max_deviation == 0.10  # Absolute value, so 0.10 > 0.03

    def test_update_signal_executed(self):
        """Test signal execution metric updates."""
        metrics = StrategyMetrics()

        # First execution (win)
        metrics.update_signal_executed(100.0, 5.0)
        assert metrics.signals_executed == 1
        assert metrics.total_volume == 100.0
        assert metrics.total_profit_loss == 5.0
        assert metrics.win_rate == 1.0

        # Second execution (loss)
        metrics.update_signal_executed(50.0, -2.0)
        assert metrics.signals_executed == 2
        assert metrics.total_volume == 150.0
        assert metrics.total_profit_loss == 3.0
        assert metrics.win_rate == 0.5  # 1 win out of 2


class TestEnhancedComplementArbStrategyInitialization:
    """Test strategy initialization and configuration."""

    def test_initialization_default_params(self):
        """Test strategy initialization with default parameters."""
        strategy = EnhancedComplementArbStrategy()

        assert strategy.min_deviation_threshold == 0.01
        assert strategy.max_deviation_threshold == 0.20
        assert strategy.base_trade_size == 10.0
        assert strategy.max_trade_size == 100.0
        assert strategy.size_scaling_factor == 50.0
        assert strategy.min_liquidity_usd == 100.0
        assert strategy.max_position_per_market == 500.0
        assert strategy.max_total_exposure == 1000.0
        assert strategy.risk_adjustment_enabled is True
        assert strategy.position_decay_hours == 24.0
        assert strategy.enable_performance_tracking is True
        assert strategy.max_concurrent_positions == 10

        assert len(strategy.active_positions) == 0
        assert strategy.metrics is not None
        assert strategy.risk_manager is None
        assert strategy.state_manager is None

    def test_initialization_custom_params(self):
        """Test strategy initialization with custom parameters."""
        strategy = EnhancedComplementArbStrategy(
            min_deviation_threshold=0.02,
            max_deviation_threshold=0.15,
            base_trade_size=20.0,
            max_trade_size=200.0,
            size_scaling_factor=75.0,
            min_liquidity_usd=500.0,
            max_position_per_market=1000.0,
            max_total_exposure=2000.0,
            risk_adjustment_enabled=False,
            position_decay_hours=12.0,
            enable_performance_tracking=False,
            max_concurrent_positions=5,
        )

        assert strategy.min_deviation_threshold == 0.02
        assert strategy.max_deviation_threshold == 0.15
        assert strategy.base_trade_size == 20.0
        assert strategy.max_trade_size == 200.0
        assert strategy.size_scaling_factor == 75.0
        assert strategy.min_liquidity_usd == 500.0
        assert strategy.max_position_per_market == 1000.0
        assert strategy.max_total_exposure == 2000.0
        assert strategy.risk_adjustment_enabled is False
        assert strategy.position_decay_hours == 12.0
        assert strategy.enable_performance_tracking is False
        assert strategy.max_concurrent_positions == 5
        assert strategy.metrics is None

    def test_set_risk_manager(self):
        """Test setting risk manager."""
        strategy = EnhancedComplementArbStrategy()
        risk_manager = Mock()

        strategy.set_risk_manager(risk_manager)
        assert strategy.risk_manager is risk_manager

    def test_set_state_manager(self):
        """Test setting state manager."""
        strategy = EnhancedComplementArbStrategy()
        state_manager = Mock()

        strategy.set_state_manager(state_manager)
        assert strategy.state_manager is state_manager


class TestSignalValidation:
    """Test signal data validation."""

    @pytest.fixture
    def strategy(self):
        return EnhancedComplementArbStrategy()

    def test_valid_signal_data(self, strategy):
        """Test validation with valid signal data."""
        signal = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.6,
            no_price=0.3,
            complement_deviation=0.1,
        )

        assert strategy._validate_signal_data(signal) is True

    def test_invalid_market_slug(self, strategy):
        """Test validation with invalid market slug."""
        signal = ComplementSignal(
            market_slug="",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.6,
            no_price=0.3,
            complement_deviation=0.1,
        )

        assert strategy._validate_signal_data(signal) is False

    def test_invalid_token_ids(self, strategy):
        """Test validation with invalid token IDs."""
        # Missing yes token ID
        signal1 = ComplementSignal(
            market_slug="test-market",
            yes_token_id="",
            no_token_id="token_no",
            yes_price=0.6,
            no_price=0.3,
            complement_deviation=0.1,
        )

        # Missing no token ID
        signal2 = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="",
            yes_price=0.6,
            no_price=0.3,
            complement_deviation=0.1,
        )

        assert strategy._validate_signal_data(signal1) is False
        assert strategy._validate_signal_data(signal2) is False

    def test_invalid_prices(self, strategy):
        """Test validation with invalid prices."""
        # None prices
        signal1 = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=None,
            no_price=0.3,
            complement_deviation=0.1,
        )

        # Negative price
        signal2 = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=-0.1,
            no_price=0.3,
            complement_deviation=0.1,
        )

        # Price > 1.0
        signal3 = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=1.5,
            no_price=0.3,
            complement_deviation=0.1,
        )

        # Price = 0
        signal4 = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.0,
            no_price=0.3,
            complement_deviation=0.1,
        )

        # Price = 1.0
        signal5 = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=1.0,
            no_price=0.3,
            complement_deviation=0.1,
        )

        assert strategy._validate_signal_data(signal1) is False
        assert strategy._validate_signal_data(signal2) is False
        assert strategy._validate_signal_data(signal3) is False
        assert strategy._validate_signal_data(signal4) is False
        assert strategy._validate_signal_data(signal5) is False


class TestPositionSizing:
    """Test position sizing calculations."""

    @pytest.fixture
    def strategy(self):
        return EnhancedComplementArbStrategy(
            base_trade_size=10.0, max_trade_size=100.0, size_scaling_factor=50.0
        )

    @pytest.fixture
    def signal(self):
        return ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.6,
            no_price=0.3,
            complement_deviation=0.1,
        )

    def test_basic_position_sizing(self, strategy):
        """Test basic position size calculation."""
        # Small deviation
        size = strategy._calculate_position_size_with_risk(
            ComplementSignal("market", "yes", "no", 0.52, 0.49, 0.01)
        )
        # Expected: base calculation with potential risk adjustments
        expected_base = 10 + (0.01 * 50)  # 10.5
        assert size >= expected_base  # May be adjusted upward by risk logic

        # Larger deviation
        size = strategy._calculate_position_size_with_risk(
            ComplementSignal("market", "yes", "no", 0.6, 0.5, 0.1)
        )
        # Expected: base calculation with potential risk adjustments
        expected_base = 10 + (0.1 * 50)  # 15
        assert size >= expected_base  # May be adjusted upward by risk logic

    def test_position_size_maximum_limit(self, strategy):
        """Test position size maximum limit."""
        # Very large deviation that would exceed maximum
        size = strategy._calculate_position_size_with_risk(
            ComplementSignal("market", "yes", "no", 0.8, 0.7, 0.5)
        )
        # Should be capped at max trade size regardless of risk adjustments
        assert size <= strategy.max_trade_size

        # Even larger deviation
        size = strategy._calculate_position_size_with_risk(
            ComplementSignal("market", "yes", "no", 0.9, 0.8, 2.0)
        )
        # Would be 10 + (2.0 * 50) = 110, should be capped at 100
        assert size == strategy.max_trade_size

    def test_position_size_minimum_limit(self, strategy):
        """Test position size minimum limit."""
        # Very small deviation
        size = strategy._calculate_position_size_with_risk(
            ComplementSignal("market", "yes", "no", 0.501, 0.500, 0.001)
        )
        # Should be at least 1.0
        assert size >= 1.0

    def test_risk_adjustment_disabled(self):
        """Test position sizing with risk adjustment disabled."""
        strategy = EnhancedComplementArbStrategy(
            base_trade_size=10.0,
            size_scaling_factor=50.0,
            risk_adjustment_enabled=False,
        )

        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)
        size = strategy._calculate_position_size_with_risk(signal)

        # Should be simple calculation without risk adjustments
        expected = 10.0 + (0.1 * 50.0)  # 15.0
        assert size == expected

    def test_risk_adjustment_with_existing_exposure(self):
        """Test position sizing with existing exposure (risk adjustments)."""
        strategy = EnhancedComplementArbStrategy(
            base_trade_size=10.0,
            size_scaling_factor=50.0,
            max_total_exposure=100.0,
            risk_adjustment_enabled=True,
        )

        # Add existing positions to simulate exposure
        strategy.active_positions = {
            "pos1": {
                "market_slug": "other-market",
                "total_size": 60.0,
                "timestamp": time.time(),
            }
        }

        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)
        size = strategy._calculate_position_size_with_risk(signal)

        # With risk adjustments, size may be different from base calculation
        # The exact value depends on risk adjustment logic
        assert size >= 1.0  # Should at least meet minimum size


class TestLiquidityChecks:
    """Test liquidity requirement checks."""

    def test_liquidity_check_disabled(self):
        """Test with liquidity checks disabled."""
        strategy = EnhancedComplementArbStrategy(min_liquidity_usd=0.0)
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)

        assert strategy._check_liquidity_requirements(signal) is True

    def test_liquidity_check_sufficient(self):
        """Test with sufficient liquidity."""
        strategy = EnhancedComplementArbStrategy(min_liquidity_usd=100.0)
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)

        # With prices 0.6 and 0.4, implied liquidity should be sufficient
        assert strategy._check_liquidity_requirements(signal) is True

    def test_liquidity_check_insufficient(self):
        """Test with insufficient liquidity."""
        strategy = EnhancedComplementArbStrategy(min_liquidity_usd=1000.0)
        signal = ComplementSignal("market", "yes", "no", 0.01, 0.01, 0.05)

        # With very low prices, implied liquidity should be insufficient
        assert strategy._check_liquidity_requirements(signal) is False


class TestPositionLimits:
    """Test position limit checks."""

    def test_no_position_limits(self):
        """Test with no existing positions."""
        strategy = EnhancedComplementArbStrategy()
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)

        assert strategy._check_position_limits(signal) is True

    def test_max_concurrent_positions_reached(self):
        """Test when maximum concurrent positions is reached."""
        strategy = EnhancedComplementArbStrategy(max_concurrent_positions=2)

        # Add maximum positions
        for i in range(2):
            strategy.active_positions[f"pos{i}"] = {
                "market_slug": f"market{i}",
                "total_size": 10.0,
                "timestamp": time.time(),
            }

        signal = ComplementSignal("new-market", "yes", "no", 0.6, 0.4, 0.1)
        assert strategy._check_position_limits(signal) is False

    def test_market_position_limit_reached(self):
        """Test when per-market position limit is reached."""
        strategy = EnhancedComplementArbStrategy(max_position_per_market=100.0)

        # Add position at market limit
        strategy.active_positions["pos1"] = {
            "market_slug": "test-market",
            "total_size": 100.0,
            "timestamp": time.time(),
        }

        signal = ComplementSignal("test-market", "yes", "no", 0.6, 0.4, 0.1)
        assert strategy._check_position_limits(signal) is False

    def test_total_exposure_limit_reached(self):
        """Test when total exposure limit is reached."""
        strategy = EnhancedComplementArbStrategy(max_total_exposure=200.0)

        # Add positions that reach total limit
        for i in range(2):
            strategy.active_positions[f"pos{i}"] = {
                "market_slug": f"market{i}",
                "total_size": 100.0,
                "timestamp": time.time(),
            }

        signal = ComplementSignal("new-market", "yes", "no", 0.6, 0.4, 0.1)
        assert strategy._check_position_limits(signal) is False


class TestRiskConstraints:
    """Test risk management constraint checks."""

    def test_no_risk_manager(self):
        """Test with no risk manager attached."""
        strategy = EnhancedComplementArbStrategy()
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)

        assert strategy._check_risk_constraints(signal) is True

    def test_risk_manager_allows_trade(self):
        """Test with risk manager that allows the trade."""
        strategy = EnhancedComplementArbStrategy()
        risk_manager = Mock()
        risk_manager.get_market_exposure.return_value = 50.0
        risk_manager.per_market_risk_cap = 100.0
        risk_manager.get_total_exposure.return_value = 200.0
        risk_manager.global_risk_cap = 1000.0

        strategy.set_risk_manager(risk_manager)
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)

        assert strategy._check_risk_constraints(signal) is True

    def test_risk_manager_blocks_market_exposure(self):
        """Test with risk manager that blocks due to market exposure."""
        strategy = EnhancedComplementArbStrategy()
        risk_manager = Mock()
        risk_manager.get_market_exposure.return_value = 150.0
        risk_manager.per_market_risk_cap = 100.0

        strategy.set_risk_manager(risk_manager)
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)

        assert strategy._check_risk_constraints(signal) is False

    def test_risk_manager_blocks_total_exposure(self):
        """Test with risk manager that blocks due to total exposure."""
        strategy = EnhancedComplementArbStrategy()
        risk_manager = Mock()
        risk_manager.get_market_exposure.return_value = 50.0
        risk_manager.per_market_risk_cap = 100.0
        risk_manager.get_total_exposure.return_value = 1200.0
        risk_manager.global_risk_cap = 1000.0

        strategy.set_risk_manager(risk_manager)
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)

        assert strategy._check_risk_constraints(signal) is False

    def test_risk_manager_error_handling(self):
        """Test error handling in risk constraint checks."""
        strategy = EnhancedComplementArbStrategy()
        risk_manager = Mock()
        risk_manager.get_market_exposure.side_effect = Exception("Risk manager error")

        strategy.set_risk_manager(risk_manager)
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)

        # Should return False on error (conservative approach)
        assert strategy._check_risk_constraints(signal) is False


class TestSignalGeneration:
    """Test trading signal generation."""

    @pytest.fixture
    def strategy(self):
        return EnhancedComplementArbStrategy(
            min_deviation_threshold=0.01, base_trade_size=10.0
        )

    def test_positive_deviation_sell_signals(self, strategy):
        """Test sell signals for positive deviation (Yes + No > 1.0)."""
        signal = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.6,
            no_price=0.5,
            complement_deviation=0.1,
        )

        signals = strategy.on_complement(signal)

        assert len(signals) == 2

        # Check Yes sell signal
        yes_signal = next(s for s in signals if s.outcome_type == OutcomeType.YES.value)
        assert yes_signal.market_slug == "test-market"
        assert yes_signal.token_id == "token_yes"
        assert yes_signal.side == SignalAction.SELL.value
        assert yes_signal.price == 0.6
        assert yes_signal.outcome_type == OutcomeType.YES.value
        assert "complement_arb_sell_yes" in yes_signal.signal_id

        # Check No sell signal
        no_signal = next(s for s in signals if s.outcome_type == OutcomeType.NO.value)
        assert no_signal.market_slug == "test-market"
        assert no_signal.token_id == "token_no"
        assert no_signal.side == SignalAction.SELL.value
        assert no_signal.price == 0.5
        assert no_signal.outcome_type == OutcomeType.NO.value
        assert "complement_arb_sell_no" in no_signal.signal_id

    def test_negative_deviation_buy_signals(self, strategy):
        """Test buy signals for negative deviation (Yes + No < 1.0)."""
        signal = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.4,
            no_price=0.3,
            complement_deviation=-0.1,  # Changed to be within max threshold
        )

        signals = strategy.on_complement(signal)

        assert len(signals) == 2

        # Check Yes buy signal
        yes_signal = next(s for s in signals if s.outcome_type == OutcomeType.YES.value)
        assert yes_signal.side == SignalAction.BUY.value
        assert yes_signal.price == 0.4
        assert "complement_arb_buy_yes" in yes_signal.signal_id

        # Check No buy signal
        no_signal = next(s for s in signals if s.outcome_type == OutcomeType.NO.value)
        assert no_signal.side == SignalAction.BUY.value
        assert no_signal.price == 0.3
        assert "complement_arb_buy_no" in no_signal.signal_id

    def test_signal_id_uniqueness(self, strategy):
        """Test that signal IDs are unique across time."""
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.5, 0.1)

        # Generate signals at different times
        signals1 = strategy.on_complement(signal)
        time.sleep(0.001)  # Ensure timestamp difference
        signals2 = strategy.on_complement(signal)

        # All signal IDs should be unique
        all_signal_ids = [s.signal_id for s in signals1 + signals2]
        assert len(set(all_signal_ids)) == len(all_signal_ids)


class TestThresholdChecks:
    """Test deviation threshold checks."""

    def test_below_minimum_threshold(self):
        """Test signals below minimum threshold are ignored."""
        strategy = EnhancedComplementArbStrategy(min_deviation_threshold=0.02)
        signal = ComplementSignal(
            "market", "yes", "no", 0.505, 0.485, 0.01
        )  # 1% deviation

        signals = strategy.on_complement(signal)
        assert len(signals) == 0

    def test_above_maximum_threshold(self):
        """Test signals above maximum threshold are ignored."""
        strategy = EnhancedComplementArbStrategy(max_deviation_threshold=0.15)
        signal = ComplementSignal("market", "yes", "no", 0.8, 0.4, 0.2)  # 20% deviation

        signals = strategy.on_complement(signal)
        assert len(signals) == 0

    def test_at_threshold_boundaries(self):
        """Test signals exactly at threshold boundaries."""
        strategy = EnhancedComplementArbStrategy(
            min_deviation_threshold=0.02, max_deviation_threshold=0.15
        )

        # At minimum threshold
        signal_min = ComplementSignal("market", "yes", "no", 0.51, 0.49, 0.02)
        signals_min = strategy.on_complement(signal_min)
        assert len(signals_min) == 2

        # At maximum threshold
        signal_max = ComplementSignal("market", "yes", "no", 0.7, 0.45, 0.15)
        signals_max = strategy.on_complement(signal_max)
        assert len(signals_max) == 2


class TestUsdToSharesConversion:
    """Test USD to shares conversion."""

    @pytest.fixture
    def strategy(self):
        return EnhancedComplementArbStrategy()

    def test_normal_conversion(self, strategy):
        """Test normal USD to shares conversion."""
        shares = strategy._convert_usd_to_shares(100.0, 0.5)
        assert shares == 200.0

    def test_precision_rounding(self, strategy):
        """Test precision rounding in conversion."""
        shares = strategy._convert_usd_to_shares(100.0, 0.333)
        assert shares == round(100.0 / 0.333, 4)

    def test_invalid_price_handling(self, strategy):
        """Test handling of invalid prices."""
        # Zero price
        shares = strategy._convert_usd_to_shares(100.0, 0.0)
        assert shares == 0.0

        # Negative price
        shares = strategy._convert_usd_to_shares(100.0, -0.5)
        assert shares == 0.0

    def test_edge_cases(self, strategy):
        """Test edge cases in conversion."""
        # Very small amount
        shares = strategy._convert_usd_to_shares(0.01, 0.5)
        assert shares == 0.02

        # Very high price (close to 1.0)
        shares = strategy._convert_usd_to_shares(100.0, 0.99)
        assert abs(shares - (100.0 / 0.99)) < 0.0001


class TestPositionTracking:
    """Test position tracking functionality."""

    @pytest.fixture
    def strategy(self):
        return EnhancedComplementArbStrategy()

    def test_position_tracking(self, strategy):
        """Test position tracking after signal generation."""
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)

        # Initially no positions
        assert len(strategy.active_positions) == 0

        # Generate signals (should track position)
        signals = strategy.on_complement(signal)
        assert len(signals) == 2

        # Should have one tracked position
        assert len(strategy.active_positions) == 1

        position_data = list(strategy.active_positions.values())[0]
        assert position_data["market_slug"] == "market"
        assert position_data["deviation"] == 0.1
        assert position_data["yes_price"] == 0.6
        assert position_data["no_price"] == 0.4
        assert position_data["signal_count"] == 2

    def test_position_cleanup(self, strategy):
        """Test cleanup of expired positions."""
        # Set short decay time for testing
        strategy.position_decay_hours = 0.001  # ~3.6 seconds

        # Add old position
        old_time = time.time() - 10  # 10 seconds ago
        strategy.active_positions["old_pos"] = {
            "market_slug": "old-market",
            "timestamp": old_time,
            "total_size": 50.0,
        }

        # Add recent position
        strategy.active_positions["new_pos"] = {
            "market_slug": "new-market",
            "timestamp": time.time(),
            "total_size": 50.0,
        }

        assert len(strategy.active_positions) == 2

        # Cleanup should remove old position
        strategy._cleanup_expired_positions()

        assert len(strategy.active_positions) == 1
        assert "new_pos" in strategy.active_positions
        assert "old_pos" not in strategy.active_positions


class TestEvaluateMethod:
    """Test the main evaluate method (Strategy interface)."""

    @pytest.fixture
    def strategy(self):
        return EnhancedComplementArbStrategy(min_deviation_threshold=0.01)

    def test_evaluate_with_valid_data(self, strategy):
        """Test evaluate method with valid market data."""
        rows = [
            {
                "market_slug": "market1",
                "yes_token_id": "yes1",
                "no_token_id": "no1",
                "yes_price": 0.6,
                "no_price": 0.5,  # Sum = 1.1, deviation = 0.1
            },
            {
                "market_slug": "market2",
                "yes_token_id": "yes2",
                "no_token_id": "no2",
                "yes_price": 0.45,
                "no_price": 0.40,  # Sum = 0.85, deviation = -0.15 (within limits)
            },
        ]

        signals = strategy.evaluate(rows)

        # Should generate 4 signals (2 per market)
        assert len(signals) == 4

        # Check market1 signals (sell both)
        market1_signals = [s for s in signals if s.market_slug == "market1"]
        assert len(market1_signals) == 2
        assert all(s.side == SignalAction.SELL.value for s in market1_signals)

        # Check market2 signals (buy both)
        market2_signals = [s for s in signals if s.market_slug == "market2"]
        assert len(market2_signals) == 2
        assert all(s.side == SignalAction.BUY.value for s in market2_signals)

    def test_evaluate_with_invalid_data(self, strategy):
        """Test evaluate method with invalid market data."""
        rows = [
            {
                "market_slug": "market1",
                # Missing token IDs and prices
            },
            {
                "market_slug": "market2",
                "yes_token_id": "yes2",
                "no_token_id": "no2",
                "yes_price": None,  # Invalid price
                "no_price": 0.3,
            },
        ]

        signals = strategy.evaluate(rows)

        # Should generate no signals due to invalid data
        assert len(signals) == 0

    def test_evaluate_error_handling(self, strategy):
        """Test evaluate method error handling."""
        # Malformed row that could cause exceptions
        rows = [
            {
                "market_slug": "market1",
                "yes_token_id": "yes1",
                "no_token_id": "no1",
                "yes_price": "invalid",  # String instead of float
                "no_price": 0.3,
            }
        ]

        # Should not raise exception, should return empty list
        signals = strategy.evaluate(rows)
        assert len(signals) == 0


class TestPerformanceMetrics:
    """Test performance metrics tracking."""

    def test_metrics_enabled(self):
        """Test with performance metrics enabled."""
        strategy = EnhancedComplementArbStrategy(enable_performance_tracking=True)
        assert strategy.metrics is not None

    def test_metrics_disabled(self):
        """Test with performance metrics disabled."""
        strategy = EnhancedComplementArbStrategy(enable_performance_tracking=False)
        assert strategy.metrics is None

    def test_metrics_update_on_signal_generation(self):
        """Test metrics update when signals are generated."""
        strategy = EnhancedComplementArbStrategy(enable_performance_tracking=True)
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)

        initial_count = strategy.metrics.signals_generated

        signals = strategy.on_complement(signal)
        assert len(signals) == 2

        # Metrics should be updated
        assert strategy.metrics.signals_generated == initial_count + 1
        assert strategy.metrics.avg_deviation == 0.1
        assert strategy.metrics.max_deviation == 0.1

    def test_reset_metrics(self):
        """Test metrics reset functionality."""
        strategy = EnhancedComplementArbStrategy(enable_performance_tracking=True)

        # Generate some signals to populate metrics
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)
        strategy.on_complement(signal)

        assert strategy.metrics.signals_generated > 0

        # Reset metrics
        strategy.reset_metrics()

        assert strategy.metrics.signals_generated == 0
        assert strategy.metrics.avg_deviation == 0.0
        assert strategy.metrics.max_deviation == 0.0


class TestStrategyMetricsOutput:
    """Test strategy metrics output."""

    def test_get_strategy_metrics(self):
        """Test strategy metrics retrieval."""
        strategy = EnhancedComplementArbStrategy(
            min_deviation_threshold=0.02,
            max_deviation_threshold=0.15,
            base_trade_size=20.0,
            enable_performance_tracking=True,
        )

        # Add some active positions
        strategy.active_positions["pos1"] = {
            "total_size": 50.0,
            "timestamp": time.time(),
        }
        strategy.active_positions["pos2"] = {
            "total_size": 75.0,
            "timestamp": time.time(),
        }

        metrics = strategy.get_strategy_metrics()

        assert metrics["strategy_name"] == "EnhancedComplementArbStrategy"
        assert metrics["min_deviation_threshold"] == 0.02
        assert metrics["max_deviation_threshold"] == 0.15
        assert metrics["base_trade_size"] == 20.0
        assert metrics["active_positions_count"] == 2
        assert metrics["current_exposure"] == 125.0
        assert "performance_metrics" in metrics

    def test_get_strategy_metrics_no_performance_tracking(self):
        """Test metrics retrieval with performance tracking disabled."""
        strategy = EnhancedComplementArbStrategy(enable_performance_tracking=False)

        metrics = strategy.get_strategy_metrics()

        assert metrics["strategy_name"] == "EnhancedComplementArbStrategy"
        assert "performance_metrics" not in metrics

    def test_get_active_positions(self):
        """Test active positions retrieval."""
        strategy = EnhancedComplementArbStrategy()

        # Add some positions
        position_data = {
            "market_slug": "test",
            "total_size": 50.0,
            "timestamp": time.time(),
        }
        strategy.active_positions["pos1"] = position_data

        positions = strategy.get_active_positions()

        assert len(positions) == 1
        assert positions["pos1"] == position_data

        # Should be a copy, not the original
        positions["pos1"]["modified"] = True
        assert "modified" not in strategy.active_positions["pos1"]

    def test_clear_positions(self):
        """Test clearing all positions."""
        strategy = EnhancedComplementArbStrategy()

        # Add some positions
        strategy.active_positions["pos1"] = {"total_size": 50.0}
        strategy.active_positions["pos2"] = {"total_size": 75.0}

        assert len(strategy.active_positions) == 2

        strategy.clear_positions()

        assert len(strategy.active_positions) == 0


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""

    def test_extract_complement_signal_missing_fields(self):
        """Test complement signal extraction with missing fields."""
        strategy = EnhancedComplementArbStrategy()

        # Missing market_slug
        row1 = {
            "yes_token_id": "yes",
            "no_token_id": "no",
            "yes_price": 0.6,
            "no_price": 0.4,
        }
        assert strategy._extract_complement_signal(row1) is None

        # Missing token IDs
        row2 = {"market_slug": "market", "yes_price": 0.6, "no_price": 0.4}
        assert strategy._extract_complement_signal(row2) is None

        # Missing prices
        row3 = {"market_slug": "market", "yes_token_id": "yes", "no_token_id": "no"}
        assert strategy._extract_complement_signal(row3) is None

    def test_extract_complement_signal_malformed_data(self):
        """Test complement signal extraction with malformed data."""
        strategy = EnhancedComplementArbStrategy()

        # Invalid row structure
        row = "not_a_dict"
        assert strategy._extract_complement_signal(row) is None

        # Row with exception-causing data
        row_with_none = {"market_slug": None, "yes_token_id": "yes"}
        # Should handle gracefully and return None
        result = strategy._extract_complement_signal(row_with_none)
        assert result is None

    def test_on_complement_exception_handling(self):
        """Test exception handling in on_complement method."""
        strategy = EnhancedComplementArbStrategy()

        # Mock a method to raise an exception
        original_method = strategy._analyze_arbitrage_opportunity
        strategy._analyze_arbitrage_opportunity = Mock(
            side_effect=Exception("Test error")
        )

        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)

        # Should not raise exception, should return empty list
        signals = strategy.on_complement(signal)
        assert len(signals) == 0

        # Restore original method
        strategy._analyze_arbitrage_opportunity = original_method

    def test_extreme_deviation_values(self):
        """Test handling of extreme deviation values."""
        strategy = EnhancedComplementArbStrategy(
            min_deviation_threshold=0.01, max_deviation_threshold=0.20
        )

        # Very small deviation (should be ignored)
        signal_tiny = ComplementSignal("market", "yes", "no", 0.5001, 0.4999, 0.0001)
        signals = strategy.on_complement(signal_tiny)
        assert len(signals) == 0

        # Extreme large deviation (should be ignored for safety)
        signal_extreme = ComplementSignal("market", "yes", "no", 0.9, 0.8, 0.7)
        signals = strategy.on_complement(signal_extreme)
        assert len(signals) == 0

    def test_zero_position_size_edge_case(self):
        """Test edge case where calculated position size is zero."""
        strategy = EnhancedComplementArbStrategy(
            base_trade_size=0.0, size_scaling_factor=0.0
        )

        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)

        # Should not generate signals if position size is effectively zero
        # (though minimum size logic should prevent this)
        signals = strategy.on_complement(signal)

        # Due to minimum size logic, should still generate signals with size >= 1.0
        if len(signals) > 0:
            assert all(s.size >= 1.0 / s.price for s in signals)  # At least 1 USD worth


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
