"""
Monitoring and metrics collection for the InkedUp Polymarket Bot.

This module provides comprehensive monitoring capabilities including:
- Prometheus metrics collection
- Health checks
- Performance monitoring
- Business metrics tracking
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import aiohttp_cors
import psutil
from aiohttp import web
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

# Import bot components for monitoring
from .config import BotConfig
from .state import StateManager

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Centralized metrics collection for the trading bot."""

    def __init__(self, config: BotConfig, registry: CollectorRegistry | None = None):
        self.config = config
        self.registry = registry or CollectorRegistry()

        # Trading metrics
        self.active_orders = Gauge(
            "inkedup_active_orders_total",
            "Total number of active orders",
            registry=self.registry,
        )

        self.orders_executed = Counter(
            "inkedup_orders_executed_total",
            "Total number of executed orders",
            ["side", "market", "strategy"],
            registry=self.registry,
        )

        self.orders_cancelled = Counter(
            "inkedup_orders_cancelled_total",
            "Total number of cancelled orders",
            ["reason", "market"],
            registry=self.registry,
        )

        self.position_value = Gauge(
            "inkedup_position_value_usd",
            "Current position value in USD",
            ["market", "outcome", "strategy"],
            registry=self.registry,
        )

        self.position_age = Gauge(
            "inkedup_position_age_minutes",
            "Age of positions in minutes",
            ["position_id", "market"],
            registry=self.registry,
        )

        # Risk metrics
        self.risk_utilization = Gauge(
            "inkedup_risk_utilization_percent",
            "Current risk utilization percentage",
            registry=self.registry,
        )

        self.daily_pnl = Gauge(
            "inkedup_daily_pnl_usd",
            "Daily profit and loss in USD",
            registry=self.registry,
        )

        # Strategy metrics
        self.arbitrage_opportunities = Counter(
            "inkedup_arbitrage_opportunities_found_total",
            "Total arbitrage opportunities found",
            ["strategy", "market_pair"],
            registry=self.registry,
        )

        self.strategy_success_rate = Gauge(
            "inkedup_strategy_success_rate",
            "Success rate of trading strategies",
            ["strategy"],
            registry=self.registry,
        )

        # API and performance metrics
        self.api_requests = Counter(
            "inkedup_api_requests_total",
            "Total API requests made",
            ["endpoint", "method", "status"],
            registry=self.registry,
        )

        self.api_request_duration = Histogram(
            "inkedup_api_request_duration_seconds",
            "API request duration in seconds",
            ["endpoint", "method"],
            registry=self.registry,
        )

        self.db_query_duration = Histogram(
            "inkedup_db_query_duration_seconds",
            "Database query duration in seconds",
            ["query_type"],
            registry=self.registry,
        )

        # System metrics
        self.memory_usage = Gauge(
            "inkedup_memory_usage_bytes",
            "Memory usage in bytes",
            registry=self.registry,
        )

        self.memory_limit = Gauge(
            "inkedup_memory_limit_bytes",
            "Memory limit in bytes",
            registry=self.registry,
        )

        self.cpu_usage = Counter(
            "inkedup_cpu_usage_seconds_total",
            "CPU usage in seconds",
            registry=self.registry,
        )

        self.disk_free = Gauge(
            "inkedup_disk_free_bytes",
            "Free disk space in bytes",
            ["mount_point"],
            registry=self.registry,
        )

        self.disk_total = Gauge(
            "inkedup_disk_total_bytes",
            "Total disk space in bytes",
            ["mount_point"],
            registry=self.registry,
        )

        # Database metrics
        self.db_connections_active = Gauge(
            "inkedup_database_connections_active",
            "Active database connections",
            registry=self.registry,
        )

        self.db_connections_max = Gauge(
            "inkedup_database_connections_max",
            "Maximum database connections",
            registry=self.registry,
        )

        # WebSocket metrics
        self.websocket_connected = Gauge(
            "inkedup_websocket_connected",
            "WebSocket connection status (1=connected, 0=disconnected)",
            ["endpoint"],
            registry=self.registry,
        )

        self.websocket_messages = Counter(
            "inkedup_websocket_messages_total",
            "WebSocket messages received",
            ["message_type", "endpoint"],
            registry=self.registry,
        )

        # Error tracking
        self.errors = Counter(
            "inkedup_errors_total",
            "Total errors encountered",
            ["error_type", "component"],
            registry=self.registry,
        )

        # Business intelligence metrics
        self.market_coverage = Gauge(
            "inkedup_market_coverage_count",
            "Number of markets being monitored",
            registry=self.registry,
        )

        self.last_market_update = Gauge(
            "inkedup_last_market_update_timestamp",
            "Timestamp of last market data update",
            registry=self.registry,
        )

        # Application info
        self.app_info = Info(
            "inkedup_application_info",
            "Application information",
            registry=self.registry,
        )

        self.deployment_info = Info(
            "inkedup_deployment_info", "Deployment information", registry=self.registry
        )

        # Message queue metrics
        self.message_queue_size = Gauge(
            "inkedup_message_queue_size",
            "Size of message processing queue",
            ["queue_name"],
            registry=self.registry,
        )

        self.goroutines_count = Gauge(
            "inkedup_goroutines_count",
            "Number of active goroutines/tasks",
            registry=self.registry,
        )

        # Initialize static metrics
        self._initialize_static_metrics()

    def _initialize_static_metrics(self):
        """Initialize metrics that don't change during runtime."""
        self.app_info.info(
            {
                "version": getattr(self.config, "version", "1.0.0"),
                "environment": getattr(self.config, "app_env", "development"),
                "python_version": f"{psutil.PYTHON}",
            }
        )

        # Set memory limit if configured
        memory_limit_mb = getattr(self.config, "memory_limit_mb", None)
        if memory_limit_mb:
            self.memory_limit.set(memory_limit_mb * 1024 * 1024)

        # Set database connection limits
        pool_size = getattr(self.config, "database_pool_size", 5)
        self.db_connections_max.set(pool_size)

    def update_system_metrics(self):
        """Update system-level metrics."""
        try:
            # Memory usage
            memory = psutil.virtual_memory()
            self.memory_usage.set(memory.used)

            # CPU usage (cumulative)
            cpu_times = psutil.cpu_times()
            self.cpu_usage._value._value = cpu_times.user + cpu_times.system

            # Disk usage
            disk = psutil.disk_usage("/")
            self.disk_free.labels(mount_point="/").set(disk.free)
            self.disk_total.labels(mount_point="/").set(disk.total)

            # Task/thread count approximation
            process = psutil.Process()
            self.goroutines_count.set(process.num_threads())

        except Exception as e:
            logger.error(f"Error updating system metrics: {e}")
            self.errors.labels(
                error_type="system_metrics", component="monitoring"
            ).inc()


@dataclass
class HealthCheck:
    """Health check definition."""

    name: str
    check_function: callable
    timeout: float = 5.0
    critical: bool = True
    tags: list[str] = field(default_factory=list)


class HealthMonitor:
    """Health monitoring system."""

    def __init__(self, config: BotConfig, state_manager: StateManager | None = None):
        self.config = config
        self.state_manager = state_manager
        self.checks: dict[str, HealthCheck] = {}
        self.last_results: dict[str, dict[str, Any]] = {}

        # Register default health checks
        self._register_default_checks()

    def register_check(self, check: HealthCheck):
        """Register a health check."""
        self.checks[check.name] = check
        logger.info(f"Registered health check: {check.name}")

    def _register_default_checks(self):
        """Register default system health checks."""
        # System health
        self.register_check(
            HealthCheck(
                name="system_memory",
                check_function=self._check_memory,
                critical=False,
                tags=["system"],
            )
        )

        self.register_check(
            HealthCheck(
                name="system_disk",
                check_function=self._check_disk,
                critical=False,
                tags=["system"],
            )
        )

        # Database health
        if self.state_manager:
            self.register_check(
                HealthCheck(
                    name="database_connection",
                    check_function=self._check_database,
                    critical=True,
                    tags=["database"],
                )
            )

        # Application health
        self.register_check(
            HealthCheck(
                name="application_ready",
                check_function=self._check_application,
                critical=True,
                tags=["application"],
            )
        )

    async def _check_memory(self) -> dict[str, Any]:
        """Check memory usage."""
        memory = psutil.virtual_memory()
        usage_percent = memory.percent

        return {
            "status": (
                "healthy"
                if usage_percent < 90
                else "degraded" if usage_percent < 95 else "unhealthy"
            ),
            "usage_percent": usage_percent,
            "available_mb": memory.available / (1024 * 1024),
            "message": f"Memory usage: {usage_percent:.1f}%",
        }

    async def _check_disk(self) -> dict[str, Any]:
        """Check disk space."""
        disk = psutil.disk_usage("/")
        free_percent = (disk.free / disk.total) * 100

        return {
            "status": (
                "healthy"
                if free_percent > 20
                else "degraded" if free_percent > 10 else "unhealthy"
            ),
            "free_percent": free_percent,
            "free_gb": disk.free / (1024**3),
            "message": f"Disk free: {free_percent:.1f}%",
        }

    async def _check_database(self) -> dict[str, Any]:
        """Check database connection."""
        if not self.state_manager:
            return {"status": "unhealthy", "message": "No state manager configured"}

        try:
            # Simple database connectivity check
            async with self.state_manager.get_db_connection() as conn:
                cursor = await conn.execute("SELECT 1")
                await cursor.fetchone()

            return {"status": "healthy", "message": "Database connection successful"}
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"Database connection failed: {str(e)}",
            }

    async def _check_application(self) -> dict[str, Any]:
        """Check application readiness."""
        # This is a placeholder - implement based on your application's readiness criteria
        return {
            "status": "healthy",
            "message": "Application is ready",
            "uptime_seconds": time.time() - getattr(self, "_start_time", time.time()),
        }

    async def run_health_checks(self) -> dict[str, Any]:
        """Run all registered health checks."""
        results = {}
        overall_status = "healthy"
        critical_failures = []

        for name, check in self.checks.items():
            try:
                # Run check with timeout
                result = await asyncio.wait_for(
                    check.check_function(), timeout=check.timeout
                )

                results[name] = {
                    "status": result["status"],
                    "message": result.get("message", ""),
                    "data": {
                        k: v
                        for k, v in result.items()
                        if k not in ["status", "message"]
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                    "tags": check.tags,
                    "critical": check.critical,
                }

                # Update overall status
                if result["status"] == "unhealthy":
                    if check.critical:
                        overall_status = "unhealthy"
                        critical_failures.append(name)
                    elif overall_status == "healthy":
                        overall_status = "degraded"
                elif result["status"] == "degraded" and overall_status == "healthy":
                    overall_status = "degraded"

            except TimeoutError:
                results[name] = {
                    "status": "unhealthy",
                    "message": f"Health check timed out after {check.timeout}s",
                    "timestamp": datetime.utcnow().isoformat(),
                    "tags": check.tags,
                    "critical": check.critical,
                }

                if check.critical:
                    overall_status = "unhealthy"
                    critical_failures.append(name)

            except Exception as e:
                logger.error(f"Health check {name} failed: {e}")
                results[name] = {
                    "status": "unhealthy",
                    "message": f"Health check error: {str(e)}",
                    "timestamp": datetime.utcnow().isoformat(),
                    "tags": check.tags,
                    "critical": check.critical,
                }

                if check.critical:
                    overall_status = "unhealthy"
                    critical_failures.append(name)

        self.last_results = results

        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": results,
            "summary": {
                "total_checks": len(results),
                "healthy": len(
                    [r for r in results.values() if r["status"] == "healthy"]
                ),
                "degraded": len(
                    [r for r in results.values() if r["status"] == "degraded"]
                ),
                "unhealthy": len(
                    [r for r in results.values() if r["status"] == "unhealthy"]
                ),
                "critical_failures": critical_failures,
            },
        }


class MonitoringServer:
    """HTTP server for metrics and health checks."""

    def __init__(
        self,
        config: BotConfig,
        metrics_collector: MetricsCollector,
        health_monitor: HealthMonitor,
        port: int = 8080,
    ):
        self.config = config
        self.metrics_collector = metrics_collector
        self.health_monitor = health_monitor
        self.port = port
        self.app = web.Application()
        self._setup_routes()
        self._setup_cors()
        self._start_time = time.time()

    def _setup_routes(self):
        """Setup HTTP routes."""
        self.app.router.add_get("/health", self.health_handler)
        self.app.router.add_get("/readiness", self.readiness_handler)
        self.app.router.add_get("/metrics", self.metrics_handler)
        self.app.router.add_get("/metrics/business", self.business_metrics_handler)
        self.app.router.add_get("/metrics/critical", self.critical_metrics_handler)
        self.app.router.add_get(
            "/metrics/performance", self.performance_metrics_handler
        )
        self.app.router.add_get("/ping", self.ping_handler)

        # Debug endpoints (only in development)
        if getattr(self.config, "enable_debug_endpoints", False):
            self.app.router.add_get("/debug/config", self.debug_config_handler)
            self.app.router.add_get("/debug/metrics", self.debug_metrics_handler)

    def _setup_cors(self):
        """Setup CORS for development."""
        if getattr(self.config, "enable_cors", False):
            cors = aiohttp_cors.setup(
                self.app,
                defaults={
                    "*": aiohttp_cors.ResourceOptions(
                        allow_credentials=True,
                        expose_headers="*",
                        allow_headers="*",
                        allow_methods="*",
                    )
                },
            )

            for route in list(self.app.router.routes()):
                cors.add(route)

    async def health_handler(self, request):
        """Health check endpoint."""
        health_results = await self.health_monitor.run_health_checks()

        status_code = 200
        if health_results["status"] == "unhealthy":
            status_code = 503
        elif health_results["status"] == "degraded":
            status_code = 200  # Still operational

        return web.json_response(health_results, status=status_code)

    async def readiness_handler(self, request):
        """Readiness check endpoint for Kubernetes."""
        # Simplified readiness check
        try:
            # Check critical components only
            critical_checks = {
                name: check
                for name, check in self.health_monitor.checks.items()
                if check.critical
            }

            if not critical_checks:
                return web.json_response({"status": "ready"})

            # Run only critical checks
            ready = True
            for name, check in critical_checks.items():
                try:
                    result = await asyncio.wait_for(check.check_function(), timeout=2.0)
                    if result["status"] == "unhealthy":
                        ready = False
                        break
                except:
                    ready = False
                    break

            status_code = 200 if ready else 503
            return web.json_response(
                {"status": "ready" if ready else "not_ready"}, status=status_code
            )

        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            return web.json_response({"status": "not_ready"}, status=503)

    async def metrics_handler(self, request):
        """Prometheus metrics endpoint."""
        # Update system metrics before serving
        self.metrics_collector.update_system_metrics()

        metrics_data = generate_latest(self.metrics_collector.registry)
        return web.Response(
            text=metrics_data.decode("utf-8"), content_type=CONTENT_TYPE_LATEST
        )

    async def business_metrics_handler(self, request):
        """Business-specific metrics endpoint."""
        # Filter to only business-related metrics
        business_registry = CollectorRegistry()

        # Add only business metrics to the registry
        # This would need to be customized based on your specific business metrics
        metrics_data = generate_latest(business_registry)
        return web.Response(
            text=metrics_data.decode("utf-8"), content_type=CONTENT_TYPE_LATEST
        )

    async def critical_metrics_handler(self, request):
        """Critical metrics endpoint for high-frequency monitoring."""
        # Return only the most critical metrics for real-time monitoring
        critical_metrics = {
            "active_orders": self.metrics_collector.active_orders._value._value,
            "risk_utilization": self.metrics_collector.risk_utilization._value._value,
            "api_errors_per_minute": 0,  # Would need to calculate from counter
            "system_healthy": 1 if self.health_monitor.last_results else 0,
            "timestamp": time.time(),
        }

        return web.json_response(critical_metrics)

    async def performance_metrics_handler(self, request):
        """Performance metrics endpoint."""
        # Return performance-related metrics
        performance_data = {
            "uptime_seconds": time.time() - self._start_time,
            "memory_usage_mb": psutil.virtual_memory().used / (1024 * 1024),
            "cpu_percent": psutil.cpu_percent(),
            "active_tasks": len(asyncio.all_tasks()),
        }

        return web.json_response(performance_data)

    async def ping_handler(self, request):
        """Simple ping endpoint."""
        return web.json_response(
            {
                "pong": True,
                "timestamp": datetime.utcnow().isoformat(),
                "uptime_seconds": time.time() - self._start_time,
            }
        )

    async def debug_config_handler(self, request):
        """Debug configuration endpoint (development only)."""
        if not getattr(self.config, "enable_debug_endpoints", False):
            return web.json_response({"error": "Debug endpoints disabled"}, status=404)

        # Return sanitized configuration (no secrets)
        safe_config = {}
        for key, value in self.config.__dict__.items():
            if "key" not in key.lower() and "password" not in key.lower():
                safe_config[key] = value
            else:
                safe_config[key] = "***REDACTED***"

        return web.json_response(safe_config)

    async def debug_metrics_handler(self, request):
        """Debug metrics information."""
        if not getattr(self.config, "enable_debug_endpoints", False):
            return web.json_response({"error": "Debug endpoints disabled"}, status=404)

        # Return metadata about available metrics
        metrics_info = []
        for collector in self.metrics_collector.registry._collector_to_names.keys():
            for metric in collector._metrics.values():
                metrics_info.append(
                    {
                        "name": metric._name,
                        "type": metric.__class__.__name__,
                        "help": metric._documentation,
                        "labels": getattr(metric, "_labelnames", []),
                    }
                )

        return web.json_response(metrics_info)

    async def start_server(self):
        """Start the monitoring server."""
        runner = web.AppRunner(self.app)
        await runner.setup()

        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()

        logger.info(f"Monitoring server started on port {self.port}")
        return runner


# Convenience function to create monitoring setup
async def setup_monitoring(
    config: BotConfig, state_manager: StateManager | None = None
) -> tuple[MetricsCollector, HealthMonitor, MonitoringServer]:
    """Setup complete monitoring infrastructure."""

    metrics_collector = MetricsCollector(config)
    health_monitor = HealthMonitor(config, state_manager)

    port = getattr(config, "metrics_port", 8080)
    monitoring_server = MonitoringServer(
        config, metrics_collector, health_monitor, port
    )

    return metrics_collector, health_monitor, monitoring_server
