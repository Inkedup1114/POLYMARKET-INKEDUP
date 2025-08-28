"""
Pydantic models for risk management configuration validation.

This module provides comprehensive validation for all risk parameters
used throughout the trading system, ensuring configuration integrity
before system initialization.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class GlobalRiskConfig(BaseModel):
    """Global risk management configuration with validation."""

    global_risk_cap: float = Field(
        ge=0,
        description="Maximum total exposure across all positions (USD)",
        examples=[10000.0, 50000.0],
    )
    position_risk_cap: float = Field(
        ge=0,
        description="Maximum exposure per individual position (USD)",
        examples=[1000.0, 5000.0],
    )
    market_risk_cap: float = Field(
        ge=0,
        description="Legacy market risk cap (USD)",
        examples=[5000.0, 10000.0],
    )
    per_market_risk_cap: float = Field(
        ge=0,
        description="Maximum exposure per market (USD)",
        examples=[2000.0, 5000.0],
    )
    per_outcome_risk_cap: float = Field(
        ge=0,
        description="Maximum exposure per outcome type (USD)",
        examples=[1500.0, 3000.0],
    )
    max_position_size: float = Field(
        gt=0,
        description="Maximum size for any single position (USD)",
        examples=[1000.0, 5000.0],
    )
    max_order_size: float = Field(
        gt=0,
        description="Maximum size for any single order (USD)",
        examples=[100.0, 1000.0],
    )

    @field_validator("global_risk_cap", "market_risk_cap", "per_market_risk_cap")
    @classmethod
    def validate_positive_caps(cls, v: float) -> float:
        """Ensure risk caps are positive when set."""
        if v < 0:
            raise ValueError("Risk caps must be non-negative")
        return v

    @model_validator(mode="after")
    def validate_risk_hierarchy(self) -> GlobalRiskConfig:
        """Validate that risk caps follow logical hierarchy."""
        errors = []

        # Position cap should be <= global cap (if both set)
        if (
            self.global_risk_cap > 0
            and self.position_risk_cap > 0
            and self.position_risk_cap > self.global_risk_cap
        ):
            errors.append(
                "position_risk_cap cannot exceed global_risk_cap "
                f"({self.position_risk_cap} > {self.global_risk_cap})"
            )

        # Market cap should be <= global cap (if both set)
        if (
            self.global_risk_cap > 0
            and self.per_market_risk_cap > 0
            and self.per_market_risk_cap > self.global_risk_cap
        ):
            errors.append(
                "per_market_risk_cap cannot exceed global_risk_cap "
                f"({self.per_market_risk_cap} > {self.global_risk_cap})"
            )

        # Outcome cap should be <= global cap (if both set)
        if (
            self.global_risk_cap > 0
            and self.per_outcome_risk_cap > 0
            and self.per_outcome_risk_cap > self.global_risk_cap
        ):
            errors.append(
                "per_outcome_risk_cap cannot exceed global_risk_cap "
                f"({self.per_outcome_risk_cap} > {self.global_risk_cap})"
            )

        # Order size should be <= position cap
        if self.max_order_size > self.max_position_size:
            errors.append(
                "max_order_size cannot exceed max_position_size "
                f"({self.max_order_size} > {self.max_position_size})"
            )

        if errors:
            raise ValueError("; ".join(errors))

        return self


class MarketConditionConfig(BaseModel):
    """Market condition-based validation configuration."""

    volatility_threshold: float = Field(
        default=0.15,
        gt=0,
        le=1.0,
        description="Volatility threshold for risk adjustments (0-1)",
        examples=[0.10, 0.15, 0.25],
    )
    volatility_adjustment_factor: float = Field(
        default=1.0,
        ge=0,
        le=5.0,
        description="Factor for volatility-based risk adjustment (0-5)",
        examples=[1.0, 1.5, 2.0],
    )
    liquidity_ratio_threshold: float = Field(
        default=0.1,
        gt=0,
        le=1.0,
        description="Minimum liquidity ratio for position sizing (0-1)",
        examples=[0.05, 0.1, 0.2],
    )
    correlation_threshold: float = Field(
        default=0.7,
        ge=0,
        le=1.0,
        description="Correlation threshold for risk assessment (0-1)",
        examples=[0.5, 0.7, 0.8],
    )
    max_correlated_exposure: float = Field(
        default=0.3,
        gt=0,
        le=1.0,
        description="Maximum allowed correlated exposure ratio (0-1)",
        examples=[0.2, 0.3, 0.4],
    )
    market_status_required: bool = Field(
        default=True,
        description="Whether to require active market status for trading",
    )

    @field_validator("volatility_threshold", "liquidity_ratio_threshold")
    @classmethod
    def validate_thresholds(cls, v: float) -> float:
        """Validate threshold values are in valid ranges."""
        if not 0 < v <= 1.0:
            raise ValueError("Threshold must be between 0 and 1")
        return v

    @field_validator("correlation_threshold", "max_correlated_exposure")
    @classmethod
    def validate_correlation_params(cls, v: float) -> float:
        """Validate correlation parameters are in valid ranges."""
        if not 0 <= v <= 1.0:
            raise ValueError("Correlation parameters must be between 0 and 1")
        return v


class OrderExecutionConfig(BaseModel):
    """Order execution risk parameters."""

    slippage_tolerance_bps: int = Field(
        default=50,
        ge=0,
        le=10000,
        description="Maximum allowed slippage in basis points (0-10000)",
        examples=[25, 50, 100],
    )
    order_timeout_seconds: int = Field(
        default=30,
        gt=0,
        le=3600,
        description="Order timeout in seconds (1-3600)",
        examples=[15, 30, 60],
    )
    price_precision: int = Field(
        default=4,
        ge=1,
        le=18,
        description="Decimal precision for prices (1-18)",
        examples=[2, 4, 6],
    )
    size_precision: int = Field(
        default=4,
        ge=1,
        le=18,
        description="Decimal precision for sizes (1-18)",
        examples=[2, 4, 6],
    )
    default_order_type: str = Field(
        default="GTC",
        pattern=r"^(GTC|IOC|FOK)$",
        description="Default order type (GTC, IOC, or FOK)",
    )

    @field_validator("slippage_tolerance_bps")
    @classmethod
    def validate_slippage(cls, v: int) -> int:
        """Validate slippage tolerance is reasonable."""
        if v > 1000:  # 10% slippage warning
            raise ValueError(
                f"Slippage tolerance {v} bps is very high (>10%). "
                "Consider using a lower value."
            )
        return v


class StrategyRiskConfig(BaseModel):
    """Strategy-specific risk configuration."""

    complement_arb_min_deviation: float = Field(
        default=0.01,
        gt=0,
        le=0.5,
        description="Minimum deviation for complement arbitrage (0-0.5)",
        examples=[0.005, 0.01, 0.02],
    )
    complement_arb_max_deviation: float = Field(
        default=0.20,
        gt=0,
        le=1.0,
        description="Maximum deviation for complement arbitrage (0-1)",
        examples=[0.15, 0.20, 0.30],
    )
    complement_arb_base_size: float = Field(
        default=10.0,
        gt=0,
        description="Base size for complement arbitrage trades (USD)",
        examples=[5.0, 10.0, 25.0],
    )
    complement_arb_max_size: float = Field(
        default=100.0,
        gt=0,
        description="Maximum size for complement arbitrage trades (USD)",
        examples=[50.0, 100.0, 250.0],
    )
    complement_arb_size_scaling: float = Field(
        default=50.0,
        gt=0,
        description="Size scaling factor for complement arbitrage",
        examples=[25.0, 50.0, 100.0],
    )

    @model_validator(mode="after")
    def validate_deviation_range(self) -> StrategyRiskConfig:
        """Validate deviation parameters are in correct order."""
        if self.complement_arb_min_deviation >= self.complement_arb_max_deviation:
            raise ValueError(
                "complement_arb_min_deviation must be less than complement_arb_max_deviation "
                f"({self.complement_arb_min_deviation} >= {self.complement_arb_max_deviation})"
            )
        return self

    @model_validator(mode="after")
    def validate_size_range(self) -> StrategyRiskConfig:
        """Validate size parameters are in correct order."""
        if self.complement_arb_base_size > self.complement_arb_max_size:
            raise ValueError(
                "complement_arb_base_size must be <= complement_arb_max_size "
                f"({self.complement_arb_base_size} > {self.complement_arb_max_size})"
            )
        return self


class RiskManagementConfig(BaseModel):
    """Complete risk management configuration with all sub-configurations."""

    global_risk: GlobalRiskConfig
    market_conditions: MarketConditionConfig = Field(
        default_factory=MarketConditionConfig
    )
    order_execution: OrderExecutionConfig = Field(default_factory=OrderExecutionConfig)
    strategy_risk: StrategyRiskConfig = Field(default_factory=StrategyRiskConfig)
    validation_enabled: bool = Field(
        default=True,
        description="Whether risk validation is enabled",
    )
    strict_mode: bool = Field(
        default=False,
        description="Whether to use strict validation (fail on warnings)",
    )

    @classmethod
    def from_bot_config(cls, bot_config: Any) -> RiskManagementConfig:
        """Create risk config from bot configuration object."""
        # Extract global risk parameters
        global_risk_data = {
            "global_risk_cap": getattr(bot_config, "global_risk_cap", 0.0),
            "position_risk_cap": getattr(bot_config, "position_risk_cap", 0.0),
            "market_risk_cap": getattr(bot_config, "market_risk_cap", 0.0),
            "per_market_risk_cap": getattr(bot_config, "per_market_risk_cap", 0.0),
            "per_outcome_risk_cap": getattr(bot_config, "per_outcome_risk_cap", 0.0),
            "max_position_size": getattr(bot_config, "max_position_size", 1000.0),
            "max_order_size": getattr(bot_config, "max_order_size", 100.0),
        }

        # Extract order execution parameters
        order_execution_data = {
            "slippage_tolerance_bps": getattr(bot_config, "slippage_tolerance_bps", 50),
            "order_timeout_seconds": getattr(bot_config, "order_timeout_seconds", 30),
            "price_precision": getattr(bot_config, "price_precision", 4),
            "size_precision": getattr(bot_config, "size_precision", 4),
            "default_order_type": getattr(bot_config, "default_order_type", "GTC"),
        }

        # Extract strategy risk parameters
        strategy_risk_data = {
            "complement_arb_min_deviation": getattr(
                bot_config, "complement_arb_min_deviation", 0.01
            ),
            "complement_arb_max_deviation": getattr(
                bot_config, "complement_arb_max_deviation", 0.20
            ),
            "complement_arb_base_size": getattr(
                bot_config, "complement_arb_base_size", 10.0
            ),
            "complement_arb_max_size": getattr(
                bot_config, "complement_arb_max_size", 100.0
            ),
            "complement_arb_size_scaling": getattr(
                bot_config, "complement_arb_size_scaling", 50.0
            ),
        }

        return cls(
            global_risk=GlobalRiskConfig(**global_risk_data),
            market_conditions=MarketConditionConfig(),
            order_execution=OrderExecutionConfig(**order_execution_data),
            strategy_risk=StrategyRiskConfig(**strategy_risk_data),
        )

    def validate_trading_parameters(
        self,
        token_id: str,
        intended_notional: float,
        market_slug: str | None = None,
        outcome_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Validate trading parameters against risk configuration.
        Returns validation result with errors and warnings.
        """
        errors = []
        warnings = []

        # Basic parameter validation
        if not token_id or not isinstance(token_id, str):
            errors.append("token_id must be a non-empty string")

        if intended_notional <= 0:
            errors.append("intended_notional must be positive")

        # Order size validation
        if intended_notional > self.global_risk.max_order_size:
            errors.append(
                f"Order size {intended_notional} exceeds max_order_size "
                f"{self.global_risk.max_order_size}"
            )

        # Position size validation
        if intended_notional > self.global_risk.max_position_size:
            errors.append(
                f"Position size {intended_notional} exceeds max_position_size "
                f"{self.global_risk.max_position_size}"
            )

        # Risk cap validations would be handled by the risk manager
        # using current exposure data

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "config_validated": True,
        }

    def get_risk_limits(self) -> dict[str, float]:
        """Get all risk limits as a dictionary for easy access."""
        return {
            "global_risk_cap": self.global_risk.global_risk_cap,
            "position_risk_cap": self.global_risk.position_risk_cap,
            "market_risk_cap": self.global_risk.market_risk_cap,
            "per_market_risk_cap": self.global_risk.per_market_risk_cap,
            "per_outcome_risk_cap": self.global_risk.per_outcome_risk_cap,
            "max_position_size": self.global_risk.max_position_size,
            "max_order_size": self.global_risk.max_order_size,
        }

    class Config:
        """Pydantic configuration."""

        extra = "forbid"  # Forbid extra fields
        validate_assignment = True  # Validate on assignment
        use_enum_values = True  # Use enum values in serialization
