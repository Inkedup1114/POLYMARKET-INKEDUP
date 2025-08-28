"""
Dynamic Connection Pool Optimizer

Intelligent connection pool sizing system that automatically adjusts pool configurations
based on real-time market activity, system load, and trading patterns to optimize
resource utilization and prevent connection contention during high-frequency trading.

Key optimizations:
- Market volatility-aware pool sizing
- Load-based dynamic scaling 
- Peak trading hours optimization
- Circuit breaker integration
- Real-time performance monitoring
- Resource utilization optimization
"""

import asyncio
import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("dynamic_connection_optimizer")


class MarketActivityLevel(Enum):
    """Market activity levels for pool sizing decisions."""

    DORMANT = 0  # Very low activity (nights, weekends)
    LOW = 1  # Low activity
    NORMAL = 2  # Normal trading activity
    HIGH = 3  # High activity (market hours)
    VOLATILE = 4  # Very high activity (breaking news, volatility spikes)
    CRITICAL = 5  # Extreme activity (major events, crashes)


class ScalingDecision(Enum):
    """Pool scaling decisions."""

    SCALE_DOWN = "scale_down"
    MAINTAIN = "maintain"
    SCALE_UP = "scale_up"
    EMERGENCY_SCALE = "emergency_scale"


@dataclass
class MarketMetrics:
    """Market activity and performance metrics."""

    # Trading activity metrics
    signals_per_minute: float = 0.0
    orders_per_minute: float = 0.0
    websocket_messages_per_minute: float = 0.0
    market_data_requests_per_minute: float = 0.0

    # System performance metrics
    connection_pool_utilization: float = 0.0
    average_response_time_ms: float = 0.0
    failed_connections: int = 0
    queue_depth: int = 0

    # Market conditions
    volatility_index: float = 0.0
    volume_spike_factor: float = 1.0
    news_event_active: bool = False

    # Time-based factors
    is_market_hours: bool = True
    is_weekend: bool = False
    hour_of_day: int = 12


@dataclass
class PoolSizingDecision:
    """Connection pool sizing decision with rationale."""

    current_min_size: int
    current_max_size: int
    recommended_min_size: int
    recommended_max_size: int
    decision: ScalingDecision
    confidence: float  # 0.0 to 1.0
    rationale: str
    priority: int  # 1=low, 5=critical
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class OptimizerConfig:
    """Configuration for dynamic connection pool optimizer."""

    # Base pool sizing
    base_min_connections: int = 2
    base_max_connections: int = 15

    # Database-specific limits
    postgresql_max_limit: int = 50
    sqlite_max_limit: int = 12  # SQLite write concurrency limit

    # Scaling thresholds
    scale_up_utilization: float = 0.75  # Scale up at 75% utilization
    scale_down_utilization: float = 0.30  # Scale down at 30% utilization
    emergency_utilization: float = 0.90  # Emergency scaling at 90%

    # Activity level thresholds (requests per minute)
    dormant_threshold: float = 5.0
    low_activity_threshold: float = 20.0
    normal_activity_threshold: float = 100.0
    high_activity_threshold: float = 300.0
    volatile_threshold: float = 1000.0

    # Response time thresholds (milliseconds)
    good_response_time: float = 50.0
    acceptable_response_time: float = 150.0
    poor_response_time: float = 500.0

    # Scaling behavior
    aggressive_scaling: bool = False  # Conservative by default
    min_scale_interval: int = 60  # Minimum seconds between scaling decisions
    max_daily_scales: int = 20  # Maximum scaling operations per day

    # Monitoring
    enable_monitoring: bool = True
    metrics_window_minutes: int = 5
    decision_history_limit: int = 100


class DynamicConnectionOptimizer:
    """
    Dynamic connection pool optimizer that adjusts pool sizes based on
    real-time market activity and system performance.
    """

    def __init__(self, config: Optional[OptimizerConfig] = None):
        """
        Initialize the dynamic connection optimizer.

        Args:
            config: Configuration for optimization behavior
        """
        self.config = config or OptimizerConfig()

        # Metrics collection
        self._metrics_history: deque = deque(maxlen=100)
        self._decision_history: deque = deque(maxlen=self.config.decision_history_limit)

        # Activity tracking
        self._activity_counters = defaultdict(int)
        self._last_activity_reset = time.time()

        # Pool references and current configurations
        self._pool_references: Dict[str, Any] = {}  # pool_id -> pool object
        self._current_configs: Dict[str, Dict[str, int]] = (
            {}
        )  # pool_id -> {min_size, max_size}

        # Scaling control
        self._last_scaling_decision = {}  # pool_id -> timestamp
        self._daily_scale_count = defaultdict(int)  # pool_id -> count
        self._last_daily_reset = datetime.now().date()

        # Market condition detection
        self._volatility_detector = VolatilityDetector()
        self._peak_hours_detector = PeakHoursDetector()

        # Monitoring and control
        self._monitoring_task: Optional[asyncio.Task] = None
        self._shutdown = False

        logger.info("Dynamic connection optimizer initialized")

    def register_pool(
        self,
        pool_id: str,
        pool_reference: Any,
        current_min_size: int,
        current_max_size: int,
    ) -> None:
        """
        Register a connection pool for dynamic optimization.

        Args:
            pool_id: Unique identifier for the pool
            pool_reference: Reference to the actual pool object
            current_min_size: Current minimum pool size
            current_max_size: Current maximum pool size
        """
        self._pool_references[pool_id] = pool_reference
        self._current_configs[pool_id] = {
            "min_size": current_min_size,
            "max_size": current_max_size,
        }

        logger.info(
            f"Registered pool {pool_id} with size {current_min_size}-{current_max_size}"
        )

    def update_activity_metrics(
        self,
        signals_count: int = 0,
        orders_count: int = 0,
        websocket_messages_count: int = 0,
        market_data_requests_count: int = 0,
    ) -> None:
        """
        Update activity counters for pool sizing decisions.

        Args:
            signals_count: Number of trading signals processed
            orders_count: Number of orders placed
            websocket_messages_count: Number of WebSocket messages received
            market_data_requests_count: Number of market data API requests
        """
        self._activity_counters["signals"] += signals_count
        self._activity_counters["orders"] += orders_count
        self._activity_counters["websocket_messages"] += websocket_messages_count
        self._activity_counters["market_data_requests"] += market_data_requests_count

    def collect_system_metrics(self, pool_id: str) -> MarketMetrics:
        """
        Collect current system and market metrics for a pool.

        Args:
            pool_id: Pool identifier to collect metrics for

        Returns:
            Current market and system metrics
        """
        current_time = time.time()
        time_elapsed = current_time - self._last_activity_reset
        minutes_elapsed = max(time_elapsed / 60.0, 0.1)  # Avoid division by zero

        # Calculate per-minute rates
        signals_per_minute = self._activity_counters["signals"] / minutes_elapsed
        orders_per_minute = self._activity_counters["orders"] / minutes_elapsed
        websocket_per_minute = (
            self._activity_counters["websocket_messages"] / minutes_elapsed
        )
        market_data_per_minute = (
            self._activity_counters["market_data_requests"] / minutes_elapsed
        )

        # Get pool-specific metrics
        pool_utilization = 0.0
        response_time = 0.0
        failed_connections = 0
        queue_depth = 0

        if pool_id in self._pool_references:
            pool = self._pool_references[pool_id]

            # Extract metrics from pool if available
            if hasattr(pool, "stats"):
                stats = pool.stats
                if hasattr(stats, "current_connections_in_use") and hasattr(
                    stats, "current_idle_connections"
                ):
                    total_connections = (
                        stats.current_connections_in_use
                        + stats.current_idle_connections
                    )
                    if total_connections > 0:
                        pool_utilization = (
                            stats.current_connections_in_use / total_connections
                        )

                if hasattr(stats, "average_response_time_ms"):
                    response_time = stats.average_response_time_ms

                if hasattr(stats, "total_failed_connections"):
                    failed_connections = getattr(stats, "total_failed_connections", 0)

        # Detect market conditions
        volatility_index = self._volatility_detector.calculate_volatility_index(
            signals_per_minute, orders_per_minute
        )

        now = datetime.now()
        is_market_hours = self._peak_hours_detector.is_market_hours(now)
        is_weekend = now.weekday() >= 5

        return MarketMetrics(
            signals_per_minute=signals_per_minute,
            orders_per_minute=orders_per_minute,
            websocket_messages_per_minute=websocket_per_minute,
            market_data_requests_per_minute=market_data_per_minute,
            connection_pool_utilization=pool_utilization,
            average_response_time_ms=response_time,
            failed_connections=failed_connections,
            queue_depth=queue_depth,
            volatility_index=volatility_index,
            volume_spike_factor=self._calculate_volume_spike_factor(),
            news_event_active=self._detect_news_event(),
            is_market_hours=is_market_hours,
            is_weekend=is_weekend,
            hour_of_day=now.hour,
        )

    def determine_market_activity_level(
        self, metrics: MarketMetrics
    ) -> MarketActivityLevel:
        """
        Determine current market activity level based on metrics.

        Args:
            metrics: Current market metrics

        Returns:
            Market activity level classification
        """
        # Calculate total request rate
        total_activity = (
            metrics.signals_per_minute
            + metrics.orders_per_minute
            + metrics.websocket_messages_per_minute
            + metrics.market_data_requests_per_minute
        )

        # Apply time-based adjustments
        if metrics.is_weekend:
            total_activity *= 0.3  # Weekend activity is typically lower
        elif not metrics.is_market_hours:
            total_activity *= 0.5  # After-hours activity is lower

        # Apply volatility multiplier
        if metrics.volatility_index > 2.0:
            total_activity *= 1.5

        # Classify activity level
        if metrics.news_event_active or metrics.volatility_index > 3.0:
            return MarketActivityLevel.CRITICAL
        elif total_activity > self.config.volatile_threshold:
            return MarketActivityLevel.VOLATILE
        elif total_activity > self.config.high_activity_threshold:
            return MarketActivityLevel.HIGH
        elif total_activity > self.config.normal_activity_threshold:
            return MarketActivityLevel.NORMAL
        elif total_activity > self.config.low_activity_threshold:
            return MarketActivityLevel.LOW
        else:
            return MarketActivityLevel.DORMANT

    def calculate_optimal_pool_size(
        self, pool_id: str, metrics: MarketMetrics, activity_level: MarketActivityLevel
    ) -> PoolSizingDecision:
        """
        Calculate optimal pool size based on current conditions.

        Args:
            pool_id: Pool identifier
            metrics: Current system metrics
            activity_level: Current market activity level

        Returns:
            Pool sizing decision with rationale
        """
        current_config = self._current_configs.get(pool_id, {})
        current_min = current_config.get("min_size", self.config.base_min_connections)
        current_max = current_config.get("max_size", self.config.base_max_connections)

        # Determine if this is a SQLite pool (has lower limits)
        pool = self._pool_references.get(pool_id)
        is_sqlite = "sqlite" in pool_id.lower() if pool_id else False
        max_limit = (
            self.config.sqlite_max_limit
            if is_sqlite
            else self.config.postgresql_max_limit
        )

        # Base sizing by activity level
        sizing_map = {
            MarketActivityLevel.DORMANT: (1, 3),
            MarketActivityLevel.LOW: (2, 6),
            MarketActivityLevel.NORMAL: (3, 12),
            MarketActivityLevel.HIGH: (5, 20),
            MarketActivityLevel.VOLATILE: (8, 30),
            MarketActivityLevel.CRITICAL: (12, 40),
        }

        base_min, base_max = sizing_map[activity_level]

        # Apply SQLite limits
        if is_sqlite:
            base_max = min(base_max, max_limit)

        # Adjust based on system performance
        performance_multiplier = 1.0

        # High utilization -> increase pool size
        if metrics.connection_pool_utilization > self.config.emergency_utilization:
            performance_multiplier = 1.5
            decision_type = ScalingDecision.EMERGENCY_SCALE
            priority = 5
        elif metrics.connection_pool_utilization > self.config.scale_up_utilization:
            performance_multiplier = 1.2
            decision_type = ScalingDecision.SCALE_UP
            priority = 3
        elif metrics.connection_pool_utilization < self.config.scale_down_utilization:
            performance_multiplier = 0.8
            decision_type = ScalingDecision.SCALE_DOWN
            priority = 2
        else:
            decision_type = ScalingDecision.MAINTAIN
            priority = 1

        # Poor response times -> increase pool size
        if metrics.average_response_time_ms > self.config.poor_response_time:
            performance_multiplier = max(performance_multiplier, 1.3)
            if decision_type == ScalingDecision.MAINTAIN:
                decision_type = ScalingDecision.SCALE_UP
                priority = 4

        # Apply performance adjustments
        recommended_min = max(1, int(base_min * performance_multiplier))
        recommended_max = max(
            recommended_min + 2, int(base_max * performance_multiplier)
        )

        # Apply hard limits
        recommended_min = min(recommended_min, max_limit - 2)
        recommended_max = min(recommended_max, max_limit)

        # Calculate confidence based on data quality
        confidence = self._calculate_confidence(metrics, activity_level)

        # Generate rationale
        rationale_parts = [
            f"Activity level: {activity_level.name}",
            f"Pool utilization: {metrics.connection_pool_utilization:.1%}",
            f"Response time: {metrics.average_response_time_ms:.1f}ms",
        ]

        if metrics.volatility_index > 2.0:
            rationale_parts.append(f"High volatility: {metrics.volatility_index:.1f}")

        if metrics.news_event_active:
            rationale_parts.append("News event detected")

        rationale = "; ".join(rationale_parts)

        return PoolSizingDecision(
            current_min_size=current_min,
            current_max_size=current_max,
            recommended_min_size=recommended_min,
            recommended_max_size=recommended_max,
            decision=decision_type,
            confidence=confidence,
            rationale=rationale,
            priority=priority,
        )

    def should_apply_scaling_decision(
        self, pool_id: str, decision: PoolSizingDecision
    ) -> bool:
        """
        Determine if a scaling decision should be applied based on constraints.

        Args:
            pool_id: Pool identifier
            decision: Proposed scaling decision

        Returns:
            True if scaling should be applied
        """
        current_time = time.time()

        # Check minimum interval between scaling decisions
        last_scaling = self._last_scaling_decision.get(pool_id, 0)
        if current_time - last_scaling < self.config.min_scale_interval:
            if decision.decision != ScalingDecision.EMERGENCY_SCALE:
                return False

        # Check daily scaling limits
        today = datetime.now().date()
        if today != self._last_daily_reset:
            self._daily_scale_count.clear()
            self._last_daily_reset = today

        if self._daily_scale_count[pool_id] >= self.config.max_daily_scales:
            if decision.decision != ScalingDecision.EMERGENCY_SCALE:
                return False

        # Check if change is significant enough
        current_min = decision.current_min_size
        current_max = decision.current_max_size
        recommended_min = decision.recommended_min_size
        recommended_max = decision.recommended_max_size

        min_change = abs(recommended_min - current_min)
        max_change = abs(recommended_max - current_max)

        # Require significant change unless it's emergency scaling
        if decision.decision != ScalingDecision.EMERGENCY_SCALE:
            if min_change <= 1 and max_change <= 2:
                return False

        # Check confidence threshold (bypass for emergency scaling)
        if decision.decision != ScalingDecision.EMERGENCY_SCALE:
            min_confidence = 0.6 if self.config.aggressive_scaling else 0.7
            if decision.confidence < min_confidence:
                return False

        return True

    async def apply_scaling_decision(
        self, pool_id: str, decision: PoolSizingDecision
    ) -> bool:
        """
        Apply a scaling decision to a connection pool.

        Args:
            pool_id: Pool identifier
            decision: Scaling decision to apply

        Returns:
            True if scaling was successfully applied
        """
        if pool_id not in self._pool_references:
            logger.error(f"Pool {pool_id} not registered for scaling")
            return False

        pool = self._pool_references[pool_id]

        try:
            # Update pool configuration
            if hasattr(pool, "min_size"):
                pool.min_size = decision.recommended_min_size
            if hasattr(pool, "max_size"):
                pool.max_size = decision.recommended_max_size

            # Update our tracking
            self._current_configs[pool_id] = {
                "min_size": decision.recommended_min_size,
                "max_size": decision.recommended_max_size,
            }

            # Record scaling decision
            self._last_scaling_decision[pool_id] = time.time()
            self._daily_scale_count[pool_id] += 1
            self._decision_history.append(decision)

            logger.info(
                f"Scaled pool {pool_id}: {decision.current_min_size}-{decision.current_max_size} "
                f"→ {decision.recommended_min_size}-{decision.recommended_max_size} "
                f"(reason: {decision.rationale})"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to scale pool {pool_id}: {e}")
            return False

    async def optimize_pool_sizes(self) -> Dict[str, PoolSizingDecision]:
        """
        Analyze all registered pools and make optimization decisions.

        Returns:
            Dictionary of pool decisions by pool_id
        """
        decisions = {}

        for pool_id in self._pool_references.keys():
            try:
                # Collect current metrics
                metrics = self.collect_system_metrics(pool_id)
                self._metrics_history.append(metrics)

                # Determine activity level
                activity_level = self.determine_market_activity_level(metrics)

                # Calculate optimal sizing
                decision = self.calculate_optimal_pool_size(
                    pool_id, metrics, activity_level
                )
                decisions[pool_id] = decision

                # Apply decision if appropriate
                if self.should_apply_scaling_decision(pool_id, decision):
                    await self.apply_scaling_decision(pool_id, decision)

            except Exception as e:
                logger.error(f"Error optimizing pool {pool_id}: {e}")

        # Reset activity counters
        self._reset_activity_counters()

        return decisions

    def _reset_activity_counters(self):
        """Reset activity counters for next measurement period."""
        self._activity_counters.clear()
        self._last_activity_reset = time.time()

    def _calculate_volume_spike_factor(self) -> float:
        """Calculate volume spike factor based on recent activity."""
        if len(self._metrics_history) < 2:
            return 1.0

        recent_activity = []
        for metrics in list(self._metrics_history)[-5:]:  # Last 5 measurements
            total_activity = (
                metrics.signals_per_minute
                + metrics.orders_per_minute
                + metrics.websocket_messages_per_minute
            )
            recent_activity.append(total_activity)

        if len(recent_activity) < 2:
            return 1.0

        current = recent_activity[-1]
        historical_avg = statistics.mean(recent_activity[:-1])

        if historical_avg == 0:
            return 1.0

        return max(1.0, current / historical_avg)

    def _detect_news_event(self) -> bool:
        """Detect if a news event is currently affecting the market."""
        # Simple heuristic: sudden spike in activity
        volume_spike = self._calculate_volume_spike_factor()
        return volume_spike > 3.0

    def _calculate_confidence(
        self, metrics: MarketMetrics, activity_level: MarketActivityLevel
    ) -> float:
        """Calculate confidence in the sizing decision."""
        confidence = 0.5  # Base confidence

        # Higher confidence with more data points
        if len(self._metrics_history) >= 10:
            confidence += 0.2

        # Higher confidence during clear activity patterns
        if activity_level in [
            MarketActivityLevel.DORMANT,
            MarketActivityLevel.CRITICAL,
        ]:
            confidence += 0.2

        # Lower confidence with high volatility (uncertain conditions)
        if metrics.volatility_index > 2.5:
            confidence -= 0.1

        # Higher confidence with good system performance
        if metrics.average_response_time_ms < self.config.good_response_time:
            confidence += 0.1

        return max(0.1, min(1.0, confidence))

    async def start_monitoring(self, optimization_interval: int = 300) -> None:
        """
        Start continuous monitoring and optimization.

        Args:
            optimization_interval: Seconds between optimization runs
        """
        if self._monitoring_task:
            logger.warning("Monitoring already started")
            return

        self._monitoring_task = asyncio.create_task(
            self._monitoring_loop(optimization_interval)
        )
        logger.info(
            f"Started connection pool monitoring (interval: {optimization_interval}s)"
        )

    async def _monitoring_loop(self, interval: int):
        """Background monitoring and optimization loop."""
        while not self._shutdown:
            try:
                decisions = await self.optimize_pool_sizes()

                # Log summary
                if decisions:
                    scaling_actions = sum(
                        1
                        for d in decisions.values()
                        if d.decision != ScalingDecision.MAINTAIN
                    )
                    logger.debug(
                        f"Pool optimization completed: {scaling_actions} scaling actions"
                    )

                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait before retry

    async def stop_monitoring(self):
        """Stop continuous monitoring."""
        self._shutdown = True
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped connection pool monitoring")

    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get current optimization statistics."""
        return {
            "registered_pools": len(self._pool_references),
            "total_decisions": len(self._decision_history),
            "recent_metrics_count": len(self._metrics_history),
            "daily_scale_counts": dict(self._daily_scale_count),
            "current_configurations": dict(self._current_configs),
            "last_optimization": (
                max(self._last_scaling_decision.values())
                if self._last_scaling_decision
                else None
            ),
        }


class VolatilityDetector:
    """Helper class to detect market volatility."""

    def __init__(self):
        self._activity_history: deque = deque(maxlen=20)

    def calculate_volatility_index(
        self, signals_per_minute: float, orders_per_minute: float
    ) -> float:
        """Calculate volatility index based on activity patterns."""
        current_activity = signals_per_minute + orders_per_minute
        self._activity_history.append(current_activity)

        if len(self._activity_history) < 5:
            return 1.0  # Default volatility

        # Calculate coefficient of variation
        activity_list = list(self._activity_history)
        if len(activity_list) < 2:
            return 1.0

        mean_activity = statistics.mean(activity_list)
        if mean_activity == 0:
            return 1.0

        try:
            std_dev = statistics.stdev(activity_list)
            volatility_index = std_dev / mean_activity
            return max(1.0, volatility_index * 3)  # Scale and normalize
        except statistics.StatisticsError:
            return 1.0


class PeakHoursDetector:
    """Helper class to detect peak trading hours."""

    def __init__(self):
        # Define peak trading hours (UTC)
        self.peak_hours = {
            "weekday": [(9, 16), (14, 21)],  # US and European markets
            "weekend": [],  # No peak hours on weekends
        }

    def is_market_hours(self, dt: datetime) -> bool:
        """Check if given datetime is during market hours."""
        is_weekend = dt.weekday() >= 5

        if is_weekend:
            return False

        hour = dt.hour
        peak_ranges = self.peak_hours["weekday"]

        for start_hour, end_hour in peak_ranges:
            if start_hour <= hour < end_hour:
                return True

        return False


# Factory functions for easy integration
def create_connection_optimizer(
    aggressive_scaling: bool = False, enable_monitoring: bool = True
) -> DynamicConnectionOptimizer:
    """
    Create a connection pool optimizer with recommended settings.

    Args:
        aggressive_scaling: Enable aggressive scaling behavior
        enable_monitoring: Enable continuous monitoring

    Returns:
        Configured DynamicConnectionOptimizer instance
    """
    config = OptimizerConfig(
        aggressive_scaling=aggressive_scaling, enable_monitoring=enable_monitoring
    )

    optimizer = DynamicConnectionOptimizer(config)
    logger.info("Created dynamic connection optimizer")
    return optimizer


logger.info("Dynamic connection optimizer module loaded successfully")
