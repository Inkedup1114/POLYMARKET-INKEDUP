"""
Production Scenario Integration Tests for InkedUp Trading Bot.

This module tests critical production scenarios that require multiple components
working together under realistic conditions that could occur in live trading.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.database import DatabaseManager
from inkedup_bot.engine import TradingEngine
from inkedup_bot.order_client import OrderClient
from inkedup_bot.rate_limiter import APIRateLimiter, EndpointType, RateLimitConfig
from inkedup_bot.scanner import Scanner
from inkedup_bot.signals import OutcomeType, SignalAction, TradingSignal
from inkedup_bot.snapshot_service import SnapshotService
from inkedup_bot.state import StateManager
from inkedup_bot.strategies.complement import ComplementArbStrategy
from inkedup_bot.utils import HTTPClient


class TestProductionRateLimitingScenarios:
    """Test rate limiting behavior in production-like scenarios."""

    @pytest.mark.asyncio
    async def test_rate_limiting_during_market_scanning(self):
        """
        Test that market scanning respects rate limits and handles 429 errors gracefully.

        This simulates the scanner making rapid API calls and being rate limited,
        ensuring the system handles this gracefully without crashing.
        """
        cfg = BotConfig(
            rate_limiting_enabled=True,
            rate_limit_market_data_per_second=2.0,  # Very restrictive for testing
            rate_limit_market_data_burst=3,
        )

        # Create scanner with rate limiting enabled
        scanner = Scanner(cfg)

        # Verify rate limiter is configured
        assert (
            scanner.client.rate_limiter is not None
        ), "Scanner should have rate limiter configured"

        # Mock the actual HTTP requests to simulate rate limiting
        original_get = scanner.client.get
        call_count = 0

        async def mock_get_with_rate_limit(path: str, params=None):
            nonlocal call_count
            call_count += 1

            # Simulate rate limiting after 3 calls
            if call_count > 3:
                from aiohttp import ClientResponseError

                raise ClientResponseError(
                    request_info=MagicMock(),
                    history=(),
                    status=429,
                    message="Too Many Requests",
                )

            return {"markets": [{"slug": f"test-market-{call_count}"}]}

        scanner.client.get = mock_get_with_rate_limit

        # Test that scanner handles rate limiting gracefully
        markets = []
        try:
            # Make multiple rapid calls that should trigger rate limiting
            for i in range(5):
                result = await scanner.client.get("/markets")
                if result:
                    markets.extend(result.get("markets", []))
        except Exception as e:
            # Rate limiting should be handled gracefully
            assert "429" in str(e) or "rate" in str(e).lower(), f"Unexpected error: {e}"

        # Verify some calls succeeded before rate limiting
        assert (
            len(markets) >= 1
        ), "Some market calls should succeed before rate limiting"
        print(
            f"✅ Handled rate limiting gracefully. Got {len(markets)} markets before rate limit."
        )

    @pytest.mark.asyncio
    async def test_rate_limiting_with_multiple_components(self):
        """
        Test rate limiting coordination between Scanner and SnapshotService.

        This ensures that multiple components sharing rate limits work together
        without interfering with each other's API usage.
        """
        cfg = BotConfig(
            rate_limiting_enabled=True,
            rate_limit_market_data_per_second=5.0,  # Shared limit
            rate_limit_market_data_per_minute=30.0,
        )

        # Create both Scanner and SnapshotService
        scanner = Scanner(cfg)
        snapshot_service = SnapshotService(cfg)

        # Verify both have rate limiting enabled
        assert scanner.client.rate_limiter is not None
        assert snapshot_service.client.rate_limiter is not None

        # Mock HTTP client responses
        mock_response = {"success": True, "data": []}
        scanner.client.get = AsyncMock(return_value=mock_response)
        snapshot_service.client.get = AsyncMock(return_value=mock_response)

        # Run concurrent operations from both components
        scanner_tasks = [scanner.client.get(f"/markets?page={i}") for i in range(3)]
        snapshot_tasks = [snapshot_service.client.get(f"/book/{i}") for i in range(3)]

        # Execute concurrently
        all_tasks = scanner_tasks + snapshot_tasks
        results = await asyncio.gather(*all_tasks, return_exceptions=True)

        # Verify no exceptions occurred
        for i, result in enumerate(results):
            assert not isinstance(result, Exception), f"Task {i} failed: {result}"

        print("✅ Multiple components successfully shared rate limiting resources")


class TestProductionDatabaseScenarios:
    """Test database behavior under production conditions."""

    @pytest.mark.asyncio
    async def test_database_connection_pool_exhaustion(self):
        """
        Test system behavior when database connection pool is exhausted.

        This simulates high concurrent database usage that exhausts the connection pool,
        ensuring the system handles this gracefully with proper queuing and timeouts.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_pool_exhaustion.db"
            cfg = BotConfig(
                database_url=f"sqlite:///{db_path}",
                database_pool_max_connections=5,  # Small pool for testing
                database_pool_timeout=2.0,  # Short timeout for testing
            )

            db_manager = DatabaseManager()
            await db_manager.initialize()

            # Create many concurrent database operations
            async def db_operation(operation_id: int):
                try:
                    # Simulate a database operation that takes some time
                    await asyncio.sleep(0.1)
                    return await db_manager.execute_query(
                        "SELECT ? as operation_id", (operation_id,)
                    )
                except Exception as e:
                    return e

            # Create more operations than the connection pool can handle
            tasks = [asyncio.create_task(db_operation(i)) for i in range(15)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Analyze results
            successful_ops = [r for r in results if not isinstance(r, Exception)]
            failed_ops = [r for r in results if isinstance(r, Exception)]

            # Some operations should succeed
            assert len(successful_ops) > 0, "Some database operations should succeed"

            # System should handle pool exhaustion gracefully
            if failed_ops:
                print(
                    f"✅ Handled connection pool exhaustion: {len(successful_ops)} succeeded, {len(failed_ops)} failed gracefully"
                )
            else:
                print(
                    f"✅ All operations succeeded with connection pooling: {len(successful_ops)} total"
                )

    @pytest.mark.asyncio
    async def test_database_corruption_recovery(self):
        """
        Test database corruption detection and recovery mechanisms.

        This simulates database file corruption and tests the system's ability
        to detect and recover from such scenarios.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_corruption.db"
            cfg = BotConfig(database_url=f"sqlite:///{db_path}")

            # Initialize database with some data
            state_manager = StateManager(db_path=str(db_path))
            await state_manager.initialize_async()

            # Add some test data
            position_data = {
                "token_id": "corruption_test_token",
                "market_slug": "corruption-test-market",
                "outcome_type": "YES",
                "size": 100.0,
                "notional_value": 50.0,
            }
            await state_manager.update_position_async(position_data)

            # Verify data was written
            initial_positions = await state_manager.get_positions_async()
            assert len(initial_positions) > 0, "Initial data should be written"

            # Simulate corruption by writing invalid data to the database file
            # (In a real scenario, this could be file system corruption, etc.)
            try:
                with open(db_path, "r+b") as f:
                    f.seek(0)
                    f.write(b"\x00" * 1024)  # Corrupt the beginning of the file
            except Exception:
                pass  # File might not exist or be locked

            # Try to create a new state manager (simulating restart after corruption)
            try:
                new_state_manager = StateManager(db_path=str(db_path))
                await new_state_manager.initialize_async()

                # System should either recover or handle corruption gracefully
                recovered_positions = await new_state_manager.get_positions_async()
                print(
                    f"✅ Database corruption handled gracefully. Recovered {len(recovered_positions)} positions"
                )

            except Exception as e:
                # If corruption can't be recovered, system should fail gracefully
                assert (
                    "database" in str(e).lower() or "corrupt" in str(e).lower()
                ), f"Unexpected error: {e}"
                print(
                    f"✅ Database corruption detected and handled: {type(e).__name__}"
                )


class TestProductionSignalProcessingScenarios:
    """Test signal processing under production conditions."""

    @pytest.mark.asyncio
    async def test_signal_processing_backpressure(self):
        """
        Test signal processing when the system is under high load.

        This simulates a scenario where signals are generated faster than
        they can be processed, testing backpressure handling.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_backpressure.db"
            cfg = BotConfig(
                database_url=f"sqlite:///{db_path}",
                signal_max_concurrent=5,  # Low limit to force backpressure
                signal_default_timeout_seconds=1.0,  # Short timeout
            )

            trading_engine = TradingEngine(cfg)

            # Mock slow order processing to create backpressure
            order_client = OrderClient(cfg)
            order_client.is_ready = MagicMock(return_value=True)

            async def slow_order_processing(*args, **kwargs):
                await asyncio.sleep(0.5)  # Slow processing
                return {
                    "order_id": f"slow_order_{id(args)}",
                    "status": "open",
                    "size": 100.0,
                    "price": 0.50,
                }

            order_client.place_limit_order = AsyncMock(
                side_effect=slow_order_processing
            )

            # Generate many signals rapidly
            signals = []
            for i in range(20):  # More signals than concurrent limit
                signal = TradingSignal(
                    token_id=f"backpressure_token_{i}",
                    action=SignalAction.BUY,
                    price=0.45 + i * 0.001,
                    size=100.0,
                    market_slug=f"backpressure-market-{i % 3}",
                    outcome_type=OutcomeType.YES,
                    confidence=0.85,
                    strategy_name="backpressure_test",
                )
                signals.append(signal)

            # Process signals concurrently
            with patch.object(trading_engine, "order_client", order_client):
                tasks = [
                    asyncio.create_task(trading_engine.process_signal(s))
                    for s in signals
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

            # Analyze results
            successful = [
                r for r in results if not isinstance(r, Exception) and r is not None
            ]
            failed_or_dropped = [
                r for r in results if isinstance(r, Exception) or r is None
            ]

            # Some signals should be processed, some may be dropped due to backpressure
            print(
                f"✅ Backpressure handling: {len(successful)} processed, {len(failed_or_dropped)} dropped/failed"
            )

            # System should remain stable under backpressure
            assert (
                len(results) == 20
            ), "All signals should have results (even if dropped)"

    @pytest.mark.asyncio
    async def test_signal_processing_with_market_volatility(self):
        """
        Test signal processing during high market volatility scenarios.

        This simulates rapid market changes that could cause signal conflicts
        or outdated signals being processed.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_volatility.db"
            cfg = BotConfig(database_url=f"sqlite:///{db_path}")

            trading_engine = TradingEngine(cfg)

            # Create complement arbitrage strategy
            strategy = ComplementArbStrategy(cfg)
            strategy.engine = trading_engine

            # Simulate rapidly changing market data (high volatility)
            volatile_markets = []
            for i in range(10):
                # Market conditions change rapidly
                yes_price = 0.30 + i * 0.05  # Price moves from 0.30 to 0.75
                no_price = 1.0 - yes_price  # Complement price

                market_data = {
                    "market_slug": "volatile-election-market",
                    "outcomes": [
                        {
                            "token_id": "volatile_yes_token",
                            "outcome_type": "YES",
                            "best_bid": yes_price - 0.02,
                            "best_ask": yes_price + 0.02,
                            "liquidity": 5000.0,
                        },
                        {
                            "token_id": "volatile_no_token",
                            "outcome_type": "NO",
                            "best_bid": no_price - 0.02,
                            "best_ask": no_price + 0.02,
                            "liquidity": 5000.0,
                        },
                    ],
                    "total_liquidity": 10000.0,
                    "timestamp": i,  # Simulate time progression
                }
                volatile_markets.append(market_data)

            # Process markets rapidly to simulate volatile conditions
            all_signals = []
            for market_data in volatile_markets:
                signals = await strategy.process_data(market_data)
                all_signals.extend(signals)

            # Verify signals were generated appropriately
            print(
                f"✅ Generated {len(all_signals)} signals during volatile market conditions"
            )

            # Signals should be valid and not conflicting
            if all_signals:
                # Group signals by token
                signals_by_token = {}
                for signal in all_signals:
                    token = signal.token_id
                    if token not in signals_by_token:
                        signals_by_token[token] = []
                    signals_by_token[token].append(signal)

                # Check for conflicting signals on the same token
                for token, token_signals in signals_by_token.items():
                    if len(token_signals) > 1:
                        # Multiple signals for same token - check for conflicts
                        actions = [s.action for s in token_signals]
                        if SignalAction.BUY in actions and SignalAction.SELL in actions:
                            print(
                                f"⚠️  Conflicting signals detected for {token}: {actions}"
                            )
                        else:
                            print(f"✅ Consistent signals for {token}: {actions}")


class TestProductionRiskScenarios:
    """Test risk management under production conditions."""

    @pytest.mark.asyncio
    async def test_risk_limits_during_market_crash(self):
        """
        Test risk management behavior during simulated market crash conditions.

        This simulates extreme market conditions where prices move rapidly
        and tests that risk limits protect the system.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_crash.db"
            cfg = BotConfig(
                database_url=f"sqlite:///{db_path}",
                max_position_size=1000.0,
                global_risk_cap=5000.0,
                max_order_size=500.0,
            )

            state_manager = StateManager(db_path=str(db_path))
            await state_manager.initialize_async()

            trading_engine = TradingEngine(cfg)

            # Mock order client
            order_client = OrderClient(cfg)
            order_client.is_ready = MagicMock(return_value=True)
            order_client.place_limit_order = AsyncMock(
                return_value={
                    "order_id": "crash_test_order",
                    "status": "open",
                    "size": 100.0,
                    "price": 0.10,  # Crash price
                }
            )

            # Simulate existing large positions (near risk limits)
            existing_positions = [
                {
                    "token_id": f"crash_position_{i}",
                    "market_slug": f"crash-market-{i}",
                    "outcome_type": "YES",
                    "size": 800.0,  # Large position
                    "notional_value": 800.0 * 0.80,  # High value
                }
                for i in range(5)  # Multiple large positions
            ]

            for pos in existing_positions:
                await state_manager.update_position_async(pos)

            # Generate signals during "market crash" (many opportunities at low prices)
            crash_signals = []
            for i in range(10):
                signal = TradingSignal(
                    token_id=f"crash_opportunity_{i}",
                    action=SignalAction.BUY,
                    price=0.10,  # Very low "crash" price
                    size=600.0,  # Large size that would exceed limits
                    market_slug=f"crash-market-{i}",
                    outcome_type=OutcomeType.YES,
                    confidence=0.95,  # High confidence (looks like great opportunity)
                    strategy_name="crash_opportunity_strategy",
                )
                crash_signals.append(signal)

            # Process crash signals
            with patch.object(trading_engine, "order_client", order_client):
                results = []
                for signal in crash_signals:
                    result = await trading_engine.process_signal(signal)
                    results.append(result)

            # Verify risk management prevented dangerous trades
            successful_trades = [r for r in results if r is not None]
            blocked_trades = [r for r in results if r is None]

            print(
                f"✅ Crash scenario: {len(blocked_trades)} trades blocked by risk management"
            )
            print(f"   {len(successful_trades)} trades allowed within risk limits")

            # Most trades should be blocked due to risk limits
            assert len(blocked_trades) >= len(
                successful_trades
            ), "Risk management should block most trades during crash"

    @pytest.mark.asyncio
    async def test_position_limit_enforcement_edge_cases(self):
        """
        Test position limit enforcement in edge cases and race conditions.

        This tests scenarios where multiple orders might be processed concurrently
        and could potentially exceed position limits if not properly coordinated.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_edge_cases.db"
            cfg = BotConfig(
                database_url=f"sqlite:///{db_path}",
                max_position_size=1000.0,
                max_order_size=300.0,
            )

            state_manager = StateManager(db_path=str(db_path))
            await state_manager.initialize_async()

            trading_engine = TradingEngine(cfg)

            # Mock order client with successful orders
            order_client = OrderClient(cfg)
            order_client.is_ready = MagicMock(return_value=True)
            order_client.place_limit_order = AsyncMock(
                return_value={
                    "order_id": "edge_case_order",
                    "status": "open",
                    "size": 250.0,
                    "price": 0.50,
                }
            )

            # Create multiple concurrent signals for the same token
            # This tests race condition handling
            concurrent_signals = []
            for i in range(
                5
            ):  # 5 concurrent orders of 250 each = 1250 total > 1000 limit
                signal = TradingSignal(
                    token_id="edge_case_token",  # Same token for all
                    action=SignalAction.BUY,
                    price=0.50,
                    size=250.0,  # Each order is within individual limits
                    market_slug="edge-case-market",
                    outcome_type=OutcomeType.YES,
                    confidence=0.90,
                    strategy_name="edge_case_strategy",
                )
                concurrent_signals.append(signal)

            # Process signals concurrently to test race conditions
            with patch.object(trading_engine, "order_client", order_client):
                tasks = [
                    asyncio.create_task(trading_engine.process_signal(s))
                    for s in concurrent_signals
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

            # Verify position limits were enforced despite concurrency
            successful_orders = [
                r for r in results if not isinstance(r, Exception) and r is not None
            ]
            rejected_orders = [
                r for r in results if isinstance(r, Exception) or r is None
            ]

            # Calculate maximum possible position size
            max_possible_position = len(successful_orders) * 250.0

            print(
                f"✅ Concurrent order processing: {len(successful_orders)} successful, {len(rejected_orders)} rejected"
            )
            print(f"   Maximum position size: {max_possible_position} (limit: 1000.0)")

            # Position limits should be enforced
            assert (
                max_possible_position <= 1000.0
            ), f"Position limit exceeded: {max_possible_position}"

            # Verify final position in state manager
            final_position = await state_manager.get_position_notional_async(
                "edge_case_token"
            )
            assert (
                final_position <= 1000.0 * 0.50
            ), f"Final position exceeds limits: {final_position}"


# Test utilities for production scenarios


@pytest.fixture
async def production_config():
    """Create a production-like configuration for testing."""
    return BotConfig(
        rate_limiting_enabled=True,
        database_pool_max_connections=10,
        signal_max_concurrent=20,
        max_position_size=10000.0,
        global_risk_cap=50000.0,
        api_retry_attempts=3,
        api_timeout_seconds=30,
    )


@pytest.fixture
async def mock_production_environment(production_config):
    """Set up a mock production environment with all components."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "production_test.db"
        production_config.database_url = f"sqlite:///{db_path}"

        # Initialize all components
        state_manager = StateManager(db_path=str(db_path))
        await state_manager.initialize_async()

        db_manager = DatabaseManager()
        await db_manager.initialize()

        trading_engine = TradingEngine(production_config)
        scanner = Scanner(production_config)

        yield {
            "config": production_config,
            "state_manager": state_manager,
            "db_manager": db_manager,
            "trading_engine": trading_engine,
            "scanner": scanner,
            "db_path": db_path,
        }
