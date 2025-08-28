"""
Test suite for risk management fallback mechanisms.

Tests the risk system's ability to gracefully degrade when database is unavailable
and switch between different operating modes (NORMAL, DEGRADED, EMERGENCY_HALT).
"""

import os
import tempfile
import time
from unittest.mock import Mock, patch

import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.order_client import OrderClient
from inkedup_bot.risk.manager import DatabaseFallbackCache, RiskManager, RiskSystemMode
from inkedup_bot.state import StateManager


class TestDatabaseFallbackCache:
    """Test the in-memory fallback cache functionality."""

    def test_cache_initialization(self):
        """Test cache initializes with empty state."""
        cache = DatabaseFallbackCache()

        assert cache.total_exposure == 0.0
        assert len(cache.positions) == 0
        assert len(cache.market_exposures) == 0
        assert len(cache.outcome_exposures) == 0
        assert cache.cache_hits == 0
        assert cache.cache_misses == 0

    def test_position_update(self):
        """Test position updates in cache."""
        cache = DatabaseFallbackCache()

        position_data = {
            "token_id": "test_token",
            "notional_value": 100.0,
            "market_slug": "test_market",
            "outcome_type": "yes",
        }

        cache.update_position("test_token", position_data)

        assert cache.total_exposure == 100.0
        assert cache.get_position_notional("test_token") == 100.0
        assert cache.get_market_exposure("test_market") == 100.0
        assert cache.get_outcome_exposure("yes") == 100.0

    def test_position_update_modification(self):
        """Test modifying existing position in cache."""
        cache = DatabaseFallbackCache()

        # Initial position
        position_data = {
            "token_id": "test_token",
            "notional_value": 100.0,
            "market_slug": "test_market",
            "outcome_type": "yes",
        }
        cache.update_position("test_token", position_data)

        # Update position
        updated_position = {
            "token_id": "test_token",
            "notional_value": 150.0,
            "market_slug": "test_market",
            "outcome_type": "yes",
        }
        cache.update_position("test_token", updated_position)

        assert cache.total_exposure == 150.0
        assert cache.get_position_notional("test_token") == 150.0
        assert cache.get_market_exposure("test_market") == 150.0
        assert cache.get_outcome_exposure("yes") == 150.0

    def test_cache_stats(self):
        """Test cache statistics tracking."""
        cache = DatabaseFallbackCache()

        # Add some data
        cache.update_position("token1", {"notional_value": 100.0})
        cache.update_position(
            "token2", {"notional_value": 200.0, "market_slug": "market1"}
        )

        # Perform some reads
        cache.get_total_exposure()
        cache.get_position_notional("token1")

        stats = cache.get_cache_stats()

        assert stats["positions_count"] == 2
        assert stats["total_exposure"] == 300.0
        assert stats["cache_hits"] == 2
        assert "age_seconds" in stats
        assert "last_updated" in stats


class TestRiskManagerFallback:
    """Test risk manager fallback mechanisms."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock bot configuration."""
        config = Mock(spec=BotConfig)
        # Set up proper attributes instead of mock objects
        config.global_risk_cap = 10000.0
        config.position_risk_cap = 1000.0
        config.market_risk_cap = 2000.0
        config.per_market_risk_cap = 2000.0
        config.per_outcome_risk_cap = 1500.0
        config.max_position_size = 500.0
        config.max_order_size = 100.0
        config.slippage_tolerance_bps = 50
        config.order_timeout_seconds = 30
        config.price_precision = 4
        config.size_precision = 4
        config.default_order_type = "GTC"
        config.complement_arb_min_deviation = 0.01
        config.complement_arb_max_deviation = 0.20
        config.complement_arb_base_size = 10.0
        config.complement_arb_max_size = 100.0
        config.complement_arb_size_scaling = 50.0
        config.risk_validation_enabled = True
        config.risk_strict_mode = False
        return config

    @pytest.fixture
    def mock_order_client(self):
        """Create a mock order client."""
        client = Mock(spec=OrderClient)
        client.ready.return_value = True
        return client

    @pytest.fixture
    def temp_state_manager(self):
        """Create a temporary state manager with in-memory database."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            db_path = tmp.name

        try:
            state = StateManager(db_path)
            yield state
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_risk_manager_initialization(
        self, mock_config, mock_order_client, temp_state_manager
    ):
        """Test risk manager initializes correctly."""
        risk_manager = RiskManager(mock_config, mock_order_client, temp_state_manager)

        assert risk_manager.mode == RiskSystemMode.NORMAL
        assert risk_manager.database_failure_count == 0
        assert isinstance(risk_manager.fallback_cache, DatabaseFallbackCache)

    def test_database_failure_handling(
        self, mock_config, mock_order_client, temp_state_manager
    ):
        """Test database failure detection and mode switching."""
        risk_manager = RiskManager(mock_config, mock_order_client, temp_state_manager)

        # Simulate database failure
        with patch.object(
            temp_state_manager,
            "get_total_exposure",
            side_effect=Exception("Database error"),
        ):
            # This should trigger fallback
            result = risk_manager._get_exposure_data_with_fallback(
                "get_total_exposure", temp_state_manager.get_total_exposure
            )

            # Should return fallback data (0.0 for empty cache)
            assert result == 0.0
            assert risk_manager.database_failure_count > 0

    def test_degraded_mode_switch(
        self, mock_config, mock_order_client, temp_state_manager
    ):
        """Test switching to degraded mode after failures."""
        risk_manager = RiskManager(mock_config, mock_order_client, temp_state_manager)

        # Force multiple failures to trigger degraded mode
        for _ in range(risk_manager.max_failure_threshold):
            risk_manager._handle_database_failure("test", Exception("Test error"))

        assert risk_manager.mode == RiskSystemMode.DEGRADED

    def test_emergency_halt_mode_switch(
        self, mock_config, mock_order_client, temp_state_manager
    ):
        """Test switching to emergency halt mode after many failures."""
        risk_manager = RiskManager(mock_config, mock_order_client, temp_state_manager)

        # Force many failures to trigger emergency halt
        for _ in range(risk_manager.emergency_halt_threshold):
            risk_manager._handle_database_failure("test", Exception("Test error"))

        assert risk_manager.mode == RiskSystemMode.EMERGENCY_HALT

    def test_emergency_halt_blocks_trading(
        self, mock_config, mock_order_client, temp_state_manager
    ):
        """Test that emergency halt mode blocks all trading operations."""
        risk_manager = RiskManager(mock_config, mock_order_client, temp_state_manager)

        # Force emergency halt
        risk_manager.set_emergency_halt("Test emergency halt")

        # Preflight check should fail
        with pytest.raises(RuntimeError, match="emergency halt mode"):
            risk_manager.preflight("test_token", 100.0)

    def test_fallback_cache_integration(
        self, mock_config, mock_order_client, temp_state_manager
    ):
        """Test that fallback cache is used during database issues."""
        risk_manager = RiskManager(mock_config, mock_order_client, temp_state_manager)

        # Set up fallback cache with test data
        risk_manager.fallback_cache.update_position(
            "test_token",
            {
                "token_id": "test_token",
                "notional_value": 100.0,
                "market_slug": "test_market",
                "outcome_type": "yes",
            },
        )

        # Switch to degraded mode
        risk_manager.mode = RiskSystemMode.DEGRADED

        # Mock database failure
        with patch.object(
            temp_state_manager,
            "get_total_exposure",
            side_effect=Exception("Database error"),
        ):
            # Should use fallback cache data
            result = risk_manager._get_exposure_data_with_fallback(
                "get_total_exposure", temp_state_manager.get_total_exposure
            )
            assert result == 100.0

    def test_preflight_with_fallback_data(
        self, mock_config, mock_order_client, temp_state_manager
    ):
        """Test preflight checks work with fallback data."""
        risk_manager = RiskManager(mock_config, mock_order_client, temp_state_manager)

        # Set up fallback cache
        risk_manager.fallback_cache.update_position(
            "existing_token",
            {
                "token_id": "existing_token",
                "notional_value": 500.0,
                "market_slug": "test_market",
                "outcome_type": "yes",
            },
        )

        # Switch to degraded mode
        risk_manager.mode = RiskSystemMode.DEGRADED

        # Mock database calls to force fallback usage
        with patch.object(
            temp_state_manager, "get_total_exposure", side_effect=Exception("DB error")
        ):
            with patch.object(
                temp_state_manager,
                "get_position_notional",
                side_effect=Exception("DB error"),
            ):
                # This should work using fallback data
                result = risk_manager.preflight("new_token", 100.0)
                assert result is True

    def test_risk_system_status(
        self, mock_config, mock_order_client, temp_state_manager
    ):
        """Test risk system status reporting."""
        risk_manager = RiskManager(mock_config, mock_order_client, temp_state_manager)

        status = risk_manager.get_risk_system_status()

        assert "mode" in status
        assert "database_failure_count" in status
        assert "trading_enabled" in status
        assert "fallback_cache" in status
        assert "thresholds" in status
        assert "risk_config_summary" in status

        assert status["mode"] == "normal"

    def test_manual_emergency_halt_and_clear(
        self, mock_config, mock_order_client, temp_state_manager
    ):
        """Test manual emergency halt and clearing."""
        risk_manager = RiskManager(mock_config, mock_order_client, temp_state_manager)

        # Manually trigger emergency halt
        risk_manager.set_emergency_halt("Manual test")
        assert risk_manager.mode == RiskSystemMode.EMERGENCY_HALT

        # Clear emergency halt (should work if database is healthy)
        with patch.object(risk_manager, "_check_database_health", return_value=True):
            result = risk_manager.clear_emergency_halt()
            assert result is True
            assert risk_manager.mode == RiskSystemMode.NORMAL

    def test_database_recovery(
        self, mock_config, mock_order_client, temp_state_manager
    ):
        """Test database recovery mechanism."""
        risk_manager = RiskManager(mock_config, mock_order_client, temp_state_manager)

        # Force degraded mode
        risk_manager.mode = RiskSystemMode.DEGRADED
        risk_manager.database_failure_count = 5

        # Simulate database recovery
        with patch.object(risk_manager, "_check_database_health", return_value=True):
            recovery_success = risk_manager._try_database_recovery()

            assert recovery_success is True
            assert risk_manager.mode == RiskSystemMode.NORMAL
            assert risk_manager.database_failure_count == 0

    def test_state_manager_risk_manager_integration(
        self, mock_config, mock_order_client, temp_state_manager
    ):
        """Test integration between state manager and risk manager."""
        risk_manager = RiskManager(mock_config, mock_order_client, temp_state_manager)
        temp_state_manager.set_risk_manager(risk_manager)

        # Update position in state manager
        position_data = {
            "token_id": "test_token",
            "notional_value": 200.0,
            "market_slug": "test_market",
            "outcome_type": "yes",
        }

        temp_state_manager.update_position(position_data)

        # Risk manager's fallback cache should be updated
        assert risk_manager.fallback_cache.get_position_notional("test_token") == 200.0


class TestRiskManagerModeTransitions:
    """Test mode transitions and edge cases."""

    @pytest.fixture
    def risk_manager_setup(self):
        """Set up risk manager for mode transition tests."""
        config = Mock(spec=BotConfig)
        # Set up proper attributes instead of mock objects
        config.global_risk_cap = 10000.0
        config.position_risk_cap = 1000.0
        config.market_risk_cap = 2000.0
        config.per_market_risk_cap = 2000.0
        config.per_outcome_risk_cap = 1500.0
        config.max_position_size = 500.0
        config.max_order_size = 100.0
        config.slippage_tolerance_bps = 50
        config.order_timeout_seconds = 30
        config.price_precision = 4
        config.size_precision = 4
        config.default_order_type = "GTC"
        config.complement_arb_min_deviation = 0.01
        config.complement_arb_max_deviation = 0.20
        config.complement_arb_base_size = 10.0
        config.complement_arb_max_size = 100.0
        config.complement_arb_size_scaling = 50.0
        config.risk_validation_enabled = True
        config.risk_strict_mode = False

        order_client = Mock(spec=OrderClient)
        order_client.ready.return_value = True

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            db_path = tmp.name

        state_manager = StateManager(db_path)
        risk_manager = RiskManager(config, order_client, state_manager)

        yield risk_manager

        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_mode_transition_logging(self, risk_manager_setup, caplog):
        """Test that mode transitions are properly logged."""
        risk_manager = risk_manager_setup

        # Trigger degraded mode
        risk_manager._switch_to_degraded_mode("Test reason")

        assert "DEGRADED mode" in caplog.text
        assert "Test reason" in caplog.text

    def test_repeated_mode_switches_dont_spam_logs(self, risk_manager_setup, caplog):
        """Test that repeated mode switches don't spam logs."""
        risk_manager = risk_manager_setup

        # Switch to degraded multiple times
        risk_manager._switch_to_degraded_mode("Test reason 1")
        caplog.clear()

        risk_manager._switch_to_degraded_mode("Test reason 2")

        # Should not log again since already in degraded mode
        assert "DEGRADED mode" not in caplog.text

    def test_failure_count_reset_on_success(self, risk_manager_setup):
        """Test that failure count decreases on successful operations."""
        risk_manager = risk_manager_setup

        # Increase failure count
        risk_manager.database_failure_count = 2

        # Simulate successful operation
        result = risk_manager._get_exposure_data_with_fallback(
            "get_total_exposure", risk_manager.state.get_total_exposure
        )

        # Failure count should decrease
        assert risk_manager.database_failure_count < 2

    def test_force_database_check(self, risk_manager_setup):
        """Test forced database health check."""
        risk_manager = risk_manager_setup

        # Set last check time to recent past
        risk_manager.last_database_check = time.time() - 30

        # Force check should work regardless of interval
        with patch.object(risk_manager, "_check_database_health", return_value=True):
            result = risk_manager.force_database_check()
            assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
