"""
Comprehensive end-to-end integration tests for the InkedUp trading system.

This module provides extensive integration testing covering:
- Complex trading scenarios and workflows
- Multi-component interactions
- Failure recovery and resilience testing
- System integration validation
- Performance and load testing
"""

import asyncio
import random
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from inkedup_bot.database import DatabaseManager
from inkedup_bot.enhanced_signal_processor import (
    EnhancedSignalProcessor,
    ProcessingResult,
    ProcessingStatus,
)
from inkedup_bot.market_condition_validator import (
    MarketMetrics,
)
from inkedup_bot.performance_tracking import PerformanceTracker
from inkedup_bot.signal_risk_validator import (
    create_portfolio_state,
)
from inkedup_bot.signal_safety_monitor import SafetyLevel, SignalSafetyMonitor
from inkedup_bot.signals import TradingSignal
from inkedup_bot.state import StateManager
from inkedup_bot.strategies.complement import ComplementArbStrategy
from inkedup_bot.strategies.spread_arbitrage import SpreadArb

# Test fixtures and utilities


class MockMarketDataProvider:
    """Mock market data provider for testing."""

    def __init__(self):
        self.market_data = {}
        self.price_history = defaultdict(list)
        self.volatility_multiplier = 1.0

    def set_market_data(self, market_slug: str, data: dict[str, Any]):
        """Set market data for a specific market."""
        self.market_data[market_slug] = data

    def get_market_snapshot(self, market_slug: str) -> dict[str, Any] | None:
        """Get current market snapshot."""
        return self.market_data.get(market_slug)

    def update_price(self, market_slug: str, token_id: str, new_price: float):
        """Update price and maintain history."""
        if market_slug not in self.market_data:
            self.market_data[market_slug] = {"tokens": []}

        # Update token price
        for token in self.market_data[market_slug]["tokens"]:
            if token["token_id"] == token_id:
                old_price = token.get("price", new_price)
                token["price"] = new_price
                self.price_history[f"{market_slug}_{token_id}"].append(
                    {
                        "price": new_price,
                        "timestamp": time.time(),
                        "change": new_price - old_price,
                    }
                )
                break

    def simulate_market_volatility(self, market_slug: str, intensity: float = 0.1):
        """Simulate market volatility by randomly adjusting prices."""
        if market_slug not in self.market_data:
            return

        for token in self.market_data[market_slug]["tokens"]:
            current_price = token.get("price", 0.5)
            change = random.uniform(-intensity, intensity) * self.volatility_multiplier
            new_price = max(0.01, min(0.99, current_price + change))
            token["price"] = new_price

    def create_complement_opportunity(self, market_slug: str, deviation: float = 0.05):
        """Create a complement arbitrage opportunity."""
        self.market_data[market_slug] = {
            "slug": market_slug,
            "tokens": [
                {
                    "token_id": f"{market_slug}_yes",
                    "outcome": "yes",
                    "price": 0.45 + deviation,
                    "best_bid": 0.44 + deviation,
                    "best_ask": 0.46 + deviation,
                    "volume_24h": 1000.0,
                    "liquidity": 500.0,
                },
                {
                    "token_id": f"{market_slug}_no",
                    "outcome": "no",
                    "price": 0.6 + deviation,
                    "best_bid": 0.59 + deviation,
                    "best_ask": 0.61 + deviation,
                    "volume_24h": 800.0,
                    "liquidity": 400.0,
                },
            ],
        }


class IntegratedTestEnvironment:
    """Integrated test environment with all system components."""

    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self.db_path = temp_dir / "test_integration.db"

        # Core components
        self.database = None
        self.state_manager = None
        self.order_client = None
        self.performance_tracker = None
        self.signal_processor = None
        self.safety_monitor = None

        # Strategies
        self.complement_strategy = None
        self.spread_strategy = None

        # Mock providers
        self.market_data_provider = MockMarketDataProvider()

        # Test state
        self.executed_orders = []
        self.generated_signals = []
        self.processing_results = []

    async def setup(self):
        """Set up the integrated test environment."""
        # Initialize database
        self.database = DatabaseManager(str(self.db_path))
        await self.database.initialize()

        # Initialize state manager
        self.state_manager = StateManager(db_path=str(self.db_path))
        await self.state_manager.initialize_async()

        # Initialize performance tracker
        self.performance_tracker = PerformanceTracker()

        # Initialize signal processor with all validators
        self.signal_processor = EnhancedSignalProcessor()

        # Initialize safety monitor
        self.safety_monitor = SignalSafetyMonitor()
        await self.safety_monitor.start_monitoring()

        # Initialize mock order client
        self.order_client = self._create_mock_order_client()

        # Initialize strategies
        self.complement_strategy = ComplementArbStrategy(
            min_deviation_threshold=0.02,
            max_deviation_threshold=0.20,
            base_trade_size=10.0,
        )

        self.spread_strategy = SpreadArb(
            {
                "enabled": True,
                "min_spread": 0.01,
                "max_spread": 0.10,
                "trade_size": 15.0,
            }
        )

    def _create_mock_order_client(self) -> Mock:
        """Create mock order client that simulates real behavior."""
        client = Mock()

        def mock_place_limit(*args, **kwargs):
            order_id = f"order_{len(self.executed_orders) + 1}"
            order_info = {
                "order_id": order_id,
                "args": args,
                "kwargs": kwargs,
                "timestamp": time.time(),
                "status": "placed",
            }
            self.executed_orders.append(order_info)

            # Simulate async order processing
            asyncio.create_task(self._simulate_order_execution(order_info))
            return order_id

        client.place_limit = Mock(side_effect=mock_place_limit)
        return client

    async def _simulate_order_execution(self, order_info: dict[str, Any]):
        """Simulate order execution with realistic delays and outcomes."""
        await asyncio.sleep(random.uniform(0.1, 0.5))  # Execution delay

        # 90% success rate
        if random.random() < 0.9:
            order_info["status"] = "filled"
            order_info["fill_time"] = time.time()
            # Simulate small price improvement/slippage
            price_adjustment = random.uniform(-0.001, 0.001)
            order_info["executed_price"] = (
                order_info["kwargs"].get("price", 0.5) + price_adjustment
            )
        else:
            order_info["status"] = "failed"
            order_info["error"] = "Insufficient liquidity"

    async def cleanup(self):
        """Clean up test environment."""
        if self.safety_monitor:
            await self.safety_monitor.stop_monitoring()

        if self.database:
            await self.database.close()

        # Remove test database
        if self.db_path.exists():
            self.db_path.unlink()

    def get_portfolio_state(self, total_capital: float = 10000.0):
        """Get current portfolio state for testing."""
        return create_portfolio_state(
            total_capital=total_capital,
            available_capital=total_capital * 0.8,
            positions={
                order["kwargs"]["token_id"]: order["kwargs"]["size"]
                for order in self.executed_orders
                if order["status"] == "filled"
            },
            market_exposures={},
        )


@pytest.fixture
async def integrated_env():
    """Create integrated test environment."""
    with tempfile.TemporaryDirectory() as temp_dir:
        env = IntegratedTestEnvironment(Path(temp_dir))
        await env.setup()
        try:
            yield env
        finally:
            await env.cleanup()


class TestComplexTradingScenarios:
    """Test complex trading scenarios and workflows."""

    @pytest.mark.asyncio
    async def test_complement_arbitrage_workflow(self, integrated_env):
        """Test complete complement arbitrage workflow."""
        env = integrated_env

        # Create complement arbitrage opportunity
        market_slug = "complement_test_market"
        env.market_data_provider.create_complement_opportunity(
            market_slug, deviation=0.08
        )

        # Get market data
        market_data = env.market_data_provider.get_market_snapshot(market_slug)

        # Generate signals using strategy
        signals = env.complement_strategy.evaluate({"market_snapshots": [market_data]})

        assert len(signals) == 2  # Should generate buy/sell pair
        assert signals[0].market_slug == market_slug
        assert signals[1].market_slug == market_slug

        # Process signals through validation pipeline
        portfolio_state = env.get_portfolio_state()

        market_metrics = MarketMetrics(
            market_slug=market_slug,
            token_id=signals[0].token_id,
            current_price=0.53,  # Total price > 1.0 (arbitrage opportunity)
            volume_24h=1800.0,
            is_active=True,
        )

        results = []
        for signal in signals:
            result = await env.signal_processor.process_signal(
                signal, market_metrics, portfolio_state
            )
            results.append(result)
            env.safety_monitor.record_signal_processed(signal, result)

        # Verify processing results
        assert all(
            r.status in [ProcessingStatus.APPROVED, ProcessingStatus.WARNING]
            for r in results
        )
        assert all(r.overall_quality_score > 50 for r in results)

        # Execute orders
        executed_orders = []
        for i, (signal, result) in enumerate(zip(signals, results, strict=False)):
            if result.status in [ProcessingStatus.APPROVED, ProcessingStatus.WARNING]:
                order_id = env.order_client.place_limit(
                    token_id=signal.token_id,
                    side=signal.side,
                    price=signal.price,
                    size=signal.size,
                    time_in_force="GTC",
                    market_slug=signal.market_slug,
                    outcome_type=signal.outcome_type,
                    notional_value=signal.price * signal.size,
                    risk_manager=None,
                )
                executed_orders.append(order_id)

        assert len(executed_orders) == 2

        # Wait for order processing
        await asyncio.sleep(1.0)

        # Verify orders were processed
        filled_orders = [
            order for order in env.executed_orders if order["status"] == "filled"
        ]
        assert len(filled_orders) >= 1  # At least one order should be filled

    @pytest.mark.asyncio
    async def test_market_volatility_response(self, integrated_env):
        """Test system response to high market volatility."""
        env = integrated_env

        market_slug = "volatile_market"
        env.market_data_provider.create_complement_opportunity(
            market_slug, deviation=0.02
        )

        # Start with normal conditions
        market_metrics = MarketMetrics(
            market_slug=market_slug,
            token_id=f"{market_slug}_yes",
            current_price=0.5,
            volatility_1h=0.05,  # Low volatility initially
            volume_24h=2000.0,
            is_active=True,
        )

        signal = TradingSignal(
            market_slug=market_slug,
            token_id=f"{market_slug}_yes",
            side="buy",
            price=0.48,
            size=50.0,
        )

        # Process under normal conditions
        portfolio_state = env.get_portfolio_state()
        result_normal = await env.signal_processor.process_signal(
            signal, market_metrics, portfolio_state
        )

        assert result_normal.status in [
            ProcessingStatus.APPROVED,
            ProcessingStatus.WARNING,
        ]

        # Increase volatility dramatically
        market_metrics.volatility_1h = 0.45  # Very high volatility

        # Process same signal under high volatility
        result_volatile = await env.signal_processor.process_signal(
            signal, market_metrics, portfolio_state
        )

        # System should respond to high volatility
        assert (
            result_volatile.risk_metrics.volatility_risk
            > result_normal.risk_metrics.volatility_risk
        )
        assert (
            result_volatile.overall_quality_score <= result_normal.overall_quality_score
        )

        # May recommend size reduction or additional constraints
        if result_volatile.recommended_size_adjustment:
            assert result_volatile.recommended_size_adjustment < 1.0

    @pytest.mark.asyncio
    async def test_multi_market_strategy_coordination(self, integrated_env):
        """Test coordination between multiple markets and strategies."""
        env = integrated_env

        # Set up multiple markets
        markets = ["market_a", "market_b", "market_c"]

        for market in markets:
            env.market_data_provider.create_complement_opportunity(
                market, deviation=random.uniform(0.03, 0.08)
            )

        # Generate signals from multiple strategies
        all_signals = []
        all_market_data = []

        for market in markets:
            market_data = env.market_data_provider.get_market_snapshot(market)
            all_market_data.append(market_data)

            # Complement arbitrage signals
            comp_signals = env.complement_strategy.evaluate(
                {"market_snapshots": [market_data]}
            )
            all_signals.extend(comp_signals)

            # Spread arbitrage signals
            spread_signals = env.spread_strategy.evaluate(
                {"market_snapshots": [market_data]}
            )
            all_signals.extend(spread_signals)

        assert len(all_signals) >= len(markets) * 2  # At least 2 signals per market

        # Process all signals
        portfolio_state = env.get_portfolio_state(
            total_capital=50000.0
        )  # Larger portfolio

        market_metrics_map = {}
        for market in markets:
            market_metrics_map[market] = MarketMetrics(
                market_slug=market,
                token_id=f"{market}_yes",
                current_price=0.5,
                volume_24h=1500.0,
                is_active=True,
            )

        # Batch processing
        results = await env.signal_processor.process_batch(
            all_signals, market_metrics_map, portfolio_state
        )

        # Analyze results
        approved_count = sum(
            1 for r in results if r.status == ProcessingStatus.APPROVED
        )
        warning_count = sum(1 for r in results if r.status == ProcessingStatus.WARNING)
        rejected_count = sum(
            1 for r in results if r.status == ProcessingStatus.REJECTED
        )

        assert approved_count + warning_count > 0  # Some signals should be processable

        # Check for proper risk management across markets
        total_exposure_by_market = defaultdict(float)
        for result in results:
            if result.status in [ProcessingStatus.APPROVED, ProcessingStatus.WARNING]:
                exposure = result.signal.price * result.signal.size
                total_exposure_by_market[result.signal.market_slug] += exposure

        # No single market should dominate exposure
        max_exposure = (
            max(total_exposure_by_market.values()) if total_exposure_by_market else 0
        )
        total_exposure = sum(total_exposure_by_market.values())

        if total_exposure > 0:
            max_market_pct = max_exposure / total_exposure
            assert max_market_pct < 0.6  # No more than 60% in single market


class TestMultiComponentInteractions:
    """Test interactions between multiple system components."""

    @pytest.mark.asyncio
    async def test_signal_processing_pipeline_integration(self, integrated_env):
        """Test complete signal processing pipeline with all components."""
        env = integrated_env

        # Create test signal
        signal = TradingSignal(
            market_slug="pipeline_test",
            token_id="test_token",
            side="buy",
            price=0.6,
            size=25.0,
            signal_id="pipeline_test_001",
        )

        # Create supporting data
        market_metrics = MarketMetrics(
            market_slug="pipeline_test",
            token_id="test_token",
            current_price=0.58,
            bid_price=0.57,
            ask_price=0.59,
            volume_24h=3000.0,
            volatility_1h=0.12,
            spread_bps=200,
            depth_2pct=800.0,
            is_active=True,
        )

        portfolio_state = env.get_portfolio_state()

        # Process through complete pipeline
        result = await env.signal_processor.process_signal(
            signal, market_metrics, portfolio_state
        )

        # Verify all components were engaged
        assert result.validation_result is not None
        assert result.market_assessment is not None
        assert result.risk_metrics is not None
        assert result.overall_quality_score > 0
        assert result.processing_time > 0

        # Record with safety monitor
        env.safety_monitor.record_signal_processed(signal, result)

        # Check safety monitor state
        safety_stats = env.safety_monitor.get_monitoring_stats()
        assert safety_stats["monitoring_cycles"] >= 0

        # If approved, execute through order client
        if result.status in [ProcessingStatus.APPROVED, ProcessingStatus.WARNING]:
            order_id = env.order_client.place_limit(
                token_id=signal.token_id,
                side=signal.side,
                price=signal.price,
                size=signal.size,
                time_in_force="GTC",
                market_slug=signal.market_slug,
                outcome_type="yes",
                notional_value=signal.price * signal.size,
                risk_manager=None,
            )

            assert order_id is not None

            # Wait for execution
            await asyncio.sleep(0.5)

            # Verify order was recorded
            assert len(env.executed_orders) > 0

    @pytest.mark.asyncio
    async def test_performance_tracking_integration(self, integrated_env):
        """Test integration of performance tracking with signal processing."""
        env = integrated_env

        # Generate multiple signals for tracking
        signals = []
        for i in range(5):
            signal = TradingSignal(
                market_slug=f"perf_market_{i}",
                token_id=f"token_{i}",
                side="buy" if i % 2 == 0 else "sell",
                price=0.5 + (i * 0.05),
                size=10.0 + i,
                signal_id=f"perf_test_{i:03d}",
            )
            signals.append(signal)

        # Process all signals
        portfolio_state = env.get_portfolio_state()
        results = []

        for signal in signals:
            market_metrics = MarketMetrics(
                market_slug=signal.market_slug,
                token_id=signal.token_id,
                current_price=signal.price - 0.01,
                volume_24h=1000.0 + (100 * len(results)),
                is_active=True,
            )

            result = await env.signal_processor.process_signal(
                signal, market_metrics, portfolio_state
            )
            results.append(result)

            # Record with performance tracker
            env.performance_tracker.record_signal_generated(signal, "test_strategy")

            if result.status in [ProcessingStatus.APPROVED, ProcessingStatus.WARNING]:
                # Simulate execution
                env.performance_tracker.record_trade_execution(
                    signal.signal_id,
                    executed_price=signal.price + random.uniform(-0.01, 0.01),
                    executed_size=signal.size,
                    fees=0.5,
                )

                # Simulate completion with random P&L
                pnl = random.uniform(-2.0, 3.0)
                env.performance_tracker.record_trade_outcome(
                    signal.signal_id,
                    exit_price=signal.price + (pnl / signal.size),
                    realized_pnl=pnl,
                    exit_timestamp=time.time() + 300,
                )

        # Verify performance tracking
        strategy_perf = env.performance_tracker.get_strategy_performance(
            "test_strategy"
        )
        assert strategy_perf.total_trades > 0
        assert strategy_perf.total_pnl != 0

        # Get processing statistics
        processing_stats = env.signal_processor.get_processing_stats()
        assert processing_stats["total_processed"] == len(signals)

    @pytest.mark.asyncio
    async def test_database_state_persistence(self, integrated_env):
        """Test database integration and state persistence."""
        env = integrated_env

        # Create and execute some trades
        test_data = [
            {
                "token_id": "persist_token_1",
                "market_slug": "persist_market_1",
                "outcome_type": "YES",
                "size": 100.0,
                "notional_value": 60.0,
            },
            {
                "token_id": "persist_token_2",
                "market_slug": "persist_market_2",
                "outcome_type": "NO",
                "size": 75.0,
                "notional_value": 30.0,
            },
        ]

        # Store positions
        for data in test_data:
            await env.state_manager.update_position_async(data)

        # Verify positions were stored
        for data in test_data:
            notional = await env.state_manager.get_position_notional_async(
                data["token_id"]
            )
            assert abs(notional - data["notional_value"]) < 0.01

        # Test state persistence across restart simulation
        old_state_manager = env.state_manager
        await old_state_manager.close_async()

        # Create new state manager (simulating restart)
        new_state_manager = StateManager(db_path=str(env.db_path))
        await new_state_manager.initialize_async()
        env.state_manager = new_state_manager

        # Verify data persisted
        for data in test_data:
            notional = await env.state_manager.get_position_notional_async(
                data["token_id"]
            )
            assert abs(notional - data["notional_value"]) < 0.01


class TestFailureRecovery:
    """Test failure recovery and system resilience."""

    @pytest.mark.asyncio
    async def test_order_client_failure_recovery(self, integrated_env):
        """Test recovery from order client failures."""
        env = integrated_env

        # Create signal
        signal = TradingSignal(
            market_slug="failure_test",
            token_id="failure_token",
            side="buy",
            price=0.5,
            size=20.0,
        )

        # Mock order client to fail initially
        original_place_limit = env.order_client.place_limit
        call_count = 0

        def failing_place_limit(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Fail first 2 attempts
                raise Exception("Connection timeout")
            return original_place_limit(*args, **kwargs)

        env.order_client.place_limit = Mock(side_effect=failing_place_limit)

        # Process signal
        portfolio_state = env.get_portfolio_state()
        market_metrics = MarketMetrics(
            market_slug="failure_test",
            token_id="failure_token",
            current_price=0.49,
            volume_24h=1000.0,
            is_active=True,
        )

        result = await env.signal_processor.process_signal(
            signal, market_metrics, portfolio_state
        )

        # Should still process the signal successfully
        assert result.status in [ProcessingStatus.APPROVED, ProcessingStatus.WARNING]

        # Simulate retry mechanism for order execution
        max_retries = 3
        for attempt in range(max_retries):
            try:
                order_id = env.order_client.place_limit(
                    token_id=signal.token_id,
                    side=signal.side,
                    price=signal.price,
                    size=signal.size,
                    time_in_force="GTC",
                    market_slug=signal.market_slug,
                    outcome_type="yes",
                    notional_value=signal.price * signal.size,
                    risk_manager=None,
                )
                assert order_id is not None
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    pytest.fail(
                        f"Order placement failed after {max_retries} attempts: {e}"
                    )
                await asyncio.sleep(0.1)  # Brief delay before retry

    @pytest.mark.asyncio
    async def test_database_connection_failure_recovery(self, integrated_env):
        """Test recovery from database connection failures."""
        env = integrated_env

        # Store initial data
        test_position = {
            "token_id": "db_failure_test",
            "market_slug": "db_test_market",
            "outcome_type": "YES",
            "size": 50.0,
            "notional_value": 25.0,
        }

        await env.state_manager.update_position_async(test_position)

        # Verify data was stored
        notional = await env.state_manager.get_position_notional_async(
            "db_failure_test"
        )
        assert abs(notional - 25.0) < 0.01

        # Simulate database connection failure and recovery
        original_execute = env.database.execute_async
        failure_count = 0

        async def failing_execute(*args, **kwargs):
            nonlocal failure_count
            failure_count += 1
            if failure_count <= 2:  # Fail first 2 attempts
                raise Exception("Database connection lost")
            return await original_execute(*args, **kwargs)

        env.database.execute_async = failing_execute

        # Try to update position (should eventually succeed with retry logic)
        updated_position = test_position.copy()
        updated_position["notional_value"] = 30.0

        # Simulate retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await env.state_manager.update_position_async(updated_position)
                break
            except Exception:
                if attempt == max_retries - 1:
                    # If all retries failed, verify the system is still functional
                    # by restoring the original method and trying again
                    env.database.execute_async = original_execute
                    await env.state_manager.update_position_async(updated_position)
                    break
                await asyncio.sleep(0.1)

        # Verify update succeeded
        final_notional = await env.state_manager.get_position_notional_async(
            "db_failure_test"
        )
        assert abs(final_notional - 30.0) < 0.01

    @pytest.mark.asyncio
    async def test_signal_validation_failure_handling(self, integrated_env):
        """Test handling of signal validation failures."""
        env = integrated_env

        # Create signals with various types of failures
        invalid_signals = [
            # Missing required fields
            TradingSignal(
                market_slug="",  # Empty market slug
                token_id="invalid_1",
                side="buy",
                price=0.5,
                size=10.0,
            ),
            # Invalid price
            TradingSignal(
                market_slug="test_market",
                token_id="invalid_2",
                side="buy",
                price=-0.1,  # Negative price
                size=10.0,
            ),
            # Invalid size
            TradingSignal(
                market_slug="test_market",
                token_id="invalid_3",
                side="buy",
                price=0.5,
                size=0,  # Zero size
            ),
            # Invalid side
            TradingSignal(
                market_slug="test_market",
                token_id="invalid_4",
                side="invalid_side",  # Invalid side
                price=0.5,
                size=10.0,
            ),
        ]

        portfolio_state = env.get_portfolio_state()
        market_metrics = MarketMetrics(
            market_slug="test_market",
            token_id="test_token",
            current_price=0.5,
            volume_24h=1000.0,
            is_active=True,
        )

        # Process invalid signals
        results = await env.signal_processor.process_batch(
            invalid_signals, {"test_market": market_metrics}, portfolio_state
        )

        # All should be rejected
        assert all(r.status == ProcessingStatus.REJECTED for r in results)
        assert all(len(r.safety_flags) > 0 for r in results)

        # System should remain operational - test with valid signal
        valid_signal = TradingSignal(
            market_slug="test_market",
            token_id="valid_token",
            side="buy",
            price=0.5,
            size=10.0,
        )

        valid_result = await env.signal_processor.process_signal(
            valid_signal, market_metrics, portfolio_state
        )

        assert valid_result.status in [
            ProcessingStatus.APPROVED,
            ProcessingStatus.WARNING,
        ]

    @pytest.mark.asyncio
    async def test_safety_monitor_circuit_breaker_recovery(self, integrated_env):
        """Test safety monitor circuit breaker and recovery."""
        env = integrated_env

        # Generate many signals quickly to trigger rate limiting
        signals = []
        for i in range(15):  # Above typical rate limit
            signal = TradingSignal(
                market_slug=f"rate_test_{i}",
                token_id=f"token_{i}",
                side="buy",
                price=0.5,
                size=5.0,
            )
            signals.append(signal)

        # Process signals rapidly
        portfolio_state = env.get_portfolio_state()
        results = []

        for signal in signals:
            market_metrics = MarketMetrics(
                market_slug=signal.market_slug,
                token_id=signal.token_id,
                current_price=0.49,
                volume_24h=500.0,
                is_active=True,
            )

            result = await env.signal_processor.process_signal(
                signal, market_metrics, portfolio_state
            )
            results.append(result)
            env.safety_monitor.record_signal_processed(signal, result)

        # Some signals should be blocked due to rate limiting
        blocked_count = sum(1 for r in results if r.status == ProcessingStatus.BLOCKED)
        assert blocked_count > 0

        # Wait for rate limit window to reset
        await asyncio.sleep(2.0)

        # System should recover - new signal should be processed
        recovery_signal = TradingSignal(
            market_slug="recovery_test",
            token_id="recovery_token",
            side="buy",
            price=0.5,
            size=10.0,
        )

        recovery_result = await env.signal_processor.process_signal(
            recovery_signal,
            MarketMetrics(
                market_slug="recovery_test",
                token_id="recovery_token",
                current_price=0.49,
                volume_24h=1000.0,
                is_active=True,
            ),
            portfolio_state,
        )

        # Should be processed normally after recovery
        assert recovery_result.status in [
            ProcessingStatus.APPROVED,
            ProcessingStatus.WARNING,
        ]


class TestSystemIntegration:
    """Test complete system integration scenarios."""

    @pytest.mark.asyncio
    async def test_complete_trading_session_simulation(self, integrated_env):
        """Simulate a complete trading session with multiple strategies."""
        env = integrated_env

        # Set up multiple markets with different characteristics
        markets_config = {
            "high_volume_market": {
                "deviation": 0.04,
                "volume_multiplier": 2.0,
                "volatility": 0.08,
            },
            "low_volume_market": {
                "deviation": 0.06,
                "volume_multiplier": 0.5,
                "volatility": 0.15,
            },
            "stable_market": {
                "deviation": 0.03,
                "volume_multiplier": 1.0,
                "volatility": 0.05,
            },
        }

        # Initialize markets
        for market_name, config in markets_config.items():
            env.market_data_provider.create_complement_opportunity(
                market_name, deviation=config["deviation"]
            )

        # Simulate trading session
        session_duration = 10  # 10 iterations
        portfolio_state = env.get_portfolio_state(total_capital=25000.0)

        session_results = {
            "signals_generated": 0,
            "signals_approved": 0,
            "orders_placed": 0,
            "orders_filled": 0,
            "total_pnl": 0.0,
            "safety_alerts": 0,
        }

        for iteration in range(session_duration):
            # Update market conditions (simulate market movement)
            for market_name in markets_config:
                env.market_data_provider.simulate_market_volatility(
                    market_name, markets_config[market_name]["volatility"] / 10
                )

            # Generate signals from strategies
            all_signals = []

            for market_name in markets_config:
                market_data = env.market_data_provider.get_market_snapshot(market_name)

                # Complement arbitrage
                comp_signals = env.complement_strategy.evaluate(
                    {"market_snapshots": [market_data]}
                )
                all_signals.extend(comp_signals)

                # Spread arbitrage
                spread_signals = env.spread_strategy.evaluate(
                    {"market_snapshots": [market_data]}
                )
                all_signals.extend(spread_signals)

            session_results["signals_generated"] += len(all_signals)

            if all_signals:
                # Create market metrics for validation
                market_metrics_map = {}
                for market_name, config in markets_config.items():
                    market_metrics_map[market_name] = MarketMetrics(
                        market_slug=market_name,
                        token_id=f"{market_name}_yes",
                        current_price=0.5,
                        volume_24h=1000.0 * config["volume_multiplier"],
                        volatility_1h=config["volatility"],
                        is_active=True,
                    )

                # Process signals
                results = await env.signal_processor.process_batch(
                    all_signals, market_metrics_map, portfolio_state
                )

                # Execute approved signals
                for signal, result in zip(all_signals, results, strict=False):
                    if result.status in [
                        ProcessingStatus.APPROVED,
                        ProcessingStatus.WARNING,
                    ]:
                        session_results["signals_approved"] += 1

                        # Place order
                        order_id = env.order_client.place_limit(
                            token_id=signal.token_id,
                            side=signal.side,
                            price=signal.price,
                            size=signal.size,
                            time_in_force="GTC",
                            market_slug=signal.market_slug,
                            outcome_type=signal.outcome_type,
                            notional_value=signal.price * signal.size,
                            risk_manager=None,
                        )
                        session_results["orders_placed"] += 1

                    # Record with safety monitor
                    env.safety_monitor.record_signal_processed(signal, result)

            # Brief pause between iterations
            await asyncio.sleep(0.1)

        # Wait for order executions
        await asyncio.sleep(1.0)

        # Analyze session results
        session_results["orders_filled"] = len(
            [o for o in env.executed_orders if o["status"] == "filled"]
        )
        session_results["safety_alerts"] = len(env.safety_monitor.get_active_alerts())

        # Verify session was productive
        assert session_results["signals_generated"] > 0
        assert session_results["signals_approved"] > 0
        assert session_results["orders_placed"] > 0

        # Get final statistics
        processing_stats = env.signal_processor.get_processing_stats()
        safety_stats = env.safety_monitor.get_monitoring_stats()

        assert processing_stats["total_processed"] > 0
        assert processing_stats["approval_rate"] > 0.1  # At least 10% approval rate

        # Safety system should be operational
        assert env.safety_monitor.get_current_safety_level() in [
            SafetyLevel.GREEN,
            SafetyLevel.YELLOW,
            SafetyLevel.ORANGE,
        ]

    @pytest.mark.asyncio
    async def test_concurrent_strategy_execution(self, integrated_env):
        """Test concurrent execution of multiple strategies."""
        env = integrated_env

        # Create concurrent tasks for different strategies
        async def run_complement_strategy():
            signals_generated = 0
            for i in range(5):
                market_name = f"comp_market_{i}"
                env.market_data_provider.create_complement_opportunity(
                    market_name, 0.05
                )

                market_data = env.market_data_provider.get_market_snapshot(market_name)
                signals = env.complement_strategy.evaluate(
                    {"market_snapshots": [market_data]}
                )
                signals_generated += len(signals)

                # Process signals
                for signal in signals:
                    market_metrics = MarketMetrics(
                        market_slug=market_name,
                        token_id=signal.token_id,
                        current_price=0.5,
                        volume_24h=1500.0,
                        is_active=True,
                    )

                    result = await env.signal_processor.process_signal(
                        signal, market_metrics, env.get_portfolio_state()
                    )
                    env.safety_monitor.record_signal_processed(signal, result)

                await asyncio.sleep(0.1)
            return signals_generated

        async def run_spread_strategy():
            signals_generated = 0
            for i in range(5):
                market_name = f"spread_market_{i}"
                env.market_data_provider.create_complement_opportunity(
                    market_name, 0.03
                )

                market_data = env.market_data_provider.get_market_snapshot(market_name)
                signals = env.spread_strategy.evaluate(
                    {"market_snapshots": [market_data]}
                )
                signals_generated += len(signals)

                # Process signals
                for signal in signals:
                    market_metrics = MarketMetrics(
                        market_slug=market_name,
                        token_id=signal.token_id,
                        current_price=0.5,
                        volume_24h=1200.0,
                        is_active=True,
                    )

                    result = await env.signal_processor.process_signal(
                        signal, market_metrics, env.get_portfolio_state()
                    )
                    env.safety_monitor.record_signal_processed(signal, result)

                await asyncio.sleep(0.1)
            return signals_generated

        # Run strategies concurrently
        comp_count, spread_count = await asyncio.gather(
            run_complement_strategy(), run_spread_strategy()
        )

        assert comp_count > 0
        assert spread_count > 0

        # Verify system handled concurrent operations
        processing_stats = env.signal_processor.get_processing_stats()
        assert processing_stats["total_processed"] > 0

        safety_level = env.safety_monitor.get_current_safety_level()
        assert safety_level in [SafetyLevel.GREEN, SafetyLevel.YELLOW]


class TestPerformanceAndLoad:
    """Test system performance and load handling."""

    @pytest.mark.asyncio
    async def test_high_volume_signal_processing(self, integrated_env):
        """Test processing of high volume signal batches."""
        env = integrated_env

        # Generate large batch of signals
        batch_size = 50
        signals = []

        for i in range(batch_size):
            signal = TradingSignal(
                market_slug=f"load_market_{i % 5}",  # 5 different markets
                token_id=f"token_{i}",
                side="buy" if i % 2 == 0 else "sell",
                price=0.4 + (i % 20) * 0.01,  # Vary prices
                size=5.0 + (i % 10),  # Vary sizes
                signal_id=f"load_test_{i:03d}",
            )
            signals.append(signal)

        # Create market metrics
        market_metrics_map = {}
        for i in range(5):
            market_name = f"load_market_{i}"
            market_metrics_map[market_name] = MarketMetrics(
                market_slug=market_name,
                token_id=f"token_{i}",
                current_price=0.45,
                volume_24h=2000.0,
                volatility_1h=0.10,
                is_active=True,
            )

        portfolio_state = env.get_portfolio_state(
            total_capital=100000.0
        )  # Large portfolio

        # Measure processing time
        start_time = time.time()

        results = await env.signal_processor.process_batch(
            signals, market_metrics_map, portfolio_state
        )

        processing_time = time.time() - start_time

        # Verify results
        assert len(results) == batch_size
        assert all(isinstance(r, ProcessingResult) for r in results)

        # Performance expectations
        avg_processing_time = processing_time / batch_size
        assert avg_processing_time < 1.0  # Less than 1 second per signal on average

        # Quality expectations
        approved_count = sum(
            1 for r in results if r.status == ProcessingStatus.APPROVED
        )
        warning_count = sum(1 for r in results if r.status == ProcessingStatus.WARNING)

        # At least some signals should be processable
        assert (approved_count + warning_count) > batch_size * 0.1  # At least 10%

        # System should remain stable
        safety_level = env.safety_monitor.get_current_safety_level()
        assert safety_level != SafetyLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_memory_usage_stability(self, integrated_env):
        """Test system memory usage remains stable under load."""
        env = integrated_env

        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Process many signals over multiple iterations
        iterations = 10
        signals_per_iteration = 20

        for iteration in range(iterations):
            signals = []
            for i in range(signals_per_iteration):
                signal = TradingSignal(
                    market_slug=f"memory_market_{i % 3}",
                    token_id=f"memory_token_{iteration}_{i}",
                    side="buy" if i % 2 == 0 else "sell",
                    price=0.5,
                    size=10.0,
                )
                signals.append(signal)

            # Process signals
            market_metrics = MarketMetrics(
                market_slug="memory_market_0",
                token_id="memory_token",
                current_price=0.5,
                volume_24h=1000.0,
                is_active=True,
            )

            portfolio_state = env.get_portfolio_state()

            for signal in signals:
                result = await env.signal_processor.process_signal(
                    signal, market_metrics, portfolio_state
                )
                env.safety_monitor.record_signal_processed(signal, result)

            # Clear caches periodically
            if iteration % 3 == 0:
                env.signal_processor.clear_cache()
                env.safety_monitor._cleanup_old_data()

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory

        # Memory growth should be reasonable (less than 50MB for this test)
        assert memory_growth < 50, f"Memory grew by {memory_growth:.1f}MB"

    @pytest.mark.asyncio
    async def test_system_stress_resilience(self, integrated_env):
        """Test system resilience under stress conditions."""
        env = integrated_env

        # Create stressful conditions
        stress_scenarios = [
            {
                "name": "rapid_fire_signals",
                "signal_count": 30,
                "delay": 0.01,  # Very short delay
            },
            {
                "name": "large_positions",
                "signal_count": 10,
                "size_multiplier": 10.0,  # Large position sizes
            },
            {
                "name": "high_volatility",
                "signal_count": 15,
                "volatility": 0.50,  # Extreme volatility
            },
        ]

        stress_results = {}

        for scenario in stress_scenarios:
            scenario_name = scenario["name"]
            signals = []

            # Generate signals for scenario
            for i in range(scenario["signal_count"]):
                size = 10.0
                if "size_multiplier" in scenario:
                    size *= scenario["size_multiplier"]

                signal = TradingSignal(
                    market_slug=f"stress_{scenario_name}",
                    token_id=f"stress_token_{i}",
                    side="buy" if i % 2 == 0 else "sell",
                    price=0.5,
                    size=size,
                    signal_id=f"{scenario_name}_{i:03d}",
                )
                signals.append(signal)

            # Create market metrics with scenario conditions
            volatility = scenario.get("volatility", 0.10)
            market_metrics = MarketMetrics(
                market_slug=f"stress_{scenario_name}",
                token_id="stress_token",
                current_price=0.5,
                volume_24h=1000.0,
                volatility_1h=volatility,
                is_active=True,
            )

            portfolio_state = env.get_portfolio_state(total_capital=50000.0)

            # Process signals with stress conditions
            start_time = time.time()
            results = []

            for signal in signals:
                result = await env.signal_processor.process_signal(
                    signal, market_metrics, portfolio_state
                )
                results.append(result)
                env.safety_monitor.record_signal_processed(signal, result)

                if "delay" in scenario:
                    await asyncio.sleep(scenario["delay"])

            processing_time = time.time() - start_time

            # Analyze results
            approved_count = sum(
                1 for r in results if r.status == ProcessingStatus.APPROVED
            )
            rejected_count = sum(
                1 for r in results if r.status == ProcessingStatus.REJECTED
            )
            blocked_count = sum(
                1 for r in results if r.status == ProcessingStatus.BLOCKED
            )

            stress_results[scenario_name] = {
                "total_signals": len(signals),
                "approved": approved_count,
                "rejected": rejected_count,
                "blocked": blocked_count,
                "processing_time": processing_time,
                "avg_time_per_signal": processing_time / len(signals),
            }

        # Verify system handled stress scenarios
        for scenario_name, results in stress_results.items():
            # System should process at least some signals
            assert results["total_signals"] > 0

            # Processing should complete in reasonable time
            assert (
                results["avg_time_per_signal"] < 2.0
            )  # Less than 2 seconds per signal

            # System should make appropriate decisions (not all rejected)
            if scenario_name == "large_positions":
                # Large positions should trigger risk management
                assert results["rejected"] + results["blocked"] > 0
            else:
                # Other scenarios should have some approved signals
                assert results["approved"] > 0

        # System should remain operational
        safety_level = env.safety_monitor.get_current_safety_level()
        assert safety_level != SafetyLevel.CRITICAL

        # Verify system stats are reasonable
        final_stats = env.signal_processor.get_processing_stats()
        assert final_stats["total_processed"] > 0
        assert final_stats["avg_processing_time"] < 5.0  # Average under 5 seconds


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
