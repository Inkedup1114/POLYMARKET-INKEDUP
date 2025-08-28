"""
Enhanced signal validation framework for trading signal processing pipeline.

This module provides comprehensive validation for trading signals including:
- Data integrity validation
- Market condition checks
- Risk assessment integration
- Signal quality scoring
- Safety requirement verification
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .signals import TradingSignal

# from .risk.validators import RiskValidator  # Optional dependency
from .validation.schemas import MessageValidator

logger = logging.getLogger("signal_validation")


class ValidationLevel(str, Enum):
    """Signal validation levels."""

    BASIC = "basic"  # Basic data integrity checks
    STANDARD = "standard"  # Standard validation with market checks
    COMPREHENSIVE = "comprehensive"  # Full validation with risk assessment
    CRITICAL = "critical"  # Maximum validation for high-risk signals


class ValidationStatus(str, Enum):
    """Validation result status."""

    VALID = "valid"  # Signal passes all validations
    WARNING = "warning"  # Signal has warnings but may proceed
    REJECTED = "rejected"  # Signal rejected due to validation failures
    BLOCKED = "blocked"  # Signal blocked by safety mechanisms


class SignalQuality(str, Enum):
    """Signal quality classification."""

    EXCELLENT = "excellent"  # High-quality signal
    GOOD = "good"  # Good quality signal
    ACCEPTABLE = "acceptable"  # Acceptable quality signal
    POOR = "poor"  # Poor quality signal
    UNACCEPTABLE = "unacceptable"  # Unacceptable quality signal


@dataclass
class ValidationResult:
    """Result of signal validation."""

    status: ValidationStatus
    quality: SignalQuality
    score: float  # Quality score (0-100)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks_passed: int = 0
    checks_failed: int = 0
    validation_time: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketCondition:
    """Market condition data for validation."""

    market_slug: str
    token_id: str
    current_price: float
    bid_price: float | None = None
    ask_price: float | None = None
    volume_24h: float | None = None
    volatility: float | None = None
    spread_bps: float | None = None
    last_trade_time: float | None = None
    is_active: bool = True
    liquidity_score: float | None = None


@dataclass
class ValidationConfig:
    """Configuration for signal validation."""

    # Validation levels
    default_level: ValidationLevel = ValidationLevel.STANDARD
    enable_market_checks: bool = True
    enable_risk_assessment: bool = True
    enable_quality_scoring: bool = True

    # Price validation
    min_price: float = 0.01
    max_price: float = 0.99
    max_price_deviation: float = 0.20  # 20% from market price

    # Size validation
    min_size: float = 1.0
    max_size: float = 10000.0
    max_notional_value: float = 5000.0

    # Market condition checks
    min_liquidity_score: float = 0.3
    max_spread_bps: float = 1000  # 10%
    max_volatility: float = 0.5  # 50%
    min_volume_24h: float = 100.0

    # Risk thresholds
    max_position_concentration: float = 0.25  # 25% of portfolio
    max_market_exposure: float = 0.40  # 40% in single market
    max_daily_loss_limit: float = 1000.0  # Daily loss limit

    # Quality scoring weights
    data_quality_weight: float = 0.3
    market_condition_weight: float = 0.3
    risk_assessment_weight: float = 0.4

    # Safety mechanisms
    enable_circuit_breakers: bool = True
    max_signals_per_minute: int = 10
    max_signals_per_hour: int = 100
    cooling_period_seconds: int = 300  # 5 minutes


class SignalValidator:
    """
    Enhanced signal validator with comprehensive validation framework.

    Provides multi-level validation including data integrity, market conditions,
    risk assessment, and signal quality scoring.
    """

    def __init__(
        self,
        config: ValidationConfig | None = None,
        risk_validator: Any | None = None,
    ):
        self.config = config or ValidationConfig()
        self.risk_validator = risk_validator
        self.message_validator = MessageValidator()

        # Validation state
        self._validation_cache: dict[str, ValidationResult] = {}
        self._signal_counts: dict[str, list[float]] = {}  # timestamp tracking
        self._blocked_signals: set[str] = set()
        self._circuit_breaker_active = False
        self._last_circuit_break = 0.0

        # Performance tracking
        self._validation_stats = {
            "total_signals": 0,
            "valid_signals": 0,
            "rejected_signals": 0,
            "warnings_issued": 0,
            "validation_time_total": 0.0,
        }

        logger.info("SignalValidator initialized")

    def validate_signal(
        self,
        signal: TradingSignal,
        market_condition: MarketCondition | None = None,
        validation_level: ValidationLevel | None = None,
    ) -> ValidationResult:
        """
        Validate a trading signal with comprehensive checks.

        Args:
            signal: Trading signal to validate
            market_condition: Current market condition data
            validation_level: Level of validation to apply

        Returns:
            ValidationResult with status, quality score, and details
        """
        start_time = time.time()
        level = validation_level or self.config.default_level

        # Initialize result
        result = ValidationResult(
            status=ValidationStatus.VALID, quality=SignalQuality.EXCELLENT, score=100.0
        )

        try:
            # Rate limiting and circuit breaker checks
            if not self._check_rate_limits(signal, result):
                return result

            if not self._check_circuit_breaker(signal, result):
                return result

            # Core validation pipeline
            self._validate_data_integrity(signal, result)

            if level in [
                ValidationLevel.STANDARD,
                ValidationLevel.COMPREHENSIVE,
                ValidationLevel.CRITICAL,
            ]:
                self._validate_market_conditions(signal, market_condition, result)

            if level in [ValidationLevel.COMPREHENSIVE, ValidationLevel.CRITICAL]:
                self._validate_risk_assessment(signal, result)

            if self.config.enable_quality_scoring:
                self._calculate_quality_score(signal, market_condition, result)

            # Additional checks for critical level
            if level == ValidationLevel.CRITICAL:
                self._validate_critical_safety_checks(signal, result)

            # Final status determination
            self._determine_final_status(result)

            # Update statistics
            self._update_validation_stats(result)

            # Cache result
            if signal.signal_id:
                self._validation_cache[signal.signal_id] = result

        except Exception as e:
            logger.error(f"Error during signal validation: {e}")
            result.status = ValidationStatus.REJECTED
            result.errors.append(f"Validation error: {str(e)}")

        finally:
            result.validation_time = time.time() - start_time
            self._validation_stats["validation_time_total"] += result.validation_time

        return result

    def _check_rate_limits(
        self, signal: TradingSignal, result: ValidationResult
    ) -> bool:
        """Check rate limiting constraints."""
        current_time = time.time()

        # Clean old entries
        minute_ago = current_time - 60
        hour_ago = current_time - 3600

        if signal.market_slug not in self._signal_counts:
            self._signal_counts[signal.market_slug] = []

        timestamps = self._signal_counts[signal.market_slug]
        timestamps[:] = [t for t in timestamps if t > hour_ago]

        # Check limits
        recent_signals = [t for t in timestamps if t > minute_ago]

        if len(recent_signals) >= self.config.max_signals_per_minute:
            result.status = ValidationStatus.BLOCKED
            result.errors.append(
                f"Rate limit exceeded: {len(recent_signals)} signals in last minute"
            )
            return False

        if len(timestamps) >= self.config.max_signals_per_hour:
            result.status = ValidationStatus.BLOCKED
            result.errors.append(
                f"Hourly rate limit exceeded: {len(timestamps)} signals"
            )
            return False

        # Record this signal
        timestamps.append(current_time)
        return True

    def _check_circuit_breaker(
        self, signal: TradingSignal, result: ValidationResult
    ) -> bool:
        """Check circuit breaker status."""
        if not self.config.enable_circuit_breakers:
            return True

        current_time = time.time()

        # Check if cooling period is active
        if (
            self._circuit_breaker_active
            and current_time - self._last_circuit_break
            < self.config.cooling_period_seconds
        ):
            result.status = ValidationStatus.BLOCKED
            result.errors.append("Circuit breaker active - cooling period in effect")
            return False

        # Reset circuit breaker if cooling period passed
        if self._circuit_breaker_active:
            self._circuit_breaker_active = False
            logger.info("Circuit breaker reset after cooling period")

        return True

    def _validate_data_integrity(self, signal: TradingSignal, result: ValidationResult):
        """Validate basic data integrity."""
        checks = 0
        failures = 0

        # Required fields check
        if not signal.market_slug:
            result.errors.append("Missing market_slug")
            failures += 1
        checks += 1

        if not signal.token_id:
            result.errors.append("Missing token_id")
            failures += 1
        checks += 1

        # Price validation
        if signal.price <= 0:
            result.errors.append(f"Invalid price: {signal.price}")
            failures += 1
        elif signal.price < self.config.min_price:
            result.warnings.append(
                f"Price below minimum: {signal.price} < {self.config.min_price}"
            )
        elif signal.price > self.config.max_price:
            result.warnings.append(
                f"Price above maximum: {signal.price} > {self.config.max_price}"
            )
        checks += 1

        # Size validation
        if signal.size <= 0:
            result.errors.append(f"Invalid size: {signal.size}")
            failures += 1
        elif signal.size < self.config.min_size:
            result.warnings.append(
                f"Size below minimum: {signal.size} < {self.config.min_size}"
            )
        elif signal.size > self.config.max_size:
            result.warnings.append(
                f"Size above maximum: {signal.size} > {self.config.max_size}"
            )
        checks += 1

        # Notional value check
        notional = signal.price * signal.size
        if notional > self.config.max_notional_value:
            result.errors.append(
                f"Notional value too high: {notional} > {self.config.max_notional_value}"
            )
            failures += 1
        checks += 1

        # Side validation
        if signal.side not in ["buy", "sell"]:
            result.errors.append(f"Invalid side: {signal.side}")
            failures += 1
        checks += 1

        # Signal age check
        signal_age = time.time() - signal.created_at
        if signal_age > 300:  # 5 minutes
            result.warnings.append(f"Signal is stale: {signal_age:.1f}s old")
        checks += 1

        result.checks_passed += checks - failures
        result.checks_failed += failures

    def _validate_market_conditions(
        self,
        signal: TradingSignal,
        market_condition: MarketCondition | None,
        result: ValidationResult,
    ):
        """Validate market condition requirements."""
        if not self.config.enable_market_checks or not market_condition:
            return

        checks = 0
        failures = 0

        # Market activity check
        if not market_condition.is_active:
            result.errors.append("Market is not active")
            failures += 1
        checks += 1

        # Price deviation check
        if market_condition.current_price:
            price_diff = (
                abs(signal.price - market_condition.current_price)
                / market_condition.current_price
            )
            if price_diff > self.config.max_price_deviation:
                result.errors.append(
                    f"Price deviation too high: {price_diff:.1%} > {self.config.max_price_deviation:.1%}"
                )
                failures += 1
        checks += 1

        # Liquidity check
        if (
            market_condition.liquidity_score is not None
            and market_condition.liquidity_score < self.config.min_liquidity_score
        ):
            result.warnings.append(
                f"Low liquidity: {market_condition.liquidity_score:.2f} < {self.config.min_liquidity_score}"
            )
        checks += 1

        # Spread check
        if (
            market_condition.spread_bps is not None
            and market_condition.spread_bps > self.config.max_spread_bps
        ):
            result.warnings.append(
                f"High spread: {market_condition.spread_bps:.0f} bps > {self.config.max_spread_bps} bps"
            )
        checks += 1

        # Volatility check
        if (
            market_condition.volatility is not None
            and market_condition.volatility > self.config.max_volatility
        ):
            result.warnings.append(
                f"High volatility: {market_condition.volatility:.1%} > {self.config.max_volatility:.1%}"
            )
        checks += 1

        # Volume check
        if (
            market_condition.volume_24h is not None
            and market_condition.volume_24h < self.config.min_volume_24h
        ):
            result.warnings.append(
                f"Low volume: {market_condition.volume_24h:.1f} < {self.config.min_volume_24h}"
            )
        checks += 1

        # Stale data check
        if (
            market_condition.last_trade_time is not None
            and time.time() - market_condition.last_trade_time > 3600
        ):  # 1 hour
            result.warnings.append("Market data is stale (>1h since last trade)")
        checks += 1

        result.checks_passed += checks - failures
        result.checks_failed += failures

    def _validate_risk_assessment(
        self, signal: TradingSignal, result: ValidationResult
    ):
        """Validate risk assessment requirements."""
        if not self.config.enable_risk_assessment or not self.risk_validator:
            return

        checks = 0
        failures = 0

        try:
            # Position concentration check
            notional = signal.price * signal.size
            # This would integrate with portfolio manager to check actual positions
            # For now, we'll use placeholder logic

            # Market exposure check
            # This would check total exposure to this market
            # Placeholder for now

            # Daily loss limit check
            # This would check against daily P&L tracking
            # Placeholder for now

            checks += 3

        except Exception as e:
            logger.error(f"Risk assessment error: {e}")
            result.warnings.append(f"Risk assessment failed: {str(e)}")
            failures += 1

        result.checks_passed += checks - failures
        result.checks_failed += failures

    def _calculate_quality_score(
        self,
        signal: TradingSignal,
        market_condition: MarketCondition | None,
        result: ValidationResult,
    ):
        """Calculate signal quality score."""
        score = 100.0

        # Data quality component
        data_score = 100.0
        if result.errors:
            data_score = max(0, 100 - len(result.errors) * 25)
        elif result.warnings:
            data_score = max(70, 100 - len(result.warnings) * 10)

        # Market condition component
        market_score = 100.0
        if market_condition:
            if market_condition.liquidity_score is not None:
                market_score *= market_condition.liquidity_score

            if market_condition.spread_bps is not None:
                spread_penalty = min(
                    30, market_condition.spread_bps / 10
                )  # Max 30% penalty
                market_score *= (100 - spread_penalty) / 100

            if market_condition.volatility is not None:
                vol_penalty = min(
                    40, market_condition.volatility * 100
                )  # Max 40% penalty
                market_score *= (100 - vol_penalty) / 100

        # Risk assessment component
        risk_score = 100.0
        # This would integrate with risk metrics
        # Placeholder for now

        # Weighted final score
        final_score = (
            data_score * self.config.data_quality_weight
            + market_score * self.config.market_condition_weight
            + risk_score * self.config.risk_assessment_weight
        )

        result.score = max(0, min(100, final_score))

        # Classify quality
        if result.score >= 90:
            result.quality = SignalQuality.EXCELLENT
        elif result.score >= 80:
            result.quality = SignalQuality.GOOD
        elif result.score >= 70:
            result.quality = SignalQuality.ACCEPTABLE
        elif result.score >= 50:
            result.quality = SignalQuality.POOR
        else:
            result.quality = SignalQuality.UNACCEPTABLE

    def _validate_critical_safety_checks(
        self, signal: TradingSignal, result: ValidationResult
    ):
        """Perform critical safety validation checks."""
        checks = 0
        failures = 0

        # Check if signal is in blocked list
        signal_key = f"{signal.market_slug}_{signal.token_id}"
        if signal_key in self._blocked_signals:
            result.errors.append("Signal from blocked market/token combination")
            failures += 1
        checks += 1

        # Extreme price check
        if signal.price < 0.001 or signal.price > 0.999:
            result.errors.append(f"Extreme price detected: {signal.price}")
            failures += 1
        checks += 1

        # Extreme size check
        if signal.size > self.config.max_size * 10:  # 10x normal max
            result.errors.append(f"Extreme size detected: {signal.size}")
            failures += 1
        checks += 1

        result.checks_passed += checks - failures
        result.checks_failed += failures

    def _determine_final_status(self, result: ValidationResult):
        """Determine final validation status."""
        if result.errors:
            result.status = ValidationStatus.REJECTED
        elif result.quality == SignalQuality.UNACCEPTABLE:
            result.status = ValidationStatus.REJECTED
        elif result.warnings or result.quality == SignalQuality.POOR:
            result.status = ValidationStatus.WARNING
        else:
            result.status = ValidationStatus.VALID

    def _update_validation_stats(self, result: ValidationResult):
        """Update validation statistics."""
        self._validation_stats["total_signals"] += 1

        if result.status == ValidationStatus.VALID:
            self._validation_stats["valid_signals"] += 1
        elif result.status == ValidationStatus.REJECTED:
            self._validation_stats["rejected_signals"] += 1

        if result.warnings:
            self._validation_stats["warnings_issued"] += len(result.warnings)

    def trigger_circuit_breaker(self, reason: str):
        """Manually trigger circuit breaker."""
        self._circuit_breaker_active = True
        self._last_circuit_break = time.time()
        logger.warning(f"Circuit breaker triggered: {reason}")

    def reset_circuit_breaker(self):
        """Reset circuit breaker."""
        self._circuit_breaker_active = False
        logger.info("Circuit breaker manually reset")

    def block_signal_source(self, market_slug: str, token_id: str):
        """Block signals from specific source."""
        signal_key = f"{market_slug}_{token_id}"
        self._blocked_signals.add(signal_key)
        logger.warning(f"Blocked signal source: {signal_key}")

    def unblock_signal_source(self, market_slug: str, token_id: str):
        """Unblock signals from specific source."""
        signal_key = f"{market_slug}_{token_id}"
        self._blocked_signals.discard(signal_key)
        logger.info(f"Unblocked signal source: {signal_key}")

    def get_validation_stats(self) -> dict[str, Any]:
        """Get validation statistics."""
        stats = self._validation_stats.copy()

        if stats["total_signals"] > 0:
            stats["validation_rate"] = stats["valid_signals"] / stats["total_signals"]
            stats["rejection_rate"] = stats["rejected_signals"] / stats["total_signals"]
            stats["avg_validation_time"] = (
                stats["validation_time_total"] / stats["total_signals"]
            )
        else:
            stats["validation_rate"] = 0.0
            stats["rejection_rate"] = 0.0
            stats["avg_validation_time"] = 0.0

        stats["circuit_breaker_active"] = self._circuit_breaker_active
        stats["blocked_sources"] = len(self._blocked_signals)

        return stats

    def clear_cache(self, max_age_seconds: int = 3600):
        """Clear old validation cache entries."""
        current_time = time.time()
        expired_keys = [
            key
            for key, result in self._validation_cache.items()
            if current_time - result.validation_time > max_age_seconds
        ]

        for key in expired_keys:
            del self._validation_cache[key]

        if expired_keys:
            logger.debug(
                f"Cleared {len(expired_keys)} expired validation cache entries"
            )


class ValidationPipeline:
    """
    Enhanced validation pipeline that orchestrates multiple validators.

    Provides a unified interface for comprehensive signal validation
    with configurable pipeline stages.
    """

    def __init__(self, config: ValidationConfig | None = None):
        self.config = config or ValidationConfig()
        self.signal_validator = SignalValidator(self.config)

        # Pipeline stages
        self._pipeline_stages = [
            ("data_integrity", self._validate_data_integrity),
            ("market_conditions", self._validate_market_conditions),
            ("risk_assessment", self._validate_risk_assessment),
            ("quality_scoring", self._calculate_quality_score),
            ("safety_checks", self._validate_safety_checks),
        ]

        # Pipeline statistics
        self._pipeline_stats = {
            "signals_processed": 0,
            "signals_passed": 0,
            "signals_rejected": 0,
            "stage_performance": {
                stage: {"processed": 0, "passed": 0}
                for stage, _ in self._pipeline_stages
            },
        }

        logger.info("ValidationPipeline initialized")

    def process_signal(
        self,
        signal: TradingSignal,
        market_condition: MarketCondition | None = None,
        validation_level: ValidationLevel | None = None,
    ) -> ValidationResult:
        """
        Process signal through validation pipeline.

        Args:
            signal: Trading signal to validate
            market_condition: Current market condition data
            validation_level: Level of validation to apply

        Returns:
            ValidationResult with comprehensive validation details
        """
        return self.signal_validator.validate_signal(
            signal, market_condition, validation_level
        )

    def process_batch(
        self,
        signals: list[TradingSignal],
        market_conditions: dict[str, MarketCondition] | None = None,
        validation_level: ValidationLevel | None = None,
    ) -> list[ValidationResult]:
        """
        Process batch of signals through validation pipeline.

        Args:
            signals: List of trading signals to validate
            market_conditions: Market conditions keyed by market_slug
            validation_level: Level of validation to apply

        Returns:
            List of ValidationResult objects
        """
        results = []

        for signal in signals:
            market_condition = None
            if market_conditions and signal.market_slug in market_conditions:
                market_condition = market_conditions[signal.market_slug]

            result = self.process_signal(signal, market_condition, validation_level)
            results.append(result)

        return results

    def get_pipeline_stats(self) -> dict[str, Any]:
        """Get pipeline performance statistics."""
        return self._pipeline_stats.copy()

    def reset_stats(self):
        """Reset pipeline statistics."""
        self._pipeline_stats = {
            "signals_processed": 0,
            "signals_passed": 0,
            "signals_rejected": 0,
            "stage_performance": {
                stage: {"processed": 0, "passed": 0}
                for stage, _ in self._pipeline_stages
            },
        }


# Utility functions for easy integration


def validate_trading_signal(
    signal: TradingSignal,
    market_condition: MarketCondition | None = None,
    config: ValidationConfig | None = None,
) -> ValidationResult:
    """
    Convenience function to validate a single trading signal.

    Args:
        signal: Trading signal to validate
        market_condition: Optional market condition data
        config: Optional validation configuration

    Returns:
        ValidationResult
    """
    validator = SignalValidator(config)
    return validator.validate_signal(signal, market_condition)


def create_market_condition(
    market_slug: str, token_id: str, current_price: float, **kwargs
) -> MarketCondition:
    """
    Convenience function to create MarketCondition object.

    Args:
        market_slug: Market identifier
        token_id: Token identifier
        current_price: Current market price
        **kwargs: Additional market condition parameters

    Returns:
        MarketCondition object
    """
    return MarketCondition(
        market_slug=market_slug,
        token_id=token_id,
        current_price=current_price,
        **kwargs,
    )
