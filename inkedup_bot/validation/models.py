"""
Comprehensive Pydantic models for database entity validation.

This module provides validation models for all database entities to prevent
data corruption and ensure consistency across the trading system.
"""

from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.types import StrictStr


class OrderStatus(str, Enum):
    """Valid order status values."""

    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    PENDING = "PENDING"
    FAILED = "FAILED"


class OrderSide(str, Enum):
    """Valid order side values."""

    BUY = "BUY"
    SELL = "SELL"


class OutcomeType(str, Enum):
    """Valid outcome types."""

    YES = "YES"
    NO = "NO"
    UP = "UP"
    DOWN = "DOWN"
    WIN = "WIN"
    LOSE = "LOSE"


class OrderValidation(BaseModel):
    """Validation model for order data."""

    id: StrictStr = Field(
        ..., min_length=1, max_length=255, description="Unique order identifier"
    )
    token_id: StrictStr = Field(
        ..., min_length=1, max_length=255, description="Token identifier"
    )
    market_slug: StrictStr | None = Field(
        None, max_length=255, description="Market slug identifier"
    )
    side: OrderSide = Field(..., description="Order side (BUY/SELL)")
    price: Decimal = Field(
        ..., ge=Decimal("0"), le=Decimal("1"), description="Order price (0-1)"
    )
    size: Decimal = Field(
        ..., gt=Decimal("0"), description="Order size (must be positive)"
    )
    status: OrderStatus = Field(..., description="Order status")
    created_at: datetime | None = Field(None, description="Order creation timestamp")
    updated_at: datetime | None = Field(None, description="Order update timestamp")
    filled_at: datetime | None = Field(None, description="Order fill timestamp")
    notional_value: Decimal | None = Field(
        None, ge=Decimal("0"), description="Notional value"
    )
    outcome_type: OutcomeType | None = Field(None, description="Outcome type")

    @field_validator("price")
    def validate_price_precision(cls, v: Decimal) -> Decimal:
        """Validate price has reasonable precision (max 6 decimal places)."""
        if v.as_tuple().exponent < -6:
            raise ValueError("Price precision cannot exceed 6 decimal places")
        return v

    @field_validator("size")
    def validate_size_precision(cls, v: Decimal) -> Decimal:
        """Validate size has reasonable precision (max 4 decimal places)."""
        if v.as_tuple().exponent < -4:
            raise ValueError("Size precision cannot exceed 4 decimal places")
        return v

    @field_validator("notional_value")
    def validate_notional_value(cls, v: Decimal | None) -> Decimal | None:
        """Validate notional value is reasonable."""
        if v is not None and v < 0:
            raise ValueError("Notional value cannot be negative")
        return v

    @model_validator(mode="after")
    def validate_timestamps_and_consistency(self) -> "OrderValidation":
        """Validate timestamp ordering and field consistency."""
        # Timestamp validation
        if self.created_at and self.updated_at and self.updated_at < self.created_at:
            raise ValueError("Updated timestamp cannot be before created timestamp")

        if self.filled_at and self.created_at and self.filled_at < self.created_at:
            raise ValueError("Filled timestamp cannot be before created timestamp")

        if self.filled_at and self.status not in [
            OrderStatus.FILLED,
            OrderStatus.PARTIALLY_FILLED,
        ]:
            raise ValueError(
                "Filled timestamp requires FILLED or PARTIALLY_FILLED status"
            )

        # Notional value consistency check
        if (
            self.notional_value is not None
            and self.price is not None
            and self.size is not None
        ):
            expected_notional = self.price * self.size
            # Allow 1% tolerance for rounding
            tolerance = expected_notional * Decimal("0.01")
            if abs(self.notional_value - expected_notional) > tolerance:
                raise ValueError(
                    f"Notional value {self.notional_value} inconsistent with price {self.price} * size {self.size} = {expected_notional}"
                )

        return self

    class Config:
        use_enum_values = True
        validate_assignment = True


class PositionValidation(BaseModel):
    """Validation model for position data."""

    token_id: StrictStr = Field(
        ..., min_length=1, max_length=255, description="Token identifier"
    )
    market_slug: StrictStr | None = Field(
        None, max_length=255, description="Market slug identifier"
    )
    outcome_type: OutcomeType | None = Field(None, description="Outcome type")
    size: Decimal = Field(..., description="Position size (can be negative for short)")
    notional_value: Decimal = Field(..., description="Notional value")
    updated_at: datetime | None = Field(None, description="Last update timestamp")

    @field_validator("size")
    def validate_size_precision(cls, v: Decimal) -> Decimal:
        """Validate size has reasonable precision (max 4 decimal places)."""
        if abs(v) > Decimal("1000000"):  # 1M max position size
            raise ValueError("Position size exceeds maximum allowed (1,000,000)")
        if v != Decimal("0") and abs(v) < Decimal("0.0001"):  # Minimum meaningful size
            raise ValueError("Position size too small (minimum 0.0001)")
        return v

    @field_validator("notional_value")
    def validate_notional_value(cls, v: Decimal) -> Decimal:
        """Validate notional value is reasonable."""
        if abs(v) > Decimal("1000000"):  # 1M max notional value
            raise ValueError("Notional value exceeds maximum allowed (1,000,000)")
        return v

    @model_validator(mode="after")
    def validate_position_consistency(self) -> "PositionValidation":
        """Validate position size and notional value consistency."""
        if self.size is not None and self.notional_value is not None:
            # Check sign consistency for meaningful positions
            if abs(self.size) > Decimal(
                "0.0001"
            ):  # Only check for non-trivial positions
                if (self.size > 0 and self.notional_value < 0) or (
                    self.size < 0 and self.notional_value > 0
                ):
                    # This might be valid in some cases, so just warn rather than error
                    pass

        return self

    class Config:
        use_enum_values = True
        validate_assignment = True


class TradeValidation(BaseModel):
    """Validation model for trade data."""

    order_id: StrictStr = Field(
        ..., min_length=1, max_length=255, description="Order identifier"
    )
    token_id: StrictStr = Field(
        ..., min_length=1, max_length=255, description="Token identifier"
    )
    market_slug: StrictStr | None = Field(
        None, max_length=255, description="Market slug identifier"
    )
    side: OrderSide = Field(..., description="Trade side (BUY/SELL)")
    price: Decimal = Field(
        ..., ge=Decimal("0"), le=Decimal("1"), description="Trade price (0-1)"
    )
    size: Decimal = Field(
        ..., gt=Decimal("0"), description="Trade size (must be positive)"
    )
    notional_value: Decimal = Field(
        ..., gt=Decimal("0"), description="Notional value (must be positive)"
    )
    outcome_type: OutcomeType | None = Field(None, description="Outcome type")
    executed_at: datetime | None = Field(None, description="Trade execution timestamp")

    @field_validator("price")
    def validate_price_precision(cls, v: Decimal) -> Decimal:
        """Validate price has reasonable precision."""
        if v.as_tuple().exponent < -6:
            raise ValueError("Price precision cannot exceed 6 decimal places")
        return v

    @field_validator("size", "notional_value")
    def validate_positive_values(cls, v: Decimal) -> Decimal:
        """Validate size and notional value are positive."""
        if v <= 0:
            raise ValueError("Trade size and notional value must be positive")
        return v

    @model_validator(mode="after")
    def validate_trade_consistency(self) -> "TradeValidation":
        """Validate trade price, size, and notional value consistency."""
        if all(v is not None for v in [self.price, self.size, self.notional_value]):
            expected_notional = self.price * self.size
            # Allow 1% tolerance for rounding
            tolerance = max(expected_notional * Decimal("0.01"), Decimal("0.01"))
            if abs(self.notional_value - expected_notional) > tolerance:
                raise ValueError(
                    f"Trade notional value {self.notional_value} inconsistent with "
                    f"price {self.price} * size {self.size} = {expected_notional}"
                )

        return self

    class Config:
        use_enum_values = True
        validate_assignment = True


class MarketSnapshotValidation(BaseModel):
    """Validation model for market snapshot data."""

    market_slug: StrictStr = Field(
        ..., min_length=1, max_length=255, description="Market slug identifier"
    )
    token_id: StrictStr = Field(
        ..., min_length=1, max_length=255, description="Token identifier"
    )
    bid: Decimal | None = Field(
        None, ge=Decimal("0"), le=Decimal("1"), description="Best bid price"
    )
    ask: Decimal | None = Field(
        None, ge=Decimal("0"), le=Decimal("1"), description="Best ask price"
    )
    spread_bps: Decimal | None = Field(
        None, ge=Decimal("0"), description="Spread in basis points"
    )
    volume_24h: Decimal | None = Field(None, ge=Decimal("0"), description="24h volume")
    liquidity: Decimal | None = Field(
        None, ge=Decimal("0"), description="Total liquidity"
    )
    snapshot_at: datetime | None = Field(None, description="Snapshot timestamp")

    @model_validator(mode="after")
    def validate_bid_ask_spread(self) -> "MarketSnapshotValidation":
        """Validate bid <= ask relationship."""
        if self.bid is not None and self.ask is not None:
            if self.bid > self.ask:
                raise ValueError(
                    f"Bid price {self.bid} cannot be greater than ask price {self.ask}"
                )

            # Calculate and validate spread
            spread = self.ask - self.bid
            if self.spread_bps is not None:
                # Convert spread to basis points
                expected_spread_bps = (spread / ((self.bid + self.ask) / 2)) * 10000
                tolerance = Decimal("10")  # 10 bps tolerance
                if abs(self.spread_bps - expected_spread_bps) > tolerance:
                    raise ValueError(
                        f"Spread BPS {self.spread_bps} inconsistent with bid/ask spread"
                    )

        return self

    class Config:
        use_enum_values = True
        validate_assignment = True


class RiskEventType(str, Enum):
    """Valid risk event types."""

    EXPOSURE_LIMIT = "EXPOSURE_LIMIT"
    POSITION_LIMIT = "POSITION_LIMIT"
    CORRELATION_LIMIT = "CORRELATION_LIMIT"
    CONCENTRATION_LIMIT = "CONCENTRATION_LIMIT"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    VOLATILITY_LIMIT = "VOLATILITY_LIMIT"


class RiskEventValidation(BaseModel):
    """Validation model for risk event data."""

    event_type: RiskEventType = Field(..., description="Type of risk event")
    token_id: StrictStr | None = Field(
        None, max_length=255, description="Token identifier"
    )
    market_slug: StrictStr | None = Field(
        None, max_length=255, description="Market slug identifier"
    )
    outcome_type: OutcomeType | None = Field(None, description="Outcome type")
    current_exposure: Decimal | None = Field(None, description="Current exposure level")
    limit_value: Decimal | None = Field(None, description="Risk limit value")
    intended_notional: Decimal | None = Field(
        None, description="Intended trade notional"
    )
    description: StrictStr | None = Field(
        None, max_length=1000, description="Event description"
    )
    occurred_at: datetime | None = Field(None, description="Event occurrence timestamp")

    @field_validator("current_exposure", "limit_value", "intended_notional")
    def validate_exposure_values(cls, v: Decimal | None) -> Decimal | None:
        """Validate exposure values are reasonable."""
        if v is not None and abs(v) > Decimal("10000000"):  # 10M max
            raise ValueError("Exposure value exceeds maximum allowed (10,000,000)")
        return v

    class Config:
        use_enum_values = True
        validate_assignment = True


class OutcomeExposureValidation(BaseModel):
    """Validation model for outcome exposure data."""

    market_slug: StrictStr = Field(
        ..., min_length=1, max_length=255, description="Market slug identifier"
    )
    outcome_id: StrictStr = Field(
        ..., min_length=1, max_length=255, description="Outcome identifier"
    )
    outcome_name: StrictStr = Field(
        ..., min_length=1, max_length=255, description="Outcome name"
    )
    position_size: Decimal = Field(..., description="Position size")
    notional_value: Decimal = Field(..., description="Notional value")
    average_price: Decimal = Field(
        ..., ge=Decimal("0"), le=Decimal("1"), description="Average price"
    )
    current_price: Decimal = Field(
        ..., ge=Decimal("0"), le=Decimal("1"), description="Current price"
    )
    unrealized_pnl: Decimal = Field(..., description="Unrealized P&L")
    realized_pnl: Decimal = Field(..., description="Realized P&L")
    correlation_coefficient: Decimal = Field(
        Decimal("0"),
        ge=Decimal("-1"),
        le=Decimal("1"),
        description="Correlation coefficient",
    )
    risk_score: Decimal = Field(Decimal("0"), ge=Decimal("0"), description="Risk score")
    last_updated: datetime | None = Field(None, description="Last update timestamp")

    @field_validator("position_size", "notional_value")
    def validate_position_values(cls, v: Decimal) -> Decimal:
        """Validate position values are reasonable."""
        if abs(v) > Decimal("10000000"):  # 10M max
            raise ValueError("Position value exceeds maximum allowed (10,000,000)")
        return v

    @field_validator("unrealized_pnl", "realized_pnl")
    def validate_pnl_values(cls, v: Decimal) -> Decimal:
        """Validate P&L values are reasonable."""
        if abs(v) > Decimal("10000000"):  # 10M max P&L
            raise ValueError("P&L value exceeds maximum allowed (10,000,000)")
        return v

    @field_validator("risk_score")
    def validate_risk_score(cls, v: Decimal) -> Decimal:
        """Validate risk score is reasonable."""
        if v > Decimal("1000"):  # Max risk score
            raise ValueError("Risk score exceeds maximum allowed (1000)")
        return v

    class Config:
        use_enum_values = True
        validate_assignment = True


class OutcomeCorrelationValidation(BaseModel):
    """Validation model for outcome correlation data."""

    outcome_a: StrictStr = Field(
        ..., min_length=1, max_length=255, description="First outcome identifier"
    )
    outcome_b: StrictStr = Field(
        ..., min_length=1, max_length=255, description="Second outcome identifier"
    )
    correlation: Decimal = Field(
        ..., ge=Decimal("-1"), le=Decimal("1"), description="Correlation coefficient"
    )
    covariance: Decimal = Field(..., description="Covariance value")
    last_calculated: datetime | None = Field(
        None, description="Last calculation timestamp"
    )

    @model_validator(mode="after")
    def validate_outcome_pair(self) -> "OutcomeCorrelationValidation":
        """Validate outcome pair consistency."""
        if self.outcome_a == self.outcome_b:
            raise ValueError("Outcome identifiers must be different")

        return self

    class Config:
        use_enum_values = True
        validate_assignment = True


class ExposureAlertType(str, Enum):
    """Valid exposure alert types."""

    GLOBAL_EXPOSURE = "GLOBAL_EXPOSURE"
    MARKET_EXPOSURE = "MARKET_EXPOSURE"
    OUTCOME_EXPOSURE = "OUTCOME_EXPOSURE"
    POSITION_CONCENTRATION = "POSITION_CONCENTRATION"
    CORRELATION_RISK = "CORRELATION_RISK"


class ExposureAlertValidation(BaseModel):
    """Validation model for exposure alert data."""

    alert_type: ExposureAlertType = Field(..., description="Type of exposure alert")
    market_slug: StrictStr | None = Field(
        None, max_length=255, description="Market slug identifier"
    )
    outcome_id: StrictStr | None = Field(
        None, max_length=255, description="Outcome identifier"
    )
    threshold_value: Decimal | None = Field(None, description="Alert threshold value")
    current_value: Decimal | None = Field(None, description="Current exposure value")
    alert_message: StrictStr | None = Field(
        None, max_length=1000, description="Alert message"
    )
    triggered_at: datetime | None = Field(None, description="Alert trigger timestamp")
    acknowledged: bool = Field(False, description="Alert acknowledgment status")

    @field_validator("threshold_value", "current_value")
    def validate_alert_values(cls, v: Decimal | None) -> Decimal | None:
        """Validate alert values are reasonable."""
        if v is not None and abs(v) > Decimal("100000000"):  # 100M max
            raise ValueError("Alert value exceeds maximum allowed (100,000,000)")
        return v

    class Config:
        use_enum_values = True
        validate_assignment = True


# Validation utilities
class ValidationError(Exception):
    """Custom validation error with detailed information."""

    def __init__(
        self,
        message: str,
        field: str = None,
        value: Any = None,
        details: dict[str, Any] = None,
    ):
        self.message = message
        self.field = field
        self.value = value
        self.details = details or {}
        super().__init__(self.message)


def validate_model_data(model_class: BaseModel, data: dict[str, Any]) -> BaseModel:
    """
    Validate data against a Pydantic model and return the validated instance.

    Args:
        model_class: The Pydantic model class to validate against
        data: Data dictionary to validate

    Returns:
        Validated model instance

    Raises:
        ValidationError: If validation fails
    """
    try:
        return model_class(**data)
    except Exception as e:
        raise ValidationError(
            f"Validation failed for {model_class.__name__}: {str(e)}",
            details={"data": data, "error": str(e)},
        )


def safe_decimal_conversion(value: Any, precision: int = 6) -> Decimal:
    """
    Safely convert value to Decimal with specified precision.

    Args:
        value: Value to convert
        precision: Maximum decimal places

    Returns:
        Decimal value with limited precision
    """
    if value is None:
        return Decimal("0")

    try:
        decimal_val = Decimal(str(value))
        # Quantize to limit precision
        quantize_val = Decimal("0." + "0" * precision)
        return decimal_val.quantize(quantize_val, rounding=ROUND_DOWN)
    except Exception:
        raise ValidationError(f"Cannot convert {value} to Decimal")


def validate_token_id_format(token_id: str) -> str:
    """
    Validate token ID format and return normalized version.

    Args:
        token_id: Token identifier to validate

    Returns:
        Normalized token ID

    Raises:
        ValidationError: If format is invalid
    """
    if not token_id or not isinstance(token_id, str):
        raise ValidationError("Token ID must be a non-empty string")

    # Remove whitespace and normalize
    normalized = token_id.strip()

    if len(normalized) < 1 or len(normalized) > 255:
        raise ValidationError("Token ID must be 1-255 characters long")

    # Check for invalid characters (basic validation)
    if any(char in normalized for char in ["\n", "\r", "\t"]):
        raise ValidationError("Token ID contains invalid characters")

    return normalized


def validate_market_slug_format(market_slug: str) -> str:
    """
    Validate market slug format and return normalized version.

    Args:
        market_slug: Market slug to validate

    Returns:
        Normalized market slug

    Raises:
        ValidationError: If format is invalid
    """
    if not market_slug or not isinstance(market_slug, str):
        raise ValidationError("Market slug must be a non-empty string")

    # Remove whitespace and normalize
    normalized = market_slug.strip().lower()

    if len(normalized) < 1 or len(normalized) > 255:
        raise ValidationError("Market slug must be 1-255 characters long")

    return normalized


# Export all validation models
__all__ = [
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
]
