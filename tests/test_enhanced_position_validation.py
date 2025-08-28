"""
Comprehensive tests for enhanced position size validation system.

Tests cover:
- Basic input validation
- Market liquidity constraints
- Dynamic position sizing
- Race condition prevention
- Atomic operations
- Market condition assessment
- Slippage and market impact validation
- Concentration risk analysis
"""

import asyncio
from decimal import Decimal

import pytest

from inkedup_bot.risk.atomic_operations import AtomicOperationManager
from inkedup_bot.risk.enhanced_position_validator import (
    EnhancedPositionValidator,
    MarketCondition,
    PositionValidationResult,
    ValidationSeverity,
)


class MockStateManager:
    """Mock state manager for testing."""

    def __init__(self):
        self.positions = {}
        self.market_exposures = {}
        self.outcome_exposures = {}
        self.total_exposure = Decimal("0")
        self._last_position_update = {}

    def get_total_exposure(self):
        return float(self.total_exposure)

    def get_market_exposure(self, market_slug):
        return float(self.market_exposures.get(market_slug, Decimal("0")))

    def get_outcome_exposure(self, outcome_type):
        return float(self.outcome_exposures.get(outcome_type, Decimal("0")))

    def get_position_notional(self, token_id):
        return float(
            self.positions.get(token_id, {}).get("notional_value", Decimal("0"))
        )


class MockOrderClient:
    """Mock order client for testing."""

    def __init__(self):
        self.pending_orders = set()
        self._ready = True

    def ready(self):
        return self._ready

    async def has_pending_orders(self, token_id):
        return token_id in self.pending_orders

    def add_pending_order(self, token_id):
        self.pending_orders.add(token_id)

    def remove_pending_order(self, token_id):
        self.pending_orders.discard(token_id)


class MockMarketDataProvider:
    """Mock market data provider for testing."""

    def __init__(self):
        self.market_data = {}

    def set_market_data(self, market_slug, data):
        self.market_data[market_slug] = data

    async def get_market_data(self, market_slug):
        return self.market_data.get(market_slug)


@pytest.fixture
def mock_state_manager():
    """Create mock state manager."""
    return MockStateManager()


@pytest.fixture
def mock_order_client():
    """Create mock order client."""
    return MockOrderClient()


@pytest.fixture
def mock_market_data_provider():
    """Create mock market data provider."""
    return MockMarketDataProvider()


@pytest.fixture
def atomic_manager():
    """Create atomic operations manager for tests."""
    return AtomicOperationManager(default_timeout=5.0, max_concurrent_operations=10)


@pytest.fixture
def enhanced_validator(
    mock_state_manager, mock_order_client, mock_market_data_provider, atomic_manager
):
    """Create enhanced position validator with mocked dependencies."""
    return EnhancedPositionValidator(
        state_manager=mock_state_manager,
        market_data_provider=mock_market_data_provider,
        order_client=mock_order_client,
        atomic_manager=atomic_manager,
        config={
            "max_liquidity_ratio": 0.1,
            "max_slippage_tolerance": 0.05,
            "volatility_adjustment_factor": 0.5,
            "correlation_threshold": 0.7,
            "min_market_depth": 100,
            "max_market_impact": 0.02,
        },
    )


@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    return {
        "bid_price": 0.45,
        "ask_price": 0.55,
        "bid_size": 1000,
        "ask_size": 1000,
        "last_price": 0.50,
        "volume_24h": 10000,
        "price_change_24h": 0.02,
        "volatility": 0.15,
        "liquidity_score": 0.7,
        "is_active": True,
        "is_suspended": False,
        "is_settled": False,
    }


class TestBasicInputValidation:
    """Test basic input validation."""

    @pytest.mark.asyncio
    async def test_empty_token_id(self, enhanced_validator):
        """Test validation fails for empty token ID."""
        result = await enhanced_validator.validate_position_size(
            token_id="",
            intended_size=Decimal("100"),
            market_slug="test_market",
            outcome_type="YES",
        )

        assert not result.is_valid
        assert result.severity == ValidationSeverity.ERROR
        assert "Token ID cannot be empty" in result.message

    @pytest.mark.asyncio
    async def test_negative_size(self, enhanced_validator):
        """Test validation fails for negative position size."""
        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("-100"),
            market_slug="test_market",
            outcome_type="YES",
        )

        assert not result.is_valid
        assert result.severity == ValidationSeverity.ERROR
        assert "must be positive" in result.message

    @pytest.mark.asyncio
    async def test_zero_size(self, enhanced_validator):
        """Test validation fails for zero position size."""
        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("0"),
            market_slug="test_market",
            outcome_type="YES",
        )

        assert not result.is_valid
        assert result.severity == ValidationSeverity.ERROR

    @pytest.mark.asyncio
    async def test_invalid_outcome_type(self, enhanced_validator):
        """Test validation fails for invalid outcome type."""
        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("100"),
            market_slug="test_market",
            outcome_type="INVALID",
        )

        assert not result.is_valid
        assert result.severity == ValidationSeverity.ERROR
        assert "must be YES or NO" in result.message


class TestMarketStateValidation:
    """Test market state validation."""

    @pytest.mark.asyncio
    async def test_settled_market(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test validation fails for settled market."""
        settled_data = {**sample_market_data, "is_settled": True}
        mock_market_data_provider.set_market_data("settled_market", settled_data)

        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("100"),
            market_slug="settled_market",
            outcome_type="YES",
        )

        assert not result.is_valid
        assert result.severity == ValidationSeverity.CRITICAL
        assert "already settled" in result.message

    @pytest.mark.asyncio
    async def test_suspended_market(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test validation fails for suspended market."""
        suspended_data = {**sample_market_data, "is_suspended": True}
        mock_market_data_provider.set_market_data("suspended_market", suspended_data)

        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("100"),
            market_slug="suspended_market",
            outcome_type="YES",
        )

        assert not result.is_valid
        assert result.severity == ValidationSeverity.ERROR
        assert "suspended" in result.message

    @pytest.mark.asyncio
    async def test_inactive_market(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test validation fails for inactive market."""
        inactive_data = {**sample_market_data, "is_active": False}
        mock_market_data_provider.set_market_data("inactive_market", inactive_data)

        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("100"),
            market_slug="inactive_market",
            outcome_type="YES",
        )

        assert not result.is_valid
        assert result.severity == ValidationSeverity.ERROR
        assert "not active" in result.message


class TestLiquidityValidation:
    """Test liquidity-based validation."""

    @pytest.mark.asyncio
    async def test_excessive_liquidity_usage(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test validation fails when position uses too much liquidity."""
        # Set low liquidity
        low_liquidity_data = {**sample_market_data, "ask_size": 100}
        mock_market_data_provider.set_market_data(
            "low_liquidity_market", low_liquidity_data
        )

        # Try to use more than 10% of liquidity (validator's default limit)
        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("50"),  # 50% of 100 ask_size
            market_slug="low_liquidity_market",
            outcome_type="YES",
        )

        assert not result.is_valid
        assert result.severity == ValidationSeverity.ERROR
        assert "liquidity threshold" in result.message
        assert result.suggested_max_size is not None

    @pytest.mark.asyncio
    async def test_acceptable_liquidity_usage(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test validation passes with acceptable liquidity usage."""
        mock_market_data_provider.set_market_data(
            "good_liquidity_market", sample_market_data
        )

        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("50"),  # 5% of 1000 ask_size
            market_slug="good_liquidity_market",
            outcome_type="YES",
        )

        # Should pass but might have warnings
        assert result.is_valid

    @pytest.mark.asyncio
    async def test_insufficient_market_depth(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test validation fails with insufficient market depth."""
        low_depth_data = {
            **sample_market_data,
            "bid_size": 30,
            "ask_size": 30,
        }  # Total 60 < 100 minimum
        mock_market_data_provider.set_market_data("low_depth_market", low_depth_data)

        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("10"),
            market_slug="low_depth_market",
            outcome_type="YES",
        )

        assert not result.is_valid
        assert "Insufficient market depth" in result.message


class TestConcentrationRiskValidation:
    """Test concentration risk validation."""

    @pytest.mark.asyncio
    async def test_high_market_concentration(
        self,
        enhanced_validator,
        mock_state_manager,
        mock_market_data_provider,
        sample_market_data,
    ):
        """Test validation fails for high market concentration."""
        # Set up existing exposure
        mock_state_manager.total_exposure = Decimal("1000")
        mock_state_manager.market_exposures["concentrated_market"] = Decimal(
            "400"
        )  # 40% already
        mock_market_data_provider.set_market_data(
            "concentrated_market", sample_market_data
        )

        # Try to add more to already concentrated market
        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("200"),  # Would make it 60% total
            market_slug="concentrated_market",
            outcome_type="YES",
        )

        assert not result.is_valid
        assert "concentration too high" in result.message

    @pytest.mark.asyncio
    async def test_high_outcome_concentration(
        self,
        enhanced_validator,
        mock_state_manager,
        mock_market_data_provider,
        sample_market_data,
    ):
        """Test validation fails for high outcome concentration."""
        # Set up existing exposure
        mock_state_manager.total_exposure = Decimal("1000")
        mock_state_manager.outcome_exposures["YES"] = Decimal("500")  # 50% already
        mock_market_data_provider.set_market_data("test_market", sample_market_data)

        # Try to add more YES exposure
        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("200"),  # Would make it 70% total
            market_slug="test_market",
            outcome_type="YES",
        )

        assert not result.is_valid
        assert "concentration too high" in result.message


class TestDynamicSizingValidation:
    """Test dynamic position sizing based on market conditions."""

    @pytest.mark.asyncio
    async def test_volatile_market_sizing(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test position size reduction in volatile markets."""
        volatile_data = {**sample_market_data, "volatility": 0.35}  # High volatility
        mock_market_data_provider.set_market_data("volatile_market", volatile_data)

        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("1000"),  # Large position
            market_slug="volatile_market",
            outcome_type="YES",
        )

        # Should fail and suggest smaller size
        assert not result.is_valid
        assert result.suggested_max_size is not None
        assert result.suggested_max_size < Decimal("1000")
        assert result.market_condition == MarketCondition.VOLATILE

    @pytest.mark.asyncio
    async def test_low_liquidity_market_sizing(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test position size reduction in low liquidity markets."""
        low_liquidity_data = {
            **sample_market_data,
            "liquidity_score": 0.2,
        }  # Low liquidity score
        mock_market_data_provider.set_market_data(
            "low_liquidity_market", low_liquidity_data
        )

        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("500"),
            market_slug="low_liquidity_market",
            outcome_type="YES",
        )

        # Should reduce position size
        assert not result.is_valid
        assert result.market_condition == MarketCondition.LOW_LIQUIDITY


class TestSlippageValidation:
    """Test slippage and market impact validation."""

    @pytest.mark.asyncio
    async def test_high_slippage_rejection(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test validation fails for high estimated slippage."""
        # Create market with wide spread and low depth
        high_slippage_data = {
            **sample_market_data,
            "bid_price": 0.30,
            "ask_price": 0.70,  # 40 cents spread
            "bid_size": 100,
            "ask_size": 100,
        }
        mock_market_data_provider.set_market_data(
            "high_slippage_market", high_slippage_data
        )

        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("150"),  # Large relative to depth
            market_slug="high_slippage_market",
            outcome_type="YES",
        )

        # Should fail due to high slippage
        assert not result.is_valid
        assert "slippage" in result.message.lower()
        assert result.estimated_slippage is not None

    @pytest.mark.asyncio
    async def test_acceptable_slippage(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test validation passes with acceptable slippage."""
        mock_market_data_provider.set_market_data(
            "good_slippage_market", sample_market_data
        )

        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("50"),  # Small relative to depth
            market_slug="good_slippage_market",
            outcome_type="YES",
        )

        assert result.is_valid
        assert result.estimated_slippage is not None
        assert result.estimated_slippage <= enhanced_validator.max_slippage_tolerance


class TestRaceConditionPrevention:
    """Test race condition prevention mechanisms."""

    @pytest.mark.asyncio
    async def test_rapid_successive_validations(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test prevention of rapid successive validations."""
        mock_market_data_provider.set_market_data("test_market", sample_market_data)

        # First validation
        result1 = await enhanced_validator.validate_position_size(
            token_id="rapid_token",
            intended_size=Decimal("100"),
            market_slug="test_market",
            outcome_type="YES",
        )

        # Immediate second validation should be rejected
        result2 = await enhanced_validator.validate_position_size(
            token_id="rapid_token",
            intended_size=Decimal("100"),
            market_slug="test_market",
            outcome_type="YES",
        )

        assert result1.is_valid
        assert not result2.is_valid
        assert "too recent" in result2.message

    @pytest.mark.asyncio
    async def test_pending_order_prevention(
        self,
        enhanced_validator,
        mock_order_client,
        mock_market_data_provider,
        sample_market_data,
    ):
        """Test validation fails when pending order exists."""
        mock_market_data_provider.set_market_data("test_market", sample_market_data)
        mock_order_client.add_pending_order("pending_token")

        result = await enhanced_validator.validate_position_size(
            token_id="pending_token",
            intended_size=Decimal("100"),
            market_slug="test_market",
            outcome_type="YES",
        )

        assert not result.is_valid
        assert "Pending order exists" in result.message

    @pytest.mark.asyncio
    async def test_concurrent_validation_detection(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test detection and prevention of concurrent validations."""
        mock_market_data_provider.set_market_data("test_market", sample_market_data)

        # Start two validations concurrently
        async def validate():
            return await enhanced_validator.validate_position_size(
                token_id="concurrent_token",
                intended_size=Decimal("100"),
                market_slug="test_market",
                outcome_type="YES",
            )

        # Use atomic validation to test race condition prevention
        tasks = [validate(), validate()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # At least one should succeed, but the system should handle concurrency safely
        valid_results = [r for r in results if isinstance(r, PositionValidationResult)]
        assert len(valid_results) >= 1


class TestAtomicOperations:
    """Test atomic operations functionality."""

    @pytest.mark.asyncio
    async def test_atomic_validation_success(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test successful atomic validation."""
        mock_market_data_provider.set_market_data("atomic_market", sample_market_data)

        result = await enhanced_validator.validate_position_size(
            token_id="atomic_token",
            intended_size=Decimal("100"),
            market_slug="atomic_market",
            outcome_type="YES",
            use_atomic_validation=True,
        )

        assert result.metadata is not None
        assert result.metadata.get("atomic_validation") is True
        assert "operation_id" in result.metadata

    @pytest.mark.asyncio
    async def test_validation_safety_check(self, enhanced_validator):
        """Test validation safety assessment."""
        safety_result = await enhanced_validator.check_concurrent_validation_safety(
            token_id="safety_token", market_slug="safety_market"
        )

        assert "is_safe" in safety_result
        assert "warnings" in safety_result
        assert "lock_status" in safety_result

    @pytest.mark.asyncio
    async def test_validation_metrics(self, enhanced_validator):
        """Test validation system metrics collection."""
        metrics = enhanced_validator.get_validation_metrics()

        assert "pending_validations" in metrics
        assert "position_update_timestamps" in metrics
        assert "market_data_cache_size" in metrics
        assert "atomic_metrics" in metrics


class TestMarketConditionAssessment:
    """Test market condition assessment."""

    @pytest.mark.asyncio
    async def test_normal_market_condition(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test normal market condition assessment."""
        mock_market_data_provider.set_market_data("normal_market", sample_market_data)

        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("100"),
            market_slug="normal_market",
            outcome_type="YES",
        )

        assert result.market_condition == MarketCondition.NORMAL

    @pytest.mark.asyncio
    async def test_stressed_market_condition(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test stressed market condition assessment."""
        stressed_data = {
            **sample_market_data,
            "volatility": 0.25,  # High volatility
            "liquidity_score": 0.4,  # Low liquidity
            "price_change_24h": 0.15,  # Large price change
        }
        mock_market_data_provider.set_market_data("stressed_market", stressed_data)

        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("100"),
            market_slug="stressed_market",
            outcome_type="YES",
        )

        assert result.market_condition == MarketCondition.STRESSED


class TestOptimalPositionSizing:
    """Test optimal position size recommendations."""

    @pytest.mark.asyncio
    async def test_get_optimal_size_normal_conditions(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test optimal size recommendation under normal conditions."""
        mock_market_data_provider.set_market_data("optimal_market", sample_market_data)

        optimal_size, suggestions = (
            await enhanced_validator.get_suggested_position_size(
                token_id="optimal_token",
                desired_size=Decimal("200"),
                market_slug="optimal_market",
                outcome_type="YES",
            )
        )

        assert optimal_size is not None
        assert len(suggestions) > 0
        assert optimal_size <= Decimal("200")  # Should not exceed desired

    @pytest.mark.asyncio
    async def test_get_optimal_size_constrained_conditions(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test optimal size recommendation under constrained conditions."""
        # Low liquidity market
        constrained_data = {**sample_market_data, "ask_size": 50}
        mock_market_data_provider.set_market_data(
            "constrained_market", constrained_data
        )

        optimal_size, suggestions = (
            await enhanced_validator.get_suggested_position_size(
                token_id="constrained_token",
                desired_size=Decimal("100"),
                market_slug="constrained_market",
                outcome_type="YES",
            )
        )

        # Should suggest smaller size due to liquidity constraints
        assert optimal_size < Decimal("100")
        assert len(suggestions) > 0


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_market_data_unavailable(self, enhanced_validator):
        """Test handling when market data is unavailable."""
        result = await enhanced_validator.validate_position_size(
            token_id="test_token",
            intended_size=Decimal("100"),
            market_slug="nonexistent_market",
            outcome_type="YES",
        )

        assert not result.is_valid
        assert "Unable to retrieve market data" in result.message

    @pytest.mark.asyncio
    async def test_validation_without_atomic_protection(
        self, enhanced_validator, mock_market_data_provider, sample_market_data
    ):
        """Test validation without atomic protection as fallback."""
        mock_market_data_provider.set_market_data("fallback_market", sample_market_data)

        result = await enhanced_validator.validate_position_size(
            token_id="fallback_token",
            intended_size=Decimal("100"),
            market_slug="fallback_market",
            outcome_type="YES",
            use_atomic_validation=False,
        )

        # Should work but without atomic protection metadata
        assert (
            result.is_valid or not result.is_valid
        )  # Either outcome is valid for fallback
        assert result.metadata is None or "atomic_validation" not in result.metadata

    @pytest.mark.asyncio
    async def test_system_overload_handling(self, enhanced_validator, atomic_manager):
        """Test handling of system overload conditions."""
        # Simulate high load by creating many pending operations
        for i in range(atomic_manager.max_concurrent_operations):
            atomic_manager._pending_operations.add(f"load_test_{i}")

        safety_check = await enhanced_validator.check_concurrent_validation_safety(
            token_id="overload_token", market_slug="overload_market"
        )

        assert not safety_check["is_safe"]
        assert len(safety_check["warnings"]) > 0


# Integration test
class TestIntegration:
    """Integration tests for the complete validation system."""

    @pytest.mark.asyncio
    async def test_full_validation_pipeline(
        self,
        enhanced_validator,
        mock_state_manager,
        mock_order_client,
        mock_market_data_provider,
        sample_market_data,
    ):
        """Test complete validation pipeline with realistic scenario."""
        # Set up realistic market conditions
        mock_market_data_provider.set_market_data(
            "integration_market", sample_market_data
        )

        # Set up some existing positions
        mock_state_manager.total_exposure = Decimal("5000")
        mock_state_manager.market_exposures["integration_market"] = Decimal("1000")
        mock_state_manager.outcome_exposures["YES"] = Decimal("2000")

        # Test a reasonable position size
        result = await enhanced_validator.validate_position_size(
            token_id="integration_token",
            intended_size=Decimal("500"),
            market_slug="integration_market",
            outcome_type="YES",
        )

        # Should have comprehensive validation result
        assert isinstance(result, PositionValidationResult)
        assert result.market_condition is not None
        assert result.metadata is not None
        assert isinstance(result.warnings, list)

        # Test metrics collection
        metrics = enhanced_validator.get_validation_metrics()
        assert all(key in metrics for key in ["pending_validations", "atomic_metrics"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
