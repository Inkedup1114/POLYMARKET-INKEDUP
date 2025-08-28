"""
Tests for the refactored SpreadArb strategy.
"""

from unittest.mock import patch

from inkedup_bot.signals import OutcomeType, SignalAction
from inkedup_bot.strategies.spread_arbitrage import SpreadArb


class TestSpreadArb:
    """Test suite for refactored SpreadArb strategy."""

    def test_initialization(self):
        """Test strategy initialization with default and custom config."""
        # Test default config
        strategy = SpreadArb({})
        assert strategy.min_spread == 0.01
        assert strategy.trade_size == 1.0

        # Test custom config
        config = {"min_spread": 0.02, "trade_size": 5.0}
        strategy = SpreadArb(config)
        assert strategy.min_spread == 0.02
        assert strategy.trade_size == 5.0

    def test_evaluate_no_market_snapshots(self):
        """Test evaluation with no market snapshots."""
        strategy = SpreadArb({})
        data = {}
        signals = strategy.evaluate(data)
        assert signals == []

        data = {"market_snapshots": []}
        signals = strategy.evaluate(data)
        assert signals == []

    def test_evaluate_valid_arbitrage_opportunity(self):
        """Test evaluation with valid arbitrage opportunity."""
        strategy = SpreadArb({"min_spread": 0.01, "trade_size": 2.0})

        market_data = {
            "market_slug": "test-market",
            "yes_price": 0.6,
            "no_price": 0.5,  # spread = 1.1 - 1 = 0.1 > 0.01
            "outcomes": [{"id": "yes_token_123"}, {"id": "no_token_456"}],
        }

        data = {"market_snapshots": [market_data]}
        signals = strategy.evaluate(data)

        assert len(signals) == 2

        # Check Yes signal
        yes_signal = signals[0]
        assert yes_signal.market_slug == "test-market"
        assert yes_signal.token_id == "yes_token_123"
        assert yes_signal.side == SignalAction.SELL.value
        assert yes_signal.price == 0.6
        assert yes_signal.size == 2.0
        assert yes_signal.outcome_type == OutcomeType.YES
        assert "spread_arb_yes" in yes_signal.signal_id

        # Check No signal
        no_signal = signals[1]
        assert no_signal.market_slug == "test-market"
        assert no_signal.token_id == "no_token_456"
        assert no_signal.side == SignalAction.SELL.value
        assert no_signal.price == 0.5
        assert no_signal.size == 2.0
        assert no_signal.outcome_type == OutcomeType.NO
        assert "spread_arb_no" in no_signal.signal_id

    def test_evaluate_spread_below_threshold(self):
        """Test evaluation with spread below threshold."""
        strategy = SpreadArb({"min_spread": 0.1, "trade_size": 1.0})

        market_data = {
            "market_slug": "test-market",
            "yes_price": 0.52,
            "no_price": 0.47,  # spread = 0.99 - 1 = -0.01 < 0.1
            "outcomes": [{"id": "yes_token_123"}, {"id": "no_token_456"}],
        }

        data = {"market_snapshots": [market_data]}
        signals = strategy.evaluate(data)

        assert len(signals) == 0

    def test_evaluate_missing_market_slug(self):
        """Test evaluation with missing market slug."""
        strategy = SpreadArb({})

        market_data = {
            # Missing market_slug
            "yes_price": 0.6,
            "no_price": 0.5,
            "outcomes": [{"id": "yes_token_123"}, {"id": "no_token_456"}],
        }

        data = {"market_snapshots": [market_data]}
        signals = strategy.evaluate(data)

        assert len(signals) == 0

    def test_evaluate_missing_prices(self):
        """Test evaluation with missing price data."""
        strategy = SpreadArb({})

        # Missing yes_price
        market_data = {
            "market_slug": "test-market",
            "no_price": 0.5,
            "outcomes": [{"id": "yes_token_123"}, {"id": "no_token_456"}],
        }
        data = {"market_snapshots": [market_data]}
        signals = strategy.evaluate(data)
        assert len(signals) == 0

        # Missing no_price
        market_data = {
            "market_slug": "test-market",
            "yes_price": 0.6,
            "outcomes": [{"id": "yes_token_123"}, {"id": "no_token_456"}],
        }
        data = {"market_snapshots": [market_data]}
        signals = strategy.evaluate(data)
        assert len(signals) == 0

    def test_validate_market_outcomes_invalid_outcomes(self):
        """Test outcome validation with invalid outcomes."""
        strategy = SpreadArb({})

        # Not a list
        result = strategy._validate_market_outcomes("test-market", "not_a_list")
        assert result is None

        # Empty list
        result = strategy._validate_market_outcomes("test-market", [])
        assert result is None

        # Only one outcome
        result = strategy._validate_market_outcomes("test-market", [{"id": "token1"}])
        assert result is None

    def test_validate_market_outcomes_missing_token_ids(self):
        """Test outcome validation with missing token IDs."""
        strategy = SpreadArb({})

        # Missing first token ID
        outcomes = [{"name": "yes"}, {"id": "no_token"}]
        result = strategy._validate_market_outcomes("test-market", outcomes)
        assert result is None

        # Missing second token ID
        outcomes = [{"id": "yes_token"}, {"name": "no"}]
        result = strategy._validate_market_outcomes("test-market", outcomes)
        assert result is None

    def test_validate_market_outcomes_valid(self):
        """Test outcome validation with valid outcomes."""
        strategy = SpreadArb({})

        outcomes = [{"id": "yes_token_123"}, {"id": "no_token_456"}]
        result = strategy._validate_market_outcomes("test-market", outcomes)

        assert result is not None
        yes_token, no_token = result
        assert yes_token == "yes_token_123"
        assert no_token == "no_token_456"

    def test_generate_arbitrage_signals(self):
        """Test arbitrage signal generation."""
        strategy = SpreadArb({"trade_size": 3.5})

        signals = strategy._generate_arbitrage_signals(
            market_slug="test-market-123",
            yes_token="yes_token_abc",
            no_token="no_token_def",
            best_yes_price=0.65,
            best_no_price=0.42,
        )

        assert len(signals) == 2

        # Verify Yes signal
        yes_signal = signals[0]
        assert yes_signal.market_slug == "test-market-123"
        assert yes_signal.token_id == "yes_token_abc"
        assert yes_signal.side == SignalAction.SELL.value
        assert yes_signal.price == 0.65
        assert yes_signal.size == 3.5
        assert yes_signal.outcome_type == OutcomeType.YES
        assert (
            "yes_token_abc" not in yes_signal.signal_id
        )  # Should contain market slug, not token ID
        assert "test-market-123" in yes_signal.signal_id

        # Verify No signal
        no_signal = signals[1]
        assert no_signal.market_slug == "test-market-123"
        assert no_signal.token_id == "no_token_def"
        assert no_signal.side == SignalAction.SELL.value
        assert no_signal.price == 0.42
        assert no_signal.size == 3.5
        assert no_signal.outcome_type == OutcomeType.NO
        assert "test-market-123" in no_signal.signal_id

    def test_evaluate_multiple_markets(self):
        """Test evaluation with multiple markets."""
        strategy = SpreadArb({"min_spread": 0.05, "trade_size": 1.0})

        market1 = {
            "market_slug": "market1",
            "yes_price": 0.6,
            "no_price": 0.5,  # spread = 0.1 > 0.05
            "outcomes": [{"id": "yes1"}, {"id": "no1"}],
        }

        market2 = {
            "market_slug": "market2",
            "yes_price": 0.51,
            "no_price": 0.48,  # spread = -0.01 < 0.05
            "outcomes": [{"id": "yes2"}, {"id": "no2"}],
        }

        market3 = {
            "market_slug": "market3",
            "yes_price": 0.7,
            "no_price": 0.4,  # spread = 0.1 > 0.05
            "outcomes": [{"id": "yes3"}, {"id": "no3"}],
        }

        data = {"market_snapshots": [market1, market2, market3]}
        signals = strategy.evaluate(data)

        # Should get signals for market1 and market3 only (4 total)
        assert len(signals) == 4

        market_slugs = {signal.market_slug for signal in signals}
        assert market_slugs == {"market1", "market3"}

    def test_get_strategy_config(self):
        """Test strategy configuration retrieval."""
        config = {"min_spread": 0.025, "trade_size": 2.5}
        strategy = SpreadArb(config)

        retrieved_config = strategy.get_strategy_config()

        assert retrieved_config["strategy_name"] == "SpreadArb"
        assert retrieved_config["min_spread"] == 0.025
        assert retrieved_config["trade_size"] == 2.5

    def test_update_config(self):
        """Test strategy configuration updates."""
        strategy = SpreadArb({"min_spread": 0.01, "trade_size": 1.0})

        # Update both parameters
        new_config = {"min_spread": 0.03, "trade_size": 4.0}
        strategy.update_config(new_config)

        assert strategy.min_spread == 0.03
        assert strategy.trade_size == 4.0

        # Update only one parameter
        strategy.update_config({"min_spread": 0.05})
        assert strategy.min_spread == 0.05
        assert strategy.trade_size == 4.0  # Should remain unchanged

        # Update with unknown parameter (should be ignored)
        strategy.update_config({"unknown_param": 999, "trade_size": 2.0})
        assert strategy.trade_size == 2.0
        assert not hasattr(strategy, "unknown_param")

    def test_edge_cases_and_robustness(self):
        """Test edge cases and robustness."""
        strategy = SpreadArb({})

        # Test with None values
        market_data = {
            "market_slug": "test",
            "yes_price": None,
            "no_price": 0.5,
            "outcomes": [{"id": "yes"}, {"id": "no"}],
        }
        data = {"market_snapshots": [market_data]}
        signals = strategy.evaluate(data)
        assert len(signals) == 0

        # Test with zero prices
        market_data = {
            "market_slug": "test",
            "yes_price": 0.0,
            "no_price": 0.0,
            "outcomes": [{"id": "yes"}, {"id": "no"}],
        }
        data = {"market_snapshots": [market_data]}
        signals = strategy.evaluate(data)
        assert len(signals) == 0  # spread = -1, below any reasonable threshold

        # Test with very high prices (edge case)
        market_data = {
            "market_slug": "test",
            "yes_price": 0.9,
            "no_price": 0.9,  # spread = 0.8
            "outcomes": [{"id": "yes"}, {"id": "no"}],
        }
        data = {"market_snapshots": [market_data]}
        signals = strategy.evaluate(data)
        assert len(signals) == 2  # Should generate signals for large spread


class TestSpreadArbIntegration:
    """Integration tests to ensure refactored code maintains original functionality."""

    def test_backward_compatibility(self):
        """Ensure refactored code produces same results as original logic."""
        strategy = SpreadArb({"min_spread": 0.02, "trade_size": 2.0})

        # Test case that should produce arbitrage signals
        test_data = {
            "market_snapshots": [
                {
                    "market_slug": "integration-test",
                    "yes_price": 0.55,
                    "no_price": 0.50,  # spread = 0.05 > 0.02
                    "outcomes": [{"id": "yes_integration"}, {"id": "no_integration"}],
                }
            ]
        }

        signals = strategy.evaluate(test_data)

        # Verify we get exactly 2 signals
        assert len(signals) == 2

        # Verify signal properties match expected behavior
        signal_types = {signal.outcome_type for signal in signals}
        assert signal_types == {OutcomeType.YES, OutcomeType.NO}

        signal_sides = {signal.side for signal in signals}
        assert signal_sides == {SignalAction.SELL.value}

        signal_sizes = {signal.size for signal in signals}
        assert signal_sizes == {2.0}

    @patch("inkedup_bot.strategies.spread_arbitrage.logger")
    def test_logging_behavior(self, mock_logger):
        """Test that logging works correctly in refactored code."""
        strategy = SpreadArb({"min_spread": 0.01})

        # Test logging for arbitrage opportunity
        test_data = {
            "market_snapshots": [
                {
                    "market_slug": "logging-test",
                    "yes_price": 0.6,
                    "no_price": 0.5,
                    "outcomes": [{"id": "yes"}, {"id": "no"}],
                }
            ]
        }

        strategy.evaluate(test_data)

        # Verify arbitrage opportunity was logged
        mock_logger.info.assert_called()
        log_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("Arbitrage opportunity found" in call for call in log_calls)
        assert any("logging-test" in call for call in log_calls)

        # Test logging for missing market slug
        test_data = {
            "market_snapshots": [
                {
                    "yes_price": 0.6,
                    "no_price": 0.5,
                    "outcomes": [{"id": "yes"}, {"id": "no"}],
                }
            ]
        }

        strategy.evaluate(test_data)
        mock_logger.warning.assert_called()
        warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
        assert any("missing market_slug" in call for call in warning_calls)
