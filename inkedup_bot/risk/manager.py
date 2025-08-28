from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError as PydanticValidationError

from ..config import BotConfig
from ..state import StateManager
from .alerts import AlertSeverity, RiskAlertManager
from .config import RiskManagementConfig
from .enhanced_position_validator import (
    EnhancedPositionValidator,
    PositionValidationResult,
)
from .exposure_analytics import ExposureHistoryTracker, ExposureSnapshot
from .exposure_calculator import ExposureCalculator
from .validators import ValidationContext

if TYPE_CHECKING:
    from ..order_client import OrderClient


log = logging.getLogger("risk")


class RiskSystemMode(Enum):
    """Operating modes for the risk system."""

    NORMAL = "normal"  # Full database functionality
    DEGRADED = "degraded"  # Fallback to in-memory cache
    EMERGENCY_HALT = "emergency_halt"  # All trading halted


class DatabaseFallbackCache:
    """
    In-memory cache for risk system fallback when database is unavailable.
    Maintains essential risk data to allow continued operation with degraded functionality.
    """

    def __init__(self):
        self.positions: dict[str, dict[str, Any]] = {}
        self.market_exposures: dict[str, float] = {}
        self.outcome_exposures: dict[str, float] = {}
        self.total_exposure: float = 0.0
        self.last_updated: float = time.time()
        self.cache_hits: int = 0
        self.cache_misses: int = 0

    def update_position(self, token_id: str, position_data: dict[str, Any]) -> None:
        """Update position in fallback cache."""
        old_notional = self.positions.get(token_id, {}).get("notional_value", 0.0)
        new_notional = position_data.get("notional_value", 0.0)

        self.positions[token_id] = position_data
        self.total_exposure += new_notional - old_notional
        self.last_updated = time.time()

        # Update market exposure if available
        market_slug = position_data.get("market_slug")
        if market_slug:
            self.market_exposures[market_slug] = self.market_exposures.get(
                market_slug, 0.0
            ) + (new_notional - old_notional)

        # Update outcome exposure if available
        outcome_type = position_data.get("outcome_type")
        if outcome_type:
            self.outcome_exposures[outcome_type] = self.outcome_exposures.get(
                outcome_type, 0.0
            ) + (new_notional - old_notional)

    def get_position_notional(self, token_id: str) -> float:
        """Get position notional from cache."""
        self.cache_hits += 1
        return self.positions.get(token_id, {}).get("notional_value", 0.0)

    def get_total_exposure(self) -> float:
        """Get total exposure from cache."""
        self.cache_hits += 1
        return self.total_exposure

    def get_market_exposure(self, market_slug: str) -> float:
        """Get market exposure from cache."""
        self.cache_hits += 1
        return self.market_exposures.get(market_slug, 0.0)

    def get_outcome_exposure(self, outcome_type: str) -> float:
        """Get outcome exposure from cache."""
        self.cache_hits += 1
        return self.outcome_exposures.get(outcome_type, 0.0)

    def clear(self) -> None:
        """Clear all cached data."""
        self.positions.clear()
        self.market_exposures.clear()
        self.outcome_exposures.clear()
        self.total_exposure = 0.0
        self.last_updated = time.time()

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics for monitoring."""
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "positions_count": len(self.positions),
            "markets_count": len(self.market_exposures),
            "outcomes_count": len(self.outcome_exposures),
            "total_exposure": self.total_exposure,
            "last_updated": self.last_updated,
            "age_seconds": time.time() - self.last_updated,
        }


class RiskManager:
    """
    Comprehensive risk management system for Polymarket trading operations.

    This class provides multi-layered risk controls and monitoring to protect against
    excessive exposure, concentration risk, and system failures. It integrates with
    the order client, state management, and alert systems to provide real-time
    risk assessment and automated position management.

    Risk Control Layers:
    1. **Global Exposure Limits**: Total portfolio exposure caps
    2. **Position Limits**: Per-position size and concentration controls
    3. **Market Limits**: Per-market exposure limits to prevent concentration
    4. **Outcome Limits**: Per-outcome type (YES/NO) exposure management
    5. **Correlation Controls**: Dynamic adjustments for correlated positions

    Operating Modes:
    - **NORMAL**: Full database functionality with complete risk tracking
    - **DEGRADED**: In-memory cache fallback with essential risk controls
    - **EMERGENCY_HALT**: All trading halted due to critical system issues

    Key Features:
    - Real-time exposure calculation and monitoring
    - Automated position validation before order placement
    - Dynamic risk limits based on market conditions
    - Comprehensive alerting system with multiple channels
    - Historical exposure tracking and analytics
    - Database failover with in-memory backup
    - Integration with trading engine for automatic risk enforcement

    Alert Channels:
    - Console output with color coding
    - Log file persistence
    - Webhook notifications (if configured)
    - Email alerts (if configured)
    - Slack integration (if configured)

    Example Usage:
        >>> from inkedup_bot.config import BotConfig
        >>> from inkedup_bot.state import StateManager
        >>> from inkedup_bot.order_client import OrderClient
        >>>
        >>> # Initialize with standard configuration
        >>> cfg = BotConfig(
        ...     global_risk_cap=10000.0,      # $10k max exposure
        ...     max_position_size=1000.0,     # $1k max per position
        ...     max_market_exposure=2500.0    # $2.5k max per market
        ... )
        >>> state = StateManager(db_path="trading.db")
        >>> order_client = OrderClient(cfg, state)
        >>> risk_manager = RiskManager(cfg, order_client, state)
        >>>
        >>> # Check if order would violate risk limits
        >>> order_data = {
        ...     "token_id": "0x123...",
        ...     "side": "buy",
        ...     "price": 0.65,
        ...     "size": 500.0,
        ...     "market_slug": "2024-election"
        ... }
        >>>
        >>> if await risk_manager.validate_order(order_data):
        ...     print("Order approved by risk management")
        ...     # Proceed with order placement
        ... else:
        ...     print("Order rejected - would exceed risk limits")
        >>>
        >>> # Monitor current exposure
        >>> exposure = await risk_manager.get_current_exposure()
        >>> print(f"Total exposure: ${exposure['total']:.2f}")
        >>> print(f"Available capacity: ${exposure['available']:.2f}")
        >>>
        >>> # Emergency halt trading if needed
        >>> if market_crash_detected:
        ...     await risk_manager.emergency_halt("Market crash detected")

    Risk Metrics Tracked:
    - Total portfolio exposure and utilization
    - Position-level exposure and P&L
    - Market concentration and diversification
    - Outcome distribution (YES/NO balance)
    - Historical volatility and drawdowns
    - Correlation-adjusted exposure
    - Liquidity-adjusted position sizes

    Failure Recovery:
    The system automatically handles database failures and network issues:
    1. Automatic retry with exponential backoff
    2. Fallback to in-memory cache for essential operations
    3. Gradual degradation of functionality while maintaining safety
    4. Emergency halt if critical systems become unavailable
    5. Automatic recovery when systems are restored
    """

    def __init__(
        self, cfg: BotConfig, order_client: OrderClient, state: StateManager
    ) -> None:
        self.cfg = cfg
        self.order_client = order_client
        self.state = state

        # Initialize alert system
        self.alert_manager = RiskAlertManager()
        self.alert_manager.add_console_handler(colored=True)
        self.alert_manager.add_file_handler("logs/risk_alerts.log")

        # Add webhook/email handlers if configured
        self._setup_alert_handlers(cfg)

        # Initialize exposure tracking systems
        self.exposure_calculator = ExposureCalculator(state.db)
        self.exposure_history = ExposureHistoryTracker(state.db)

        # Initialize fallback system
        self.mode = RiskSystemMode.NORMAL
        self.fallback_cache = DatabaseFallbackCache()
        self.database_failure_count = 0
        self.last_database_check = time.time()
        self.max_failure_threshold = (
            3  # Number of failures before switching to degraded mode
        )
        self.emergency_halt_threshold = 10  # Number of failures before emergency halt
        self.database_check_interval = 60  # Seconds between database health checks
        self.database_retry_attempts = (
            3  # Number of retry attempts for database operations
        )
        self.database_retry_delay = 1.0  # Seconds between retry attempts

        # Initialize and validate risk configuration using Pydantic
        try:
            self.risk_config = RiskManagementConfig.from_bot_config(cfg)
            log.info("Risk configuration validated successfully")
        except PydanticValidationError as e:
            log.error(f"Risk configuration validation failed: {e}")
            raise RuntimeError(
                f"Invalid risk configuration prevents system startup: {e}"
            ) from e
        except Exception as e:
            log.error(f"Unexpected error during risk configuration validation: {e}")
            raise RuntimeError(f"Risk configuration validation error: {e}") from e

        # Initialize validation framework with validated config
        self.validation_context = ValidationContext(
            config=self.risk_config.model_dump()
        )

        # Initialize enhanced position validator
        self.enhanced_validator = EnhancedPositionValidator(
            state_manager=state,
            market_data_provider=None,  # Will be set if available
            order_client=order_client,
            config={
                "max_liquidity_ratio": 0.1,
                "max_slippage_tolerance": 0.05,
                "volatility_adjustment_factor": 0.5,
                "correlation_threshold": 0.7,
                "min_market_depth": 100,
                "max_market_impact": 0.02,
            },
        )

        # Check order client readiness but don't fail for scanning-only operations
        self._trading_enabled = self.order_client.ready()
        if not self._trading_enabled:
            log.warning("Order client not ready - trading functionality disabled")

        # Initialize fallback cache with current state if possible
        self._initialize_fallback_cache()

        # Set up state manager integration for fallback cache
        self.state.set_risk_manager(self)

        # Log risk configuration summary
        self._log_risk_configuration()

    def _setup_alert_handlers(self, cfg: BotConfig) -> None:
        """Set up additional alert handlers based on configuration."""
        try:
            # Add webhook handler if configured
            webhook_url = getattr(cfg, "risk_webhook_url", None)
            if webhook_url:
                self.alert_manager.add_webhook_handler(
                    webhook_url, AlertSeverity.WARNING
                )
                log.info("Risk webhook handler configured")

            # Add email handler if configured
            email_config = getattr(cfg, "risk_email_alerts", None)
            if email_config and isinstance(email_config, dict):
                required_fields = [
                    "smtp_server",
                    "smtp_port",
                    "username",
                    "password",
                    "from_email",
                    "to_emails",
                ]
                if all(field in email_config for field in required_fields):
                    self.alert_manager.add_email_handler(
                        smtp_server=email_config["smtp_server"],
                        smtp_port=email_config["smtp_port"],
                        username=email_config["username"],
                        password=email_config["password"],
                        from_email=email_config["from_email"],
                        to_emails=email_config["to_emails"],
                        min_severity=AlertSeverity.CRITICAL,
                    )
                    log.info("Risk email handler configured")
                else:
                    log.warning(
                        "Incomplete email configuration - skipping email alerts"
                    )

        except Exception as e:
            log.warning(f"Failed to set up additional alert handlers: {e}")

    def _initialize_fallback_cache(self) -> None:
        """Initialize fallback cache with current position data if database is available."""
        try:
            # Try to populate cache from current database state
            total_exposure = self.state.get_total_exposure()
            self.fallback_cache.total_exposure = total_exposure
            log.info(
                f"Fallback cache initialized with total exposure: ${total_exposure:,.2f}"
            )
        except Exception as e:
            log.warning(f"Could not initialize fallback cache from database: {e}")
            self.fallback_cache.clear()

    def _check_database_health(self) -> bool:
        """Check if database is accessible and responding with retry logic."""
        for attempt in range(self.database_retry_attempts):
            try:
                # Simple health check - try to get total exposure
                result = self.state.get_total_exposure()
                # Additional validation: ensure we get a reasonable response
                if isinstance(result, (int, float)) and result >= 0:
                    if attempt > 0:
                        log.info(
                            f"Database health check succeeded on attempt {attempt + 1}"
                        )
                    return True
                else:
                    log.warning(f"Database returned invalid result: {result}")

            except Exception as e:
                log.warning(f"Database health check attempt {attempt + 1} failed: {e}")
                if attempt < self.database_retry_attempts - 1:
                    time.sleep(
                        self.database_retry_delay * (attempt + 1)
                    )  # Exponential backoff

        log.error(
            f"Database health check failed after {self.database_retry_attempts} attempts"
        )
        return False

    def _handle_database_failure(self, operation: str, error: Exception) -> None:
        """Handle database failure and determine appropriate fallback mode."""
        self.database_failure_count += 1
        log.error(
            f"Database failure during {operation}: {error} (failure count: {self.database_failure_count})"
        )

        # Send database failure alert
        asyncio.create_task(
            self.alert_manager.database_failure_alert(
                operation=operation,
                error=str(error),
                failure_count=self.database_failure_count,
                context={
                    "current_mode": self.mode.value,
                    "max_failure_threshold": self.max_failure_threshold,
                    "emergency_halt_threshold": self.emergency_halt_threshold,
                },
            )
        )

        # Determine fallback mode based on failure count
        if self.database_failure_count >= self.emergency_halt_threshold:
            self._switch_to_emergency_halt(
                f"Database failure threshold exceeded: {self.database_failure_count}"
            )
        elif self.database_failure_count >= self.max_failure_threshold:
            self._switch_to_degraded_mode(
                f"Database instability detected: {self.database_failure_count} failures"
            )

    def _switch_to_degraded_mode(self, reason: str) -> None:
        """Switch to degraded mode with in-memory cache fallback."""
        if self.mode != RiskSystemMode.DEGRADED:
            old_mode = self.mode.value
            self.mode = RiskSystemMode.DEGRADED
            log.critical(f"RISK SYSTEM: Switching to DEGRADED mode - {reason}")
            log.critical(
                "Risk checks will continue using in-memory cache with limited functionality"
            )
            log.critical(
                "Database connectivity issues detected - position tracking may be incomplete"
            )

            # Send mode change alert
            asyncio.create_task(
                self.alert_manager.risk_mode_change_alert(
                    old_mode=old_mode,
                    new_mode="degraded",
                    reason=reason,
                    context={
                        "database_failure_count": self.database_failure_count,
                        "functionality": "limited",
                        "cache_stats": self.fallback_cache.get_cache_stats(),
                    },
                )
            )

    def _switch_to_emergency_halt(self, reason: str) -> None:
        """Switch to emergency halt mode - all trading stopped."""
        if self.mode != RiskSystemMode.EMERGENCY_HALT:
            old_mode = self.mode.value
            self.mode = RiskSystemMode.EMERGENCY_HALT
            log.critical(f"RISK SYSTEM: EMERGENCY HALT ACTIVATED - {reason}")
            log.critical("ALL TRADING ACTIVITY SUSPENDED")
            log.critical(
                "Manual intervention required to restore trading functionality"
            )
            log.critical(
                "Check database connectivity and system health before resuming"
            )

            # Send emergency halt alert
            asyncio.create_task(
                self.alert_manager.trading_halt_alert(
                    reason=reason,
                    context={
                        "old_mode": old_mode,
                        "database_failure_count": self.database_failure_count,
                        "emergency_halt_threshold": self.emergency_halt_threshold,
                        "intervention_required": True,
                    },
                )
            )

    def _try_database_recovery(self) -> bool:
        """Attempt to recover database connectivity."""
        current_time = time.time()
        if current_time - self.last_database_check < self.database_check_interval:
            return False  # Too soon to retry

        self.last_database_check = current_time

        if self._check_database_health():
            # Database is back online
            old_mode = self.mode
            self.mode = RiskSystemMode.NORMAL
            self.database_failure_count = 0
            log.info(
                f"Database connectivity restored - switching from {old_mode.value} to NORMAL mode"
            )

            # Re-initialize cache with fresh data
            self._initialize_fallback_cache()
            return True

        return False

    def _get_exposure_data_with_fallback(self, operation: str, func, *args, **kwargs):
        """Get exposure data with automatic fallback handling."""
        # If in emergency halt mode, don't even try
        if self.mode == RiskSystemMode.EMERGENCY_HALT:
            raise RuntimeError(
                "Risk system in emergency halt mode - all trading suspended"
            )

        # Try database recovery if we're not in normal mode
        if self.mode != RiskSystemMode.NORMAL:
            self._try_database_recovery()

        # If still not in normal mode, use fallback
        if self.mode != RiskSystemMode.NORMAL:
            if operation == "get_total_exposure":
                return self.fallback_cache.get_total_exposure()
            elif operation == "get_position_notional":
                return self.fallback_cache.get_position_notional(args[0])
            elif operation == "get_market_exposure":
                return self.fallback_cache.get_market_exposure(args[0])
            elif operation == "get_outcome_exposure":
                return self.fallback_cache.get_outcome_exposure(args[0])
            else:
                log.warning(f"Unknown fallback operation: {operation}")
                return 0.0

        # Try normal database operation
        try:
            result = func(*args, **kwargs)
            # Reset failure count on successful operation
            if self.database_failure_count > 0:
                self.database_failure_count = max(0, self.database_failure_count - 1)
            return result
        except Exception as e:
            self._handle_database_failure(operation, e)

            # Return fallback data
            if operation == "get_total_exposure":
                return self.fallback_cache.get_total_exposure()
            elif operation == "get_position_notional":
                return self.fallback_cache.get_position_notional(args[0])
            elif operation == "get_market_exposure":
                return self.fallback_cache.get_market_exposure(args[0])
            elif operation == "get_outcome_exposure":
                return self.fallback_cache.get_outcome_exposure(args[0])
            else:
                log.error(f"No fallback available for operation: {operation}")
                raise

    def _log_risk_configuration(self) -> None:
        """Log summary of validated risk configuration."""
        limits = self.risk_config.get_risk_limits()
        log.info("Risk Management Configuration:")
        log.info(f"  Global Risk Cap: ${limits['global_risk_cap']:,.2f}")
        log.info(f"  Position Risk Cap: ${limits['position_risk_cap']:,.2f}")
        log.info(f"  Per-Market Risk Cap: ${limits['per_market_risk_cap']:,.2f}")
        log.info(f"  Per-Outcome Risk Cap: ${limits['per_outcome_risk_cap']:,.2f}")
        log.info(f"  Max Position Size: ${limits['max_position_size']:,.2f}")
        log.info(f"  Max Order Size: ${limits['max_order_size']:,.2f}")
        log.info(f"  Validation Enabled: {self.risk_config.validation_enabled}")
        log.info(f"  Strict Mode: {self.risk_config.strict_mode}")

    def _create_validation_pipeline(self):
        """Create validation pipeline with configured validators."""
        # Simplified validation for now
        return None

    def preflight(
        self,
        token_id: str,
        intended_notional: float,
        market_slug: str | None = None,
        outcome_type: str | None = None,
    ) -> bool:
        """
        Synchronous preflight check for backward compatibility.
        Enhanced with Pydantic validation framework.
        """
        # Check order client readiness first (for backward compatibility)
        # Check both the cached state and current readiness
        if not self._trading_enabled or not self.order_client.ready():
            raise RuntimeError("Order client not ready")

        # First, validate the trading parameters against our risk configuration
        if self.risk_config.validation_enabled:
            validation_result = self.risk_config.validate_trading_parameters(
                token_id, intended_notional, market_slug, outcome_type
            )

            if not validation_result["is_valid"]:
                # For backward compatibility, extract the original error message for simple validation errors
                for error in validation_result["errors"]:
                    if "intended_notional must be positive" in error:
                        raise ValueError("Intended notional must be positive")

                error_messages = "; ".join(validation_result["errors"])
                raise ValueError(f"Parameter validation failed: {error_messages}")

            # Handle warnings in strict mode
            if self.risk_config.strict_mode and validation_result["warnings"]:
                warning_messages = "; ".join(validation_result["warnings"])
                raise ValueError(
                    f"Strict mode - warnings treated as errors: {warning_messages}"
                )

        # Perform enhanced validation checks
        return self._enhanced_preflight_check_sync(
            token_id, intended_notional, market_slug, outcome_type
        )

    def _enhanced_preflight_check_sync(
        self,
        token_id: str,
        intended_notional: float,
        market_slug: str | None = None,
        outcome_type: str | None = None,
    ) -> bool:
        """
        Synchronous enhanced preflight check using validated risk configuration.
        Uses validated limits from Pydantic models with database fallback support.
        """
        limits = self.risk_config.get_risk_limits()

        # Basic input validation (redundant with Pydantic but kept for safety)
        if intended_notional <= 0:
            raise ValueError("Intended notional must be positive")

        # Check if we're in emergency halt mode
        if self.mode == RiskSystemMode.EMERGENCY_HALT:
            raise RuntimeError(
                "Risk system in emergency halt mode - all trading suspended"
            )

        # Global exposure check with fallback
        total = self._get_exposure_data_with_fallback(
            "get_total_exposure", self.state.get_total_exposure
        )
        if (
            limits["global_risk_cap"] > 0
            and total + intended_notional > limits["global_risk_cap"]
        ):
            # Log mode information for debugging
            mode_info = (
                f" (Risk system mode: {self.mode.value})"
                if self.mode != RiskSystemMode.NORMAL
                else ""
            )
            raise RuntimeError(
                f"Global cap exceeded ({total + intended_notional:.2f} > {limits['global_risk_cap']}){mode_info}"
            )

        # Per-position risk check with fallback
        current_notional = self._get_exposure_data_with_fallback(
            "get_position_notional", self.state.get_position_notional, token_id
        )
        new_notional = current_notional + intended_notional
        if (
            limits["position_risk_cap"] > 0
            and new_notional > limits["position_risk_cap"]
        ):
            mode_info = (
                f" (Risk system mode: {self.mode.value})"
                if self.mode != RiskSystemMode.NORMAL
                else ""
            )
            raise RuntimeError(
                f"Per-position cap exceeded ({new_notional:.2f} > {limits['position_risk_cap']}){mode_info}"
            )

        # Per-market risk check with fallback
        if market_slug and limits["per_market_risk_cap"] > 0:
            current_market_exposure = self._get_exposure_data_with_fallback(
                "get_market_exposure", self.state.get_market_exposure, market_slug
            )
            new_market_exposure = current_market_exposure + intended_notional
            if new_market_exposure > limits["per_market_risk_cap"]:
                mode_info = (
                    f" (Risk system mode: {self.mode.value})"
                    if self.mode != RiskSystemMode.NORMAL
                    else ""
                )
                raise RuntimeError(
                    f"Per-market cap exceeded for {market_slug} ({new_market_exposure:.2f} > {limits['per_market_risk_cap']}){mode_info}"
                )

        # Per-outcome risk check with fallback
        if outcome_type and limits["per_outcome_risk_cap"] > 0:
            current_outcome_exposure = self._get_exposure_data_with_fallback(
                "get_outcome_exposure", self.state.get_outcome_exposure, outcome_type
            )
            new_outcome_exposure = current_outcome_exposure + intended_notional
            if new_outcome_exposure > limits["per_outcome_risk_cap"]:
                mode_info = (
                    f" (Risk system mode: {self.mode.value})"
                    if self.mode != RiskSystemMode.NORMAL
                    else ""
                )
                raise RuntimeError(
                    f"Per-outcome cap exceeded for {outcome_type} ({new_outcome_exposure:.2f} > {limits['per_outcome_risk_cap']}){mode_info}"
                )

        # Log mode information if not in normal mode
        if self.mode != RiskSystemMode.NORMAL:
            log.warning(
                f"Preflight check completed in {self.mode.value} mode - using fallback data"
            )

        # Additional validation logging
        log.debug(
            f"Preflight passed - token_id={token_id}, notional=${intended_notional:.2f}, "
            f"market={market_slug}, outcome={outcome_type} (mode: {self.mode.value})"
        )

        return True

    async def preflight_async(
        self,
        token_id: str,
        intended_notional: float,
        market_slug: str | None = None,
        outcome_type: str | None = None,
    ) -> bool:
        """
        Async version of preflight check for new async workflows.
        Enhanced with Pydantic validation framework.
        """
        # Check order client readiness first
        if not self._trading_enabled:
            raise RuntimeError("Order client not ready")

        # First, validate the trading parameters against our risk configuration
        if self.risk_config.validation_enabled:
            validation_result = self.risk_config.validate_trading_parameters(
                token_id, intended_notional, market_slug, outcome_type
            )

            if not validation_result["is_valid"]:
                error_messages = "; ".join(validation_result["errors"])
                raise ValueError(f"Parameter validation failed: {error_messages}")

            # Handle warnings in strict mode
            if self.risk_config.strict_mode and validation_result["warnings"]:
                warning_messages = "; ".join(validation_result["warnings"])
                raise ValueError(
                    f"Strict mode - warnings treated as errors: {warning_messages}"
                )

        # Perform enhanced validation checks
        return await self._enhanced_preflight_check(
            token_id, intended_notional, market_slug, outcome_type
        )

    async def _enhanced_preflight_check(
        self,
        token_id: str,
        intended_notional: float,
        market_slug: str | None = None,
        outcome_type: str | None = None,
    ) -> bool:
        """
        Enhanced preflight check using validated risk configuration.
        Uses validated limits from Pydantic models with database fallback support.
        """
        limits = self.risk_config.get_risk_limits()

        # Basic input validation (redundant with Pydantic but kept for safety)
        if intended_notional <= 0:
            raise ValueError("Intended notional must be positive")

        # Check if we're in emergency halt mode
        if self.mode == RiskSystemMode.EMERGENCY_HALT:
            raise RuntimeError(
                "Risk system in emergency halt mode - all trading suspended"
            )

        # Global exposure check with fallback
        total = self._get_exposure_data_with_fallback(
            "get_total_exposure", self.state.get_total_exposure
        )
        if (
            limits["global_risk_cap"] > 0
            and total + intended_notional > limits["global_risk_cap"]
        ):
            mode_info = (
                f" (Risk system mode: {self.mode.value})"
                if self.mode != RiskSystemMode.NORMAL
                else ""
            )
            raise RuntimeError(
                f"Global cap exceeded ({total + intended_notional:.2f} > {limits['global_risk_cap']}){mode_info}"
            )

        # Per-position risk check with fallback
        current_notional = self._get_exposure_data_with_fallback(
            "get_position_notional", self.state.get_position_notional, token_id
        )
        new_notional = current_notional + intended_notional
        if (
            limits["position_risk_cap"] > 0
            and new_notional > limits["position_risk_cap"]
        ):
            mode_info = (
                f" (Risk system mode: {self.mode.value})"
                if self.mode != RiskSystemMode.NORMAL
                else ""
            )
            raise RuntimeError(
                f"Per-position cap exceeded ({new_notional:.2f} > {limits['position_risk_cap']}){mode_info}"
            )

        # Per-market risk check with fallback
        if market_slug and limits["per_market_risk_cap"] > 0:
            current_market_exposure = self._get_exposure_data_with_fallback(
                "get_market_exposure", self.state.get_market_exposure, market_slug
            )
            new_market_exposure = current_market_exposure + intended_notional
            if new_market_exposure > limits["per_market_risk_cap"]:
                mode_info = (
                    f" (Risk system mode: {self.mode.value})"
                    if self.mode != RiskSystemMode.NORMAL
                    else ""
                )
                raise RuntimeError(
                    f"Per-market cap exceeded for {market_slug} ({new_market_exposure:.2f} > {limits['per_market_risk_cap']}){mode_info}"
                )

        # Per-outcome risk check with fallback
        if outcome_type and limits["per_outcome_risk_cap"] > 0:
            current_outcome_exposure = self._get_exposure_data_with_fallback(
                "get_outcome_exposure", self.state.get_outcome_exposure, outcome_type
            )
            new_outcome_exposure = current_outcome_exposure + intended_notional
            if new_outcome_exposure > limits["per_outcome_risk_cap"]:
                mode_info = (
                    f" (Risk system mode: {self.mode.value})"
                    if self.mode != RiskSystemMode.NORMAL
                    else ""
                )
                raise RuntimeError(
                    f"Per-outcome cap exceeded for {outcome_type} ({new_outcome_exposure:.2f} > {limits['per_outcome_risk_cap']}){mode_info}"
                )

        # Log mode information if not in normal mode
        if self.mode != RiskSystemMode.NORMAL:
            log.warning(
                f"Preflight check completed in {self.mode.value} mode - using fallback data"
            )

        # Additional validation logging
        log.debug(
            f"Preflight passed - token_id={token_id}, notional=${intended_notional:.2f}, "
            f"market={market_slug}, outcome={outcome_type} (mode: {self.mode.value})"
        )

        return True

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
    ) -> dict[str, Any]:
        """
        Enhanced parameter validation using Pydantic models.
        Returns comprehensive validation results with detailed error context.
        """
        try:
            # First run Pydantic validation
            if self.risk_config.validation_enabled:
                pydantic_result = self.risk_config.validate_trading_parameters(
                    token_id, intended_notional, market_slug, outcome_type
                )

                if not pydantic_result["is_valid"]:
                    return {
                        "is_valid": False,
                        "errors": [
                            {"field": "config", "message": err}
                            for err in pydantic_result["errors"]
                        ],
                        "warnings": [
                            {"field": "config", "message": warn}
                            for warn in pydantic_result.get("warnings", [])
                        ],
                        "metadata": {
                            "validation_type": "pydantic",
                            "config_validated": True,
                        },
                    }

            # Then run the enhanced preflight check
            self.preflight(token_id, intended_notional, market_slug, outcome_type)

            return {
                "is_valid": True,
                "errors": [],
                "warnings": [],
                "metadata": {
                    "validation_type": "enhanced",
                    "config_validated": True,
                    "risk_limits_checked": True,
                },
            }
        except ValueError as e:
            return {
                "is_valid": False,
                "errors": [{"field": "parameter", "message": str(e)}],
                "warnings": [],
                "metadata": {"validation_type": "parameter_error"},
            }
        except RuntimeError as e:
            return {
                "is_valid": False,
                "errors": [{"field": "risk_limit", "message": str(e)}],
                "warnings": [],
                "metadata": {"validation_type": "risk_limit_error"},
            }
        except Exception as e:
            return {
                "is_valid": False,
                "errors": [{"field": "general", "message": str(e)}],
                "warnings": [],
                "metadata": {"validation_type": "unexpected_error"},
            }

    def record_trade(
        self,
        token_id: str,
        notional: float,
        market_slug: str | None = None,
        outcome_type: str | None = None,
        trade_size: float | None = None,
        trade_price: float | None = None,
        side: str | None = None,
    ) -> dict[str, Any]:
        """
        Records a completed trade and updates exposure tracking.
        Should be called after successful order execution.

        Returns the trade impact details for further processing.
        """
        # Enhanced trade recording with full trade details
        if all([trade_size, trade_price, side, market_slug, outcome_type]):
            try:
                # Use the enhanced trade impact recording
                result = self.state.record_trade_impact(
                    token_id=token_id,
                    trade_size=trade_size,
                    trade_price=trade_price,
                    side=side,
                    market_slug=market_slug,
                    outcome_type=outcome_type,
                )

                log.info(
                    f"Enhanced trade recorded: {token_id} {side} {trade_size} @ {trade_price} "
                    f"(market: {market_slug}, outcome: {outcome_type}, notional: {result.get('trade_notional', 0):.2f})"
                )
                return result

            except Exception as e:
                log.error(f"Failed to record enhanced trade impact: {e}")
                # Fall through to legacy method

        # Legacy method for backward compatibility
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
            f"Trade recorded (legacy): {token_id} notional={notional:.2f}, market={market_slug}, outcome={outcome_type}"
        )

        return {
            "token_id": token_id,
            "notional_delta": notional,
            "market_slug": market_slug,
            "outcome_type": outcome_type,
            "method": "legacy",
        }

    async def record_trade_async(
        self,
        token_id: str,
        trade_size: float,
        trade_price: float,
        side: str,
        market_slug: str,
        outcome_type: str,
    ) -> dict[str, Any]:
        """
        Async version of trade recording with full trade details.
        Preferred method for new implementations.
        """
        result = await self.state.record_trade_impact_async(
            token_id=token_id,
            trade_size=trade_size,
            trade_price=trade_price,
            side=side,
            market_slug=market_slug,
            outcome_type=outcome_type,
        )

        log.info(
            f"Enhanced trade recorded (async): {token_id} {side} {trade_size} @ {trade_price} "
            f"(market: {market_slug}, outcome: {outcome_type}, notional: {result.get('trade_notional', 0):.2f})"
        )
        return result

    def get_exposure_summary(self) -> dict[str, Any]:
        """
        Get comprehensive exposure summary across all markets and outcomes.
        """
        try:
            total_exposure = self.state.get_total_exposure()
            all_positions = self.state.get_all_positions()

            # Calculate market exposures
            market_exposures = {}
            outcome_exposures = {}

            for position in all_positions:
                market = position.get("market_slug", "unknown")
                outcome = position.get("outcome_type", "unknown")
                notional = abs(position.get("notional_value", 0.0))

                if market not in market_exposures:
                    market_exposures[market] = 0.0
                market_exposures[market] += notional

                if outcome not in outcome_exposures:
                    outcome_exposures[outcome] = 0.0
                outcome_exposures[outcome] += notional

            return {
                "total_exposure": total_exposure,
                "position_count": len(all_positions),
                "market_count": len(market_exposures),
                "outcome_count": len(outcome_exposures),
                "market_exposures": market_exposures,
                "outcome_exposures": outcome_exposures,
                "risk_limits": self.risk_config.get_risk_limits(),
                "utilization": {
                    "global": (
                        total_exposure / self.risk_config.global_risk.global_risk_cap
                        if self.risk_config.global_risk.global_risk_cap > 0
                        else 0.0
                    ),
                },
            }
        except Exception as e:
            log.error(f"Failed to get exposure summary: {e}")
            return {
                "error": str(e),
                "total_exposure": 0.0,
                "position_count": 0,
                "market_count": 0,
                "outcome_count": 0,
            }

    def get_market_risk_analysis(self, market_slug: str) -> dict[str, Any]:
        """
        Get detailed risk analysis for a specific market.
        """
        try:
            market_summary = self.state.get_market_summary(market_slug)
            risk_limits = self.risk_config.get_risk_limits()

            # Calculate risk metrics
            market_exposure = market_summary.get("absolute_exposure", 0.0)
            market_cap = risk_limits.get("per_market_risk_cap", 0.0)

            risk_analysis = {
                **market_summary,
                "risk_metrics": {
                    "exposure_utilization": (
                        market_exposure / market_cap if market_cap > 0 else 0.0
                    ),
                    "risk_score": min(market_exposure / max(market_cap, 1.0), 1.0),
                    "positions_at_risk": sum(
                        1
                        for outcome in market_summary.get("outcome_breakdown", [])
                        if outcome.get("absolute_exposure", 0)
                        > risk_limits.get("position_risk_cap", float("inf"))
                    ),
                },
                "limits": {
                    "market_cap": market_cap,
                    "position_cap": risk_limits.get("position_risk_cap", 0.0),
                    "remaining_capacity": max(0.0, market_cap - market_exposure),
                },
            }

            return risk_analysis
        except Exception as e:
            log.error(f"Failed to get market risk analysis for {market_slug}: {e}")
            return {
                "market_slug": market_slug,
                "error": str(e),
                "risk_metrics": {"risk_score": 1.0},  # Max risk on error
            }

    def get_outcome_risk_analysis(self, outcome_type: str) -> dict[str, Any]:
        """
        Get detailed risk analysis for a specific outcome type.
        """
        try:
            outcome_summary = self.state.get_outcome_summary(outcome_type)
            risk_limits = self.risk_config.get_risk_limits()

            # Calculate risk metrics
            outcome_exposure = outcome_summary.get("absolute_exposure", 0.0)
            outcome_cap = risk_limits.get("per_outcome_risk_cap", 0.0)

            risk_analysis = {
                **outcome_summary,
                "risk_metrics": {
                    "exposure_utilization": (
                        outcome_exposure / outcome_cap if outcome_cap > 0 else 0.0
                    ),
                    "risk_score": min(outcome_exposure / max(outcome_cap, 1.0), 1.0),
                    "markets_at_risk": sum(
                        1
                        for market in outcome_summary.get("market_breakdown", [])
                        if market.get("absolute_exposure", 0)
                        > risk_limits.get("per_market_risk_cap", float("inf"))
                    ),
                },
                "limits": {
                    "outcome_cap": outcome_cap,
                    "market_cap": risk_limits.get("per_market_risk_cap", 0.0),
                    "remaining_capacity": max(0.0, outcome_cap - outcome_exposure),
                },
            }

            return risk_analysis
        except Exception as e:
            log.error(f"Failed to get outcome risk analysis for {outcome_type}: {e}")
            return {
                "outcome_type": outcome_type,
                "error": str(e),
                "risk_metrics": {"risk_score": 1.0},  # Max risk on error
            }

    def update_market_data(self, market_data: dict[str, Any]) -> None:
        """
        Update market data in validation context.
        This allows validators to access current market information.
        """
        self.validation_context.update_market_data(market_data)
        log.info(f"Updated market data for {len(market_data)} markets")

    def get_validation_config(self) -> dict[str, Any]:
        """Get current validation configuration from Pydantic model."""
        return {
            "risk_caps": self.risk_config.get_risk_limits(),
            "market_conditions": self.risk_config.market_conditions.model_dump(),
            "order_execution": self.risk_config.order_execution.model_dump(),
            "strategy_risk": self.risk_config.strategy_risk.model_dump(),
            "validation_enabled": self.risk_config.validation_enabled,
            "strict_mode": self.risk_config.strict_mode,
        }

    def validate_system_startup(self) -> dict[str, Any]:
        """
        Validate system configuration at startup to prevent invalid configurations.
        This is called during initialization to ensure all parameters are valid.
        """
        validation_results = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "config_summary": {},
        }

        try:
            # Check if risk configuration is properly initialized
            if not hasattr(self, "risk_config"):
                validation_results["is_valid"] = False
                validation_results["errors"].append(
                    "Risk configuration not initialized"
                )
                return validation_results

            # Validate configuration consistency
            limits = self.risk_config.get_risk_limits()
            config_summary = {
                "global_risk_cap": limits["global_risk_cap"],
                "position_risk_cap": limits["position_risk_cap"],
                "max_position_size": limits["max_position_size"],
                "max_order_size": limits["max_order_size"],
                "validation_enabled": self.risk_config.validation_enabled,
            }
            validation_results["config_summary"] = config_summary

            # Check for potential configuration warnings
            warnings = []
            if limits["global_risk_cap"] == 0:
                warnings.append("Global risk cap is disabled (set to 0)")

            if limits["position_risk_cap"] == 0:
                warnings.append("Position risk cap is disabled (set to 0)")

            if not self.risk_config.validation_enabled:
                warnings.append(
                    "Risk validation is disabled - system will not validate parameters"
                )

            if limits["max_order_size"] >= limits["max_position_size"]:
                warnings.append(
                    f"Max order size (${limits['max_order_size']}) is >= max position size "
                    f"(${limits['max_position_size']}) - may allow oversized positions"
                )

            validation_results["warnings"] = warnings

            log.info("Risk system startup validation completed successfully")
            return validation_results

        except Exception as e:
            validation_results["is_valid"] = False
            validation_results["errors"].append(f"Startup validation failed: {str(e)}")
            log.error(f"Risk system startup validation failed: {e}")
            return validation_results

    @classmethod
    def validate_config_before_startup(cls, cfg: BotConfig) -> dict[str, Any]:
        """
        Static method to validate configuration before RiskManager initialization.
        This allows catching configuration errors early in the startup process.
        """
        try:
            # Attempt to create and validate the risk configuration
            risk_config = RiskManagementConfig.from_bot_config(cfg)

            return {
                "is_valid": True,
                "errors": [],
                "warnings": [],
                "risk_config": risk_config.model_dump(),
            }
        except PydanticValidationError as e:
            error_details = []
            for error in e.errors():
                field = " -> ".join(str(x) for x in error["loc"])
                message = error["msg"]
                error_details.append(f"{field}: {message}")

            return {
                "is_valid": False,
                "errors": error_details,
                "warnings": [],
                "validation_error": str(e),
            }
        except Exception as e:
            return {
                "is_valid": False,
                "errors": [f"Unexpected validation error: {str(e)}"],
                "warnings": [],
            }

    # Fallback system utility methods
    def update_fallback_cache_position(
        self, token_id: str, position_data: dict[str, Any]
    ) -> None:
        """Update position in fallback cache for position tracking."""
        try:
            self.fallback_cache.update_position(token_id, position_data)
            log.debug(f"Updated fallback cache for position {token_id}")
        except Exception as e:
            log.error(f"Failed to update fallback cache for position {token_id}: {e}")

    def get_risk_system_status(self) -> dict[str, Any]:
        """Get comprehensive status of the risk system including fallback state."""
        cache_stats = self.fallback_cache.get_cache_stats()

        return {
            "mode": self.mode.value,
            "database_failure_count": self.database_failure_count,
            "trading_enabled": self._trading_enabled,
            "last_database_check": self.last_database_check,
            "fallback_cache": cache_stats,
            "thresholds": {
                "max_failure_threshold": self.max_failure_threshold,
                "emergency_halt_threshold": self.emergency_halt_threshold,
                "database_check_interval": self.database_check_interval,
            },
            "risk_config_summary": self.risk_config.get_risk_limits(),
        }

    def force_database_check(self) -> bool:
        """Force an immediate database health check and potential mode change."""
        log.info("Forcing database health check...")
        self.last_database_check = 0  # Reset check time to force immediate check
        return self._try_database_recovery()

    def reset_database_failure_count(self) -> None:
        """Reset database failure count (for manual recovery)."""
        old_count = self.database_failure_count
        self.database_failure_count = 0
        log.info(f"Reset database failure count from {old_count} to 0")

    # Enhanced exposure tracking methods

    async def start_exposure_tracking(self) -> None:
        """Start the exposure tracking systems."""
        try:
            await self.exposure_history.start()
            log.info("Exposure tracking systems started")
        except Exception as e:
            log.error(f"Failed to start exposure tracking: {e}")

    async def stop_exposure_tracking(self) -> None:
        """Stop the exposure tracking systems."""
        try:
            await self.exposure_history.stop()
            log.info("Exposure tracking systems stopped")
        except Exception as e:
            log.error(f"Failed to stop exposure tracking: {e}")

    async def get_comprehensive_portfolio_exposure(
        self, include_analytics: bool = True, include_predictions: bool = False
    ) -> dict[str, Any]:
        """
        Get comprehensive portfolio exposure analysis.

        Args:
            include_analytics: Include historical analytics
            include_predictions: Include trend predictions

        Returns:
            Complete portfolio exposure report
        """
        try:
            # Get current portfolio exposure
            portfolio = await self.exposure_calculator.calculate_portfolio_exposure()

            # Create exposure snapshot for history
            snapshot = ExposureSnapshot(
                timestamp=time.time(),
                total_exposure=float(portfolio.total_notional),
                net_exposure=float(portfolio.net_exposure),
                market_exposures={
                    market: float(exp.total_notional)
                    for market, exp in portfolio.market_exposures.items()
                },
                outcome_exposures={
                    outcome: float(exp.total_notional)
                    for outcome, exp in portfolio.outcome_exposures.items()
                },
                position_count=portfolio.position_count,
            )

            # Record snapshot
            await self.exposure_history.record_exposure_snapshot(snapshot)

            result = {
                "portfolio": {
                    "total_notional": float(portfolio.total_notional),
                    "net_exposure": float(portfolio.net_exposure),
                    "gross_exposure": float(portfolio.gross_exposure),
                    "market_count": portfolio.market_count,
                    "outcome_count": portfolio.outcome_count,
                    "position_count": portfolio.position_count,
                },
                "market_exposures": {
                    market: {
                        "total_notional": float(exp.total_notional),
                        "net_exposure": float(exp.net_exposure),
                        "position_count": exp.position_count,
                        "outcome_breakdown": {
                            k: float(v) for k, v in exp.outcome_breakdown.items()
                        },
                    }
                    for market, exp in portfolio.market_exposures.items()
                },
                "outcome_exposures": {
                    outcome: {
                        "total_notional": float(exp.total_notional),
                        "net_exposure": float(exp.net_exposure),
                        "position_count": exp.position_count,
                        "market_breakdown": {
                            k: float(v) for k, v in exp.market_breakdown.items()
                        },
                    }
                    for outcome, exp in portfolio.outcome_exposures.items()
                },
                "concentration_metrics": {
                    k: float(v) for k, v in portfolio.concentration_metrics.items()
                },
                "risk_metrics": {
                    k: float(v) for k, v in portfolio.risk_metrics.items()
                },
                "timestamp": time.time(),
            }

            # Add analytics if requested
            if include_analytics:
                analytics = await self.exposure_history.get_exposure_analytics()
                result["analytics"] = {
                    "trend": analytics.exposure_trend,
                    "trend_strength": analytics.trend_strength,
                    "volatility": analytics.volatility,
                    "mean_exposure": analytics.mean_exposure,
                    "max_exposure": analytics.max_exposure,
                    "var_95": analytics.var_95,
                    "max_drawdown": analytics.max_drawdown,
                    "sharpe_ratio": analytics.sharpe_ratio,
                    "risk_alerts": analytics.risk_alerts,
                    "insights": analytics.insights,
                }

            # Add predictions if requested
            if include_predictions:
                prediction = await self.exposure_history.predict_exposure_trend()
                result["prediction"] = prediction

            return result

        except Exception as e:
            log.error(f"Failed to get comprehensive portfolio exposure: {e}")
            return {"error": str(e)}

    def set_emergency_halt(self, reason: str = "Manual emergency halt") -> None:
        """Manually trigger emergency halt mode."""
        self._switch_to_emergency_halt(reason)

    def clear_emergency_halt(self) -> bool:
        """
        Attempt to clear emergency halt mode by checking database health.
        Returns True if successfully cleared, False otherwise.
        """
        if self.mode != RiskSystemMode.EMERGENCY_HALT:
            log.info("Not in emergency halt mode - no action needed")
            return True

        log.info("Attempting to clear emergency halt mode...")

        # Reset failure count and try database recovery
        self.database_failure_count = 0
        if self._check_database_health():
            self.mode = RiskSystemMode.NORMAL
            self._initialize_fallback_cache()
            log.info("Emergency halt cleared - risk system restored to normal mode")
            return True
        else:
            log.error("Cannot clear emergency halt - database still unhealthy")
            return False

    async def enhanced_position_validation(
        self,
        token_id: str,
        intended_size: float,
        market_slug: str,
        outcome_type: str,
        order_type: str = "market",
    ) -> PositionValidationResult:
        """
        Enhanced position validation with comprehensive edge case handling.

        This method provides advanced validation that considers:
        - Market liquidity and order book depth
        - Dynamic position sizing based on market conditions
        - Race condition prevention through atomic operations
        - Slippage protection and market impact estimation
        - Concentration and correlation risk analysis

        Args:
            token_id: Token identifier
            intended_size: Intended position size in USD
            market_slug: Market identifier
            outcome_type: Outcome type (YES/NO)
            order_type: Order type (market/limit)

        Returns:
            PositionValidationResult with detailed validation outcome
        """
        try:
            # Check if enhanced validation is enabled
            if (
                not hasattr(self, "enhanced_validator")
                or self.enhanced_validator is None
            ):
                log.warning(
                    "Enhanced validator not available, falling back to basic validation"
                )
                # Fallback to basic validation
                basic_passed = await self.preflight_async(
                    token_id, intended_size, market_slug, outcome_type
                )
                return PositionValidationResult(
                    is_valid=basic_passed,
                    severity=(
                        PositionValidationResult.ValidationSeverity.INFO
                        if basic_passed
                        else PositionValidationResult.ValidationSeverity.ERROR
                    ),
                    message=(
                        "Basic validation passed"
                        if basic_passed
                        else "Basic validation failed"
                    ),
                )

            # Use enhanced validator
            from decimal import Decimal

            validation_result = await self.enhanced_validator.validate_position_size(
                token_id=token_id,
                intended_size=Decimal(str(intended_size)),
                market_slug=market_slug,
                outcome_type=outcome_type,
                order_type=order_type,
            )

            # Log validation result
            if validation_result.is_valid:
                log.info(
                    f"Enhanced validation passed for {token_id}: {validation_result.message}"
                )
                if validation_result.warnings:
                    for warning in validation_result.warnings:
                        log.warning(f"Position validation warning: {warning}")
            else:
                log.error(
                    f"Enhanced validation failed for {token_id}: {validation_result.message}"
                )

            return validation_result

        except Exception as e:
            log.error(f"Enhanced position validation error: {e}")
            return PositionValidationResult(
                is_valid=False,
                severity=PositionValidationResult.ValidationSeverity.CRITICAL,
                message=f"Enhanced validation system error: {str(e)}",
            )

    async def get_optimal_position_size(
        self, token_id: str, desired_size: float, market_slug: str, outcome_type: str
    ) -> dict[str, Any]:
        """
        Get optimal position size recommendation with explanations.

        Returns a dictionary containing:
        - optimal_size: Recommended position size
        - explanations: List of reasons for the recommendation
        - risk_metrics: Associated risk metrics
        - market_conditions: Current market condition assessment
        """
        try:
            if (
                not hasattr(self, "enhanced_validator")
                or self.enhanced_validator is None
            ):
                return {
                    "optimal_size": min(
                        desired_size,
                        float(self.risk_config.get_risk_limits()["max_position_size"]),
                    ),
                    "explanations": [
                        "Enhanced validator not available - using basic limits"
                    ],
                    "risk_metrics": {},
                    "market_conditions": "unknown",
                }

            from decimal import Decimal

            (
                optimal_size,
                suggestions,
            ) = await self.enhanced_validator.get_suggested_position_size(
                token_id=token_id,
                desired_size=Decimal(str(desired_size)),
                market_slug=market_slug,
                outcome_type=outcome_type,
            )

            # Get validation result for additional metrics
            validation_result = await self.enhanced_validator.validate_position_size(
                token_id=token_id,
                intended_size=optimal_size,
                market_slug=market_slug,
                outcome_type=outcome_type,
            )

            return {
                "optimal_size": float(optimal_size),
                "explanations": suggestions,
                "risk_metrics": validation_result.metadata or {},
                "market_conditions": (
                    validation_result.market_condition.value
                    if validation_result.market_condition
                    else "unknown"
                ),
                "estimated_slippage": (
                    float(validation_result.estimated_slippage)
                    if validation_result.estimated_slippage
                    else None
                ),
            }

        except Exception as e:
            log.error(f"Error getting optimal position size: {e}")
            return {
                "optimal_size": 0.0,
                "explanations": [f"Error calculating optimal size: {str(e)}"],
                "risk_metrics": {},
                "market_conditions": "error",
            }

    def update_enhanced_validator_config(self, config_updates: dict[str, Any]) -> None:
        """Update enhanced validator configuration."""
        if hasattr(self, "enhanced_validator") and self.enhanced_validator is not None:
            for key, value in config_updates.items():
                if hasattr(self.enhanced_validator, key):
                    setattr(self.enhanced_validator, key, value)
                    log.info(f"Updated enhanced validator config: {key} = {value}")
                else:
                    log.warning(f"Unknown enhanced validator config key: {key}")
        else:
            log.warning("Enhanced validator not available for configuration update")

    def set_market_data_provider(self, provider) -> None:
        """Set market data provider for enhanced validation."""
        if hasattr(self, "enhanced_validator") and self.enhanced_validator is not None:
            self.enhanced_validator.market_data_provider = provider
            log.info("Market data provider set for enhanced validation")
        else:
            log.warning(
                "Enhanced validator not available for market data provider setup"
            )
