"""
Enhanced position size validation with comprehensive edge case handling.

This module provides robust position size validation that considers:
- Market liquidity and order book depth
- Dynamic position sizing based on market conditions
- Race condition prevention through atomic operations
- Slippage protection and market impact estimation
- Time-based constraints and market state validation
- Correlation and concentration risk analysis
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from .atomic_operations import AtomicOperationManager, get_atomic_manager

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for position validation results."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MarketCondition(Enum):
    """Current market condition states."""

    NORMAL = "normal"
    VOLATILE = "volatile"
    LOW_LIQUIDITY = "low_liquidity"
    STRESSED = "stressed"
    HALTED = "halted"


@dataclass
class MarketData:
    """Market data snapshot for validation."""

    market_id: str
    bid_price: Decimal
    ask_price: Decimal
    bid_size: Decimal
    ask_size: Decimal
    last_price: Decimal
    volume_24h: Decimal
    price_change_24h: Decimal
    volatility: Decimal
    liquidity_score: Decimal
    is_active: bool
    is_suspended: bool
    is_settled: bool
    timestamp: float


@dataclass
class PositionValidationResult:
    """Result of enhanced position validation."""

    is_valid: bool
    severity: ValidationSeverity
    message: str
    suggested_max_size: Decimal | None = None
    estimated_slippage: Decimal | None = None
    market_condition: MarketCondition | None = None
    warnings: list[str] = None
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.metadata is None:
            self.metadata = {}


class EnhancedPositionValidator:
    """Enhanced position size validator with comprehensive edge case handling."""

    def __init__(
        self,
        state_manager,
        market_data_provider=None,
        order_client=None,
        config: dict[str, Any] = None,
        atomic_manager: AtomicOperationManager | None = None,
    ):
        self.state_manager = state_manager
        self.market_data_provider = market_data_provider
        self.order_client = order_client
        self.config = config or {}
        self._validation_lock = asyncio.Lock()
        self._market_data_cache: dict[str, MarketData] = {}
        self._cache_ttl = 30  # seconds

        # Atomic operations manager for race condition prevention
        self.atomic_manager = atomic_manager or get_atomic_manager()

        # Position update tracking for race condition detection
        self._position_update_timestamps: dict[str, float] = {}
        self._pending_validations: dict[str, str] = {}  # token_id -> operation_id

        # Configuration defaults
        self.max_liquidity_ratio = self.config.get("max_liquidity_ratio", 0.1)
        self.max_slippage_tolerance = self.config.get("max_slippage_tolerance", 0.05)
        self.volatility_adjustment_factor = self.config.get(
            "volatility_adjustment_factor", 0.5
        )
        self.correlation_threshold = self.config.get("correlation_threshold", 0.7)
        self.min_market_depth = self.config.get("min_market_depth", Decimal("100"))
        self.max_market_impact = self.config.get("max_market_impact", 0.02)

    async def validate_position_size(
        self,
        token_id: str,
        intended_size: Decimal,
        market_slug: str,
        outcome_type: str,
        order_type: str = "market",
        use_atomic_validation: bool = True,
    ) -> PositionValidationResult:
        """
        Comprehensive position size validation with edge case handling.

        Args:
            token_id: Token identifier
            intended_size: Intended position size in USD
            market_slug: Market identifier
            outcome_type: Outcome type (YES/NO)
            order_type: Order type (market/limit)
            use_atomic_validation: Whether to use atomic validation (prevents race conditions)

        Returns:
            PositionValidationResult with validation outcome and suggestions
        """
        if use_atomic_validation:
            # Use atomic validation to prevent race conditions
            return await self._validate_with_atomic_protection(
                token_id, intended_size, market_slug, outcome_type, order_type
            )
        else:
            # Fallback to basic validation without atomic protection
            async with self._validation_lock:
                return await self._perform_validation_checks(
                    token_id, intended_size, market_slug, outcome_type, order_type
                )

    async def _validate_with_atomic_protection(
        self,
        token_id: str,
        intended_size: Decimal,
        market_slug: str,
        outcome_type: str,
        order_type: str,
    ) -> PositionValidationResult:
        """Validate position size with atomic protection against race conditions."""
        operation_id = f"validate_{token_id}_{uuid.uuid4().hex[:8]}"

        try:
            # First check if operation is safe to perform
            safety_check = await self.atomic_manager.validate_operation_safety(
                token_id, market_slug, "position_validation"
            )

            if not safety_check["is_safe"]:
                warnings = safety_check.get("warnings", [])
                return PositionValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.WARNING,
                    message="Operation not safe due to concurrent operations",
                    warnings=warnings,
                    metadata={"safety_check": safety_check},
                )

            # Check if another validation is pending for this token
            pending_operation = self._pending_validations.get(token_id)
            if pending_operation:
                return PositionValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.WARNING,
                    message=f"Concurrent validation in progress for {token_id}",
                    metadata={
                        "pending_operation_id": pending_operation,
                        "safety_check": safety_check,
                    },
                )

            # Use atomic context manager for validation
            async with self.atomic_manager.atomic_position_validation(
                token_id, market_slug, operation_id
            ):
                # Track this validation operation
                self._pending_validations[token_id] = operation_id

                try:
                    result = await self._perform_validation_checks(
                        token_id, intended_size, market_slug, outcome_type, order_type
                    )

                    # Add atomic operation metadata
                    if result.metadata is None:
                        result.metadata = {}
                    result.metadata.update(
                        {
                            "operation_id": operation_id,
                            "atomic_validation": True,
                            "safety_check": safety_check,
                        }
                    )

                    return result

                finally:
                    # Clean up validation tracking
                    self._pending_validations.pop(token_id, None)
                    self._position_update_timestamps[token_id] = time.time()

        except TimeoutError:
            return PositionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                message="Validation timeout - system too busy or deadlock detected",
                metadata={"operation_id": operation_id, "timeout": True},
            )
        except Exception as e:
            logger.error(f"Error in atomic validation for {token_id}: {e}")
            return PositionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.CRITICAL,
                message=f"Atomic validation system error: {str(e)}",
                metadata={"operation_id": operation_id, "error": str(e)},
            )

    async def _perform_validation_checks(
        self,
        token_id: str,
        intended_size: Decimal,
        market_slug: str,
        outcome_type: str,
        order_type: str,
    ) -> PositionValidationResult:
        """Perform the actual validation checks (called within atomic context)."""
        try:
            # 1. Basic input validation
            basic_validation = self._validate_basic_inputs(
                token_id, intended_size, market_slug, outcome_type
            )
            if not basic_validation.is_valid:
                return basic_validation

            # 2. Get current market data
            market_data = await self._get_market_data(market_slug)
            if not market_data:
                return PositionValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"Unable to retrieve market data for {market_slug}",
                )

            # 3. Market state validation
            market_state_validation = await self._validate_market_state(market_data)
            if not market_state_validation.is_valid:
                return market_state_validation

            # 4. Liquidity-based validation
            liquidity_validation = await self._validate_liquidity_constraints(
                intended_size, market_data, outcome_type
            )
            if not liquidity_validation.is_valid:
                return liquidity_validation

            # 5. Risk concentration validation
            concentration_validation = await self._validate_concentration_risk(
                token_id, intended_size, market_slug, outcome_type
            )
            if not concentration_validation.is_valid:
                return concentration_validation

            # 6. Dynamic position size adjustment
            adjusted_validation = await self._validate_dynamic_sizing(
                intended_size, market_data, market_slug
            )
            if not adjusted_validation.is_valid:
                return adjusted_validation

            # 7. Slippage and market impact validation
            slippage_validation = await self._validate_slippage_impact(
                intended_size, market_data, order_type
            )
            if not slippage_validation.is_valid:
                return slippage_validation

            # 8. Race condition prevention check (enhanced with atomic tracking)
            race_condition_validation = await self._validate_atomic_constraints(
                token_id, intended_size, market_slug
            )
            if not race_condition_validation.is_valid:
                return race_condition_validation

            # Combine all warnings and metadata
            all_warnings = []
            all_metadata = {}
            for validation in [
                liquidity_validation,
                concentration_validation,
                adjusted_validation,
                slippage_validation,
                race_condition_validation,
            ]:
                all_warnings.extend(validation.warnings)
                all_metadata.update(validation.metadata)

            return PositionValidationResult(
                is_valid=True,
                severity=ValidationSeverity.INFO,
                message="Position size validation passed",
                suggested_max_size=intended_size,
                estimated_slippage=slippage_validation.estimated_slippage,
                market_condition=self._assess_market_condition(market_data),
                warnings=all_warnings,
                metadata=all_metadata,
            )

        except Exception as e:
            logger.error(f"Position validation error: {e}")
            return PositionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.CRITICAL,
                message=f"Validation system error: {str(e)}",
            )

    def _validate_basic_inputs(
        self, token_id: str, intended_size: Decimal, market_slug: str, outcome_type: str
    ) -> PositionValidationResult:
        """Validate basic input parameters."""
        if not token_id:
            return PositionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                message="Token ID cannot be empty",
            )

        if intended_size <= 0:
            return PositionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                message="Intended size must be positive",
            )

        if not market_slug:
            return PositionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                message="Market slug cannot be empty",
            )

        if outcome_type not in ["YES", "NO"]:
            return PositionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                message="Outcome type must be YES or NO",
            )

        return PositionValidationResult(
            is_valid=True,
            severity=ValidationSeverity.INFO,
            message="Basic input validation passed",
        )

    async def _get_market_data(self, market_slug: str) -> MarketData | None:
        """Get market data with caching."""
        current_time = time.time()

        # Check cache first
        if market_slug in self._market_data_cache:
            cached_data = self._market_data_cache[market_slug]
            if current_time - cached_data.timestamp < self._cache_ttl:
                return cached_data

        # Fetch new data if provider available
        if self.market_data_provider:
            try:
                raw_data = await self.market_data_provider.get_market_data(market_slug)
                if raw_data:
                    market_data = MarketData(
                        market_id=market_slug,
                        bid_price=Decimal(str(raw_data.get("bid_price", 0))),
                        ask_price=Decimal(str(raw_data.get("ask_price", 0))),
                        bid_size=Decimal(str(raw_data.get("bid_size", 0))),
                        ask_size=Decimal(str(raw_data.get("ask_size", 0))),
                        last_price=Decimal(str(raw_data.get("last_price", 0))),
                        volume_24h=Decimal(str(raw_data.get("volume_24h", 0))),
                        price_change_24h=Decimal(
                            str(raw_data.get("price_change_24h", 0))
                        ),
                        volatility=Decimal(str(raw_data.get("volatility", 0.1))),
                        liquidity_score=Decimal(
                            str(raw_data.get("liquidity_score", 0.5))
                        ),
                        is_active=raw_data.get("is_active", True),
                        is_suspended=raw_data.get("is_suspended", False),
                        is_settled=raw_data.get("is_settled", False),
                        timestamp=current_time,
                    )
                    self._market_data_cache[market_slug] = market_data
                    return market_data
            except Exception as e:
                logger.error(f"Error fetching market data for {market_slug}: {e}")

        # Return None if no market data available (don't fallback to mock data)
        return None

    async def _validate_market_state(
        self, market_data: MarketData
    ) -> PositionValidationResult:
        """Validate current market state allows trading."""
        if market_data.is_settled:
            return PositionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.CRITICAL,
                message=f"Market {market_data.market_id} has already settled",
            )

        if market_data.is_suspended:
            return PositionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                message=f"Market {market_data.market_id} is currently suspended",
            )

        if not market_data.is_active:
            return PositionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                message=f"Market {market_data.market_id} is not active",
            )

        return PositionValidationResult(
            is_valid=True,
            severity=ValidationSeverity.INFO,
            message="Market state validation passed",
        )

    async def _validate_liquidity_constraints(
        self, intended_size: Decimal, market_data: MarketData, outcome_type: str
    ) -> PositionValidationResult:
        """Validate position size against market liquidity."""
        warnings = []
        metadata = {}

        # Determine relevant market side based on outcome
        relevant_size = (
            market_data.ask_size if outcome_type == "YES" else market_data.bid_size
        )

        # Check if position size exceeds liquidity ratio threshold
        if relevant_size > 0:
            liquidity_ratio = intended_size / relevant_size
            metadata["liquidity_ratio"] = float(liquidity_ratio)

            if liquidity_ratio > self.max_liquidity_ratio:
                suggested_max = relevant_size * Decimal(str(self.max_liquidity_ratio))
                return PositionValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"Position size {intended_size} exceeds liquidity threshold ({liquidity_ratio:.1%} of available {relevant_size})",
                    suggested_max_size=suggested_max,
                    metadata=metadata,
                )
            elif liquidity_ratio > self.max_liquidity_ratio * 0.5:
                warnings.append(
                    f"Position size uses {liquidity_ratio:.1%} of available liquidity"
                )

        # Check minimum market depth
        total_depth = market_data.bid_size + market_data.ask_size
        if total_depth < self.min_market_depth:
            return PositionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                message=f"Insufficient market depth: {total_depth} < {self.min_market_depth}",
                metadata=metadata,
            )

        return PositionValidationResult(
            is_valid=True,
            severity=ValidationSeverity.INFO,
            message="Liquidity constraints validation passed",
            warnings=warnings,
            metadata=metadata,
        )

    async def _validate_concentration_risk(
        self, token_id: str, intended_size: Decimal, market_slug: str, outcome_type: str
    ) -> PositionValidationResult:
        """Validate concentration risk across portfolio."""
        warnings = []
        metadata = {}

        try:
            # Get current portfolio exposure
            current_exposure = Decimal(str(self.state_manager.get_total_exposure()))
            market_exposure = Decimal(
                str(self.state_manager.get_market_exposure(market_slug))
            )
            outcome_exposure = Decimal(
                str(self.state_manager.get_outcome_exposure(outcome_type))
            )

            # Calculate concentration ratios
            if current_exposure > 0:
                new_total = current_exposure + intended_size
                market_concentration = (market_exposure + intended_size) / new_total
                outcome_concentration = (outcome_exposure + intended_size) / new_total

                metadata.update(
                    {
                        "market_concentration": float(market_concentration),
                        "outcome_concentration": float(outcome_concentration),
                        "total_exposure": float(new_total),
                    }
                )

                # Check market concentration
                if market_concentration > 0.5:  # 50% concentration limit
                    return PositionValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message=f"Market concentration too high: {market_concentration:.1%}",
                        metadata=metadata,
                    )
                elif market_concentration > 0.3:
                    warnings.append(
                        f"High market concentration: {market_concentration:.1%}"
                    )

                # Check outcome concentration
                if outcome_concentration > 0.6:  # 60% outcome concentration limit
                    return PositionValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message=f"Outcome concentration too high: {outcome_concentration:.1%}",
                        metadata=metadata,
                    )
                elif outcome_concentration > 0.4:
                    warnings.append(
                        f"High outcome concentration: {outcome_concentration:.1%}"
                    )

        except Exception as e:
            logger.error(f"Error in concentration risk validation: {e}")
            warnings.append("Unable to fully assess concentration risk")

        return PositionValidationResult(
            is_valid=True,
            severity=ValidationSeverity.INFO,
            message="Concentration risk validation passed",
            warnings=warnings,
            metadata=metadata,
        )

    async def _validate_dynamic_sizing(
        self, intended_size: Decimal, market_data: MarketData, market_slug: str
    ) -> PositionValidationResult:
        """Validate position size with dynamic market condition adjustments."""
        warnings = []
        metadata = {}

        market_condition = self._assess_market_condition(market_data)
        metadata["market_condition"] = market_condition.value

        # Adjust maximum size based on market conditions
        base_max_size = intended_size
        adjustment_factor = Decimal("1.0")

        if market_condition == MarketCondition.VOLATILE:
            adjustment_factor = Decimal("0.7")  # Reduce by 30%
            warnings.append("Position size reduced due to high volatility")
        elif market_condition == MarketCondition.LOW_LIQUIDITY:
            adjustment_factor = Decimal("0.5")  # Reduce by 50%
            warnings.append("Position size reduced due to low liquidity")
        elif market_condition == MarketCondition.STRESSED:
            adjustment_factor = Decimal("0.3")  # Reduce by 70%
            warnings.append(
                "Position size significantly reduced due to stressed market conditions"
            )
        elif market_condition == MarketCondition.HALTED:
            return PositionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.CRITICAL,
                message="Trading halted due to extreme market conditions",
                metadata=metadata,
            )

        adjusted_max_size = base_max_size * adjustment_factor
        metadata["adjustment_factor"] = float(adjustment_factor)
        metadata["adjusted_max_size"] = float(adjusted_max_size)

        if intended_size > adjusted_max_size:
            return PositionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.WARNING,
                message="Position size exceeds market-adjusted limit",
                suggested_max_size=adjusted_max_size,
                market_condition=market_condition,
                warnings=warnings,
                metadata=metadata,
            )

        return PositionValidationResult(
            is_valid=True,
            severity=ValidationSeverity.INFO,
            message="Dynamic sizing validation passed",
            market_condition=market_condition,
            warnings=warnings,
            metadata=metadata,
        )

    async def _validate_slippage_impact(
        self, intended_size: Decimal, market_data: MarketData, order_type: str
    ) -> PositionValidationResult:
        """Validate estimated slippage and market impact."""
        warnings = []
        metadata = {}

        # Estimate slippage based on order size vs market depth
        spread = market_data.ask_price - market_data.bid_price
        mid_price = (market_data.bid_price + market_data.ask_price) / 2

        if mid_price > 0:
            spread_ratio = spread / mid_price
            metadata["spread_ratio"] = float(spread_ratio)

            # Estimate market impact
            total_depth = market_data.bid_size + market_data.ask_size
            if total_depth > 0:
                impact_ratio = intended_size / total_depth
                estimated_slippage = spread_ratio * (1 + impact_ratio)

                metadata.update(
                    {
                        "estimated_slippage": float(estimated_slippage),
                        "market_impact_ratio": float(impact_ratio),
                    }
                )

                # Check slippage tolerance
                if estimated_slippage > self.max_slippage_tolerance:
                    return PositionValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message=f"Estimated slippage {estimated_slippage:.2%} exceeds tolerance {self.max_slippage_tolerance:.2%}",
                        estimated_slippage=estimated_slippage,
                        metadata=metadata,
                    )
                elif estimated_slippage > self.max_slippage_tolerance * 0.5:
                    warnings.append(
                        f"High estimated slippage: {estimated_slippage:.2%}"
                    )

                # Check market impact
                if impact_ratio > self.max_market_impact:
                    warnings.append(
                        f"Significant market impact expected: {impact_ratio:.2%}"
                    )

                return PositionValidationResult(
                    is_valid=True,
                    severity=ValidationSeverity.INFO,
                    message="Slippage validation passed",
                    estimated_slippage=estimated_slippage,
                    warnings=warnings,
                    metadata=metadata,
                )

        return PositionValidationResult(
            is_valid=True,
            severity=ValidationSeverity.INFO,
            message="Slippage validation passed (insufficient data)",
            warnings=warnings,
            metadata=metadata,
        )

    async def _validate_atomic_constraints(
        self, token_id: str, intended_size: Decimal, market_slug: str
    ) -> PositionValidationResult:
        """Enhanced validation constraints to prevent race conditions with atomic operations."""
        warnings = []
        metadata = {}

        try:
            current_time = time.time()

            # Check our own position update tracking
            last_update_time = self._position_update_timestamps.get(token_id, 0)
            time_since_update = current_time - last_update_time
            metadata["time_since_last_update"] = time_since_update

            # Prevent rapid successive updates
            min_update_interval = 1.0  # 1 second minimum between updates
            if time_since_update < min_update_interval:
                return PositionValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.WARNING,
                    message=f"Position update too recent, wait {min_update_interval - time_since_update:.1f}s",
                    metadata=metadata,
                )

            # Check if another validation is pending for this token (only in atomic mode)
            # This check is moved to the atomic validation path since it's only relevant there

            # Check atomic manager metrics for system health
            lock_metrics = self.atomic_manager.get_lock_metrics()
            metadata["atomic_metrics"] = lock_metrics

            # Warn if system is under high load
            if (
                lock_metrics.get("current_active", 0)
                > lock_metrics.get("position_locks", 0) * 0.8
            ):
                warnings.append("High system load detected - validation may be slower")

            # Check if another order is pending for this token
            if hasattr(self.order_client, "has_pending_orders"):
                try:
                    if await self.order_client.has_pending_orders(token_id):
                        return PositionValidationResult(
                            is_valid=False,
                            severity=ValidationSeverity.WARNING,
                            message="Pending order exists for this token, wait for completion",
                            metadata=metadata,
                        )
                except Exception as e:
                    warnings.append(f"Unable to check pending orders: {e}")

            # Additional state manager check for position locks
            if hasattr(self.state_manager, "_last_position_update"):
                state_last_update = self.state_manager._last_position_update.get(
                    token_id, 0
                )
                if (
                    current_time - state_last_update < 0.5
                ):  # 500ms for state manager updates
                    warnings.append("Recent position update in state manager")

        except Exception as e:
            logger.error(f"Error in enhanced atomic constraints validation: {e}")
            warnings.append(f"Atomic constraints validation error: {str(e)}")
            # Don't fail the validation for atomic constraint errors unless critical

        return PositionValidationResult(
            is_valid=True,
            severity=ValidationSeverity.INFO,
            message="Enhanced atomic constraints validation passed",
            warnings=warnings,
            metadata=metadata,
        )

    async def check_concurrent_validation_safety(
        self, token_id: str, market_slug: str
    ) -> dict[str, Any]:
        """
        Check if it's safe to perform validation on this token/market combination.

        Returns detailed safety assessment for concurrent operations.
        """
        return await self.atomic_manager.validate_operation_safety(
            token_id, market_slug, "position_validation"
        )

    def get_validation_metrics(self) -> dict[str, Any]:
        """Get current validation system metrics."""
        return {
            "pending_validations": len(self._pending_validations),
            "position_update_timestamps": len(self._position_update_timestamps),
            "market_data_cache_size": len(self._market_data_cache),
            "atomic_metrics": self.atomic_manager.get_lock_metrics(),
        }

    def _assess_market_condition(self, market_data: MarketData) -> MarketCondition:
        """Assess current market condition based on market data."""
        # High volatility check
        if market_data.volatility > Decimal("0.3"):
            return MarketCondition.VOLATILE

        # Low liquidity check
        if market_data.liquidity_score < Decimal("0.3"):
            return MarketCondition.LOW_LIQUIDITY

        # Stressed market check (high volatility + low liquidity + large price change)
        if (
            market_data.volatility > Decimal("0.2")
            and market_data.liquidity_score < Decimal("0.5")
            and abs(market_data.price_change_24h) > Decimal("0.1")
        ):
            return MarketCondition.STRESSED

        # Halted market check
        if (
            market_data.bid_size == 0
            or market_data.ask_size == 0
            or market_data.volume_24h == 0
        ):
            return MarketCondition.HALTED

        return MarketCondition.NORMAL

    async def get_suggested_position_size(
        self, token_id: str, desired_size: Decimal, market_slug: str, outcome_type: str
    ) -> tuple[Decimal, list[str]]:
        """Get suggested position size with explanations."""
        validation_result = await self.validate_position_size(
            token_id, desired_size, market_slug, outcome_type
        )

        suggestions = []

        if validation_result.is_valid:
            return desired_size, ["Desired size is acceptable"]

        if validation_result.suggested_max_size:
            suggestions.append(
                f"Consider reducing size to {validation_result.suggested_max_size}"
            )
            return validation_result.suggested_max_size, suggestions

        # Fallback to conservative sizing
        market_data = await self._get_market_data(market_slug)
        if market_data:
            conservative_size = min(
                desired_size * Decimal("0.5"),  # 50% of desired
                market_data.ask_size * Decimal("0.1"),  # 10% of liquidity
            )
            suggestions.append("Conservative sizing based on market conditions")
            return conservative_size, suggestions

        return Decimal("0"), ["Unable to determine safe position size"]
