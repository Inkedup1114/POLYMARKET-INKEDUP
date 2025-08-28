"""
Memory-optimized signal manager with LRU cache, object pooling, and compression.

This module extends the existing signal manager with comprehensive memory optimization:
- Object pooling for signal wrappers and metadata
- LRU cache with automatic eviction and compression
- Memory-efficient storage with cleanup strategies
- Performance monitoring and optimization analytics
"""

import logging
import time
from collections import defaultdict, deque
from typing import Any, Dict, Optional

from .enhanced_signal_manager import EnhancedSignalManager, EnhancedSignalManagerConfig
from .memory_optimization import (
    LRUCache,
    MemoryOptimizationConfig,
    ObjectPool,
    create_enhanced_signal_wrapper_factory,
    create_signal_wrapper_factory,
    get_memory_optimizer,
)
from .signal_manager import (
    SignalManager,
    SignalManagerConfig,
    SignalStatus,
    SignalWrapper,
)
from .signals import TradingSignal

logger = logging.getLogger("optimized_signal_manager")


class OptimizedSignalManagerConfig:
    """Configuration for memory-optimized signal manager."""

    def __init__(
        self,
        # Base signal manager config
        max_concurrent_signals: int = 10,
        signal_default_timeout_seconds: float = 30.0,
        signal_complement_timeout_seconds: float = 45.0,
        cleanup_interval: float = 300.0,
        max_processed_signals: int = 100,  # Reduced from 1000
        max_expired_signals: int = 50,  # Reduced from 1000
        max_failed_signals: int = 25,  # Reduced from 500
        # Memory optimization settings
        enable_memory_optimization: bool = True,
        max_signal_cache_size: int = 500,
        max_signal_memory_mb: float = 25.0,
        enable_signal_compression: bool = True,
        compression_threshold: int = 512,
        # Object pooling
        enable_object_pooling: bool = True,
        signal_wrapper_pool_size: int = 50,
        # Cleanup optimization
        aggressive_cleanup_threshold: int = 200,
    ):

        # Store all configuration
        self.max_concurrent_signals = max_concurrent_signals
        self.signal_default_timeout_seconds = signal_default_timeout_seconds
        self.signal_complement_timeout_seconds = signal_complement_timeout_seconds
        self.cleanup_interval = cleanup_interval
        self.max_processed_signals = max_processed_signals
        self.max_expired_signals = max_expired_signals
        self.max_failed_signals = max_failed_signals

        self.enable_memory_optimization = enable_memory_optimization
        self.max_signal_cache_size = max_signal_cache_size
        self.max_signal_memory_mb = max_signal_memory_mb
        self.enable_signal_compression = enable_signal_compression
        self.compression_threshold = compression_threshold

        self.enable_object_pooling = enable_object_pooling
        self.signal_wrapper_pool_size = signal_wrapper_pool_size
        self.aggressive_cleanup_threshold = aggressive_cleanup_threshold

    def to_base_config(self) -> SignalManagerConfig:
        """Convert to base SignalManagerConfig for parent class."""
        return SignalManagerConfig(
            max_concurrent_signals=self.max_concurrent_signals,
            default_signal_timeout=self.signal_default_timeout_seconds,
            complement_signal_timeout=self.signal_complement_timeout_seconds,
            cleanup_interval=self.cleanup_interval,
            max_expired_signals=self.max_expired_signals,
            max_failed_signals=self.max_failed_signals,
        )


class OptimizedSignalManager(SignalManager):
    """
    Memory-optimized signal manager with advanced optimization strategies.

    Provides significant memory footprint reduction through:
    - LRU caching with compression for historical signals
    - Object pooling for frequently created/destroyed objects
    - Aggressive cleanup of old signals
    - Memory-efficient storage structures
    """

    def __init__(self, config: Optional[OptimizedSignalManagerConfig] = None):
        self.optimized_config = config or OptimizedSignalManagerConfig()

        # Initialize base signal manager with base config
        base_config = self.optimized_config.to_base_config()
        super().__init__(base_config)

        # Memory optimization setup
        self._memory_optimizer = None
        self._signal_wrapper_pool: Optional[ObjectPool] = None
        self._signal_cache: Optional[LRUCache] = None

        if self.optimized_config.enable_memory_optimization:
            self._setup_memory_optimization()

        # Optimized storage structures
        self._processed_signals = deque(
            maxlen=self.optimized_config.max_processed_signals
        )
        self._expired_signals = deque(maxlen=self.optimized_config.max_expired_signals)
        self._failed_signals = deque(maxlen=self.optimized_config.max_failed_signals)

        # Memory usage tracking
        self._memory_stats = {
            "total_signals_pooled": 0,
            "total_signals_cached": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "pool_reuse_rate": 0.0,
            "memory_saved_mb": 0.0,
            "cleanup_operations": 0,
        }

        # Last cleanup time
        self._last_cleanup = time.time()

        logger.info("OptimizedSignalManager initialized with memory optimization")

    def _setup_memory_optimization(self):
        """Initialize memory optimization components."""
        try:
            # Get global memory optimizer
            memory_config = MemoryOptimizationConfig(
                max_cache_size=self.optimized_config.max_signal_cache_size,
                max_cache_memory_mb=self.optimized_config.max_signal_memory_mb,
                enable_compression=self.optimized_config.enable_signal_compression,
                compression_threshold=self.optimized_config.compression_threshold,
            )

            self._memory_optimizer = get_memory_optimizer(memory_config)

            # Create object pool for signal wrappers
            if self.optimized_config.enable_object_pooling:
                factory, reset_func = create_signal_wrapper_factory()
                self._signal_wrapper_pool = self._memory_optimizer.create_object_pool(
                    "signal_wrappers", factory, reset_func
                )

            # Get global cache for signal storage
            self._signal_cache = self._memory_optimizer.get_cache()

            logger.info("Memory optimization setup complete")

        except Exception as e:
            logger.error(f"Failed to setup memory optimization: {e}")
            self.optimized_config.enable_memory_optimization = False

    def _create_signal_wrapper(
        self, signal: TradingSignal, timeout: float
    ) -> SignalWrapper:
        """Create signal wrapper with optional object pooling."""
        if self._signal_wrapper_pool:
            try:
                # Get wrapper from pool
                wrapper = self._signal_wrapper_pool.acquire()

                # Configure the wrapper
                wrapper.signal = signal
                wrapper.metadata.signal_id = signal.signal_id
                wrapper.metadata.created_at = time.time()
                wrapper.metadata.expires_at = wrapper.metadata.created_at + timeout
                wrapper.metadata.status = SignalStatus.PENDING

                self._memory_stats["total_signals_pooled"] += 1
                return wrapper

            except Exception as e:
                logger.warning(f"Failed to get wrapper from pool: {e}")

        # Fallback to normal creation
        return super()._create_signal_wrapper(signal, timeout)

    def _store_processed_signal(self, wrapper: SignalWrapper):
        """Store processed signal with caching optimization."""
        try:
            # Store in cache if available
            if self._signal_cache:
                cache_key = f"processed_{wrapper.metadata.signal_id}"

                # Create lightweight cache entry
                cache_entry = {
                    "signal_id": wrapper.metadata.signal_id,
                    "created_at": wrapper.metadata.created_at,
                    "status": wrapper.metadata.status.value,
                    "market_slug": (
                        wrapper.signal.market_slug if wrapper.signal else None
                    ),
                    "token_id": wrapper.signal.token_id if wrapper.signal else None,
                    "strategy_name": getattr(wrapper.signal, "strategy_name", None),
                }

                self._signal_cache.put(cache_key, cache_entry)
                self._memory_stats["total_signals_cached"] += 1

            # Store in deque with size limit
            self._processed_signals.append(wrapper)

            # Release wrapper back to pool
            if self._signal_wrapper_pool:
                self._signal_wrapper_pool.release(wrapper)

        except Exception as e:
            logger.error(f"Error storing processed signal: {e}")
            # Fallback to deque storage only
            self._processed_signals.append(wrapper)

    def _store_expired_signal(self, wrapper: SignalWrapper):
        """Store expired signal with optimization."""
        try:
            # Store minimal info in cache
            if self._signal_cache:
                cache_key = f"expired_{wrapper.metadata.signal_id}"
                cache_entry = {
                    "signal_id": wrapper.metadata.signal_id,
                    "expired_at": time.time(),
                    "original_timeout": wrapper.metadata.expires_at
                    - wrapper.metadata.created_at,
                }
                self._signal_cache.put(cache_key, cache_entry)

            # Store in limited deque
            self._expired_signals.append(wrapper)

            # Release to pool
            if self._signal_wrapper_pool:
                self._signal_wrapper_pool.release(wrapper)

        except Exception as e:
            logger.error(f"Error storing expired signal: {e}")
            self._expired_signals.append(wrapper)

    def _store_failed_signal(self, wrapper: SignalWrapper, error_msg: str):
        """Store failed signal with optimization."""
        try:
            # Store failure info in cache
            if self._signal_cache:
                cache_key = f"failed_{wrapper.metadata.signal_id}"
                cache_entry = {
                    "signal_id": wrapper.metadata.signal_id,
                    "failed_at": time.time(),
                    "error_message": error_msg[:200],  # Truncate error message
                    "market_slug": (
                        wrapper.signal.market_slug if wrapper.signal else None
                    ),
                }
                self._signal_cache.put(cache_key, cache_entry)

            # Store in limited deque
            self._failed_signals.append(wrapper)

            # Release to pool
            if self._signal_wrapper_pool:
                self._signal_wrapper_pool.release(wrapper)

        except Exception as e:
            logger.error(f"Error storing failed signal: {e}")
            self._failed_signals.append(wrapper)

    def get_signal_history(self, signal_id: str) -> Optional[Dict[str, Any]]:
        """Get signal history from cache or storage."""
        if not self._signal_cache:
            return None

        # Check cache for all types
        for prefix in ["processed", "expired", "failed"]:
            cache_key = f"{prefix}_{signal_id}"
            entry = self._signal_cache.get(cache_key)
            if entry:
                self._memory_stats["cache_hits"] += 1
                return {"type": prefix, "data": entry}

        self._memory_stats["cache_misses"] += 1
        return None

    def _should_cleanup(self) -> bool:
        """Determine if aggressive cleanup should be performed."""
        current_time = time.time()

        # Time-based cleanup
        if current_time - self._last_cleanup > self.optimized_config.cleanup_interval:
            return True

        # Signal count-based cleanup
        total_signals = (
            len(self._pending_signals)
            + len(self._processing_signals)
            + len(self._processed_signals)
            + len(self._expired_signals)
            + len(self._failed_signals)
        )

        if total_signals > self.optimized_config.aggressive_cleanup_threshold:
            return True

        return False

    def _perform_optimized_cleanup(self):
        """Perform comprehensive memory cleanup."""
        try:
            logger.debug("Starting optimized signal cleanup")

            cleanup_start = time.time()
            initial_memory = self._estimate_memory_usage()

            # Clean up expired signals beyond limits
            while (
                len(self._expired_signals)
                > self.optimized_config.max_expired_signals // 2
            ):
                self._expired_signals.popleft()

            # Clean up old processed signals
            while (
                len(self._processed_signals)
                > self.optimized_config.max_processed_signals // 2
            ):
                self._processed_signals.popleft()

            # Clean up old failed signals
            while (
                len(self._failed_signals)
                > self.optimized_config.max_failed_signals // 2
            ):
                self._failed_signals.popleft()

            # Force memory optimizer cleanup
            if self._memory_optimizer:
                self._memory_optimizer.force_cleanup()

            # Update stats
            cleanup_time = time.time() - cleanup_start
            final_memory = self._estimate_memory_usage()
            memory_saved = initial_memory - final_memory

            self._memory_stats["cleanup_operations"] += 1
            self._memory_stats["memory_saved_mb"] += memory_saved / (1024 * 1024)
            self._last_cleanup = time.time()

            logger.info(
                f"Optimized cleanup completed in {cleanup_time:.3f}s, saved {memory_saved/1024/1024:.2f}MB"
            )

        except Exception as e:
            logger.error(f"Error during optimized cleanup: {e}")

    def _estimate_memory_usage(self) -> int:
        """Estimate current memory usage in bytes."""
        try:
            # Rough estimation based on signal counts and average sizes
            pending_size = len(self._pending_signals) * 1024  # ~1KB per pending signal
            processing_size = len(self._processing_signals) * 1024
            processed_size = len(self._processed_signals) * 512  # Smaller for processed
            expired_size = len(self._expired_signals) * 256  # Even smaller for expired
            failed_size = len(self._failed_signals) * 256

            return (
                pending_size
                + processing_size
                + processed_size
                + expired_size
                + failed_size
            )

        except Exception:
            return 0

    def submit_signal(self, signal: TradingSignal) -> str:
        """Submit signal with memory optimization."""
        # Check if cleanup is needed before processing
        if self._should_cleanup():
            self._perform_optimized_cleanup()

        # Use parent method for actual submission
        return super().submit_signal(signal)

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics."""
        base_stats = self.get_metrics()

        # Add memory optimization stats
        memory_stats = {
            "memory_optimization": self._memory_stats.copy(),
            "storage_counts": {
                "pending": len(self._pending_signals),
                "processing": len(self._processing_signals),
                "processed": len(self._processed_signals),
                "expired": len(self._expired_signals),
                "failed": len(self._failed_signals),
            },
            "estimated_memory_mb": self._estimate_memory_usage() / (1024 * 1024),
        }

        # Get memory optimizer stats if available
        if self._memory_optimizer:
            optimizer_stats = self._memory_optimizer.get_memory_stats()
            memory_stats["optimizer_stats"] = optimizer_stats

        # Calculate efficiency metrics
        total_cached = self._memory_stats["total_signals_cached"]
        total_pooled = self._memory_stats["total_signals_pooled"]

        if total_cached > 0:
            cache_hit_rate = (
                self._memory_stats["cache_hits"]
                / (
                    self._memory_stats["cache_hits"]
                    + self._memory_stats["cache_misses"]
                )
                if (
                    self._memory_stats["cache_hits"]
                    + self._memory_stats["cache_misses"]
                )
                > 0
                else 0
            )
            memory_stats["memory_optimization"]["cache_hit_rate"] = cache_hit_rate

        if total_pooled > 0:
            pool_efficiency = total_pooled / (
                total_pooled + len(self._processed_signals)
            )
            memory_stats["memory_optimization"]["pool_efficiency"] = pool_efficiency

        # Combine with base stats
        base_stats["memory_stats"] = memory_stats
        return base_stats

    def shutdown(self):
        """Shutdown with memory optimization cleanup."""
        logger.info("Shutting down optimized signal manager")

        # Perform final cleanup
        self._perform_optimized_cleanup()

        # Shutdown memory optimizer
        if self._memory_optimizer:
            try:
                self._memory_optimizer.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down memory optimizer: {e}")

        logger.info("OptimizedSignalManager shutdown complete")


class OptimizedEnhancedSignalManager(EnhancedSignalManager):
    """
    Memory-optimized enhanced signal manager combining both optimization approaches.

    Provides the advanced signal processing capabilities of EnhancedSignalManager
    with the memory efficiency of OptimizedSignalManager.
    """

    def __init__(self, config: Optional[EnhancedSignalManagerConfig] = None):
        super().__init__(config)

        # Add memory optimization
        self.optimized_config = OptimizedSignalManagerConfig()
        self._memory_optimizer = None
        self._signal_cache: Optional[LRUCache] = None

        if self.optimized_config.enable_memory_optimization:
            self._setup_memory_optimization()

        # Memory tracking
        self._memory_stats = {
            "enhanced_signals_cached": 0,
            "priority_queue_optimizations": 0,
            "volatility_data_compressed": 0,
        }

        logger.info("OptimizedEnhancedSignalManager initialized")

    def _setup_memory_optimization(self):
        """Setup memory optimization for enhanced signal manager."""
        try:
            from .memory_optimization import (
                MemoryOptimizationConfig,
                get_memory_optimizer,
            )

            memory_config = MemoryOptimizationConfig(
                max_cache_size=self.optimized_config.max_signal_cache_size,
                max_cache_memory_mb=self.optimized_config.max_signal_memory_mb,
                enable_compression=True,
                compression_threshold=256,  # Smaller threshold for enhanced data
            )

            self._memory_optimizer = get_memory_optimizer(memory_config)
            self._signal_cache = self._memory_optimizer.get_cache()

            logger.info("Enhanced signal manager memory optimization setup complete")

        except Exception as e:
            logger.error(f"Failed to setup enhanced memory optimization: {e}")

    def _optimize_priority_queues(self):
        """Optimize priority queue memory usage."""
        if not self._signal_cache:
            return

        try:
            # Cache frequently accessed market conditions
            for token_id, condition in self._market_conditions.items():
                cache_key = f"market_condition_{token_id}"
                self._signal_cache.put(cache_key, condition.value)

            # Limit volatility history size more aggressively
            for token_id, history in self._volatility_history.items():
                if len(history) > 50:  # Reduced from 100
                    # Keep only recent entries
                    recent_history = deque(list(history)[-50:], maxlen=50)
                    self._volatility_history[token_id] = recent_history

            # Similar optimization for price history
            for token_id, history in self._price_history.items():
                if len(history) > 50:
                    recent_history = deque(list(history)[-50:], maxlen=50)
                    self._price_history[token_id] = recent_history

            self._memory_stats["priority_queue_optimizations"] += 1

        except Exception as e:
            logger.error(f"Error optimizing priority queues: {e}")

    async def submit_enhanced_signal(self, *args, **kwargs) -> str:
        """Submit enhanced signal with memory optimization."""
        # Optimize memory before processing
        self._optimize_priority_queues()

        # Use parent method
        return await super().submit_enhanced_signal(*args, **kwargs)

    def get_enhanced_memory_stats(self) -> Dict[str, Any]:
        """Get enhanced memory statistics."""
        stats = {
            "enhanced_memory_stats": self._memory_stats.copy(),
            "priority_queues_size": {
                priority.value: len(queue)
                for priority, queue in self._priority_queues.items()
            },
            "volatility_history_size": len(self._volatility_history),
            "price_history_size": len(self._price_history),
            "market_conditions_tracked": len(self._market_conditions),
        }

        # Get base enhanced stats
        base_stats = self.get_enhanced_stats()
        stats.update(base_stats)

        return stats


# Factory functions for creating optimized signal managers
def create_optimized_signal_manager(
    config: Optional[OptimizedSignalManagerConfig] = None,
) -> OptimizedSignalManager:
    """Create memory-optimized signal manager."""
    return OptimizedSignalManager(config)


def create_optimized_enhanced_signal_manager(
    config: Optional[EnhancedSignalManagerConfig] = None,
) -> OptimizedEnhancedSignalManager:
    """Create memory-optimized enhanced signal manager."""
    return OptimizedEnhancedSignalManager(config)


logger.info("Optimized signal manager module loaded successfully")
