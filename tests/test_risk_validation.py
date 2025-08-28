"""
Tests for risk parameter validation using Pydantic models.
"""

from unittest.mock import Mock

import pytest
from pydantic import ValidationError as PydanticValidationError

from inkedup_bot.config import BotConfig
from inkedup_bot.risk import (
    GlobalRiskConfig,
    MarketConditionConfig,
    OrderExecutionConfig,
    RiskManagementConfig,
    RiskManager,
    StrategyRiskConfig,
)
from inkedup_bot.state import StateManager


class TestGlobalRiskConfig:
    """Test GlobalRiskConfig validation."""

    def test_valid_config(self):
        """Test valid global risk configuration."""
        config = GlobalRiskConfig(
            global_risk_cap=10000.0,
            position_risk_cap=1000.0,
            market_risk_cap=5000.0,
            per_market_risk_cap=2000.0,
            per_outcome_risk_cap=1500.0,
            max_position_size=1000.0,
            max_order_size=100.0,
        )

        assert config.global_risk_cap == 10000.0
        assert config.position_risk_cap == 1000.0
        assert config.max_order_size == 100.0

    def test_negative_values_rejected(self):
        """Test that negative risk caps are rejected."""
        with pytest.raises(PydanticValidationError) as excinfo:
            GlobalRiskConfig(
                global_risk_cap=-1000.0,  # Invalid
                position_risk_cap=1000.0,
                market_risk_cap=5000.0,
                per_market_risk_cap=2000.0,
                per_outcome_risk_cap=1500.0,
                max_position_size=1000.0,
                max_order_size=100.0,
            )

        errors = excinfo.value.errors()
        assert any("global_risk_cap" in str(error) for error in errors)

    def test_zero_values_allowed(self):
        """Test that zero values are allowed (disables the limit)."""
        config = GlobalRiskConfig(
            global_risk_cap=0.0,  # Valid - disables limit
            position_risk_cap=0.0,  # Valid - disables limit
            market_risk_cap=0.0,
            per_market_risk_cap=0.0,
            per_outcome_risk_cap=0.0,
            max_position_size=1000.0,
            max_order_size=100.0,
        )

        assert config.global_risk_cap == 0.0
        assert config.position_risk_cap == 0.0

    def test_hierarchy_validation(self):
        """Test risk cap hierarchy validation."""
        # This should fail: position cap > global cap
        with pytest.raises(PydanticValidationError) as excinfo:
            GlobalRiskConfig(
                global_risk_cap=5000.0,
                position_risk_cap=10000.0,  # Exceeds global cap
                market_risk_cap=0.0,
                per_market_risk_cap=2000.0,
                per_outcome_risk_cap=1500.0,
                max_position_size=1000.0,
                max_order_size=100.0,
            )

        error_msg = str(excinfo.value)
        assert "position_risk_cap cannot exceed global_risk_cap" in error_msg

    def test_order_size_hierarchy(self):
        """Test that order size cannot exceed position size."""
        with pytest.raises(PydanticValidationError) as excinfo:
            GlobalRiskConfig(
                global_risk_cap=10000.0,
                position_risk_cap=1000.0,
                market_risk_cap=5000.0,
                per_market_risk_cap=2000.0,
                per_outcome_risk_cap=1500.0,
                max_position_size=100.0,
                max_order_size=200.0,  # Exceeds position size
            )

        error_msg = str(excinfo.value)
        assert "max_order_size cannot exceed max_position_size" in error_msg


class TestMarketConditionConfig:
    """Test MarketConditionConfig validation."""

    def test_valid_config(self):
        """Test valid market condition configuration."""
        config = MarketConditionConfig(
            volatility_threshold=0.15,
            volatility_adjustment_factor=1.5,
            liquidity_ratio_threshold=0.1,
            correlation_threshold=0.7,
            max_correlated_exposure=0.3,
            market_status_required=True,
        )

        assert config.volatility_threshold == 0.15
        assert config.volatility_adjustment_factor == 1.5
        assert config.market_status_required is True

    def test_threshold_bounds(self):
        """Test threshold value bounds validation."""
        with pytest.raises(PydanticValidationError):
            MarketConditionConfig(volatility_threshold=1.5)  # > 1.0

        with pytest.raises(PydanticValidationError):
            MarketConditionConfig(volatility_threshold=0.0)  # <= 0

        with pytest.raises(PydanticValidationError):
            MarketConditionConfig(correlation_threshold=1.5)  # > 1.0


class TestOrderExecutionConfig:
    """Test OrderExecutionConfig validation."""

    def test_valid_config(self):
        """Test valid order execution configuration."""
        config = OrderExecutionConfig(
            slippage_tolerance_bps=50,
            order_timeout_seconds=30,
            price_precision=4,
            size_precision=4,
            default_order_type="GTC",
        )

        assert config.slippage_tolerance_bps == 50
        assert config.order_timeout_seconds == 30
        assert config.default_order_type == "GTC"

    def test_high_slippage_warning(self):
        """Test that very high slippage values are rejected."""
        with pytest.raises(PydanticValidationError) as excinfo:
            OrderExecutionConfig(slippage_tolerance_bps=1500)  # 15% slippage

        error_msg = str(excinfo.value)
        assert "very high" in error_msg

    def test_invalid_order_type(self):
        """Test that invalid order types are rejected."""
        with pytest.raises(PydanticValidationError):
            OrderExecutionConfig(default_order_type="INVALID")


class TestStrategyRiskConfig:
    """Test StrategyRiskConfig validation."""

    def test_valid_config(self):
        """Test valid strategy risk configuration."""
        config = StrategyRiskConfig(
            complement_arb_min_deviation=0.01,
            complement_arb_max_deviation=0.20,
            complement_arb_base_size=10.0,
            complement_arb_max_size=100.0,
            complement_arb_size_scaling=50.0,
        )

        assert config.complement_arb_min_deviation == 0.01
        assert config.complement_arb_max_deviation == 0.20

    def test_deviation_range_validation(self):
        """Test that min deviation must be less than max deviation."""
        with pytest.raises(PydanticValidationError) as excinfo:
            StrategyRiskConfig(
                complement_arb_min_deviation=0.25,
                complement_arb_max_deviation=0.20,  # Less than min
                complement_arb_base_size=10.0,
                complement_arb_max_size=100.0,
                complement_arb_size_scaling=50.0,
            )

        error_msg = str(excinfo.value)
        assert "min_deviation must be less than" in error_msg

    def test_size_range_validation(self):
        """Test that base size must be <= max size."""
        with pytest.raises(PydanticValidationError) as excinfo:
            StrategyRiskConfig(
                complement_arb_min_deviation=0.01,
                complement_arb_max_deviation=0.20,
                complement_arb_base_size=150.0,  # Greater than max
                complement_arb_max_size=100.0,
                complement_arb_size_scaling=50.0,
            )

        error_msg = str(excinfo.value)
        assert "base_size must be <=" in error_msg


class TestRiskManagementConfig:
    """Test complete RiskManagementConfig."""

    def test_from_bot_config(self):
        """Test creating risk config from bot config."""
        # Create a mock bot config
        bot_config = Mock()
        bot_config.global_risk_cap = 10000.0
        bot_config.position_risk_cap = 1000.0
        bot_config.market_risk_cap = 5000.0
        bot_config.per_market_risk_cap = 2000.0
        bot_config.per_outcome_risk_cap = 1500.0
        bot_config.max_position_size = 1000.0
        bot_config.max_order_size = 100.0
        bot_config.slippage_tolerance_bps = 50
        bot_config.order_timeout_seconds = 30
        bot_config.price_precision = 4
        bot_config.size_precision = 4
        bot_config.default_order_type = "GTC"
        bot_config.complement_arb_min_deviation = 0.01
        bot_config.complement_arb_max_deviation = 0.20
        bot_config.complement_arb_base_size = 10.0
        bot_config.complement_arb_max_size = 100.0
        bot_config.complement_arb_size_scaling = 50.0

        risk_config = RiskManagementConfig.from_bot_config(bot_config)

        assert risk_config.global_risk.global_risk_cap == 10000.0
        assert risk_config.global_risk.position_risk_cap == 1000.0
        assert risk_config.order_execution.slippage_tolerance_bps == 50
        assert risk_config.strategy_risk.complement_arb_min_deviation == 0.01

    def test_validate_trading_parameters(self):
        """Test trading parameter validation."""
        risk_config = RiskManagementConfig(
            global_risk=GlobalRiskConfig(
                global_risk_cap=10000.0,
                position_risk_cap=1000.0,
                market_risk_cap=5000.0,
                per_market_risk_cap=2000.0,
                per_outcome_risk_cap=1500.0,
                max_position_size=1000.0,
                max_order_size=100.0,
            )
        )

        # Valid parameters
        result = risk_config.validate_trading_parameters(
            token_id="test_token",
            intended_notional=50.0,
            market_slug="test_market",
            outcome_type="yes",
        )

        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_invalid_parameters(self):
        """Test validation with invalid parameters."""
        risk_config = RiskManagementConfig(
            global_risk=GlobalRiskConfig(
                global_risk_cap=10000.0,
                position_risk_cap=1000.0,
                market_risk_cap=5000.0,
                per_market_risk_cap=2000.0,
                per_outcome_risk_cap=1500.0,
                max_position_size=1000.0,
                max_order_size=100.0,
            )
        )

        # Invalid parameters - negative notional
        result = risk_config.validate_trading_parameters(
            token_id="test_token",
            intended_notional=-50.0,  # Invalid
            market_slug="test_market",
            outcome_type="yes",
        )

        assert result["is_valid"] is False
        assert len(result["errors"]) > 0


class TestRiskManagerValidation:
    """Test RiskManager with validation."""

    @pytest.fixture
    def mock_order_client(self):
        """Create mock order client."""
        client = Mock()
        client.ready.return_value = True
        return client

    @pytest.fixture
    def mock_state_manager(self):
        """Create mock state manager."""
        state = Mock(spec=StateManager)
        state.get_total_exposure.return_value = 1000.0
        state.get_position_notional.return_value = 100.0
        state.get_market_exposure.return_value = 500.0
        state.get_outcome_exposure.return_value = 300.0
        return state

    @pytest.fixture
    def valid_bot_config(self):
        """Create valid bot configuration."""
        config = Mock(spec=BotConfig)
        config.global_risk_cap = 10000.0
        config.position_risk_cap = 1000.0
        config.market_risk_cap = 5000.0
        config.per_market_risk_cap = 2000.0
        config.per_outcome_risk_cap = 1500.0
        config.max_position_size = 1000.0
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
        return config

    def test_risk_manager_initialization_with_valid_config(
        self, valid_bot_config, mock_order_client, mock_state_manager
    ):
        """Test RiskManager initialization with valid configuration."""
        risk_manager = RiskManager(
            cfg=valid_bot_config,
            order_client=mock_order_client,
            state=mock_state_manager,
        )

        assert hasattr(risk_manager, "risk_config")
        assert risk_manager.risk_config.validation_enabled is True

        # Check that configuration was validated
        limits = risk_manager.risk_config.get_risk_limits()
        assert limits["global_risk_cap"] == 10000.0

    def test_risk_manager_initialization_with_invalid_config(
        self, mock_order_client, mock_state_manager
    ):
        """Test RiskManager initialization with invalid configuration."""
        # Create invalid config
        invalid_config = Mock(spec=BotConfig)
        invalid_config.global_risk_cap = 1000.0
        invalid_config.position_risk_cap = 5000.0  # Exceeds global cap
        invalid_config.market_risk_cap = 5000.0
        invalid_config.per_market_risk_cap = 2000.0
        invalid_config.per_outcome_risk_cap = 1500.0
        invalid_config.max_position_size = 50.0
        invalid_config.max_order_size = 100.0  # Exceeds position size
        invalid_config.slippage_tolerance_bps = 50
        invalid_config.order_timeout_seconds = 30
        invalid_config.price_precision = 4
        invalid_config.size_precision = 4
        invalid_config.default_order_type = "GTC"
        invalid_config.complement_arb_min_deviation = 0.01
        invalid_config.complement_arb_max_deviation = 0.20
        invalid_config.complement_arb_base_size = 10.0
        invalid_config.complement_arb_max_size = 100.0
        invalid_config.complement_arb_size_scaling = 50.0

        with pytest.raises(RuntimeError) as excinfo:
            RiskManager(
                cfg=invalid_config,
                order_client=mock_order_client,
                state=mock_state_manager,
            )

        assert "Invalid risk configuration" in str(excinfo.value)

    def test_enhanced_preflight_validation(
        self, valid_bot_config, mock_order_client, mock_state_manager
    ):
        """Test enhanced preflight validation."""
        risk_manager = RiskManager(
            cfg=valid_bot_config,
            order_client=mock_order_client,
            state=mock_state_manager,
        )

        # Valid trade should pass
        result = risk_manager.preflight(
            token_id="test_token",
            intended_notional=50.0,
            market_slug="test_market",
            outcome_type="yes",
        )

        assert result is True

    def test_preflight_parameter_validation_failure(
        self, valid_bot_config, mock_order_client, mock_state_manager
    ):
        """Test preflight validation with invalid parameters."""
        risk_manager = RiskManager(
            cfg=valid_bot_config,
            order_client=mock_order_client,
            state=mock_state_manager,
        )

        # Invalid trade - negative notional should fail
        with pytest.raises(ValueError) as excinfo:
            risk_manager.preflight(
                token_id="test_token",
                intended_notional=-50.0,  # Invalid
                market_slug="test_market",
                outcome_type="yes",
            )

        # The error message should be the backward compatible version
        assert "Intended notional must be positive" in str(excinfo.value)

    def test_validate_config_before_startup(self, valid_bot_config):
        """Test static configuration validation before startup."""
        result = RiskManager.validate_config_before_startup(valid_bot_config)

        assert result["is_valid"] is True
        assert len(result["errors"]) == 0
        assert "risk_config" in result

    def test_validate_config_before_startup_invalid(self):
        """Test static configuration validation with invalid config."""
        invalid_config = Mock(spec=BotConfig)
        invalid_config.global_risk_cap = -1000.0  # Invalid
        invalid_config.position_risk_cap = 1000.0
        invalid_config.market_risk_cap = 5000.0
        invalid_config.per_market_risk_cap = 2000.0
        invalid_config.per_outcome_risk_cap = 1500.0
        invalid_config.max_position_size = 1000.0
        invalid_config.max_order_size = 100.0
        invalid_config.slippage_tolerance_bps = 50
        invalid_config.order_timeout_seconds = 30
        invalid_config.price_precision = 4
        invalid_config.size_precision = 4
        invalid_config.default_order_type = "GTC"
        invalid_config.complement_arb_min_deviation = 0.01
        invalid_config.complement_arb_max_deviation = 0.20
        invalid_config.complement_arb_base_size = 10.0
        invalid_config.complement_arb_max_size = 100.0
        invalid_config.complement_arb_size_scaling = 50.0

        result = RiskManager.validate_config_before_startup(invalid_config)

        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

    def test_startup_validation(
        self, valid_bot_config, mock_order_client, mock_state_manager
    ):
        """Test startup validation method."""
        risk_manager = RiskManager(
            cfg=valid_bot_config,
            order_client=mock_order_client,
            state=mock_state_manager,
        )

        result = risk_manager.validate_system_startup()

        assert result["is_valid"] is True
        assert "config_summary" in result
        assert result["config_summary"]["global_risk_cap"] == 10000.0
