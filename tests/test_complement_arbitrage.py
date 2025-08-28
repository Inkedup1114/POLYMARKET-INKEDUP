"""
Tests for complement arbitrage strategy.
"""

from inkedup_bot.signals import (
    ComplementSignal,
    OutcomeType,
    SignalAction,
)
from inkedup_bot.strategies.complement import ComplementArbStrategy


class TestComplementArbStrategy:
    """Test suite for ComplementArbStrategy."""

    def test_initialization_default_params(self):
        """Test strategy initialization with default parameters."""
        strategy = ComplementArbStrategy()

        assert strategy.min_deviation_threshold == 0.01
        assert strategy.max_deviation_threshold == 0.20
        assert strategy.base_trade_size == 10.0
        assert strategy.max_trade_size == 100.0
        assert strategy.size_scaling_factor == 50.0
        assert strategy.min_liquidity_check is True
        assert strategy.risk_adjustment_enabled is True

    def test_initialization_custom_params(self):
        """Test strategy initialization with custom parameters."""
        strategy = ComplementArbStrategy(
            min_deviation_threshold=0.02,
            max_deviation_threshold=0.15,
            base_trade_size=20.0,
            max_trade_size=200.0,
            size_scaling_factor=75.0,
        )

        assert strategy.min_deviation_threshold == 0.02
        assert strategy.max_deviation_threshold == 0.15
        assert strategy.base_trade_size == 20.0
        assert strategy.max_trade_size == 200.0
        assert strategy.size_scaling_factor == 75.0

    def test_validate_signal_data_valid(self):
        """Test signal validation with valid data."""
        strategy = ComplementArbStrategy()
        signal = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.6,
            no_price=0.3,
            complement_deviation=0.1,
        )

        assert strategy._validate_signal_data(signal) is True

    def test_validate_signal_data_missing_market_slug(self):
        """Test signal validation with missing market slug."""
        strategy = ComplementArbStrategy()
        signal = ComplementSignal(
            market_slug="",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.6,
            no_price=0.3,
            complement_deviation=0.1,
        )

        assert strategy._validate_signal_data(signal) is False

    def test_validate_signal_data_missing_token_ids(self):
        """Test signal validation with missing token IDs."""
        strategy = ComplementArbStrategy()
        signal = ComplementSignal(
            market_slug="test-market",
            yes_token_id="",
            no_token_id="token_no",
            yes_price=0.6,
            no_price=0.3,
            complement_deviation=0.1,
        )

        assert strategy._validate_signal_data(signal) is False

    def test_validate_signal_data_invalid_prices(self):
        """Test signal validation with invalid prices."""
        strategy = ComplementArbStrategy()
        signal = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=1.5,  # Invalid: > 1.0
            no_price=0.3,
            complement_deviation=0.1,
        )

        assert strategy._validate_signal_data(signal) is False

    def test_calculate_position_size_base(self):
        """Test position size calculation with base parameters."""
        strategy = ComplementArbStrategy(base_trade_size=10.0, size_scaling_factor=50.0)

        # Small deviation
        size = strategy._calculate_position_size(0.02)
        # expected = 10.0 + (0.02 * 50.0)  # 10 + 1 = 11
        assert size == 11.0

        # Larger deviation
        size = strategy._calculate_position_size(0.05)
        # expected = 10.0 + (0.05 * 50.0)  # 10 + 2.5 = 12.5
        assert size == 12.5

    def test_calculate_position_size_max_limit(self):
        """Test position size calculation with maximum limit."""
        strategy = ComplementArbStrategy(
            base_trade_size=10.0, max_trade_size=15.0, size_scaling_factor=100.0
        )

        # Large deviation that would exceed max
        size = strategy._calculate_position_size(0.1)
        # Would be 10 + (0.1 * 100) = 20, but capped at 15
        assert size == 15.0

    def test_convert_usd_to_shares(self):
        """Test USD to shares conversion."""
        strategy = ComplementArbStrategy()

        # Normal case
        shares = strategy._convert_usd_to_shares(100.0, 0.5)
        assert shares == 200.0

        # Edge case with small price
        shares = strategy._convert_usd_to_shares(10.0, 0.1)
        assert shares == 100.0

        # Invalid price
        shares = strategy._convert_usd_to_shares(100.0, 0.0)
        assert shares == 0.0

    def test_below_minimum_threshold(self):
        """Test that signals below minimum threshold are ignored."""
        strategy = ComplementArbStrategy(min_deviation_threshold=0.02)
        signal = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.51,
            no_price=0.48,
            complement_deviation=0.01,  # Below 0.02 threshold
        )

        signals = strategy.on_complement(signal)
        assert len(signals) == 0

    def test_above_maximum_threshold(self):
        """Test that signals above maximum threshold are ignored."""
        strategy = ComplementArbStrategy(max_deviation_threshold=0.15)
        signal = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.7,
            no_price=0.5,
            complement_deviation=0.2,  # Above 0.15 threshold
        )

        signals = strategy.on_complement(signal)
        assert len(signals) == 0

    def test_positive_deviation_sell_signals(self):
        """Test sell signals generation for positive deviation (Yes + No > 1.0)."""
        strategy = ComplementArbStrategy(
            min_deviation_threshold=0.01, base_trade_size=10.0
        )
        signal = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.6,
            no_price=0.5,
            complement_deviation=0.1,  # Positive deviation
        )

        signals = strategy.on_complement(signal)

        assert len(signals) == 2

        # Check Yes sell signal
        yes_signal = signals[0]
        assert yes_signal.market_slug == "test-market"
        assert yes_signal.token_id == "token_yes"
        assert yes_signal.side == SignalAction.SELL.value
        assert yes_signal.price == 0.6
        assert yes_signal.outcome_type == OutcomeType.YES.value
        assert "complement_arb_sell_yes" in yes_signal.signal_id

        # Check No sell signal
        no_signal = signals[1]
        assert no_signal.market_slug == "test-market"
        assert no_signal.token_id == "token_no"
        assert no_signal.side == SignalAction.SELL.value
        assert no_signal.price == 0.5
        assert no_signal.outcome_type == OutcomeType.NO.value
        assert "complement_arb_sell_no" in no_signal.signal_id

    def test_negative_deviation_buy_signals(self):
        """Test buy signals generation for negative deviation (Yes + No < 1.0)."""
        strategy = ComplementArbStrategy(
            min_deviation_threshold=0.01, base_trade_size=10.0
        )
        signal = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.4,
            no_price=0.3,
            complement_deviation=-0.1,  # Negative deviation within limits
        )

        signals = strategy.on_complement(signal)

        assert len(signals) == 2

        # Check Yes buy signal
        yes_signal = signals[0]
        assert yes_signal.market_slug == "test-market"
        assert yes_signal.token_id == "token_yes"
        assert yes_signal.side == SignalAction.BUY.value
        assert yes_signal.price == 0.4
        assert yes_signal.outcome_type == OutcomeType.YES.value
        assert "complement_arb_buy_yes" in yes_signal.signal_id

        # Check No buy signal
        no_signal = signals[1]
        assert no_signal.market_slug == "test-market"
        assert no_signal.token_id == "token_no"
        assert no_signal.side == SignalAction.BUY.value
        assert no_signal.price == 0.3
        assert no_signal.outcome_type == OutcomeType.NO.value
        assert "complement_arb_buy_no" in no_signal.signal_id

    def test_position_sizing_scales_with_deviation(self):
        """Test that position size scales with deviation magnitude."""
        strategy = ComplementArbStrategy(
            min_deviation_threshold=0.01,
            base_trade_size=10.0,
            size_scaling_factor=100.0,
        )

        # Small deviation
        signal_small = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.52,
            no_price=0.49,
            complement_deviation=0.01,
        )

        signals_small = strategy.on_complement(signal_small)
        small_size = signals_small[0].size

        # Large deviation
        signal_large = ComplementSignal(
            market_slug="test-market",
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.6,
            no_price=0.5,
            complement_deviation=0.1,
        )

        signals_large = strategy.on_complement(signal_large)
        large_size = signals_large[0].size

        # Larger deviation should result in larger position size
        assert large_size > small_size

    def test_error_handling_invalid_signal(self):
        """Test error handling with invalid signal."""
        strategy = ComplementArbStrategy()
        signal = ComplementSignal(
            market_slug="",  # Invalid
            yes_token_id="token_yes",
            no_token_id="token_no",
            yes_price=0.6,
            no_price=0.3,
            complement_deviation=0.1,
        )

        # Should return empty list due to validation failure
        signals = strategy.on_complement(signal)
        assert len(signals) == 0

    def test_get_strategy_metrics(self):
        """Test strategy metrics retrieval."""
        strategy = ComplementArbStrategy(
            min_deviation_threshold=0.02,
            max_deviation_threshold=0.15,
            base_trade_size=20.0,
        )

        metrics = strategy.get_strategy_metrics()

        assert metrics["strategy_name"] == "ComplementArbStrategy"
        assert metrics["min_deviation_threshold"] == 0.02
        assert metrics["max_deviation_threshold"] == 0.15
        assert metrics["base_trade_size"] == 20.0
        assert "max_trade_size" in metrics
        assert "size_scaling_factor" in metrics
