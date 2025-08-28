"""
Comprehensive tests for the performance tracking system integration.

Tests all components of the performance tracking system including:
- Core performance tracking functionality
- Enhanced strategy base classes
- Performance analytics and reporting
- Integration with order client and state management
"""

import time
from unittest.mock import Mock

import pytest

from inkedup_bot.performance_analytics import PerformanceAnalytics
from inkedup_bot.performance_tracking import (
    PerformanceTracker,
    TradeStatus,
)
from inkedup_bot.signals import TradingSignal
from inkedup_bot.strategies.enhanced_base import (
    ComplementArbStrategy,
    SpreadArbStrategy,
)
from inkedup_bot.strategy_performance_integration import (
    PerformanceDashboard,
    PerformanceIntegratedOrderClient,
    StrategyManager,
)


class TestPerformanceTracker:
    """Test core performance tracking functionality."""

    @pytest.fixture
    def performance_tracker(self):
        return PerformanceTracker()

    def test_initialization(self, performance_tracker):
        """Test performance tracker initialization."""
        assert performance_tracker._tracking_active == False
        assert len(performance_tracker._strategy_metrics) == 0
        assert len(performance_tracker._trade_executions) == 0

    def test_signal_generation_tracking(self, performance_tracker):
        """Test signal generation tracking."""
        signal = TradingSignal(
            market_slug="test-market",
            token_id="token123",
            side="buy",
            price=0.6,
            size=10.0,
            outcome_type="yes",
        )
        signal.signal_id = "test_signal_001"

        performance_tracker.record_signal_generated(signal, "test_strategy")

        # Check if signal was recorded
        assert "test_strategy" in performance_tracker._strategy_metrics
        assert "test_signal_001" in performance_tracker._trade_executions

    def test_trade_execution_recording(self, performance_tracker):
        """Test trade execution recording."""
        signal = TradingSignal(
            market_slug="test-market",
            token_id="token123",
            side="buy",
            price=0.6,
            size=10.0,
        )
        signal.signal_id = "test_signal_001"

        # Record signal first
        performance_tracker.record_signal_generated(signal, "test_strategy")

        # Record execution
        performance_tracker.record_trade_execution(
            signal_id="test_signal_001",
            executed_price=0.58,
            executed_size=10.0,
            fees=0.1,
        )

        # Check execution was recorded
        assert "test_signal_001" in performance_tracker._trade_executions
        execution = performance_tracker._trade_executions["test_signal_001"]
        assert execution.executed_price == 0.58
        assert execution.executed_size == 10.0
        assert execution.fees_paid == 0.1
        assert execution.status == TradeStatus.FILLED

    def test_trade_outcome_recording(self, performance_tracker):
        """Test trade outcome recording."""
        signal = TradingSignal(
            market_slug="test-market",
            token_id="token123",
            side="buy",
            price=0.6,
            size=10.0,
        )
        signal.signal_id = "test_signal_001"

        # Record full trade lifecycle
        performance_tracker.record_signal_generated(signal, "test_strategy")
        performance_tracker.record_trade_execution("test_signal_001", 0.58, 10.0, 0.1)
        performance_tracker.record_trade_outcome(
            "test_signal_001", 0.65, 0.6, time.time()
        )

        # Check final status
        execution = performance_tracker._trade_executions["test_signal_001"]
        assert execution.exit_price == 0.65
        assert execution.realized_pnl == 0.6

        # Check strategy metrics updated
        metrics = performance_tracker._strategy_metrics["test_strategy"]
        assert metrics.total_trades == 1
        assert metrics.winning_trades == 1
        assert metrics.total_pnl == 0.6

    def test_performance_metrics_calculation(self, performance_tracker):
        """Test performance metrics calculation."""
        strategy_name = "test_strategy"

        # Simulate multiple trades
        for i in range(5):
            signal = TradingSignal(
                market_slug="test-market",
                token_id=f"token{i}",
                side="buy",
                price=0.5,
                size=10.0,
            )
            signal.signal_id = f"signal_{i}"

            pnl = 1.0 if i < 3 else -0.5  # 3 wins, 2 losses

            performance_tracker.record_signal_generated(signal, strategy_name)
            performance_tracker.record_trade_execution(signal.signal_id, 0.5, 10.0, 0.0)
            performance_tracker.record_trade_outcome(
                signal.signal_id, 0.5, pnl, time.time()
            )

        metrics = performance_tracker.get_strategy_performance(strategy_name)

        assert metrics.total_trades == 5
        assert metrics.winning_trades == 3
        assert metrics.losing_trades == 2
        assert metrics.win_rate == 0.6
        assert metrics.total_pnl == 2.0  # 3*1.0 - 2*0.5
        assert metrics.profit_factor == 3.0  # 3.0 / 1.0 (absolute gross loss)


class TestEnhancedStrategyBase:
    """Test enhanced strategy base classes."""

    @pytest.fixture
    def mock_performance_tracker(self):
        return Mock(spec=PerformanceTracker)

    @pytest.fixture
    def complement_strategy(self, mock_performance_tracker):
        config = {
            "enabled": True,
            "min_deviation_threshold": 0.02,
            "max_deviation_threshold": 0.15,
            "base_trade_size": 15.0,
        }
        return ComplementArbStrategy(config, mock_performance_tracker)

    def test_strategy_initialization(
        self, complement_strategy, mock_performance_tracker
    ):
        """Test strategy initialization with performance tracking."""
        assert complement_strategy.strategy_name == "complement_arbitrage"
        assert complement_strategy.enabled == True
        assert complement_strategy.performance_tracker == mock_performance_tracker
        assert complement_strategy.min_deviation_threshold == 0.02

    def test_signal_validation(self, complement_strategy):
        """Test signal validation in enhanced strategies."""
        # Valid signal
        valid_signal = TradingSignal(
            market_slug="test-market",
            token_id="token123",
            side="buy",
            price=0.5,
            size=10.0,
        )

        # Invalid signals
        invalid_price_signal = TradingSignal(
            market_slug="test-market",
            token_id="token123",
            side="buy",
            price=0.0,  # Invalid
            size=10.0,
        )

        invalid_side_signal = TradingSignal(
            market_slug="test-market",
            token_id="token123",
            side="invalid",  # Invalid
            price=0.5,
            size=10.0,
        )

        assert complement_strategy._is_valid_signal(valid_signal) == True
        assert complement_strategy._is_valid_signal(invalid_price_signal) == False
        assert complement_strategy._is_valid_signal(invalid_side_signal) == False

    def test_risk_checks(self, complement_strategy):
        """Test risk validation for signals."""
        # Signal within limits
        safe_signal = TradingSignal(
            market_slug="test-market",
            token_id="token123",
            side="buy",
            price=0.5,
            size=50.0,  # 25.0 notional value
        )

        # Signal exceeding risk limit
        risky_signal = TradingSignal(
            market_slug="test-market",
            token_id="token123",
            side="buy",
            price=0.8,
            size=200.0,  # 160.0 notional value (exceeds default 100.0 limit)
        )

        assert complement_strategy._passes_risk_checks(safe_signal) == True
        assert complement_strategy._passes_risk_checks(risky_signal) == False

    def test_complement_arbitrage_logic(self, complement_strategy):
        """Test complement arbitrage signal generation."""
        market_data = {
            "market_snapshots": [
                {
                    "slug": "test-market",
                    "tokens": [
                        {"token_id": "yes_token", "outcome": "yes", "price": 0.4},
                        {
                            "token_id": "no_token",
                            "outcome": "no",
                            "price": 0.7,  # Total = 1.1, deviation = 0.1
                        },
                    ],
                }
            ]
        }

        signals = complement_strategy.generate_signals(market_data)

        # Should generate 2 sell signals (prices too high)
        assert len(signals) == 2
        assert all(signal.side == "sell" for signal in signals)
        assert any(signal.token_id == "yes_token" for signal in signals)
        assert any(signal.token_id == "no_token" for signal in signals)


class TestStrategyManager:
    """Test centralized strategy manager."""

    @pytest.fixture
    def mock_performance_tracker(self):
        return Mock(spec=PerformanceTracker)

    @pytest.fixture
    def mock_order_client(self):
        return Mock()

    @pytest.fixture
    def strategy_manager(self, mock_performance_tracker, mock_order_client):
        integrated_client = Mock()
        integrated_client.order_client = mock_order_client
        return StrategyManager(mock_performance_tracker, integrated_client)

    def test_strategy_registration(self, strategy_manager, mock_performance_tracker):
        """Test strategy registration with manager."""
        strategy = ComplementArbStrategy()

        strategy_manager.register_strategy(strategy, {"enabled": True})

        assert "complement_arbitrage" in strategy_manager._strategies
        assert strategy.performance_tracker == mock_performance_tracker
        assert strategy_manager._strategies["complement_arbitrage"] == strategy

    def test_multiple_strategy_evaluation(self, strategy_manager):
        """Test evaluation of multiple strategies."""
        # Register multiple strategies
        complement_strategy = ComplementArbStrategy({"enabled": True})
        spread_strategy = SpreadArbStrategy({"enabled": True})

        strategy_manager.register_strategy(complement_strategy)
        strategy_manager.register_strategy(spread_strategy)

        # Mock market data
        market_data = {
            "market_snapshots": [
                {
                    "slug": "test-market",
                    "tokens": [
                        {
                            "token_id": "token1",
                            "outcome": "yes",
                            "price": 0.4,
                            "best_bid": 0.39,
                            "best_ask": 0.41,
                        }
                    ],
                }
            ]
        }

        all_signals = strategy_manager.evaluate_all_strategies(market_data)

        assert "complement_arbitrage" in all_signals
        assert "spread_arbitrage" in all_signals
        assert strategy_manager._evaluation_count == 1

    def test_strategy_enable_disable(self, strategy_manager):
        """Test enabling and disabling strategies."""
        strategy = ComplementArbStrategy({"enabled": True})
        strategy_manager.register_strategy(strategy)

        # Initially enabled
        assert strategy.enabled == True
        assert "complement_arbitrage" in strategy_manager.get_active_strategies()

        # Disable strategy
        strategy_manager.disable_strategy("complement_arbitrage")
        assert strategy.enabled == False
        assert "complement_arbitrage" not in strategy_manager.get_active_strategies()

        # Re-enable strategy
        strategy_manager.enable_strategy("complement_arbitrage")
        assert strategy.enabled == True
        assert "complement_arbitrage" in strategy_manager.get_active_strategies()


class TestPerformanceIntegration:
    """Test integration between components."""

    @pytest.fixture
    def mock_order_client(self):
        order_client = Mock()
        order_client.place_limit.return_value = "order_123"
        return order_client

    @pytest.fixture
    def performance_tracker(self):
        return PerformanceTracker()

    @pytest.fixture
    def integrated_client(self, mock_order_client, performance_tracker):
        return PerformanceIntegratedOrderClient(mock_order_client, performance_tracker)

    def test_order_placement_with_tracking(self, integrated_client, mock_order_client):
        """Test order placement with performance tracking."""
        order_id = integrated_client.place_limit(
            token_id="token123",
            side="buy",
            price=0.5,
            size=10.0,
            time_in_force="GTC",
            market_slug="test-market",
            outcome_type="yes",
            notional_value=5.0,
            risk_manager=None,
            signal_id="signal_001",
        )

        assert order_id == "order_123"
        assert "order_123" in integrated_client._pending_orders
        assert integrated_client._pending_orders["order_123"] == "signal_001"

        # Verify original order client was called
        mock_order_client.place_limit.assert_called_once()

    def test_order_fill_handling(self, integrated_client, performance_tracker):
        """Test order fill handling with performance tracking."""
        # Place order first
        integrated_client._pending_orders["order_123"] = "signal_001"

        # Simulate fill
        integrated_client.on_order_filled("order_123", 0.52, 10.0, 0.05)

        # Check performance tracker received the call
        assert "order_123" not in integrated_client._pending_orders

    def test_end_to_end_performance_tracking(self):
        """Test complete end-to-end performance tracking flow."""
        # Setup components
        performance_tracker = PerformanceTracker()
        mock_order_client = Mock()
        mock_order_client.place_limit.return_value = "order_123"

        integrated_client = PerformanceIntegratedOrderClient(
            mock_order_client, performance_tracker
        )
        strategy_manager = StrategyManager(performance_tracker, integrated_client)

        # Register strategy
        strategy = ComplementArbStrategy({"enabled": True})
        strategy_manager.register_strategy(strategy)

        # Generate market data that should create arbitrage opportunity
        market_data = {
            "market_snapshots": [
                {
                    "slug": "arb-market",
                    "tokens": [
                        {"token_id": "yes_token", "outcome": "yes", "price": 0.35},
                        {
                            "token_id": "no_token",
                            "outcome": "no",
                            "price": 0.6,  # Total = 0.95, deviation = 0.05 (above threshold)
                        },
                    ],
                }
            ]
        }

        # Evaluate strategies
        all_signals = strategy_manager.evaluate_all_strategies(market_data)

        # Execute signals
        execution_results = strategy_manager.execute_signals(all_signals)

        # Verify signals were generated and executed
        complement_signals = all_signals.get("complement_arbitrage", [])
        assert len(complement_signals) == 2  # Buy both tokens

        # Check order execution was attempted
        assert len(execution_results["complement_arbitrage"]) == 2

        # Verify performance tracking integration
        metrics = performance_tracker.get_strategy_performance("complement_arbitrage")
        assert len(performance_tracker._trade_executions) >= 2


class TestPerformanceAnalytics:
    """Test advanced performance analytics."""

    @pytest.fixture
    def performance_tracker_with_data(self):
        """Create performance tracker with sample data."""
        tracker = PerformanceTracker()

        # Add sample strategy data
        strategies = ["strategy_a", "strategy_b", "strategy_c"]

        for i, strategy in enumerate(strategies):
            for j in range(10):
                signal = TradingSignal(
                    market_slug=f"market_{j}",
                    token_id=f"token_{i}_{j}",
                    side="buy",
                    price=0.5,
                    size=10.0,
                )
                signal.signal_id = f"{strategy}_signal_{j}"

                # Varying performance: A > B > C
                base_pnl = (3 - i) * 0.5  # 1.0, 0.5, 0.0
                pnl = base_pnl if j < 7 else -0.2  # 70% win rate for all

                tracker.record_signal_generated(signal, strategy)
                tracker.record_trade_execution(signal.signal_id, 0.5, 10.0, 0.0)
                tracker.record_trade_outcome(signal.signal_id, 0.5, pnl, time.time())

        return tracker

    @pytest.fixture
    def performance_analytics(self, performance_tracker_with_data):
        return PerformanceAnalytics(performance_tracker_with_data)

    def test_performance_report_generation(self, performance_analytics):
        """Test performance report generation."""
        report = performance_analytics.generate_performance_report()

        assert "report_timestamp" in report
        assert "individual_performance" in report
        assert "comparative_analysis" in report
        assert "portfolio_metrics" in report
        assert len(report["individual_performance"]) == 3  # 3 strategies

    def test_individual_strategy_analysis(self, performance_analytics):
        """Test individual strategy analysis."""
        report = performance_analytics.generate_performance_report(["strategy_a"])

        # Check strategy A analysis
        strategy_data = report["individual_performance"]["strategy_a"]
        assert "performance_grade" in strategy_data
        assert "basic_metrics" in strategy_data
        assert "risk_metrics" in strategy_data

    def test_comparative_analysis(self, performance_analytics):
        """Test comparative analysis functionality."""
        report = performance_analytics.generate_performance_report(
            ["strategy_a", "strategy_b"]
        )

        comparative_data = report["comparative_analysis"]
        assert "rankings" in comparative_data
        assert "correlations" in comparative_data
        assert "diversification_score" in comparative_data

    def test_portfolio_metrics(self, performance_analytics):
        """Test portfolio metrics calculation."""
        report = performance_analytics.generate_performance_report(
            ["strategy_a", "strategy_b"]
        )

        portfolio_data = report["portfolio_metrics"]
        assert "active_strategies" in portfolio_data
        assert "total_trades" in portfolio_data
        assert "net_profit" in portfolio_data


class TestPerformanceDashboard:
    """Test performance dashboard functionality."""

    @pytest.fixture
    def mock_strategy_manager(self):
        manager = Mock()
        manager.get_strategy_performance_summary.return_value = {
            "strategy_a": {"total_trades": 10, "win_rate": 70.0, "net_profit": 5.0}
        }
        manager.get_manager_stats.return_value = {
            "total_strategies": 1,
            "active_strategies": 1,
        }
        return manager

    @pytest.fixture
    def mock_performance_tracker(self):
        tracker = Mock()
        tracker.get_performance_summary.return_value = {
            "total_strategies": 1,
            "total_trades": 10,
            "overall_pnl": 5.0,
        }
        tracker.get_strategy_ranking.return_value = [
            {"strategy_name": "strategy_a", "total_pnl": 5.0}
        ]
        tracker.get_trade_history.return_value = []
        return tracker

    @pytest.fixture
    def dashboard(self, mock_strategy_manager, mock_performance_tracker):
        return PerformanceDashboard(mock_strategy_manager, mock_performance_tracker)

    def test_dashboard_data_generation(self, dashboard):
        """Test dashboard data generation."""
        data = dashboard.get_dashboard_data()

        assert "timestamp" in data
        assert "summary" in data
        assert "strategy_performance" in data
        assert "manager_stats" in data
        assert "top_performers" in data
        assert "recent_trades" in data

    def test_performance_alerts(self, dashboard, mock_performance_tracker):
        """Test performance alert generation."""
        # Mock poor performing strategy
        poor_metrics = Mock()
        poor_metrics.win_rate = 0.2  # Low win rate
        poor_metrics.total_trades = 15
        poor_metrics.max_drawdown_percent = 30.0  # High drawdown
        poor_metrics.profit_factor = 0.5  # Negative expectancy

        mock_performance_tracker.get_strategy_performance.return_value = poor_metrics

        alert = dashboard.generate_performance_alert("poor_strategy")

        assert alert is not None
        assert alert["strategy_name"] == "poor_strategy"
        assert len(alert["alerts"]) >= 2  # Should have multiple alerts

        # Check for specific alert types
        alert_types = [alert["type"] for alert in alert["alerts"]]
        assert "low_win_rate" in alert_types
        assert "high_drawdown" in alert_types
        assert "negative_expectancy" in alert_types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
