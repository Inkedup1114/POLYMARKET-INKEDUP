"""
Liquidity calculation and management module for Polymarket order books.

This module provides various methods for calculating market liquidity
from order book data, supporting different calculation strategies.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class LiquidityMethod(str, Enum):
    """Liquidity calculation methods."""

    TOTAL_DEPTH = "total_depth"  # Sum of all bids and asks
    TOP_N_LEVELS = "top_n_levels"  # Sum of top N price levels
    WEIGHTED_DEPTH = "weighted_depth"  # Distance-weighted liquidity
    BID_ASK_IMBALANCE = "bid_ask_imbalance"  # Consider bid/ask balance
    EFFECTIVE_DEPTH = "effective_depth"  # Liquidity within percentage of mid


@dataclass
class LiquidityMetrics:
    """Container for comprehensive liquidity metrics."""

    total_bid_liquidity: float
    total_ask_liquidity: float
    total_liquidity: float
    bid_ask_ratio: float
    top_3_levels_liquidity: float
    effective_liquidity_1pct: float
    effective_liquidity_5pct: float
    market_depth_score: float
    method_used: str


@dataclass
class LiquidityConfig:
    """Configuration for liquidity calculations."""

    method: LiquidityMethod = LiquidityMethod.TOTAL_DEPTH
    top_n_levels: int = 3
    effective_spread_pct: float = 0.05  # 5% for effective depth
    min_price_threshold: float = 0.01  # Minimum price to consider
    max_price_threshold: float = 0.99  # Maximum price to consider
    cache_ttl_seconds: int = 30  # Cache results for 30 seconds
    weight_decay_factor: float = 0.8  # For weighted depth calculation

    # Fallback configuration
    fallback_enabled: bool = True
    fallback_minimum: float = 0.0
    fallback_market_average: float = 500.0
    fallback_high_volume: float = 2000.0
    api_timeout_seconds: float = 5.0
    max_retries: int = 2


class LiquidityCalculator:
    """
    Calculator for various liquidity metrics from order book data.

    Supports multiple calculation methods and caches results for performance.
    """

    def __init__(self, config: LiquidityConfig | None = None):
        """Initialize the liquidity calculator with configuration."""
        self.config = config or LiquidityConfig()
        self._cache: dict[str, tuple[float, LiquidityMetrics]] = {}

    def calculate_liquidity(
        self,
        book_data: dict[str, Any],
        method: LiquidityMethod | None = None,
        market_info: dict[str, Any] | None = None,
    ) -> float:
        """
        Calculate liquidity for a given order book using specified method with fallback support.

        Args:
            book_data: Order book data from API
            method: Calculation method to use (defaults to config method)
            market_info: Optional market information for intelligent fallbacks

        Returns:
            Calculated liquidity value with intelligent fallbacks
        """
        if not book_data:
            return self._get_fallback_liquidity(market_info, "empty_book_data")

        method = method or self.config.method
        retry_count = 0
        last_error = None

        while retry_count <= self.config.max_retries:
            try:
                # Check cache
                cache_key = self._get_cache_key(book_data, method)
                if cache_key in self._cache:
                    timestamp, metrics = self._cache[cache_key]
                    if timestamp > 0:  # Simple cache check
                        result = metrics.total_liquidity
                        if result > 0 or not self.config.fallback_enabled:
                            return result

                # Calculate metrics with timeout consideration
                metrics = self._calculate_comprehensive_metrics(book_data)

                # Apply selected method
                if method == LiquidityMethod.TOTAL_DEPTH:
                    result = metrics.total_liquidity
                elif method == LiquidityMethod.TOP_N_LEVELS:
                    result = metrics.top_3_levels_liquidity
                elif method == LiquidityMethod.WEIGHTED_DEPTH:
                    result = self._calculate_weighted_depth(book_data)
                elif method == LiquidityMethod.BID_ASK_IMBALANCE:
                    result = self._calculate_balanced_liquidity(metrics)
                elif method == LiquidityMethod.EFFECTIVE_DEPTH:
                    result = metrics.effective_liquidity_5pct
                else:
                    result = metrics.total_liquidity

                # Cache result
                self._cache[cache_key] = (1.0, metrics)  # Simple timestamp

                # Use fallback if result is zero and fallbacks are enabled
                if result <= 0 and self.config.fallback_enabled:
                    fallback_value = self._get_fallback_liquidity(
                        market_info, "zero_liquidity"
                    )
                    logger.warning(
                        f"Calculated liquidity is {result}, using fallback: {fallback_value}"
                    )
                    return fallback_value

                return max(result, self.config.fallback_minimum)

            except Exception as e:
                last_error = e
                retry_count += 1
                logger.warning(
                    f"Liquidity calculation attempt {retry_count} failed: {e}"
                )

                if retry_count <= self.config.max_retries:
                    continue

        # All retries exhausted
        logger.error(
            f"All liquidity calculation attempts failed. Last error: {last_error}"
        )
        return self._get_fallback_liquidity(market_info, "calculation_failed")

    def get_comprehensive_metrics(self, book_data: dict[str, Any]) -> LiquidityMetrics:
        """
        Get comprehensive liquidity metrics for an order book.

        Args:
            book_data: Order book data from API

        Returns:
            Complete liquidity metrics
        """
        try:
            return self._calculate_comprehensive_metrics(book_data)
        except Exception as e:
            logger.error(f"Error calculating comprehensive metrics: {e}")
            return LiquidityMetrics(
                total_bid_liquidity=0.0,
                total_ask_liquidity=0.0,
                total_liquidity=0.0,
                bid_ask_ratio=0.0,
                top_3_levels_liquidity=0.0,
                effective_liquidity_1pct=0.0,
                effective_liquidity_5pct=0.0,
                market_depth_score=0.0,
                method_used="error",
            )

    def _calculate_comprehensive_metrics(
        self, book_data: dict[str, Any]
    ) -> LiquidityMetrics:
        """Calculate all liquidity metrics for an order book."""
        bids = book_data.get("bids", [])
        asks = book_data.get("asks", [])

        if not bids and not asks:
            return LiquidityMetrics(
                total_bid_liquidity=0.0,
                total_ask_liquidity=0.0,
                total_liquidity=0.0,
                bid_ask_ratio=0.0,
                top_3_levels_liquidity=0.0,
                effective_liquidity_1pct=0.0,
                effective_liquidity_5pct=0.0,
                market_depth_score=0.0,
                method_used=str(self.config.method),
            )

        # Calculate basic liquidity
        bid_liquidity = self._calculate_side_liquidity(bids)
        ask_liquidity = self._calculate_side_liquidity(asks)
        total_liquidity = bid_liquidity + ask_liquidity

        # Calculate bid/ask ratio
        bid_ask_ratio = bid_liquidity / ask_liquidity if ask_liquidity > 0 else 0.0

        # Calculate top N levels liquidity
        top_bid_liquidity = self._calculate_top_n_liquidity(
            bids, self.config.top_n_levels
        )
        top_ask_liquidity = self._calculate_top_n_liquidity(
            asks, self.config.top_n_levels
        )
        top_3_levels_liquidity = top_bid_liquidity + top_ask_liquidity

        # Calculate effective liquidity at different spreads
        mid_price = self._calculate_mid_price(bids, asks)
        effective_1pct = self._calculate_effective_liquidity(
            bids, asks, mid_price, 0.01
        )
        effective_5pct = self._calculate_effective_liquidity(
            bids, asks, mid_price, 0.05
        )

        # Calculate overall market depth score
        depth_score = self._calculate_market_depth_score(
            total_liquidity, bid_ask_ratio, len(bids), len(asks)
        )

        return LiquidityMetrics(
            total_bid_liquidity=bid_liquidity,
            total_ask_liquidity=ask_liquidity,
            total_liquidity=total_liquidity,
            bid_ask_ratio=bid_ask_ratio,
            top_3_levels_liquidity=top_3_levels_liquidity,
            effective_liquidity_1pct=effective_1pct,
            effective_liquidity_5pct=effective_5pct,
            market_depth_score=depth_score,
            method_used=str(self.config.method),
        )

    def _calculate_side_liquidity(self, orders: list[dict[str, Any]]) -> float:
        """Calculate liquidity for one side of the order book."""
        total = 0.0
        for order in orders:
            try:
                price = float(order.get("price", 0))
                size = float(order.get("size", 0))

                # Filter out orders outside price thresholds
                if (
                    price < self.config.min_price_threshold
                    or price > self.config.max_price_threshold
                ):
                    continue

                # Calculate USD value of liquidity
                total += price * size

            except (ValueError, TypeError) as e:
                logger.debug(f"Error parsing order: {e}")
                continue

        return total

    def _calculate_top_n_liquidity(self, orders: list[dict[str, Any]], n: int) -> float:
        """Calculate liquidity for top N price levels."""
        if not orders or n <= 0:
            return 0.0

        # Take top N orders (assuming they're already sorted)
        top_orders = orders[:n]
        return self._calculate_side_liquidity(top_orders)

    def _calculate_mid_price(
        self, bids: list[dict[str, Any]], asks: list[dict[str, Any]]
    ) -> float | None:
        """Calculate mid price from best bid and ask."""
        try:
            if not bids or not asks:
                return None

            best_bid = float(bids[0].get("price", 0))
            best_ask = float(asks[0].get("price", 0))

            if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
                return None

            return (best_bid + best_ask) / 2.0

        except (ValueError, TypeError, IndexError):
            return None

    def _calculate_effective_liquidity(
        self,
        bids: list[dict[str, Any]],
        asks: list[dict[str, Any]],
        mid_price: float | None,
        spread_pct: float,
    ) -> float:
        """Calculate effective liquidity within percentage of mid price."""
        if not mid_price or mid_price <= 0:
            return 0.0

        spread_threshold = mid_price * spread_pct
        min_bid_price = mid_price - spread_threshold
        max_ask_price = mid_price + spread_threshold

        # Count liquidity within the spread
        effective_liquidity = 0.0

        # Add bid liquidity within threshold
        for bid in bids:
            try:
                price = float(bid.get("price", 0))
                size = float(bid.get("size", 0))
                if price >= min_bid_price:
                    effective_liquidity += price * size
                else:
                    break  # Orders should be sorted by price
            except (ValueError, TypeError):
                continue

        # Add ask liquidity within threshold
        for ask in asks:
            try:
                price = float(ask.get("price", 0))
                size = float(ask.get("size", 0))
                if price <= max_ask_price:
                    effective_liquidity += price * size
                else:
                    break  # Orders should be sorted by price
            except (ValueError, TypeError):
                continue

        return effective_liquidity

    def _calculate_weighted_depth(self, book_data: dict[str, Any]) -> float:
        """Calculate liquidity with distance-based weighting."""
        bids = book_data.get("bids", [])
        asks = book_data.get("asks", [])

        if not bids and not asks:
            return 0.0

        mid_price = self._calculate_mid_price(bids, asks)
        if not mid_price:
            # Fallback to simple calculation if no mid price
            return self._calculate_side_liquidity(
                bids
            ) + self._calculate_side_liquidity(asks)

        weighted_liquidity = 0.0

        # Weight bids by distance from mid
        for i, bid in enumerate(bids):
            try:
                price = float(bid.get("price", 0))
                size = float(bid.get("size", 0))

                # Calculate weight based on distance and position
                distance_weight = 1.0 - abs(price - mid_price) / mid_price
                position_weight = self.config.weight_decay_factor**i
                weight = distance_weight * position_weight

                weighted_liquidity += price * size * weight

            except (ValueError, TypeError):
                continue

        # Weight asks by distance from mid
        for i, ask in enumerate(asks):
            try:
                price = float(ask.get("price", 0))
                size = float(ask.get("size", 0))

                # Calculate weight based on distance and position
                distance_weight = 1.0 - abs(price - mid_price) / mid_price
                position_weight = self.config.weight_decay_factor**i
                weight = distance_weight * position_weight

                weighted_liquidity += price * size * weight

            except (ValueError, TypeError):
                continue

        return weighted_liquidity

    def _calculate_balanced_liquidity(self, metrics: LiquidityMetrics) -> float:
        """Calculate liquidity considering bid/ask imbalance."""
        # Penalize extreme imbalances
        if metrics.bid_ask_ratio == 0:
            return metrics.total_ask_liquidity  # Only ask liquidity

        # Use harmonic mean to penalize imbalances
        bid_liq = metrics.total_bid_liquidity
        ask_liq = metrics.total_ask_liquidity

        if bid_liq == 0 or ask_liq == 0:
            return bid_liq + ask_liq  # Fallback to total

        # Harmonic mean gives lower values for imbalanced markets
        harmonic_mean = 2 * (bid_liq * ask_liq) / (bid_liq + ask_liq)

        # Weight between harmonic mean and total
        balance_factor = min(metrics.bid_ask_ratio, 1 / metrics.bid_ask_ratio)

        return (
            balance_factor * harmonic_mean
            + (1 - balance_factor) * metrics.total_liquidity
        )

    def _calculate_market_depth_score(
        self, total_liquidity: float, bid_ask_ratio: float, num_bids: int, num_asks: int
    ) -> float:
        """Calculate overall market depth quality score."""
        if total_liquidity == 0:
            return 0.0

        # Base score from total liquidity (log scale)
        import math

        base_score = math.log10(max(1, total_liquidity))

        # Penalty for imbalanced bid/ask ratio
        balance_penalty = 1.0 - abs(
            1.0 - min(bid_ask_ratio, 1 / bid_ask_ratio if bid_ask_ratio > 0 else 0)
        )

        # Bonus for order book depth (number of levels)
        depth_bonus = min(
            1.0, (num_bids + num_asks) / 20.0
        )  # Max bonus at 20 total levels

        return base_score * balance_penalty * (1 + depth_bonus)

    def _get_cache_key(self, book_data: dict[str, Any], method: LiquidityMethod) -> str:
        """Generate cache key for book data and method."""
        # Simple cache key based on first few price levels and method
        bids = book_data.get("bids", [])[:3]
        asks = book_data.get("asks", [])[:3]

        key_parts = [str(method)]
        for bid in bids:
            key_parts.append(f"b{bid.get('price', 0)}{bid.get('size', 0)}")
        for ask in asks:
            key_parts.append(f"a{ask.get('price', 0)}{ask.get('size', 0)}")

        return "|".join(key_parts)

    def clear_cache(self) -> None:
        """Clear the liquidity calculation cache."""
        self._cache.clear()

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics."""
        return {
            "cache_size": len(self._cache),
            "cache_ttl": self.config.cache_ttl_seconds,
        }

    def _get_fallback_liquidity(
        self, market_info: dict[str, Any] | None, reason: str
    ) -> float:
        """
        Get intelligent fallback liquidity value based on market information.

        Args:
            market_info: Optional market information for context
            reason: Reason for using fallback (for logging)

        Returns:
            Appropriate fallback liquidity value
        """
        if not self.config.fallback_enabled:
            logger.debug(
                f"Fallback disabled, returning minimum: {self.config.fallback_minimum}"
            )
            return self.config.fallback_minimum

        # Start with minimum fallback
        fallback_value = self.config.fallback_minimum

        if market_info:
            # Use market-specific information to determine appropriate fallback
            volume_24h = market_info.get("volume_24h", 0)
            num_traders = market_info.get("traders", 0)
            market_age_days = market_info.get("age_days", 0)
            is_popular = market_info.get("is_popular", False)

            # High volume markets get higher fallback liquidity
            if volume_24h > 10000:  # High volume threshold
                fallback_value = max(fallback_value, self.config.fallback_high_volume)
                logger.debug(
                    f"Using high volume fallback: {fallback_value} (volume: {volume_24h})"
                )
            elif volume_24h > 1000:  # Medium volume threshold
                fallback_value = max(
                    fallback_value, self.config.fallback_market_average
                )
                logger.debug(
                    f"Using average volume fallback: {fallback_value} (volume: {volume_24h})"
                )

            # Popular or well-established markets get higher fallback
            if is_popular or (num_traders > 50 and market_age_days > 7):
                fallback_value = max(
                    fallback_value, self.config.fallback_market_average
                )
                logger.debug(
                    f"Using established market fallback: {fallback_value} "
                    f"(traders: {num_traders}, age: {market_age_days} days)"
                )

        else:
            # No market info available, use conservative fallback
            fallback_value = self.config.fallback_market_average
            logger.debug(f"No market info, using average fallback: {fallback_value}")

        logger.info(
            f"Using liquidity fallback: {fallback_value:.2f} (reason: {reason})"
        )

        return fallback_value

    def calculate_liquidity_with_market_context(
        self,
        book_data: dict[str, Any],
        market_slug: str,
        volume_24h: float = 0.0,
        traders_count: int = 0,
        method: LiquidityMethod | None = None,
    ) -> float:
        """
        Calculate liquidity with additional market context for better fallback decisions.

        Args:
            book_data: Order book data from API
            market_slug: Market identifier for logging
            volume_24h: 24-hour trading volume
            traders_count: Number of unique traders
            method: Calculation method to use

        Returns:
            Calculated or fallback liquidity value
        """
        market_info = {
            "market_slug": market_slug,
            "volume_24h": volume_24h,
            "traders": traders_count,
            "is_popular": volume_24h > 5000 or traders_count > 100,
        }

        result = self.calculate_liquidity(book_data, method, market_info)

        logger.debug(
            f"Liquidity for {market_slug}: {result:.2f} "
            f"(volume_24h: {volume_24h}, traders: {traders_count})"
        )

        return result
