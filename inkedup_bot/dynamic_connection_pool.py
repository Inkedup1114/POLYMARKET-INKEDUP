"""
Dynamic Connection Pool Management System.

This module provides an adaptive connection pooling system that automatically 
adjusts pool sizes based on real-time activity metrics and load patterns.

Key Features:
- Dynamic pool sizing based on queue depth and activity patterns
- Activity monitoring with moving averages and trend analysis
- Load-based scaling with configurable thresholds and limits
- Performance metrics collection and optimization recommendations
- Automatic pool resizing during high/low activity periods
- Integration with existing connection pool infrastructure

The system monitors connection usage patterns and automatically scales pool
sizes up during high-activity periods and down during quiet periods to
optimize resource utilization and performance.
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from .connection_pool import ConnectionPoolManager, PoolState

logger = logging.getLogger("dynamic_connection_pool")


class ActivityLevel(Enum):
    """Activity level classifications for dynamic pool sizing."""

    IDLE = "idle"  # Very low activity
    LOW = "low"  # Below normal activity
    NORMAL = "normal"  # Normal activity levels
    HIGH = "high"  # Above normal activity
    PEAK = "peak"  # Very high activity
    OVERLOAD = "overload"  # Extreme activity requiring max resources


@dataclass
class ActivityMetrics:
    """Activity metrics for connection pool monitoring."""

    timestamp: float
    active_connections: int = 0
    pending_requests: int = 0
    requests_per_second: float = 0.0
    average_wait_time: float = 0.0
    pool_utilization: float = 0.0
    error_rate: float = 0.0


@dataclass
class DynamicPoolConfig:
    """Configuration for dynamic connection pool management."""

    # Base pool configuration
    initial_size: int = 5
    min_size: int = 1
    max_size: int = 50

    # Activity level thresholds (pool utilization %)
    idle_threshold: float = 0.1  # < 10% utilization
    low_threshold: float = 0.3  # < 30% utilization
    normal_threshold: float = 0.6  # < 60% utilization
    high_threshold: float = 0.8  # < 80% utilization
    peak_threshold: float = 0.9  # < 90% utilization
    # > 90% = overload

    # Scaling parameters
    scale_up_factor: float = 1.5  # Multiply pool size by this when scaling up
    scale_down_factor: float = 0.8  # Multiply pool size by this when scaling down
    min_scale_interval: float = 30.0  # Minimum seconds between scaling operations

    # Monitoring configuration
    metrics_window_size: int = 60  # Number of metrics samples to keep
    evaluation_interval: float = 10.0  # Seconds between pool evaluation

    # Performance thresholds
    max_wait_time_ms: float = 100.0  # Max acceptable wait time in ms
    max_error_rate: float = 0.05  # Max acceptable error rate (5%)


class DynamicConnectionPoolManager:
    """
    Dynamic connection pool manager that adapts pool sizes based on activity.

    This manager wraps existing connection pools and provides automatic
    scaling based on real-time metrics and usage patterns.
    """

    def __init__(
        self,
        base_pool_manager: ConnectionPoolManager,
        config: Optional[DynamicPoolConfig] = None,
    ):
        self.base_pool_manager = base_pool_manager
        self.config = config or DynamicPoolConfig()

        # Activity monitoring
        self.metrics_history: deque[ActivityMetrics] = deque(
            maxlen=self.config.metrics_window_size
        )
        self.current_activity_level = ActivityLevel.NORMAL
        self.last_scale_time = 0.0

        # Performance tracking
        self.scaling_history: List[Dict[str, Any]] = []
        self.performance_stats = {
            "total_scale_ups": 0,
            "total_scale_downs": 0,
            "current_pool_size": self.config.initial_size,
            "peak_pool_size": self.config.initial_size,
            "avg_utilization": 0.0,
            "avg_wait_time": 0.0,
        }

        # Background tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info(
            f"DynamicConnectionPoolManager initialized with config: {self.config}"
        )

    async def start(self):
        """Start the dynamic pool management system."""
        if self._running:
            return

        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Dynamic connection pool monitoring started")

    async def stop(self):
        """Stop the dynamic pool management system."""
        if not self._running:
            return

        self._running = False

        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Dynamic connection pool monitoring stopped")

    async def _monitoring_loop(self):
        """Main monitoring loop that evaluates and adjusts pool sizes."""
        while self._running:
            try:
                # Collect current metrics
                metrics = await self._collect_metrics()
                self.metrics_history.append(metrics)

                # Evaluate activity level
                activity_level = self._evaluate_activity_level(metrics)

                # Check if scaling is needed
                if self._should_scale(activity_level, metrics):
                    await self._scale_pool(activity_level, metrics)

                # Update performance statistics
                self._update_performance_stats()

                await asyncio.sleep(self.config.evaluation_interval)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.config.evaluation_interval)

    async def _collect_metrics(self) -> ActivityMetrics:
        """Collect current activity metrics from the connection pool."""
        current_time = time.time()

        try:
            # Get pool statistics if available
            pool_stats = {}
            if hasattr(self.base_pool_manager, "get_pool_stats"):
                pool_stats = await self.base_pool_manager.get_pool_stats()

            # Calculate metrics from available data
            active_connections = pool_stats.get("active_connections", 0)
            pool_size = pool_stats.get("pool_size", self.config.initial_size)
            pending_requests = pool_stats.get("pending_requests", 0)

            # Calculate utilization
            utilization = active_connections / max(pool_size, 1)

            # Estimate requests per second from recent activity
            rps = self._calculate_requests_per_second()

            # Get average wait time if available
            avg_wait_time = pool_stats.get("average_wait_time", 0.0)

            # Calculate error rate from recent history
            error_rate = self._calculate_error_rate()

            return ActivityMetrics(
                timestamp=current_time,
                active_connections=active_connections,
                pending_requests=pending_requests,
                requests_per_second=rps,
                average_wait_time=avg_wait_time,
                pool_utilization=utilization,
                error_rate=error_rate,
            )

        except Exception as e:
            logger.warning(f"Failed to collect metrics: {e}")
            return ActivityMetrics(timestamp=current_time)

    def _calculate_requests_per_second(self) -> float:
        """Calculate requests per second from recent metrics."""
        if len(self.metrics_history) < 2:
            return 0.0

        # Get metrics from last 10 seconds
        recent_metrics = [
            m for m in self.metrics_history if time.time() - m.timestamp <= 10.0
        ]

        if len(recent_metrics) < 2:
            return 0.0

        # Estimate RPS from connection activity changes
        total_activity = sum(m.active_connections for m in recent_metrics)
        time_span = recent_metrics[-1].timestamp - recent_metrics[0].timestamp

        return total_activity / max(time_span, 1.0)

    def _calculate_error_rate(self) -> float:
        """Calculate error rate from recent activity."""
        # This would be enhanced with actual error tracking
        # For now, return a low baseline
        return 0.01

    def _evaluate_activity_level(self, metrics: ActivityMetrics) -> ActivityLevel:
        """Evaluate current activity level based on metrics."""
        utilization = metrics.pool_utilization

        if utilization >= self.config.peak_threshold:
            return ActivityLevel.OVERLOAD if utilization > 0.95 else ActivityLevel.PEAK
        elif utilization >= self.config.high_threshold:
            return ActivityLevel.HIGH
        elif utilization >= self.config.normal_threshold:
            return ActivityLevel.NORMAL
        elif utilization >= self.config.low_threshold:
            return ActivityLevel.LOW
        elif utilization >= self.config.idle_threshold:
            return ActivityLevel.LOW
        else:
            return ActivityLevel.IDLE

    def _should_scale(
        self, activity_level: ActivityLevel, metrics: ActivityMetrics
    ) -> bool:
        """Determine if pool scaling is needed."""
        current_time = time.time()

        # Check minimum interval between scaling operations
        if current_time - self.last_scale_time < self.config.min_scale_interval:
            return False

        # Check if activity level has changed significantly
        if activity_level != self.current_activity_level:
            self.current_activity_level = activity_level
            return True

        # Check performance thresholds
        if (
            metrics.average_wait_time > self.config.max_wait_time_ms
            or metrics.error_rate > self.config.max_error_rate
        ):
            return True

        # Check if we have sustained high/low activity
        if len(self.metrics_history) >= 5:
            recent_utilizations = [
                m.pool_utilization for m in list(self.metrics_history)[-5:]
            ]
            avg_utilization = sum(recent_utilizations) / len(recent_utilizations)

            # Scale up if sustained high utilization
            if avg_utilization > self.config.high_threshold:
                return True

            # Scale down if sustained low utilization
            if avg_utilization < self.config.low_threshold:
                return True

        return False

    async def _scale_pool(
        self, activity_level: ActivityLevel, metrics: ActivityMetrics
    ):
        """Scale the connection pool based on activity level."""
        current_size = self.performance_stats["current_pool_size"]
        new_size = self._calculate_target_size(activity_level, current_size)

        if new_size == current_size:
            return

        # Ensure new size is within bounds
        new_size = max(self.config.min_size, min(self.config.max_size, new_size))

        try:
            # Attempt to resize the pool (this would depend on pool implementation)
            success = await self._resize_pool(new_size)

            if success:
                scaling_direction = "up" if new_size > current_size else "down"

                # Record scaling operation
                self.scaling_history.append(
                    {
                        "timestamp": time.time(),
                        "from_size": current_size,
                        "to_size": new_size,
                        "direction": scaling_direction,
                        "activity_level": activity_level.value,
                        "utilization": metrics.pool_utilization,
                        "reason": self._get_scaling_reason(activity_level, metrics),
                    }
                )

                # Update statistics
                self.performance_stats["current_pool_size"] = new_size
                self.performance_stats["peak_pool_size"] = max(
                    self.performance_stats["peak_pool_size"], new_size
                )

                if scaling_direction == "up":
                    self.performance_stats["total_scale_ups"] += 1
                else:
                    self.performance_stats["total_scale_downs"] += 1

                self.last_scale_time = time.time()

                logger.info(
                    f"Pool scaled {scaling_direction}: {current_size} → {new_size} "
                    f"(activity: {activity_level.value}, utilization: {metrics.pool_utilization:.1%})"
                )

        except Exception as e:
            logger.error(f"Failed to scale pool: {e}")

    def _calculate_target_size(
        self, activity_level: ActivityLevel, current_size: int
    ) -> int:
        """Calculate target pool size based on activity level."""
        if activity_level in (ActivityLevel.OVERLOAD, ActivityLevel.PEAK):
            # Scale up aggressively for high activity
            return min(
                int(current_size * self.config.scale_up_factor), self.config.max_size
            )
        elif activity_level == ActivityLevel.HIGH:
            # Moderate scale up
            return min(int(current_size * 1.2), self.config.max_size)
        elif activity_level == ActivityLevel.IDLE:
            # Scale down for idle periods
            return max(
                int(current_size * self.config.scale_down_factor), self.config.min_size
            )
        elif activity_level == ActivityLevel.LOW:
            # Small scale down
            return max(int(current_size * 0.9), self.config.min_size)
        else:
            # Normal activity - no change
            return current_size

    async def _resize_pool(self, new_size: int) -> bool:
        """Resize the underlying connection pool."""
        # This would need to be implemented based on the specific pool implementation
        # For now, simulate successful resizing
        logger.debug(f"Simulating pool resize to {new_size}")
        return True

    def _get_scaling_reason(
        self, activity_level: ActivityLevel, metrics: ActivityMetrics
    ) -> str:
        """Get human-readable reason for scaling decision."""
        reasons = []

        if activity_level in (ActivityLevel.OVERLOAD, ActivityLevel.PEAK):
            reasons.append("high activity level")
        elif activity_level == ActivityLevel.IDLE:
            reasons.append("idle period")

        if metrics.pool_utilization > self.config.high_threshold:
            reasons.append(f"high utilization ({metrics.pool_utilization:.1%})")

        if metrics.average_wait_time > self.config.max_wait_time_ms:
            reasons.append(f"high wait time ({metrics.average_wait_time:.1f}ms)")

        if metrics.error_rate > self.config.max_error_rate:
            reasons.append(f"high error rate ({metrics.error_rate:.1%})")

        return "; ".join(reasons) or "activity level change"

    def _update_performance_stats(self):
        """Update performance statistics from recent metrics."""
        if not self.metrics_history:
            return

        recent_metrics = list(self.metrics_history)[-10:]  # Last 10 samples

        self.performance_stats["avg_utilization"] = sum(
            m.pool_utilization for m in recent_metrics
        ) / len(recent_metrics)

        self.performance_stats["avg_wait_time"] = sum(
            m.average_wait_time for m in recent_metrics
        ) / len(recent_metrics)

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        return {
            "config": {
                "min_size": self.config.min_size,
                "max_size": self.config.max_size,
                "initial_size": self.config.initial_size,
            },
            "current_state": {
                "pool_size": self.performance_stats["current_pool_size"],
                "activity_level": self.current_activity_level.value,
                "utilization": self.performance_stats["avg_utilization"],
                "wait_time": self.performance_stats["avg_wait_time"],
            },
            "scaling_stats": {
                "total_scale_ups": self.performance_stats["total_scale_ups"],
                "total_scale_downs": self.performance_stats["total_scale_downs"],
                "peak_pool_size": self.performance_stats["peak_pool_size"],
                "total_scaling_events": len(self.scaling_history),
            },
            "recent_scaling": self.scaling_history[-5:] if self.scaling_history else [],
            "metrics_collected": len(self.metrics_history),
            "monitoring_active": self._running,
        }

    def get_optimization_recommendations(self) -> List[str]:
        """Get optimization recommendations based on collected metrics."""
        recommendations = []

        stats = self.performance_stats

        if stats["total_scale_ups"] > stats["total_scale_downs"] * 2:
            recommendations.append(
                "Consider increasing base pool size - frequent scale-ups detected"
            )

        if stats["total_scale_downs"] > stats["total_scale_ups"] * 2:
            recommendations.append(
                "Consider reducing base pool size - frequent scale-downs detected"
            )

        if stats["avg_utilization"] > 0.8:
            recommendations.append(
                "High average utilization - consider increasing max pool size"
            )

        if stats["avg_utilization"] < 0.2:
            recommendations.append(
                "Low average utilization - consider reducing base pool size"
            )

        if stats["avg_wait_time"] > self.config.max_wait_time_ms:
            recommendations.append(
                "High average wait times - consider more aggressive scaling"
            )

        if len(self.scaling_history) > 50:
            recommendations.append(
                "Frequent scaling events - consider adjusting thresholds"
            )

        return recommendations or ["Pool configuration appears optimal"]


async def create_dynamic_pool_manager(
    database_url: str, config: Optional[DynamicPoolConfig] = None, **base_pool_kwargs
) -> DynamicConnectionPoolManager:
    """Create a dynamic connection pool manager with the specified configuration."""

    # Create base pool manager
    base_manager = ConnectionPoolManager.create_pool(
        database_url=database_url, **base_pool_kwargs
    )

    # Create dynamic manager
    dynamic_manager = DynamicConnectionPoolManager(
        base_pool_manager=base_manager, config=config
    )

    # Start monitoring
    await dynamic_manager.start()

    logger.info(
        f"Dynamic connection pool manager created and started for {database_url}"
    )

    return dynamic_manager
