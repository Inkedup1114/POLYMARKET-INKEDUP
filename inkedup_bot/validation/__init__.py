"""
Validation package for state management and database operations.

This package provides comprehensive validation for all state updates and database
operations to prevent data corruption and ensure consistency.
"""

from .decorators import (
    ValidationBatch,
    ValidationContext,
    batch_validate,
    default_validation_context,
    get_validation_context,
    safe_database_operation,
    set_validation_context,
    validate_database_write,
    validate_input,
    validate_order_data,
    validate_output,
    validate_position_data,
    validate_state_update,
    validate_trade_data,
)
from .models import (
    ExposureAlertType,
    ExposureAlertValidation,
    MarketSnapshotValidation,
    OrderSide,
    OrderStatus,
    OrderValidation,
    OutcomeCorrelationValidation,
    OutcomeExposureValidation,
    OutcomeType,
    PositionValidation,
    RiskEventType,
    RiskEventValidation,
    TradeValidation,
    ValidationError,
    safe_decimal_conversion,
    validate_market_slug_format,
    validate_model_data,
    validate_token_id_format,
)

__all__ = [
    # Models
    "OrderValidation",
    "PositionValidation",
    "TradeValidation",
    "MarketSnapshotValidation",
    "RiskEventValidation",
    "OutcomeExposureValidation",
    "OutcomeCorrelationValidation",
    "ExposureAlertValidation",
    "OrderStatus",
    "OrderSide",
    "OutcomeType",
    "RiskEventType",
    "ExposureAlertType",
    "ValidationError",
    "validate_model_data",
    "safe_decimal_conversion",
    "validate_token_id_format",
    "validate_market_slug_format",
    # Decorators and utilities
    "validate_input",
    "validate_output",
    "validate_order_data",
    "validate_position_data",
    "validate_trade_data",
    "validate_database_write",
    "safe_database_operation",
    "validate_state_update",
    "batch_validate",
    "ValidationBatch",
    "ValidationContext",
    "set_validation_context",
    "get_validation_context",
    "default_validation_context",
]
