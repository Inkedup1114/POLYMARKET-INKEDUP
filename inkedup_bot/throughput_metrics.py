"""
Throughput Metrics for All Components

Comprehensive throughput measurement system for monitoring data flow rates,
processing capacity, and system performance across all bot components.
"""

import logging
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any, Optional

from .performance_metrics import ComponentType, MetricType, PerformanceMetricsTracker

logger = logging.getLogger(__name__)


class ThroughputType(Enum):
    """Types of throughput measurements"""

    REQUESTS_PER_SECOND = "requests_per_second"
    MESSAGES_PER_SECOND = "messages_per_second"
    ORDERS_PER_MINUTE = "orders_per_minute"
    SIGNALS_PER_MINUTE = "signals_per_minute"
    QUERIES_PER_SECOND = "queries_per_second"
    BYTES_PER_SECOND = "bytes_per_second"
    EVENTS_PER_SECOND = "events_per_second"
    TRADES_PER_MINUTE = "trades_per_minute"


class TimeWindow(Enum):
    """Time windows for throughput calculation"""

    SECONDS_1 = 1
    SECONDS_5 = 5
    SECONDS_10 = 10
    SECONDS_30 = 30
    MINUTES_1 = 60
    MINUTES_5 = 300
    MINUTES_15 = 900


@dataclass
class ThroughputEvent:
    """Individual throughput event"""

    component: ComponentType
    event_type: str
    timestamp: datetime
    count: int = 1
    bytes_size: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThroughputStats:
    """Throughput statistics for a specific metric"""

    component: ComponentType
    metric_name: str
    throughput_type: ThroughputType
    time_window: TimeWindow
    current_rate: float
    peak_rate: float
    avg_rate: float
    min_rate: float
    total_events: int
    total_bytes: int | None
    last_updated: datetime
    trend: str = "stable"  # "increasing", "decreasing", "stable"


@dataclass
class ComponentThroughputSummary:
    """Overall throughput summary for a component"""

    component: ComponentType
    total_throughput_rate: float
    peak_throughput_rate: float
    active_metrics: int
    time_range_minutes: int
    health_status: str  # "healthy", "warning", "critical"
    bottlenecks: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class ThroughputTracker:
    """
    Comprehensive throughput tracking system

    Tracks event rates, data flow, processing capacity, and provides
    performance insights across all system components.
    """

    def __init__(self, retention_hours: int = 24):
        self.retention_hours = retention_hours
        self.retention_seconds = retention_hours * 3600
        self.lock = threading.RLock()

        # Core event storage
        self.events: deque = deque(maxlen=100000)  # Last 100k events
        self.events_by_component: dict[ComponentType, deque] = defaultdict(
            lambda: deque(maxlen=10000)
        )

        # Throughput statistics
        self.throughput_stats: dict[
            tuple[ComponentType, str, TimeWindow], ThroughputStats
        ] = {}
        self.component_summaries: dict[ComponentType, ComponentThroughputSummary] = {}

        # Real-time rate calculations
        self.rate_calculators: dict[str, RateCalculator] = {}

        # Performance tracking
        self.performance_tracker = PerformanceMetricsTracker(self.retention_seconds)

        # Throughput thresholds (events per second)
        self.throughput_thresholds = {
            ComponentType.ORDER_CLIENT: {"warning": 50, "critical": 100},
            ComponentType.SIGNAL_PROCESSOR: {"warning": 100, "critical": 200},
            ComponentType.DATABASE: {"warning": 500, "critical": 1000},
            ComponentType.WEBSOCKET: {"warning": 1000, "critical": 2000},
            ComponentType.MARKET_DATA: {"warning": 500, "critical": 1000},
            ComponentType.SYSTEM: {"warning": 100, "critical": 500},
        }

        # Background calculation thread
        self.calculation_thread = None
        self.running = False

        logger.info("Throughput tracker initialized")

    def start_background_calculations(self):
        """Start background thread for throughput calculations"""
        if self.running:
            return

        self.running = True
        self.calculation_thread = threading.Thread(
            target=self._calculation_loop, daemon=True
        )
        self.calculation_thread.start()
        logger.info("Throughput calculation thread started")

    def stop_background_calculations(self):
        """Stop background calculations"""
        self.running = False
        if self.calculation_thread:
            self.calculation_thread.join(timeout=2.0)
        logger.info("Throughput calculations stopped")

    def _calculation_loop(self):
        """Background loop for throughput calculations"""
        while self.running:
            try:
                self._update_all_throughput_stats()
                self._cleanup_old_events()
                time.sleep(1.0)  # Update every second
            except Exception as e:
                logger.error(f"Error in throughput calculation loop: {e}")
                time.sleep(1.0)

    def record_event(
        self,
        component: ComponentType,
        event_type: str,
        count: int = 1,
        bytes_size: int | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Record a throughput event"""

        event = ThroughputEvent(
            component=component,
            event_type=event_type,
            timestamp=datetime.now(),
            count=count,
            bytes_size=bytes_size,
            metadata=metadata or {},
        )

        with self.lock:
            self.events.append(event)
            self.events_by_component[component].append(event)

            # Update rate calculators
            rate_key = f"{component.value}_{event_type}"
            if rate_key not in self.rate_calculators:
                self.rate_calculators[rate_key] = RateCalculator()

            self.rate_calculators[rate_key].record_event(count, bytes_size)

            # Record in performance tracker
            self.performance_tracker.record_metric(
                component, MetricType.COUNTER, f"throughput_{event_type}", count
            )

    def _update_all_throughput_stats(self):
        """Update throughput statistics for all components and metrics"""
        current_time = datetime.now()

        with self.lock:
            # Update stats for each component and time window
            for component in ComponentType:
                if component not in self.events_by_component:
                    continue

                component_events = self.events_by_component[component]
                if not component_events:
                    continue

                # Get unique event types for this component
                event_types = set(event.event_type for event in component_events)

                for event_type in event_types:
                    for time_window in TimeWindow:
                        self._calculate_throughput_stats(
                            component, event_type, time_window, current_time
                        )

            # Update component summaries
            self._update_component_summaries(current_time)

    def _calculate_throughput_stats(
        self,
        component: ComponentType,
        event_type: str,
        time_window: TimeWindow,
        current_time: datetime,
    ):
        """Calculate throughput statistics for specific component/event/window"""

        window_seconds = time_window.value
        cutoff_time = current_time - timedelta(seconds=window_seconds)

        # Get events in time window
        relevant_events = [
            event
            for event in self.events_by_component[component]
            if (event.event_type == event_type and event.timestamp >= cutoff_time)
        ]

        if not relevant_events:
            return

        # Calculate statistics
        total_events = sum(event.count for event in relevant_events)
        total_bytes = sum(event.bytes_size or 0 for event in relevant_events)
        total_bytes = total_bytes if total_bytes > 0 else None

        current_rate = total_events / window_seconds

        # Determine throughput type
        throughput_type = self._determine_throughput_type(event_type)

        # Get or create stats object
        stats_key = (component, event_type, time_window)
        if stats_key not in self.throughput_stats:
            self.throughput_stats[stats_key] = ThroughputStats(
                component=component,
                metric_name=event_type,
                throughput_type=throughput_type,
                time_window=time_window,
                current_rate=0.0,
                peak_rate=0.0,
                avg_rate=0.0,
                min_rate=float("inf"),
                total_events=0,
                total_bytes=None,
                last_updated=current_time,
            )

        stats = self.throughput_stats[stats_key]

        # Update statistics
        stats.current_rate = current_rate
        stats.peak_rate = max(stats.peak_rate, current_rate)
        stats.min_rate = min(stats.min_rate, current_rate)
        stats.total_events = total_events
        stats.total_bytes = total_bytes
        stats.last_updated = current_time

        # Calculate trend (compare to previous rate)
        rate_key = f"{component.value}_{event_type}"
        if rate_key in self.rate_calculators:
            previous_rate = self.rate_calculators[rate_key].get_rate(
                window_seconds * 2
            )  # Double window for trend

            if current_rate > previous_rate * 1.1:  # 10% increase
                stats.trend = "increasing"
            elif current_rate < previous_rate * 0.9:  # 10% decrease
                stats.trend = "decreasing"
            else:
                stats.trend = "stable"

        # Calculate average rate over longer period
        longer_window = min(3600, window_seconds * 10)  # Up to 1 hour
        longer_cutoff = current_time - timedelta(seconds=longer_window)
        longer_events = [
            event
            for event in self.events_by_component[component]
            if (event.event_type == event_type and event.timestamp >= longer_cutoff)
        ]

        if longer_events:
            longer_total = sum(event.count for event in longer_events)
            stats.avg_rate = longer_total / longer_window

    def _determine_throughput_type(self, event_type: str) -> ThroughputType:
        """Determine throughput type based on event type"""
        event_lower = event_type.lower()

        if "order" in event_lower:
            return ThroughputType.ORDERS_PER_MINUTE
        elif "signal" in event_lower:
            return ThroughputType.SIGNALS_PER_MINUTE
        elif "query" in event_lower or "database" in event_lower:
            return ThroughputType.QUERIES_PER_SECOND
        elif "message" in event_lower or "websocket" in event_lower:
            return ThroughputType.MESSAGES_PER_SECOND
        elif "trade" in event_lower:
            return ThroughputType.TRADES_PER_MINUTE
        elif "request" in event_lower:
            return ThroughputType.REQUESTS_PER_SECOND
        elif "byte" in event_lower or "data" in event_lower:
            return ThroughputType.BYTES_PER_SECOND
        else:
            return ThroughputType.EVENTS_PER_SECOND

    def _update_component_summaries(self, current_time: datetime):
        """Update component throughput summaries"""

        for component in ComponentType:
            if component not in self.events_by_component:
                continue

            # Get all stats for this component (1-minute window)
            component_stats = [
                stats
                for (comp, event_type, window), stats in self.throughput_stats.items()
                if comp == component and window == TimeWindow.MINUTES_1
            ]

            if not component_stats:
                continue

            # Calculate summary metrics
            total_rate = sum(stats.current_rate for stats in component_stats)
            peak_rate = max((stats.peak_rate for stats in component_stats), default=0.0)

            # Determine health status
            thresholds = self.throughput_thresholds.get(
                component, {"warning": 100, "critical": 200}
            )

            if total_rate >= thresholds["critical"]:
                health_status = "critical"
            elif total_rate >= thresholds["warning"]:
                health_status = "warning"
            else:
                health_status = "healthy"

            # Identify bottlenecks
            bottlenecks = []
            recommendations = []

            for stats in component_stats:
                if stats.current_rate >= thresholds["critical"]:
                    bottlenecks.append(
                        f"{stats.metric_name}: {stats.current_rate:.1f}/s"
                    )
                    recommendations.append(f"Optimize {stats.metric_name} processing")
                elif (
                    stats.trend == "increasing"
                    and stats.current_rate >= thresholds["warning"]
                ):
                    recommendations.append(f"Monitor {stats.metric_name} rate increase")

            # Create summary
            self.component_summaries[component] = ComponentThroughputSummary(
                component=component,
                total_throughput_rate=total_rate,
                peak_throughput_rate=peak_rate,
                active_metrics=len(component_stats),
                time_range_minutes=1,
                health_status=health_status,
                bottlenecks=bottlenecks,
                recommendations=recommendations,
            )

    def _cleanup_old_events(self):
        """Remove events older than retention period"""
        cutoff_time = datetime.now() - timedelta(seconds=self.retention_seconds)

        with self.lock:
            # Clean main events deque
            while self.events and self.events[0].timestamp < cutoff_time:
                self.events.popleft()

            # Clean component-specific events
            for component_events in self.events_by_component.values():
                while component_events and component_events[0].timestamp < cutoff_time:
                    component_events.popleft()

    def get_throughput_stats(
        self,
        component: ComponentType | None = None,
        time_window: TimeWindow = TimeWindow.MINUTES_1,
    ) -> dict[str, Any]:
        """Get throughput statistics"""

        with self.lock:
            result = {
                "time_window": time_window.value,
                "timestamp": datetime.now().isoformat(),
                "components": {},
            }

            for (comp, event_type, window), stats in self.throughput_stats.items():
                if component and comp != component:
                    continue
                if window != time_window:
                    continue

                comp_name = comp.value
                if comp_name not in result["components"]:
                    result["components"][comp_name] = {}

                result["components"][comp_name][event_type] = {
                    "current_rate": stats.current_rate,
                    "peak_rate": stats.peak_rate,
                    "avg_rate": stats.avg_rate,
                    "min_rate": stats.min_rate if stats.min_rate != float("inf") else 0,
                    "total_events": stats.total_events,
                    "total_bytes": stats.total_bytes,
                    "trend": stats.trend,
                    "throughput_type": stats.throughput_type.value,
                }

            return result

    def get_component_summary(
        self, component: ComponentType
    ) -> ComponentThroughputSummary | None:
        """Get throughput summary for specific component"""
        with self.lock:
            return self.component_summaries.get(component)

    def get_all_component_summaries(
        self,
    ) -> dict[ComponentType, ComponentThroughputSummary]:
        """Get throughput summaries for all components"""
        with self.lock:
            return self.component_summaries.copy()

    def get_top_throughput_metrics(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get top throughput metrics across all components"""

        with self.lock:
            # Get 1-minute window stats
            one_minute_stats = [
                (stats, f"{stats.component.value}_{stats.metric_name}")
                for (comp, event_type, window), stats in self.throughput_stats.items()
                if window == TimeWindow.MINUTES_1
            ]

            # Sort by current rate
            one_minute_stats.sort(key=lambda x: x[0].current_rate, reverse=True)

            result = []
            for stats, name in one_minute_stats[:limit]:
                result.append(
                    {
                        "name": name,
                        "component": stats.component.value,
                        "metric": stats.metric_name,
                        "current_rate": stats.current_rate,
                        "peak_rate": stats.peak_rate,
                        "trend": stats.trend,
                        "throughput_type": stats.throughput_type.value,
                    }
                )

            return result

    def get_system_throughput_health(self) -> dict[str, Any]:
        """Get overall system throughput health assessment"""

        summaries = self.get_all_component_summaries()

        critical_components = [
            comp.value
            for comp, summary in summaries.items()
            if summary.health_status == "critical"
        ]

        warning_components = [
            comp.value
            for comp, summary in summaries.items()
            if summary.health_status == "warning"
        ]

        total_throughput = sum(
            summary.total_throughput_rate for summary in summaries.values()
        )
        peak_throughput = max(
            (summary.peak_throughput_rate for summary in summaries.values()),
            default=0.0,
        )

        # Overall health assessment
        if critical_components:
            overall_health = "critical"
        elif warning_components:
            overall_health = "warning"
        else:
            overall_health = "healthy"

        # Collect all bottlenecks and recommendations
        all_bottlenecks = []
        all_recommendations = []

        for summary in summaries.values():
            all_bottlenecks.extend(summary.bottlenecks)
            all_recommendations.extend(summary.recommendations)

        return {
            "overall_health": overall_health,
            "total_throughput_rate": total_throughput,
            "peak_throughput_rate": peak_throughput,
            "critical_components": critical_components,
            "warning_components": warning_components,
            "total_components": len(summaries),
            "bottlenecks": all_bottlenecks[:10],  # Top 10
            "recommendations": list(set(all_recommendations))[:10],  # Top 10 unique
            "timestamp": datetime.now().isoformat(),
        }


class RateCalculator:
    """Helper class for real-time rate calculations"""

    def __init__(self, max_events: int = 10000):
        self.events = deque(maxlen=max_events)
        self.lock = threading.RLock()

    def record_event(self, count: int = 1, bytes_size: int | None = None):
        """Record an event for rate calculation"""
        with self.lock:
            self.events.append(
                {"timestamp": time.time(), "count": count, "bytes": bytes_size or 0}
            )

    def get_rate(self, window_seconds: int = 60) -> float:
        """Get events per second in the specified window"""
        current_time = time.time()
        cutoff_time = current_time - window_seconds

        with self.lock:
            recent_events = [
                event for event in self.events if event["timestamp"] >= cutoff_time
            ]

            if not recent_events:
                return 0.0

            total_count = sum(event["count"] for event in recent_events)
            return total_count / window_seconds

    def get_bytes_rate(self, window_seconds: int = 60) -> float:
        """Get bytes per second in the specified window"""
        current_time = time.time()
        cutoff_time = current_time - window_seconds

        with self.lock:
            recent_events = [
                event for event in self.events if event["timestamp"] >= cutoff_time
            ]

            if not recent_events:
                return 0.0

            total_bytes = sum(event["bytes"] for event in recent_events)
            return total_bytes / window_seconds


# Decorators for automatic throughput tracking
def track_throughput(
    component: ComponentType,
    event_type: str,
    tracker: Optional["ThroughputTracker"] = None,
):
    """Decorator for automatic throughput tracking"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal tracker
            if tracker is None:
                tracker = get_throughput_tracker()

            # Record the event
            tracker.record_event(component, event_type)

            try:
                result = func(*args, **kwargs)
                return result
            except Exception:
                # Record error event
                tracker.record_event(component, f"{event_type}_error")
                raise

        return wrapper

    return decorator


def track_throughput_with_size(
    component: ComponentType,
    event_type: str,
    size_func: Callable | None = None,
    tracker: Optional["ThroughputTracker"] = None,
):
    """Decorator for throughput tracking with data size measurement"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal tracker
            if tracker is None:
                tracker = get_throughput_tracker()

            try:
                result = func(*args, **kwargs)

                # Calculate size if function provided
                bytes_size = None
                if size_func:
                    try:
                        bytes_size = size_func(result)
                    except Exception as size_error:
                        # Log size calculation errors for debugging but don't fail the operation
                        log.debug(
                            f"Failed to calculate size for throughput tracking: {size_error}"
                        )

                # Record the event
                tracker.record_event(component, event_type, bytes_size=bytes_size)

                return result

            except Exception:
                tracker.record_event(component, f"{event_type}_error")
                raise

        return wrapper

    return decorator


# Context manager for throughput tracking
class ThroughputContext:
    """Context manager for tracking throughput events"""

    def __init__(
        self,
        component: ComponentType,
        event_type: str,
        tracker: ThroughputTracker | None = None,
        count: int = 1,
        metadata: dict[str, Any] | None = None,
    ):
        self.component = component
        self.event_type = event_type
        self.tracker = tracker or get_throughput_tracker()
        self.count = count
        self.metadata = metadata
        self.bytes_size = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Record error event
            self.tracker.record_event(
                self.component,
                f"{self.event_type}_error",
                self.count,
                self.bytes_size,
                self.metadata,
            )
        else:
            # Record success event
            self.tracker.record_event(
                self.component,
                self.event_type,
                self.count,
                self.bytes_size,
                self.metadata,
            )

    def set_bytes_size(self, bytes_size: int):
        """Set the bytes size for this event"""
        self.bytes_size = bytes_size

    def set_count(self, count: int):
        """Set the event count"""
        self.count = count

    def add_metadata(self, key: str, value: Any):
        """Add metadata to the event"""
        if self.metadata is None:
            self.metadata = {}
        self.metadata[key] = value


# Global throughput tracker instance
_throughput_tracker = None


def get_throughput_tracker() -> ThroughputTracker:
    """Get global throughput tracker instance"""
    global _throughput_tracker

    if _throughput_tracker is None:
        _throughput_tracker = ThroughputTracker()
        _throughput_tracker.start_background_calculations()

    return _throughput_tracker


def initialize_throughput_tracking(retention_hours: int = 24) -> ThroughputTracker:
    """Initialize global throughput tracking"""
    global _throughput_tracker

    if _throughput_tracker is not None:
        _throughput_tracker.stop_background_calculations()

    _throughput_tracker = ThroughputTracker(retention_hours)
    _throughput_tracker.start_background_calculations()

    logger.info("Global throughput tracking initialized")

    return _throughput_tracker
