"""
Enhanced Scanner with Advanced Liquidity Analysis Integration.

This module extends the existing scanner with advanced liquidity analysis
capabilities, replacing any remaining simplified liquidity calculations
with comprehensive real-time order book depth analysis.

The enhancement provides:
- Real-time order book depth metrics
- Price impact calculations for various order sizes
- Liquidity quality scoring
- Slippage estimation
- Market microstructure analysis
"""

import logging
from typing import Any, Dict, List, Optional

from .advanced_liquidity_analyzer import (
    AdvancedLiquidityAnalyzer,
    AdvancedLiquidityConfig,
    LiquiditySnapshot,
    SlippageEstimate,
)
from .config import BotConfig
from .scanner import Scanner

logger = logging.getLogger("scanner_enhanced")


class EnhancedLiquidityScanner(Scanner):
    """
    Enhanced scanner with advanced liquidity analysis capabilities.

    This scanner extends the base Scanner class with sophisticated
    liquidity analysis that provides deeper insights into market
    conditions and execution quality.
    """

    def __init__(self, cfg: BotConfig | None = None):
        """Initialize enhanced scanner with advanced liquidity analyzer."""
        super().__init__(cfg)

        # Initialize advanced liquidity analyzer
        liquidity_config = AdvancedLiquidityConfig(
            depth_levels=[0.01, 0.02, 0.05, 0.10],  # 1%, 2%, 5%, 10% depth levels
            low_impact_threshold=10.0,
            medium_impact_threshold=50.0,
            high_impact_threshold=100.0,
            benchmark_sizes=[100.0, 500.0, 1000.0, 5000.0],
            time_window_minutes=15,
            sample_interval_seconds=30,
            min_liquidity_usd=100.0,
            min_levels=3,
            max_spread_bps=500.0,
        )

        self.advanced_analyzer = AdvancedLiquidityAnalyzer(liquidity_config)

        # Cache for liquidity snapshots
        self.liquidity_snapshots: Dict[str, LiquiditySnapshot] = {}

        # Metrics tracking
        self.enhanced_scan_count = 0
        self.liquidity_warnings = []

        logger.info("Enhanced liquidity scanner initialized with advanced analysis")

    async def scan_once(self, top: int = 10) -> list[dict[str, Any]]:
        """
        Enhanced scan with advanced liquidity analysis.

        This method extends the base scan to include comprehensive
        liquidity analysis for each market.

        Args:
            top: Number of top markets to return

        Returns:
            List of market composites with enhanced liquidity data
        """
        # Get base scan results
        composites = await super().scan_once(top)

        # Enhance each composite with advanced liquidity analysis
        enhanced_composites = []

        for composite in composites:
            try:
                enhanced = await self._enhance_with_liquidity_analysis(composite)
                enhanced_composites.append(enhanced)

            except Exception as e:
                logger.error(
                    f"Error enhancing composite for {composite.get('market_slug', 'unknown')}: {e}"
                )
                # Keep original composite on error
                enhanced_composites.append(composite)

        self.enhanced_scan_count += 1

        # Log any liquidity warnings
        if self.liquidity_warnings:
            for warning in self.liquidity_warnings[-5:]:  # Show last 5 warnings
                logger.warning(warning)
            self.liquidity_warnings.clear()

        return enhanced_composites

    async def _enhance_with_liquidity_analysis(
        self, composite: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Enhance a market composite with advanced liquidity analysis.

        Args:
            composite: Original market composite

        Returns:
            Enhanced composite with liquidity metrics
        """
        market_slug = composite.get("market_slug", "unknown")

        # Get order book data if available
        yes_book = composite.get("yes_book", {})
        no_book = composite.get("no_book", {})

        # Analyze YES token liquidity
        yes_snapshot = None
        if yes_book:
            yes_snapshot = self.advanced_analyzer.analyze_order_book(
                yes_book, f"{market_slug}_YES"
            )
            self.liquidity_snapshots[f"{market_slug}_YES"] = yes_snapshot

        # Analyze NO token liquidity
        no_snapshot = None
        if no_book:
            no_snapshot = self.advanced_analyzer.analyze_order_book(
                no_book, f"{market_slug}_NO"
            )
            self.liquidity_snapshots[f"{market_slug}_NO"] = no_snapshot

        # Calculate combined liquidity metrics
        if yes_snapshot and no_snapshot:
            total_liquidity = (
                yes_snapshot.total_bid_liquidity
                + yes_snapshot.total_ask_liquidity
                + no_snapshot.total_bid_liquidity
                + no_snapshot.total_ask_liquidity
            )

            avg_spread = (yes_snapshot.spread_bps + no_snapshot.spread_bps) / 2
            avg_resilience = (
                yes_snapshot.resilience_score + no_snapshot.resilience_score
            ) / 2

            # Determine overall quality (worst of the two)
            if (
                yes_snapshot.liquidity_quality.value == "very_poor"
                or no_snapshot.liquidity_quality.value == "very_poor"
            ):
                overall_quality = "very_poor"
            elif (
                yes_snapshot.liquidity_quality.value == "poor"
                or no_snapshot.liquidity_quality.value == "poor"
            ):
                overall_quality = "poor"
            elif (
                yes_snapshot.liquidity_quality.value == "moderate"
                or no_snapshot.liquidity_quality.value == "moderate"
            ):
                overall_quality = "moderate"
            elif (
                yes_snapshot.liquidity_quality.value == "good"
                or no_snapshot.liquidity_quality.value == "good"
            ):
                overall_quality = "good"
            else:
                overall_quality = "excellent"

            # Calculate average price impacts
            avg_impact_100 = (
                yes_snapshot.impact_100_usd + no_snapshot.impact_100_usd
            ) / 2
            avg_impact_500 = (
                yes_snapshot.impact_500_usd + no_snapshot.impact_500_usd
            ) / 2
            avg_impact_1000 = (
                yes_snapshot.impact_1000_usd + no_snapshot.impact_1000_usd
            ) / 2

        else:
            # Fallback values if analysis failed
            total_liquidity = composite.get("liquidity", 0.0)
            avg_spread = composite.get("spread_bps", 0.0)
            avg_resilience = 0.0
            overall_quality = "unknown"
            avg_impact_100 = 0.0
            avg_impact_500 = 0.0
            avg_impact_1000 = 0.0

        # Replace simple liquidity value with comprehensive metrics
        composite["liquidity"] = total_liquidity  # Keep backward compatibility

        # Add advanced liquidity metrics
        composite["liquidity_advanced"] = {
            "total_liquidity_usd": total_liquidity,
            "average_spread_bps": avg_spread,
            "resilience_score": avg_resilience,
            "quality": overall_quality,
            "price_impacts": {
                "impact_100_usd": avg_impact_100,
                "impact_500_usd": avg_impact_500,
                "impact_1000_usd": avg_impact_1000,
            },
            "yes_liquidity": (
                {
                    "bid": yes_snapshot.total_bid_liquidity if yes_snapshot else 0.0,
                    "ask": yes_snapshot.total_ask_liquidity if yes_snapshot else 0.0,
                    "depth_1pct": yes_snapshot.depth_at_1pct if yes_snapshot else 0.0,
                    "depth_2pct": yes_snapshot.depth_at_2pct if yes_snapshot else 0.0,
                    "depth_5pct": yes_snapshot.depth_at_5pct if yes_snapshot else 0.0,
                    "profile": (
                        yes_snapshot.depth_profile.value if yes_snapshot else "unknown"
                    ),
                }
                if yes_snapshot
                else {}
            ),
            "no_liquidity": (
                {
                    "bid": no_snapshot.total_bid_liquidity if no_snapshot else 0.0,
                    "ask": no_snapshot.total_ask_liquidity if no_snapshot else 0.0,
                    "depth_1pct": no_snapshot.depth_at_1pct if no_snapshot else 0.0,
                    "depth_2pct": no_snapshot.depth_at_2pct if no_snapshot else 0.0,
                    "depth_5pct": no_snapshot.depth_at_5pct if no_snapshot else 0.0,
                    "profile": (
                        no_snapshot.depth_profile.value if no_snapshot else "unknown"
                    ),
                }
                if no_snapshot
                else {}
            ),
            "timestamp": yes_snapshot.timestamp if yes_snapshot else 0.0,
        }

        # Add execution quality indicators
        composite["execution_quality"] = {
            "can_execute_100_usd": avg_impact_100 < 50.0,  # Less than 50 bps impact
            "can_execute_500_usd": avg_impact_500 < 100.0,  # Less than 100 bps impact
            "can_execute_1000_usd": avg_impact_1000 < 200.0,  # Less than 200 bps impact
            "recommended_max_order": self._calculate_recommended_order_size(
                avg_impact_100, avg_impact_500, avg_impact_1000
            ),
        }

        # Generate warnings for poor liquidity
        if overall_quality in ["poor", "very_poor"]:
            self.liquidity_warnings.append(
                f"Market {market_slug} has {overall_quality} liquidity - exercise caution with large orders"
            )

        if avg_spread > 200:  # Over 200 bps spread
            self.liquidity_warnings.append(
                f"Market {market_slug} has wide spread ({avg_spread:.0f} bps) - high transaction costs"
            )

        return composite

    def _calculate_recommended_order_size(
        self, impact_100: float, impact_500: float, impact_1000: float
    ) -> float:
        """Calculate recommended maximum order size based on price impacts."""
        if impact_100 >= 100:  # 100+ bps impact for $100 order
            return 50.0  # Very limited liquidity
        elif impact_500 >= 100:  # 100+ bps impact for $500 order
            return 250.0
        elif impact_1000 >= 100:  # 100+ bps impact for $1000 order
            return 750.0
        elif impact_1000 >= 50:  # 50+ bps impact for $1000 order
            return 1500.0
        else:
            return 5000.0  # Good liquidity

    def estimate_order_slippage(
        self, market_slug: str, token_type: str, order_size_usd: float, side: str
    ) -> Optional[SlippageEstimate]:
        """
        Estimate slippage for a hypothetical order.

        Args:
            market_slug: Market identifier
            token_type: 'YES' or 'NO'
            order_size_usd: Order size in USD
            side: 'buy' or 'sell'

        Returns:
            Slippage estimate or None if not available
        """
        snapshot_key = f"{market_slug}_{token_type}"

        if snapshot_key not in self.liquidity_snapshots:
            logger.warning(f"No liquidity snapshot available for {snapshot_key}")
            return None

        snapshot = self.liquidity_snapshots[snapshot_key]

        # Get the appropriate order book from metadata
        book_data = snapshot.metadata.get("book_data", {})

        if not book_data:
            logger.warning(f"No order book data in snapshot for {snapshot_key}")
            return None

        return self.advanced_analyzer.estimate_slippage(book_data, order_size_usd, side)

    def get_liquidity_summary(self, market_slug: str) -> Dict[str, Any]:
        """
        Get comprehensive liquidity summary for a market.

        Args:
            market_slug: Market identifier

        Returns:
            Liquidity summary with recommendations
        """
        yes_key = f"{market_slug}_YES"
        no_key = f"{market_slug}_NO"

        yes_snapshot = self.liquidity_snapshots.get(yes_key)
        no_snapshot = self.liquidity_snapshots.get(no_key)

        if not yes_snapshot and not no_snapshot:
            return {
                "status": "no_data",
                "message": "No liquidity data available for this market",
            }

        summary = {
            "market_slug": market_slug,
            "timestamp": max(
                yes_snapshot.timestamp if yes_snapshot else 0,
                no_snapshot.timestamp if no_snapshot else 0,
            ),
            "yes_token": {
                "quality": (
                    yes_snapshot.liquidity_quality.value if yes_snapshot else "unknown"
                ),
                "total_liquidity": (
                    (
                        yes_snapshot.total_bid_liquidity
                        + yes_snapshot.total_ask_liquidity
                    )
                    if yes_snapshot
                    else 0
                ),
                "spread_bps": yes_snapshot.spread_bps if yes_snapshot else 0,
                "resilience": yes_snapshot.resilience_score if yes_snapshot else 0,
                "depth_profile": (
                    yes_snapshot.depth_profile.value if yes_snapshot else "unknown"
                ),
            },
            "no_token": {
                "quality": (
                    no_snapshot.liquidity_quality.value if no_snapshot else "unknown"
                ),
                "total_liquidity": (
                    (no_snapshot.total_bid_liquidity + no_snapshot.total_ask_liquidity)
                    if no_snapshot
                    else 0
                ),
                "spread_bps": no_snapshot.spread_bps if no_snapshot else 0,
                "resilience": no_snapshot.resilience_score if no_snapshot else 0,
                "depth_profile": (
                    no_snapshot.depth_profile.value if no_snapshot else "unknown"
                ),
            },
        }

        # Add recommendations
        recommendations = []

        if yes_snapshot and yes_snapshot.liquidity_quality.value in [
            "poor",
            "very_poor",
        ]:
            recommendations.append(
                "YES token has limited liquidity - use small orders or limit orders"
            )

        if no_snapshot and no_snapshot.liquidity_quality.value in ["poor", "very_poor"]:
            recommendations.append(
                "NO token has limited liquidity - use small orders or limit orders"
            )

        if yes_snapshot and yes_snapshot.spread_bps > 100:
            recommendations.append(
                f"YES token has wide spread ({yes_snapshot.spread_bps:.0f} bps) - consider limit orders"
            )

        if no_snapshot and no_snapshot.spread_bps > 100:
            recommendations.append(
                f"NO token has wide spread ({no_snapshot.spread_bps:.0f} bps) - consider limit orders"
            )

        if yes_snapshot and yes_snapshot.depth_profile.value == "top_heavy":
            recommendations.append(
                "YES token liquidity concentrated at top - larger orders will have high impact"
            )

        if no_snapshot and no_snapshot.depth_profile.value == "top_heavy":
            recommendations.append(
                "NO token liquidity concentrated at top - larger orders will have high impact"
            )

        summary["recommendations"] = (
            recommendations
            if recommendations
            else ["Market has adequate liquidity for trading"]
        )

        return summary

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for enhanced scanner."""
        base_stats = {
            "enhanced_scans": self.enhanced_scan_count,
            "markets_analyzed": len(self.liquidity_snapshots),
            "warnings_generated": len(self.liquidity_warnings),
        }

        # Add analyzer stats
        analyzer_stats = self.advanced_analyzer.get_performance_stats()
        base_stats.update(analyzer_stats)

        return base_stats


# Factory function for easy integration
def create_enhanced_scanner(
    config: Optional[BotConfig] = None,
) -> EnhancedLiquidityScanner:
    """
    Create an enhanced scanner with advanced liquidity analysis.

    Args:
        config: Bot configuration

    Returns:
        Enhanced scanner instance
    """
    scanner = EnhancedLiquidityScanner(config)
    logger.info("Created enhanced liquidity scanner with real-time order book analysis")
    return scanner
