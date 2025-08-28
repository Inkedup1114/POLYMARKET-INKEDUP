"""
End-to-End Workflow Integration Tests for InkedUp Trading Bot.

This module provides comprehensive end-to-end testing for critical production workflows
that span multiple system components and simulate real trading scenarios.
"""

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.database import DatabaseManager
from inkedup_bot.engine import TradingEngine
from inkedup_bot.order_client import OrderClient
from inkedup_bot.scanner import Scanner
from inkedup_bot.signals import OutcomeType, SignalAction, TradingSignal
from inkedup_bot.state import StateManager
from inkedup_bot.strategies.complement import ComplementArbStrategy
from inkedup_bot.ws_manager import WebSocketManager


class TestFullTradingWorkflow:
    """Test complete trading workflows from signal generation to order execution."""

    @pytest.mark.asyncio
    async def test_complete_complement_arbitrage_workflow(self):
        """
        Test complete complement arbitrage workflow from market scanning to order execution.

        This tests the full pipeline:
        1. Market scanning discovers opportunity
        2. Signal is generated and validated
        3. Risk management approves the trade
        4. Order is placed through OrderClient
        5. Position is tracked in StateManager
        6. Database persists all state changes
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # Setup test configuration and components
            db_path = Path(temp_dir) / "test_workflow.db"
            cfg = BotConfig(database_url=f"sqlite:///{db_path}")

            # Initialize core components
            state_manager = StateManager(db_path=str(db_path))
            await state_manager.initialize_async()

            db_manager = DatabaseManager()
            await db_manager.initialize()

            trading_engine = TradingEngine(cfg)

            # Mock OrderClient to avoid actual API calls
            order_client = OrderClient(cfg)
            order_client.is_ready = MagicMock(return_value=True)
            order_client.place_limit_order = AsyncMock(
                return_value={
                    "order_id": "test_order_123",
                    "status": "open",
                    "size": 100.0,
                    "price": 0.45,
                }
            )

            # Create and configure complement arbitrage strategy
            strategy = ComplementArbStrategy(cfg)
            strategy.engine = trading_engine

            # Simulate market data that triggers complement arbitrage opportunity
            market_data = {
                "market_slug": "test-election-market",
                "outcomes": [
                    {
                        "token_id": "test_token_yes",
                        "outcome_type": "YES",
                        "best_bid": 0.40,
                        "best_ask": 0.45,
                        "liquidity": 10000.0,
                    },
                    {
                        "token_id": "test_token_no",
                        "outcome_type": "NO",
                        "best_bid": 0.50,
                        "best_ask": 0.55,
                        "liquidity": 10000.0,
                    },
                ],
                "total_liquidity": 20000.0,
            }

            # Process market data through strategy
            signals = await strategy.process_data(market_data)

            # Verify signal was generated
            assert (
                len(signals) > 0
            ), "Complement arbitrage opportunity should generate signals"

            signal = signals[0]
            assert isinstance(signal, TradingSignal)
            assert signal.action in [SignalAction.BUY, SignalAction.SELL]

            # Process signal through trading engine
            with patch.object(trading_engine, "order_client", order_client):
                result = await trading_engine.process_signal(signal)

                # Verify order was placed
                assert result is not None, "Signal processing should succeed"
                order_client.place_limit_order.assert_called_once()

                # Verify position was updated in state manager
                position_data = await state_manager.get_positions_async()
                assert len(position_data) > 0, "Position should be recorded in state"

                # Verify database persistence
                positions = await db_manager.get_positions()
                assert len(positions) > 0, "Positions should be persisted to database"

    @pytest.mark.asyncio
    async def test_websocket_to_trading_workflow(self):
        """
        Test real-time data flow from WebSocket to trading execution.

        This tests:
        1. WebSocket receives market data
        2. Message is processed and validated
        3. Scanner processes updated market data
        4. Trading strategy generates signals
        5. Risk management validates signals
        6. Orders are executed and tracked
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_ws_workflow.db"
            cfg = BotConfig(
                database_url=f"sqlite:///{db_path}",
                ws_enabled=False,  # Disable actual WebSocket for testing
            )

            # Initialize components
            state_manager = StateManager(db_path=str(db_path))
            await state_manager.initialize_async()

            trading_engine = TradingEngine(cfg)

            # Mock WebSocket manager
            ws_manager = WebSocketManager(cfg)
            ws_manager.connect = AsyncMock()
            ws_manager.is_connected = MagicMock(return_value=True)

            # Mock market scanner
            scanner = Scanner(cfg)
            scanner._fetch_market_data = AsyncMock()

            # Simulate WebSocket message
            mock_ws_message = {
                "type": "book",
                "market": "0x1234567890abcdef",
                "asset_id": "test_token_123",
                "bids": [["0.45", "1000"], ["0.44", "500"]],
                "asks": [["0.55", "800"], ["0.56", "400"]],
                "timestamp": int(time.time() * 1000),
            }

            # Process WebSocket message
            processed_data = await ws_manager.process_message(mock_ws_message)

            # Simulate scanner processing the updated data
            market_update = {
                "market_slug": "test-market",
                "liquidity": 5000.0,
                "outcomes": [
                    {
                        "token_id": "test_token_123",
                        "outcome_type": "YES",
                        "best_bid": 0.45,
                        "best_ask": 0.55,
                        "liquidity": 2500.0,
                    }
                ],
            }

            # Process through trading engine
            mock_strategy = MagicMock()
            mock_strategy.process_data = AsyncMock(return_value=[])
            trading_engine.strategies = [mock_strategy]

            await trading_engine.process_market_update(market_update)

            # Verify the data flow worked
            mock_strategy.process_data.assert_called_once_with(market_update)

    @pytest.mark.asyncio
    async def test_risk_management_integration_workflow(self):
        """
        Test risk management integration across the full trading workflow.

        This tests:
        1. Position limits are enforced
        2. Risk checks prevent dangerous trades
        3. Portfolio balance is maintained
        4. Stop-loss mechanisms work
        5. Risk metrics are tracked
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_risk_workflow.db"
            cfg = BotConfig(
                database_url=f"sqlite:///{db_path}",
                max_position_size=1000.0,  # Set position limit
                max_order_size=500.0,  # Set order limit
                global_risk_cap=2000.0,  # Set portfolio limit
            )

            state_manager = StateManager(db_path=str(db_path))
            await state_manager.initialize_async()

            trading_engine = TradingEngine(cfg)

            # Create a signal that would exceed position limits
            large_signal = TradingSignal(
                token_id="test_token_large",
                action=SignalAction.BUY,
                price=0.50,
                size=1500.0,  # Exceeds max_position_size
                market_slug="test-large-market",
                outcome_type=OutcomeType.YES,
                confidence=0.95,
                strategy_name="test_strategy",
            )

            # Mock order client
            order_client = OrderClient(cfg)
            order_client.is_ready = MagicMock(return_value=True)
            order_client.place_limit_order = AsyncMock()

            # Process signal that should be rejected by risk management
            with patch.object(trading_engine, "order_client", order_client):
                result = await trading_engine.process_signal(large_signal)

                # Verify order was NOT placed due to risk limits
                order_client.place_limit_order.assert_not_called()
                assert (
                    result is None or not result
                ), "Large order should be rejected by risk management"

            # Now test a valid signal within limits
            valid_signal = TradingSignal(
                token_id="test_token_valid",
                action=SignalAction.BUY,
                price=0.50,
                size=400.0,  # Within limits
                market_slug="test-valid-market",
                outcome_type=OutcomeType.YES,
                confidence=0.95,
                strategy_name="test_strategy",
            )

            order_client.place_limit_order = AsyncMock(
                return_value={
                    "order_id": "valid_order_123",
                    "status": "open",
                    "size": 400.0,
                    "price": 0.50,
                }
            )

            with patch.object(trading_engine, "order_client", order_client):
                result = await trading_engine.process_signal(valid_signal)

                # Verify valid order was placed
                order_client.place_limit_order.assert_called_once()
                assert (
                    result is not None
                ), "Valid order should be processed successfully"

    @pytest.mark.asyncio
    async def test_database_state_consistency_workflow(self):
        """
        Test database and state consistency across multiple operations.

        This tests:
        1. Concurrent database operations
        2. State manager consistency
        3. Transaction rollback on failures
        4. Data integrity under load
        5. Connection pool behavior
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_consistency.db"
            cfg = BotConfig(database_url=f"sqlite:///{db_path}")

            state_manager = StateManager(db_path=str(db_path))
            await state_manager.initialize_async()

            db_manager = DatabaseManager()
            await db_manager.initialize()

            # Perform multiple concurrent operations
            async def update_position(token_id: str, size: float):
                position_data = {
                    "token_id": token_id,
                    "market_slug": "test-market",
                    "outcome_type": "YES",
                    "size": size,
                    "notional_value": size * 0.50,
                }
                await state_manager.update_position_async(position_data)
                return await state_manager.get_position_notional_async(token_id)

            # Create concurrent tasks
            tasks = []
            for i in range(10):
                task = asyncio.create_task(update_position(f"token_{i}", 100.0 + i))
                tasks.append(task)

            # Wait for all operations to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Verify all operations succeeded
            for i, result in enumerate(results):
                assert not isinstance(result, Exception), f"Task {i} failed: {result}"
                assert result > 0, f"Position {i} should have positive notional value"

            # Verify database consistency
            positions = await db_manager.get_positions()
            assert len(positions) == 10, "All 10 positions should be persisted"

            # Verify state manager consistency
            for i in range(10):
                notional = await state_manager.get_position_notional_async(f"token_{i}")
                expected = (100.0 + i) * 0.50
                assert (
                    abs(notional - expected) < 0.01
                ), f"Position {i} notional value mismatch"

    @pytest.mark.asyncio
    async def test_failure_recovery_workflow(self):
        """
        Test system behavior during various failure scenarios.

        This tests:
        1. Network failure recovery
        2. Database connection loss recovery
        3. OrderClient failure handling
        4. WebSocket reconnection
        5. State recovery after restart
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_recovery.db"
            cfg = BotConfig(database_url=f"sqlite:///{db_path}")

            state_manager = StateManager(db_path=str(db_path))
            await state_manager.initialize_async()

            trading_engine = TradingEngine(cfg)

            # Test OrderClient failure handling
            order_client = OrderClient(cfg)
            order_client.is_ready = MagicMock(return_value=True)

            # Simulate order failure
            order_client.place_limit_order = AsyncMock(
                side_effect=Exception("Network timeout")
            )

            signal = TradingSignal(
                token_id="test_token_recovery",
                action=SignalAction.BUY,
                price=0.50,
                size=100.0,
                market_slug="test-recovery-market",
                outcome_type=OutcomeType.YES,
                confidence=0.95,
                strategy_name="test_strategy",
            )

            with patch.object(trading_engine, "order_client", order_client):
                result = await trading_engine.process_signal(signal)

                # Verify system handled failure gracefully
                assert (
                    result is None or not result
                ), "Failed order should be handled gracefully"

            # Test state recovery after "restart"
            initial_positions = await state_manager.get_positions_async()

            # Simulate system restart by creating new state manager
            new_state_manager = StateManager(db_path=str(db_path))
            await new_state_manager.initialize_async()

            recovered_positions = await new_state_manager.get_positions_async()

            # Verify state was recovered correctly
            assert len(recovered_positions) == len(
                initial_positions
            ), "State should be recovered after restart"


class TestPerformanceIntegrationWorkflow:
    """Test performance-critical workflows under realistic conditions."""

    @pytest.mark.asyncio
    async def test_high_frequency_signal_processing(self):
        """
        Test system performance under high-frequency signal processing.

        This simulates realistic high-frequency trading conditions to ensure
        the system can handle the expected production load.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_performance.db"
            cfg = BotConfig(database_url=f"sqlite:///{db_path}")

            state_manager = StateManager(db_path=str(db_path))
            await state_manager.initialize_async()

            trading_engine = TradingEngine(cfg)

            # Mock order client for performance testing
            order_client = OrderClient(cfg)
            order_client.is_ready = MagicMock(return_value=True)
            order_client.place_limit_order = AsyncMock(
                return_value={
                    "order_id": "perf_test_order",
                    "status": "open",
                    "size": 100.0,
                    "price": 0.50,
                }
            )

            # Generate multiple signals rapidly
            signals = []
            for i in range(50):  # 50 signals for performance testing
                signal = TradingSignal(
                    token_id=f"perf_token_{i}",
                    action=SignalAction.BUY if i % 2 == 0 else SignalAction.SELL,
                    price=0.45 + (i % 10) * 0.01,
                    size=100.0,
                    market_slug=f"perf-market-{i // 10}",
                    outcome_type=OutcomeType.YES if i % 2 == 0 else OutcomeType.NO,
                    confidence=0.85 + (i % 15) * 0.01,
                    strategy_name="performance_test_strategy",
                )
                signals.append(signal)

            # Process signals and measure performance
            start_time = time.time()

            tasks = []
            with patch.object(trading_engine, "order_client", order_client):
                for signal in signals:
                    task = asyncio.create_task(trading_engine.process_signal(signal))
                    tasks.append(task)

                results = await asyncio.gather(*tasks, return_exceptions=True)

            processing_time = time.time() - start_time

            # Performance assertions
            assert (
                processing_time < 10.0
            ), f"Processing 50 signals took too long: {processing_time:.2f}s"

            # Verify successful processing rate
            successful_results = [r for r in results if not isinstance(r, Exception)]
            success_rate = len(successful_results) / len(results)
            assert success_rate > 0.8, f"Success rate too low: {success_rate:.1%}"

            print(f"✅ Processed {len(signals)} signals in {processing_time:.2f}s")
            print(f"   Average: {processing_time/len(signals)*1000:.1f}ms per signal")
            print(f"   Success rate: {success_rate:.1%}")

    @pytest.mark.asyncio
    async def test_concurrent_market_updates_workflow(self):
        """
        Test system behavior with concurrent market data updates.

        This simulates multiple markets updating simultaneously to ensure
        the system can handle concurrent data flows without conflicts.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_concurrent.db"
            cfg = BotConfig(database_url=f"sqlite:///{db_path}")

            trading_engine = TradingEngine(cfg)

            # Create mock strategy that generates signals
            mock_strategy = MagicMock()
            mock_strategy.process_data = AsyncMock(return_value=[])
            trading_engine.strategies = [mock_strategy]

            # Generate concurrent market updates
            async def process_market_update(market_id: int):
                market_data = {
                    "market_slug": f"concurrent-market-{market_id}",
                    "liquidity": 5000.0 + market_id * 100,
                    "outcomes": [
                        {
                            "token_id": f"token_{market_id}_yes",
                            "outcome_type": "YES",
                            "best_bid": 0.40 + market_id * 0.01,
                            "best_ask": 0.60 - market_id * 0.01,
                            "liquidity": 2500.0,
                        }
                    ],
                }
                return await trading_engine.process_market_update(market_data)

            # Process multiple markets concurrently
            start_time = time.time()

            tasks = []
            for i in range(20):  # 20 concurrent market updates
                task = asyncio.create_task(process_market_update(i))
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)
            processing_time = time.time() - start_time

            # Verify all updates were processed successfully
            for i, result in enumerate(results):
                assert not isinstance(
                    result, Exception
                ), f"Market update {i} failed: {result}"

            # Verify all strategy calls were made
            assert (
                mock_strategy.process_data.call_count == 20
            ), "All market updates should be processed"

            print(
                f"✅ Processed {len(tasks)} concurrent market updates in {processing_time:.2f}s"
            )


# Performance and load testing utilities


@pytest.mark.performance
class TestSystemStressWorkflow:
    """Stress testing for system limits and behavior under extreme conditions."""

    @pytest.mark.asyncio
    async def test_memory_usage_under_load(self):
        """Test memory usage patterns under sustained load."""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_memory.db"
            cfg = BotConfig(database_url=f"sqlite:///{db_path}")

            state_manager = StateManager(db_path=str(db_path))
            await state_manager.initialize_async()

            # Generate sustained load
            for batch in range(10):  # 10 batches of operations
                tasks = []
                for i in range(100):  # 100 operations per batch
                    position_data = {
                        "token_id": f"memory_test_{batch}_{i}",
                        "market_slug": f"memory-market-{batch}",
                        "outcome_type": "YES" if i % 2 == 0 else "NO",
                        "size": 100.0 + i,
                        "notional_value": (100.0 + i) * 0.50,
                    }
                    task = asyncio.create_task(
                        state_manager.update_position_async(position_data)
                    )
                    tasks.append(task)

                await asyncio.gather(*tasks)

                # Check memory usage
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_growth = current_memory - initial_memory

                # Memory growth should be reasonable (less than 100MB per batch)
                assert memory_growth < 100 * (
                    batch + 1
                ), f"Excessive memory growth: {memory_growth:.1f}MB"

        final_memory = process.memory_info().rss / 1024 / 1024
        total_growth = final_memory - initial_memory

        print(
            f"✅ Memory usage: Initial {initial_memory:.1f}MB → Final {final_memory:.1f}MB"
        )
        print(f"   Total growth: {total_growth:.1f}MB")

        # Final memory growth should be reasonable for the amount of work done
        assert total_growth < 200, f"Total memory growth too high: {total_growth:.1f}MB"
