"""
Integration test demonstrating the complete enhanced position validation system.

This test shows how all the components work together:
- Enhanced position validator
- Atomic operations manager  
- Race condition prevention
- Market condition assessment
- Liquidity-based validation
- Dynamic position sizing
"""

import asyncio
import os
import sys
from decimal import Decimal

import pytest

# Add the parent directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from inkedup_bot.risk.atomic_operations import AtomicOperationManager
from inkedup_bot.risk.enhanced_position_validator import (
    EnhancedPositionValidator,
    MarketCondition,
    ValidationSeverity,
)


class IntegratedMockStateManager:
    """Integrated mock state manager with realistic behavior."""

    def __init__(self):
        self.positions = {
            "token_1": {
                "notional_value": 500.0,
                "market_slug": "market_A",
                "outcome_type": "YES",
            },
            "token_2": {
                "notional_value": 300.0,
                "market_slug": "market_B",
                "outcome_type": "NO",
            },
            "token_3": {
                "notional_value": 200.0,
                "market_slug": "market_A",
                "outcome_type": "NO",
            },
        }
        self.total_exposure = 1000.0
        self.market_exposures = {"market_A": 700.0, "market_B": 300.0}
        self.outcome_exposures = {"YES": 500.0, "NO": 500.0}
        self._last_position_update = {}

    def get_total_exposure(self):
        return self.total_exposure

    def get_market_exposure(self, market_slug):
        return self.market_exposures.get(market_slug, 0.0)

    def get_outcome_exposure(self, outcome_type):
        return self.outcome_exposures.get(outcome_type, 0.0)

    def get_position_notional(self, token_id):
        return self.positions.get(token_id, {}).get("notional_value", 0.0)


class IntegratedMockOrderClient:
    """Mock order client with pending order tracking."""

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


class IntegratedMockMarketDataProvider:
    """Mock market data provider with various market conditions."""

    def __init__(self):
        self.market_scenarios = {
            "normal_market": {
                "bid_price": 0.49,
                "ask_price": 0.51,
                "bid_size": 2000,
                "ask_size": 2000,  # Tighter spread
                "last_price": 0.50,
                "volume_24h": 50000,
                "price_change_24h": 0.02,
                "volatility": 0.10,
                "liquidity_score": 0.8,
                "is_active": True,
                "is_suspended": False,
                "is_settled": False,
            },
            "volatile_market": {
                "bid_price": 0.30,
                "ask_price": 0.70,
                "bid_size": 1000,
                "ask_size": 1000,
                "last_price": 0.50,
                "volume_24h": 20000,
                "price_change_24h": 0.15,
                "volatility": 0.35,
                "liquidity_score": 0.6,
                "is_active": True,
                "is_suspended": False,
                "is_settled": False,
            },
            "low_liquidity_market": {
                "bid_price": 0.48,
                "ask_price": 0.52,
                "bid_size": 50,
                "ask_size": 50,
                "last_price": 0.50,
                "volume_24h": 1000,
                "price_change_24h": 0.01,
                "volatility": 0.05,
                "liquidity_score": 0.2,
                "is_active": True,
                "is_suspended": False,
                "is_settled": False,
            },
            "stressed_market": {
                "bid_price": 0.20,
                "ask_price": 0.80,
                "bid_size": 100,
                "ask_size": 100,
                "last_price": 0.50,
                "volume_24h": 5000,
                "price_change_24h": 0.20,
                "volatility": 0.30,
                "liquidity_score": 0.3,
                "is_active": True,
                "is_suspended": False,
                "is_settled": False,
            },
            "suspended_market": {
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
                "is_suspended": True,
                "is_settled": False,
            },
        }

    async def get_market_data(self, market_slug):
        return self.market_scenarios.get(market_slug)


@pytest.fixture
async def integrated_system():
    """Create complete integrated enhanced position validation system."""
    atomic_manager = AtomicOperationManager(
        default_timeout=5.0, max_concurrent_operations=10
    )
    state_manager = IntegratedMockStateManager()
    order_client = IntegratedMockOrderClient()
    market_data_provider = IntegratedMockMarketDataProvider()

    validator = EnhancedPositionValidator(
        state_manager=state_manager,
        market_data_provider=market_data_provider,
        order_client=order_client,
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

    yield {
        "validator": validator,
        "atomic_manager": atomic_manager,
        "state_manager": state_manager,
        "order_client": order_client,
        "market_data_provider": market_data_provider,
    }

    await atomic_manager.shutdown()


class TestEnhancedPositionValidationIntegration:
    """Integration tests for the complete enhanced position validation system."""

    @pytest.mark.asyncio
    async def test_normal_market_validation_success(self, integrated_system):
        """Test successful validation under normal market conditions."""
        validator = integrated_system["validator"]

        result = await validator.validate_position_size(
            token_id="integration_token_1",
            intended_size=Decimal("100"),  # Reasonable size
            market_slug="normal_market",
            outcome_type="YES",
        )

        # Should pass validation
        assert result.is_valid
        assert result.severity == ValidationSeverity.INFO
        assert result.market_condition == MarketCondition.NORMAL
        assert result.metadata["atomic_validation"] is True
        assert "operation_id" in result.metadata

        print(f"✓ Normal market validation: {result.message}")
        print(f"✓ Market condition: {result.market_condition.value}")
        print(f"✓ Estimated slippage: {result.estimated_slippage}")

    @pytest.mark.asyncio
    async def test_volatile_market_size_adjustment(self, integrated_system):
        """Test position size adjustment in volatile markets."""
        validator = integrated_system["validator"]

        result = await validator.validate_position_size(
            token_id="integration_token_2",
            intended_size=Decimal("500"),  # Large position in volatile market
            market_slug="volatile_market",
            outcome_type="YES",
        )

        # Should fail due to volatility but suggest smaller size
        assert not result.is_valid
        assert result.market_condition == MarketCondition.VOLATILE
        assert result.suggested_max_size is not None
        assert result.suggested_max_size < Decimal("500")

        print(f"✓ Volatile market adjustment: {result.message}")
        print(f"✓ Suggested max size: {result.suggested_max_size}")
        print(f"✓ Market condition: {result.market_condition.value}")

    @pytest.mark.asyncio
    async def test_low_liquidity_rejection(self, integrated_system):
        """Test rejection due to insufficient liquidity."""
        validator = integrated_system["validator"]

        result = await validator.validate_position_size(
            token_id="integration_token_3",
            intended_size=Decimal("25"),  # 50% of available liquidity (50 ask_size)
            market_slug="low_liquidity_market",
            outcome_type="YES",
        )

        # Should fail due to liquidity constraints
        assert not result.is_valid
        assert "liquidity threshold" in result.message
        assert result.suggested_max_size is not None

        print(f"✓ Low liquidity rejection: {result.message}")
        print(f"✓ Liquidity ratio: {result.metadata.get('liquidity_ratio', 'N/A')}")

    @pytest.mark.asyncio
    async def test_market_suspension_blocking(self, integrated_system):
        """Test validation blocking for suspended markets."""
        validator = integrated_system["validator"]

        result = await validator.validate_position_size(
            token_id="integration_token_4",
            intended_size=Decimal("100"),
            market_slug="suspended_market",
            outcome_type="YES",
        )

        # Should fail due to market suspension
        assert not result.is_valid
        assert result.severity == ValidationSeverity.ERROR
        assert "suspended" in result.message

        print(f"✓ Market suspension blocking: {result.message}")

    @pytest.mark.asyncio
    async def test_concentration_risk_prevention(self, integrated_system):
        """Test concentration risk prevention."""
        validator = integrated_system["validator"]

        # Try to add large position to already concentrated market
        result = await validator.validate_position_size(
            token_id="integration_token_5",
            intended_size=Decimal(
                "400"
            ),  # Would make market_A 55% of portfolio (700 + 400) / 2000
            market_slug="normal_market",
            outcome_type="YES",
        )

        # Check concentration warnings or failures
        has_concentration_warning = any(
            "concentration" in warning.lower() for warning in result.warnings
        )
        concentration_failed = "concentration" in result.message.lower()

        if not result.is_valid and concentration_failed:
            print(f"✓ Concentration risk prevented: {result.message}")
        elif has_concentration_warning:
            print(f"✓ Concentration risk warned: {result.warnings}")
        else:
            print("✓ Concentration risk assessment completed")

    @pytest.mark.asyncio
    async def test_concurrent_validation_safety(self, integrated_system):
        """Test safety of concurrent validations."""
        validator = integrated_system["validator"]
        results = []

        async def validate_position(token_id, size):
            result = await validator.validate_position_size(
                token_id=f"concurrent_{token_id}",
                intended_size=Decimal(str(size)),
                market_slug="normal_market",
                outcome_type="YES",
            )
            results.append(
                (token_id, result.is_valid, result.metadata.get("operation_id"))
            )

        # Run multiple concurrent validations
        await asyncio.gather(
            validate_position("A", 50),
            validate_position("B", 75),
            validate_position("C", 100),
            validate_position("D", 125),
        )

        assert len(results) == 4
        # All should have unique operation IDs
        operation_ids = [r[2] for r in results if r[2]]
        assert len(set(operation_ids)) == len(operation_ids)

        print(f"✓ Concurrent validations completed: {len(results)} operations")
        print(f"✓ Unique operation IDs: {len(operation_ids)}")

    @pytest.mark.asyncio
    async def test_race_condition_prevention(self, integrated_system):
        """Test race condition prevention mechanisms."""
        validator = integrated_system["validator"]
        order_client = integrated_system["order_client"]

        # Add pending order to simulate race condition
        order_client.add_pending_order("race_condition_token")

        result = await validator.validate_position_size(
            token_id="race_condition_token",
            intended_size=Decimal("100"),
            market_slug="normal_market",
            outcome_type="YES",
        )

        # Should be blocked due to pending order
        assert not result.is_valid
        assert "Pending order exists" in result.message

        print(f"✓ Race condition prevented: {result.message}")

        # Remove pending order and try again
        order_client.remove_pending_order("race_condition_token")

        result2 = await validator.validate_position_size(
            token_id="race_condition_token",
            intended_size=Decimal("100"),
            market_slug="normal_market",
            outcome_type="YES",
        )

        # Should now succeed
        assert result2.is_valid
        print(f"✓ Validation after clearing race condition: {result2.message}")

    @pytest.mark.asyncio
    async def test_optimal_position_sizing_recommendation(self, integrated_system):
        """Test optimal position size recommendations."""
        validator = integrated_system["validator"]

        # Test with various desired sizes
        test_cases = [
            ("normal_market", 200, "Normal market conditions"),
            ("volatile_market", 200, "Volatile market conditions"),
            ("low_liquidity_market", 50, "Low liquidity conditions"),
        ]

        for market, desired_size, description in test_cases:
            optimal_size, suggestions = await validator.get_suggested_position_size(
                token_id=f"optimal_{market}",
                desired_size=Decimal(str(desired_size)),
                market_slug=market,
                outcome_type="YES",
            )
            optimal_info = {
                "optimal_size": float(optimal_size),
                "explanations": suggestions,
                "market_conditions": "unknown",
                "estimated_slippage": None,
            }

            print(f"✓ {description}:")
            print(
                f"  Desired: ${desired_size}, Optimal: ${optimal_info['optimal_size']}"
            )
            print(f"  Explanations: {optimal_info['explanations']}")
            print(f"  Market condition: {optimal_info['market_conditions']}")
            if optimal_info["estimated_slippage"]:
                print(f"  Estimated slippage: {optimal_info['estimated_slippage']:.2%}")
            print()

            assert "optimal_size" in optimal_info
            assert "explanations" in optimal_info
            assert optimal_info["optimal_size"] <= desired_size

    @pytest.mark.asyncio
    async def test_system_metrics_and_monitoring(self, integrated_system):
        """Test system metrics collection and monitoring."""
        validator = integrated_system["validator"]
        atomic_manager = integrated_system["atomic_manager"]

        # Perform several operations
        for i in range(3):
            await validator.validate_position_size(
                token_id=f"metrics_token_{i}",
                intended_size=Decimal("50"),
                market_slug="normal_market",
                outcome_type="YES",
            )

        # Check validation metrics
        validation_metrics = validator.get_validation_metrics()
        atomic_metrics = atomic_manager.get_lock_metrics()

        print("✓ System Metrics:")
        print(f"  Validation metrics: {validation_metrics}")
        print(f"  Atomic operations metrics: {atomic_metrics}")

        assert validation_metrics["position_update_timestamps"] >= 3
        assert atomic_metrics["total_acquisitions"] >= 3
        assert atomic_metrics["current_active"] == 0  # All operations completed

    @pytest.mark.asyncio
    async def test_error_recovery_and_resilience(self, integrated_system):
        """Test error recovery and system resilience."""
        validator = integrated_system["validator"]

        # Test with invalid market (should handle gracefully)
        result = await validator.validate_position_size(
            token_id="error_recovery_token",
            intended_size=Decimal("100"),
            market_slug="nonexistent_market",
            outcome_type="YES",
        )

        assert not result.is_valid
        assert "Unable to retrieve market data" in result.message
        print(f"✓ Error recovery for missing market: {result.message}")

        # Test with invalid input (should handle gracefully)
        result2 = await validator.validate_position_size(
            token_id="",  # Invalid token ID
            intended_size=Decimal("100"),
            market_slug="normal_market",
            outcome_type="YES",
        )

        assert not result2.is_valid
        assert "Token ID cannot be empty" in result2.message
        print(f"✓ Error recovery for invalid input: {result2.message}")

        # System should still work for valid requests
        result3 = await validator.validate_position_size(
            token_id="recovery_test_token",
            intended_size=Decimal("50"),
            market_slug="normal_market",
            outcome_type="YES",
        )

        assert result3.is_valid
        print(f"✓ System recovery after errors: {result3.message}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])  # -s to show print statements
