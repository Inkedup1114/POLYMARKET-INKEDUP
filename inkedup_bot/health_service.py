"""
Centralized Health Check Service for InkedUp Trading Bot.

This module provides a unified health check service that integrates all system
components and provides standardized health monitoring interfaces for operations,
monitoring systems, and deployment environments.

Key Features:
    - Centralized health status aggregation
    - Standardized health check interfaces
    - Support for external monitoring integration  
    - Kubernetes-ready liveness and readiness probes
    - Component-specific health checks
    - Automated health status reporting
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import BotConfig
from .monitoring.health import (
    ComponentHealth,
    DatabaseHealthCheck,
    HealthStatus,
    OrderClientHealthCheck,
    SystemHealth,
    SystemResourceHealthCheck,
    WebSocketHealthCheck,
)

log = logging.getLogger("health_service")


class OverallHealthStatus(Enum):
    """Overall system health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class HealthCheckService:
    """
    Centralized health check service for the trading bot.

    Provides unified health monitoring across all system components with
    support for external monitoring systems and operational tools.
    """

    def __init__(self, config: BotConfig = None):
        """Initialize health check service."""
        self.config = config or BotConfig()
        self.system_health = SystemHealth()
        self.health_history = []
        self.max_history_size = 100
        self.service_start_time = datetime.now()

        # Component references (set during bot initialization)
        self.database_manager = None
        self.order_client = None
        self.ws_manager = None
        self.scanner = None
        self.trading_engine = None

        log.info("Health check service initialized")

    def register_components(self, **components):
        """Register system components for health monitoring."""
        self.database_manager = components.get("database_manager")
        self.order_client = components.get("order_client")
        self.ws_manager = components.get("ws_manager")
        self.scanner = components.get("scanner")
        self.trading_engine = components.get("trading_engine")

        self._setup_component_health_checks()
        log.info(f"Registered {len(components)} components for health monitoring")

    def _setup_component_health_checks(self):
        """Setup health checks for all registered components."""

        # Database health checks
        if self.database_manager:
            database_component = ComponentHealth("database")

            # Add database connectivity check
            if hasattr(self.database_manager, "db_path"):
                db_path = str(self.database_manager.db_path)
                database_component.add_health_check(DatabaseHealthCheck(db_path))

            self.system_health.add_component(database_component)

        # Order client health checks
        if self.order_client:
            order_client_component = ComponentHealth("order_client")
            order_client_component.add_health_check(
                OrderClientHealthCheck(self.order_client)
            )
            self.system_health.add_component(order_client_component)

        # WebSocket health checks
        if self.ws_manager:
            websocket_component = ComponentHealth("websocket")
            websocket_component.add_health_check(WebSocketHealthCheck(self.ws_manager))
            self.system_health.add_component(websocket_component)

        # System resources health checks
        system_component = ComponentHealth("system_resources")
        system_component.add_health_check(SystemResourceHealthCheck())
        self.system_health.add_component(system_component)

    async def get_system_health_status(
        self, include_details: bool = True
    ) -> Dict[str, Any]:
        """
        Get comprehensive system health status.

        Args:
            include_details: Whether to include detailed component information

        Returns:
            Dictionary containing system health status
        """
        try:
            health_result = await self.system_health.get_system_health()

            # Determine overall status
            overall_status = self._determine_overall_status(health_result)

            # Build response
            response = {
                "service": "InkedUp Trading Bot",
                "overall_status": overall_status.value,
                "timestamp": datetime.now().isoformat(),
                "uptime_seconds": (
                    datetime.now() - self.service_start_time
                ).total_seconds(),
                "system_start_time": self.service_start_time.isoformat(),
                "summary": health_result.get("summary", {}),
            }

            if include_details:
                response["components"] = health_result.get("components", {})
            else:
                # Just include component status summary
                response["component_status"] = {
                    name: comp.get("overall_status", "unknown")
                    for name, comp in health_result.get("components", {}).items()
                }

            # Store in history
            self._store_health_result(response)

            return response

        except Exception as e:
            log.error(f"Failed to get system health status: {e}")
            return {
                "service": "InkedUp Trading Bot",
                "overall_status": OverallHealthStatus.UNKNOWN.value,
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }

    def _determine_overall_status(
        self, health_result: Dict[str, Any]
    ) -> OverallHealthStatus:
        """Determine overall system status from component health results."""
        summary = health_result.get("summary", {})

        unhealthy_count = summary.get("unhealthy_components", 0)
        warning_count = summary.get("warning_components", 0)
        healthy_count = summary.get("healthy_components", 0)
        total_count = summary.get("total_components", 0)

        if total_count == 0:
            return OverallHealthStatus.UNKNOWN

        # System is unhealthy if any critical component is unhealthy
        critical_components = ["database", "order_client"]
        for comp_name, comp_data in health_result.get("components", {}).items():
            if (
                comp_name in critical_components
                and comp_data.get("overall_status") == "unhealthy"
            ):
                return OverallHealthStatus.UNHEALTHY

        # System is unhealthy if majority of components are unhealthy
        if unhealthy_count > total_count / 2:
            return OverallHealthStatus.UNHEALTHY

        # System is degraded if any component has warnings or some are unhealthy
        if warning_count > 0 or unhealthy_count > 0:
            return OverallHealthStatus.DEGRADED

        return OverallHealthStatus.HEALTHY

    def _store_health_result(self, health_result: Dict[str, Any]):
        """Store health result in history."""
        self.health_history.append(health_result)

        # Trim history if too large
        if len(self.health_history) > self.max_history_size:
            self.health_history = self.health_history[-self.max_history_size :]

    async def is_healthy(self) -> bool:
        """Simple boolean health check."""
        try:
            status = await self.get_system_health_status(include_details=False)
            return status.get("overall_status") in ["healthy", "degraded"]
        except Exception:
            return False

    async def is_ready(self) -> bool:
        """
        Check if system is ready to serve traffic.

        Returns True if critical components are operational.
        """
        try:
            status = await self.get_system_health_status(include_details=True)
            components = status.get("components", {})

            # Check critical components
            critical_components = ["database", "order_client"]
            for comp_name in critical_components:
                comp_status = components.get(comp_name, {}).get(
                    "overall_status", "unknown"
                )
                if comp_status == "unhealthy":
                    return False

            return True
        except Exception:
            return False

    async def get_liveness_status(self) -> Dict[str, Any]:
        """
        Get liveness probe status for Kubernetes/container orchestration.

        Returns basic application liveness information.
        """
        return {
            "alive": True,
            "service": "InkedUp Trading Bot",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": (
                datetime.now() - self.service_start_time
            ).total_seconds(),
        }

    async def get_readiness_status(self) -> Dict[str, Any]:
        """
        Get readiness probe status for Kubernetes/container orchestration.

        Returns readiness information based on critical component health.
        """
        try:
            ready = await self.is_ready()
            status = await self.get_system_health_status(include_details=False)

            result = {
                "ready": ready,
                "service": "InkedUp Trading Bot",
                "timestamp": datetime.now().isoformat(),
                "overall_status": status.get("overall_status", "unknown"),
            }

            if not ready:
                # Include information about why not ready
                components = status.get("component_status", {})
                unhealthy_components = [
                    name for name, status in components.items() if status == "unhealthy"
                ]
                result["unhealthy_components"] = unhealthy_components

            return result

        except Exception as e:
            return {
                "ready": False,
                "service": "InkedUp Trading Bot",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }

    def get_health_trends(self, hours: int = 1) -> Dict[str, Any]:
        """
        Get health trends over time.

        Args:
            hours: Number of hours to analyze

        Returns:
            Health trend analysis
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # Filter history to requested timeframe
        recent_history = [
            result
            for result in self.health_history
            if datetime.fromisoformat(result["timestamp"]) > cutoff_time
        ]

        if not recent_history:
            return {
                "analysis_period_hours": hours,
                "data_points": 0,
                "trend": "insufficient_data",
            }

        # Analyze trends
        status_counts = {"healthy": 0, "degraded": 0, "unhealthy": 0, "unknown": 0}
        for result in recent_history:
            status = result.get("overall_status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        total_points = len(recent_history)

        return {
            "analysis_period_hours": hours,
            "data_points": total_points,
            "status_distribution": {
                status: {
                    "count": count,
                    "percentage": round((count / total_points) * 100, 1),
                }
                for status, count in status_counts.items()
            },
            "latest_status": recent_history[-1].get("overall_status", "unknown"),
            "trend": self._calculate_trend(recent_history),
        }

    def _calculate_trend(self, history: List[Dict[str, Any]]) -> str:
        """Calculate health trend from historical data."""
        if len(history) < 2:
            return "stable"

        # Simple trend analysis based on recent vs earlier status
        recent_third = history[-len(history) // 3 :]
        earlier_third = history[: len(history) // 3]

        recent_unhealthy = sum(
            1 for h in recent_third if h.get("overall_status") == "unhealthy"
        )
        earlier_unhealthy = sum(
            1 for h in earlier_third if h.get("overall_status") == "unhealthy"
        )

        recent_healthy = sum(
            1 for h in recent_third if h.get("overall_status") == "healthy"
        )
        earlier_healthy = sum(
            1 for h in earlier_third if h.get("overall_status") == "healthy"
        )

        if recent_unhealthy > earlier_unhealthy:
            return "deteriorating"
        elif recent_healthy > earlier_healthy:
            return "improving"
        else:
            return "stable"

    def export_health_status(
        self, format: str = "json", output_path: Optional[Path] = None
    ) -> str:
        """
        Export health status to file or return as string.

        Args:
            format: Export format ("json", "text")
            output_path: Optional file path to save export

        Returns:
            Exported health status as string
        """
        try:
            if format.lower() == "json":
                status = asyncio.run(
                    self.get_system_health_status(include_details=True)
                )
                content = json.dumps(status, indent=2)
            else:
                # Text format
                status = asyncio.run(
                    self.get_system_health_status(include_details=True)
                )
                lines = []
                lines.append(f"InkedUp Trading Bot - Health Status Report")
                lines.append(f"Generated: {status['timestamp']}")
                lines.append(f"Overall Status: {status['overall_status'].upper()}")
                lines.append(f"Uptime: {status['uptime_seconds']:.0f} seconds")
                lines.append("")

                # Component summary
                lines.append("Component Status:")
                for comp_name, comp_data in status.get("components", {}).items():
                    comp_status = comp_data.get("overall_status", "unknown")
                    lines.append(f"  {comp_name}: {comp_status}")

                content = "\n".join(lines)

            if output_path:
                with open(output_path, "w") as f:
                    f.write(content)
                log.info(f"Health status exported to {output_path}")

            return content

        except Exception as e:
            log.error(f"Failed to export health status: {e}")
            return f"Export failed: {e}"

    async def run_health_diagnostics(self) -> Dict[str, Any]:
        """
        Run comprehensive health diagnostics.

        Returns detailed diagnostic information for troubleshooting.
        """
        try:
            # Get full health status
            health_status = await self.get_system_health_status(include_details=True)

            # Add diagnostic information
            diagnostics = {
                "health_status": health_status,
                "health_trends": self.get_health_trends(hours=1),
                "service_info": {
                    "start_time": self.service_start_time.isoformat(),
                    "uptime_hours": (
                        datetime.now() - self.service_start_time
                    ).total_seconds()
                    / 3600,
                    "health_checks_performed": len(self.health_history),
                    "components_registered": len(self.system_health.components),
                },
                "recommendations": self._generate_health_recommendations(health_status),
            }

            return diagnostics

        except Exception as e:
            log.error(f"Health diagnostics failed: {e}")
            return {"error": str(e), "timestamp": datetime.now().isoformat()}

    def _generate_health_recommendations(
        self, health_status: Dict[str, Any]
    ) -> List[str]:
        """Generate health improvement recommendations."""
        recommendations = []

        components = health_status.get("components", {})

        for comp_name, comp_data in components.items():
            comp_status = comp_data.get("overall_status", "unknown")

            if comp_status == "unhealthy":
                if comp_name == "database":
                    recommendations.append("Check database connectivity and disk space")
                elif comp_name == "order_client":
                    recommendations.append(
                        "Verify API credentials and network connectivity"
                    )
                elif comp_name == "websocket":
                    recommendations.append(
                        "Check WebSocket connection and authentication"
                    )
                elif comp_name == "system_resources":
                    recommendations.append(
                        "Monitor CPU and memory usage, consider scaling"
                    )

            elif comp_status == "warning":
                if comp_name == "system_resources":
                    recommendations.append("Monitor system resource usage trends")
                else:
                    recommendations.append(
                        f"Monitor {comp_name} component for potential issues"
                    )

        if not recommendations:
            recommendations.append("All systems operating normally")

        return recommendations


# Global health service instance
_health_service = None


def get_health_service(config: BotConfig = None) -> HealthCheckService:
    """Get or create global health service instance."""
    global _health_service
    if _health_service is None:
        _health_service = HealthCheckService(config)
    return _health_service


def setup_health_service(config: BotConfig = None, **components) -> HealthCheckService:
    """Setup health service with configuration and components."""
    global _health_service
    _health_service = HealthCheckService(config)
    if components:
        _health_service.register_components(**components)
    return _health_service


# CLI-friendly functions
async def quick_health_check() -> bool:
    """Quick boolean health check for CLI usage."""
    health_service = get_health_service()
    return await health_service.is_healthy()


async def detailed_health_status() -> Dict[str, Any]:
    """Detailed health status for CLI usage."""
    health_service = get_health_service()
    return await health_service.get_system_health_status()


async def health_diagnostics() -> Dict[str, Any]:
    """Full health diagnostics for CLI usage."""
    health_service = get_health_service()
    return await health_service.run_health_diagnostics()
