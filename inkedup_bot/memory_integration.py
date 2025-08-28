#!/usr/bin/env python3
"""
Memory Optimization Integration for InkedUp Bot

This module integrates memory optimization capabilities into existing bot components,
providing seamless memory management across all systems.
"""

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from .memory_optimizer import MemoryPriority, memory_optimizer
from .memory_profiler import ProfileMode, advanced_memory_profiler

logger = logging.getLogger(__name__)


@dataclass
class MemoryOptimizedConfig:
    """Global memory optimization configuration for the bot."""

    enabled: bool = True
    max_memory_mb: float = 1024.0  # 1GB default
    memory_threshold: float = 0.75  # 75% threshold
    profiling_enabled: bool = True
    profiling_mode: ProfileMode = ProfileMode.STANDARD
    cache_enabled: bool = True
    object_pooling_enabled: bool = True
    streaming_threshold: int = 10000  # Use streaming for datasets > 10k items
    gc_optimization_enabled: bool = True


class MemoryOptimizedBot:
    """
    Memory-optimized wrapper for bot components.

    Provides memory optimization for all major bot operations including:
    - Order processing
    - Market data handling
    - Position tracking
    - Signal processing
    """

    def __init__(self, config: MemoryOptimizedConfig | None = None):
        self.config = config or MemoryOptimizedConfig()
        self._initialized = False

        # Memory optimization components
        self.memory_optimizer = None
        self.profiler = None

        # Caches for different data types
        self._order_cache = None
        self._market_cache = None
        self._position_cache = None
        self._signal_cache = None

        # Object pools
        self._order_pool = None
        self._trade_pool = None
        self._signal_pool = None

    async def initialize(self):
        """Initialize memory optimization system."""
        if self._initialized:
            return

        if not self.config.enabled:
            logger.info("Memory optimization disabled")
            return

        logger.info("Initializing memory optimization system...")

        # Initialize memory optimizer
        self.memory_optimizer = memory_optimizer
        if not self.memory_optimizer._initialized:
            self.memory_optimizer.initialize()

        # Initialize profiler if enabled
        if self.config.profiling_enabled:
            self.profiler = advanced_memory_profiler

        # Create caches if enabled
        if self.config.cache_enabled:
            await self._initialize_caches()

        # Create object pools if enabled
        if self.config.object_pooling_enabled:
            await self._initialize_pools()

        # Register memory pressure handlers
        self.memory_optimizer.monitor.add_cleanup_callback(self._handle_memory_pressure)

        self._initialized = True
        logger.info("Memory optimization system initialized")

    async def shutdown(self):
        """Shutdown memory optimization system."""
        if not self._initialized:
            return

        logger.info("Shutting down memory optimization system...")

        # Stop profiling if active
        if self.profiler and self.profiler.profiling_active:
            self.profiler.stop_profiling()

        # Clear all caches
        if self._order_cache:
            self._order_cache.clear()
        if self._market_cache:
            self._market_cache.clear()
        if self._position_cache:
            self._position_cache.clear()
        if self._signal_cache:
            self._signal_cache.clear()

        # Clear all pools
        if self._order_pool:
            self._order_pool.clear()
        if self._trade_pool:
            self._trade_pool.clear()
        if self._signal_pool:
            self._signal_pool.clear()

        self._initialized = False
        logger.info("Memory optimization system shutdown completed")

    async def _initialize_caches(self):
        """Initialize memory-efficient caches for different data types."""
        cache_size_mb = self.config.max_memory_mb * 0.2  # 20% for caches
        individual_cache_size = cache_size_mb / 4  # Split among 4 caches

        self._order_cache = self.memory_optimizer.create_cache(
            "orders", max_memory_mb=individual_cache_size
        )

        self._market_cache = self.memory_optimizer.create_cache(
            "market_data", max_memory_mb=individual_cache_size
        )

        self._position_cache = self.memory_optimizer.create_cache(
            "positions", max_memory_mb=individual_cache_size
        )

        self._signal_cache = self.memory_optimizer.create_cache(
            "signals", max_memory_mb=individual_cache_size
        )

        logger.info(f"Initialized caches with {individual_cache_size:.1f} MB each")

    async def _initialize_pools(self):
        """Initialize object pools for frequently used objects."""

        # Order object pool
        def create_order():
            return {
                "id": None,
                "token_id": None,
                "price": 0.0,
                "size": 0.0,
                "side": None,
                "status": "pending",
                "created_at": None,
                "updated_at": None,
                "metadata": {},
            }

        self._order_pool = self.memory_optimizer.create_pool(
            "orders", create_order, max_size=1000
        )

        # Trade object pool
        def create_trade():
            return {
                "id": None,
                "order_id": None,
                "price": 0.0,
                "size": 0.0,
                "side": None,
                "timestamp": None,
                "market_slug": None,
                "metadata": {},
            }

        self._trade_pool = self.memory_optimizer.create_pool(
            "trades", create_trade, max_size=500
        )

        # Signal object pool
        def create_signal():
            return {
                "id": None,
                "type": None,
                "market_slug": None,
                "side": None,
                "confidence": 0.0,
                "timestamp": None,
                "metadata": {},
                "processed": False,
            }

        self._signal_pool = self.memory_optimizer.create_pool(
            "signals", create_signal, max_size=200
        )

        logger.info("Initialized object pools for orders, trades, and signals")

    def _handle_memory_pressure(self, threshold_level):
        """Handle memory pressure events."""
        logger.warning(f"Memory pressure detected: {threshold_level.value}")

        from .memory_optimizer import MemoryThresholdLevel

        if threshold_level == MemoryThresholdLevel.CRITICAL:
            # Clear low-priority cache entries
            self._clear_low_priority_caches()

        elif threshold_level == MemoryThresholdLevel.EMERGENCY:
            # Emergency cleanup
            self._emergency_cleanup()

    def _clear_low_priority_caches(self):
        """Clear low-priority entries from caches."""
        if self._market_cache:
            # Clear older market data (lowest priority for trading)
            with self._market_cache._lock:
                keys_to_remove = [
                    key
                    for key, priority in self._market_cache._priorities.items()
                    if priority == MemoryPriority.LOW
                ]
                for key in keys_to_remove[: len(keys_to_remove) // 2]:
                    self._market_cache._remove_key(key)

    def _emergency_cleanup(self):
        """Perform emergency memory cleanup."""
        logger.error("Performing emergency memory cleanup")

        # Clear all non-critical caches
        if self._market_cache:
            self._market_cache.clear()
        if self._signal_cache:
            self._signal_cache.clear()

        # Force garbage collection
        if self.config.gc_optimization_enabled:
            import gc

            collected = gc.collect()
            logger.info(f"Emergency GC collected {collected} objects")

    @asynccontextmanager
    async def memory_profiling_session(self, label: str = "session"):
        """Context manager for memory profiling sessions."""
        if not self.profiler or not self.config.profiling_enabled:
            yield None
            return

        self.profiler.start_profiling(label)
        try:
            yield self.profiler
        finally:
            analysis = self.profiler.stop_profiling()

            # Log important findings
            session_summary = analysis.get("session_summary", {})
            memory_delta = session_summary.get("memory_delta_mb", 0)

            if abs(memory_delta) > 10:  # More than 10MB change
                logger.warning(
                    f"Significant memory change in {label}: {memory_delta:+.2f} MB"
                )

            # Check for recommendations
            recommendations = analysis.get("optimization_recommendations", [])
            if recommendations:
                logger.info(
                    f"Memory optimization recommendations available for {label}"
                )

    # Cache management methods

    def cache_order(
        self,
        order_id: str,
        order_data: dict[str, Any],
        priority: MemoryPriority = MemoryPriority.NORMAL,
    ) -> bool:
        """Cache order data with memory efficiency."""
        if not self._order_cache or not self.config.cache_enabled:
            return False

        return self._order_cache.put(order_id, order_data, priority)

    def get_cached_order(self, order_id: str) -> dict[str, Any] | None:
        """Get cached order data."""
        if not self._order_cache or not self.config.cache_enabled:
            return None

        return self._order_cache.get(order_id)

    def cache_market_data(
        self,
        market_key: str,
        market_data: dict[str, Any],
        priority: MemoryPriority = MemoryPriority.LOW,
    ) -> bool:
        """Cache market data (typically lower priority)."""
        if not self._market_cache or not self.config.cache_enabled:
            return False

        return self._market_cache.put(market_key, market_data, priority)

    def get_cached_market_data(self, market_key: str) -> dict[str, Any] | None:
        """Get cached market data."""
        if not self._market_cache or not self.config.cache_enabled:
            return None

        return self._market_cache.get(market_key)

    def cache_position(
        self,
        position_key: str,
        position_data: dict[str, Any],
        priority: MemoryPriority = MemoryPriority.HIGH,
    ) -> bool:
        """Cache position data (high priority for risk management)."""
        if not self._position_cache or not self.config.cache_enabled:
            return False

        return self._position_cache.put(position_key, position_data, priority)

    def get_cached_position(self, position_key: str) -> dict[str, Any] | None:
        """Get cached position data."""
        if not self._position_cache or not self.config.cache_enabled:
            return None

        return self._position_cache.get(position_key)

    # Object pool management methods

    def get_order_object(self) -> dict[str, Any]:
        """Get order object from pool or create new one."""
        if not self._order_pool or not self.config.object_pooling_enabled:
            return {
                "id": None,
                "token_id": None,
                "price": 0.0,
                "size": 0.0,
                "side": None,
                "status": "pending",
                "created_at": None,
                "updated_at": None,
                "metadata": {},
            }

        return self._order_pool.get()

    def return_order_object(self, order_obj: dict[str, Any]):
        """Return order object to pool."""
        if not self._order_pool or not self.config.object_pooling_enabled:
            return

        # Reset object state
        order_obj.update(
            {
                "id": None,
                "token_id": None,
                "price": 0.0,
                "size": 0.0,
                "side": None,
                "status": "pending",
                "created_at": None,
                "updated_at": None,
                "metadata": {},
            }
        )

        self._order_pool.put(order_obj)

    def get_trade_object(self) -> dict[str, Any]:
        """Get trade object from pool."""
        if not self._trade_pool or not self.config.object_pooling_enabled:
            return {
                "id": None,
                "order_id": None,
                "price": 0.0,
                "size": 0.0,
                "side": None,
                "timestamp": None,
                "market_slug": None,
                "metadata": {},
            }

        return self._trade_pool.get()

    def return_trade_object(self, trade_obj: dict[str, Any]):
        """Return trade object to pool."""
        if not self._trade_pool or not self.config.object_pooling_enabled:
            return

        # Reset object state
        trade_obj.update(
            {
                "id": None,
                "order_id": None,
                "price": 0.0,
                "size": 0.0,
                "side": None,
                "timestamp": None,
                "market_slug": None,
                "metadata": {},
            }
        )

        self._trade_pool.put(trade_obj)

    def should_use_streaming(self, data_size: int) -> bool:
        """Determine if streaming should be used based on data size."""
        return data_size > self.config.streaming_threshold

    def get_memory_report(self) -> dict[str, Any]:
        """Get comprehensive memory usage report."""
        if not self._initialized:
            return {"error": "Memory optimization not initialized"}

        base_report = self.memory_optimizer.get_memory_report()

        # Add bot-specific metrics
        bot_metrics = {
            "config": {
                "enabled": self.config.enabled,
                "max_memory_mb": self.config.max_memory_mb,
                "memory_threshold": self.config.memory_threshold,
                "cache_enabled": self.config.cache_enabled,
                "object_pooling_enabled": self.config.object_pooling_enabled,
            },
            "cache_stats": {},
            "pool_stats": {},
        }

        # Cache statistics
        if self._order_cache:
            bot_metrics["cache_stats"]["orders"] = self._order_cache.get_memory_info()
        if self._market_cache:
            bot_metrics["cache_stats"][
                "market_data"
            ] = self._market_cache.get_memory_info()
        if self._position_cache:
            bot_metrics["cache_stats"][
                "positions"
            ] = self._position_cache.get_memory_info()
        if self._signal_cache:
            bot_metrics["cache_stats"]["signals"] = self._signal_cache.get_memory_info()

        # Pool statistics
        if self._order_pool:
            bot_metrics["pool_stats"]["orders"] = self._order_pool.get_stats()
        if self._trade_pool:
            bot_metrics["pool_stats"]["trades"] = self._trade_pool.get_stats()
        if self._signal_pool:
            bot_metrics["pool_stats"]["signals"] = self._signal_pool.get_stats()

        return {**base_report, "bot_memory_optimization": bot_metrics}


# Global memory-optimized bot instance
memory_optimized_bot = MemoryOptimizedBot()


# Convenience functions for easy integration
async def initialize_memory_optimization(config: MemoryOptimizedConfig | None = None):
    """Initialize global memory optimization."""
    global memory_optimized_bot
    if config:
        memory_optimized_bot.config = config
    await memory_optimized_bot.initialize()


async def shutdown_memory_optimization():
    """Shutdown global memory optimization."""
    global memory_optimized_bot
    await memory_optimized_bot.shutdown()


def get_memory_optimized_bot() -> MemoryOptimizedBot:
    """Get the global memory-optimized bot instance."""
    return memory_optimized_bot
