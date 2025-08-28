"""
Connection pool monitoring and health check utilities.

Provides monitoring, alerting, and health checking for database connection pools.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .connection_pool import BaseConnectionPool

log = logging.getLogger("connection_monitor")


class PoolHealthStatus(Enum):
    """Connection pool health status levels."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class PoolAlert:
    """Connection pool alert information."""

    level: str
    message: str
    timestamp: datetime
    pool_type: str
    metric_name: str
    current_value: Any
    threshold_value: Any

    def to_dict(self) -> dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "level": self.level,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "pool_type": self.pool_type,
            "metric_name": self.metric_name,
            "current_value": self.current_value,
            "threshold_value": self.threshold_value,
        }


@dataclass
class HealthThresholds:
    """Health check thresholds for connection pool monitoring."""

    max_pool_utilization_warning: float = 0.7  # 70%
    max_pool_utilization_critical: float = 0.9  # 90%
    max_avg_query_time_warning_ms: float = 100.0
    max_avg_query_time_critical_ms: float = 500.0
    max_connection_errors_warning: int = 5
    max_connection_errors_critical: int = 20
    max_pool_full_events_warning: int = 3
    max_pool_full_events_critical: int = 10
    min_available_connections_warning: int = 1
    min_available_connections_critical: int = 0


class ConnectionPoolMonitor:
    """
    Monitor connection pool health and performance.

    Provides real-time monitoring, alerting, and health status tracking
    for database connection pools.
    """

    def __init__(
        self,
        pool: BaseConnectionPool,
        monitor_interval: float = 30.0,
        thresholds: HealthThresholds | None = None,
        alert_callback: Callable[[PoolAlert], None] | None = None,
    ):
        self.pool = pool
        self.monitor_interval = monitor_interval
        self.thresholds = thresholds or HealthThresholds()
        self.alert_callback = alert_callback or self._default_alert_handler

        self._monitoring = False
        self._monitor_task: asyncio.Task | None = None
        self._last_stats_snapshot: dict[str, Any] | None = None
        self._health_history: list[dict[str, Any]] = []
        self._alerts: list[PoolAlert] = []
        self._max_history_size = 100

    def _default_alert_handler(self, alert: PoolAlert) -> None:
        """Default alert handler that logs alerts."""
        level_map = {"warning": logging.WARNING, "critical": logging.CRITICAL}
        log_level = level_map.get(alert.level, logging.INFO)
        log.log(log_level, f"Pool Alert: {alert.message}")

    async def start_monitoring(self) -> None:
        """Start continuous monitoring of the connection pool."""
        if self._monitoring:
            log.warning("Connection pool monitoring already started")
            return

        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        log.info(
            f"Started connection pool monitoring (interval: {self.monitor_interval}s)"
        )

    async def stop_monitoring(self) -> None:
        """Stop connection pool monitoring."""
        if not self._monitoring:
            return

        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        log.info("Stopped connection pool monitoring")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._monitoring:
            try:
                await self._perform_health_check()
                await asyncio.sleep(self.monitor_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in connection pool monitoring: {e}")
                await asyncio.sleep(self.monitor_interval)

    async def _perform_health_check(self) -> None:
        """Perform comprehensive health check."""
        try:
            # Get current pool status
            current_status = await self.pool.get_pool_status()
            stats = current_status.get("stats", {})

            # Calculate derived metrics
            pool_utilization = self._calculate_pool_utilization(current_status)
            available_connections = self._calculate_available_connections(
                current_status
            )

            # Determine health status
            health_status = self._determine_health_status(
                current_status, pool_utilization
            )

            # Create health snapshot
            health_snapshot = {
                "timestamp": datetime.now(),
                "health_status": health_status.value,
                "pool_utilization": pool_utilization,
                "available_connections": available_connections,
                "stats": stats,
                "pool_info": current_status,
            }

            # Store history
            self._health_history.append(health_snapshot)
            if len(self._health_history) > self._max_history_size:
                self._health_history.pop(0)

            # Check for alerts
            await self._check_alerts(health_snapshot)

            # Store snapshot for comparison
            self._last_stats_snapshot = stats

        except Exception as e:
            log.error(f"Error performing health check: {e}")

    def _calculate_pool_utilization(self, status: dict[str, Any]) -> float:
        """Calculate pool utilization percentage."""
        stats = status.get("stats", {})
        connections_in_use = stats.get("current_connections_in_use", 0)
        max_size = status.get("max_size", 1)
        return connections_in_use / max_size if max_size > 0 else 0.0

    def _calculate_available_connections(self, status: dict[str, Any]) -> int:
        """Calculate number of available connections."""
        stats = status.get("stats", {})
        max_size = status.get("max_size", 0)
        connections_in_use = stats.get("current_connections_in_use", 0)
        return max(0, max_size - connections_in_use)

    def _determine_health_status(
        self, status: dict[str, Any], pool_utilization: float
    ) -> PoolHealthStatus:
        """Determine overall health status based on metrics."""
        stats = status.get("stats", {})

        # Check critical conditions
        if (
            pool_utilization >= self.thresholds.max_pool_utilization_critical
            or stats.get("avg_query_time_ms", 0)
            >= self.thresholds.max_avg_query_time_critical_ms
            or stats.get("connection_errors", 0)
            >= self.thresholds.max_connection_errors_critical
            or stats.get("pool_full_events", 0)
            >= self.thresholds.max_pool_full_events_critical
        ):
            return PoolHealthStatus.CRITICAL

        # Check warning conditions
        if (
            pool_utilization >= self.thresholds.max_pool_utilization_warning
            or stats.get("avg_query_time_ms", 0)
            >= self.thresholds.max_avg_query_time_warning_ms
            or stats.get("connection_errors", 0)
            >= self.thresholds.max_connection_errors_warning
            or stats.get("pool_full_events", 0)
            >= self.thresholds.max_pool_full_events_warning
        ):
            return PoolHealthStatus.WARNING

        return PoolHealthStatus.HEALTHY

    async def _check_alerts(self, health_snapshot: dict[str, Any]) -> None:
        """Check for alert conditions and generate alerts."""
        stats = health_snapshot["stats"]
        pool_info = health_snapshot["pool_info"]
        pool_type = pool_info.get("pool_type", "unknown")

        alerts_to_send = []

        # Pool utilization alerts
        utilization = health_snapshot["pool_utilization"]
        if utilization >= self.thresholds.max_pool_utilization_critical:
            alerts_to_send.append(
                PoolAlert(
                    level="critical",
                    message=f"Critical pool utilization: {utilization:.1%}",
                    timestamp=health_snapshot["timestamp"],
                    pool_type=pool_type,
                    metric_name="pool_utilization",
                    current_value=utilization,
                    threshold_value=self.thresholds.max_pool_utilization_critical,
                )
            )
        elif utilization >= self.thresholds.max_pool_utilization_warning:
            alerts_to_send.append(
                PoolAlert(
                    level="warning",
                    message=f"High pool utilization: {utilization:.1%}",
                    timestamp=health_snapshot["timestamp"],
                    pool_type=pool_type,
                    metric_name="pool_utilization",
                    current_value=utilization,
                    threshold_value=self.thresholds.max_pool_utilization_warning,
                )
            )

        # Query time alerts
        avg_query_time = stats.get("avg_query_time_ms", 0)
        if avg_query_time >= self.thresholds.max_avg_query_time_critical_ms:
            alerts_to_send.append(
                PoolAlert(
                    level="critical",
                    message=f"Critical query response time: {avg_query_time:.1f}ms",
                    timestamp=health_snapshot["timestamp"],
                    pool_type=pool_type,
                    metric_name="avg_query_time_ms",
                    current_value=avg_query_time,
                    threshold_value=self.thresholds.max_avg_query_time_critical_ms,
                )
            )
        elif avg_query_time >= self.thresholds.max_avg_query_time_warning_ms:
            alerts_to_send.append(
                PoolAlert(
                    level="warning",
                    message=f"Slow query response time: {avg_query_time:.1f}ms",
                    timestamp=health_snapshot["timestamp"],
                    pool_type=pool_type,
                    metric_name="avg_query_time_ms",
                    current_value=avg_query_time,
                    threshold_value=self.thresholds.max_avg_query_time_warning_ms,
                )
            )

        # Connection error alerts
        connection_errors = stats.get("connection_errors", 0)
        if (
            self._last_stats_snapshot
            and connection_errors
            > self._last_stats_snapshot.get("connection_errors", 0)
        ):
            if connection_errors >= self.thresholds.max_connection_errors_critical:
                alerts_to_send.append(
                    PoolAlert(
                        level="critical",
                        message=f"Critical connection errors: {connection_errors}",
                        timestamp=health_snapshot["timestamp"],
                        pool_type=pool_type,
                        metric_name="connection_errors",
                        current_value=connection_errors,
                        threshold_value=self.thresholds.max_connection_errors_critical,
                    )
                )
            elif connection_errors >= self.thresholds.max_connection_errors_warning:
                alerts_to_send.append(
                    PoolAlert(
                        level="warning",
                        message=f"Elevated connection errors: {connection_errors}",
                        timestamp=health_snapshot["timestamp"],
                        pool_type=pool_type,
                        metric_name="connection_errors",
                        current_value=connection_errors,
                        threshold_value=self.thresholds.max_connection_errors_warning,
                    )
                )

        # Pool full event alerts
        pool_full_events = stats.get("pool_full_events", 0)
        if (
            self._last_stats_snapshot
            and pool_full_events > self._last_stats_snapshot.get("pool_full_events", 0)
        ):
            if pool_full_events >= self.thresholds.max_pool_full_events_critical:
                alerts_to_send.append(
                    PoolAlert(
                        level="critical",
                        message=f"Critical pool full events: {pool_full_events}",
                        timestamp=health_snapshot["timestamp"],
                        pool_type=pool_type,
                        metric_name="pool_full_events",
                        current_value=pool_full_events,
                        threshold_value=self.thresholds.max_pool_full_events_critical,
                    )
                )
            elif pool_full_events >= self.thresholds.max_pool_full_events_warning:
                alerts_to_send.append(
                    PoolAlert(
                        level="warning",
                        message=f"Pool full events detected: {pool_full_events}",
                        timestamp=health_snapshot["timestamp"],
                        pool_type=pool_type,
                        metric_name="pool_full_events",
                        current_value=pool_full_events,
                        threshold_value=self.thresholds.max_pool_full_events_warning,
                    )
                )

        # Send alerts
        for alert in alerts_to_send:
            self._alerts.append(alert)
            if self.alert_callback:
                try:
                    self.alert_callback(alert)
                except Exception as e:
                    log.error(f"Error in alert callback: {e}")

        # Limit alert history
        if len(self._alerts) > 200:
            self._alerts = self._alerts[-100:]  # Keep last 100 alerts

    def get_current_health(self) -> dict[str, Any]:
        """Get current health status."""
        if not self._health_history:
            return {"status": "no_data"}

        latest = self._health_history[-1]
        return {
            "status": latest["health_status"],
            "timestamp": latest["timestamp"].isoformat(),
            "pool_utilization": latest["pool_utilization"],
            "available_connections": latest["available_connections"],
            "stats": latest["stats"],
        }

    def get_health_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get health history."""
        return [
            {
                **entry,
                "timestamp": entry["timestamp"].isoformat(),
            }
            for entry in self._health_history[-limit:]
        ]

    def get_recent_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent alerts."""
        return [alert.to_dict() for alert in self._alerts[-limit:]]

    def clear_alerts(self) -> None:
        """Clear alert history."""
        self._alerts.clear()

    async def force_health_check(self) -> dict[str, Any]:
        """Force immediate health check and return results."""
        await self._perform_health_check()
        return self.get_current_health()

    def get_summary_stats(self) -> dict[str, Any]:
        """Get summary statistics over the monitoring period."""
        if not self._health_history:
            return {"status": "no_data"}

        # Calculate averages over recent history
        recent_history = self._health_history[-20:]  # Last 20 readings

        avg_utilization = sum(h["pool_utilization"] for h in recent_history) / len(
            recent_history
        )
        min_available = min(h["available_connections"] for h in recent_history)
        max_utilization = max(h["pool_utilization"] for h in recent_history)

        total_alerts = len(self._alerts)
        critical_alerts = sum(1 for alert in self._alerts if alert.level == "critical")
        warning_alerts = sum(1 for alert in self._alerts if alert.level == "warning")

        return {
            "monitoring_duration_hours": (
                (datetime.now() - self._health_history[0]["timestamp"]).total_seconds()
                / 3600
                if self._health_history
                else 0
            ),
            "avg_pool_utilization": avg_utilization,
            "max_pool_utilization": max_utilization,
            "min_available_connections": min_available,
            "total_health_checks": len(self._health_history),
            "total_alerts": total_alerts,
            "critical_alerts": critical_alerts,
            "warning_alerts": warning_alerts,
            "current_health": self.get_current_health()["status"],
        }
