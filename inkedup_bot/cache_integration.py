#!/usr/bin/env python3
"""
Cache Integration Layer for InkedUp Bot

This module integrates the intelligent caching system with existing bot components:
- Scanner caching integration
- Database query caching
- API response caching with the HTTPClient
- Configuration caching integration
- Cache invalidation coordination
"""

import asyncio
import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from .cache import CacheConfig, CacheStrategy, cache_manager
from .config import BotConfig
from .config_cache import get_config_cache
from .market_cache import get_market_cache
from .utils import HTTPClient

logger = logging.getLogger("cache_integration")


class CacheIntegrationManager:
    """
    Central manager for coordinating caching across all bot components.
    """

    def __init__(self, bot_config: BotConfig = None):
        self.bot_config = bot_config

        # Initialize cache systems
        self.market_cache = get_market_cache()
        self.config_cache = get_config_cache(bot_config)

        # Cache invalidation coordination
        self._invalidation_strategies: dict[str, list[Callable]] = {}
        self._cache_dependencies: dict[str, set[str]] = {}

        # Performance tracking
        self._cache_hits = 0
        self._cache_misses = 0
        self._start_time = time.time()

        logger.info("Initialized cache integration manager")

    def register_invalidation_strategy(self, cache_type: str, strategy: Callable):
        """
        Register an invalidation strategy for a cache type.

        Args:
            cache_type: Type of cache (e.g., 'market_data', 'api_responses')
            strategy: Callable that handles invalidation
        """
        if cache_type not in self._invalidation_strategies:
            self._invalidation_strategies[cache_type] = []

        self._invalidation_strategies[cache_type].append(strategy)
        logger.debug(f"Registered invalidation strategy for {cache_type}")

    def register_cache_dependency(self, primary_cache: str, dependent_caches: set[str]):
        """
        Register cache dependencies for coordinated invalidation.

        Args:
            primary_cache: Primary cache that others depend on
            dependent_caches: Caches that should be invalidated when primary changes
        """
        self._cache_dependencies[primary_cache] = dependent_caches
        logger.debug(f"Registered dependencies: {primary_cache} -> {dependent_caches}")

    async def invalidate_related_caches(self, cache_type: str, key_pattern: str = "*"):
        """
        Invalidate cache and all dependent caches.

        Args:
            cache_type: Primary cache type to invalidate
            key_pattern: Pattern of keys to invalidate
        """
        # Invalidate primary cache
        if cache_type in self._invalidation_strategies:
            for strategy in self._invalidation_strategies[cache_type]:
                try:
                    await strategy(key_pattern)
                except Exception as e:
                    logger.error(
                        f"Cache invalidation strategy failed for {cache_type}: {e}"
                    )

        # Invalidate dependent caches
        if cache_type in self._cache_dependencies:
            for dependent_cache in self._cache_dependencies[cache_type]:
                await self.invalidate_related_caches(dependent_cache, key_pattern)

        logger.info(f"Invalidated cache type '{cache_type}' and dependencies")

    async def warm_all_caches(self, market_loader: Callable | None = None):
        """
        Warm all caches with initial data.

        Args:
            market_loader: Function to load market data
        """
        logger.info("Warming all caches...")

        tasks = []

        # Warm configuration cache
        tasks.append(self.config_cache.warm_configuration_cache())

        # Warm market cache if loader provided
        if market_loader:
            tasks.append(self.market_cache.warm_popular_markets(market_loader))

        # Execute warming tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log results
        successful_tasks = len([r for r in results if not isinstance(r, Exception)])
        logger.info(
            f"Cache warming completed: {successful_tasks}/{len(tasks)} successful"
        )

    def get_global_cache_stats(self) -> dict[str, Any]:
        """Get comprehensive cache statistics across all systems."""
        uptime = time.time() - self._start_time
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (
            (self._cache_hits / total_requests * 100) if total_requests > 0 else 0
        )

        return {
            "integration_manager": {
                "uptime_seconds": uptime,
                "total_cache_hits": self._cache_hits,
                "total_cache_misses": self._cache_misses,
                "overall_hit_rate_percent": hit_rate,
                "registered_strategies": len(self._invalidation_strategies),
                "cache_dependencies": len(self._cache_dependencies),
            },
            "market_cache": self.market_cache.get_cache_stats(),
            "config_cache": self.config_cache.get_cache_stats(),
            "global_caches": cache_manager.get_global_stats(),
        }

    async def shutdown(self):
        """Shutdown all cache systems."""
        logger.info("Shutting down cache integration")

        await self.market_cache.shutdown()
        await self.config_cache.shutdown()
        await cache_manager.shutdown_all()


class CachedHTTPClient(HTTPClient):
    """
    HTTP Client with intelligent response caching.
    """

    def __init__(
        self,
        base_url: str,
        timeout: int = 12,
        rate_limiter=None,
        cache_config: CacheConfig = None,
    ):
        super().__init__(base_url, timeout, rate_limiter)

        # Initialize response cache
        cache_config = cache_config or CacheConfig(
            max_size=2000,
            default_ttl=300.0,  # 5 minutes
            strategy=CacheStrategy.LRU,
            enable_background_refresh=True,
        )
        self.response_cache = cache_manager.get_cache("http_responses", cache_config)

        # Cache configuration
        self.cache_enabled = True
        self.cache_get_requests = True
        self.cache_post_requests = False  # Usually don't cache POST requests

        # Response validation
        self._response_validators: dict[str, Callable] = {}

    def register_response_validator(self, path_pattern: str, validator: Callable):
        """
        Register a validator for response caching.

        Args:
            path_pattern: URL path pattern to match
            validator: Function that validates if response should be cached
        """
        self._response_validators[path_pattern] = validator

    def _should_cache_request(self, method: str, path: str) -> bool:
        """Determine if request should be cached."""
        if not self.cache_enabled:
            return False

        if method.upper() == "GET" and self.cache_get_requests:
            # Don't cache requests with authentication or sensitive data
            if any(
                sensitive in path.lower()
                for sensitive in ["auth", "login", "token", "key"]
            ):
                return False
            return True

        if method.upper() == "POST" and self.cache_post_requests:
            # Only cache idempotent POST requests
            if any(
                idempotent in path.lower()
                for idempotent in ["search", "query", "validate"]
            ):
                return True

        return False

    def _generate_cache_key(self, method: str, path: str, params: dict = None) -> str:
        """Generate cache key for HTTP request."""
        key_parts = [method.upper(), path]

        if params:
            # Sort params for consistent key generation
            param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            key_parts.append(param_str)

        return ":".join(key_parts)

    def _determine_ttl(self, path: str, response_data: Any) -> float:
        """Determine TTL based on path and response characteristics."""
        path_lower = path.lower()

        # Static data - longer TTL
        if any(keyword in path_lower for keyword in ["/markets", "/tokens", "/info"]):
            return 1800.0  # 30 minutes

        # Dynamic data - shorter TTL
        if any(keyword in path_lower for keyword in ["/books", "/trades", "/prices"]):
            return 30.0  # 30 seconds

        # Default TTL
        return 300.0  # 5 minutes

    def _validate_response_for_caching(self, path: str, response_data: Any) -> bool:
        """Validate if response should be cached."""
        # Check registered validators
        for pattern, validator in self._response_validators.items():
            import fnmatch

            if fnmatch.fnmatch(path, pattern):
                try:
                    return validator(response_data)
                except Exception as e:
                    logger.error(f"Response validator error for {path}: {e}")
                    return False

        # Default validation
        if isinstance(response_data, dict):
            # Don't cache error responses
            if response_data.get("error") or response_data.get("status") == "error":
                return False

            # Don't cache empty responses
            if not response_data:
                return False

        return True

    async def get(self, path: str, params: dict = None) -> Any:
        """Enhanced GET with response caching."""
        # Check cache first if caching is enabled
        if self._should_cache_request("GET", path):
            cache_key = self._generate_cache_key("GET", path, params)
            cached_response = await self.response_cache.get(cache_key)

            if cached_response is not None:
                logger.debug(f"Cache HIT: GET {path}")
                return cached_response

            logger.debug(f"Cache MISS: GET {path}")

        # Call parent method to get response
        response = await super().get(path, params)

        # Cache the response if appropriate
        if (
            self._should_cache_request("GET", path)
            and response is not None
            and self._validate_response_for_caching(path, response)
        ):
            cache_key = self._generate_cache_key("GET", path, params)
            ttl = self._determine_ttl(path, response)

            # Determine tags
            tags = {"http_response", "get_request"}
            if "market" in path.lower():
                tags.add("market_data")
            if "book" in path.lower():
                tags.add("order_book")

            await self.response_cache.set(cache_key, response, ttl=ttl, tags=tags)
            logger.debug(f"Cached GET response: {path} (TTL: {ttl}s)")

        return response

    async def invalidate_cache(self, path_pattern: str = "*"):
        """Invalidate cached responses by path pattern."""
        pattern = f"GET:{path_pattern}*"
        invalidated = await self.response_cache.invalidate_by_pattern(pattern)
        logger.info(
            f"Invalidated {invalidated} cached HTTP responses matching {path_pattern}"
        )
        return invalidated


def integrate_scanner_caching(scanner_instance, cache_manager: CacheIntegrationManager):
    """
    Integrate caching with the scanner instance.

    Args:
        scanner_instance: Scanner instance to enhance with caching
        cache_manager: Cache integration manager
    """
    # Replace scanner's HTTPClient with cached version
    if hasattr(scanner_instance, "client"):
        original_client = scanner_instance.client

        # Create cached HTTP client with same configuration
        cached_client = CachedHTTPClient(
            base_url=str(original_client.base_url),
            timeout=original_client.timeout,
            rate_limiter=getattr(original_client, "rate_limiter", None),
        )

        # Register response validators for scanner endpoints
        cached_client.register_response_validator(
            "/markets*",
            lambda response: isinstance(response, (list, dict)) and bool(response),
        )

        cached_client.register_response_validator(
            "/books*",
            lambda response: isinstance(response, dict)
            and "bids" in response
            or "asks" in response,
        )

        scanner_instance.client = cached_client
        logger.info("Integrated scanner with cached HTTP client")

    # Enhance market data fetching
    if hasattr(scanner_instance, "ensure_markets"):
        original_ensure_markets = scanner_instance.ensure_markets

        async def cached_ensure_markets(force: bool = False):
            # Use market cache instead of internal cache
            if force or not await cache_manager.market_cache.get_market_info(
                "markets_list"
            ):
                # Call original method to fetch markets
                await original_ensure_markets(force=True)

                # Cache the markets data
                if (
                    hasattr(scanner_instance, "_markets_cache")
                    and scanner_instance._markets_cache
                ):
                    await cache_manager.market_cache.set_market_info(
                        "markets_list", scanner_instance._markets_cache
                    )

                    # Cache individual market info
                    for market in scanner_instance._markets_cache:
                        market_id = market.get("id") or market.get("market_id")
                        if market_id:
                            await cache_manager.market_cache.set_market_info(
                                market_id, market
                            )
            else:
                # Load from cache
                cached_markets = await cache_manager.market_cache.get_market_info(
                    "markets_list"
                )
                if cached_markets:
                    scanner_instance._markets_cache = cached_markets
                    scanner_instance._markets_refreshed_at = time.time()

        scanner_instance.ensure_markets = cached_ensure_markets
        logger.info("Enhanced scanner market fetching with caching")


def cache_database_queries(db_manager_instance, cache_config: CacheConfig = None):
    """
    Add caching to database query methods.

    Args:
        db_manager_instance: Database manager instance
        cache_config: Configuration for database query cache
    """
    cache_config = cache_config or CacheConfig(
        max_size=1000,
        default_ttl=300.0,
        strategy=CacheStrategy.LRU,  # 5 minutes
    )

    db_cache = cache_manager.get_cache("database_queries", cache_config)

    # Cache common read operations
    if hasattr(db_manager_instance, "get_market_snapshots"):
        original_get_snapshots = db_manager_instance.get_market_snapshots

        async def cached_get_snapshots(market_id: str, limit: int = 100):
            cache_key = f"snapshots:{market_id}:{limit}"

            cached_result = await db_cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            result = await original_get_snapshots(market_id, limit)

            if result:
                await db_cache.set(
                    cache_key, result, ttl=300.0, tags={"database", "snapshots"}
                )

            return result

        db_manager_instance.get_market_snapshots = cached_get_snapshots

    # Cache position queries
    if hasattr(db_manager_instance, "get_positions"):
        original_get_positions = db_manager_instance.get_positions

        async def cached_get_positions():
            cache_key = "positions:all"

            cached_result = await db_cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            result = await original_get_positions()

            if result:
                await db_cache.set(
                    cache_key, result, ttl=60.0, tags={"database", "positions"}
                )

            return result

        db_manager_instance.get_positions = cached_get_positions

    logger.info("Integrated database manager with query caching")


# Global cache integration manager
_integration_manager = None


def get_cache_integration_manager(
    bot_config: BotConfig = None,
) -> CacheIntegrationManager:
    """Get global cache integration manager."""
    global _integration_manager

    if _integration_manager is None:
        _integration_manager = CacheIntegrationManager(bot_config)

    return _integration_manager


# Decorator for automatic cache integration
def auto_cache_integration(cache_type: str = "default", ttl: float = 300.0):
    """
    Decorator that automatically integrates caching for any function.

    Args:
        cache_type: Type of cache to use
        ttl: Time to live for cached results

    Example:
        @auto_cache_integration("market_data", ttl=600.0)
        async def fetch_market_info(market_id: str):
            # API call here
            pass
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{func.__name__}:{':'.join(str(arg) for arg in args)}"
            if kwargs:
                cache_key += (
                    f":{'&'.join(f'{k}={v}' for k, v in sorted(kwargs.items()))}"
                )

            # Get appropriate cache
            cache = cache_manager.get_cache(cache_type)

            # Try cache first
            result = await cache.get(cache_key)

            if result is None:
                # Cache miss - call function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Cache the result
                if result is not None:
                    tags = {cache_type, func.__name__}
                    await cache.set(cache_key, result, ttl=ttl, tags=tags)

            return result

        return wrapper

    return decorator


# Example integration functions for common components
async def setup_complete_caching_integration(
    scanner=None, db_manager=None, bot_config: BotConfig = None
):
    """
    Set up complete caching integration for all bot components.

    Args:
        scanner: Scanner instance to integrate
        db_manager: Database manager instance to integrate
        bot_config: Bot configuration
    """
    logger.info("Setting up complete caching integration...")

    # Initialize cache integration manager
    integration_manager = get_cache_integration_manager(bot_config)

    # Register common invalidation strategies
    integration_manager.register_invalidation_strategy(
        "market_data",
        lambda pattern: integration_manager.market_cache.invalidate_market_data(
            pattern.replace("*", "")
        ),
    )

    integration_manager.register_invalidation_strategy(
        "api_responses",
        lambda pattern: integration_manager.config_cache.invalidate_api_cache(pattern),
    )

    # Register cache dependencies
    integration_manager.register_cache_dependency(
        "market_data", {"api_responses", "database_queries"}
    )

    # Integrate with scanner if provided
    if scanner:
        integrate_scanner_caching(scanner, integration_manager)

    # Integrate with database manager if provided
    if db_manager:
        cache_database_queries(db_manager)

    # Warm caches
    if scanner and hasattr(scanner, "_markets_cache"):
        await integration_manager.warm_all_caches(lambda: scanner._markets_cache or [])
    else:
        await integration_manager.warm_all_caches()

    logger.info("Complete caching integration setup finished")

    return integration_manager
