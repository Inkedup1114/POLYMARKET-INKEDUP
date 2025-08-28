"""
Advanced Liquidity Analysis System with Real-Time Order Book Depth Analysis.

This module provides enhanced liquidity analysis capabilities that go beyond
simple order book summation, offering sophisticated metrics for better
market entry/exit decisions.

Key Features:
- Real-time order book depth analysis with price impact calculations
- Dynamic liquidity scoring based on multiple factors
- Slippage estimation for different order sizes
- Market microstructure analysis
- Time-weighted average liquidity tracking
- Cross-market liquidity comparison
- Liquidity resilience scoring (ability to absorb large orders)

The system provides actionable liquidity metrics that help determine:
- Optimal order sizing to minimize price impact
- Best execution timing based on liquidity patterns
- Market depth quality beyond simple volume metrics
- Hidden liquidity detection through pattern analysis
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("advanced_liquidity")


class LiquidityQuality(Enum):
    """Liquidity quality classifications."""

    EXCELLENT = "excellent"  # Deep, balanced, resilient liquidity
    GOOD = "good"  # Adequate liquidity for most orders
    MODERATE = "moderate"  # Sufficient for small-medium orders
    POOR = "poor"  # Limited liquidity, high slippage risk
    VERY_POOR = "very_poor"  # Minimal liquidity, avoid large orders


class MarketDepthProfile(Enum):
    """Market depth profile types."""

    BALANCED = "balanced"  # Even distribution of bids and asks
    BID_HEAVY = "bid_heavy"  # More buy-side liquidity
    ASK_HEAVY = "ask_heavy"  # More sell-side liquidity
    TOP_HEAVY = "top_heavy"  # Liquidity concentrated at best prices
    DEEP = "deep"  # Liquidity distributed through book
    THIN = "thin"  # Limited liquidity overall


@dataclass
class OrderBookLevel:
    """Represents a single level in the order book."""

    price: float
    size: float
    cumulative_size: float = 0.0
    price_impact: float = 0.0
    distance_from_mid: float = 0.0


@dataclass
class LiquiditySnapshot:
    """Comprehensive liquidity snapshot at a point in time."""

    timestamp: float
    market_slug: str
    total_bid_liquidity: float
    total_ask_liquidity: float
    bid_ask_ratio: float
    spread_bps: float

    # Depth metrics
    depth_at_1pct: float  # Liquidity within 1% of mid price
    depth_at_2pct: float  # Liquidity within 2% of mid price
    depth_at_5pct: float  # Liquidity within 5% of mid price

    # Quality metrics
    liquidity_quality: LiquidityQuality
    depth_profile: MarketDepthProfile
    resilience_score: float  # 0-100 score for order absorption capacity

    # Price impact estimates (in bps)
    impact_100_usd: float  # Price impact for $100 order
    impact_500_usd: float  # Price impact for $500 order
    impact_1000_usd: float  # Price impact for $1000 order

    # Market microstructure
    avg_level_size: float  # Average order size per level
    level_count: int  # Number of price levels
    concentration_score: (
        float  # How concentrated liquidity is (0=dispersed, 1=concentrated)
    )

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SlippageEstimate:
    """Slippage estimation for a hypothetical order."""

    order_size: float
    side: str  # 'buy' or 'sell'
    expected_price: float
    average_fill_price: float
    slippage_bps: float
    price_impact_bps: float
    executable: bool
    fill_percentage: float  # Percentage of order that can be filled
    levels_consumed: int  # Number of order book levels consumed


@dataclass
class AdvancedLiquidityConfig:
    """Configuration for advanced liquidity analysis."""

    # Depth analysis parameters
    depth_levels: List[float] = field(
        default_factory=lambda: [0.01, 0.02, 0.05, 0.10]
    )  # 1%, 2%, 5%, 10%

    # Price impact thresholds (in bps)
    low_impact_threshold: float = 10.0  # < 10 bps is low impact
    medium_impact_threshold: float = 50.0  # < 50 bps is medium impact
    high_impact_threshold: float = 100.0  # >= 100 bps is high impact

    # Quality scoring weights
    depth_weight: float = 0.3
    balance_weight: float = 0.2
    spread_weight: float = 0.2
    resilience_weight: float = 0.3

    # Order size benchmarks for impact calculation
    benchmark_sizes: List[float] = field(
        default_factory=lambda: [100.0, 500.0, 1000.0, 5000.0]
    )

    # Time-weighted averaging
    time_window_minutes: int = 15
    sample_interval_seconds: int = 30

    # Minimum requirements
    min_liquidity_usd: float = 100.0
    min_levels: int = 3
    max_spread_bps: float = 500.0


class AdvancedLiquidityAnalyzer:
    """
    Advanced liquidity analyzer with sophisticated order book analysis.

    Provides real-time liquidity metrics, price impact calculations,
    and market microstructure analysis for optimal trade execution.
    """

    def __init__(self, config: Optional[AdvancedLiquidityConfig] = None):
        self.config = config or AdvancedLiquidityConfig()

        # Time-weighted liquidity tracking
        self.liquidity_history: Dict[str, deque] = {}
        self.max_history_size = int(
            self.config.time_window_minutes * 60 / self.config.sample_interval_seconds
        )

        # Performance metrics
        self.analysis_count = 0
        self.total_analysis_time = 0.0

        logger.info("Advanced liquidity analyzer initialized")

    def analyze_order_book(
        self, book_data: Dict[str, Any], market_slug: str
    ) -> LiquiditySnapshot:
        """
        Perform comprehensive analysis of an order book.

        Args:
            book_data: Raw order book data with 'bids' and 'asks'
            market_slug: Market identifier

        Returns:
            Comprehensive liquidity snapshot
        """
        start_time = time.perf_counter()

        try:
            # Parse order book
            bid_levels = self._parse_order_book_side(book_data.get("bids", []), "bid")
            ask_levels = self._parse_order_book_side(book_data.get("asks", []), "ask")

            if not bid_levels or not ask_levels:
                return self._create_empty_snapshot(market_slug)

            # Calculate mid price and spread
            best_bid = bid_levels[0].price
            best_ask = ask_levels[0].price
            mid_price = (best_bid + best_ask) / 2
            spread_bps = ((best_ask - best_bid) / mid_price) * 10000

            # Calculate depth at various levels
            depth_metrics = self._calculate_depth_metrics(
                bid_levels, ask_levels, mid_price
            )

            # Calculate liquidity sums
            total_bid_liquidity = sum(level.size * level.price for level in bid_levels)
            total_ask_liquidity = sum(level.size * level.price for level in ask_levels)
            bid_ask_ratio = total_bid_liquidity / max(total_ask_liquidity, 0.01)

            # Analyze market microstructure
            depth_profile = self._analyze_depth_profile(bid_levels, ask_levels)
            concentration_score = self._calculate_concentration_score(
                bid_levels, ask_levels
            )

            # Calculate price impacts for benchmark sizes
            impact_100 = self._estimate_price_impact(ask_levels, 100.0, mid_price)
            impact_500 = self._estimate_price_impact(ask_levels, 500.0, mid_price)
            impact_1000 = self._estimate_price_impact(ask_levels, 1000.0, mid_price)

            # Calculate resilience score
            resilience_score = self._calculate_resilience_score(
                bid_levels,
                ask_levels,
                total_bid_liquidity,
                total_ask_liquidity,
                spread_bps,
            )

            # Determine liquidity quality
            liquidity_quality = self._assess_liquidity_quality(
                total_bid_liquidity + total_ask_liquidity,
                spread_bps,
                resilience_score,
                depth_metrics["depth_at_2pct"],
            )

            # Create snapshot
            snapshot = LiquiditySnapshot(
                timestamp=time.time(),
                market_slug=market_slug,
                total_bid_liquidity=total_bid_liquidity,
                total_ask_liquidity=total_ask_liquidity,
                bid_ask_ratio=bid_ask_ratio,
                spread_bps=spread_bps,
                depth_at_1pct=depth_metrics["depth_at_1pct"],
                depth_at_2pct=depth_metrics["depth_at_2pct"],
                depth_at_5pct=depth_metrics["depth_at_5pct"],
                liquidity_quality=liquidity_quality,
                depth_profile=depth_profile,
                resilience_score=resilience_score,
                impact_100_usd=impact_100,
                impact_500_usd=impact_500,
                impact_1000_usd=impact_1000,
                avg_level_size=(total_bid_liquidity + total_ask_liquidity)
                / (len(bid_levels) + len(ask_levels)),
                level_count=len(bid_levels) + len(ask_levels),
                concentration_score=concentration_score,
                metadata={
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "mid_price": mid_price,
                    "bid_levels": len(bid_levels),
                    "ask_levels": len(ask_levels),
                },
            )

            # Update history for time-weighted analysis
            self._update_liquidity_history(market_slug, snapshot)

            # Update performance metrics
            self.analysis_count += 1
            self.total_analysis_time += time.perf_counter() - start_time

            return snapshot

        except Exception as e:
            logger.error(f"Error analyzing order book for {market_slug}: {e}")
            return self._create_empty_snapshot(market_slug)

    def _parse_order_book_side(
        self, orders: List[Dict], side: str
    ) -> List[OrderBookLevel]:
        """Parse one side of the order book into structured levels."""
        levels = []
        cumulative_size = 0.0

        for order in orders:
            try:
                price = float(order.get("price", 0))
                size = float(order.get("size", 0))

                if price <= 0 or size <= 0:
                    continue

                cumulative_size += size

                level = OrderBookLevel(
                    price=price, size=size, cumulative_size=cumulative_size
                )
                levels.append(level)

            except (ValueError, TypeError) as e:
                logger.debug(f"Skipping invalid order: {e}")
                continue

        return levels

    def _calculate_depth_metrics(
        self,
        bid_levels: List[OrderBookLevel],
        ask_levels: List[OrderBookLevel],
        mid_price: float,
    ) -> Dict[str, float]:
        """Calculate depth at various percentage levels from mid price."""
        metrics = {}

        for pct in self.config.depth_levels:
            bid_depth = 0.0
            ask_depth = 0.0

            # Calculate price bounds
            lower_bound = mid_price * (1 - pct)
            upper_bound = mid_price * (1 + pct)

            # Sum liquidity within bounds
            for level in bid_levels:
                if level.price >= lower_bound:
                    bid_depth += level.size * level.price

            for level in ask_levels:
                if level.price <= upper_bound:
                    ask_depth += level.size * level.price

            metrics[f"depth_at_{int(pct*100)}pct"] = bid_depth + ask_depth

        return metrics

    def _analyze_depth_profile(
        self, bid_levels: List[OrderBookLevel], ask_levels: List[OrderBookLevel]
    ) -> MarketDepthProfile:
        """Analyze the shape and distribution of market depth."""
        if not bid_levels or not ask_levels:
            return MarketDepthProfile.THIN

        total_bid_size = sum(level.size for level in bid_levels)
        total_ask_size = sum(level.size for level in ask_levels)

        # Check balance
        ratio = total_bid_size / max(total_ask_size, 0.01)
        if ratio > 1.5:
            return MarketDepthProfile.BID_HEAVY
        elif ratio < 0.67:
            return MarketDepthProfile.ASK_HEAVY

        # Check concentration
        if len(bid_levels) >= 3 and len(ask_levels) >= 3:
            top_3_bid = sum(level.size for level in bid_levels[:3])
            top_3_ask = sum(level.size for level in ask_levels[:3])

            bid_concentration = top_3_bid / total_bid_size if total_bid_size > 0 else 1
            ask_concentration = top_3_ask / total_ask_size if total_ask_size > 0 else 1

            avg_concentration = (bid_concentration + ask_concentration) / 2

            if avg_concentration > 0.7:
                return MarketDepthProfile.TOP_HEAVY
            elif len(bid_levels) > 10 and len(ask_levels) > 10:
                return MarketDepthProfile.DEEP

        if len(bid_levels) < 5 or len(ask_levels) < 5:
            return MarketDepthProfile.THIN

        return MarketDepthProfile.BALANCED

    def _calculate_concentration_score(
        self, bid_levels: List[OrderBookLevel], ask_levels: List[OrderBookLevel]
    ) -> float:
        """Calculate how concentrated the liquidity is (Herfindahl index style)."""
        all_sizes = [level.size for level in bid_levels + ask_levels]

        if not all_sizes:
            return 1.0

        total_size = sum(all_sizes)
        if total_size == 0:
            return 1.0

        # Calculate concentration (similar to Herfindahl index)
        concentration = sum((size / total_size) ** 2 for size in all_sizes)

        # Normalize: 1/n is minimum concentration, 1 is maximum
        min_concentration = 1.0 / len(all_sizes)
        normalized = (
            (concentration - min_concentration) / (1 - min_concentration)
            if len(all_sizes) > 1
            else 1.0
        )

        return max(0.0, min(1.0, normalized))

    def _estimate_price_impact(
        self, levels: List[OrderBookLevel], order_size_usd: float, mid_price: float
    ) -> float:
        """Estimate price impact in basis points for a given order size."""
        if not levels:
            return 1000.0  # Max impact if no liquidity

        remaining_size = order_size_usd
        total_cost = 0.0
        total_filled = 0.0

        for level in levels:
            level_value = level.size * level.price

            if remaining_size <= level_value:
                # Order filled at this level
                total_cost += remaining_size * (level.price / level.price)  # Normalized
                total_filled += remaining_size / level.price
                remaining_size = 0
                break
            else:
                # Consume entire level
                total_cost += level_value * (level.price / level.price)
                total_filled += level.size
                remaining_size -= level_value

        if total_filled == 0:
            return 1000.0  # Max impact

        avg_fill_price = total_cost / total_filled if total_filled > 0 else mid_price
        impact_bps = abs((avg_fill_price - mid_price) / mid_price) * 10000

        return min(impact_bps, 1000.0)  # Cap at 1000 bps

    def _calculate_resilience_score(
        self,
        bid_levels: List[OrderBookLevel],
        ask_levels: List[OrderBookLevel],
        total_bid_liquidity: float,
        total_ask_liquidity: float,
        spread_bps: float,
    ) -> float:
        """Calculate market resilience score (ability to absorb orders)."""
        scores = []

        # Liquidity depth score
        total_liquidity = total_bid_liquidity + total_ask_liquidity
        if total_liquidity > 10000:
            liquidity_score = 100.0
        elif total_liquidity > 5000:
            liquidity_score = 80.0
        elif total_liquidity > 1000:
            liquidity_score = 60.0
        elif total_liquidity > 500:
            liquidity_score = 40.0
        else:
            liquidity_score = 20.0
        scores.append(liquidity_score * 0.4)

        # Balance score
        balance_ratio = min(total_bid_liquidity, total_ask_liquidity) / max(
            total_bid_liquidity, total_ask_liquidity, 0.01
        )
        balance_score = balance_ratio * 100
        scores.append(balance_score * 0.2)

        # Spread score
        if spread_bps < 50:
            spread_score = 100.0
        elif spread_bps < 100:
            spread_score = 80.0
        elif spread_bps < 200:
            spread_score = 60.0
        elif spread_bps < 500:
            spread_score = 40.0
        else:
            spread_score = 20.0
        scores.append(spread_score * 0.2)

        # Level depth score
        level_count = len(bid_levels) + len(ask_levels)
        if level_count > 20:
            level_score = 100.0
        elif level_count > 10:
            level_score = 80.0
        elif level_count > 5:
            level_score = 60.0
        else:
            level_score = 40.0
        scores.append(level_score * 0.2)

        return sum(scores)

    def _assess_liquidity_quality(
        self,
        total_liquidity: float,
        spread_bps: float,
        resilience_score: float,
        depth_at_2pct: float,
    ) -> LiquidityQuality:
        """Assess overall liquidity quality based on multiple factors."""
        # Simple quality assessment based on thresholds
        if (
            total_liquidity > 5000
            and spread_bps < 50
            and resilience_score > 80
            and depth_at_2pct > 1000
        ):
            return LiquidityQuality.EXCELLENT
        elif (
            total_liquidity > 2000
            and spread_bps < 100
            and resilience_score > 60
            and depth_at_2pct > 500
        ):
            return LiquidityQuality.GOOD
        elif total_liquidity > 500 and spread_bps < 200 and resilience_score > 40:
            return LiquidityQuality.MODERATE
        elif total_liquidity > 100:
            return LiquidityQuality.POOR
        else:
            return LiquidityQuality.VERY_POOR

    def estimate_slippage(
        self, book_data: Dict[str, Any], order_size_usd: float, side: str
    ) -> SlippageEstimate:
        """
        Estimate slippage for a hypothetical order.

        Args:
            book_data: Order book data
            order_size_usd: Size of hypothetical order in USD
            side: 'buy' or 'sell'

        Returns:
            Detailed slippage estimate
        """
        # Select appropriate side of book
        if side == "buy":
            levels = self._parse_order_book_side(book_data.get("asks", []), "ask")
        else:
            levels = self._parse_order_book_side(book_data.get("bids", []), "bid")

        if not levels:
            return SlippageEstimate(
                order_size=order_size_usd,
                side=side,
                expected_price=0.0,
                average_fill_price=0.0,
                slippage_bps=1000.0,
                price_impact_bps=1000.0,
                executable=False,
                fill_percentage=0.0,
                levels_consumed=0,
            )

        expected_price = levels[0].price
        remaining_size = order_size_usd
        total_cost = 0.0
        total_filled = 0.0
        levels_consumed = 0

        for level in levels:
            level_value = level.size * level.price
            levels_consumed += 1

            if remaining_size <= level_value:
                # Order filled at this level
                fill_size = remaining_size / level.price
                total_cost += remaining_size
                total_filled += fill_size
                remaining_size = 0
                break
            else:
                # Consume entire level
                total_cost += level_value
                total_filled += level.size
                remaining_size -= level_value

        fill_percentage = (1 - remaining_size / order_size_usd) * 100
        executable = remaining_size == 0

        if total_filled > 0:
            avg_fill_price = total_cost / total_filled
            slippage = abs(avg_fill_price - expected_price)
            slippage_bps = (slippage / expected_price) * 10000
            price_impact_bps = slippage_bps  # Simplified
        else:
            avg_fill_price = expected_price
            slippage_bps = 0.0
            price_impact_bps = 0.0

        return SlippageEstimate(
            order_size=order_size_usd,
            side=side,
            expected_price=expected_price,
            average_fill_price=avg_fill_price,
            slippage_bps=slippage_bps,
            price_impact_bps=price_impact_bps,
            executable=executable,
            fill_percentage=fill_percentage,
            levels_consumed=levels_consumed,
        )

    def _update_liquidity_history(self, market_slug: str, snapshot: LiquiditySnapshot):
        """Update time-weighted liquidity history for a market."""
        if market_slug not in self.liquidity_history:
            self.liquidity_history[market_slug] = deque(maxlen=self.max_history_size)

        self.liquidity_history[market_slug].append(snapshot)

    def get_time_weighted_liquidity(self, market_slug: str) -> Optional[float]:
        """Get time-weighted average liquidity for a market."""
        if market_slug not in self.liquidity_history:
            return None

        snapshots = list(self.liquidity_history[market_slug])
        if not snapshots:
            return None

        # Simple average for now (could weight by time gaps)
        total_liquidity = sum(
            s.total_bid_liquidity + s.total_ask_liquidity for s in snapshots
        )
        return total_liquidity / len(snapshots)

    def _create_empty_snapshot(self, market_slug: str) -> LiquiditySnapshot:
        """Create an empty liquidity snapshot for error cases."""
        return LiquiditySnapshot(
            timestamp=time.time(),
            market_slug=market_slug,
            total_bid_liquidity=0.0,
            total_ask_liquidity=0.0,
            bid_ask_ratio=0.0,
            spread_bps=0.0,
            depth_at_1pct=0.0,
            depth_at_2pct=0.0,
            depth_at_5pct=0.0,
            liquidity_quality=LiquidityQuality.VERY_POOR,
            depth_profile=MarketDepthProfile.THIN,
            resilience_score=0.0,
            impact_100_usd=1000.0,
            impact_500_usd=1000.0,
            impact_1000_usd=1000.0,
            avg_level_size=0.0,
            level_count=0,
            concentration_score=1.0,
        )

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for the analyzer."""
        avg_time = self.total_analysis_time / max(self.analysis_count, 1)

        return {
            "total_analyses": self.analysis_count,
            "average_analysis_time_ms": avg_time * 1000,
            "markets_tracked": len(self.liquidity_history),
            "total_snapshots": sum(len(h) for h in self.liquidity_history.values()),
        }
