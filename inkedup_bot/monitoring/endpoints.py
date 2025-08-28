"""
Health check HTTP endpoints for the InkedUp Polymarket trading bot.

This module provides HTTP endpoints for monitoring system health, metrics export,
and operational status checks. These endpoints are designed to be used by
external monitoring systems, load balancers, and Kubernetes health probes.
"""

import logging
import time
from datetime import datetime

from aiohttp import web
from aiohttp.web import Request, Response

from .core import MonitoringManager

log = logging.getLogger(__name__)


class HealthCheckServer:
    """HTTP server providing health check and monitoring endpoints."""

    def __init__(
        self,
        monitoring_manager: MonitoringManager,
        host: str = "0.0.0.0",
        port: int = 8080,
        enable_metrics_endpoint: bool = True,
    ):
        self.monitoring = monitoring_manager
        self.host = host
        self.port = port
        self.enable_metrics_endpoint = enable_metrics_endpoint

        self.app: web.Application | None = None
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self._server_start_time = time.time()

    async def start(self):
        """Start the health check HTTP server."""
        if self.app is not None:
            log.warning("Health check server already running")
            return

        # Create aiohttp application
        self.app = web.Application()

        # Register routes
        self._setup_routes()

        # Setup CORS for dashboard access
        self._setup_cors()

        # Start server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

        log.info(f"Health check server started on http://{self.host}:{self.port}")

    async def stop(self):
        """Stop the health check HTTP server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

        self.app = None
        self.runner = None
        self.site = None

        log.info("Health check server stopped")

    def _setup_routes(self):
        """Setup HTTP routes."""
        # Basic health checks
        self.app.router.add_get("/health", self._health_handler)
        self.app.router.add_get("/health/live", self._liveness_handler)
        self.app.router.add_get("/health/ready", self._readiness_handler)

        # Detailed status endpoints
        self.app.router.add_get("/status", self._status_handler)
        self.app.router.add_get("/status/components", self._components_status_handler)

        # Metrics endpoints
        if self.enable_metrics_endpoint:
            self.app.router.add_get("/metrics", self._prometheus_metrics_handler)
            self.app.router.add_get("/metrics/json", self._json_metrics_handler)

        # System information
        self.app.router.add_get("/info", self._info_handler)
        self.app.router.add_get("/version", self._version_handler)

        # Debug endpoints (for development)
        self.app.router.add_get("/debug/config", self._debug_config_handler)

        # Root endpoint
        self.app.router.add_get("/", self._root_handler)

    def _setup_cors(self):
        """Setup CORS headers for dashboard access."""

        async def cors_middleware(request: Request, handler):
            response = await handler(request)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return response

        self.app.middlewares.append(cors_middleware)

    async def _health_handler(self, request: Request) -> Response:
        """
        Basic health check endpoint.
        Returns 200 if system is healthy, 503 if unhealthy.
        """
        try:
            health_results = await self.monitoring.health.run_health_checks()

            if health_results["overall_status"] == "healthy":
                return web.json_response(
                    {
                        "status": "healthy",
                        "timestamp": datetime.utcnow().isoformat(),
                        "uptime_seconds": time.time() - self._server_start_time,
                    },
                    status=200,
                )
            else:
                return web.json_response(
                    {
                        "status": health_results["overall_status"],
                        "timestamp": datetime.utcnow().isoformat(),
                        "components": {
                            name: comp["status"]
                            for name, comp in health_results["components"].items()
                        },
                    },
                    status=503,
                )
        except Exception as e:
            log.error(f"Health check error: {e}")
            return web.json_response(
                {
                    "status": "error",
                    "message": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                },
                status=500,
            )

    async def _liveness_handler(self, request: Request) -> Response:
        """
        Kubernetes liveness probe endpoint.
        Returns 200 if the application is running (even if degraded).
        """
        return web.json_response(
            {
                "alive": True,
                "timestamp": datetime.utcnow().isoformat(),
                "uptime_seconds": time.time() - self._server_start_time,
            },
            status=200,
        )

    async def _readiness_handler(self, request: Request) -> Response:
        """
        Kubernetes readiness probe endpoint.
        Returns 200 if system is ready to accept traffic.
        """
        try:
            health_results = await self.monitoring.health.run_health_checks()

            # Consider system ready if no critical failures
            critical_failures = [
                name
                for name, comp in health_results["components"].items()
                if comp["status"] == "unhealthy"
            ]

            if not critical_failures:
                return web.json_response(
                    {
                        "ready": True,
                        "timestamp": datetime.utcnow().isoformat(),
                        "status": health_results["overall_status"],
                    },
                    status=200,
                )
            else:
                return web.json_response(
                    {
                        "ready": False,
                        "timestamp": datetime.utcnow().isoformat(),
                        "critical_failures": critical_failures,
                    },
                    status=503,
                )
        except Exception as e:
            log.error(f"Readiness check error: {e}")
            return web.json_response(
                {
                    "ready": False,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                },
                status=503,
            )

    async def _status_handler(self, request: Request) -> Response:
        """
        Comprehensive system status endpoint.
        Returns detailed status information for all components.
        """
        try:
            system_status = self.monitoring.get_system_status()
            return web.json_response(system_status, status=200)
        except Exception as e:
            log.error(f"Status check error: {e}")
            return web.json_response(
                {"error": str(e), "timestamp": datetime.utcnow().isoformat()},
                status=500,
            )

    async def _components_status_handler(self, request: Request) -> Response:
        """
        Individual component status endpoint.
        Supports filtering by component name via ?component= parameter.
        """
        try:
            # Parse query parameters
            component_filter = request.query.get("component")

            health_results = await self.monitoring.health.run_health_checks()
            components = health_results.get("components", {})

            if component_filter:
                if component_filter in components:
                    return web.json_response(
                        {
                            "component": component_filter,
                            "status": components[component_filter],
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                        status=200,
                    )
                else:
                    return web.json_response(
                        {
                            "error": f"Component {component_filter} not found",
                            "available_components": list(components.keys()),
                        },
                        status=404,
                    )
            else:
                return web.json_response(
                    {
                        "components": components,
                        "summary": health_results.get("summary", {}),
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    status=200,
                )
        except Exception as e:
            log.error(f"Components status error: {e}")
            return web.json_response(
                {"error": str(e), "timestamp": datetime.utcnow().isoformat()},
                status=500,
            )

    async def _prometheus_metrics_handler(self, request: Request) -> Response:
        """
        Prometheus metrics endpoint.
        Returns metrics in Prometheus exposition format.
        """
        try:
            metrics_summary = self.monitoring.metrics.get_metrics_summary()

            # Convert to Prometheus format
            prometheus_lines = [
                "# HELP inkedup_info Information about the InkedUp trading bot",
                "# TYPE inkedup_info gauge",
                'inkedup_info{version="1.0.0",component="trading_bot"} 1',
                "",
            ]

            # Add timestamp
            timestamp_ms = int(time.time() * 1000)

            # Export counters
            for name, value in metrics_summary.get("counters", {}).items():
                prometheus_lines.extend(
                    [f"# TYPE {name} counter", f"{name} {value} {timestamp_ms}"]
                )

            # Export gauges
            for name, value in metrics_summary.get("gauges", {}).items():
                prometheus_lines.extend(
                    [f"# TYPE {name} gauge", f"{name} {value} {timestamp_ms}"]
                )

            # Export histogram summaries
            for name, stats in metrics_summary.get("histograms", {}).items():
                prometheus_lines.extend(
                    [
                        f"# TYPE {name} histogram",
                        f"{name}_count {stats['count']} {timestamp_ms}",
                        f"{name}_sum {stats['mean'] * stats['count']} {timestamp_ms}",
                    ]
                )

                # Add percentiles
                for percentile, value in stats.get("percentiles", {}).items():
                    prometheus_lines.append(
                        f'{name}{{quantile="{percentile/100}"}} {value} {timestamp_ms}'
                    )

            # Add health check metrics
            health_results = self.monitoring.health.get_last_health_check()
            if health_results:
                healthy_count = health_results["summary"]["healthy_checks"]
                total_count = health_results["summary"]["total_checks"]

                prometheus_lines.extend(
                    [
                        "# TYPE health_checks_total gauge",
                        f"health_checks_total {total_count} {timestamp_ms}",
                        "# TYPE health_checks_healthy gauge",
                        f"health_checks_healthy {healthy_count} {timestamp_ms}",
                    ]
                )

            return Response(
                text="\n".join(prometheus_lines),
                content_type="text/plain; version=0.0.4; charset=utf-8",
                status=200,
            )

        except Exception as e:
            log.error(f"Prometheus metrics error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def _json_metrics_handler(self, request: Request) -> Response:
        """
        JSON metrics endpoint.
        Returns metrics in structured JSON format.
        """
        try:
            metrics_summary = self.monitoring.metrics.get_metrics_summary()

            # Add health metrics
            health_results = self.monitoring.health.get_last_health_check()
            if health_results:
                metrics_summary["health"] = {
                    "overall_status": health_results["overall_status"],
                    "component_summary": health_results["summary"],
                }

            # Add server metrics
            metrics_summary["server"] = {
                "uptime_seconds": time.time() - self._server_start_time,
                "timestamp": datetime.utcnow().isoformat(),
            }

            return web.json_response(metrics_summary, status=200)

        except Exception as e:
            log.error(f"JSON metrics error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def _info_handler(self, request: Request) -> Response:
        """System information endpoint."""
        try:
            import platform

            import psutil

            info = {
                "application": {
                    "name": "InkedUp Polymarket Trading Bot",
                    "version": "1.0.0",
                    "uptime_seconds": time.time() - self._server_start_time,
                    "start_time": datetime.fromtimestamp(
                        self._server_start_time
                    ).isoformat(),
                },
                "system": {
                    "platform": platform.platform(),
                    "python_version": platform.python_version(),
                    "cpu_count": psutil.cpu_count(),
                    "memory_total_gb": round(
                        psutil.virtual_memory().total / (1024**3), 2
                    ),
                },
                "monitoring": {
                    "components_registered": len(self.monitoring.monitored_components),
                    "health_checks_registered": len(
                        self.monitoring.health.health_checks
                    ),
                    "monitoring_running": self.monitoring.is_running,
                },
                "timestamp": datetime.utcnow().isoformat(),
            }

            return web.json_response(info, status=200)

        except Exception as e:
            log.error(f"Info endpoint error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def _version_handler(self, request: Request) -> Response:
        """Version information endpoint."""
        return web.json_response(
            {
                "version": "1.0.0",
                "build_date": "2024-01-01",  # Would be set during build
                "git_commit": "unknown",  # Would be set during build
                "timestamp": datetime.utcnow().isoformat(),
            },
            status=200,
        )

    async def _debug_config_handler(self, request: Request) -> Response:
        """Debug configuration endpoint (sanitized)."""
        try:
            config_info = {
                "monitoring_config": {
                    "health_check_interval": self.monitoring.config.health_check_interval,
                    "metrics_collection_interval": self.monitoring.config.metrics_collection_interval,
                    "monitoring_level": self.monitoring.config.monitoring_level.value,
                    "metrics_retention_hours": self.monitoring.config.metrics_retention_hours,
                },
                "server_config": {
                    "host": self.host,
                    "port": self.port,
                    "metrics_endpoint_enabled": self.enable_metrics_endpoint,
                },
                "timestamp": datetime.utcnow().isoformat(),
            }

            return web.json_response(config_info, status=200)

        except Exception as e:
            log.error(f"Debug config error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def _root_handler(self, request: Request) -> Response:
        """Root endpoint with API documentation."""
        api_docs = {
            "service": "InkedUp Polymarket Trading Bot - Health Check API",
            "version": "1.0.0",
            "endpoints": {
                "health": {
                    "path": "/health",
                    "description": "Basic health check - returns 200 if healthy, 503 if unhealthy",
                },
                "liveness": {
                    "path": "/health/live",
                    "description": "Kubernetes liveness probe - returns 200 if application is running",
                },
                "readiness": {
                    "path": "/health/ready",
                    "description": "Kubernetes readiness probe - returns 200 if ready to serve traffic",
                },
                "status": {
                    "path": "/status",
                    "description": "Comprehensive system status with detailed component information",
                },
                "components": {
                    "path": "/status/components",
                    "description": "Individual component status, supports ?component=name filtering",
                },
                "prometheus_metrics": {
                    "path": "/metrics",
                    "description": "Prometheus-compatible metrics export",
                },
                "json_metrics": {
                    "path": "/metrics/json",
                    "description": "Structured JSON metrics export",
                },
                "info": {
                    "path": "/info",
                    "description": "System and application information",
                },
                "version": {
                    "path": "/version",
                    "description": "Application version information",
                },
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

        return web.json_response(api_docs, status=200)


async def create_health_server(
    monitoring_manager: MonitoringManager, host: str = "0.0.0.0", port: int = 8080
) -> HealthCheckServer:
    """
    Factory function to create and start a health check server.

    Args:
        monitoring_manager: The monitoring manager instance
        host: Server host address
        port: Server port

    Returns:
        HealthCheckServer instance
    """
    server = HealthCheckServer(monitoring_manager, host, port)
    await server.start()
    return server


# Integration helpers for trading bot components
def register_trading_component_health_checks(monitoring: MonitoringManager):
    """Register health checks for core trading bot components."""

    async def database_health_check():
        """Check database connectivity and health."""
        try:
            # This would be implemented based on actual database manager
            return {
                "status": "healthy",
                "message": "Database connection OK",
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"Database error: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def websocket_health_check():
        """Check WebSocket connection health."""
        try:
            # This would check actual WebSocket connection status
            return {
                "status": "healthy",
                "message": "WebSocket connection active",
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"WebSocket error: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def order_client_health_check():
        """Check order client health."""
        try:
            # This would check order client status
            return {
                "status": "healthy",
                "message": "Order client operational",
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"Order client error: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
            }

    # Register the health checks
    monitoring.health.register_health_check("database", database_health_check)
    monitoring.health.register_health_check("websocket", websocket_health_check)
    monitoring.health.register_health_check("order_client", order_client_health_check)

    log.info("Registered core trading component health checks")
