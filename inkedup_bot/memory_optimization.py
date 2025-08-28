"""
Memory optimization system for the Polymarket trading bot.

This module provides comprehensive memory management including:
- Object pooling for frequently created/destroyed objects
- LRU cache optimization with automatic eviction
- Data compression for stored objects
- Memory monitoring and cleanup
- Performance tracking and analytics
"""

import gc
import logging
import pickle
import threading
import time
import zlib
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Optional, TypeVar, Union
from weakref import WeakSet

logger = logging.getLogger("memory_optimization")

T = TypeVar("T")


@dataclass
class MemoryStats:
    """Memory usage statistics."""

    total_objects_created: int = 0
    total_objects_reused: int = 0
    pool_hit_rate: float = 0.0
    cache_hit_rate: float = 0.0
    compressed_objects: int = 0
    compression_ratio: float = 0.0
    memory_freed_bytes: int = 0
    gc_collections: int = 0
    last_cleanup_time: float = 0.0


@dataclass
class ObjectPoolConfig:
    """Configuration for object pooling."""

    max_pool_size: int = 100
    max_idle_time: float = 300.0  # 5 minutes
    enable_stats: bool = True
    cleanup_interval: float = 60.0  # 1 minute
    prealloc_count: int = 10


class ObjectPool(Generic[T]):
    """
    Generic object pool for memory optimization.

    Maintains a pool of reusable objects to reduce allocation overhead.
    """

    def __init__(
        self,
        factory: Callable[[], T],
        reset_func: Optional[Callable[[T], None]] = None,
        config: Optional[ObjectPoolConfig] = None,
    ):
        self.factory = factory
        self.reset_func = reset_func or (lambda x: None)
        self.config = config or ObjectPoolConfig()

        self._pool: deque[tuple[T, float]] = deque()  # (object, last_used_time)
        self._in_use: WeakSet[T] = WeakSet()
        self._lock = threading.Lock()

        # Statistics
        self._stats = {
            "objects_created": 0,
            "objects_reused": 0,
            "pool_hits": 0,
            "pool_misses": 0,
        }

        # Pre-allocate initial objects
        self._preallocate()

        logger.info(f"ObjectPool initialized with max_size={self.config.max_pool_size}")

    def _preallocate(self):
        """Pre-allocate initial objects."""
        for _ in range(min(self.config.prealloc_count, self.config.max_pool_size)):
            obj = self.factory()
            self._pool.append((obj, time.time()))

    def acquire(self) -> T:
        """Acquire an object from the pool."""
        current_time = time.time()

        with self._lock:
            # Try to get from pool
            while self._pool:
                obj, last_used = self._pool.popleft()

                # Check if object is too old
                if current_time - last_used > self.config.max_idle_time:
                    continue

                # Reset and return object
                try:
                    self.reset_func(obj)
                    self._in_use.add(obj)
                    self._stats["objects_reused"] += 1
                    self._stats["pool_hits"] += 1
                    return obj
                except Exception as e:
                    logger.warning(f"Failed to reset pooled object: {e}")
                    continue

            # No suitable object in pool, create new one
            try:
                obj = self.factory()
                self._in_use.add(obj)
                self._stats["objects_created"] += 1
                self._stats["pool_misses"] += 1
                return obj
            except Exception as e:
                logger.error(f"Failed to create new object: {e}")
                raise

    def release(self, obj: T):
        """Release an object back to the pool."""
        with self._lock:
            if obj in self._in_use:
                self._in_use.discard(obj)

            # Add to pool if there's space
            if len(self._pool) < self.config.max_pool_size:
                self._pool.append((obj, time.time()))

    def cleanup(self):
        """Clean up old objects from pool."""
        current_time = time.time()
        cleaned = 0

        with self._lock:
            # Remove old objects
            new_pool = deque()
            while self._pool:
                obj, last_used = self._pool.popleft()
                if current_time - last_used <= self.config.max_idle_time:
                    new_pool.append((obj, last_used))
                else:
                    cleaned += 1

            self._pool = new_pool

        if cleaned > 0:
            logger.debug(f"ObjectPool cleaned up {cleaned} old objects")

    def get_stats(self) -> dict:
        """Get pool statistics."""
        with self._lock:
            total_requests = self._stats["pool_hits"] + self._stats["pool_misses"]
            hit_rate = (
                self._stats["pool_hits"] / total_requests if total_requests > 0 else 0.0
            )

            return {
                "pool_size": len(self._pool),
                "in_use": len(self._in_use),
                "objects_created": self._stats["objects_created"],
                "objects_reused": self._stats["objects_reused"],
                "hit_rate": hit_rate,
                "total_requests": total_requests,
            }


class LRUCache(Generic[T]):
    """
    LRU cache with compression and memory optimization.

    Provides automatic eviction based on usage patterns and memory constraints.
    """

    def __init__(
        self,
        max_size: int = 1000,
        max_memory_mb: float = 50.0,
        enable_compression: bool = True,
        compression_threshold: int = 1024,
    ):
        self.max_size = max_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.enable_compression = enable_compression
        self.compression_threshold = compression_threshold

        self._cache: OrderedDict[str, tuple[T, bool, int]] = (
            OrderedDict()
        )  # key -> (value, compressed, size)
        self._lock = threading.Lock()
        self._current_memory = 0

        # Statistics
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "compressed_entries": 0,
            "compression_saved_bytes": 0,
        }

        logger.info(
            f"LRUCache initialized: max_size={max_size}, max_memory={max_memory_mb}MB"
        )

    def _compress_if_needed(self, value: T) -> tuple[Union[T, bytes], bool, int]:
        """Compress value if it exceeds threshold."""
        if not self.enable_compression:
            size = self._estimate_size(value)
            return value, False, size

        # Serialize to estimate size
        try:
            serialized = pickle.dumps(value)
            original_size = len(serialized)

            if original_size > self.compression_threshold:
                compressed = zlib.compress(serialized, level=6)
                compressed_size = len(compressed)

                if compressed_size < original_size * 0.8:  # Only compress if saves 20%+
                    self._stats["compression_saved_bytes"] += (
                        original_size - compressed_size
                    )
                    return compressed, True, compressed_size

            return value, False, original_size

        except Exception as e:
            logger.warning(f"Compression failed: {e}")
            size = self._estimate_size(value)
            return value, False, size

    def _decompress_if_needed(self, data: Union[T, bytes], compressed: bool) -> T:
        """Decompress data if it was compressed."""
        if not compressed:
            return data

        try:
            serialized = zlib.decompress(data)
            return pickle.loads(serialized)
        except Exception as e:
            logger.error(f"Decompression failed: {e}")
            raise

    def _estimate_size(self, obj: Any) -> int:
        """Estimate memory size of an object."""
        try:
            return len(pickle.dumps(obj))
        except:
            # Fallback estimation
            if isinstance(obj, (str, bytes)):
                return len(obj)
            elif isinstance(obj, (list, tuple)):
                return sum(self._estimate_size(item) for item in obj)
            elif isinstance(obj, dict):
                return sum(
                    self._estimate_size(k) + self._estimate_size(v)
                    for k, v in obj.items()
                )
            else:
                return 64  # Default estimate

    def _evict_if_needed(self):
        """Evict entries if cache exceeds limits."""
        # Evict by size first
        while len(self._cache) >= self.max_size and self._cache:
            key, (_, _, size) = self._cache.popitem(last=False)
            self._current_memory -= size
            self._stats["evictions"] += 1

        # Evict by memory second
        while self._current_memory > self.max_memory_bytes and self._cache:
            key, (_, _, size) = self._cache.popitem(last=False)
            self._current_memory -= size
            self._stats["evictions"] += 1

    def get(self, key: str) -> Optional[T]:
        """Get value from cache."""
        with self._lock:
            if key in self._cache:
                value, compressed, size = self._cache.pop(
                    key
                )  # Remove and re-insert for LRU
                self._cache[key] = (value, compressed, size)
                self._stats["hits"] += 1

                # Decompress if needed
                return self._decompress_if_needed(value, compressed)
            else:
                self._stats["misses"] += 1
                return None

    def put(self, key: str, value: T):
        """Put value in cache."""
        with self._lock:
            # Remove existing entry if present
            if key in self._cache:
                _, _, old_size = self._cache.pop(key)
                self._current_memory -= old_size

            # Compress and add new entry
            stored_value, compressed, size = self._compress_if_needed(value)
            self._cache[key] = (stored_value, compressed, size)
            self._current_memory += size

            if compressed:
                self._stats["compressed_entries"] += 1

            # Evict if needed
            self._evict_if_needed()

    def remove(self, key: str) -> bool:
        """Remove key from cache."""
        with self._lock:
            if key in self._cache:
                _, _, size = self._cache.pop(key)
                self._current_memory -= size
                return True
            return False

    def clear(self):
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._current_memory = 0

    def get_stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                self._stats["hits"] / total_requests if total_requests > 0 else 0.0
            )

            return {
                "size": len(self._cache),
                "memory_mb": self._current_memory / (1024 * 1024),
                "hit_rate": hit_rate,
                "evictions": self._stats["evictions"],
                "compressed_entries": self._stats["compressed_entries"],
                "compression_saved_mb": self._stats["compression_saved_bytes"]
                / (1024 * 1024),
            }


@dataclass
class MemoryOptimizationConfig:
    """Configuration for memory optimization system."""

    enable_object_pooling: bool = True
    enable_lru_caching: bool = True
    enable_compression: bool = True
    enable_periodic_cleanup: bool = True

    # Object pool settings
    max_pool_size: int = 100
    pool_cleanup_interval: float = 60.0

    # Cache settings
    max_cache_size: int = 1000
    max_cache_memory_mb: float = 50.0
    compression_threshold: int = 1024

    # Cleanup settings
    cleanup_interval: float = 300.0  # 5 minutes
    gc_threshold: float = 0.8  # Trigger GC when memory usage > 80%

    # Memory monitoring
    enable_memory_monitoring: bool = True
    memory_alert_threshold_mb: float = 100.0


class MemoryOptimizer:
    """
    Comprehensive memory optimization system.

    Coordinates object pooling, caching, compression, and cleanup.
    """

    def __init__(self, config: Optional[MemoryOptimizationConfig] = None):
        self.config = config or MemoryOptimizationConfig()

        # Object pools for common types
        self._pools: dict[str, ObjectPool] = {}

        # Global LRU cache
        self._cache: Optional[LRUCache] = None
        if self.config.enable_lru_caching:
            self._cache = LRUCache(
                max_size=self.config.max_cache_size,
                max_memory_mb=self.config.max_cache_memory_mb,
                enable_compression=self.config.enable_compression,
                compression_threshold=self.config.compression_threshold,
            )

        # Cleanup management
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_cleanup = threading.Event()

        # Statistics
        self._global_stats = MemoryStats()
        self._lock = threading.Lock()

        # Start cleanup thread
        if self.config.enable_periodic_cleanup:
            self._start_cleanup_thread()

        logger.info("MemoryOptimizer initialized with comprehensive optimization")

    def create_object_pool(
        self,
        name: str,
        factory: Callable[[], T],
        reset_func: Optional[Callable[[T], None]] = None,
    ) -> ObjectPool[T]:
        """Create a named object pool."""
        if name in self._pools:
            return self._pools[name]

        pool_config = ObjectPoolConfig(
            max_pool_size=self.config.max_pool_size,
            cleanup_interval=self.config.pool_cleanup_interval,
            enable_stats=True,
        )

        pool = ObjectPool(factory, reset_func, pool_config)
        self._pools[name] = pool

        logger.info(f"Created object pool '{name}'")
        return pool

    def get_cache(self) -> Optional[LRUCache]:
        """Get the global LRU cache."""
        return self._cache

    def cache_get(self, key: str) -> Any:
        """Get value from global cache."""
        if self._cache:
            return self._cache.get(key)
        return None

    def cache_put(self, key: str, value: Any):
        """Put value in global cache."""
        if self._cache:
            self._cache.put(key, value)

    def cache_remove(self, key: str) -> bool:
        """Remove key from global cache."""
        if self._cache:
            return self._cache.remove(key)
        return False

    def force_cleanup(self):
        """Force immediate memory cleanup."""
        logger.info("Starting forced memory cleanup")

        # Clean up all object pools
        for name, pool in self._pools.items():
            pool.cleanup()
            logger.debug(f"Cleaned pool '{name}'")

        # Force garbage collection
        collected = gc.collect()

        with self._lock:
            self._global_stats.gc_collections += 1
            self._global_stats.last_cleanup_time = time.time()

        logger.info(f"Memory cleanup completed, collected {collected} objects")
        return collected

    def _start_cleanup_thread(self):
        """Start background cleanup thread."""
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
        logger.info("Started background memory cleanup thread")

    def _cleanup_loop(self):
        """Background cleanup loop."""
        while not self._stop_cleanup.wait(self.config.cleanup_interval):
            try:
                self.force_cleanup()
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    def get_memory_stats(self) -> dict:
        """Get comprehensive memory statistics."""
        stats = {
            "global_stats": {
                "total_objects_created": self._global_stats.total_objects_created,
                "total_objects_reused": self._global_stats.total_objects_reused,
                "gc_collections": self._global_stats.gc_collections,
                "last_cleanup_time": self._global_stats.last_cleanup_time,
            },
            "object_pools": {},
            "cache_stats": {},
        }

        # Get pool stats
        for name, pool in self._pools.items():
            stats["object_pools"][name] = pool.get_stats()

        # Get cache stats
        if self._cache:
            stats["cache_stats"] = self._cache.get_stats()

        return stats

    def shutdown(self):
        """Shutdown memory optimizer."""
        logger.info("Shutting down memory optimizer")

        if self._cleanup_thread:
            self._stop_cleanup.set()
            self._cleanup_thread.join(timeout=5.0)

        # Final cleanup
        self.force_cleanup()

        # Clear cache
        if self._cache:
            self._cache.clear()

        logger.info("Memory optimizer shutdown complete")


# Global memory optimizer instance
_global_optimizer: Optional[MemoryOptimizer] = None
_optimizer_lock = threading.Lock()


def get_memory_optimizer(
    config: Optional[MemoryOptimizationConfig] = None,
) -> MemoryOptimizer:
    """Get the global memory optimizer instance."""
    global _global_optimizer

    with _optimizer_lock:
        if _global_optimizer is None:
            _global_optimizer = MemoryOptimizer(config)
        return _global_optimizer


def create_object_pool(
    name: str,
    factory: Callable[[], T],
    reset_func: Optional[Callable[[T], None]] = None,
) -> ObjectPool[T]:
    """Create a named object pool using the global optimizer."""
    optimizer = get_memory_optimizer()
    return optimizer.create_object_pool(name, factory, reset_func)


def cache_get(key: str) -> Any:
    """Get value from global cache."""
    optimizer = get_memory_optimizer()
    return optimizer.cache_get(key)


def cache_put(key: str, value: Any):
    """Put value in global cache."""
    optimizer = get_memory_optimizer()
    optimizer.cache_put(key, value)


def force_memory_cleanup():
    """Force immediate memory cleanup."""
    optimizer = get_memory_optimizer()
    return optimizer.force_cleanup()


def get_global_memory_stats() -> dict:
    """Get global memory statistics."""
    optimizer = get_memory_optimizer()
    return optimizer.get_memory_stats()


# Factory functions for common objects
def create_signal_wrapper_factory():
    """Factory function for signal wrapper objects."""
    from .signal_manager import SignalMetadata, SignalStatus, SignalWrapper

    def factory():
        metadata = SignalMetadata(
            signal_id="", created_at=0.0, expires_at=0.0, status=SignalStatus.PENDING
        )
        return SignalWrapper(signal=None, metadata=metadata)

    def reset(wrapper):
        wrapper.signal = None
        wrapper.metadata.signal_id = ""
        wrapper.metadata.created_at = 0.0
        wrapper.metadata.expires_at = 0.0
        wrapper.metadata.status = SignalStatus.PENDING

    return factory, reset


def create_enhanced_signal_wrapper_factory():
    """Factory function for enhanced signal wrapper objects."""
    try:
        from .enhanced_signal_manager import (
            EnhancedSignalMetadata,
            EnhancedSignalWrapper,
        )
        from .signal_manager import SignalStatus

        def factory():
            metadata = EnhancedSignalMetadata(
                signal_id="",
                created_at=0.0,
                expires_at=0.0,
                status=SignalStatus.PENDING,
            )
            return EnhancedSignalWrapper(signal=None, metadata=metadata)

        def reset(wrapper):
            wrapper.signal = None
            wrapper.metadata.signal_id = ""
            wrapper.metadata.created_at = 0.0
            wrapper.metadata.expires_at = 0.0
            wrapper.metadata.status = SignalStatus.PENDING
            # Reset enhanced fields
            wrapper.metadata.strategy_name = ""
            wrapper.metadata.market_sector = ""
            wrapper.metadata.volatility_score = 0.0
            wrapper.metadata.priority = "normal"
            if hasattr(wrapper.metadata, "execution_context"):
                wrapper.metadata.execution_context = {}

        return factory, reset

    except ImportError:
        # Fallback to basic signal wrapper
        return create_signal_wrapper_factory()


logger.info("Memory optimization module loaded successfully")
