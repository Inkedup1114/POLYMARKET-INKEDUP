"""
Health check system for comprehensive component monitoring.

This module provides health checks for all system components including
database connections, WebSocket connections, order client, and system resources.
"""

import logging
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import psutil

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    WARNING = "warning"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a health check operation."""

    status: HealthStatus
    message: str
    details: dict[str, Any] | None = None
    timestamp: datetime | None = None
    duration_ms: float | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class HealthCheck(ABC):
    """Base class for all health checks."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.last_result: HealthCheckResult | None = None
        self.check_count = 0
        self.failure_count = 0

    @abstractmethod
    async def check(self) -> HealthCheckResult:
        """Perform the health check."""
        pass

    async def run_check(self) -> HealthCheckResult:
        """Run the health check with timing and error handling."""
        start_time = time.time()
        self.check_count += 1

        try:
            result = await self.check()
            result.duration_ms = (time.time() - start_time) * 1000

            if result.status != HealthStatus.HEALTHY:
                self.failure_count += 1

            self.last_result = result
            return result

        except Exception as e:
            self.failure_count += 1
            duration_ms = (time.time() - start_time) * 1000

            result = HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                details={"error_type": type(e).__name__, "error": str(e)},
                duration_ms=duration_ms,
            )

            self.last_result = result
            logger.error(f"Health check '{self.name}' failed: {e}")
            return result

    def get_failure_rate(self) -> float:
        """Get the failure rate as a percentage."""
        if self.check_count == 0:
            return 0.0
        return (self.failure_count / self.check_count) * 100


class DatabaseHealthCheck(HealthCheck):
    """Health check for database connectivity and performance."""

    def __init__(self, database_path: str, name: str = "database"):
        super().__init__(name, f"Database health check for {database_path}")
        self.database_path = database_path

    async def check(self) -> HealthCheckResult:
        """Check database connectivity and basic operations."""
        try:
            # Check if database file exists
            db_path = Path(self.database_path)
            if not db_path.exists():
                return HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    message="Database file does not exist",
                    details={"path": str(db_path)},
                )

            # Check file permissions and size
            db_stats = db_path.stat()
            db_size_mb = db_stats.st_size / (1024 * 1024)

            # Test database connectivity
            connection_start = time.time()
            conn = sqlite3.connect(self.database_path, timeout=5.0)
            connection_time_ms = (time.time() - connection_start) * 1000

            try:
                # Test basic operations
                cursor = conn.cursor()

                # Test query execution
                query_start = time.time()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                query_time_ms = (time.time() - query_start) * 1000

                if result[0] != 1:
                    return HealthCheckResult(
                        status=HealthStatus.UNHEALTHY,
                        message="Database query returned unexpected result",
                    )

                # Get database information
                cursor.execute("PRAGMA database_list")
                db_info = cursor.fetchall()

                cursor.execute("PRAGMA table_list")
                tables = cursor.fetchall()
                table_count = len(tables)

                # Check for common issues
                warnings = []
                status = HealthStatus.HEALTHY

                if connection_time_ms > 1000:
                    warnings.append(f"Slow connection time: {connection_time_ms:.2f}ms")
                    status = HealthStatus.WARNING

                if query_time_ms > 100:
                    warnings.append(f"Slow query time: {query_time_ms:.2f}ms")
                    status = HealthStatus.WARNING

                if db_size_mb > 1000:  # Warn if database is over 1GB
                    warnings.append(f"Large database size: {db_size_mb:.2f}MB")
                    status = HealthStatus.WARNING

                message = "Database is healthy"
                if warnings:
                    message += f" (warnings: {'; '.join(warnings)})"

                return HealthCheckResult(
                    status=status,
                    message=message,
                    details={
                        "database_path": self.database_path,
                        "size_mb": round(db_size_mb, 2),
                        "table_count": table_count,
                        "connection_time_ms": round(connection_time_ms, 2),
                        "query_time_ms": round(query_time_ms, 2),
                        "database_info": db_info,
                        "warnings": warnings,
                    },
                )

            finally:
                conn.close()

        except sqlite3.OperationalError as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Database operational error: {str(e)}",
                details={"error_type": "OperationalError", "error": str(e)},
            )

        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Database health check failed: {str(e)}",
                details={"error_type": type(e).__name__, "error": str(e)},
            )


class WebSocketHealthCheck(HealthCheck):
    """Health check for WebSocket connection status."""

    def __init__(self, ws_manager, name: str = "websocket"):
        super().__init__(name, "WebSocket connection health check")
        self.ws_manager = ws_manager

    async def check(self) -> HealthCheckResult:
        """Check WebSocket connection health."""
        try:
            if not hasattr(self.ws_manager, "connection_state"):
                return HealthCheckResult(
                    status=HealthStatus.UNKNOWN,
                    message="WebSocket manager does not support health checks",
                )

            # Get connection metrics if available
            metrics = {}
            if hasattr(self.ws_manager, "get_connection_metrics"):
                try:
                    metrics = self.ws_manager.get_connection_metrics()
                except Exception as e:
                    logger.warning(f"Failed to get WebSocket metrics: {e}")

            connection_state = getattr(self.ws_manager, "connection_state", "unknown")
            is_running = getattr(self.ws_manager, "is_running", False)

            # Determine status based on connection state
            if connection_state == "connected" and is_running:
                status = HealthStatus.HEALTHY
                message = "WebSocket connection is healthy"
            elif connection_state == "connecting" or connection_state == "reconnecting":
                status = HealthStatus.WARNING
                message = f"WebSocket is in {connection_state} state"
            elif connection_state == "failed" or not is_running:
                status = HealthStatus.UNHEALTHY
                message = f"WebSocket connection is {connection_state}"
            else:
                status = HealthStatus.WARNING
                message = f"WebSocket connection state: {connection_state}"

            # Add warnings based on metrics
            warnings = []
            if metrics:
                # Check reconnection rate
                total_connections = metrics.get("metrics", {}).get(
                    "total_connections", 0
                )
                failed_connections = metrics.get("metrics", {}).get(
                    "failed_connections", 0
                )
                if total_connections > 0:
                    failure_rate = (failed_connections / total_connections) * 100
                    if failure_rate > 20:
                        warnings.append(
                            f"High connection failure rate: {failure_rate:.1f}%"
                        )
                        if status == HealthStatus.HEALTHY:
                            status = HealthStatus.WARNING

                # Check heartbeat failures
                heartbeat_failures = metrics.get("metrics", {}).get(
                    "heartbeat_failures", 0
                )
                if heartbeat_failures > 5:
                    warnings.append(f"Recent heartbeat failures: {heartbeat_failures}")
                    if status == HealthStatus.HEALTHY:
                        status = HealthStatus.WARNING

            if warnings:
                message += f" (warnings: {'; '.join(warnings)})"

            return HealthCheckResult(
                status=status,
                message=message,
                details={
                    "connection_state": str(connection_state),
                    "is_running": is_running,
                    "metrics": metrics,
                    "warnings": warnings,
                },
            )

        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"WebSocket health check failed: {str(e)}",
                details={"error_type": type(e).__name__, "error": str(e)},
            )


class OrderClientHealthCheck(HealthCheck):
    """Health check for order client functionality."""

    def __init__(self, order_client, name: str = "order_client"):
        super().__init__(name, "Order client health check")
        self.order_client = order_client

    async def check(self) -> HealthCheckResult:
        """Check order client health and functionality."""
        try:
            # Check if client is initialized and has required attributes
            if not self.order_client:
                return HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    message="Order client is not initialized",
                )

            # Check client ready state
            client_ready = getattr(self.order_client, "client_ready", False)

            # Get exception statistics if available
            exception_stats = {}
            if hasattr(self.order_client, "get_exception_statistics"):
                try:
                    exception_stats = self.order_client.get_exception_statistics()
                except Exception as e:
                    logger.warning(f"Failed to get order client exception stats: {e}")

            # Get recent exception details if available
            recent_exceptions = []
            if hasattr(self.order_client, "get_recent_exception_details"):
                try:
                    recent_exceptions = self.order_client.get_recent_exception_details(
                        60
                    )
                except Exception as e:
                    logger.warning(f"Failed to get recent exceptions: {e}")

            # Determine health status
            status = HealthStatus.HEALTHY
            warnings = []

            if not client_ready:
                status = HealthStatus.WARNING
                warnings.append("Order client not ready")

            # Check exception rates
            if exception_stats:
                recent_1h = exception_stats.get("recent_exceptions_1h", 0)
                if recent_1h > 10:
                    warnings.append(
                        f"High exception rate: {recent_1h} exceptions in last hour"
                    )
                    if status == HealthStatus.HEALTHY:
                        status = HealthStatus.WARNING

                frequent_exceptions = exception_stats.get("frequent_exceptions", {})
                if frequent_exceptions:
                    for exc_type, count in frequent_exceptions.items():
                        if count > 5:
                            warnings.append(f"Frequent {exc_type}: {count} occurrences")
                            if status == HealthStatus.HEALTHY:
                                status = HealthStatus.WARNING

            # Check for critical recent exceptions
            critical_exceptions = [
                exc
                for exc in recent_exceptions
                if exc.get("exception_type")
                in ["ConnectionError", "TimeoutError", "AuthenticationError"]
            ]

            if critical_exceptions:
                status = HealthStatus.WARNING
                warnings.append(
                    f"{len(critical_exceptions)} critical exceptions in last hour"
                )

            message = "Order client is healthy"
            if status == HealthStatus.WARNING:
                message = "Order client has warnings"
            elif status == HealthStatus.UNHEALTHY:
                message = "Order client is unhealthy"

            if warnings:
                message += f" ({'; '.join(warnings)})"

            return HealthCheckResult(
                status=status,
                message=message,
                details={
                    "client_ready": client_ready,
                    "exception_stats": exception_stats,
                    "recent_critical_exceptions": len(critical_exceptions),
                    "warnings": warnings,
                },
            )

        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Order client health check failed: {str(e)}",
                details={"error_type": type(e).__name__, "error": str(e)},
            )


class SystemResourceHealthCheck(HealthCheck):
    """Health check for system resources (CPU, memory, disk)."""

    def __init__(self, name: str = "system_resources"):
        super().__init__(name, "System resource health check")

    async def check(self) -> HealthCheckResult:
        """Check system resource utilization."""
        try:
            # Get CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)

            # Get memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available_gb = memory.available / (1024**3)

            # Get disk usage for current directory
            disk = psutil.disk_usage(".")
            disk_percent = (disk.used / disk.total) * 100
            disk_free_gb = disk.free / (1024**3)

            # Get process-specific information
            process = psutil.Process()
            process_memory_mb = process.memory_info().rss / (1024**2)
            process_cpu_percent = process.cpu_percent()

            # Check network connections
            connections = psutil.net_connections()
            established_connections = len(
                [c for c in connections if c.status == "ESTABLISHED"]
            )

            # Determine health status
            status = HealthStatus.HEALTHY
            warnings = []

            # CPU checks
            if cpu_percent > 90:
                status = HealthStatus.UNHEALTHY
                warnings.append(f"Critical CPU usage: {cpu_percent:.1f}%")
            elif cpu_percent > 70:
                status = HealthStatus.WARNING
                warnings.append(f"High CPU usage: {cpu_percent:.1f}%")

            # Memory checks
            if memory_percent > 95:
                status = HealthStatus.UNHEALTHY
                warnings.append(f"Critical memory usage: {memory_percent:.1f}%")
            elif memory_percent > 80:
                if status == HealthStatus.HEALTHY:
                    status = HealthStatus.WARNING
                warnings.append(f"High memory usage: {memory_percent:.1f}%")

            # Disk space checks
            if disk_percent > 95:
                status = HealthStatus.UNHEALTHY
                warnings.append(f"Critical disk usage: {disk_percent:.1f}%")
            elif disk_percent > 85:
                if status == HealthStatus.HEALTHY:
                    status = HealthStatus.WARNING
                warnings.append(f"High disk usage: {disk_percent:.1f}%")

            # Process-specific checks
            if process_memory_mb > 1000:  # 1GB
                if status == HealthStatus.HEALTHY:
                    status = HealthStatus.WARNING
                warnings.append(f"High process memory usage: {process_memory_mb:.1f}MB")

            message = "System resources are healthy"
            if warnings:
                message = f"System resources have issues: {'; '.join(warnings)}"

            return HealthCheckResult(
                status=status,
                message=message,
                details={
                    "cpu_percent": round(cpu_percent, 1),
                    "memory_percent": round(memory_percent, 1),
                    "memory_available_gb": round(memory_available_gb, 2),
                    "disk_percent": round(disk_percent, 1),
                    "disk_free_gb": round(disk_free_gb, 2),
                    "process_memory_mb": round(process_memory_mb, 1),
                    "process_cpu_percent": round(process_cpu_percent, 1),
                    "established_connections": established_connections,
                    "warnings": warnings,
                },
            )

        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"System resource health check failed: {str(e)}",
                details={"error_type": type(e).__name__, "error": str(e)},
            )


class ComponentHealth:
    """Aggregated health status for a component."""

    def __init__(self, name: str):
        self.name = name
        self.health_checks: list[HealthCheck] = []
        self.last_check_time: datetime | None = None
        self.overall_status = HealthStatus.UNKNOWN

    def add_health_check(self, health_check: HealthCheck):
        """Add a health check to this component."""
        self.health_checks.append(health_check)

    async def run_all_checks(self) -> dict[str, Any]:
        """Run all health checks for this component."""
        results = {
            "component": self.name,
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "checks": {},
        }

        overall_status = HealthStatus.HEALTHY

        for health_check in self.health_checks:
            try:
                result = await health_check.run_check()
                results["checks"][health_check.name] = {
                    "status": result.status.value,
                    "message": result.message,
                    "details": result.details,
                    "duration_ms": result.duration_ms,
                    "failure_rate": health_check.get_failure_rate(),
                }

                # Update overall status
                if result.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif (
                    result.status == HealthStatus.WARNING
                    and overall_status == HealthStatus.HEALTHY
                ):
                    overall_status = HealthStatus.WARNING

            except Exception as e:
                logger.error(f"Health check '{health_check.name}' failed: {e}")
                results["checks"][health_check.name] = {
                    "status": "unhealthy",
                    "message": f"Check execution failed: {str(e)}",
                    "error": str(e),
                }
                overall_status = HealthStatus.UNHEALTHY

        results["overall_status"] = overall_status.value
        self.overall_status = overall_status
        self.last_check_time = datetime.now()

        return results


class SystemHealth:
    """System-wide health monitoring."""

    def __init__(self):
        self.components: dict[str, ComponentHealth] = {}
        self.system_start_time = datetime.now()

    def add_component(self, component: ComponentHealth):
        """Add a component to system health monitoring."""
        self.components[component.name] = component

    async def get_system_health(self) -> dict[str, Any]:
        """Get comprehensive system health status."""
        system_health = {
            "timestamp": datetime.now().isoformat(),
            "system_start_time": self.system_start_time.isoformat(),
            "uptime_seconds": (datetime.now() - self.system_start_time).total_seconds(),
            "overall_status": "healthy",
            "components": {},
            "summary": {
                "total_components": len(self.components),
                "healthy_components": 0,
                "warning_components": 0,
                "unhealthy_components": 0,
                "unknown_components": 0,
            },
        }

        overall_status = HealthStatus.HEALTHY

        for name, component in self.components.items():
            try:
                component_result = await component.run_all_checks()
                system_health["components"][name] = component_result

                # Update summary counts
                status = component_result["overall_status"]
                if status == "healthy":
                    system_health["summary"]["healthy_components"] += 1
                elif status == "warning":
                    system_health["summary"]["warning_components"] += 1
                    if overall_status == HealthStatus.HEALTHY:
                        overall_status = HealthStatus.WARNING
                elif status == "unhealthy":
                    system_health["summary"]["unhealthy_components"] += 1
                    overall_status = HealthStatus.UNHEALTHY
                else:
                    system_health["summary"]["unknown_components"] += 1
                    if overall_status == HealthStatus.HEALTHY:
                        overall_status = HealthStatus.WARNING

            except Exception as e:
                logger.error(f"Component health check failed for '{name}': {e}")
                system_health["components"][name] = {
                    "component": name,
                    "overall_status": "unhealthy",
                    "error": str(e),
                }
                system_health["summary"]["unhealthy_components"] += 1
                overall_status = HealthStatus.UNHEALTHY

        system_health["overall_status"] = overall_status.value
        return system_health
