"""
Market condition validation module for enhanced signal processing.

This module provides comprehensive market condition checks including:
- Real-time market data validation
- Liquidity assessment
- Volatility analysis
- Market health monitoring
- Trading halt detection
"""

from __future__ import annotations

import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("market_condition_validator")


class MarketStatus(str, Enum):
    """Market status classifications."""

    ACTIVE = "active"  # Normal trading conditions
    VOLATILE = "volatile"  # High volatility conditions
    ILLIQUID = "illiquid"  # Low liquidity conditions
    STALE = "stale"  # Stale/outdated data
    HALTED = "halted"  # Trading halted
    CLOSED = "closed"  # Market closed
    UNKNOWN = "unknown"  # Status unknown


class LiquidityLevel(str, Enum):
    """Liquidity level classifications."""

    EXCELLENT = "excellent"  # Very high liquidity
    GOOD = "good"  # Good liquidity
    MODERATE = "moderate"  # Moderate liquidity
    POOR = "poor"  # Poor liquidity
    VERY_POOR = "very_poor"  # Very poor liquidity


class VolatilityLevel(str, Enum):
    """Volatility level classifications."""

    VERY_LOW = "very_low"  # Very low volatility
    LOW = "low"  # Low volatility
    MODERATE = "moderate"  # Moderate volatility
    HIGH = "high"  # High volatility
    EXTREME = "extreme"  # Extreme volatility


@dataclass
class MarketMetrics:
    """Real-time market metrics."""

    market_slug: str
    token_id: str
    timestamp: float = field(default_factory=time.time)

    # Price metrics
    current_price: float = 0.0
    bid_price: float | None = None
    ask_price: float | None = None
    mid_price: float | None = None
    last_trade_price: float | None = None

    # Volume and liquidity
    volume_24h: float = 0.0
    volume_1h: float = 0.0
    total_bid_size: float = 0.0
    total_ask_size: float = 0.0
    depth_2pct: float = 0.0  # Liquidity within 2% of mid
    depth_5pct: float = 0.0  # Liquidity within 5% of mid

    # Spread metrics
    spread_absolute: float | None = None
    spread_bps: float | None = None
    spread_percentage: float | None = None

    # Volatility metrics
    price_change_1h: float | None = None
    price_change_24h: float | None = None
    volatility_1h: float | None = None
    volatility_24h: float | None = None

    # Trade metrics
    trade_count_1h: int = 0
    trade_count_24h: int = 0
    last_trade_time: float | None = None
    avg_trade_size: float | None = None

    # Market health indicators
    is_active: bool = True
    is_halted: bool = False
    data_freshness_seconds: float = 0.0


@dataclass
class MarketConditionThresholds:
    """Configurable thresholds for market condition assessment."""

    # Liquidity thresholds
    excellent_liquidity_threshold: float = 1000.0
    good_liquidity_threshold: float = 500.0
    moderate_liquidity_threshold: float = 100.0
    poor_liquidity_threshold: float = 50.0

    # Volatility thresholds (as percentages)
    low_volatility_threshold: float = 0.05  # 5%
    moderate_volatility_threshold: float = 0.15  # 15%
    high_volatility_threshold: float = 0.30  # 30%
    extreme_volatility_threshold: float = 0.50  # 50%

    # Spread thresholds (in basis points)
    tight_spread_threshold: float = 50  # 0.5%
    acceptable_spread_threshold: float = 200  # 2%
    wide_spread_threshold: float = 500  # 5%
    very_wide_spread_threshold: float = 1000  # 10%

    # Data freshness thresholds (seconds)
    fresh_data_threshold: float = 60  # 1 minute
    acceptable_data_threshold: float = 300  # 5 minutes
    stale_data_threshold: float = 900  # 15 minutes

    # Volume thresholds
    high_volume_threshold: float = 10000.0
    moderate_volume_threshold: float = 1000.0
    low_volume_threshold: float = 100.0

    # Trade activity thresholds
    active_trade_threshold: int = 10  # trades per hour
    moderate_trade_threshold: int = 3  # trades per hour


class MarketConditionAssessment:
    """Comprehensive market condition assessment."""

    def __init__(
        self,
        metrics: MarketMetrics,
        thresholds: MarketConditionThresholds | None = None,
    ):
        self.metrics = metrics
        self.thresholds = thresholds or MarketConditionThresholds()
        self.timestamp = time.time()

        # Calculate derived assessments
        self.status = self._assess_market_status()
        self.liquidity_level = self._assess_liquidity_level()
        self.volatility_level = self._assess_volatility_level()
        self.data_quality_score = self._calculate_data_quality_score()
        self.overall_score = self._calculate_overall_score()

        # Risk flags
        self.risk_flags = self._identify_risk_flags()

        # Recommendations
        self.trading_recommendations = self._generate_trading_recommendations()

    def _assess_market_status(self) -> MarketStatus:
        """Assess overall market status."""
        if not self.metrics.is_active:
            return MarketStatus.CLOSED

        if self.metrics.is_halted:
            return MarketStatus.HALTED

        # Check data freshness
        if self.metrics.data_freshness_seconds > self.thresholds.stale_data_threshold:
            return MarketStatus.STALE

        # Check volatility
        if (
            self.metrics.volatility_1h is not None
            and self.metrics.volatility_1h
            > self.thresholds.extreme_volatility_threshold
        ):
            return MarketStatus.VOLATILE

        # Check liquidity
        total_liquidity = self.metrics.total_bid_size + self.metrics.total_ask_size
        if total_liquidity < self.thresholds.poor_liquidity_threshold:
            return MarketStatus.ILLIQUID

        return MarketStatus.ACTIVE

    def _assess_liquidity_level(self) -> LiquidityLevel:
        """Assess market liquidity level."""
        # Use depth within 2% as primary liquidity measure
        liquidity_measure = self.metrics.depth_2pct

        if liquidity_measure >= self.thresholds.excellent_liquidity_threshold:
            return LiquidityLevel.EXCELLENT
        elif liquidity_measure >= self.thresholds.good_liquidity_threshold:
            return LiquidityLevel.GOOD
        elif liquidity_measure >= self.thresholds.moderate_liquidity_threshold:
            return LiquidityLevel.MODERATE
        elif liquidity_measure >= self.thresholds.poor_liquidity_threshold:
            return LiquidityLevel.POOR
        else:
            return LiquidityLevel.VERY_POOR

    def _assess_volatility_level(self) -> VolatilityLevel:
        """Assess market volatility level."""
        # Use 1-hour volatility as primary measure
        volatility = self.metrics.volatility_1h or 0.0

        if volatility >= self.thresholds.extreme_volatility_threshold:
            return VolatilityLevel.EXTREME
        elif volatility >= self.thresholds.high_volatility_threshold:
            return VolatilityLevel.HIGH
        elif volatility >= self.thresholds.moderate_volatility_threshold:
            return VolatilityLevel.MODERATE
        elif volatility >= self.thresholds.low_volatility_threshold:
            return VolatilityLevel.LOW
        else:
            return VolatilityLevel.VERY_LOW

    def _calculate_data_quality_score(self) -> float:
        """Calculate data quality score (0-100)."""
        score = 100.0

        # Penalize stale data
        if self.metrics.data_freshness_seconds > self.thresholds.fresh_data_threshold:
            staleness_penalty = min(50, self.metrics.data_freshness_seconds / 60 * 5)
            score -= staleness_penalty

        # Penalize missing data
        missing_fields = 0
        total_fields = 0

        optional_fields = [
            "bid_price",
            "ask_price",
            "volume_24h",
            "volatility_1h",
            "last_trade_time",
            "spread_bps",
        ]

        for field in optional_fields:
            total_fields += 1
            if getattr(self.metrics, field) is None:
                missing_fields += 1

        if total_fields > 0:
            completeness_score = (total_fields - missing_fields) / total_fields * 100
            score = score * (completeness_score / 100)

        return max(0, min(100, score))

    def _calculate_overall_score(self) -> float:
        """Calculate overall market condition score (0-100)."""
        # Component scores
        liquidity_score = self._get_liquidity_score()
        volatility_score = self._get_volatility_score()
        activity_score = self._get_activity_score()
        spread_score = self._get_spread_score()

        # Weighted average
        overall = (
            liquidity_score * 0.3
            + volatility_score * 0.25
            + activity_score * 0.25
            + spread_score * 0.20
        )

        # Apply data quality multiplier
        overall *= self.data_quality_score / 100

        return max(0, min(100, overall))

    def _get_liquidity_score(self) -> float:
        """Get liquidity component score."""
        level_scores = {
            LiquidityLevel.EXCELLENT: 100,
            LiquidityLevel.GOOD: 80,
            LiquidityLevel.MODERATE: 60,
            LiquidityLevel.POOR: 40,
            LiquidityLevel.VERY_POOR: 20,
        }
        return level_scores.get(self.liquidity_level, 0)

    def _get_volatility_score(self) -> float:
        """Get volatility component score (inverted - lower volatility = higher score)."""
        level_scores = {
            VolatilityLevel.VERY_LOW: 100,
            VolatilityLevel.LOW: 80,
            VolatilityLevel.MODERATE: 60,
            VolatilityLevel.HIGH: 40,
            VolatilityLevel.EXTREME: 20,
        }
        return level_scores.get(self.volatility_level, 0)

    def _get_activity_score(self) -> float:
        """Get trading activity component score."""
        if self.metrics.trade_count_1h >= self.thresholds.active_trade_threshold:
            return 100
        elif self.metrics.trade_count_1h >= self.thresholds.moderate_trade_threshold:
            return 70
        elif self.metrics.trade_count_1h > 0:
            return 40
        else:
            return 20

    def _get_spread_score(self) -> float:
        """Get spread component score."""
        if self.metrics.spread_bps is None:
            return 50  # Neutral score if unknown

        spread = self.metrics.spread_bps

        if spread <= self.thresholds.tight_spread_threshold:
            return 100
        elif spread <= self.thresholds.acceptable_spread_threshold:
            return 80
        elif spread <= self.thresholds.wide_spread_threshold:
            return 60
        elif spread <= self.thresholds.very_wide_spread_threshold:
            return 40
        else:
            return 20

    def _identify_risk_flags(self) -> list[str]:
        """Identify risk flags based on market conditions."""
        flags = []

        if self.status == MarketStatus.HALTED:
            flags.append("TRADING_HALTED")

        if self.status == MarketStatus.STALE:
            flags.append("STALE_DATA")

        if self.liquidity_level in [LiquidityLevel.POOR, LiquidityLevel.VERY_POOR]:
            flags.append("LOW_LIQUIDITY")

        if self.volatility_level == VolatilityLevel.EXTREME:
            flags.append("EXTREME_VOLATILITY")

        if (
            self.metrics.spread_bps is not None
            and self.metrics.spread_bps > self.thresholds.very_wide_spread_threshold
        ):
            flags.append("WIDE_SPREAD")

        if self.metrics.trade_count_1h == 0:
            flags.append("NO_RECENT_TRADES")

        if self.data_quality_score < 50:
            flags.append("POOR_DATA_QUALITY")

        return flags

    def _generate_trading_recommendations(self) -> list[str]:
        """Generate trading recommendations based on conditions."""
        recommendations = []

        if self.status != MarketStatus.ACTIVE:
            recommendations.append("AVOID_TRADING")
            return recommendations

        if self.liquidity_level == LiquidityLevel.VERY_POOR:
            recommendations.append("USE_SMALL_SIZES")
            recommendations.append("AVOID_MARKET_ORDERS")

        if self.volatility_level == VolatilityLevel.EXTREME:
            recommendations.append("REDUCE_POSITION_SIZES")
            recommendations.append("USE_WIDER_STOPS")

        if (
            self.metrics.spread_bps is not None
            and self.metrics.spread_bps > self.thresholds.wide_spread_threshold
        ):
            recommendations.append("AVOID_MARKET_ORDERS")
            recommendations.append("USE_LIMIT_ORDERS")

        if self.overall_score >= 80:
            recommendations.append("FAVORABLE_CONDITIONS")
        elif self.overall_score < 50:
            recommendations.append("UNFAVORABLE_CONDITIONS")

        return recommendations


class MarketConditionValidator:
    """
    Validator for market conditions with historical tracking and trend analysis.
    """

    def __init__(self, thresholds: MarketConditionThresholds | None = None):
        self.thresholds = thresholds or MarketConditionThresholds()

        # Historical data tracking
        self._historical_metrics: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=100)
        )
        self._assessments_cache: dict[str, MarketConditionAssessment] = {}

        # Trend tracking
        self._trend_data: dict[str, dict[str, deque]] = defaultdict(
            lambda: {
                "prices": deque(maxlen=50),
                "volumes": deque(maxlen=50),
                "spreads": deque(maxlen=50),
                "timestamps": deque(maxlen=50),
            }
        )

        # Statistics
        self._validation_stats = {
            "assessments_created": 0,
            "markets_tracked": 0,
            "risk_flags_raised": 0,
            "unfavorable_conditions": 0,
        }

        logger.info("MarketConditionValidator initialized")

    def validate_market_condition(
        self, metrics: MarketMetrics
    ) -> MarketConditionAssessment:
        """
        Validate market conditions and create assessment.

        Args:
            metrics: Current market metrics

        Returns:
            MarketConditionAssessment with comprehensive analysis
        """
        market_key = f"{metrics.market_slug}_{metrics.token_id}"

        # Create assessment
        assessment = MarketConditionAssessment(metrics, self.thresholds)

        # Store in cache
        self._assessments_cache[market_key] = assessment

        # Update historical data
        self._update_historical_data(market_key, metrics)

        # Update trend data
        self._update_trend_data(market_key, metrics)

        # Update statistics
        self._update_validation_stats(assessment)

        logger.debug(
            f"Market condition validated for {market_key}: "
            f"status={assessment.status.value}, score={assessment.overall_score:.1f}"
        )

        return assessment

    def _update_historical_data(self, market_key: str, metrics: MarketMetrics):
        """Update historical metrics data."""
        self._historical_metrics[market_key].append(
            {
                "timestamp": metrics.timestamp,
                "current_price": metrics.current_price,
                "volume_1h": metrics.volume_1h,
                "spread_bps": metrics.spread_bps,
                "volatility_1h": metrics.volatility_1h,
                "total_liquidity": metrics.total_bid_size + metrics.total_ask_size,
            }
        )

    def _update_trend_data(self, market_key: str, metrics: MarketMetrics):
        """Update trend analysis data."""
        trends = self._trend_data[market_key]

        trends["timestamps"].append(metrics.timestamp)
        trends["prices"].append(metrics.current_price)
        trends["volumes"].append(metrics.volume_1h)

        if metrics.spread_bps is not None:
            trends["spreads"].append(metrics.spread_bps)

    def _update_validation_stats(self, assessment: MarketConditionAssessment):
        """Update validation statistics."""
        self._validation_stats["assessments_created"] += 1

        if assessment.risk_flags:
            self._validation_stats["risk_flags_raised"] += len(assessment.risk_flags)

        if assessment.overall_score < 50:
            self._validation_stats["unfavorable_conditions"] += 1

        # Update markets tracked
        self._validation_stats["markets_tracked"] = len(self._assessments_cache)

    def get_market_trends(self, market_slug: str, token_id: str) -> dict[str, Any]:
        """Get trend analysis for a market."""
        market_key = f"{market_slug}_{token_id}"

        if market_key not in self._trend_data:
            return {}

        trends = self._trend_data[market_key]

        # Calculate trends
        price_trend = self._calculate_trend(list(trends["prices"]))
        volume_trend = self._calculate_trend(list(trends["volumes"]))

        return {
            "price_trend": price_trend,
            "volume_trend": volume_trend,
            "data_points": len(trends["prices"]),
            "time_span_hours": (
                (trends["timestamps"][-1] - trends["timestamps"][0]) / 3600
                if len(trends["timestamps"]) > 1
                else 0
            ),
        }

    def _calculate_trend(self, values: list[float]) -> dict[str, Any]:
        """Calculate trend statistics for a series of values."""
        if len(values) < 2:
            return {"direction": "insufficient_data", "strength": 0.0}

        # Simple linear trend
        x = list(range(len(values)))
        n = len(values)

        sum_x = sum(x)
        sum_y = sum(values)
        sum_xy = sum(xi * yi for xi, yi in zip(x, values, strict=False))
        sum_x2 = sum(xi * xi for xi in x)

        # Calculate slope
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)

        # Determine trend direction and strength
        if abs(slope) < 0.001:
            direction = "flat"
            strength = 0.0
        elif slope > 0:
            direction = "increasing"
            strength = min(1.0, abs(slope) * 100)
        else:
            direction = "decreasing"
            strength = min(1.0, abs(slope) * 100)

        # Calculate volatility
        mean_val = statistics.mean(values)
        volatility = statistics.stdev(values) / mean_val if mean_val > 0 else 0

        return {
            "direction": direction,
            "strength": strength,
            "slope": slope,
            "volatility": volatility,
            "current_vs_start": (values[-1] / values[0] - 1) if values[0] != 0 else 0,
        }

    def get_cached_assessment(
        self, market_slug: str, token_id: str
    ) -> MarketConditionAssessment | None:
        """Get cached market condition assessment."""
        market_key = f"{market_slug}_{token_id}"
        return self._assessments_cache.get(market_key)

    def is_market_favorable(
        self, market_slug: str, token_id: str, min_score: float = 60.0
    ) -> bool:
        """Check if market conditions are favorable for trading."""
        assessment = self.get_cached_assessment(market_slug, token_id)

        if not assessment:
            return False

        return (
            assessment.status == MarketStatus.ACTIVE
            and assessment.overall_score >= min_score
            and "TRADING_HALTED" not in assessment.risk_flags
        )

    def get_validation_stats(self) -> dict[str, Any]:
        """Get validation statistics."""
        return self._validation_stats.copy()

    def clear_cache(self, max_age_seconds: int = 3600):
        """Clear old cached assessments."""
        current_time = time.time()
        expired_keys = [
            key
            for key, assessment in self._assessments_cache.items()
            if current_time - assessment.timestamp > max_age_seconds
        ]

        for key in expired_keys:
            del self._assessments_cache[key]

        if expired_keys:
            logger.debug(
                f"Cleared {len(expired_keys)} expired market condition cache entries"
            )


# Utility functions


def create_market_metrics(market_slug: str, token_id: str, **kwargs) -> MarketMetrics:
    """
    Convenience function to create MarketMetrics object.

    Args:
        market_slug: Market identifier
        token_id: Token identifier
        **kwargs: Additional market metrics parameters

    Returns:
        MarketMetrics object
    """
    return MarketMetrics(market_slug=market_slug, token_id=token_id, **kwargs)


def assess_market_condition(
    metrics: MarketMetrics, thresholds: MarketConditionThresholds | None = None
) -> MarketConditionAssessment:
    """
    Convenience function to assess market conditions.

    Args:
        metrics: Market metrics to assess
        thresholds: Optional custom thresholds

    Returns:
        MarketConditionAssessment
    """
    return MarketConditionAssessment(metrics, thresholds)
