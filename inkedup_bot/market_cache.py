#!/usr/bin/env python3
"""
Market Data Caching System for InkedUp Bot

This module provides specialized caching for market data including:
- Static market information caching
- Price data caching with volatility-based TTL
- Order book caching with smart refresh
- Trading pair information caching
- Market metadata caching
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from .cache import CacheConfig, CacheStrategy, cache_manager, cached

logger = logging.getLogger("market_cache")


@dataclass
class MarketCacheConfig:
    """Configuration for market data caching."""

    # Static data caching (rarely changes)
    market_info_ttl: float = 3600.0  # 1 hour
    trading_pairs_ttl: float = 1800.0  # 30 minutes
    market_metadata_ttl: float = 7200.0  # 2 hours

    # Dynamic data caching (changes frequently)
    price_data_ttl: float = 60.0  # 1 minute
    order_book_ttl: float = 10.0  # 10 seconds
    volume_data_ttl: float = 120.0  # 2 minutes

    # Volatility-based TTL adjustments
    enable_volatility_adjustment: bool = True
    high_volatility_multiplier: float = 0.5  # Reduce TTL by 50% for volatile markets
    low_volatility_multiplier: float = 2.0  # Increase TTL by 100% for stable markets
    volatility_threshold: float = 0.05  # 5% price change threshold

    # Smart refresh settings
    enable_smart_refresh: bool = True
    refresh_threshold: float = 0.7  # Refresh when 70% of TTL elapsed
    max_concurrent_refreshes: int = 10

    # Cache sizes
    max_market_entries: int = 1000
    max_price_entries: int = 5000
    max_book_entries: int = 2000

    # Performance settings
    enable_preloading: bool = True
    preload_popular_markets: bool = True
    popular_market_threshold: int = 100  # Volume threshold


class MarketDataCache:
    """
    Specialized cache for market data with intelligent refresh strategies.
    """

    def __init__(self, config: MarketCacheConfig = None):
        self.config = config or MarketCacheConfig()

        # Initialize specialized cache instances
        self._init_caches()

        # Market volatility tracking
        self._price_history: dict[str, list[tuple[float, float]]] = (
            {}
        )  # market_id -> [(timestamp, price)]
        self._volatility_cache: dict[str, float] = {}  # market_id -> volatility

        # Popular markets tracking
        self._market_access_counts: dict[str, int] = {}
        self._popular_markets: set[str] = set()

        # Refresh tracking
        self._refresh_in_progress: set[str] = set()

        logger.info("Initialized market data cache system")

    def _init_caches(self):
        """Initialize specialized cache instances."""

        # Static market information cache
        market_info_config = CacheConfig(
            max_size=self.config.max_market_entries,
            default_ttl=self.config.market_info_ttl,
            strategy=CacheStrategy.TTL,
            enable_background_refresh=True,
            refresh_threshold=0.8,
        )
        self.market_info_cache = cache_manager.get_cache(
            "market_info", market_info_config
        )

        # Price data cache
        price_config = CacheConfig(
            max_size=self.config.max_price_entries,
            default_ttl=self.config.price_data_ttl,
            strategy=CacheStrategy.LRU,
            enable_background_refresh=self.config.enable_smart_refresh,
            refresh_threshold=self.config.refresh_threshold,
        )
        self.price_cache = cache_manager.get_cache("price_data", price_config)

        # Order book cache
        book_config = CacheConfig(
            max_size=self.config.max_book_entries,
            default_ttl=self.config.order_book_ttl,
            strategy=CacheStrategy.LRU,
            enable_background_refresh=True,
            refresh_threshold=0.6,
        )
        self.book_cache = cache_manager.get_cache("order_books", book_config)

        # Market metadata cache
        metadata_config = CacheConfig(
            max_size=self.config.max_market_entries,
            default_ttl=self.config.market_metadata_ttl,
            strategy=CacheStrategy.TTL,
            enable_background_refresh=True,
        )
        self.metadata_cache = cache_manager.get_cache(
            "market_metadata", metadata_config
        )

        # Register refresh callbacks
        self._register_refresh_callbacks()

    def _register_refresh_callbacks(self):
        """Register refresh callbacks for different data types."""

        # Market info refresh
        self.market_info_cache.register_refresh_callback(
            "market:*", self._refresh_market_info
        )

        # Price data refresh
        self.price_cache.register_refresh_callback("price:*", self._refresh_price_data)

        # Order book refresh
        self.book_cache.register_refresh_callback("book:*", self._refresh_order_book)

    async def get_market_info(
        self, market_id: str, force_refresh: bool = False
    ) -> dict[str, Any] | None:
        """
        Get market information with caching.

        Args:
            market_id: Market identifier
            force_refresh: Force refresh from source

        Returns:
            Market information dictionary
        """
        self._track_market_access(market_id)

        cache_key = f"market:{market_id}"

        if force_refresh:
            await self.market_info_cache.delete(cache_key)

        return await self.market_info_cache.get(cache_key)

    async def set_market_info(
        self,
        market_id: str,
        market_data: dict[str, Any],
        ttl_override: float | None = None,
    ) -> bool:
        """
        Cache market information.

        Args:
            market_id: Market identifier
            market_data: Market data to cache
            ttl_override: Override default TTL

        Returns:
            True if cached successfully
        """
        cache_key = f"market:{market_id}"
        ttl = ttl_override or self.config.market_info_ttl

        # Add market access tracking
        self._track_market_access(market_id)

        tags = {"market_data", "static"}
        if market_id in self._popular_markets:
            tags.add("popular")

        return await self.market_info_cache.set(
            cache_key, market_data, ttl=ttl, tags=tags
        )

    async def get_price_data(
        self, market_id: str, token_id: str = None
    ) -> dict[str, Any] | None:
        """
        Get price data with volatility-adjusted caching.

        Args:
            market_id: Market identifier
            token_id: Specific token ID (optional)

        Returns:
            Price data dictionary
        """
        self._track_market_access(market_id)

        cache_key = f"price:{market_id}"
        if token_id:
            cache_key += f":{token_id}"

        return await self.price_cache.get(cache_key)

    async def set_price_data(
        self, market_id: str, price_data: dict[str, Any], token_id: str = None
    ) -> bool:
        """
        Cache price data with volatility-based TTL adjustment.

        Args:
            market_id: Market identifier
            price_data: Price data to cache
            token_id: Specific token ID (optional)

        Returns:
            True if cached successfully
        """
        cache_key = f"price:{market_id}"
        if token_id:
            cache_key += f":{token_id}"

        # Calculate volatility-adjusted TTL
        ttl = await self._calculate_price_ttl(market_id, price_data)

        # Update price history for volatility calculation
        await self._update_price_history(market_id, price_data)

        tags = {"price_data", "dynamic"}
        if self._is_high_volatility(market_id):
            tags.add("high_volatility")
        if market_id in self._popular_markets:
            tags.add("popular")

        return await self.price_cache.set(cache_key, price_data, ttl=ttl, tags=tags)

    async def get_order_book(self, token_id: str) -> dict[str, Any] | None:
        """
        Get order book data with smart refresh.

        Args:
            token_id: Token identifier

        Returns:
            Order book data
        """
        cache_key = f"book:{token_id}"
        return await self.book_cache.get(cache_key)

    async def set_order_book(
        self, token_id: str, book_data: dict[str, Any], market_id: str = None
    ) -> bool:
        """
        Cache order book data.

        Args:
            token_id: Token identifier
            book_data: Order book data
            market_id: Associated market ID

        Returns:
            True if cached successfully
        """
        cache_key = f"book:{token_id}"

        # Adjust TTL based on market activity
        ttl = self.config.order_book_ttl
        if market_id and self._is_high_volatility(market_id):
            ttl *= self.config.high_volatility_multiplier

        tags = {"order_book", "dynamic"}
        if market_id:
            tags.add(f"market:{market_id}")
            if market_id in self._popular_markets:
                tags.add("popular")

        return await self.book_cache.set(cache_key, book_data, ttl=ttl, tags=tags)

    async def get_market_metadata(self, market_id: str) -> dict[str, Any] | None:
        """
        Get market metadata (configuration, rules, etc.).

        Args:
            market_id: Market identifier

        Returns:
            Market metadata
        """
        cache_key = f"metadata:{market_id}"
        return await self.metadata_cache.get(cache_key)

    async def set_market_metadata(
        self, market_id: str, metadata: dict[str, Any]
    ) -> bool:
        """
        Cache market metadata.

        Args:
            market_id: Market identifier
            metadata: Metadata to cache

        Returns:
            True if cached successfully
        """
        cache_key = f"metadata:{market_id}"

        tags = {"metadata", "static"}

        return await self.metadata_cache.set(
            cache_key, metadata, ttl=self.config.market_metadata_ttl, tags=tags
        )

    async def warm_popular_markets(self, market_loader: callable, top_n: int = 50):
        """
        Warm cache with popular market data.

        Args:
            market_loader: Function to load market data
            top_n: Number of top markets to warm
        """
        try:
            if not self.config.enable_preloading:
                return

            logger.info(f"Warming cache with top {top_n} popular markets")

            # Load market list
            markets = await market_loader()

            # Sort by volume or activity
            if isinstance(markets, list) and markets:
                sorted_markets = sorted(
                    markets, key=lambda m: m.get("volume", 0), reverse=True
                )

                popular_markets = sorted_markets[:top_n]

                # Pre-load market info
                warming_tasks = []
                for market in popular_markets:
                    market_id = market.get("id") or market.get("market_id")
                    if market_id:
                        self._popular_markets.add(market_id)
                        warming_tasks.append(self.set_market_info(market_id, market))

                # Execute warming tasks
                await asyncio.gather(*warming_tasks, return_exceptions=True)

                logger.info(f"Warmed cache with {len(warming_tasks)} popular markets")

        except Exception as e:
            logger.error(f"Failed to warm popular markets cache: {e}")

    async def invalidate_market_data(self, market_id: str):
        """
        Invalidate all cached data for a specific market.

        Args:
            market_id: Market to invalidate
        """
        # Invalidate by tags
        await self.market_info_cache.invalidate_by_tag(f"market:{market_id}")
        await self.price_cache.invalidate_by_tag(f"market:{market_id}")
        await self.book_cache.invalidate_by_tag(f"market:{market_id}")
        await self.metadata_cache.invalidate_by_tag(f"market:{market_id}")

        # Invalidate by patterns
        await self.market_info_cache.invalidate_by_pattern(f"market:{market_id}*")
        await self.price_cache.invalidate_by_pattern(f"price:{market_id}*")
        await self.book_cache.invalidate_by_pattern(f"book:{market_id}*")

        logger.info(f"Invalidated all cached data for market {market_id}")

    async def invalidate_volatile_markets(self):
        """Invalidate cached data for highly volatile markets."""
        volatile_markets = [
            market_id
            for market_id, volatility in self._volatility_cache.items()
            if volatility > self.config.volatility_threshold * 2
        ]

        for market_id in volatile_markets:
            await self.price_cache.invalidate_by_pattern(f"price:{market_id}*")
            await self.book_cache.invalidate_by_pattern(f"book:*{market_id}*")

        if volatile_markets:
            logger.info(
                f"Invalidated cache for {len(volatile_markets)} volatile markets"
            )

    def _track_market_access(self, market_id: str):
        """Track market access for popularity ranking."""
        if market_id not in self._market_access_counts:
            self._market_access_counts[market_id] = 0

        self._market_access_counts[market_id] += 1

        # Update popular markets set
        if (
            self._market_access_counts[market_id]
            >= self.config.popular_market_threshold
        ):
            self._popular_markets.add(market_id)

    async def _calculate_price_ttl(
        self, market_id: str, price_data: dict[str, Any]
    ) -> float:
        """
        Calculate TTL for price data based on market volatility.

        Args:
            market_id: Market identifier
            price_data: Current price data

        Returns:
            Calculated TTL in seconds
        """
        base_ttl = self.config.price_data_ttl

        if not self.config.enable_volatility_adjustment:
            return base_ttl

        volatility = self._get_market_volatility(market_id)

        if volatility > self.config.volatility_threshold:
            # High volatility - reduce TTL
            return base_ttl * self.config.high_volatility_multiplier
        elif volatility < self.config.volatility_threshold / 2:
            # Low volatility - increase TTL
            return base_ttl * self.config.low_volatility_multiplier
        else:
            # Normal volatility
            return base_ttl

    async def _update_price_history(self, market_id: str, price_data: dict[str, Any]):
        """Update price history for volatility calculation."""
        try:
            current_time = time.time()

            # Extract price from data (handle different formats)
            price = None
            if "yes_price" in price_data:
                price = float(price_data["yes_price"])
            elif "price" in price_data:
                price = float(price_data["price"])
            elif "mid_price" in price_data:
                price = float(price_data["mid_price"])

            if price is None:
                return

            # Initialize history if needed
            if market_id not in self._price_history:
                self._price_history[market_id] = []

            # Add new price point
            self._price_history[market_id].append((current_time, price))

            # Keep only last hour of data
            cutoff_time = current_time - 3600
            self._price_history[market_id] = [
                (timestamp, price)
                for timestamp, price in self._price_history[market_id]
                if timestamp > cutoff_time
            ]

            # Calculate volatility
            self._calculate_volatility(market_id)

        except Exception as e:
            logger.error(f"Error updating price history for {market_id}: {e}")

    def _calculate_volatility(self, market_id: str):
        """Calculate price volatility for a market."""
        if market_id not in self._price_history:
            return

        history = self._price_history[market_id]
        if len(history) < 2:
            return

        # Calculate price changes
        price_changes = []
        for i in range(1, len(history)):
            prev_price = history[i - 1][1]
            curr_price = history[i][1]

            if prev_price > 0:
                change = abs(curr_price - prev_price) / prev_price
                price_changes.append(change)

        if price_changes:
            # Use standard deviation as volatility measure
            mean_change = sum(price_changes) / len(price_changes)
            variance = sum(
                (change - mean_change) ** 2 for change in price_changes
            ) / len(price_changes)
            volatility = variance**0.5

            self._volatility_cache[market_id] = volatility

    def _get_market_volatility(self, market_id: str) -> float:
        """Get volatility measure for a market."""
        return self._volatility_cache.get(market_id, 0.0)

    def _is_high_volatility(self, market_id: str) -> bool:
        """Check if market is highly volatile."""
        return self._get_market_volatility(market_id) > self.config.volatility_threshold

    async def _refresh_market_info(self, cache_key: str) -> dict[str, Any] | None:
        """Refresh callback for market info."""
        if cache_key in self._refresh_in_progress:
            return None

        self._refresh_in_progress.add(cache_key)

        try:
            # Extract market_id from cache key (format: "market:market_id")
            market_id = cache_key.split(":", 1)[1]

            # Here you would implement the actual refresh logic
            # This is a placeholder - integrate with your data source
            logger.debug(f"Refreshing market info for {market_id}")

            # Return None to indicate refresh is handled externally
            return None

        finally:
            self._refresh_in_progress.discard(cache_key)

    async def _refresh_price_data(self, cache_key: str) -> dict[str, Any] | None:
        """Refresh callback for price data."""
        if cache_key in self._refresh_in_progress:
            return None

        self._refresh_in_progress.add(cache_key)

        try:
            # Extract identifiers from cache key
            parts = cache_key.split(":")
            market_id = parts[1]
            token_id = parts[2] if len(parts) > 2 else None

            logger.debug(f"Refreshing price data for {market_id}:{token_id}")

            # Placeholder for refresh logic
            return None

        finally:
            self._refresh_in_progress.discard(cache_key)

    async def _refresh_order_book(self, cache_key: str) -> dict[str, Any] | None:
        """Refresh callback for order book data."""
        if cache_key in self._refresh_in_progress:
            return None

        self._refresh_in_progress.add(cache_key)

        try:
            # Extract token_id from cache key (format: "book:token_id")
            token_id = cache_key.split(":", 1)[1]

            logger.debug(f"Refreshing order book for {token_id}")

            # Placeholder for refresh logic
            return None

        finally:
            self._refresh_in_progress.discard(cache_key)

    def get_cache_stats(self) -> dict[str, Any]:
        """Get comprehensive cache statistics."""
        return {
            "market_info_cache": self.market_info_cache.get_stats(),
            "price_cache": self.price_cache.get_stats(),
            "book_cache": self.book_cache.get_stats(),
            "metadata_cache": self.metadata_cache.get_stats(),
            "popular_markets": len(self._popular_markets),
            "volatility_tracking": len(self._volatility_cache),
            "access_counts": len(self._market_access_counts),
            "config": {
                "market_info_ttl": self.config.market_info_ttl,
                "price_data_ttl": self.config.price_data_ttl,
                "order_book_ttl": self.config.order_book_ttl,
                "volatility_adjustment": self.config.enable_volatility_adjustment,
                "smart_refresh": self.config.enable_smart_refresh,
            },
        }

    async def shutdown(self):
        """Shutdown market cache system."""
        logger.info("Shutting down market data cache")

        await self.market_info_cache.shutdown()
        await self.price_cache.shutdown()
        await self.book_cache.shutdown()
        await self.metadata_cache.shutdown()


# Global market cache instance
_market_cache_instance = None


def get_market_cache(config: MarketCacheConfig = None) -> MarketDataCache:
    """Get global market cache instance."""
    global _market_cache_instance

    if _market_cache_instance is None:
        _market_cache_instance = MarketDataCache(config)

    return _market_cache_instance


# Convenient decorators for market data caching
def cache_market_info(ttl: float = 3600.0):
    """Decorator for caching market information."""
    return cached("market_info", ttl=ttl, tags={"market_data", "static"})


def cache_price_data(ttl: float = 60.0):
    """Decorator for caching price data."""
    return cached("price_data", ttl=ttl, tags={"price_data", "dynamic"})


def cache_order_book(ttl: float = 10.0):
    """Decorator for caching order book data."""
    return cached("order_books", ttl=ttl, tags={"order_book", "dynamic"})
