"""
Correlation-Based Risk Management System.

This module implements advanced correlation analysis for position risk management,
accounting for market correlations when calculating position limits and risk
adjustments. It provides a sophisticated layer of risk control that considers
the interdependencies between different market positions.

Key Features:
- Real-time correlation matrix calculation between markets and outcomes
- Dynamic position limit adjustments based on correlation strength
- Market sector correlation analysis (politics, sports, crypto, etc.)
- Temporal correlation patterns with volatility adjustment
- Portfolio-wide correlation risk assessment
- Automatic risk limit reduction for highly correlated positions

The system integrates with existing risk management to provide more accurate
risk assessments by considering how positions might move together during
market stress events.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("correlation_risk")


class CorrelationType(Enum):
    """Types of correlation analysis."""

    MARKET_CORRELATION = "market"  # Between different markets
    OUTCOME_CORRELATION = "outcome"  # Between YES/NO outcomes
    SECTOR_CORRELATION = "sector"  # Between market sectors
    TEMPORAL_CORRELATION = "temporal"  # Time-based correlation patterns


class CorrelationStrength(Enum):
    """Correlation strength classifications."""

    VERY_LOW = "very_low"  # |r| < 0.2
    LOW = "low"  # 0.2 <= |r| < 0.4
    MODERATE = "moderate"  # 0.4 <= |r| < 0.6
    HIGH = "high"  # 0.6 <= |r| < 0.8
    VERY_HIGH = "very_high"  # |r| >= 0.8


@dataclass
class CorrelationMetrics:
    """Correlation metrics between two entities."""

    entity_a: str
    entity_b: str
    correlation_coefficient: float
    p_value: float = 0.0
    covariance: float = 0.0
    sample_size: int = 0
    strength: CorrelationStrength = CorrelationStrength.VERY_LOW
    confidence_interval: Tuple[float, float] = (0.0, 0.0)
    last_updated: float = field(default_factory=time.time)

    def __post_init__(self):
        """Calculate correlation strength after initialization."""
        self.strength = self._classify_strength(abs(self.correlation_coefficient))

    def _classify_strength(self, abs_corr: float) -> CorrelationStrength:
        """Classify correlation strength based on absolute value."""
        if abs_corr < 0.2:
            return CorrelationStrength.VERY_LOW
        elif abs_corr < 0.4:
            return CorrelationStrength.LOW
        elif abs_corr < 0.6:
            return CorrelationStrength.MODERATE
        elif abs_corr < 0.8:
            return CorrelationStrength.HIGH
        else:
            return CorrelationStrength.VERY_HIGH


@dataclass
class RiskAdjustment:
    """Risk adjustment based on correlation analysis."""

    original_limit: float
    adjusted_limit: float
    adjustment_factor: float
    correlation_score: float
    affected_positions: List[str]
    reason: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class CorrelationRiskConfig:
    """Configuration for correlation-based risk management."""

    # Correlation thresholds
    high_correlation_threshold: float = 0.6
    moderate_correlation_threshold: float = 0.4
    low_correlation_threshold: float = 0.2

    # Risk adjustment factors
    high_correlation_penalty: float = 0.5  # 50% limit reduction
    moderate_correlation_penalty: float = 0.7  # 30% limit reduction
    low_correlation_penalty: float = 0.9  # 10% limit reduction

    # Market sectors and their correlations
    sector_correlations: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: {
            "politics": {"sports": 0.1, "crypto": 0.3, "economics": 0.7},
            "sports": {"politics": 0.1, "crypto": 0.2, "economics": 0.2},
            "crypto": {"politics": 0.3, "sports": 0.2, "economics": 0.6},
            "economics": {"politics": 0.7, "crypto": 0.6, "sports": 0.2},
        }
    )

    # Data requirements
    min_data_points: int = 10
    lookback_hours: int = 168  # 1 week
    correlation_update_interval: float = 300.0  # 5 minutes

    # Portfolio limits
    max_correlated_exposure: float = 0.4  # 40% of portfolio in correlated positions
    correlation_concentration_limit: float = 0.6  # Max 60% in highly correlated group


class CorrelationDataStore:
    """In-memory storage for correlation calculation data."""

    def __init__(self, max_data_points: int = 1000):
        self.max_data_points = max_data_points
        self.price_data: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_data_points)
        )
        self.exposure_data: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_data_points)
        )
        self.timestamp_data: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_data_points)
        )

    def add_market_data(
        self, market_id: str, price: float, exposure: float, timestamp: float = None
    ):
        """Add market data point for correlation calculation."""
        if timestamp is None:
            timestamp = time.time()

        self.price_data[market_id].append(price)
        self.exposure_data[market_id].append(exposure)
        self.timestamp_data[market_id].append(timestamp)

    def get_market_series(
        self, market_id: str, lookback_hours: float
    ) -> Tuple[List[float], List[float]]:
        """Get price and exposure series for correlation calculation."""
        cutoff_time = time.time() - (lookback_hours * 3600)

        prices = []
        exposures = []

        timestamps = list(self.timestamp_data[market_id])
        price_series = list(self.price_data[market_id])
        exposure_series = list(self.exposure_data[market_id])

        for i, ts in enumerate(timestamps):
            if ts >= cutoff_time and i < len(price_series) and i < len(exposure_series):
                prices.append(price_series[i])
                exposures.append(exposure_series[i])

        return prices, exposures

    def get_available_markets(self) -> List[str]:
        """Get list of markets with available data."""
        return [market for market, data in self.price_data.items() if len(data) > 0]


class CorrelationRiskManager:
    """
    Advanced correlation-based risk management system.

    Analyzes correlations between positions and markets to provide
    more accurate risk assessments and dynamic position limit adjustments.
    """

    def __init__(self, config: Optional[CorrelationRiskConfig] = None):
        self.config = config or CorrelationRiskConfig()
        self.data_store = CorrelationDataStore()

        # Correlation matrices
        self.market_correlations: Dict[str, Dict[str, CorrelationMetrics]] = {}
        self.sector_correlations: Dict[str, Dict[str, float]] = (
            self.config.sector_correlations
        )

        # Risk adjustments tracking
        self.active_adjustments: Dict[str, RiskAdjustment] = {}
        self.adjustment_history: List[RiskAdjustment] = []

        # Background tasks
        self._correlation_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info("CorrelationRiskManager initialized")

    async def start(self):
        """Start the correlation risk management system."""
        if self._running:
            return

        self._running = True
        self._correlation_task = asyncio.create_task(self._correlation_update_loop())
        logger.info("Correlation risk management system started")

    async def stop(self):
        """Stop the correlation risk management system."""
        if not self._running:
            return

        self._running = False

        if self._correlation_task:
            self._correlation_task.cancel()
            try:
                await self._correlation_task
            except asyncio.CancelledError:
                pass

        logger.info("Correlation risk management system stopped")

    def add_market_data(
        self,
        market_slug: str,
        current_price: float,
        exposure: float,
        metadata: Dict[str, Any] = None,
    ):
        """Add market data for correlation analysis."""
        self.data_store.add_market_data(market_slug, current_price, exposure)

        # Extract sector information if available
        if metadata and "sector" in metadata:
            self._update_sector_mapping(market_slug, metadata["sector"])

    def _update_sector_mapping(self, market_slug: str, sector: str):
        """Update market to sector mapping."""
        if not hasattr(self, "_market_sectors"):
            self._market_sectors = {}
        self._market_sectors[market_slug] = sector

    def get_market_sector(self, market_slug: str) -> str:
        """Get sector for a market (inferred if not explicitly provided)."""
        if hasattr(self, "_market_sectors") and market_slug in self._market_sectors:
            return self._market_sectors[market_slug]

        # Simple heuristic-based sector classification
        market_lower = market_slug.lower()
        if any(
            keyword in market_lower
            for keyword in ["election", "politics", "vote", "president"]
        ):
            return "politics"
        elif any(
            keyword in market_lower
            for keyword in ["sports", "nfl", "nba", "soccer", "football"]
        ):
            return "sports"
        elif any(
            keyword in market_lower for keyword in ["crypto", "bitcoin", "eth", "price"]
        ):
            return "crypto"
        elif any(
            keyword in market_lower
            for keyword in ["economy", "gdp", "inflation", "fed"]
        ):
            return "economics"
        else:
            return "other"

    async def calculate_market_correlations(
        self,
    ) -> Dict[str, Dict[str, CorrelationMetrics]]:
        """Calculate correlation matrix between markets."""
        markets = self.data_store.get_available_markets()
        correlations = {}

        for i, market_a in enumerate(markets):
            correlations[market_a] = {}

            for market_b in markets:
                if market_a == market_b:
                    # Perfect correlation with self
                    correlations[market_a][market_b] = CorrelationMetrics(
                        entity_a=market_a,
                        entity_b=market_b,
                        correlation_coefficient=1.0,
                        sample_size=len(self.data_store.price_data[market_a]),
                        strength=CorrelationStrength.VERY_HIGH,
                    )
                else:
                    # Calculate correlation between different markets
                    corr_metrics = await self._calculate_correlation_metrics(
                        market_a, market_b
                    )
                    correlations[market_a][market_b] = corr_metrics

        self.market_correlations = correlations
        return correlations

    async def _calculate_correlation_metrics(
        self, market_a: str, market_b: str
    ) -> CorrelationMetrics:
        """Calculate detailed correlation metrics between two markets."""
        try:
            # Get price and exposure data
            prices_a, exposures_a = self.data_store.get_market_series(
                market_a, self.config.lookback_hours
            )
            prices_b, exposures_b = self.data_store.get_market_series(
                market_b, self.config.lookback_hours
            )

            # Ensure we have enough data points
            min_length = min(len(prices_a), len(prices_b))
            if min_length < self.config.min_data_points:
                return CorrelationMetrics(
                    entity_a=market_a,
                    entity_b=market_b,
                    correlation_coefficient=0.0,
                    sample_size=min_length,
                )

            # Align the series (take last N points where N = min_length)
            prices_a_aligned = np.array(prices_a[-min_length:])
            prices_b_aligned = np.array(prices_b[-min_length:])

            # Calculate price returns for more stable correlation
            returns_a = np.diff(prices_a_aligned) / prices_a_aligned[:-1]
            returns_b = np.diff(prices_b_aligned) / prices_b_aligned[:-1]

            # Handle edge cases
            if len(returns_a) < 2 or len(returns_b) < 2:
                return CorrelationMetrics(
                    entity_a=market_a,
                    entity_b=market_b,
                    correlation_coefficient=0.0,
                    sample_size=min_length,
                )

            # Calculate correlation coefficient
            correlation = np.corrcoef(returns_a, returns_b)[0, 1]
            correlation = float(correlation) if not np.isnan(correlation) else 0.0

            # Calculate covariance
            covariance = np.cov(returns_a, returns_b)[0, 1]
            covariance = float(covariance) if not np.isnan(covariance) else 0.0

            # Simple p-value estimation (would need more sophisticated stats in production)
            p_value = max(0.01, 1.0 - abs(correlation))

            # Confidence interval (simplified)
            ci_width = 1.96 / np.sqrt(
                max(len(returns_a) - 3, 1)
            )  # 95% CI approximation
            confidence_interval = (
                max(-1.0, correlation - ci_width),
                min(1.0, correlation + ci_width),
            )

            return CorrelationMetrics(
                entity_a=market_a,
                entity_b=market_b,
                correlation_coefficient=correlation,
                p_value=p_value,
                covariance=covariance,
                sample_size=min_length,
                confidence_interval=confidence_interval,
            )

        except Exception as e:
            logger.error(
                f"Error calculating correlation between {market_a} and {market_b}: {e}"
            )
            return CorrelationMetrics(
                entity_a=market_a,
                entity_b=market_b,
                correlation_coefficient=0.0,
                sample_size=0,
            )

    async def assess_position_correlation_risk(
        self, new_market: str, new_exposure: float, existing_positions: Dict[str, float]
    ) -> RiskAdjustment:
        """Assess correlation risk for a new position given existing positions."""

        # Calculate correlation risk score
        correlation_risk_score = 0.0
        affected_positions = []
        high_correlation_exposure = 0.0

        for existing_market, existing_exposure in existing_positions.items():
            if existing_market == new_market:
                continue

            # Get correlation coefficient
            if (
                new_market in self.market_correlations
                and existing_market in self.market_correlations[new_market]
            ):
                corr_metrics = self.market_correlations[new_market][existing_market]
                correlation = abs(corr_metrics.correlation_coefficient)
            else:
                # Fall back to sector-based correlation
                new_sector = self.get_market_sector(new_market)
                existing_sector = self.get_market_sector(existing_market)
                correlation = abs(
                    self.sector_correlations.get(new_sector, {}).get(
                        existing_sector, 0.0
                    )
                )

            # Weight by exposure size
            exposure_weight = existing_exposure / max(
                sum(existing_positions.values()), 1.0
            )
            correlation_contribution = correlation * exposure_weight
            correlation_risk_score += correlation_contribution

            # Track highly correlated positions
            if correlation >= self.config.high_correlation_threshold:
                affected_positions.append(existing_market)
                high_correlation_exposure += existing_exposure

        # Determine adjustment factor based on correlation risk
        if correlation_risk_score >= self.config.high_correlation_threshold:
            adjustment_factor = self.config.high_correlation_penalty
            reason = f"High correlation risk (score: {correlation_risk_score:.2f})"
        elif correlation_risk_score >= self.config.moderate_correlation_threshold:
            adjustment_factor = self.config.moderate_correlation_penalty
            reason = f"Moderate correlation risk (score: {correlation_risk_score:.2f})"
        elif correlation_risk_score >= self.config.low_correlation_threshold:
            adjustment_factor = self.config.low_correlation_penalty
            reason = f"Low correlation risk (score: {correlation_risk_score:.2f})"
        else:
            adjustment_factor = 1.0
            reason = "No significant correlation risk detected"

        # Check portfolio-wide correlation concentration
        total_exposure = sum(existing_positions.values()) + new_exposure
        if total_exposure > 0:
            correlated_concentration = high_correlation_exposure / total_exposure
            if correlated_concentration > self.config.correlation_concentration_limit:
                adjustment_factor *= 0.5  # Additional penalty for concentration
                reason += (
                    f" + correlation concentration ({correlated_concentration:.1%})"
                )

        return RiskAdjustment(
            original_limit=new_exposure,
            adjusted_limit=new_exposure * adjustment_factor,
            adjustment_factor=adjustment_factor,
            correlation_score=correlation_risk_score,
            affected_positions=affected_positions,
            reason=reason,
        )

    async def get_portfolio_correlation_metrics(
        self, positions: Dict[str, float]
    ) -> Dict[str, Any]:
        """Get comprehensive correlation metrics for the entire portfolio."""

        if len(positions) < 2:
            return {
                "total_positions": len(positions),
                "correlation_risk_score": 0.0,
                "highly_correlated_groups": [],
                "diversification_score": 1.0,
                "recommendations": [
                    "Add more positions to enable correlation analysis"
                ],
            }

        markets = list(positions.keys())
        total_exposure = sum(positions.values())

        # Calculate average pairwise correlation
        correlations = []
        highly_correlated_pairs = []

        for i, market_a in enumerate(markets):
            for market_b in markets[i + 1 :]:
                if (
                    market_a in self.market_correlations
                    and market_b in self.market_correlations[market_a]
                ):
                    corr = abs(
                        self.market_correlations[market_a][
                            market_b
                        ].correlation_coefficient
                    )
                else:
                    # Fall back to sector correlation
                    sector_a = self.get_market_sector(market_a)
                    sector_b = self.get_market_sector(market_b)
                    corr = abs(
                        self.sector_correlations.get(sector_a, {}).get(sector_b, 0.0)
                    )

                correlations.append(corr)

                if corr >= self.config.high_correlation_threshold:
                    exposure_a = positions[market_a]
                    exposure_b = positions[market_b]
                    highly_correlated_pairs.append(
                        {
                            "market_a": market_a,
                            "market_b": market_b,
                            "correlation": corr,
                            "combined_exposure": exposure_a + exposure_b,
                            "exposure_pct": (exposure_a + exposure_b) / total_exposure,
                        }
                    )

        avg_correlation = np.mean(correlations) if correlations else 0.0
        max_correlation = np.max(correlations) if correlations else 0.0

        # Calculate diversification score (1 - average correlation)
        diversification_score = max(0.0, 1.0 - avg_correlation)

        # Group highly correlated positions
        correlation_groups = self._find_correlation_groups(
            positions, self.config.high_correlation_threshold
        )

        # Generate recommendations
        recommendations = self._generate_correlation_recommendations(
            avg_correlation, highly_correlated_pairs, correlation_groups, total_exposure
        )

        return {
            "total_positions": len(positions),
            "correlation_risk_score": avg_correlation,
            "max_pairwise_correlation": max_correlation,
            "highly_correlated_pairs": len(highly_correlated_pairs),
            "highly_correlated_groups": correlation_groups,
            "diversification_score": diversification_score,
            "avg_correlation": avg_correlation,
            "recommendations": recommendations,
        }

    def _find_correlation_groups(
        self, positions: Dict[str, float], threshold: float
    ) -> List[Dict[str, Any]]:
        """Find groups of highly correlated positions."""
        markets = list(positions.keys())
        groups = []
        used_markets = set()

        for market_a in markets:
            if market_a in used_markets:
                continue

            group = [market_a]
            group_exposure = positions[market_a]

            for market_b in markets:
                if market_b == market_a or market_b in used_markets:
                    continue

                # Check correlation
                if (
                    market_a in self.market_correlations
                    and market_b in self.market_correlations[market_a]
                ):
                    corr = abs(
                        self.market_correlations[market_a][
                            market_b
                        ].correlation_coefficient
                    )
                else:
                    sector_a = self.get_market_sector(market_a)
                    sector_b = self.get_market_sector(market_b)
                    corr = abs(
                        self.sector_correlations.get(sector_a, {}).get(sector_b, 0.0)
                    )

                if corr >= threshold:
                    group.append(market_b)
                    group_exposure += positions[market_b]

            if len(group) > 1:  # Only include groups with multiple markets
                for market in group:
                    used_markets.add(market)

                groups.append(
                    {
                        "markets": group,
                        "size": len(group),
                        "total_exposure": group_exposure,
                        "exposure_pct": group_exposure / sum(positions.values()),
                        "avg_correlation": threshold,  # Simplified
                    }
                )

        return sorted(groups, key=lambda g: g["total_exposure"], reverse=True)

    def _generate_correlation_recommendations(
        self,
        avg_correlation: float,
        highly_correlated_pairs: List[Dict],
        correlation_groups: List[Dict],
        total_exposure: float,
    ) -> List[str]:
        """Generate correlation-based risk management recommendations."""
        recommendations = []

        if avg_correlation > 0.6:
            recommendations.append(
                "High portfolio correlation detected - consider diversifying into uncorrelated markets"
            )
        elif avg_correlation > 0.4:
            recommendations.append(
                "Moderate portfolio correlation - monitor for concentration risk"
            )

        if len(highly_correlated_pairs) > 3:
            recommendations.append(
                f"Multiple highly correlated pairs ({len(highly_correlated_pairs)}) - reduce correlation concentration"
            )

        for group in correlation_groups:
            if group["exposure_pct"] > 0.5:
                recommendations.append(
                    f"High exposure concentration in correlated group: {group['size']} markets, {group['exposure_pct']:.1%} of portfolio"
                )

        if len(correlation_groups) == 0 and avg_correlation < 0.2:
            recommendations.append(
                "Well diversified portfolio with low correlation risk"
            )

        return recommendations or ["Continue monitoring correlation patterns"]

    async def _correlation_update_loop(self):
        """Background loop to update correlations periodically."""
        while self._running:
            try:
                await self.calculate_market_correlations()
                logger.debug("Updated correlation matrices")
                await asyncio.sleep(self.config.correlation_update_interval)

            except Exception as e:
                logger.error(f"Error in correlation update loop: {e}")
                await asyncio.sleep(self.config.correlation_update_interval)

    def get_correlation_summary(self) -> Dict[str, Any]:
        """Get summary of correlation analysis system status."""
        return {
            "markets_tracked": len(self.data_store.get_available_markets()),
            "correlation_matrices": len(self.market_correlations),
            "active_adjustments": len(self.active_adjustments),
            "total_adjustments": len(self.adjustment_history),
            "config": {
                "high_correlation_threshold": self.config.high_correlation_threshold,
                "correlation_penalty": self.config.high_correlation_penalty,
                "lookback_hours": self.config.lookback_hours,
                "update_interval": self.config.correlation_update_interval,
            },
            "running": self._running,
        }
