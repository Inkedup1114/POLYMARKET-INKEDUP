from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Any, Optional
import asyncio

from .config import BotConfig
from .state import StateManager
from .risk.validators import (
    ValidationContext,
    ValidationPipeline,
    create_notional_validator,
    create_token_validator,
    create_market_validator,
    create_position_limit_validator,
    create_global_limit_validator,
    ValidationError,
    ValidationSeverity,
)

if TYPE_CHECKING:
    from .order_client import OrderClient


log = logging.getLogger("risk")


class RiskManager:
    """
    Enhanced risk management with per-market and per-outcome exposure limits.
    Supports global, position, market, and outcome-level risk controls.
    """

    def __init__(
        self, cfg: BotConfig, order_client: OrderClient, state: StateManager
    ) -> None:
        self.cfg = cfg
        self.order_client = order_client
        self.state = state
        
        # Initialize validation framework
        self.validation_context = ValidationContext(config=self.cfg.risk)
        self.validation_pipeline = self._create_validation_pipeline()
        
        # Centralized readiness check
        if not self.order_client.ready():
            raise RuntimeError("Order client not ready at startup")

    def _create_validation_pipeline(self) -> ValidationPipeline:
        """Create validation pipeline with configured validators."""
        validators = [
            create_token_validator("token_id"),
            create_notional_validator(
                "intended_notional",
                min_value=0.01,  # Minimum trade size
                max_value=self.cfg.risk.get('max_trade_size')
            ),
            create_market_validator("market_slug"),
            create_position_limit_validator("position_size"),
            create_global_limit_validator("global_exposure"),
        ]
        return ValidationPipeline(validators)

    async def preflight(
        self,
        token_id: str,
        intended_notional: float,
        market_slug: str | None = None,
        outcome_type: str | None = None,
    ) -> bool:
        """
        Enhanced preflight check using the new validation framework.
        Maintains backward compatibility with existing error handling.
        """
        # Build validation parameters
        validation_params = {
            "token_id": token_id,
            "intended_notional": intended_notional,
            "market_slug": market_slug,
            "position_size": self.state.get_position_notional(token_id) + intended_notional,
            "global_exposure": self.state.get_total_exposure() + intended_notional,
        }

        # Run validation pipeline
        validation_result = await self.validation_pipeline.validate_all(
            validation_params,
            self.validation_context
        )

        if not validation_result.is_valid:
            # Convert validation errors to appropriate exceptions for backward compatibility
            critical_errors = [
                error for error in validation_result.errors
                if error.severity in [ValidationSeverity.HIGH, ValidationSeverity.CRITICAL]
            ]
            
            if critical_errors:
                error_messages = [f"{error.field}: {error.message}" for error in critical_errors]
                raise RuntimeError(f"Validation failed: {'; '.join(error_messages)}")
            
            # Log warnings
            for warning in validation_result.warnings:
                log.warning(f"Validation warning: {warning.field} - {warning.message}")

        # Legacy validation checks (for backward compatibility)
        return self._legacy_preflight_check(
            token_id, intended_notional, market_slug, outcome_type
        )

    def _legacy_preflight_check(
        self,
        token_id: str,
        intended_notional: float,
        market_slug: str | None = None,
        outcome_type: str | None = None,
    ) -> bool:
        """Legacy preflight check for backward compatibility."""
        # Basic input validation
        if intended_notional <= 0:
            raise ValueError("Intended notional must be positive")

        # Global exposure check
        total = self.state.get_total_exposure()
        if (
            self.cfg.global_risk_cap
            and total + intended_notional > self.cfg.global_risk_cap
        ):
            raise RuntimeError(
                f"Global cap exceeded ({total + intended_notional:.2f} > {self.cfg.global_risk_cap})"
            )

        # Per-position risk check
        current_notional = self.state.get_position_notional(token_id)
        new_notional = current_notional + intended_notional
        if self.cfg.position_risk_cap and new_notional > self.cfg.position_risk_cap:
            raise RuntimeError(
                f"Per-position cap exceeded ({new_notional:.2f} > {self.cfg.position_risk_cap})"
            )

        # Per-market risk check
        if market_slug and self.cfg.per_market_risk_cap:
            current_market_exposure = self.state.get_market_exposure(market_slug)
            new_market_exposure = current_market_exposure + intended_notional
            if new_market_exposure > self.cfg.per_market_risk_cap:
                raise RuntimeError(
                    f"Per-market cap exceeded for {market_slug} ({new_market_exposure:.2f} > {self.cfg.per_market_risk_cap})"
                )

        # Per-outcome risk check
        if outcome_type and self.cfg.per_outcome_risk_cap:
            current_outcome_exposure = self.state.get_outcome_exposure(outcome_type)
            new_outcome_exposure = current_outcome_exposure + intended_notional
            if new_outcome_exposure > self.cfg.per_outcome_risk_cap:
                raise RuntimeError(
                    f"Per-outcome cap exceeded for {outcome_type} ({new_outcome_exposure:.2f} > {self.cfg.per_outcome_risk_cap})"
                )

        return True

    async def validate_parameters(
        self,
        token_id: str,
        intended_notional: float,
        market_slug: str | None = None,
        outcome_type: str | None = None,
    ) -> Dict[str, Any]:
        """
        New method for detailed parameter validation.
        Returns validation results with detailed error information.
        """
        validation_params = {
            "token_id": token_id,
            "intended_notional": intended_notional,
            "market_slug": market_slug,
            "position_size": self.state.get_position_notional(token_id) + intended_notional,
            "global_exposure": self.state.get_total_exposure() + intended_notional,
        }

        validation_result = await self.validation_pipeline.validate_all(
            validation_params,
            self.validation_context
        )

        return {
            "is_valid": validation_result.is_valid,
            "errors": [
                {
                    "field": error.field,
                    "message": error.message,
                    "severity": error.severity.value,
                    "category": error.category.value,
                    "value": error.value,
                    "expected": error.expected,
                }
                for error in validation_result.errors
            ],
            "warnings": [
                {
                    "field": warning.field,
                    "message": warning.message,
                    "severity": warning.severity.value,
                    "category": warning.category.value,
                }
                for warning in validation_result.warnings
            ],
            "metadata": validation_result.metadata,
        }

    def record_trade(
        self,
        token_id: str,
        notional: float,
        market_slug: str | None = None,
        outcome_type: str | None = None,
    ) -> None:
        """
        Records a completed trade and updates exposure tracking.
        Should be called after successful order execution.
        """
        # Update position tracking
        position_data = {
            "token_id": token_id,
            "notional_value": self.state.positions.get(token_id, {}).get(
                "notional_value", 0
            )
            + notional,
            "market_slug": market_slug,
            "outcome_type": outcome_type,
        }
        self.state.update_position(position_data)

        # Update market exposure if provided
        if market_slug:
            self.state.update_market_exposure(market_slug, notional)

        # Update outcome exposure if provided
        if outcome_type:
            self.state.update_outcome_exposure(outcome_type, notional)

        log.info(
            f"Trade recorded: {token_id} notional={notional:.2f}, market={market_slug}, outcome={outcome_type}"
        )

    def update_market_data(self, market_data: Dict[str, Any]) -> None:
        """
        Update market data in validation context.
        This allows validators to access current market information.
        """
        self.validation_context.update_market_data(market_data)
        log.info(f"Updated market data for {len(market_data)} markets")

    def get_validation_config(self) -> Dict[str, Any]:
        """Get current validation configuration."""
        return {
            "risk_caps": {
                "global": self.cfg.global_risk_cap,
                "position": self.cfg.position_risk_cap,
                "market": self.cfg.per_market_risk_cap,
                "outcome": self.cfg.per_outcome_risk_cap,
            },
            "validation_enabled": True,
            "legacy_mode": False,  # Set to True to use only legacy validation
        }
