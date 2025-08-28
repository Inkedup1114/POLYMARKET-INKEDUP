"""
Comprehensive tests for the validation layer.

Tests all validation models, decorators, and integration with database and state management.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from inkedup_bot.validation import (
    MarketSnapshotValidation,
    OrderSide,
    OrderStatus,
    OrderValidation,
    OutcomeCorrelationValidation,
    OutcomeExposureValidation,
    PositionValidation,
    TradeValidation,
    ValidationBatch,
    ValidationError,
    get_validation_context,
    safe_decimal_conversion,
    set_validation_context,
    validate_market_slug_format,
    validate_model_data,
    validate_token_id_format,
)


class TestValidationModels:
    """Test Pydantic validation models."""

    def test_order_validation_valid_data(self):
        """Test OrderValidation with valid data."""
        valid_order = {
            "id": "order_123",
            "token_id": "token_456",
            "market_slug": "test-market",
            "side": "BUY",
            "price": Decimal("0.55"),
            "size": Decimal("100.0"),
            "status": "OPEN",
            "notional_value": Decimal("55.0"),
            "outcome_type": "YES",
        }

        validated = OrderValidation(**valid_order)
        assert validated.id == "order_123"
        assert validated.side == OrderSide.BUY
        assert validated.status == OrderStatus.OPEN
        assert validated.price == Decimal("0.55")
        assert validated.size == Decimal("100.0")

    def test_order_validation_invalid_price(self):
        """Test OrderValidation with invalid price (>1)."""
        invalid_order = {
            "id": "order_123",
            "token_id": "token_456",
            "side": "BUY",
            "price": Decimal("1.5"),  # Invalid: > 1
            "size": Decimal("100.0"),
            "status": "OPEN",
        }

        with pytest.raises(Exception):  # Pydantic ValidationError
            OrderValidation(**invalid_order)

    def test_order_validation_negative_size(self):
        """Test OrderValidation with negative size."""
        invalid_order = {
            "id": "order_123",
            "token_id": "token_456",
            "side": "BUY",
            "price": Decimal("0.5"),
            "size": Decimal("-10.0"),  # Invalid: negative size
            "status": "OPEN",
        }

        with pytest.raises(Exception):  # Pydantic ValidationError
            OrderValidation(**invalid_order)

    def test_order_validation_precision_limits(self):
        """Test OrderValidation precision validation."""
        # Test price with too many decimal places
        invalid_order = {
            "id": "order_123",
            "token_id": "token_456",
            "side": "BUY",
            "price": Decimal("0.1234567"),  # 7 decimal places (max 6)
            "size": Decimal("100.0"),
            "status": "OPEN",
        }

        with pytest.raises(Exception):  # Should fail precision validation
            OrderValidation(**invalid_order)

    def test_position_validation_valid_data(self):
        """Test PositionValidation with valid data."""
        valid_position = {
            "token_id": "token_456",
            "market_slug": "test-market",
            "outcome_type": "YES",
            "size": Decimal("50.0"),
            "notional_value": Decimal("25.0"),
        }

        validated = PositionValidation(**valid_position)
        assert validated.token_id == "token_456"
        assert validated.size == Decimal("50.0")
        assert validated.notional_value == Decimal("25.0")

    def test_position_validation_large_size(self):
        """Test PositionValidation with oversized position."""
        invalid_position = {
            "token_id": "token_456",
            "size": Decimal("2000000"),  # Exceeds 1M limit
            "notional_value": Decimal("1000000"),
        }

        with pytest.raises(Exception):  # Should fail size validation
            PositionValidation(**invalid_position)

    def test_trade_validation_valid_data(self):
        """Test TradeValidation with valid data."""
        valid_trade = {
            "order_id": "order_123",
            "token_id": "token_456",
            "market_slug": "test-market",
            "side": "BUY",
            "price": Decimal("0.55"),
            "size": Decimal("100.0"),
            "notional_value": Decimal("55.0"),
            "outcome_type": "YES",
        }

        validated = TradeValidation(**valid_trade)
        assert validated.order_id == "order_123"
        assert validated.side == OrderSide.BUY
        assert validated.notional_value == Decimal("55.0")

    def test_trade_validation_consistency_check(self):
        """Test TradeValidation notional value consistency."""
        inconsistent_trade = {
            "order_id": "order_123",
            "token_id": "token_456",
            "side": "BUY",
            "price": Decimal("0.55"),
            "size": Decimal("100.0"),
            "notional_value": Decimal("100.0"),  # Should be 55.0 (price * size)
        }

        with pytest.raises(Exception):  # Should fail consistency check
            TradeValidation(**inconsistent_trade)

    def test_market_snapshot_validation(self):
        """Test MarketSnapshotValidation."""
        valid_snapshot = {
            "market_slug": "test-market",
            "token_id": "token_456",
            "bid": Decimal("0.54"),
            "ask": Decimal("0.56"),
            "spread_bps": Decimal("357"),  # ~3.57%
            "volume_24h": Decimal("10000.0"),
            "liquidity": Decimal("50000.0"),
        }

        validated = MarketSnapshotValidation(**valid_snapshot)
        assert validated.market_slug == "test-market"
        assert validated.bid < validated.ask

    def test_market_snapshot_invalid_bid_ask(self):
        """Test MarketSnapshotValidation with bid > ask."""
        invalid_snapshot = {
            "market_slug": "test-market",
            "token_id": "token_456",
            "bid": Decimal("0.60"),  # Bid higher than ask
            "ask": Decimal("0.55"),
        }

        with pytest.raises(Exception):  # Should fail bid/ask validation
            MarketSnapshotValidation(**invalid_snapshot)

    def test_outcome_exposure_validation(self):
        """Test OutcomeExposureValidation."""
        valid_exposure = {
            "market_slug": "test-market",
            "outcome_id": "outcome_123",
            "outcome_name": "Yes",
            "position_size": Decimal("100.0"),
            "notional_value": Decimal("55.0"),
            "average_price": Decimal("0.55"),
            "current_price": Decimal("0.57"),
            "unrealized_pnl": Decimal("2.0"),
            "realized_pnl": Decimal("0.0"),
            "correlation_coefficient": Decimal("0.3"),
            "risk_score": Decimal("5.0"),
        }

        validated = OutcomeExposureValidation(**valid_exposure)
        assert validated.market_slug == "test-market"
        assert validated.correlation_coefficient == Decimal("0.3")

    def test_outcome_correlation_validation(self):
        """Test OutcomeCorrelationValidation."""
        valid_correlation = {
            "outcome_a": "outcome_123",
            "outcome_b": "outcome_456",
            "correlation": Decimal("0.75"),
            "covariance": Decimal("0.0025"),
        }

        validated = OutcomeCorrelationValidation(**valid_correlation)
        assert validated.correlation == Decimal("0.75")

    def test_outcome_correlation_same_outcomes(self):
        """Test OutcomeCorrelationValidation with same outcomes."""
        invalid_correlation = {
            "outcome_a": "outcome_123",
            "outcome_b": "outcome_123",  # Same as outcome_a
            "correlation": Decimal("1.0"),
            "covariance": Decimal("0.001"),
        }

        with pytest.raises(Exception):  # Should fail same outcome validation
            OutcomeCorrelationValidation(**invalid_correlation)


class TestValidationUtilities:
    """Test validation utility functions."""

    def test_validate_model_data_success(self):
        """Test validate_model_data with valid data."""
        valid_data = {
            "id": "order_123",
            "token_id": "token_456",
            "side": "BUY",
            "price": 0.55,
            "size": 100.0,
            "status": "OPEN",
        }

        result = validate_model_data(OrderValidation, valid_data)
        assert isinstance(result, OrderValidation)
        assert result.id == "order_123"

    def test_validate_model_data_failure(self):
        """Test validate_model_data with invalid data."""
        invalid_data = {
            "id": "order_123",
            "token_id": "token_456",
            "side": "INVALID_SIDE",  # Invalid enum value
            "price": 0.55,
            "size": 100.0,
            "status": "OPEN",
        }

        with pytest.raises(ValidationError):
            validate_model_data(OrderValidation, invalid_data)

    def test_safe_decimal_conversion(self):
        """Test safe_decimal_conversion utility."""
        # Valid conversions
        assert safe_decimal_conversion("0.55") == Decimal("0.55")
        assert safe_decimal_conversion(0.55) == Decimal("0.55")
        assert safe_decimal_conversion(None) == Decimal("0")

        # Test precision limiting
        result = safe_decimal_conversion("0.1234567", precision=4)
        assert len(str(result).split(".")[-1]) <= 4

    def test_safe_decimal_conversion_invalid(self):
        """Test safe_decimal_conversion with invalid input."""
        with pytest.raises(ValidationError):
            safe_decimal_conversion("invalid_decimal")

    def test_validate_token_id_format(self):
        """Test token ID format validation."""
        # Valid token IDs
        assert validate_token_id_format("token_123") == "token_123"
        assert (
            validate_token_id_format("  token_456  ") == "token_456"
        )  # Strips whitespace

        # Invalid token IDs
        with pytest.raises(ValidationError):
            validate_token_id_format("")  # Empty string

        with pytest.raises(ValidationError):
            validate_token_id_format("token\nwith_newline")  # Invalid characters

    def test_validate_market_slug_format(self):
        """Test market slug format validation."""
        # Valid market slugs
        assert validate_market_slug_format("test-market") == "test-market"
        assert (
            validate_market_slug_format("  TEST-MARKET  ") == "test-market"
        )  # Normalized

        # Invalid market slugs
        with pytest.raises(ValidationError):
            validate_market_slug_format("")  # Empty string


class TestValidationBatch:
    """Test batch validation utilities."""

    def test_validation_batch_success(self):
        """Test ValidationBatch with valid items."""
        batch = ValidationBatch(OrderValidation)

        valid_items = [
            {
                "id": "order_1",
                "token_id": "token_1",
                "side": "BUY",
                "price": 0.55,
                "size": 100.0,
                "status": "OPEN",
            },
            {
                "id": "order_2",
                "token_id": "token_2",
                "side": "SELL",
                "price": 0.45,
                "size": 50.0,
                "status": "OPEN",
            },
        ]

        results = batch.validate_batch(valid_items)
        assert results["total_items"] == 2
        assert results["valid_items"] == 2
        assert results["error_count"] == 0
        assert results["success_rate"] == 1.0

    def test_validation_batch_mixed_results(self):
        """Test ValidationBatch with mixed valid/invalid items."""
        batch = ValidationBatch(OrderValidation)

        mixed_items = [
            {
                "id": "order_1",
                "token_id": "token_1",
                "side": "BUY",
                "price": 0.55,
                "size": 100.0,
                "status": "OPEN",
            },
            {
                "id": "order_2",
                "token_id": "token_2",
                "side": "INVALID_SIDE",  # Invalid
                "price": 0.45,
                "size": 50.0,
                "status": "OPEN",
            },
        ]

        results = batch.validate_batch(mixed_items)
        assert results["total_items"] == 2
        assert results["valid_items"] == 1
        assert results["error_count"] == 1
        assert results["success_rate"] == 0.5

    def test_validation_batch_summary(self):
        """Test ValidationBatch summary generation."""
        batch = ValidationBatch(OrderValidation)

        # Add some validation results
        batch.validate_item(
            {
                "id": "order_1",
                "token_id": "token_1",
                "side": "BUY",
                "price": 0.55,
                "size": 100.0,
                "status": "OPEN",
            }
        )
        batch.validate_item({"id": "order_2", "side": "INVALID"})  # Invalid

        summary = batch.get_summary()
        assert "2 items" in summary
        assert "1 valid" in summary
        assert "1 errors" in summary


class TestValidationContext:
    """Test validation context configuration."""

    def test_validation_context_defaults(self):
        """Test default validation context settings."""
        context = get_validation_context()
        assert context.strict_mode == True
        assert context.log_validation_errors == True
        assert context.raise_on_validation_error == True

    def test_set_validation_context(self):
        """Test updating validation context."""
        original_strict = get_validation_context().strict_mode

        # Update setting
        set_validation_context(strict_mode=False)
        assert get_validation_context().strict_mode == False

        # Restore original
        set_validation_context(strict_mode=original_strict)


@pytest.mark.asyncio
class TestDatabaseIntegration:
    """Test validation integration with database operations."""

    def test_database_manager_imports(self):
        """Test that DatabaseManager imports validation components."""
        from inkedup_bot.database import DatabaseManager

        # Should not raise ImportError
        assert DatabaseManager is not None

    @pytest.mark.asyncio
    async def test_insert_order_validation(self):
        """Test that insert_order validates data."""
        from inkedup_bot.database import DatabaseManager

        db = DatabaseManager(":memory:")
        await db.initialize()

        # Valid order should work
        valid_order = {
            "id": "order_123",
            "token_id": "token_456",
            "side": "BUY",
            "price": 0.55,
            "size": 100.0,
            "status": "OPEN",
        }

        await db.insert_order(valid_order)  # Should not raise

        # Invalid order should fail
        invalid_order = {
            "id": "order_123",
            "token_id": "token_456",
            "side": "INVALID_SIDE",
            "price": 0.55,
            "size": 100.0,
            "status": "OPEN",
        }

        with pytest.raises(ValidationError):
            await db.insert_order(invalid_order)

        await db.close()

    @pytest.mark.asyncio
    async def test_upsert_position_validation(self):
        """Test that upsert_position validates data."""
        from inkedup_bot.database import DatabaseManager

        db = DatabaseManager(":memory:")
        await db.initialize()

        # Valid position should work
        valid_position = {
            "token_id": "token_456",
            "market_slug": "test-market",
            "outcome_type": "YES",
            "size": 50.0,
            "notional_value": 25.0,
        }

        await db.upsert_position(valid_position)  # Should not raise

        # Invalid position should fail
        invalid_position = {
            "token_id": "token_456",
            "size": 2000000,  # Exceeds limit
            "notional_value": 1000000,
        }

        with pytest.raises(ValidationError):
            await db.upsert_position(invalid_position)

        await db.close()


class TestStateManagerIntegration:
    """Test validation integration with StateManager."""

    def test_state_manager_imports(self):
        """Test that StateManager imports validation components."""
        from inkedup_bot.state import StateManager

        # Should not raise ImportError
        assert StateManager is not None

    def test_add_order_validation(self):
        """Test that add_order validates data."""
        from inkedup_bot.state import StateManager

        state_manager = StateManager(":memory:")

        # Valid order should work
        valid_order = {
            "id": "order_123",
            "token_id": "token_456",
            "side": "BUY",
            "price": 0.55,
            "size": 100.0,
            "status": "OPEN",
        }

        state_manager.add_order(valid_order)  # Should not raise

        # Invalid order should fail
        invalid_order = {
            "id": "order_123",
            "token_id": "token_456",
            "side": "INVALID_SIDE",
            "price": 0.55,
            "size": 100.0,
            "status": "OPEN",
        }

        with pytest.raises(ValidationError):
            state_manager.add_order(invalid_order)

    def test_update_position_validation(self):
        """Test that update_position validates data."""
        from inkedup_bot.state import StateManager

        state_manager = StateManager(":memory:")

        # Valid position should work
        valid_position = {
            "token_id": "token_456",
            "market_slug": "test-market",
            "outcome_type": "YES",
            "size": 50.0,
            "notional_value": 25.0,
        }

        state_manager.update_position(valid_position)  # Should not raise

        # Invalid position should fail
        invalid_position = {
            "token_id": "token_456",
            "size": 2000000,  # Exceeds limit
            "notional_value": 1000000,
        }

        with pytest.raises(ValidationError):
            state_manager.update_position(invalid_position)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_data_validation(self):
        """Test validation with empty data."""
        with pytest.raises(ValidationError):
            validate_model_data(OrderValidation, {})

    def test_none_values_handling(self):
        """Test handling of None values in optional fields."""
        valid_order = {
            "id": "order_123",
            "token_id": "token_456",
            "side": "BUY",
            "price": 0.55,
            "size": 100.0,
            "status": "OPEN",
            "market_slug": None,  # Optional field
            "outcome_type": None,  # Optional field
        }

        validated = validate_model_data(OrderValidation, valid_order)
        assert validated.market_slug is None
        assert validated.outcome_type is None

    def test_timestamp_validation(self):
        """Test timestamp field validation."""
        now = datetime.now()
        past = now - timedelta(hours=1)
        future = now + timedelta(hours=1)

        # Valid timestamp ordering
        valid_order = {
            "id": "order_123",
            "token_id": "token_456",
            "side": "BUY",
            "price": 0.55,
            "size": 100.0,
            "status": "FILLED",
            "created_at": past,
            "updated_at": now,
            "filled_at": now,
        }

        validated = validate_model_data(OrderValidation, valid_order)
        assert validated.created_at == past

    def test_boundary_values(self):
        """Test boundary value validation."""
        # Test minimum valid price
        min_price_order = {
            "id": "order_123",
            "token_id": "token_456",
            "side": "BUY",
            "price": 0.0,  # Minimum valid price
            "size": 0.0001,  # Minimum valid size
            "status": "OPEN",
        }

        validated = validate_model_data(OrderValidation, min_price_order)
        assert validated.price == Decimal("0.0")

        # Test maximum valid price
        max_price_order = {
            "id": "order_123",
            "token_id": "token_456",
            "side": "BUY",
            "price": 1.0,  # Maximum valid price
            "size": 1000000,  # Large but valid size
            "status": "OPEN",
        }

        validated = validate_model_data(OrderValidation, max_price_order)
        assert validated.price == Decimal("1.0")


# Integration test with real-world scenarios
class TestRealWorldScenarios:
    """Test validation with real-world trading scenarios."""

    def test_typical_order_flow(self):
        """Test validation through typical order lifecycle."""
        # New order placement
        new_order = {
            "id": "ord_2024_001",
            "token_id": "tok_market_yes_001",
            "market_slug": "presidential-election-2024",
            "side": "BUY",
            "price": 0.52,
            "size": 1000.0,
            "status": "OPEN",
            "outcome_type": "YES",
            "notional_value": 520.0,
        }

        validated_order = validate_model_data(OrderValidation, new_order)
        assert validated_order.id == "ord_2024_001"

        # Position update after partial fill
        position_update = {
            "token_id": "tok_market_yes_001",
            "market_slug": "presidential-election-2024",
            "outcome_type": "YES",
            "size": 500.0,  # Partially filled
            "notional_value": 260.0,
        }

        validated_position = validate_model_data(PositionValidation, position_update)
        assert validated_position.size == Decimal("500.0")

        # Trade record
        trade_record = {
            "order_id": "ord_2024_001",
            "token_id": "tok_market_yes_001",
            "market_slug": "presidential-election-2024",
            "side": "BUY",
            "price": 0.52,
            "size": 500.0,
            "notional_value": 260.0,
            "outcome_type": "YES",
        }

        validated_trade = validate_model_data(TradeValidation, trade_record)
        assert validated_trade.notional_value == Decimal("260.0")

    def test_error_recovery_scenarios(self):
        """Test validation error handling and recovery."""
        # Simulate data corruption scenarios
        corrupted_orders = [
            {"id": "ord_1", "price": -0.5},  # Negative price
            {"id": "ord_2", "size": 0},  # Zero size
            {"id": "ord_3", "side": "MAYBE"},  # Invalid side
        ]

        batch = ValidationBatch(OrderValidation)

        for order in corrupted_orders:
            # Fill in minimum required fields
            order.update(
                {
                    "token_id": "token_test",
                    "side": order.get("side", "BUY"),
                    "price": order.get("price", 0.5),
                    "size": order.get("size", 100.0),
                    "status": "OPEN",
                }
            )

            result = batch.validate_item(order, order["id"])
            assert result == False  # Should fail validation

        assert len(batch.errors) == 3  # All orders should have failed


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
