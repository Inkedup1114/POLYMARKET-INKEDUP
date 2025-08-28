#!/usr/bin/env python3
"""
Intelligent Caching System for InkedUp Bot

This module provides a comprehensive caching framework with:
- TTL-based cache expiration
- Smart cache invalidation strategies
- LRU eviction policies
- Cache hit/miss analytics
- Configurable cache tiers
- Background refresh mechanisms
- Cache warming strategies
"""

import asyncio
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any

logger = logging.getLogger("cache")

# Import analytics for performance monitoring
_analytics_available = False
try:
    from .cache_analytics import get_cache_analytics

    _analytics_available = True
except ImportError:
    logger.debug("Cache analytics not available - monitoring disabled")


class CacheStrategy(str, Enum):
    """Cache strategies for different data types."""

    LRU = "lru"  # Least Recently Used
    TTL = "ttl"  # Time To Live
    WRITE_THROUGH = "write_through"  # Write to cache and storage
    WRITE_BEHIND = "write_behind"  # Write to cache first, storage async
    REFRESH_AHEAD = "refresh_ahead"  # Proactive refresh before expiry


class CacheEvent(str, Enum):
    """Cache events for monitoring and invalidation."""

    HIT = "hit"
    MISS = "miss"
    SET = "set"
    DELETE = "delete"
    EXPIRE = "expire"
    EVICT = "evict"
    REFRESH = "refresh"
    INVALIDATE = "invalidate"


@dataclass
class CacheEntry:
    """Individual cache entry with metadata."""

    key: str
    value: Any
    created_at: float
    accessed_at: float
    ttl: float | None = None
    hit_count: int = 0
    tags: set[str] = field(default_factory=set)

    @property
    def age(self) -> float:
        """Age of the cache entry in seconds."""
        return time.time() - self.created_at

    @property
    def time_since_access(self) -> float:
        """Time since last access in seconds."""
        return time.time() - self.accessed_at

    @property
    def is_expired(self) -> bool:
        """Check if entry has expired based on TTL."""
        if self.ttl is None:
            return False
        return time.time() - self.created_at > self.ttl

    def touch(self):
        """Update access time and increment hit count."""
        self.accessed_at = time.time()
        self.hit_count += 1


@dataclass
class CacheConfig:
    """Configuration for cache behavior."""

    # Basic configuration
    max_size: int = 1000
    default_ttl: float | None = 300.0  # 5 minutes
    strategy: CacheStrategy = CacheStrategy.LRU

    # Advanced features
    enable_analytics: bool = True
    enable_background_refresh: bool = True
    refresh_threshold: float = 0.8  # Refresh when 80% of TTL has elapsed
    max_refresh_workers: int = 5

    # Eviction settings
    eviction_batch_size: int = 10
    memory_threshold_mb: float = 100.0

    # Persistence settings
    enable_persistence: bool = False
    persistence_file: str | None = None

    # Monitoring
    log_cache_operations: bool = False
    metrics_collection_interval: float = 60.0


@dataclass
class CacheMetrics:
    """Cache performance metrics."""

    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0
    refreshes: int = 0

    # Memory metrics
    current_size: int = 0
    max_size_reached: int = 0
    memory_usage_mb: float = 0.0

    # Performance metrics
    avg_access_time_ms: float = 0.0
    hit_ratio: float = 0.0

    # Timing
    start_time: float = field(default_factory=time.time)
    last_reset: float = field(default_factory=time.time)

    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    def miss_rate(self) -> float:
        """Calculate cache miss rate."""
        total = self.hits + self.misses
        return (self.misses / total * 100) if total > 0 else 0.0

    def operations_per_second(self) -> float:
        """Calculate operations per second."""
        elapsed = time.time() - self.start_time
        total_ops = self.hits + self.misses + self.sets + self.deletes
        return total_ops / elapsed if elapsed > 0 else 0.0

    def reset(self):
        """Reset metrics counters."""
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.evictions = 0
        self.refreshes = 0
        self.last_reset = time.time()


class IntelligentCache:
    """
    Intelligent caching system with advanced features.

    Features:
    - Multiple eviction strategies (LRU, TTL-based)
    - Tag-based invalidation
    - Background refresh
    - Performance analytics
    - Memory management
    - Cache warming
    """

    def __init__(self, name: str, config: CacheConfig = None):
        self.name = name
        self.config = config or CacheConfig()

        # Core storage
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()

        # Metrics and analytics
        self.metrics = CacheMetrics()

        # Background tasks
        self._refresh_workers: list[asyncio.Task] = []
        self._cleanup_task: asyncio.Task | None = None
        self._metrics_task: asyncio.Task | None = None

        # Event handlers
        self._event_handlers: dict[CacheEvent, list[Callable]] = {
            event: [] for event in CacheEvent
        }

        # Refresh callbacks
        self._refresh_callbacks: dict[str, Callable] = {}

        # Tag mappings for invalidation
        self._tag_to_keys: dict[str, set[str]] = {}

        # Start background tasks
        if self.config.enable_background_refresh:
            self._start_background_tasks()

        logger.info(f"Initialized cache '{name}' with config: {self.config}")

    def _start_background_tasks(self):
        """Start background maintenance tasks."""
        try:
            loop = asyncio.get_event_loop()

            # Cleanup task
            self._cleanup_task = loop.create_task(self._cleanup_loop())

            # Metrics collection task
            if self.config.enable_analytics:
                self._metrics_task = loop.create_task(self._metrics_loop())

        except RuntimeError:
            # No event loop running, tasks will be started when needed
            pass

    async def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from cache.

        Args:
            key: Cache key
            default: Default value if key not found

        Returns:
            Cached value or default
        """
        start_time = time.time()

        with self._lock:
            if key in self._cache:
                entry = self._cache[key]

                # Check if expired
                if entry.is_expired:
                    self._remove_entry(key, CacheEvent.EXPIRE)
                    self.metrics.misses += 1
                    self._emit_event(CacheEvent.MISS, key)

                    # Record analytics event for expired entry
                    if _analytics_available:
                        try:
                            analytics = get_cache_analytics()
                            access_time = (time.time() - start_time) * 1000
                            analytics.record_cache_miss(self.name, key, access_time)
                        except Exception as e:
                            logger.debug(
                                f"Failed to record expired cache analytics: {e}"
                            )

                    return default

                # Update access info and move to end (LRU)
                entry.touch()
                self._cache.move_to_end(key)

                self.metrics.hits += 1
                self._emit_event(CacheEvent.HIT, key)

                # Update access time metrics
                access_time = (time.time() - start_time) * 1000
                self._update_access_time(access_time)

                # Record analytics event
                if _analytics_available:
                    try:
                        analytics = get_cache_analytics()
                        data_size = len(str(entry.value)) if entry.value else 0
                        analytics.record_cache_hit(
                            self.name, key, access_time, data_size
                        )
                    except Exception as e:
                        logger.debug(f"Failed to record cache hit analytics: {e}")

                # Check if refresh is needed
                if self._needs_refresh(entry):
                    asyncio.create_task(self._refresh_entry(key))

                return entry.value

            else:
                self.metrics.misses += 1
                self._emit_event(CacheEvent.MISS, key)

                # Record analytics event
                if _analytics_available:
                    try:
                        analytics = get_cache_analytics()
                        access_time = (time.time() - start_time) * 1000
                        analytics.record_cache_miss(self.name, key, access_time)
                    except Exception as e:
                        logger.debug(f"Failed to record cache miss analytics: {e}")

                return default

    async def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
        tags: set[str] | None = None,
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            tags: Tags for invalidation

        Returns:
            True if set successfully
        """
        if ttl is None:
            ttl = self.config.default_ttl

        tags = tags or set()

        with self._lock:
            # Check if we need to evict entries
            if len(self._cache) >= self.config.max_size:
                self._evict_entries()

            # Create new entry
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=time.time(),
                accessed_at=time.time(),
                ttl=ttl,
                tags=tags,
            )

            # Remove old entry if exists
            if key in self._cache:
                self._remove_entry(key)

            # Add new entry
            self._cache[key] = entry

            # Update tag mappings
            for tag in tags:
                if tag not in self._tag_to_keys:
                    self._tag_to_keys[tag] = set()
                self._tag_to_keys[tag].add(key)

            self.metrics.sets += 1
            self.metrics.current_size = len(self._cache)

            if self.config.log_cache_operations:
                logger.debug(f"Cache SET: {key} (ttl={ttl}, tags={tags})")

            self._emit_event(CacheEvent.SET, key, value)

            return True

    async def delete(self, key: str) -> bool:
        """
        Delete entry from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key existed and was deleted
        """
        with self._lock:
            if key in self._cache:
                self._remove_entry(key, CacheEvent.DELETE)
                self.metrics.deletes += 1

                if self.config.log_cache_operations:
                    logger.debug(f"Cache DELETE: {key}")

                return True

            return False

    async def invalidate_by_tag(self, tag: str) -> int:
        """
        Invalidate all cache entries with a specific tag.

        Args:
            tag: Tag to invalidate

        Returns:
            Number of entries invalidated
        """
        with self._lock:
            if tag not in self._tag_to_keys:
                return 0

            keys_to_remove = list(self._tag_to_keys[tag])
            count = 0

            for key in keys_to_remove:
                if key in self._cache:
                    self._remove_entry(key, CacheEvent.INVALIDATE)
                    count += 1

            # Clean up tag mapping
            del self._tag_to_keys[tag]

            logger.info(f"Invalidated {count} cache entries with tag '{tag}'")
            return count

    async def invalidate_by_pattern(self, pattern: str) -> int:
        """
        Invalidate cache entries matching a pattern.

        Args:
            pattern: Pattern to match (supports wildcards)

        Returns:
            Number of entries invalidated
        """
        import fnmatch

        with self._lock:
            keys_to_remove = [
                key for key in self._cache.keys() if fnmatch.fnmatch(key, pattern)
            ]

            count = 0
            for key in keys_to_remove:
                self._remove_entry(key, CacheEvent.INVALIDATE)
                count += 1

            logger.info(
                f"Invalidated {count} cache entries matching pattern '{pattern}'"
            )
            return count

    async def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._tag_to_keys.clear()
            self.metrics.current_size = 0

            logger.info(f"Cleared cache '{self.name}': {count} entries removed")
            return count

    def register_refresh_callback(self, key_pattern: str, callback: Callable):
        """
        Register a callback for refreshing cache entries.

        Args:
            key_pattern: Pattern to match cache keys
            callback: Async function to refresh the value
        """
        self._refresh_callbacks[key_pattern] = callback
        logger.debug(f"Registered refresh callback for pattern '{key_pattern}'")

    def add_event_handler(self, event: CacheEvent, handler: Callable):
        """
        Add event handler for cache events.

        Args:
            event: Cache event to listen for
            handler: Function to call on event
        """
        self._event_handlers[event].append(handler)

    async def warm_cache(self, keys_and_loaders: dict[str, Callable]) -> int:
        """
        Warm the cache with predefined key-value pairs.

        Args:
            keys_and_loaders: Dict mapping cache keys to loader functions

        Returns:
            Number of entries warmed
        """
        count = 0

        for key, loader in keys_and_loaders.items():
            try:
                if callable(loader):
                    if asyncio.iscoroutinefunction(loader):
                        value = await loader()
                    else:
                        value = loader()
                else:
                    value = loader

                await self.set(key, value)
                count += 1

            except Exception as e:
                logger.error(f"Failed to warm cache for key '{key}': {e}")

        logger.info(f"Warmed cache '{self.name}' with {count} entries")
        return count

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive cache statistics."""
        with self._lock:
            # Calculate additional metrics
            total_requests = self.metrics.hits + self.metrics.misses
            hit_rate = (
                (self.metrics.hits / total_requests * 100) if total_requests > 0 else 0
            )

            # Memory usage estimation
            estimated_memory = (
                sum(
                    len(str(entry.key)) + len(str(entry.value)) + 200  # Rough estimate
                    for entry in self._cache.values()
                )
                / 1024
                / 1024
            )  # Convert to MB

            # Age statistics
            ages = [entry.age for entry in self._cache.values()]
            avg_age = sum(ages) / len(ages) if ages else 0

            return {
                "name": self.name,
                "size": len(self._cache),
                "max_size": self.config.max_size,
                "hit_rate_percent": hit_rate,
                "total_requests": total_requests,
                "hits": self.metrics.hits,
                "misses": self.metrics.misses,
                "sets": self.metrics.sets,
                "deletes": self.metrics.deletes,
                "evictions": self.metrics.evictions,
                "refreshes": self.metrics.refreshes,
                "estimated_memory_mb": estimated_memory,
                "average_age_seconds": avg_age,
                "operations_per_second": self.metrics.operations_per_second(),
                "config": {
                    "strategy": self.config.strategy.value,
                    "default_ttl": self.config.default_ttl,
                    "max_size": self.config.max_size,
                },
                "uptime_seconds": time.time() - self.metrics.start_time,
            }

    def _needs_refresh(self, entry: CacheEntry) -> bool:
        """Check if entry needs background refresh."""
        if not self.config.enable_background_refresh or entry.ttl is None:
            return False

        elapsed = time.time() - entry.created_at
        refresh_time = entry.ttl * self.config.refresh_threshold

        return elapsed >= refresh_time

    async def _refresh_entry(self, key: str):
        """Refresh a cache entry in the background."""
        if key not in self._cache:
            return

        # Find matching refresh callback
        callback = None
        for pattern, cb in self._refresh_callbacks.items():
            import fnmatch

            if fnmatch.fnmatch(key, pattern):
                callback = cb
                break

        if callback is None:
            return

        try:
            if asyncio.iscoroutinefunction(callback):
                new_value = await callback(key)
            else:
                new_value = callback(key)

            # Update cache entry with new value
            with self._lock:
                if key in self._cache:
                    entry = self._cache[key]
                    entry.value = new_value
                    entry.created_at = time.time()  # Reset TTL

                    self.metrics.refreshes += 1
                    self._emit_event(CacheEvent.REFRESH, key, new_value)

                    if self.config.log_cache_operations:
                        logger.debug(f"Cache REFRESH: {key}")

        except Exception as e:
            logger.error(f"Failed to refresh cache entry '{key}': {e}")

    def _evict_entries(self):
        """Evict entries based on configured strategy."""
        batch_size = self.config.eviction_batch_size
        evicted = 0

        if self.config.strategy == CacheStrategy.LRU:
            # Remove least recently used entries
            keys_to_evict = list(self._cache.keys())[:batch_size]

        elif self.config.strategy == CacheStrategy.TTL:
            # Remove expired entries first, then oldest
            expired_keys = [
                key for key, entry in self._cache.items() if entry.is_expired
            ]

            if len(expired_keys) >= batch_size:
                keys_to_evict = expired_keys[:batch_size]
            else:
                # Add oldest entries to reach batch size
                oldest_keys = sorted(
                    self._cache.keys(), key=lambda k: self._cache[k].created_at
                )
                keys_to_evict = (
                    expired_keys + oldest_keys[: batch_size - len(expired_keys)]
                )

        else:
            # Default to LRU
            keys_to_evict = list(self._cache.keys())[:batch_size]

        # Remove selected entries
        for key in keys_to_evict:
            if key in self._cache:
                self._remove_entry(key, CacheEvent.EVICT)
                evicted += 1

        self.metrics.evictions += evicted

        if evicted > 0:
            logger.debug(f"Evicted {evicted} cache entries")

    def _remove_entry(self, key: str, event: CacheEvent = CacheEvent.DELETE):
        """Remove entry and clean up tag mappings."""
        if key not in self._cache:
            return

        entry = self._cache[key]

        # Remove from tag mappings
        for tag in entry.tags:
            if tag in self._tag_to_keys:
                self._tag_to_keys[tag].discard(key)
                if not self._tag_to_keys[tag]:
                    del self._tag_to_keys[tag]

        # Remove from cache
        del self._cache[key]
        self.metrics.current_size = len(self._cache)

        self._emit_event(event, key, entry.value)

    def _emit_event(self, event: CacheEvent, key: str, value: Any = None):
        """Emit cache event to registered handlers."""
        for handler in self._event_handlers[event]:
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(event, key, value))
                else:
                    handler(event, key, value)
            except Exception as e:
                logger.error(f"Cache event handler error: {e}")

    def _update_access_time(self, access_time_ms: float):
        """Update average access time metric."""
        if self.metrics.avg_access_time_ms == 0:
            self.metrics.avg_access_time_ms = access_time_ms
        else:
            # Simple exponential moving average
            alpha = 0.1
            self.metrics.avg_access_time_ms = (
                alpha * access_time_ms + (1 - alpha) * self.metrics.avg_access_time_ms
            )

    async def _cleanup_loop(self):
        """Background task to clean up expired entries."""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute

                with self._lock:
                    expired_keys = [
                        key for key, entry in self._cache.items() if entry.is_expired
                    ]

                    for key in expired_keys:
                        self._remove_entry(key, CacheEvent.EXPIRE)

                    if expired_keys:
                        logger.debug(
                            f"Cleaned up {len(expired_keys)} expired cache entries"
                        )

            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")

    async def _metrics_loop(self):
        """Background task to collect and log metrics."""
        while True:
            try:
                await asyncio.sleep(self.config.metrics_collection_interval)

                stats = self.get_stats()
                logger.info(
                    f"Cache '{self.name}' stats: "
                    f"{stats['hit_rate_percent']:.1f}% hit rate, "
                    f"{stats['size']}/{stats['max_size']} entries, "
                    f"{stats['estimated_memory_mb']:.1f}MB"
                )

            except Exception as e:
                logger.error(f"Cache metrics error: {e}")

    async def shutdown(self):
        """Shutdown cache and cleanup background tasks."""
        logger.info(f"Shutting down cache '{self.name}'")

        # Cancel background tasks
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._metrics_task:
            self._metrics_task.cancel()

        for task in self._refresh_workers:
            task.cancel()

        # Clear cache
        await self.clear()


class CacheManager:
    """
    Global cache manager for managing multiple cache instances.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._caches: dict[str, IntelligentCache] = {}
        self._global_config = CacheConfig()
        self._initialized = True

        logger.info("Initialized global cache manager")

    def get_cache(
        self, name: str, config: CacheConfig | None = None
    ) -> IntelligentCache:
        """
        Get or create a named cache instance.

        Args:
            name: Cache name
            config: Cache configuration (uses global config if None)

        Returns:
            Cache instance
        """
        if name not in self._caches:
            cache_config = config or self._global_config
            self._caches[name] = IntelligentCache(name, cache_config)

        return self._caches[name]

    def list_caches(self) -> list[str]:
        """List all cache names."""
        return list(self._caches.keys())

    def get_global_stats(self) -> dict[str, Any]:
        """Get statistics for all caches."""
        return {name: cache.get_stats() for name, cache in self._caches.items()}

    async def shutdown_all(self):
        """Shutdown all caches."""
        logger.info("Shutting down all caches")

        for cache in self._caches.values():
            await cache.shutdown()

        self._caches.clear()


# Global cache manager instance
cache_manager = CacheManager()


def cached(
    cache_name: str = "default",
    ttl: float | None = None,
    tags: set[str] | None = None,
    key_generator: Callable | None = None,
):
    """
    Decorator for caching function results.

    Args:
        cache_name: Name of cache to use
        ttl: Time to live for cached result
        tags: Tags for cache invalidation
        key_generator: Function to generate cache key from args

    Example:
        @cached("api_responses", ttl=300, tags={"api"})
        async def fetch_data(market_id: str):
            # API call here
            pass
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache = cache_manager.get_cache(cache_name)

            # Generate cache key
            if key_generator:
                cache_key = key_generator(*args, **kwargs)
            else:
                # Default key generation
                key_parts = [func.__name__]
                key_parts.extend(str(arg) for arg in args)
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = ":".join(key_parts)

            # Try to get from cache
            result = await cache.get(cache_key)

            if result is None:
                # Cache miss - call function and cache result
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                await cache.set(cache_key, result, ttl=ttl, tags=tags)

            return result

        return wrapper

    return decorator
