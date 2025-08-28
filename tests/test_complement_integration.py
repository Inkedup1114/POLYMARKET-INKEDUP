"""
Integration tests for Complement Arbitrage Strategy.

These tests verify integration with the trading engine, risk management,
and other system components.
"""

from unittest.mock import Mock

import pytest

from inkedup_bot.signals import ComplementSignal, OutcomeType, SignalAction
from inkedup_bot.strategies.complement import ComplementArbStrategy
from inkedup_bot.strategies.complement_enhanced import EnhancedComplementArbStrategy


class MockRiskManager:
    """Mock risk manager for testing."""

    def __init__(self):
        self.per_market_risk_cap = 1000.0
        self.global_risk_cap = 5000.0
        self._market_exposures = {}
        self._total_exposure = 0.0

    def get_market_exposure(self, market_slug: str) -> float:
        return self._market_exposures.get(market_slug, 0.0)

    def get_total_exposure(self) -> float:
        return self._total_exposure

    def set_market_exposure(self, market_slug: str, exposure: float):
        self._market_exposures[market_slug] = exposure

    def set_total_exposure(self, exposure: float):
        self._total_exposure = exposure


class MockStateManager:
    """Mock state manager for testing."""

    def __init__(self):
        self.orders = {}
        self.positions = {}

    async def add_order(self, order_data):
        self.orders[order_data["id"]] = order_data

    async def get_position(self, token_id: str):
        return self.positions.get(token_id)

    async def update_position(self, position_data):
        self.positions[position_data["token_id"]] = position_data


class TestOriginalStrategyCompatibility:
    """Test that the original strategy still works as expected."""

    def test_original_strategy_basic_functionality(self):
        """Test that original ComplementArbStrategy still works."""
        strategy = ComplementArbStrategy()

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

        # Verify signal structure
        for sig in signals:
            assert hasattr(sig, "market_slug")
            assert hasattr(sig, "token_id")
            assert hasattr(sig, "side")
            assert hasattr(sig, "price")
            assert hasattr(sig, "size")
            assert hasattr(sig, "signal_id")
            assert hasattr(sig, "outcome_type")


class TestEnhancedStrategyBasicIntegration:
    """Test basic integration of Enhanced strategy."""

    @pytest.fixture
    def strategy(self):
        return EnhancedComplementArbStrategy(
            min_deviation_threshold=0.01, enable_performance_tracking=True
        )

    @pytest.fixture
    def risk_manager(self):
        return MockRiskManager()

    @pytest.fixture
    def state_manager(self):
        return MockStateManager()

    def test_strategy_with_risk_manager_integration(self, strategy, risk_manager):
        """Test strategy integration with risk manager."""
        strategy.set_risk_manager(risk_manager)

        # Risk manager allows trade
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)
        signals = strategy.on_complement(signal)
        assert len(signals) == 2

        # Risk manager blocks trade due to market exposure
        risk_manager.set_market_exposure("market", 1500.0)  # Above limit
        signals = strategy.on_complement(signal)
        assert len(signals) == 0

    def test_strategy_with_state_manager_integration(self, strategy, state_manager):
        """Test strategy integration with state manager."""
        strategy.set_state_manager(state_manager)

        # Strategy should work normally
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)
        signals = strategy.on_complement(signal)
        assert len(signals) == 2

        # Verify state manager is attached
        assert strategy.state_manager is state_manager

    def test_evaluate_method_integration(self, strategy):
        """Test the evaluate method works with market data rows."""
        market_rows = [
            {
                "market_slug": "market1",
                "yes_token_id": "yes1",
                "no_token_id": "no1",
                "yes_price": 0.6,
                "no_price": 0.5,
            },
            {
                "market_slug": "market2",
                "yes_token_id": "yes2",
                "no_token_id": "no2",
                "yes_price": 0.4,
                "no_price": 0.45,
            },
        ]

        signals = strategy.evaluate(market_rows)

        # Should generate signals for both markets
        assert len(signals) == 4

        # Verify signals are properly formed
        for signal in signals:
            assert signal.market_slug in ["market1", "market2"]
            assert signal.side in [SignalAction.BUY.value, SignalAction.SELL.value]
            assert signal.outcome_type in [OutcomeType.YES.value, OutcomeType.NO.value]
            assert signal.size > 0
            assert signal.price > 0
            assert signal.signal_id is not None


class TestRiskManagementIntegration:
    """Test integration with risk management systems."""

    @pytest.fixture
    def strategy(self):
        return EnhancedComplementArbStrategy(
            max_position_per_market=500.0,
            max_total_exposure=1000.0,
            max_concurrent_positions=5,
        )

    @pytest.fixture
    def risk_manager(self):
        return MockRiskManager()

    def test_position_limit_enforcement(self, strategy):
        """Test that position limits are enforced."""
        # Fill up concurrent positions
        for i in range(5):  # Max concurrent = 5
            strategy.active_positions[f"pos{i}"] = {
                "market_slug": f"market{i}",
                "total_size": 50.0,
                "timestamp": 1234567890,
            }

        # Should block new positions
        signal = ComplementSignal("new_market", "yes", "no", 0.6, 0.4, 0.1)
        signals = strategy.on_complement(signal)
        assert len(signals) == 0

    def test_market_exposure_limits(self, strategy):
        """Test per-market exposure limits."""
        # Add position near market limit
        strategy.active_positions["pos1"] = {
            "market_slug": "test_market",
            "total_size": 450.0,  # Near 500 limit
            "timestamp": 1234567890,
        }

        signal = ComplementSignal("test_market", "yes", "no", 0.6, 0.4, 0.1)

        # Should still allow small position
        signals = strategy.on_complement(signal)
        # May or may not generate signals depending on calculated size

        # Add position at market limit
        strategy.active_positions["pos2"] = {
            "market_slug": "test_market",
            "total_size": 50.0,  # Total = 500
            "timestamp": 1234567890,
        }

        # Should block new positions in this market
        signals = strategy.on_complement(signal)
        assert len(signals) == 0

    def test_total_exposure_limits(self, strategy):
        """Test total exposure limits."""
        # Fill up to total exposure limit
        for i in range(10):
            strategy.active_positions[f"pos{i}"] = {
                "market_slug": f"market{i}",
                "total_size": 100.0,  # Total = 1000
                "timestamp": 1234567890,
            }

        # Should block new positions
        signal = ComplementSignal("new_market", "yes", "no", 0.6, 0.4, 0.1)
        signals = strategy.on_complement(signal)
        assert len(signals) == 0

    def test_risk_manager_integration(self, strategy, risk_manager):
        """Test comprehensive risk manager integration."""
        strategy.set_risk_manager(risk_manager)

        # Normal operation
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)
        signals = strategy.on_complement(signal)
        assert len(signals) == 2

        # Risk manager blocks due to global exposure
        risk_manager.set_total_exposure(6000.0)  # Above limit
        signals = strategy.on_complement(signal)
        assert len(signals) == 0

        # Reset and test market-specific blocking
        risk_manager.set_total_exposure(0.0)
        risk_manager.set_market_exposure("market", 1500.0)  # Above limit
        signals = strategy.on_complement(signal)
        assert len(signals) == 0


class TestPerformanceTracking:
    """Test performance tracking integration."""

    @pytest.fixture
    def strategy(self):
        return EnhancedComplementArbStrategy(enable_performance_tracking=True)

    def test_metrics_tracking(self, strategy):
        """Test that metrics are tracked correctly."""
        assert strategy.metrics is not None

        # Initial state
        assert strategy.metrics.signals_generated == 0

        # Generate some signals
        signal1 = ComplementSignal("market1", "yes", "no", 0.6, 0.4, 0.1)
        signals1 = strategy.on_complement(signal1)
        assert len(signals1) == 2

        # Check metrics updated
        assert strategy.metrics.signals_generated == 1
        assert strategy.metrics.avg_deviation == 0.1

        # Generate more signals
        signal2 = ComplementSignal("market2", "yes", "no", 0.7, 0.25, 0.05)
        signals2 = strategy.on_complement(signal2)
        assert len(signals2) == 2

        # Check metrics updated again
        assert strategy.metrics.signals_generated == 2
        assert abs(strategy.metrics.avg_deviation - 0.075) < 0.001  # (0.1 + 0.05) / 2
        assert strategy.metrics.max_deviation == 0.1

    def test_strategy_metrics_output(self, strategy):
        """Test strategy metrics output."""
        # Generate some activity
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)
        strategy.on_complement(signal)

        metrics = strategy.get_strategy_metrics()

        # Check basic configuration
        assert metrics["strategy_name"] == "EnhancedComplementArbStrategy"
        assert "min_deviation_threshold" in metrics
        assert "performance_metrics" in metrics

        # Check performance metrics
        perf_metrics = metrics["performance_metrics"]
        assert perf_metrics["signals_generated"] == 1
        assert perf_metrics["avg_deviation"] == 0.1

    def test_metrics_reset(self, strategy):
        """Test metrics reset functionality."""
        # Generate activity
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)
        strategy.on_complement(signal)

        assert strategy.metrics.signals_generated == 1

        # Reset metrics
        strategy.reset_metrics()

        assert strategy.metrics.signals_generated == 0
        assert strategy.metrics.avg_deviation == 0.0


class TestEdgeCaseIntegration:
    """Test integration edge cases and error conditions."""

    @pytest.fixture
    def strategy(self):
        return EnhancedComplementArbStrategy()

    def test_malformed_market_data_handling(self, strategy):
        """Test handling of malformed market data in evaluate method."""
        malformed_rows = [
            {},  # Empty row
            {"market_slug": "partial"},  # Missing required fields
            {"invalid": "structure"},  # Wrong structure
            None,  # Null row
        ]

        # Should handle gracefully without exceptions
        signals = strategy.evaluate(malformed_rows)
        assert len(signals) == 0

    def test_risk_manager_exceptions(self, strategy):
        """Test handling of risk manager exceptions."""
        # Create risk manager that throws exceptions
        risk_manager = Mock()
        risk_manager.get_market_exposure.side_effect = Exception("Risk error")
        risk_manager.get_total_exposure.side_effect = Exception("Total error")

        strategy.set_risk_manager(risk_manager)

        # Should handle exceptions gracefully
        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)
        signals = strategy.on_complement(signal)

        # Should block trades when risk manager errors (conservative approach)
        assert len(signals) == 0

    def test_position_cleanup_integration(self, strategy):
        """Test position cleanup with very short decay time."""
        import time

        # Set very short decay time
        strategy.position_decay_hours = 0.0001  # ~0.36 seconds

        # Add an old position
        old_time = time.time() - 1.0  # 1 second ago
        strategy.active_positions["old"] = {
            "market_slug": "old_market",
            "timestamp": old_time,
            "total_size": 50.0,
        }

        # Evaluate should trigger cleanup
        signals = strategy.evaluate(
            [
                {
                    "market_slug": "market",
                    "yes_token_id": "yes",
                    "no_token_id": "no",
                    "yes_price": 0.6,
                    "no_price": 0.4,
                }
            ]
        )

        # Old position should be cleaned up
        assert "old" not in strategy.active_positions

        # New signals should be generated (deviation = 0.6 + 0.4 - 1.0 = 0.0, too small)
        # Let's use a signal that will generate trades
        signals = strategy.evaluate(
            [
                {
                    "market_slug": "market",
                    "yes_token_id": "yes",
                    "no_token_id": "no",
                    "yes_price": 0.6,
                    "no_price": 0.5,  # Sum = 1.1, deviation = 0.1
                }
            ]
        )
        assert len(signals) == 2


class TestStrategyComparison:
    """Compare original and enhanced strategies."""

    def test_signal_compatibility(self):
        """Test that both strategies generate compatible signals."""
        original = ComplementArbStrategy()
        enhanced = EnhancedComplementArbStrategy()

        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)

        original_signals = original.on_complement(signal)
        enhanced_signals = enhanced.on_complement(signal)

        assert len(original_signals) == len(enhanced_signals)

        # Signals should have same basic structure (though values may differ)
        for orig, enh in zip(original_signals, enhanced_signals, strict=False):
            assert orig.market_slug == enh.market_slug
            assert orig.side == enh.side
            assert orig.outcome_type == enh.outcome_type
            assert orig.price == enh.price
            # Sizes may differ due to different sizing logic

    def test_threshold_behavior_consistency(self):
        """Test that threshold behavior is consistent between strategies."""
        config = {
            "min_deviation_threshold": 0.02,
            "max_deviation_threshold": 0.15,
        }

        original = ComplementArbStrategy(**config)
        enhanced = EnhancedComplementArbStrategy(**config)

        # Below minimum threshold
        signal_low = ComplementSignal("market", "yes", "no", 0.505, 0.495, 0.01)
        assert len(original.on_complement(signal_low)) == 0
        assert len(enhanced.on_complement(signal_low)) == 0

        # Above maximum threshold
        signal_high = ComplementSignal("market", "yes", "no", 0.8, 0.4, 0.2)
        assert len(original.on_complement(signal_high)) == 0
        assert len(enhanced.on_complement(signal_high)) == 0

        # Within thresholds
        signal_valid = ComplementSignal("market", "yes", "no", 0.6, 0.35, 0.05)
        assert len(original.on_complement(signal_valid)) == 2
        assert len(enhanced.on_complement(signal_valid)) == 2


class TestIntegrationScenarios:
    """Test real-world integration scenarios."""

    @pytest.fixture
    def full_setup(self):
        """Set up strategy with all components."""
        strategy = EnhancedComplementArbStrategy(
            min_deviation_threshold=0.01,
            max_position_per_market=1000.0,
            max_total_exposure=5000.0,
            enable_performance_tracking=True,
        )

        risk_manager = MockRiskManager()
        state_manager = MockStateManager()

        strategy.set_risk_manager(risk_manager)
        strategy.set_state_manager(state_manager)

        return strategy, risk_manager, state_manager

    def test_full_trading_scenario(self, full_setup):
        """Test a complete trading scenario."""
        strategy, risk_manager, state_manager = full_setup

        # Market data with opportunities
        market_data = [
            {
                "market_slug": "election_market",
                "yes_token_id": "election_yes",
                "no_token_id": "election_no",
                "yes_price": 0.6,
                "no_price": 0.5,  # Sum = 1.1, sell both
            },
            {
                "market_slug": "sports_market",
                "yes_token_id": "sports_yes",
                "no_token_id": "sports_no",
                "yes_price": 0.4,
                "no_price": 0.45,  # Sum = 0.85, buy both
            },
        ]

        # Evaluate markets
        signals = strategy.evaluate(market_data)

        # Should generate 4 signals (2 per market)
        assert len(signals) == 4

        # Verify signal distribution
        election_signals = [s for s in signals if s.market_slug == "election_market"]
        sports_signals = [s for s in signals if s.market_slug == "sports_market"]

        assert len(election_signals) == 2
        assert len(sports_signals) == 2

        # Election market should have sell signals
        assert all(s.side == SignalAction.SELL.value for s in election_signals)

        # Sports market should have buy signals
        assert all(s.side == SignalAction.BUY.value for s in sports_signals)

        # Check performance tracking
        assert strategy.metrics.signals_generated == 2  # Two markets processed

        # Check position tracking
        assert len(strategy.active_positions) == 2  # Two positions tracked

    def test_progressive_risk_limits(self, full_setup):
        """Test how strategy behaves as risk limits are approached."""
        strategy, risk_manager, state_manager = full_setup

        signal = ComplementSignal("market", "yes", "no", 0.6, 0.4, 0.1)

        # Stage 1: Normal operation
        signals = strategy.on_complement(signal)
        assert len(signals) == 2

        # Stage 2: Add some exposure
        for i in range(3):
            strategy.active_positions[f"pos{i}"] = {
                "market_slug": f"market{i}",
                "total_size": 800.0,
                "timestamp": 1234567890,
            }

        # Should still work but with adjusted sizing
        signals = strategy.on_complement(signal)
        # Behavior depends on risk adjustment logic

        # Stage 3: Approach total exposure limit
        for i in range(3, 6):
            strategy.active_positions[f"pos{i}"] = {
                "market_slug": f"market{i}",
                "total_size": 800.0,
                "timestamp": 1234567890,
            }
        # Total exposure now: 6 * 800 = 4800, close to 5000 limit

        signals = strategy.on_complement(signal)
        # May be blocked or heavily reduced

        # Stage 4: Exceed limit
        strategy.active_positions["final"] = {
            "market_slug": "final_market",
            "total_size": 300.0,  # Total = 5100, over limit
            "timestamp": 1234567890,
        }

        signals = strategy.on_complement(signal)
        assert len(signals) == 0  # Should be blocked


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
