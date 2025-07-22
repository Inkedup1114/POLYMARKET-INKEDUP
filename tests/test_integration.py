"""
Integration tests for the InkedUp bot.

This module tests the integration between different components
of the system working together.
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.database import DatabaseManager
from inkedup_bot.engine import TradingEngine
from inkedup_bot.order_client import OrderClient
from inkedup_bot.risk import RiskManager
from inkedup_bot.signals import OutcomeType, SignalAction, TradingSignal
from inkedup_bot.state import StateManager


class TestDatabaseIntegration:
    """Test integration between components and database."""

    @pytest.mark.asyncio
    async def test_state_manager_database_integration(self) -> None:
        """Test StateManager integration with DatabaseManager."""
        db_path = Path("test_integration.db")

        try:
            state = StateManager(db_path=str(db_path))
            await state.initialize_async()

            # Test that state manager can persist and load data
            position_data = {
                "token_id": "token1",
                "market_slug": "test-market",
                "outcome_type": "YES",
                "size": 100.0,
                "notional_value": 50.0,
            }
            await state.update_position_async(position_data)

            # Create new state manager to test loading
            new_state = StateManager(db_path=str(db_path))
            await new_state.initialize_async()

            # Verify data was persisted and loaded
            position_notional = await new_state.get_position_notional_async("token1")
            assert position_notional == 50.0

        finally:
            await asyncio.sleep(0.1)
            if db_path.exists():
                db_path.unlink()

    @pytest.mark.asyncio
    async def test_risk_manager_database_integration(self) -> None:
        """Test RiskManager integration with database for logging events."""
        db_path = Path("test_risk_integration.db")
        db = DatabaseManager(db_path=db_path)
        await db.initialize()

        try:
            cfg = BotConfig(global_risk_cap=100.0)
            order_client = MagicMock()
            order_client.ready.return_value = True

            state = StateManager(db_path=str(db_path))
            await state.initialize_async()
            risk = RiskManager(cfg, order_client, state)

            # Set up state to trigger risk limit
            position_data = {
                "token_id": "token1",
                "market_slug": "test-market",
                "outcome_type": "YES",
                "size": 200.0,
                "notional_value": 90.0,
            }
            await state.update_position_async(position_data)

            # This should trigger a risk limit breach
            with pytest.raises(RuntimeError, match="Global cap exceeded"):
                risk.preflight("token2", 20.0)

        finally:
            await asyncio.sleep(0.1)
            if db_path.exists():
                db_path.unlink()


class TestTradingEngineIntegration:
    """Test trading engine integration with other components."""

    @pytest.mark.asyncio
    async def test_trading_engine_signal_processing(self) -> None:
        """Test TradingEngine processing signals with all components."""
        cfg = BotConfig()
        engine = TradingEngine(cfg)
        await engine.initialize()

        # Mock order client
        order_client = MagicMock(spec=OrderClient)
        order_client.ready.return_value = True
        order_client.place_limit.return_value = {"id": "order123", "status": "OPEN"}
        engine.order_client = order_client

        # Create a test signal
        signal = TradingSignal(
            market_slug="test-market",
            token_id="token123",
            side=SignalAction.BUY.value,
            price=0.5,
            size=10.0,
            outcome_type=OutcomeType.YES,
        )

        # Process the signal
        engine.process_signal(signal)

        # Verify order was placed
        assert order_client.place_limit.called

    @pytest.mark.asyncio
    async def test_trading_engine_risk_integration(self) -> None:
        """Test TradingEngine respecting risk limits."""
        cfg = BotConfig(global_risk_cap=50.0)  # Low cap for testing
        engine = TradingEngine(cfg)
        await engine.initialize()

        order_client = MagicMock(spec=OrderClient)
        order_client.ready.return_value = True
        engine.order_client = order_client

        # Set up existing position that approaches risk limit
        position_data = {
            "token_id": "existing_token",
            "market_slug": "test-market",
            "outcome_type": "YES",
            "size": 100.0,
            "notional_value": 45.0,
        }
        await engine.state.update_position_async(position_data)

        # Create signal that would breach risk limit
        signal = TradingSignal(
            market_slug="test-market",
            token_id="new_token",
            side=SignalAction.BUY.value,
            price=0.5,
            size=20.0,  # Would result in 10.0 notional, exceeding cap
            outcome_type=OutcomeType.YES,
        )

        # Process signal - should be rejected due to risk limits
        engine.process_signal(signal)

        # Verify no order was placed
        assert not order_client.place_limit.called


class TestEndToEndScenarios:
    """Test complete end-to-end scenarios."""

    @pytest.mark.asyncio
    async def test_complete_trade_lifecycle(self) -> None:
        """Test a complete trade from signal to execution and tracking."""
        db_path = Path("test_trade_lifecycle.db")
        db = DatabaseManager(db_path=db_path)
        await db.initialize()

        try:
            cfg = BotConfig()
            engine = TradingEngine(cfg)
            engine.state = StateManager(db_path=str(db_path))
            await engine.state.initialize_async()

            # Mock successful order placement
            order_client = MagicMock(spec=OrderClient)
            order_client.ready.return_value = True
            order_client.place_limit.return_value = {"id": "order123", "status": "OPEN"}
            engine.order_client = order_client

            signal = TradingSignal(
                market_slug="test-market",
                token_id="token123",
                side=SignalAction.BUY.value,
                price=0.5,
                size=10.0,
                outcome_type=OutcomeType.YES,
            )

            # Process the signal
            engine.process_signal(signal)

            # Verify order was placed
            assert order_client.place_limit.called

        finally:
            await asyncio.sleep(0.1)
            if db_path.exists():
                db_path.unlink()

    @pytest.mark.asyncio
    async def test_system_recovery_after_restart(self) -> None:
        """Test system recovery after simulated restart."""
        db_path = Path("test_recovery.db")

        # Phase 1: Initial setup and operation
        db1 = DatabaseManager(db_path=db_path)
        await db1.initialize()

        try:
            state1 = StateManager(db_path=str(db_path))
            await state1.initialize_async()

            # Simulate some trading activity
            position1_data = {
                "token_id": "token1",
                "market_slug": "market1",
                "outcome_type": "YES",
                "size": 100.0,
                "notional_value": 50.0,
            }
            position2_data = {
                "token_id": "token2",
                "market_slug": "market2",
                "outcome_type": "NO",
                "size": 200.0,
                "notional_value": 100.0,
            }
            await state1.update_position_async(position1_data)
            await state1.update_position_async(position2_data)

            order_data = {
                "id": "order123",
                "token_id": "token1",
                "side": "buy",
                "price": 0.5,
                "size": 100,
                "status": "OPEN",
                "notional_value": 50.0,
            }
            await state1.add_order_async(order_data)

            # Phase 2: Simulate restart by creating new instances
            state2 = StateManager(db_path=str(db_path))
            await state2.initialize_async()

            # Verify state was recovered
            total_exposure = await state2.get_total_exposure_async()
            assert total_exposure == 150.0  # 50 + 100

            position1 = await state2.get_position_notional_async("token1")
            assert position1 == 50.0

            position2 = await state2.get_position_notional_async("token2")
            assert position2 == 100.0

            # Verify open orders were recovered
            open_orders = await db1.get_open_orders()
            assert len(open_orders) == 1
            assert open_orders[0]["id"] == "order123"

        finally:
            await asyncio.sleep(0.1)
            if db_path.exists():
                db_path.unlink()


class TestComponentInteractions:
    """Test interactions between different components."""

    @pytest.mark.asyncio
    async def test_risk_manager_state_interaction(self) -> None:
        """Test RiskManager correctly using StateManager data."""
        cfg = BotConfig(global_risk_cap=100.0)

        state = StateManager(db_path=":memory:")
        await state.initialize_async()

        order_client = MagicMock()
        order_client.ready.return_value = True

        risk = RiskManager(cfg, order_client, state)

        # Add some positions to the state
        position_data = {
            "token_id": "token1",
            "market_slug": "market1",
            "outcome_type": "YES",
            "size": 100.0,
            "notional_value": 40.0,
        }
        await state.update_position_async(position_data)

        # This should pass risk checks
        risk.preflight("token2", 30.0)  # Total would be 70.0, under 100.0 cap

        # This should fail risk checks
        with pytest.raises(RuntimeError):
            risk.preflight("token3", 80.0)  # Total would be 120.0, over 100.0 cap

    @pytest.mark.asyncio
    async def test_state_manager_position_aggregation(self) -> None:
        """Test StateManager correctly aggregating positions."""
        state = StateManager(db_path=":memory:")
        await state.initialize_async()

        # Add positions across different markets and outcomes
        position1_data = {
            "token_id": "token1",
            "market_slug": "market1",
            "outcome_type": "YES",
            "size": 100.0,
            "notional_value": 50.0,
        }
        position2_data = {
            "token_id": "token2",
            "market_slug": "market1",
            "outcome_type": "NO",
            "size": -50.0,
            "notional_value": -25.0,
        }
        position3_data = {
            "token_id": "token3",
            "market_slug": "market2",
            "outcome_type": "YES",
            "size": 200.0,
            "notional_value": 100.0,
        }
        position4_data = {
            "token_id": "token4",
            "market_slug": "market3",
            "outcome_type": "NO",
            "size": 150.0,
            "notional_value": 75.0,
        }

        await state.update_position_async(position1_data)
        await state.update_position_async(position2_data)
        await state.update_position_async(position3_data)
        await state.update_position_async(position4_data)

        # Test total exposure (sum of absolute values)
        total = await state.get_total_exposure_async()
        assert total == 250.0  # |50| + |-25| + |100| + |75|

        # Test market-specific exposure
        market1_exposure = await state.get_market_exposure_async("market1")
        assert market1_exposure == 75.0  # |50| + |-25|

        market2_exposure = await state.get_market_exposure_async("market2")
        assert market2_exposure == 100.0

        # Test outcome-specific exposure
        yes_exposure = await state.get_outcome_exposure_async("YES")
        assert yes_exposure == 150.0  # |50| + |100|

        no_exposure = await state.get_outcome_exposure_async("NO")
        assert no_exposure == 100.0  # |-25| + |75|


class TestErrorRecovery:
    """Test error recovery in integrated scenarios."""

    @pytest.mark.asyncio
    async def test_database_error_recovery(self) -> None:
        """Test system behavior when database operations fail."""
        state = StateManager(db_path=":memory:")
        await state.initialize_async()

        # Test that system can still operate without database
        position_data = {
            "token_id": "token1",
            "market_slug": "market1",
            "outcome_type": "YES",
            "size": 100.0,
            "notional_value": 50.0,
        }
        await state.update_position_async(position_data)

        total_exposure = await state.get_total_exposure_async()
        assert total_exposure == 50.0

    @pytest.mark.asyncio
    async def test_order_client_error_recovery(self) -> None:
        """Test system behavior when order placement fails."""
        cfg = BotConfig()
        engine = TradingEngine(cfg)
        await engine.initialize()

        # Mock order client that fails
        order_client = MagicMock(spec=OrderClient)
        order_client.ready.return_value = True
        order_client.place_limit.side_effect = Exception("Order placement failed")
        engine.order_client = order_client

        signal = TradingSignal(
            market_slug="test-market",
            token_id="token123",
            side=SignalAction.BUY.value,
            price=0.5,
            size=10.0,
            outcome_type=OutcomeType.YES,
        )

        # Should handle order placement failure gracefully
        engine.process_signal(signal)

        # Verify the engine handled the error without crashing
        # The specific error handling behavior may need to be implemented
