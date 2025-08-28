"""
Comprehensive exposure calculation engine for market and outcome tracking.

Provides atomic calculation methods for position exposures across different
dimensions (market, outcome, strategy) with real-time updates and risk analysis.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ..database import DatabaseManager
from ..position_models import Position

log = logging.getLogger("exposure_calculator")


@dataclass
class MarketExposure:
    """Comprehensive market-level exposure data."""

    market_slug: str
    total_notional: Decimal
    net_exposure: Decimal  # Long - Short
    gross_exposure: Decimal  # |Long| + |Short|
    long_exposure: Decimal
    short_exposure: Decimal
    position_count: int
    outcome_breakdown: dict[str, Decimal]
    average_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    last_updated: float = field(default_factory=time.time)


@dataclass
class OutcomeExposure:
    """Comprehensive outcome-level exposure data."""

    outcome_type: str
    total_notional: Decimal
    net_exposure: Decimal
    gross_exposure: Decimal
    position_count: int
    market_breakdown: dict[str, Decimal]
    average_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    correlation_score: float = 0.0
    concentration_risk: float = 0.0
    last_updated: float = field(default_factory=time.time)


@dataclass
class PortfolioExposure:
    """Complete portfolio exposure summary."""

    total_notional: Decimal
    net_exposure: Decimal
    gross_exposure: Decimal
    market_count: int
    outcome_count: int
    position_count: int
    market_exposures: dict[str, MarketExposure]
    outcome_exposures: dict[str, OutcomeExposure]
    concentration_metrics: dict[str, float]
    risk_metrics: dict[str, float]
    timestamp: float = field(default_factory=time.time)


class ExposureCalculator:
    """
    Advanced exposure calculation engine with real-time updates.

    Features:
    - Atomic exposure calculations across all dimensions
    - Real-time P&L tracking with mark-to-market
    - Concentration risk analysis
    - Correlation-adjusted exposure metrics
    - Performance-optimized with caching
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._cache_ttl = 1.0  # 1 second cache TTL
        self._exposure_cache: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

        # Configuration
        self.precision = Decimal("0.0001")  # 4 decimal places
        self.concentration_threshold = Decimal("0.3")  # 30% concentration alert

    async def calculate_portfolio_exposure(
        self,
        positions: list[Position] | None = None,
        include_unrealized_pnl: bool = True,
        mark_prices: dict[str, Decimal] | None = None,
    ) -> PortfolioExposure:
        """
        Calculate comprehensive portfolio exposure across all dimensions.

        Args:
            positions: List of positions to analyze (None = fetch all)
            include_unrealized_pnl: Whether to include unrealized P&L
            mark_prices: Current market prices for P&L calculation

        Returns:
            Complete portfolio exposure analysis
        """
        async with self._lock:
            cache_key = "portfolio_exposure"
            cached = self._get_cached_value(cache_key)
            if cached and not mark_prices:  # Skip cache if prices provided
                return cached

            # Fetch positions if not provided
            if positions is None:
                positions = await self._fetch_all_positions()

            if not positions:
                return self._empty_portfolio_exposure()

            # Calculate exposures by dimension
            market_exposures = await self._calculate_market_exposures(
                positions, include_unrealized_pnl, mark_prices
            )
            outcome_exposures = await self._calculate_outcome_exposures(
                positions, include_unrealized_pnl, mark_prices
            )

            # Calculate portfolio-level metrics
            total_notional = sum(
                exp.total_notional for exp in market_exposures.values()
            )
            net_exposure = sum(exp.net_exposure for exp in market_exposures.values())
            gross_exposure = sum(
                exp.gross_exposure for exp in market_exposures.values()
            )

            # Calculate concentration and risk metrics
            concentration_metrics = self._calculate_concentration_metrics(
                market_exposures, outcome_exposures, total_notional
            )
            risk_metrics = await self._calculate_risk_metrics(
                positions, market_exposures, outcome_exposures
            )

            portfolio = PortfolioExposure(
                total_notional=total_notional,
                net_exposure=net_exposure,
                gross_exposure=gross_exposure,
                market_count=len(market_exposures),
                outcome_count=len(outcome_exposures),
                position_count=len(positions),
                market_exposures=market_exposures,
                outcome_exposures=outcome_exposures,
                concentration_metrics=concentration_metrics,
                risk_metrics=risk_metrics,
            )

            self._cache_value(cache_key, portfolio)
            return portfolio

    async def calculate_market_exposure(
        self,
        market_slug: str,
        positions: list[Position] | None = None,
        include_unrealized_pnl: bool = True,
        mark_prices: dict[str, Decimal] | None = None,
    ) -> MarketExposure | None:
        """
        Calculate comprehensive exposure for a specific market.

        Args:
            market_slug: Market identifier
            positions: Positions to analyze (None = fetch for market)
            include_unrealized_pnl: Whether to include unrealized P&L
            mark_prices: Current market prices

        Returns:
            Market exposure analysis or None if no positions
        """
        cache_key = f"market_exposure:{market_slug}"
        cached = self._get_cached_value(cache_key)
        if cached and not mark_prices:
            return cached

        # Fetch market positions if not provided
        if positions is None:
            positions = await self._fetch_market_positions(market_slug)

        if not positions:
            return None

        market_positions = [
            p for p in positions if p.market_slug == market_slug and p.is_open
        ]

        if not market_positions:
            return None

        exposure = await self._calculate_single_market_exposure(
            market_slug, market_positions, include_unrealized_pnl, mark_prices
        )

        self._cache_value(cache_key, exposure)
        return exposure

    async def calculate_outcome_exposure(
        self,
        outcome_type: str,
        positions: list[Position] | None = None,
        include_unrealized_pnl: bool = True,
        mark_prices: dict[str, Decimal] | None = None,
    ) -> OutcomeExposure | None:
        """
        Calculate comprehensive exposure for a specific outcome type.

        Args:
            outcome_type: Outcome identifier (e.g., 'YES', 'NO')
            positions: Positions to analyze (None = fetch for outcome)
            include_unrealized_pnl: Whether to include unrealized P&L
            mark_prices: Current market prices

        Returns:
            Outcome exposure analysis or None if no positions
        """
        cache_key = f"outcome_exposure:{outcome_type}"
        cached = self._get_cached_value(cache_key)
        if cached and not mark_prices:
            return cached

        # Fetch outcome positions if not provided
        if positions is None:
            positions = await self._fetch_outcome_positions(outcome_type)

        if not positions:
            return None

        outcome_positions = [
            p for p in positions if p.outcome_type == outcome_type and p.is_open
        ]

        if not outcome_positions:
            return None

        exposure = await self._calculate_single_outcome_exposure(
            outcome_type, outcome_positions, include_unrealized_pnl, mark_prices
        )

        self._cache_value(cache_key, exposure)
        return exposure

    async def calculate_real_time_exposure_delta(
        self, position_delta: dict[str, Any]
    ) -> dict[str, Decimal]:
        """
        Calculate exposure changes from a position update without full recalculation.

        Args:
            position_delta: Position change data

        Returns:
            Exposure deltas by dimension
        """
        token_id = position_delta.get("token_id")
        size_delta = Decimal(str(position_delta.get("size_delta", 0)))
        price = Decimal(str(position_delta.get("price", 0)))
        market_slug = position_delta.get("market_slug")
        outcome_type = position_delta.get("outcome_type")

        notional_delta = abs(size_delta * price)
        net_delta = size_delta * price  # Signed for net calculation

        return {
            "total_notional_delta": notional_delta,
            "total_net_delta": net_delta,
            "market_notional_delta": notional_delta if market_slug else Decimal("0"),
            "market_net_delta": net_delta if market_slug else Decimal("0"),
            "outcome_notional_delta": notional_delta if outcome_type else Decimal("0"),
            "outcome_net_delta": net_delta if outcome_type else Decimal("0"),
            "position_count_delta": 1 if size_delta != 0 else 0,
        }

    async def get_exposure_limits_utilization(
        self, portfolio: PortfolioExposure, limits: dict[str, Decimal]
    ) -> dict[str, float]:
        """
        Calculate utilization percentages against exposure limits.

        Args:
            portfolio: Portfolio exposure data
            limits: Risk limits configuration

        Returns:
            Utilization ratios (0.0 to 1.0+) for each limit type
        """
        utilization = {}

        # Global limits
        if "global_risk_cap" in limits and limits["global_risk_cap"] > 0:
            utilization["global"] = float(
                portfolio.total_notional / limits["global_risk_cap"]
            )

        # Market limits
        if "per_market_risk_cap" in limits and limits["per_market_risk_cap"] > 0:
            market_utils = {}
            for market_slug, exposure in portfolio.market_exposures.items():
                market_utils[market_slug] = float(
                    exposure.total_notional / limits["per_market_risk_cap"]
                )
            utilization["markets"] = market_utils
            utilization["max_market"] = (
                max(market_utils.values()) if market_utils else 0.0
            )

        # Outcome limits
        if "per_outcome_risk_cap" in limits and limits["per_outcome_risk_cap"] > 0:
            outcome_utils = {}
            for outcome_type, exposure in portfolio.outcome_exposures.items():
                outcome_utils[outcome_type] = float(
                    exposure.total_notional / limits["per_outcome_risk_cap"]
                )
            utilization["outcomes"] = outcome_utils
            utilization["max_outcome"] = (
                max(outcome_utils.values()) if outcome_utils else 0.0
            )

        return utilization

    async def analyze_exposure_concentration(
        self, portfolio: PortfolioExposure
    ) -> dict[str, Any]:
        """
        Analyze concentration risk in the portfolio.

        Args:
            portfolio: Portfolio exposure data

        Returns:
            Concentration analysis including HHI and top positions
        """
        if portfolio.total_notional == 0:
            return {
                "herfindahl_index_markets": 0.0,
                "herfindahl_index_outcomes": 0.0,
                "top_markets": [],
                "top_outcomes": [],
                "concentration_risk_score": 0.0,
            }

        # Calculate Herfindahl-Hirschman Index for markets
        market_hhi = sum(
            (float(exp.total_notional / portfolio.total_notional)) ** 2
            for exp in portfolio.market_exposures.values()
        )

        # Calculate HHI for outcomes
        outcome_hhi = sum(
            (float(exp.total_notional / portfolio.total_notional)) ** 2
            for exp in portfolio.outcome_exposures.values()
        )

        # Get top concentrations
        top_markets = sorted(
            [
                {
                    "market_slug": market_slug,
                    "exposure": float(exp.total_notional),
                    "percentage": float(
                        exp.total_notional / portfolio.total_notional * 100
                    ),
                }
                for market_slug, exp in portfolio.market_exposures.items()
            ],
            key=lambda x: x["exposure"],
            reverse=True,
        )[:5]

        top_outcomes = sorted(
            [
                {
                    "outcome_type": outcome_type,
                    "exposure": float(exp.total_notional),
                    "percentage": float(
                        exp.total_notional / portfolio.total_notional * 100
                    ),
                }
                for outcome_type, exp in portfolio.outcome_exposures.items()
            ],
            key=lambda x: x["exposure"],
            reverse=True,
        )[:5]

        # Overall concentration risk score (0-1, higher = more concentrated)
        concentration_risk_score = max(market_hhi, outcome_hhi)

        return {
            "herfindahl_index_markets": market_hhi,
            "herfindahl_index_outcomes": outcome_hhi,
            "top_markets": top_markets,
            "top_outcomes": top_outcomes,
            "concentration_risk_score": concentration_risk_score,
        }

    # Private helper methods

    async def _calculate_market_exposures(
        self,
        positions: list[Position],
        include_unrealized_pnl: bool,
        mark_prices: dict[str, Decimal] | None,
    ) -> dict[str, MarketExposure]:
        """Calculate exposures grouped by market."""
        market_groups = defaultdict(list)
        for position in positions:
            if position.is_open and position.market_slug:
                market_groups[position.market_slug].append(position)

        exposures = {}
        for market_slug, market_positions in market_groups.items():
            exposures[market_slug] = await self._calculate_single_market_exposure(
                market_slug, market_positions, include_unrealized_pnl, mark_prices
            )

        return exposures

    async def _calculate_outcome_exposures(
        self,
        positions: list[Position],
        include_unrealized_pnl: bool,
        mark_prices: dict[str, Decimal] | None,
    ) -> dict[str, OutcomeExposure]:
        """Calculate exposures grouped by outcome."""
        outcome_groups = defaultdict(list)
        for position in positions:
            if position.is_open and position.outcome_type:
                outcome_groups[position.outcome_type].append(position)

        exposures = {}
        for outcome_type, outcome_positions in outcome_groups.items():
            exposures[outcome_type] = await self._calculate_single_outcome_exposure(
                outcome_type, outcome_positions, include_unrealized_pnl, mark_prices
            )

        return exposures

    async def _calculate_single_market_exposure(
        self,
        market_slug: str,
        positions: list[Position],
        include_unrealized_pnl: bool,
        mark_prices: dict[str, Decimal] | None,
    ) -> MarketExposure:
        """Calculate exposure for a single market."""
        if not positions:
            return self._empty_market_exposure(market_slug)

        # Aggregate position data
        total_notional = sum(p.notional_value for p in positions)
        long_exposure = sum(p.notional_value for p in positions if p.size > 0)
        short_exposure = sum(abs(p.notional_value) for p in positions if p.size < 0)
        net_exposure = long_exposure - short_exposure
        gross_exposure = long_exposure + short_exposure

        # Calculate outcome breakdown
        outcome_breakdown = defaultdict(Decimal)
        for position in positions:
            if position.outcome_type:
                outcome_breakdown[position.outcome_type] += position.notional_value

        # Calculate average price (weighted by size)
        total_size = sum(abs(p.size) for p in positions)
        average_price = (
            sum(p.average_price * abs(p.size) for p in positions) / total_size
            if total_size > 0
            else Decimal("0")
        )

        # Calculate P&L
        unrealized_pnl = Decimal("0")
        realized_pnl = sum(p.realized_pnl for p in positions)

        if include_unrealized_pnl:
            for position in positions:
                mark_price = (
                    mark_prices.get(position.token_id, position.current_price)
                    if mark_prices
                    else position.current_price
                )
                unrealized_pnl += (mark_price - position.average_price) * position.size

        return MarketExposure(
            market_slug=market_slug,
            total_notional=total_notional,
            net_exposure=net_exposure,
            gross_exposure=gross_exposure,
            long_exposure=long_exposure,
            short_exposure=short_exposure,
            position_count=len(positions),
            outcome_breakdown=dict(outcome_breakdown),
            average_price=average_price,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
        )

    async def _calculate_single_outcome_exposure(
        self,
        outcome_type: str,
        positions: list[Position],
        include_unrealized_pnl: bool,
        mark_prices: dict[str, Decimal] | None,
    ) -> OutcomeExposure:
        """Calculate exposure for a single outcome type."""
        if not positions:
            return self._empty_outcome_exposure(outcome_type)

        # Aggregate position data
        total_notional = sum(p.notional_value for p in positions)
        long_exposure = sum(p.notional_value for p in positions if p.size > 0)
        short_exposure = sum(abs(p.notional_value) for p in positions if p.size < 0)
        net_exposure = long_exposure - short_exposure
        gross_exposure = long_exposure + short_exposure

        # Calculate market breakdown
        market_breakdown = defaultdict(Decimal)
        for position in positions:
            if position.market_slug:
                market_breakdown[position.market_slug] += position.notional_value

        # Calculate average price (weighted by size)
        total_size = sum(abs(p.size) for p in positions)
        average_price = (
            sum(p.average_price * abs(p.size) for p in positions) / total_size
            if total_size > 0
            else Decimal("0")
        )

        # Calculate P&L
        unrealized_pnl = Decimal("0")
        realized_pnl = sum(p.realized_pnl for p in positions)

        if include_unrealized_pnl:
            for position in positions:
                mark_price = (
                    mark_prices.get(position.token_id, position.current_price)
                    if mark_prices
                    else position.current_price
                )
                unrealized_pnl += (mark_price - position.average_price) * position.size

        return OutcomeExposure(
            outcome_type=outcome_type,
            total_notional=total_notional,
            net_exposure=net_exposure,
            gross_exposure=gross_exposure,
            position_count=len(positions),
            market_breakdown=dict(market_breakdown),
            average_price=average_price,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
        )

    def _calculate_concentration_metrics(
        self,
        market_exposures: dict[str, MarketExposure],
        outcome_exposures: dict[str, OutcomeExposure],
        total_notional: Decimal,
    ) -> dict[str, float]:
        """Calculate concentration risk metrics."""
        if total_notional == 0:
            return {
                "market_concentration": 0.0,
                "outcome_concentration": 0.0,
                "top_market_percentage": 0.0,
                "top_outcome_percentage": 0.0,
            }

        # Market concentration
        max_market_exposure = max(
            (exp.total_notional for exp in market_exposures.values()),
            default=Decimal("0"),
        )
        market_concentration = float(max_market_exposure / total_notional)

        # Outcome concentration
        max_outcome_exposure = max(
            (exp.total_notional for exp in outcome_exposures.values()),
            default=Decimal("0"),
        )
        outcome_concentration = float(max_outcome_exposure / total_notional)

        return {
            "market_concentration": market_concentration,
            "outcome_concentration": outcome_concentration,
            "top_market_percentage": market_concentration * 100,
            "top_outcome_percentage": outcome_concentration * 100,
        }

    async def _calculate_risk_metrics(
        self,
        positions: list[Position],
        market_exposures: dict[str, MarketExposure],
        outcome_exposures: dict[str, OutcomeExposure],
    ) -> dict[str, float]:
        """Calculate portfolio risk metrics."""
        if not positions:
            return {"var_estimate": 0.0, "sharpe_ratio": 0.0, "max_drawdown": 0.0}

        # Simple risk metrics calculation
        total_pnl = sum(p.unrealized_pnl + p.realized_pnl for p in positions)
        total_notional = sum(p.notional_value for p in positions)

        # Basic VAR estimate (simplified)
        var_estimate = float(total_notional * Decimal("0.05"))  # 5% VAR

        # Return on investment
        roi = float(total_pnl / total_notional) if total_notional > 0 else 0.0

        return {
            "var_estimate": var_estimate,
            "roi": roi,
            "total_pnl": float(total_pnl),
            "pnl_ratio": roi,
        }

    async def _fetch_all_positions(self) -> list[Position]:
        """Fetch all positions from database."""
        # This would integrate with the actual database/position manager
        # For now, return empty list - will be implemented based on actual schema
        return []

    async def _fetch_market_positions(self, market_slug: str) -> list[Position]:
        """Fetch positions for a specific market."""
        # This would integrate with the actual database/position manager
        return []

    async def _fetch_outcome_positions(self, outcome_type: str) -> list[Position]:
        """Fetch positions for a specific outcome type."""
        # This would integrate with the actual database/position manager
        return []

    def _empty_portfolio_exposure(self) -> PortfolioExposure:
        """Return empty portfolio exposure."""
        return PortfolioExposure(
            total_notional=Decimal("0"),
            net_exposure=Decimal("0"),
            gross_exposure=Decimal("0"),
            market_count=0,
            outcome_count=0,
            position_count=0,
            market_exposures={},
            outcome_exposures={},
            concentration_metrics={},
            risk_metrics={},
        )

    def _empty_market_exposure(self, market_slug: str) -> MarketExposure:
        """Return empty market exposure."""
        return MarketExposure(
            market_slug=market_slug,
            total_notional=Decimal("0"),
            net_exposure=Decimal("0"),
            gross_exposure=Decimal("0"),
            long_exposure=Decimal("0"),
            short_exposure=Decimal("0"),
            position_count=0,
            outcome_breakdown={},
            average_price=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
        )

    def _empty_outcome_exposure(self, outcome_type: str) -> OutcomeExposure:
        """Return empty outcome exposure."""
        return OutcomeExposure(
            outcome_type=outcome_type,
            total_notional=Decimal("0"),
            net_exposure=Decimal("0"),
            gross_exposure=Decimal("0"),
            position_count=0,
            market_breakdown={},
            average_price=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
        )

    def _get_cached_value(self, key: str) -> Any:
        """Get value from cache if not expired."""
        if key in self._exposure_cache:
            value, timestamp = self._exposure_cache[key]
            if time.time() - timestamp < self._cache_ttl:
                return value
            else:
                del self._exposure_cache[key]
        return None

    def _cache_value(self, key: str, value: Any) -> None:
        """Cache value with timestamp."""
        self._exposure_cache[key] = (value, time.time())

        # Clean up old cache entries
        current_time = time.time()
        expired_keys = [
            k
            for k, (_, timestamp) in self._exposure_cache.items()
            if current_time - timestamp > self._cache_ttl * 2
        ]
        for key in expired_keys:
            del self._exposure_cache[key]
