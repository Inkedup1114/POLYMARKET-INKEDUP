"""
Enhanced signal processing pipeline with comprehensive validation and quality scoring.

This module integrates all signal validation components into a unified processing
pipeline that ensures trading signals meet quality and safety requirements.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .market_condition_validator import (
    MarketConditionAssessment,
    MarketConditionValidator,
    MarketMetrics,
)
from .signal_risk_validator import (
    PortfolioState,
    RiskLevel,
    RiskMetrics,
    SignalRiskValidator,
)
from .signal_validation import (
    MarketCondition,
    SignalValidator,
    ValidationConfig,
    ValidationLevel,
    ValidationResult,
    ValidationStatus,
)
from .signals import TradingSignal

logger = logging.getLogger("enhanced_signal_processor")


class ProcessingStatus(str, Enum):
    """Signal processing status."""

    PENDING = "pending"  # Awaiting processing
    PROCESSING = "processing"  # Currently being processed
    APPROVED = "approved"  # Approved for execution
    REJECTED = "rejected"  # Rejected - do not execute
    WARNING = "warning"  # Approved with warnings
    BLOCKED = "blocked"  # Blocked by safety mechanisms


class SignalPriority(str, Enum):
    """Signal priority levels."""

    LOW = "low"  # Low priority
    NORMAL = "normal"  # Normal priority
    HIGH = "high"  # High priority
    URGENT = "urgent"  # Urgent priority
    CRITICAL = "critical"  # Critical priority


@dataclass
class ProcessingResult:
    """Result of enhanced signal processing."""

    signal: TradingSignal
    status: ProcessingStatus
    priority: SignalPriority

    # Validation results
    validation_result: ValidationResult | None = None
    market_assessment: MarketConditionAssessment | None = None
    risk_metrics: RiskMetrics | None = None

    # Quality metrics
    overall_quality_score: float = 0.0
    execution_recommendation: str = ""

    # Processing metadata
    processing_time: float = 0.0
    processed_at: float = field(default_factory=time.time)
    processor_version: str = "1.0"

    # Flags and warnings
    warning_flags: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    safety_flags: list[str] = field(default_factory=list)

    # Execution parameters
    recommended_size_adjustment: float | None = None  # Size multiplier (0-1)
    recommended_timeout: int | None = None  # Timeout in seconds
    execution_constraints: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessingConfig:
    """Configuration for enhanced signal processing."""

    # Processing behavior
    enable_parallel_processing: bool = True
    max_concurrent_signals: int = 20

    # Tiered timeout system based on signal urgency
    critical_timeout: int = 5  # 5s for critical/time-sensitive signals
    high_timeout: int = 15  # 15s for high priority signals
    normal_timeout: int = 10  # 10s for normal priority signals
    low_timeout: int = 15  # 15s for low priority signals

    # Backward compatibility
    processing_timeout: int = 10  # Default fallback timeout

    # Quality requirements
    min_quality_score: float = 60.0
    min_acceptable_score: float = 40.0

    # Risk tolerances
    max_risk_level: RiskLevel = RiskLevel.HIGH
    auto_reject_extreme_risk: bool = True

    # Market condition requirements
    require_market_assessment: bool = True
    min_market_score: float = 30.0

    # Safety mechanisms
    enable_circuit_breakers: bool = True
    max_processing_rate: int = 100  # signals per minute

    # Priority scoring weights
    quality_weight: float = 0.4
    risk_weight: float = 0.3
    market_weight: float = 0.2
    timing_weight: float = 0.1


class EnhancedSignalProcessor:
    """
    Enhanced signal processor with comprehensive validation pipeline.

    Integrates signal validation, market condition assessment, risk evaluation,
    and quality scoring to ensure signals meet safety and quality requirements.
    """

    def __init__(
        self,
        config: ProcessingConfig | None = None,
        validation_config: ValidationConfig | None = None,
    ):
        self.config = config or ProcessingConfig()

        # Initialize validators
        self.signal_validator = SignalValidator(validation_config)
        self.market_validator = MarketConditionValidator()
        self.risk_validator = SignalRiskValidator()

        # Processing state
        self._processing_queue: asyncio.Queue = asyncio.Queue()
        self._active_processing: dict[str, asyncio.Task] = {}
        self._processing_semaphore = asyncio.Semaphore(
            self.config.max_concurrent_signals
        )

        # Results cache
        self._results_cache: dict[str, ProcessingResult] = {}

        # Rate limiting
        self._processing_timestamps: list[float] = []

        # Statistics
        self._processing_stats = {
            "total_processed": 0,
            "approved_signals": 0,
            "rejected_signals": 0,
            "warning_signals": 0,
            "blocked_signals": 0,
            "timeout_errors": 0,
            "avg_processing_time": 0.0,
            "avg_quality_score": 0.0,
            "high_risk_count": 0,
            # Timeout tier statistics
            "critical_timeouts_used": 0,
            "high_timeouts_used": 0,
            "normal_timeouts_used": 0,
            "low_timeouts_used": 0,
        }

        logger.info("EnhancedSignalProcessor initialized with tiered timeout system")

    def _determine_processing_timeout(self, signal: TradingSignal) -> int:
        """
        Determine appropriate processing timeout based on signal characteristics.

        Args:
            signal: Trading signal to analyze

        Returns:
            Timeout in seconds based on signal urgency
        """
        # Factors that indicate urgency/time-sensitivity
        urgency_score = 0

        # 1. Check signal type - some are inherently time-sensitive
        if hasattr(signal, "signal_type"):
            time_sensitive_types = ["arbitrage", "complement_arb", "flash_opportunity"]
            if any(
                sig_type in str(signal.signal_type).lower()
                for sig_type in time_sensitive_types
            ):
                urgency_score += 30

        # 2. Check deviation magnitude for arbitrage opportunities
        if hasattr(signal, "complement_deviation"):
            deviation = abs(getattr(signal, "complement_deviation", 0))
            if deviation > 0.02:  # > 2% deviation is very urgent
                urgency_score += 25
            elif deviation > 0.01:  # > 1% deviation is urgent
                urgency_score += 15

        # 3. Check market volatility if available
        if hasattr(signal, "market_volatility"):
            volatility = getattr(signal, "market_volatility", 0)
            if volatility > 0.8:  # High volatility = time sensitive
                urgency_score += 20
            elif volatility > 0.5:
                urgency_score += 10

        # 4. Check signal age - older signals are less urgent
        signal_age = time.time() - getattr(signal, "created_at", time.time())
        if signal_age > 60:  # > 1 minute old
            urgency_score -= 20
        elif signal_age > 30:  # > 30 seconds old
            urgency_score -= 10

        # 5. Check if signal contains urgency indicators in ID or metadata
        signal_id = str(getattr(signal, "signal_id", ""))
        if any(
            keyword in signal_id.lower()
            for keyword in ["urgent", "critical", "flash", "fast"]
        ):
            urgency_score += 25

        # 6. Price proximity to extreme values (for prediction markets)
        if hasattr(signal, "price"):
            price = getattr(signal, "price", 0.5)
            # Prices very close to 0 or 1 are often time-sensitive
            price_distance = min(price, 1 - price)
            if price_distance < 0.05:  # Within 5% of extreme
                urgency_score += 15
            elif price_distance < 0.1:  # Within 10% of extreme
                urgency_score += 8

        # 7. Large position sizes suggest urgency
        if hasattr(signal, "size"):
            size = getattr(signal, "size", 0)
            if size > 100:  # Large positions
                urgency_score += 10
            elif size > 50:
                urgency_score += 5

        # Determine timeout tier based on urgency score
        if urgency_score >= 60:
            timeout = self.config.critical_timeout
            tier = "CRITICAL"
        elif urgency_score >= 30:
            timeout = self.config.high_timeout
            tier = "HIGH"
        elif urgency_score >= 10:
            timeout = self.config.normal_timeout
            tier = "NORMAL"
        else:
            timeout = self.config.low_timeout
            tier = "LOW"

        logger.debug(
            f"Signal {getattr(signal, 'signal_id', 'unknown')} urgency analysis: "
            f"score={urgency_score}, tier={tier}, timeout={timeout}s"
        )

        return timeout

    async def _process_signal_phases(
        self,
        signal: TradingSignal,
        result: ProcessingResult,
        market_metrics: MarketMetrics | None,
        portfolio_state: PortfolioState | None,
        validation_level: ValidationLevel | None,
    ) -> None:
        """Execute all signal processing phases with timeout management."""
        # Phase 1: Basic signal validation
        await self._validate_signal(signal, result, validation_level)

        if result.status == ProcessingStatus.BLOCKED:
            return

        # Phase 2: Market condition assessment
        if self.config.require_market_assessment and market_metrics:
            await self._assess_market_conditions(signal, market_metrics, result)

        # Phase 3: Risk assessment
        if portfolio_state:
            await self._assess_signal_risk(signal, portfolio_state, result)

        # Phase 4: Quality scoring and prioritization
        await self._calculate_quality_and_priority(result)

        # Phase 5: Final processing decision
        await self._make_processing_decision(result)

        # Phase 6: Generate execution recommendations
        await self._generate_execution_recommendations(result)

    async def process_signal(
        self,
        signal: TradingSignal,
        market_metrics: MarketMetrics | None = None,
        portfolio_state: PortfolioState | None = None,
        validation_level: ValidationLevel | None = None,
    ) -> ProcessingResult:
        """
        Process a single signal through the enhanced validation pipeline.

        Args:
            signal: Trading signal to process
            market_metrics: Optional market metrics for market condition assessment
            portfolio_state: Optional portfolio state for risk assessment
            validation_level: Level of validation to apply

        Returns:
            ProcessingResult with comprehensive analysis
        """
        start_time = time.time()
        signal_id = signal.signal_id or f"signal_{int(time.time() * 1000)}"
        signal.signal_id = signal_id

        # Determine appropriate timeout based on signal urgency
        processing_timeout = self._determine_processing_timeout(signal)

        # Initialize result
        result = ProcessingResult(
            signal=signal,
            status=ProcessingStatus.PROCESSING,
            priority=SignalPriority.NORMAL,
        )

        try:
            # Rate limiting check
            if not await self._check_rate_limits(result):
                return result

            # Process with dynamic timeout
            async with self._processing_semaphore:
                await asyncio.wait_for(
                    self._process_signal_phases(
                        signal,
                        result,
                        market_metrics,
                        portfolio_state,
                        validation_level,
                    ),
                    timeout=processing_timeout,
                )

        except TimeoutError:
            logger.warning(
                f"Signal processing timeout for {signal_id} after {processing_timeout}s "
                f"(urgency-based timeout)"
            )
            result.status = ProcessingStatus.REJECTED
            result.safety_flags.append(f"PROCESSING_TIMEOUT_{processing_timeout}s")

        except Exception as e:
            logger.error(f"Error processing signal {signal_id}: {e}")
            result.status = ProcessingStatus.REJECTED
            result.safety_flags.append(f"PROCESSING_ERROR: {str(e)}")

        finally:
            result.processing_time = time.time() - start_time
            self._update_processing_stats(result, processing_timeout)

            # Cache result
            self._results_cache[signal_id] = result

        return result

    async def process_batch(
        self,
        signals: list[TradingSignal],
        market_data: dict[str, MarketMetrics] | None = None,
        portfolio_state: PortfolioState | None = None,
        validation_level: ValidationLevel | None = None,
    ) -> list[ProcessingResult]:
        """
        Process batch of signals in parallel.

        Args:
            signals: List of signals to process
            market_data: Dictionary of market metrics keyed by market_slug
            portfolio_state: Portfolio state for risk assessment
            validation_level: Validation level to apply

        Returns:
            List of ProcessingResult objects
        """
        if not signals:
            return []

        # Create processing tasks
        tasks = []
        for signal in signals:
            market_metrics = None
            if market_data and signal.market_slug in market_data:
                market_metrics = market_data[signal.market_slug]

            task = asyncio.create_task(
                self.process_signal(
                    signal, market_metrics, portfolio_state, validation_level
                )
            )
            tasks.append(task)

        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error processing signal {i}: {result}")
                # Create error result
                error_result = ProcessingResult(
                    signal=signals[i],
                    status=ProcessingStatus.REJECTED,
                    priority=SignalPriority.LOW,
                )
                error_result.safety_flags.append(
                    f"BATCH_PROCESSING_ERROR: {str(result)}"
                )
                processed_results.append(error_result)
            else:
                processed_results.append(result)

        return processed_results

    async def _check_rate_limits(self, result: ProcessingResult) -> bool:
        """Check processing rate limits."""
        current_time = time.time()

        # Clean old timestamps
        minute_ago = current_time - 60
        self._processing_timestamps = [
            t for t in self._processing_timestamps if t > minute_ago
        ]

        # Check rate limit
        if len(self._processing_timestamps) >= self.config.max_processing_rate:
            result.status = ProcessingStatus.BLOCKED
            result.safety_flags.append("RATE_LIMIT_EXCEEDED")
            return False

        # Record this processing
        self._processing_timestamps.append(current_time)
        return True

    async def _validate_signal(
        self,
        signal: TradingSignal,
        result: ProcessingResult,
        validation_level: ValidationLevel | None,
    ):
        """Phase 1: Basic signal validation."""
        try:
            # Convert market metrics to MarketCondition if available
            market_condition = None
            if signal.market_slug in self.market_validator._assessments_cache:
                assessment = self.market_validator._assessments_cache[
                    signal.market_slug + "_" + signal.token_id
                ]
                market_condition = MarketCondition(
                    market_slug=signal.market_slug,
                    token_id=signal.token_id,
                    current_price=assessment.metrics.current_price,
                    bid_price=assessment.metrics.bid_price,
                    ask_price=assessment.metrics.ask_price,
                    volume_24h=assessment.metrics.volume_24h,
                    volatility=assessment.metrics.volatility_1h,
                    spread_bps=assessment.metrics.spread_bps,
                    last_trade_time=assessment.metrics.last_trade_time,
                    is_active=assessment.metrics.is_active,
                    liquidity_score=(
                        assessment.metrics.depth_2pct / 100
                        if assessment.metrics.depth_2pct
                        else None
                    ),
                )

            # Perform validation
            validation_result = self.signal_validator.validate_signal(
                signal, market_condition, validation_level
            )

            result.validation_result = validation_result

            # Update result based on validation
            if validation_result.status == ValidationStatus.BLOCKED:
                result.status = ProcessingStatus.BLOCKED
                result.safety_flags.extend(validation_result.errors)
            elif validation_result.status == ValidationStatus.REJECTED:
                result.status = ProcessingStatus.REJECTED
                result.safety_flags.extend(validation_result.errors)
            elif validation_result.status == ValidationStatus.WARNING:
                result.warning_flags.extend(validation_result.warnings)

        except Exception as e:
            logger.error(f"Signal validation error: {e}")
            result.status = ProcessingStatus.REJECTED
            result.safety_flags.append(f"VALIDATION_ERROR: {str(e)}")

    async def _assess_market_conditions(
        self,
        signal: TradingSignal,
        market_metrics: MarketMetrics,
        result: ProcessingResult,
    ):
        """Phase 2: Market condition assessment."""
        try:
            assessment = self.market_validator.validate_market_condition(market_metrics)
            result.market_assessment = assessment

            # Check minimum market score
            if assessment.overall_score < self.config.min_market_score:
                result.status = ProcessingStatus.REJECTED
                result.safety_flags.append(
                    f"POOR_MARKET_CONDITIONS: score={assessment.overall_score:.1f}"
                )

            # Add market-specific flags
            if assessment.risk_flags:
                result.risk_flags.extend(assessment.risk_flags)

            # Add trading recommendations as constraints
            if assessment.trading_recommendations:
                result.execution_constraints["market_recommendations"] = (
                    assessment.trading_recommendations
                )

        except Exception as e:
            logger.error(f"Market assessment error: {e}")
            result.warning_flags.append(f"MARKET_ASSESSMENT_FAILED: {str(e)}")

    async def _assess_signal_risk(
        self,
        signal: TradingSignal,
        portfolio_state: PortfolioState,
        result: ProcessingResult,
    ):
        """Phase 3: Risk assessment."""
        try:
            self.risk_validator.set_portfolio_state(portfolio_state)

            # Get market volatility and liquidity from market assessment
            market_volatility = None
            market_liquidity = None

            if result.market_assessment:
                market_volatility = result.market_assessment.metrics.volatility_1h
                market_liquidity = result.market_assessment.metrics.depth_2pct

            risk_metrics = self.risk_validator.validate_signal_risk(
                signal, market_volatility, market_liquidity
            )

            result.risk_metrics = risk_metrics

            # Check risk tolerance
            if (
                self.config.auto_reject_extreme_risk
                and risk_metrics.overall_risk_level == RiskLevel.EXTREME
            ):
                result.status = ProcessingStatus.REJECTED
                result.safety_flags.append("EXTREME_RISK_REJECTED")
            elif risk_metrics.overall_risk_level == RiskLevel.HIGH:
                result.warning_flags.append("HIGH_RISK_SIGNAL")

            # Add risk factors as flags
            if risk_metrics.risk_factors:
                result.risk_flags.extend(risk_metrics.risk_factors)

            if risk_metrics.risk_warnings:
                result.warning_flags.extend(risk_metrics.risk_warnings)

            # Calculate size adjustment based on risk
            if risk_metrics.overall_risk_level in [RiskLevel.HIGH, RiskLevel.EXTREME]:
                # Reduce position size for high-risk signals
                risk_multiplier = (
                    0.5 if risk_metrics.overall_risk_level == RiskLevel.HIGH else 0.25
                )
                result.recommended_size_adjustment = risk_multiplier

        except Exception as e:
            logger.error(f"Risk assessment error: {e}")
            result.warning_flags.append(f"RISK_ASSESSMENT_FAILED: {str(e)}")

    async def _calculate_quality_and_priority(self, result: ProcessingResult):
        """Phase 4: Calculate overall quality score and priority."""
        try:
            scores = []
            weights = []

            # Validation quality score
            if result.validation_result:
                scores.append(result.validation_result.score)
                weights.append(self.config.quality_weight)

            # Market condition score
            if result.market_assessment:
                scores.append(result.market_assessment.overall_score)
                weights.append(self.config.market_weight)

            # Risk score (inverted - lower risk = higher score)
            if result.risk_metrics:
                risk_score = 100.0 - result.risk_metrics.overall_risk_score
                scores.append(risk_score)
                weights.append(self.config.risk_weight)

            # Timing score (fresher signals get higher score)
            signal_age = time.time() - result.signal.created_at
            timing_score = max(
                0, 100 - (signal_age / 300) * 100
            )  # Decay over 5 minutes
            scores.append(timing_score)
            weights.append(self.config.timing_weight)

            # Calculate weighted average
            if scores and weights:
                total_weight = sum(weights)
                weighted_sum = sum(
                    score * weight
                    for score, weight in zip(scores, weights, strict=False)
                )
                result.overall_quality_score = weighted_sum / total_weight
            else:
                result.overall_quality_score = 50.0  # Default neutral score

            # Determine priority based on quality score
            if result.overall_quality_score >= 90:
                result.priority = SignalPriority.CRITICAL
            elif result.overall_quality_score >= 80:
                result.priority = SignalPriority.HIGH
            elif result.overall_quality_score >= 60:
                result.priority = SignalPriority.NORMAL
            else:
                result.priority = SignalPriority.LOW

        except Exception as e:
            logger.error(f"Quality calculation error: {e}")
            result.overall_quality_score = 0.0
            result.priority = SignalPriority.LOW

    async def _make_processing_decision(self, result: ProcessingResult):
        """Phase 5: Make final processing decision."""
        # Skip if already blocked or rejected
        if result.status in [ProcessingStatus.BLOCKED, ProcessingStatus.REJECTED]:
            return

        # Check quality thresholds
        if result.overall_quality_score < self.config.min_acceptable_score:
            result.status = ProcessingStatus.REJECTED
            result.safety_flags.append(
                f"QUALITY_TOO_LOW: {result.overall_quality_score:.1f}"
            )
            return

        # Determine final status
        if (
            result.overall_quality_score >= self.config.min_quality_score
            and not result.warning_flags
        ):
            result.status = ProcessingStatus.APPROVED
        elif result.overall_quality_score >= self.config.min_quality_score:
            result.status = ProcessingStatus.WARNING
        else:
            result.status = ProcessingStatus.WARNING

    async def _generate_execution_recommendations(self, result: ProcessingResult):
        """Phase 6: Generate execution recommendations."""
        try:
            recommendations = []

            # Base recommendation
            if result.status == ProcessingStatus.APPROVED:
                recommendations.append("Signal approved for execution")
            elif result.status == ProcessingStatus.WARNING:
                recommendations.append("Execute with caution - warnings present")
            else:
                recommendations.append("Do not execute")
                result.execution_recommendation = "; ".join(recommendations)
                return

            # Size adjustment recommendations
            if (
                result.recommended_size_adjustment
                and result.recommended_size_adjustment < 1.0
            ):
                recommendations.append(
                    f"Reduce position size by {(1-result.recommended_size_adjustment)*100:.0f}%"
                )

            # Market condition recommendations
            if (
                result.market_assessment
                and result.market_assessment.trading_recommendations
            ):
                recommendations.extend(result.market_assessment.trading_recommendations)

            # Risk-based recommendations
            if result.risk_metrics:
                if result.risk_metrics.overall_risk_level == RiskLevel.HIGH:
                    recommendations.append("Monitor position closely")
                    result.recommended_timeout = 300  # 5 minutes
                elif result.risk_metrics.overall_risk_level == RiskLevel.EXTREME:
                    recommendations.append("Consider avoiding this trade")

            # Priority-based recommendations
            if result.priority in [SignalPriority.HIGH, SignalPriority.CRITICAL]:
                recommendations.append("Execute with high priority")
                result.execution_constraints["priority"] = "high"

            result.execution_recommendation = "; ".join(recommendations)

        except Exception as e:
            logger.error(f"Execution recommendation error: {e}")
            result.execution_recommendation = "Execute with standard parameters"

    def _update_processing_stats(
        self, result: ProcessingResult, timeout_used: int = None
    ):
        """Update processing statistics."""
        stats = self._processing_stats

        stats["total_processed"] += 1

        if result.status == ProcessingStatus.APPROVED:
            stats["approved_signals"] += 1
        elif result.status == ProcessingStatus.REJECTED:
            stats["rejected_signals"] += 1
            # Check if it was a timeout error
            if any("PROCESSING_TIMEOUT" in flag for flag in result.safety_flags):
                stats["timeout_errors"] += 1
        elif result.status == ProcessingStatus.WARNING:
            stats["warning_signals"] += 1
        elif result.status == ProcessingStatus.BLOCKED:
            stats["blocked_signals"] += 1

        # Track timeout tier usage
        if timeout_used is not None:
            if timeout_used == self.config.critical_timeout:
                stats["critical_timeouts_used"] += 1
            elif timeout_used == self.config.high_timeout:
                stats["high_timeouts_used"] += 1
            elif timeout_used == self.config.normal_timeout:
                stats["normal_timeouts_used"] += 1
            elif timeout_used == self.config.low_timeout:
                stats["low_timeouts_used"] += 1

        # Update averages
        count = stats["total_processed"]
        current_avg_time = stats["avg_processing_time"]
        stats["avg_processing_time"] = (
            (current_avg_time * (count - 1)) + result.processing_time
        ) / count

        current_avg_quality = stats["avg_quality_score"]
        stats["avg_quality_score"] = (
            (current_avg_quality * (count - 1)) + result.overall_quality_score
        ) / count

        # Risk tracking
        if result.risk_metrics and result.risk_metrics.overall_risk_level in [
            RiskLevel.HIGH,
            RiskLevel.EXTREME,
        ]:
            stats["high_risk_count"] += 1

    def get_processed_result(self, signal_id: str) -> ProcessingResult | None:
        """Get cached processing result."""
        return self._results_cache.get(signal_id)

    def get_processing_stats(self) -> dict[str, Any]:
        """Get processing statistics with timeout tier information."""
        stats = self._processing_stats.copy()

        if stats["total_processed"] > 0:
            stats["approval_rate"] = (
                stats["approved_signals"] / stats["total_processed"]
            )
            stats["rejection_rate"] = (
                stats["rejected_signals"] / stats["total_processed"]
            )
            stats["warning_rate"] = stats["warning_signals"] / stats["total_processed"]
            stats["timeout_error_rate"] = (
                stats["timeout_errors"] / stats["total_processed"]
            )

            # Timeout tier usage rates
            total_timeouts = (
                stats["critical_timeouts_used"]
                + stats["high_timeouts_used"]
                + stats["normal_timeouts_used"]
                + stats["low_timeouts_used"]
            )

            if total_timeouts > 0:
                stats["critical_timeout_usage_rate"] = (
                    stats["critical_timeouts_used"] / total_timeouts
                )
                stats["high_timeout_usage_rate"] = (
                    stats["high_timeouts_used"] / total_timeouts
                )
                stats["normal_timeout_usage_rate"] = (
                    stats["normal_timeouts_used"] / total_timeouts
                )
                stats["low_timeout_usage_rate"] = (
                    stats["low_timeouts_used"] / total_timeouts
                )

            # Timeout efficiency metrics
            stats["avg_timeout_saved"] = self._calculate_avg_timeout_saved()

        return stats

    def _calculate_avg_timeout_saved(self) -> float:
        """Calculate average timeout savings from tiered system."""
        stats = self._processing_stats
        default_timeout = self.config.normal_timeout  # Use normal as baseline

        total_saved = 0.0
        total_signals = 0

        # Calculate savings for each tier
        critical_saved = (default_timeout - self.config.critical_timeout) * stats[
            "critical_timeouts_used"
        ]
        high_saved = (default_timeout - self.config.high_timeout) * stats[
            "high_timeouts_used"
        ]
        low_cost = (self.config.low_timeout - default_timeout) * stats[
            "low_timeouts_used"
        ]

        total_saved = critical_saved + high_saved - low_cost
        total_signals = (
            stats["critical_timeouts_used"]
            + stats["high_timeouts_used"]
            + stats["normal_timeouts_used"]
            + stats["low_timeouts_used"]
        )

        return total_saved / total_signals if total_signals > 0 else 0.0

    def get_timeout_configuration(self) -> dict[str, int]:
        """Get current timeout tier configuration."""
        return {
            "critical_timeout": self.config.critical_timeout,
            "high_timeout": self.config.high_timeout,
            "normal_timeout": self.config.normal_timeout,
            "low_timeout": self.config.low_timeout,
            "default_fallback": self.config.processing_timeout,
        }

    def clear_cache(self, max_age_seconds: int = 3600):
        """Clear old cached results."""
        current_time = time.time()
        expired_keys = [
            key
            for key, result in self._results_cache.items()
            if current_time - result.processed_at > max_age_seconds
        ]

        for key in expired_keys:
            del self._results_cache[key]

        if expired_keys:
            logger.debug(
                f"Cleared {len(expired_keys)} expired processing cache entries"
            )


# Utility functions


async def process_trading_signal(
    signal: TradingSignal,
    market_metrics: MarketMetrics | None = None,
    portfolio_state: PortfolioState | None = None,
    config: ProcessingConfig | None = None,
) -> ProcessingResult:
    """
    Convenience function to process a single trading signal.

    Args:
        signal: Trading signal to process
        market_metrics: Optional market metrics
        portfolio_state: Optional portfolio state
        config: Optional processing configuration

    Returns:
        ProcessingResult
    """
    processor = EnhancedSignalProcessor(config)
    return await processor.process_signal(signal, market_metrics, portfolio_state)


def is_signal_approved(result: ProcessingResult) -> bool:
    """Check if signal is approved for execution."""
    return result.status in [ProcessingStatus.APPROVED, ProcessingStatus.WARNING]


def get_execution_priority(result: ProcessingResult) -> int:
    """Get numeric execution priority (higher = more urgent)."""
    priority_map = {
        SignalPriority.LOW: 1,
        SignalPriority.NORMAL: 2,
        SignalPriority.HIGH: 3,
        SignalPriority.URGENT: 4,
        SignalPriority.CRITICAL: 5,
    }
    return priority_map.get(result.priority, 2)
