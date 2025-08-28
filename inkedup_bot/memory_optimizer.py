#!/usr/bin/env python3
"""
Memory Optimization System for InkedUp Bot

This module provides comprehensive memory optimization capabilities including:
- Memory-efficient data structures
- Memory usage monitoring and profiling
- Automatic memory cleanup and garbage collection
- Memory-aware caching and batch processing
"""

import gc
import logging
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import psutil

logger = logging.getLogger(__name__)


class MemoryPriority(Enum):
    """Priority levels for memory management."""

    CRITICAL = 1  # Never evict unless absolutely necessary
    HIGH = 2  # Evict only under memory pressure
    NORMAL = 3  # Standard eviction behavior
    LOW = 4  # First to be evicted


class MemoryThresholdLevel(Enum):
    """Memory usage threshold levels."""

    SAFE = "safe"  # < 60% usage
    WARNING = "warning"  # 60-80% usage
    CRITICAL = "critical"  # 80-95% usage
    EMERGENCY = "emergency"  # > 95% usage


@dataclass
class MemoryMetrics:
    """Memory usage metrics snapshot."""

    timestamp: datetime = field(default_factory=datetime.now)
    total_memory_mb: float = 0.0
    used_memory_mb: float = 0.0
    available_memory_mb: float = 0.0
    memory_percent: float = 0.0
    process_memory_mb: float = 0.0
    process_memory_percent: float = 0.0
    gc_count: tuple[int, int, int] = (0, 0, 0)
    objects_count: int = 0
    threshold_level: MemoryThresholdLevel = MemoryThresholdLevel.SAFE


@dataclass
class MemoryAlert:
    """Memory usage alert."""

    timestamp: datetime
    level: MemoryThresholdLevel
    message: str
    metrics: MemoryMetrics
    action_taken: str | None = None


class MemoryEfficientCache:
    """
    Memory-efficient cache with advanced eviction strategies.

    Features:
    - Size-based and memory-based limits
    - LRU eviction with priority considerations
    - Weak references for automatic cleanup
    - Memory usage tracking per entry
    """

    def __init__(self, max_size: int = 1000, max_memory_mb: float = 100.0):
        self.max_size = max_size
        self.max_memory_mb = max_memory_mb
        self._cache: dict[str, dict[str, Any]] = {}
        self._access_times: dict[str, datetime] = {}
        self._priorities: dict[str, MemoryPriority] = {}
        self._memory_usage: dict[str, float] = {}
        self._lock = threading.RLock()
        self._total_memory_mb = 0.0

    def get(self, key: str) -> Any | None:
        """Get value from cache, updating access time."""
        with self._lock:
            if key in self._cache:
                self._access_times[key] = datetime.now()
                return self._cache[key].get("value")
            return None

    def put(
        self, key: str, value: Any, priority: MemoryPriority = MemoryPriority.NORMAL
    ) -> bool:
        """Put value in cache with memory tracking."""
        with self._lock:
            # Estimate memory usage of the value
            memory_size = self._estimate_memory_usage(value)

            # Check if we need to evict entries
            while (
                len(self._cache) >= self.max_size
                or self._total_memory_mb + memory_size > self.max_memory_mb
            ):
                if not self._evict_lru():
                    return False  # Could not make space

            # Store the value
            self._cache[key] = {"value": value, "created_at": datetime.now()}
            self._access_times[key] = datetime.now()
            self._priorities[key] = priority
            self._memory_usage[key] = memory_size
            self._total_memory_mb += memory_size

            return True

    def _estimate_memory_usage(self, obj: Any) -> float:
        """Estimate memory usage of an object in MB."""
        try:
            if isinstance(obj, (str, bytes)):
                return len(obj) / (1024 * 1024)
            elif isinstance(obj, (list, tuple)):
                return sum(self._estimate_memory_usage(item) for item in obj)
            elif isinstance(obj, dict):
                return sum(
                    self._estimate_memory_usage(k) + self._estimate_memory_usage(v)
                    for k, v in obj.items()
                )
            else:
                return sys.getsizeof(obj) / (1024 * 1024)
        except Exception:
            # Fallback estimation
            return sys.getsizeof(obj) / (1024 * 1024)

    def _evict_lru(self) -> bool:
        """Evict least recently used item with lowest priority."""
        if not self._cache:
            return False

        # Sort by priority (higher value = lower priority) then by access time
        candidates = sorted(
            self._cache.keys(),
            key=lambda k: (self._priorities[k].value, self._access_times[k]),
        )

        if candidates:
            key = candidates[0]
            self._remove_key(key)
            return True

        return False

    def _remove_key(self, key: str):
        """Remove a key and update memory tracking."""
        if key in self._cache:
            self._total_memory_mb -= self._memory_usage.get(key, 0)
            del self._cache[key]
            del self._access_times[key]
            del self._priorities[key]
            del self._memory_usage[key]

    def clear(self):
        """Clear all cached items."""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()
            self._priorities.clear()
            self._memory_usage.clear()
            self._total_memory_mb = 0.0

    def get_memory_info(self) -> dict[str, Any]:
        """Get cache memory information."""
        with self._lock:
            return {
                "total_items": len(self._cache),
                "total_memory_mb": self._total_memory_mb,
                "max_memory_mb": self.max_memory_mb,
                "memory_utilization": self._total_memory_mb / self.max_memory_mb,
                "priority_distribution": {
                    priority.name: sum(
                        1 for p in self._priorities.values() if p == priority
                    )
                    for priority in MemoryPriority
                },
            }


class CircularBuffer:
    """
    Memory-efficient circular buffer with fixed size.

    Automatically overwrites old data when capacity is reached,
    preventing unlimited memory growth.
    """

    def __init__(self, maxsize: int):
        self.maxsize = maxsize
        self._buffer = [None] * maxsize
        self._head = 0
        self._tail = 0
        self._count = 0
        self._lock = threading.RLock()

    def append(self, item: Any) -> None:
        """Add item to buffer, overwriting oldest if full."""
        with self._lock:
            self._buffer[self._tail] = item
            self._tail = (self._tail + 1) % self.maxsize

            if self._count < self.maxsize:
                self._count += 1
            else:
                self._head = (self._head + 1) % self.maxsize

    def __iter__(self) -> Generator[Any, None, None]:
        """Iterate over buffer contents in chronological order."""
        with self._lock:
            for i in range(self._count):
                yield self._buffer[(self._head + i) % self.maxsize]

    def __len__(self) -> int:
        return self._count

    def clear(self) -> None:
        """Clear all buffer contents."""
        with self._lock:
            self._buffer = [None] * self.maxsize
            self._head = 0
            self._tail = 0
            self._count = 0

    def get_recent(self, n: int) -> list[Any]:
        """Get n most recent items."""
        with self._lock:
            if n >= self._count:
                return list(self)

            result = []
            for i in range(n):
                idx = (self._tail - 1 - i) % self.maxsize
                result.append(self._buffer[idx])
            return result[::-1]  # Return in chronological order


class MemoryPool:
    """
    Object pool for reusing memory allocations.

    Reduces garbage collection pressure by reusing objects
    instead of constantly allocating and deallocating.
    """

    def __init__(self, factory: Callable[[], Any], max_size: int = 100):
        self.factory = factory
        self.max_size = max_size
        self._pool: deque = deque()
        self._lock = threading.RLock()
        self._created_count = 0
        self._reused_count = 0

    def get(self) -> Any:
        """Get an object from the pool or create a new one."""
        with self._lock:
            if self._pool:
                self._reused_count += 1
                return self._pool.popleft()
            else:
                self._created_count += 1
                return self.factory()

    def put(self, obj: Any) -> None:
        """Return an object to the pool for reuse."""
        with self._lock:
            if len(self._pool) < self.max_size:
                # Reset object state if it has a reset method
                if hasattr(obj, "reset"):
                    obj.reset()
                self._pool.append(obj)

    def get_stats(self) -> dict[str, Any]:
        """Get pool usage statistics."""
        with self._lock:
            total_requests = self._created_count + self._reused_count
            reuse_rate = (
                self._reused_count / total_requests if total_requests > 0 else 0
            )

            return {
                "pool_size": len(self._pool),
                "max_size": self.max_size,
                "created_count": self._created_count,
                "reused_count": self._reused_count,
                "reuse_rate": reuse_rate,
            }

    def clear(self) -> None:
        """Clear the pool."""
        with self._lock:
            self._pool.clear()


class MemoryMonitor:
    """
    Comprehensive memory monitoring system.

    Tracks memory usage, detects memory pressure,
    and triggers cleanup actions when needed.
    """

    def __init__(self, check_interval: float = 30.0):
        self.check_interval = check_interval
        self.thresholds = {
            MemoryThresholdLevel.WARNING: 60.0,
            MemoryThresholdLevel.CRITICAL: 80.0,
            MemoryThresholdLevel.EMERGENCY: 95.0,
        }

        self._running = False
        self._thread: threading.Thread | None = None
        self._metrics_history: CircularBuffer = CircularBuffer(
            1440
        )  # 24h of minute samples
        self._alert_history: CircularBuffer = CircularBuffer(1000)
        self._cleanup_callbacks: list[Callable[[MemoryThresholdLevel], None]] = []
        self._lock = threading.RLock()

    def start(self) -> None:
        """Start memory monitoring."""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
            logger.info("Memory monitoring started")

    def stop(self) -> None:
        """Stop memory monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("Memory monitoring stopped")

    def get_current_metrics(self) -> MemoryMetrics:
        """Get current memory metrics."""
        try:
            # System memory info
            memory = psutil.virtual_memory()

            # Process memory info
            process = psutil.Process()
            process_memory = process.memory_info()

            # Garbage collection info
            gc_stats = gc.get_count()

            metrics = MemoryMetrics(
                total_memory_mb=memory.total / (1024 * 1024),
                used_memory_mb=memory.used / (1024 * 1024),
                available_memory_mb=memory.available / (1024 * 1024),
                memory_percent=memory.percent,
                process_memory_mb=process_memory.rss / (1024 * 1024),
                process_memory_percent=process.memory_percent(),
                gc_count=gc_stats,
                objects_count=len(gc.get_objects()),
            )

            # Determine threshold level
            if (
                metrics.memory_percent
                >= self.thresholds[MemoryThresholdLevel.EMERGENCY]
            ):
                metrics.threshold_level = MemoryThresholdLevel.EMERGENCY
            elif (
                metrics.memory_percent >= self.thresholds[MemoryThresholdLevel.CRITICAL]
            ):
                metrics.threshold_level = MemoryThresholdLevel.CRITICAL
            elif (
                metrics.memory_percent >= self.thresholds[MemoryThresholdLevel.WARNING]
            ):
                metrics.threshold_level = MemoryThresholdLevel.WARNING
            else:
                metrics.threshold_level = MemoryThresholdLevel.SAFE

            return metrics

        except Exception as e:
            logger.error(f"Error getting memory metrics: {e}")
            return MemoryMetrics()

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        last_threshold = MemoryThresholdLevel.SAFE

        while self._running:
            try:
                metrics = self.get_current_metrics()
                self._metrics_history.append(metrics)

                # Check for threshold changes
                if metrics.threshold_level != last_threshold:
                    self._handle_threshold_change(metrics, last_threshold)
                    last_threshold = metrics.threshold_level

                time.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"Error in memory monitoring loop: {e}")
                time.sleep(self.check_interval)

    def _handle_threshold_change(
        self, metrics: MemoryMetrics, previous_level: MemoryThresholdLevel
    ) -> None:
        """Handle memory threshold level change."""
        if metrics.threshold_level.value < previous_level.value:
            # Memory pressure increasing
            message = f"Memory usage increased to {metrics.threshold_level.value}: {metrics.memory_percent:.1f}%"
            logger.warning(message)

            alert = MemoryAlert(
                timestamp=datetime.now(),
                level=metrics.threshold_level,
                message=message,
                metrics=metrics,
            )

            self._alert_history.append(alert)

            # Trigger cleanup callbacks
            for callback in self._cleanup_callbacks:
                try:
                    callback(metrics.threshold_level)
                except Exception as e:
                    logger.error(f"Error in memory cleanup callback: {e}")

            # Automatic cleanup actions
            if metrics.threshold_level == MemoryThresholdLevel.EMERGENCY:
                self._emergency_cleanup()
            elif metrics.threshold_level == MemoryThresholdLevel.CRITICAL:
                self._critical_cleanup()

    def _critical_cleanup(self) -> None:
        """Perform critical memory cleanup."""
        logger.warning("Performing critical memory cleanup")

        # Force garbage collection
        collected = gc.collect()
        logger.info(f"Garbage collection freed {collected} objects")

    def _emergency_cleanup(self) -> None:
        """Perform emergency memory cleanup."""
        logger.error("Performing emergency memory cleanup")

        # Aggressive garbage collection
        for generation in range(3):
            collected = gc.collect(generation)
            logger.warning(f"GC generation {generation}: freed {collected} objects")

        # Additional cleanup could be added here
        # e.g., clearing caches, reducing buffer sizes, etc.

    def add_cleanup_callback(
        self, callback: Callable[[MemoryThresholdLevel], None]
    ) -> None:
        """Add a cleanup callback function."""
        self._cleanup_callbacks.append(callback)

    def get_metrics_history(self, hours: int = 1) -> list[MemoryMetrics]:
        """Get metrics history for the specified number of hours."""
        samples_needed = min(hours * 60, len(self._metrics_history))
        return self._metrics_history.get_recent(samples_needed)

    def get_alert_history(self, hours: int = 24) -> list[MemoryAlert]:
        """Get alert history for the specified number of hours."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        alerts = []

        for alert in self._alert_history:
            if alert.timestamp >= cutoff_time:
                alerts.append(alert)

        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)


class MemoryOptimizer:
    """
    Main memory optimization coordinator.

    Integrates all memory optimization components and provides
    a unified interface for memory management.
    """

    def __init__(self):
        self.monitor = MemoryMonitor()
        self.pools: dict[str, MemoryPool] = {}
        self.caches: dict[str, MemoryEfficientCache] = {}
        self._initialized = False

        # Register cleanup callbacks
        self.monitor.add_cleanup_callback(self._handle_memory_pressure)

    def initialize(self) -> None:
        """Initialize the memory optimization system."""
        if not self._initialized:
            self.monitor.start()
            self._initialized = True
            logger.info("Memory optimization system initialized")

    def shutdown(self) -> None:
        """Shutdown the memory optimization system."""
        if self._initialized:
            self.monitor.stop()
            self._clear_all_pools()
            self._clear_all_caches()
            self._initialized = False
            logger.info("Memory optimization system shutdown")

    def create_cache(
        self, name: str, max_size: int = 1000, max_memory_mb: float = 100.0
    ) -> MemoryEfficientCache:
        """Create a memory-efficient cache."""
        cache = MemoryEfficientCache(max_size, max_memory_mb)
        self.caches[name] = cache
        return cache

    def create_pool(
        self, name: str, factory: Callable[[], Any], max_size: int = 100
    ) -> MemoryPool:
        """Create a memory pool."""
        pool = MemoryPool(factory, max_size)
        self.pools[name] = pool
        return pool

    def create_circular_buffer(self, maxsize: int) -> CircularBuffer:
        """Create a circular buffer."""
        return CircularBuffer(maxsize)

    def _handle_memory_pressure(self, threshold_level: MemoryThresholdLevel) -> None:
        """Handle memory pressure by cleaning up managed resources."""
        logger.info(f"Handling memory pressure: {threshold_level.value}")

        if threshold_level == MemoryThresholdLevel.CRITICAL:
            # Clear low priority cache entries
            for cache in self.caches.values():
                self._clear_low_priority_cache_entries(cache)

        elif threshold_level == MemoryThresholdLevel.EMERGENCY:
            # Clear all cache entries except critical ones
            for cache in self.caches.values():
                self._emergency_clear_cache(cache)

            # Clear all pools
            for pool in self.pools.values():
                pool.clear()

    def _clear_low_priority_cache_entries(self, cache: MemoryEfficientCache) -> None:
        """Clear low priority entries from cache."""
        with cache._lock:
            keys_to_remove = [
                key
                for key, priority in cache._priorities.items()
                if priority == MemoryPriority.LOW
            ]

            for key in keys_to_remove:
                cache._remove_key(key)

    def _emergency_clear_cache(self, cache: MemoryEfficientCache) -> None:
        """Emergency cache clearing, keeping only critical entries."""
        with cache._lock:
            keys_to_keep = [
                key
                for key, priority in cache._priorities.items()
                if priority == MemoryPriority.CRITICAL
            ]

            # Create new cache state with only critical entries
            new_cache = {}
            new_access_times = {}
            new_priorities = {}
            new_memory_usage = {}
            new_total_memory = 0.0

            for key in keys_to_keep:
                if key in cache._cache:
                    new_cache[key] = cache._cache[key]
                    new_access_times[key] = cache._access_times[key]
                    new_priorities[key] = cache._priorities[key]
                    new_memory_usage[key] = cache._memory_usage[key]
                    new_total_memory += cache._memory_usage[key]

            # Update cache state
            cache._cache = new_cache
            cache._access_times = new_access_times
            cache._priorities = new_priorities
            cache._memory_usage = new_memory_usage
            cache._total_memory_mb = new_total_memory

    def _clear_all_pools(self) -> None:
        """Clear all memory pools."""
        for pool in self.pools.values():
            pool.clear()

    def _clear_all_caches(self) -> None:
        """Clear all caches."""
        for cache in self.caches.values():
            cache.clear()

    def get_memory_report(self) -> dict[str, Any]:
        """Get comprehensive memory usage report."""
        metrics = self.monitor.get_current_metrics()

        cache_info = {}
        for name, cache in self.caches.items():
            cache_info[name] = cache.get_memory_info()

        pool_info = {}
        for name, pool in self.pools.items():
            pool_info[name] = pool.get_stats()

        return {
            "timestamp": datetime.now().isoformat(),
            "system_metrics": {
                "total_memory_mb": metrics.total_memory_mb,
                "used_memory_mb": metrics.used_memory_mb,
                "available_memory_mb": metrics.available_memory_mb,
                "memory_percent": metrics.memory_percent,
                "process_memory_mb": metrics.process_memory_mb,
                "process_memory_percent": metrics.process_memory_percent,
                "threshold_level": metrics.threshold_level.value,
            },
            "caches": cache_info,
            "pools": pool_info,
            "gc_stats": {"count": metrics.gc_count, "objects": metrics.objects_count},
        }


# Global memory optimizer instance
memory_optimizer = MemoryOptimizer()
