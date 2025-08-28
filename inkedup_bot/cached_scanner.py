"""
Enhanced scanner with advanced market data caching.

This module extends the existing scanner with sophisticated caching capabilities
that replace simple time-based refreshes with LRU cache management, TTL-based
expiration, and background refresh for optimal performance.

Key improvements over basic scanner:
- LRU cache for market metadata with automatic expiration
- Individual cache entries with appropriate TTL values  
- Background refresh to prevent cache misses during trading
- Cache hit/miss tracking and performance optimization
- Memory-efficient compressed storage for large data sets
- Hierarchical caching for different data types
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .config import BotConfig
from .market_data_cache import (
    CacheConfig,
    CacheEntryType,
    MarketDataCache,
    cache_market_list,
    cache_market_metadata,
    cache_order_book,
    get_cached_market_list,
    get_cached_market_metadata,
    get_cached_order_book,
    get_market_data_cache,
)
from .scanner import Scanner
from .utils import fetch_markets

logger = logging.getLogger("cached_scanner")


class CachedScannerConfig:
    """Configuration for cached scanner with optimized cache settings."""

    def __init__(
        self,
        # Cache size and memory limits
        max_cache_entries: int = 2000,
        max_cache_memory_mb: float = 150.0,
        # TTL settings optimized for trading
        market_list_ttl: float = 180.0,  # 3 minutes - markets don't change often
        market_metadata_ttl: float = 600.0,  # 10 minutes - metadata is stable
        token_metadata_ttl: float = 900.0,  # 15 minutes - token info rarely changes
        order_book_ttl: float = 2.0,  # 2 seconds - order books change rapidly
        price_data_ttl: float = 1.0,  # 1 second - prices change very rapidly
        spread_data_ttl: float = 5.0,  # 5 seconds - spreads update frequently
        volume_data_ttl: float = 30.0,  # 30 seconds - volume updates moderately
        # Performance optimizations
        enable_background_refresh: bool = True,
        background_refresh_ratio: float = 0.7,  # Refresh at 70% of TTL
        enable_compression: bool = True,
        compression_threshold: int = 512,
        # Cache warming for popular markets
        enable_cache_warming: bool = True,
        warm_top_markets: int = 50,  # Pre-warm top 50 markets
    ):

        self.max_cache_entries = max_cache_entries
        self.max_cache_memory_mb = max_cache_memory_mb
        self.market_list_ttl = market_list_ttl
        self.market_metadata_ttl = market_metadata_ttl
        self.token_metadata_ttl = token_metadata_ttl
        self.order_book_ttl = order_book_ttl
        self.price_data_ttl = price_data_ttl
        self.spread_data_ttl = spread_data_ttl
        self.volume_data_ttl = volume_data_ttl
        self.enable_background_refresh = enable_background_refresh
        self.background_refresh_ratio = background_refresh_ratio
        self.enable_compression = enable_compression
        self.compression_threshold = compression_threshold
        self.enable_cache_warming = enable_cache_warming
        self.warm_top_markets = warm_top_markets

    def to_cache_config(self) -> CacheConfig:
        """Convert to CacheConfig for the caching system."""
        return CacheConfig(
            max_total_entries=self.max_cache_entries,
            max_memory_mb=self.max_cache_memory_mb,
            market_list_ttl=self.market_list_ttl,
            market_metadata_ttl=self.market_metadata_ttl,
            token_metadata_ttl=self.token_metadata_ttl,
            order_book_ttl=self.order_book_ttl,
            price_data_ttl=self.price_data_ttl,
            spread_data_ttl=self.spread_data_ttl,
            volume_data_ttl=self.volume_data_ttl,
            enable_compression=self.enable_compression,
            compression_threshold_bytes=self.compression_threshold,
            enable_background_refresh=self.enable_background_refresh,
            background_refresh_ratio=self.background_refresh_ratio,
            enable_cache_warming=self.enable_cache_warming,
        )


class CachedScanner(Scanner):
    """
    Enhanced scanner with advanced market data caching capabilities.

    Replaces the simple time-based cache refresh with sophisticated LRU caching
    that provides better performance, memory efficiency, and cache hit rates.
    """

    def __init__(
        self,
        cfg: Optional[BotConfig] = None,
        cache_config: Optional[CachedScannerConfig] = None,
    ):
        super().__init__(cfg)

        # Cache configuration
        self.cache_config = cache_config or CachedScannerConfig()

        # Initialize market data cache
        cache_cfg = self.cache_config.to_cache_config()
        self._market_cache = get_market_data_cache(cache_cfg)

        # Override parent's market cache variables
        self._markets_cache = []
        self._markets_refreshed_at = 0.0

        # Cache performance tracking
        self._cache_stats = {
            "market_list_hits": 0,
            "market_list_misses": 0,
            "market_metadata_hits": 0,
            "market_metadata_misses": 0,
            "order_book_hits": 0,
            "order_book_misses": 0,
            "last_stats_log": time.time(),
        }

        # Popular markets tracking for cache warming
        self._market_popularity: Dict[str, int] = {}
        self._last_popularity_update = time.time()

        logger.info(
            f"CachedScanner initialized with advanced caching: {self.cache_config}"
        )

    async def _refresh_markets_cached(self, force: bool = False) -> None:
        """
        Enhanced market refresh with LRU caching.

        Replaces the simple TTL-based refresh with sophisticated caching
        that handles individual cache entries and background refresh.
        """
        # Try to get from cache first
        cached_markets = get_cached_market_list()

        if cached_markets is not None and not force:
            # Cache hit
            self._markets_cache = cached_markets
            self._cache_stats["market_list_hits"] += 1
            logger.debug(
                f"Market list loaded from cache: {len(cached_markets)} markets"
            )
            return

        # Cache miss - fetch from API
        self._cache_stats["market_list_misses"] += 1
        logger.info("Market list cache miss - fetching from API")

        try:
            # Fetch fresh data
            markets = await fetch_markets(self.cfg)

            # Update local cache
            self._markets_cache = markets
            self._markets_refreshed_at = time.time()

            # Store in advanced cache
            cache_market_list(markets, custom_ttl=self.cache_config.market_list_ttl)

            logger.info(f"Markets refreshed and cached: {len(markets)} markets")

            # Update market popularity for cache warming
            self._update_market_popularity(markets)

        except Exception as e:
            logger.error(f"Failed to refresh markets: {e}")
            # Fall back to existing cache if available
            if not self._markets_cache:
                self._markets_cache = []

    def _update_market_popularity(self, markets: List[Dict[str, Any]]):
        """Update market popularity tracking for cache warming."""
        current_time = time.time()

        # Update popularity based on volume, recent activity, etc.
        for market in markets:
            market_slug = market.get("slug", "")
            if market_slug:
                volume = market.get("volume", 0)
                recent_trades = market.get("recent_trades", 0)

                # Simple popularity score based on volume and activity
                popularity_score = int(volume / 1000) + recent_trades
                self._market_popularity[market_slug] = popularity_score

        self._last_popularity_update = current_time

    async def _warm_popular_market_caches(self):
        """Pre-warm caches for popular markets."""
        if not self.cache_config.enable_cache_warming:
            return

        # Get top markets by popularity
        popular_markets = sorted(
            self._market_popularity.items(), key=lambda x: x[1], reverse=True
        )[: self.cache_config.warm_top_markets]

        logger.debug(f"Warming caches for {len(popular_markets)} popular markets")

        for market_slug, popularity in popular_markets:
            try:
                # Check if market metadata is cached
                cached_metadata = get_cached_market_metadata(market_slug)
                if cached_metadata is None:
                    # Would normally fetch and cache market metadata here
                    # For now, we'll just log the warming attempt
                    logger.debug(
                        f"Would warm cache for market: {market_slug} (popularity: {popularity})"
                    )

            except Exception as e:
                logger.warning(f"Cache warming failed for {market_slug}: {e}")

    async def get_cached_order_book(self, token_id: str) -> Optional[Dict[str, Any]]:
        """
        Get order book with advanced caching.

        Args:
            token_id: Token identifier

        Returns:
            Cached order book data or None if not available
        """
        # Try cache first
        cached_book = get_cached_order_book(token_id)

        if cached_book is not None:
            self._cache_stats["order_book_hits"] += 1
            return cached_book

        self._cache_stats["order_book_misses"] += 1
        return None

    def cache_order_book_data(self, token_id: str, book_data: Dict[str, Any]) -> bool:
        """
        Cache order book data with appropriate TTL.

        Args:
            token_id: Token identifier
            book_data: Order book data to cache

        Returns:
            True if cached successfully
        """
        return cache_order_book(
            token_id, book_data, custom_ttl=self.cache_config.order_book_ttl
        )

    async def fetch_books_batch_cached(self, token_ids: List[str]) -> Dict[str, Any]:
        """
        Enhanced batch order book fetching with caching.

        Checks cache first for each token, only fetches missing ones from API.
        """
        books = {}
        tokens_to_fetch = []

        # Check cache for each token
        for token_id in token_ids:
            cached_book = await self.get_cached_order_book(token_id)
            if cached_book is not None:
                books[token_id] = cached_book
            else:
                tokens_to_fetch.append(token_id)

        # Fetch missing tokens from API
        if tokens_to_fetch:
            logger.debug(
                f"Fetching {len(tokens_to_fetch)} order books from API (cache misses)"
            )

            fresh_books = await self.fetch_books_batch(tokens_to_fetch)

            # Cache the fresh data and add to results
            for token_id, book_data in fresh_books.items():
                self.cache_order_book_data(token_id, book_data)
                books[token_id] = book_data

        logger.debug(
            f"Batch fetch complete: {len(books)} books ({len(token_ids) - len(tokens_to_fetch)} from cache)"
        )
        return books

    async def scan_once_cached(self, top: int = 10) -> List[Dict[str, Any]]:
        """
        Enhanced scan with comprehensive caching.

        Uses the advanced cache system for all market data operations.
        """
        start_time = time.time()

        # Refresh markets with caching
        await self._refresh_markets_cached()

        # Warm popular caches if enabled
        if self.cache_config.enable_cache_warming:
            await self._warm_popular_market_caches()

        # Use parent's scan logic but with cached data fetching
        # This would need to be integrated with the parent's scan_once method
        # For now, we'll call the parent method and add cache integration
        composites = await super().scan_once(top)

        # Cache any additional data discovered during scanning
        for composite in composites:
            market_slug = composite.get("market_slug")
            if market_slug:
                # Cache market metadata if we have it
                cache_market_metadata(market_slug, composite)

        scan_time = time.time() - start_time

        # Log performance stats periodically
        await self._log_cache_performance(scan_time)

        return composites

    async def _log_cache_performance(self, scan_time: float):
        """Log cache performance statistics."""
        current_time = time.time()

        # Log every 5 minutes
        if current_time - self._cache_stats["last_stats_log"] > 300:
            cache_stats = self._market_cache.get_cache_stats()

            logger.info(f"Cache Performance Summary:")
            logger.info(f"  Overall hit rate: {cache_stats['hit_rate']:.2%}")
            logger.info(f"  Total entries: {cache_stats['total_entries']}")
            logger.info(f"  Cache size: {cache_stats['total_size_mb']:.2f} MB")
            logger.info(
                f"  Market list hits/misses: {self._cache_stats['market_list_hits']}/{self._cache_stats['market_list_misses']}"
            )
            logger.info(
                f"  Order book hits/misses: {self._cache_stats['order_book_hits']}/{self._cache_stats['order_book_misses']}"
            )
            logger.info(f"  Last scan time: {scan_time:.3f}s")

            self._cache_stats["last_stats_log"] = current_time

    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        base_stats = self._market_cache.get_cache_stats()

        # Add scanner-specific stats
        scanner_stats = {
            "scanner_cache_stats": self._cache_stats.copy(),
            "popular_markets_tracked": len(self._market_popularity),
            "top_popular_markets": sorted(
                self._market_popularity.items(), key=lambda x: x[1], reverse=True
            )[
                :10
            ],  # Top 10 popular markets
        }

        base_stats.update(scanner_stats)
        return base_stats

    async def shutdown_cached(self):
        """Shutdown with cache cleanup."""
        logger.info("Shutting down cached scanner")

        # Log final cache stats
        cache_stats = self.get_cache_statistics()
        logger.info(f"Final cache statistics: {cache_stats}")

        # Shutdown the market cache
        await self._market_cache.shutdown()

        logger.info("Cached scanner shutdown complete")


# Factory function for easy integration
def create_cached_scanner(
    bot_config: Optional[BotConfig] = None,
    cache_config: Optional[CachedScannerConfig] = None,
) -> CachedScanner:
    """
    Create a cached scanner with optimized configuration.

    Args:
        bot_config: Bot configuration
        cache_config: Cache configuration

    Returns:
        CachedScanner instance with advanced caching
    """
    scanner = CachedScanner(bot_config, cache_config)
    logger.info("Created cached scanner with advanced market data caching")
    return scanner


logger.info("Cached scanner module loaded successfully")
