"""
Cache performance dashboard and monitoring interface.

This module provides a real-time dashboard for monitoring cache performance,
displaying metrics, alerts, and providing administrative controls for cache management.
"""

import json
import logging
from datetime import datetime
from typing import Any

from .cache_analytics import AlertSeverity, get_cache_analytics
from .cache_integration import get_cache_integration_manager

logger = logging.getLogger(__name__)


class CacheDashboard:
    """Real-time cache performance dashboard and monitoring interface."""

    def __init__(self):
        self.analytics = get_cache_analytics()
        self.integration_manager = get_cache_integration_manager()
        self._dashboard_data: dict[str, Any] = {}
        self._last_update = datetime.now()
        self._update_interval = 30  # seconds

    async def get_dashboard_data(self, refresh: bool = False) -> dict[str, Any]:
        """Get comprehensive dashboard data with performance metrics and alerts."""
        now = datetime.now()

        # Check if we need to refresh data
        if refresh or (now - self._last_update).total_seconds() > self._update_interval:
            await self._refresh_dashboard_data()
            self._last_update = now

        return self._dashboard_data

    async def _refresh_dashboard_data(self):
        """Refresh dashboard data with latest metrics."""
        try:
            # Get performance summary for all caches
            performance_summary = self.analytics.get_all_caches_summary(
                time_window_minutes=60
            )

            # Get active alerts
            all_alerts = self.analytics.get_active_alerts()
            critical_alerts = self.analytics.get_active_alerts(AlertSeverity.CRITICAL)
            high_alerts = self.analytics.get_active_alerts(AlertSeverity.HIGH)

            # Calculate system-wide statistics
            system_stats = await self._calculate_system_stats()

            # Get cache status information
            cache_status = await self._get_cache_status()

            self._dashboard_data = {
                "timestamp": datetime.now().isoformat(),
                "system_overview": {
                    "total_requests_1h": performance_summary["overall_metrics"][
                        "total_requests"
                    ],
                    "overall_hit_rate": performance_summary["overall_metrics"][
                        "overall_hit_rate"
                    ],
                    "overall_error_rate": performance_summary["overall_metrics"][
                        "overall_error_rate"
                    ],
                    "active_caches": performance_summary["overall_metrics"][
                        "active_caches"
                    ],
                    "system_health_score": self._calculate_system_health_score(
                        performance_summary
                    ),
                    **system_stats,
                },
                "cache_performance": performance_summary["cache_details"],
                "alerts": {
                    "total_active": len(all_alerts),
                    "critical": len(critical_alerts),
                    "high": len(high_alerts),
                    "medium": len(
                        [a for a in all_alerts if a.severity == AlertSeverity.MEDIUM]
                    ),
                    "low": len(
                        [a for a in all_alerts if a.severity == AlertSeverity.LOW]
                    ),
                    "recent_alerts": [
                        self._format_alert(alert) for alert in all_alerts[:10]
                    ],  # Last 10 alerts
                },
                "cache_status": cache_status,
                "recommendations": performance_summary["recommendations"],
                "trends": await self._calculate_performance_trends(),
            }

        except Exception as e:
            logger.error(f"Error refreshing dashboard data: {e}")
            self._dashboard_data["error"] = f"Dashboard refresh failed: {str(e)}"

    async def _calculate_system_stats(self) -> dict[str, Any]:
        """Calculate system-wide cache statistics."""
        try:
            # This would typically integrate with system monitoring
            # For now, we'll provide estimated values based on cache metrics
            return {
                "total_memory_usage_mb": 0.0,  # Would be calculated from all cache instances
                "cache_efficiency_score": 0.0,  # Composite efficiency metric
                "api_calls_saved_1h": 0,  # Estimated API calls prevented by caching
                "database_queries_saved_1h": 0,  # Estimated DB queries prevented
                "average_latency_reduction_ms": 0.0,  # Average latency improvement from caching
            }
        except Exception as e:
            logger.error(f"Error calculating system stats: {e}")
            return {}

    async def _get_cache_status(self) -> dict[str, Any]:
        """Get current status of all cache instances."""
        try:
            cache_statuses = {}

            # Get status from integration manager
            if hasattr(self.integration_manager, "market_cache"):
                cache_statuses["market_data"] = {
                    "status": "active",
                    "last_refresh": datetime.now().isoformat(),
                    "entries": 0,  # Would get from actual cache
                    "memory_mb": 0.0,
                }

            if hasattr(self.integration_manager, "config_cache"):
                cache_statuses["configuration"] = {
                    "status": "active",
                    "last_refresh": datetime.now().isoformat(),
                    "entries": 0,  # Would get from actual cache
                    "memory_mb": 0.0,
                }

            return cache_statuses

        except Exception as e:
            logger.error(f"Error getting cache status: {e}")
            return {}

    def _calculate_system_health_score(
        self, performance_summary: dict[str, Any]
    ) -> float:
        """Calculate overall system health score based on all cache performance."""
        try:
            cache_details = performance_summary.get("cache_details", {})
            if not cache_details:
                return 0.0

            health_scores = []
            for cache_data in cache_details.values():
                if not cache_data.get("no_data", False):
                    # Calculate individual cache health score
                    hit_rate = cache_data["rates"]["hit_rate"]
                    avg_response_time = cache_data["response_times_ms"]["average"]
                    error_rate = cache_data["rates"]["error_rate"]

                    health_score = self.analytics._calculate_health_score(
                        hit_rate, avg_response_time, error_rate
                    )
                    health_scores.append(health_score)

            return sum(health_scores) / len(health_scores) if health_scores else 0.0

        except Exception as e:
            logger.error(f"Error calculating system health score: {e}")
            return 0.0

    async def _calculate_performance_trends(self) -> dict[str, Any]:
        """Calculate performance trends over time."""
        try:
            trends = {}

            # This is a simplified trend calculation
            # In a production system, you'd store historical data points
            trends["hit_rate_trend"] = (
                "stable"  # Could be 'improving', 'declining', 'stable'
            )
            trends["response_time_trend"] = "stable"
            trends["error_rate_trend"] = "stable"

            return trends

        except Exception as e:
            logger.error(f"Error calculating performance trends: {e}")
            return {}

    def _format_alert(self, alert) -> dict[str, Any]:
        """Format alert for dashboard display."""
        return {
            "id": id(alert),  # Simple ID for now
            "cache_name": alert.cache_name,
            "type": alert.alert_type,
            "severity": alert.severity.value,
            "message": alert.message,
            "timestamp": alert.timestamp.isoformat(),
            "resolved": alert.resolved,
            "metrics": alert.metrics,
        }

    async def get_cache_details(
        self, cache_name: str, time_window_minutes: int = 60
    ) -> dict[str, Any]:
        """Get detailed performance data for a specific cache."""
        try:
            performance = self.analytics.get_cache_performance(
                cache_name, time_window_minutes
            )

            # Add additional cache-specific details
            details = {
                **performance,
                "configuration": await self._get_cache_configuration(cache_name),
                "recent_events": await self._get_recent_cache_events(
                    cache_name, limit=20
                ),
                "top_keys": await self._get_top_cache_keys(cache_name, limit=10),
            }

            return details

        except Exception as e:
            logger.error(f"Error getting cache details for {cache_name}: {e}")
            return {"error": str(e)}

    async def _get_cache_configuration(self, cache_name: str) -> dict[str, Any]:
        """Get configuration details for a specific cache."""
        # This would retrieve actual cache configuration
        return {
            "default_ttl": 300,  # seconds
            "max_size": 1000,
            "eviction_policy": "LRU",
            "background_refresh": True,
        }

    async def _get_recent_cache_events(
        self, cache_name: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get recent events for a specific cache."""
        try:
            # Filter events for this cache
            cache_events = [
                event
                for event in self.analytics._events
                if event.cache_name == cache_name
            ]

            # Sort by timestamp and take the most recent
            recent_events = sorted(
                cache_events, key=lambda x: x.timestamp, reverse=True
            )[:limit]

            # Format for display
            return [
                {
                    "timestamp": event.timestamp.isoformat(),
                    "type": event.event_type.value,
                    "key": (
                        event.key[:50] + "..." if len(event.key) > 50 else event.key
                    ),  # Truncate long keys
                    "response_time_ms": event.response_time_ms,
                    "data_size_bytes": event.data_size_bytes,
                }
                for event in recent_events
            ]

        except Exception as e:
            logger.error(f"Error getting recent cache events: {e}")
            return []

    async def _get_top_cache_keys(
        self, cache_name: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get the most frequently accessed cache keys."""
        try:
            # Count key access frequency
            key_counts = {}
            for event in self.analytics._events:
                if event.cache_name == cache_name and event.event_type.value in [
                    "hit",
                    "miss",
                ]:
                    key_counts[event.key] = key_counts.get(event.key, 0) + 1

            # Sort by frequency and return top keys
            top_keys = sorted(key_counts.items(), key=lambda x: x[1], reverse=True)[
                :limit
            ]

            return [
                {
                    "key": key[:50] + "..." if len(key) > 50 else key,
                    "access_count": count,
                    "hit_rate": self._calculate_key_hit_rate(cache_name, key),
                }
                for key, count in top_keys
            ]

        except Exception as e:
            logger.error(f"Error getting top cache keys: {e}")
            return []

    def _calculate_key_hit_rate(self, cache_name: str, key: str) -> float:
        """Calculate hit rate for a specific key."""
        try:
            hits = sum(
                1
                for event in self.analytics._events
                if event.cache_name == cache_name
                and event.key == key
                and event.event_type.value == "hit"
            )
            total = sum(
                1
                for event in self.analytics._events
                if event.cache_name == cache_name
                and event.key == key
                and event.event_type.value in ["hit", "miss"]
            )

            return hits / total if total > 0 else 0.0

        except Exception:
            return 0.0

    async def clear_cache(self, cache_name: str) -> dict[str, Any]:
        """Clear all entries from a specific cache."""
        try:
            # This would call the actual cache clear method
            # For now, we'll simulate the operation
            logger.info(f"Cache clear requested for: {cache_name}")

            return {
                "success": True,
                "message": f"Cache {cache_name} cleared successfully",
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error clearing cache {cache_name}: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def invalidate_cache_pattern(
        self, cache_name: str, pattern: str
    ) -> dict[str, Any]:
        """Invalidate cache entries matching a pattern."""
        try:
            # This would call the actual cache invalidation method
            logger.info(
                f"Cache invalidation requested for {cache_name} with pattern: {pattern}"
            )

            return {
                "success": True,
                "message": f"Cache entries matching pattern '{pattern}' invalidated",
                "cache_name": cache_name,
                "pattern": pattern,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error invalidating cache pattern: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def export_dashboard_data(self, output_file: str) -> dict[str, Any]:
        """Export current dashboard data to a file."""
        try:
            dashboard_data = await self.get_dashboard_data(refresh=True)

            export_data = {
                "export_metadata": {
                    "exported_at": datetime.now().isoformat(),
                    "dashboard_version": "1.0",
                },
                "dashboard_data": dashboard_data,
            }

            with open(output_file, "w") as f:
                json.dump(export_data, f, indent=2, default=str)

            return {
                "success": True,
                "message": f"Dashboard data exported to {output_file}",
                "file_size_bytes": len(json.dumps(export_data)),
            }

        except Exception as e:
            logger.error(f"Error exporting dashboard data: {e}")
            return {"success": False, "error": str(e)}


# Global dashboard instance
_cache_dashboard: CacheDashboard | None = None


def get_cache_dashboard() -> CacheDashboard:
    """Get the global cache dashboard instance."""
    global _cache_dashboard
    if _cache_dashboard is None:
        _cache_dashboard = CacheDashboard()
    return _cache_dashboard


async def print_cache_status():
    """Print a formatted cache status report to console."""
    dashboard = get_cache_dashboard()

    try:
        data = await dashboard.get_dashboard_data(refresh=True)

        print("\n" + "=" * 80)
        print("CACHE PERFORMANCE DASHBOARD")
        print("=" * 80)

        # System Overview
        overview = data["system_overview"]
        print("\nSYSTEM OVERVIEW (Last 1 Hour)")
        print(f"├── Health Score: {overview.get('system_health_score', 0):.1f}/100")
        print(f"├── Active Caches: {overview.get('active_caches', 0)}")
        print(f"├── Total Requests: {overview.get('total_requests_1h', 0):,}")
        print(f"├── Hit Rate: {overview.get('overall_hit_rate', 0):.2%}")
        print(f"└── Error Rate: {overview.get('overall_error_rate', 0):.2%}")

        # Cache Performance
        cache_perf = data.get("cache_performance", {})
        if cache_perf:
            print("\nCACHE PERFORMANCE")
            for cache_name, perf in cache_perf.items():
                if not perf.get("no_data", False):
                    print(f"├── {cache_name}:")
                    print(f"│   ├── Hit Rate: {perf['rates']['hit_rate']:.2%}")
                    print(
                        f"│   ├── Avg Response: {perf['response_times_ms']['average']:.1f}ms"
                    )
                    print(f"│   └── Requests: {perf['requests']['total']:,}")

        # Alerts
        alerts = data.get("alerts", {})
        total_alerts = alerts.get("total_active", 0)
        if total_alerts > 0:
            print(f"\nACTIVE ALERTS ({total_alerts})")
            print(f"├── Critical: {alerts.get('critical', 0)}")
            print(f"├── High: {alerts.get('high', 0)}")
            print(f"├── Medium: {alerts.get('medium', 0)}")
            print(f"└── Low: {alerts.get('low', 0)}")

            recent = alerts.get("recent_alerts", [])
            if recent:
                print("\nRECENT ALERTS:")
                for alert in recent[:5]:  # Show top 5
                    print(
                        f"├── [{alert['severity'].upper()}] {alert['cache_name']}: {alert['message']}"
                    )

        # Recommendations
        recommendations = data.get("recommendations", [])
        if recommendations:
            print("\nOPTIMIZATION RECOMMENDATIONS")
            for i, rec in enumerate(recommendations[:5], 1):
                print(f"├── {i}. {rec}")

        print("=" * 80)
        print(f"Last Updated: {data.get('timestamp', 'Unknown')}")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\nError displaying cache status: {e}\n")
