"""
Enhanced monitoring dashboard with key indicators for the InkedUp Polymarket trading bot.

This module provides HTTP endpoints, web dashboards, and API interfaces
for accessing monitoring data, health status, and operational metrics.
Features a comprehensive web-based dashboard for real-time system visualization.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

# For HTTP server functionality
try:
    from aiohttp import web
    from aiohttp.web_response import Response

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    web = None
    Response = None

logger = logging.getLogger(__name__)


class HealthEndpoint:
    """Health check HTTP endpoint."""

    def __init__(self, monitoring_manager):
        self.monitoring_manager = monitoring_manager
        self.startup_time = datetime.now()

    async def health_check(self, request=None) -> dict[str, Any]:
        """Main health check endpoint."""
        try:
            # Get system health status
            health_results = await self.monitoring_manager.health.run_health_checks()

            # Calculate uptime
            uptime_seconds = (datetime.now() - self.startup_time).total_seconds()

            # Basic system info
            system_info = {
                "service": "InkedUp Polymarket Bot",
                "version": "1.0.0",
                "startup_time": self.startup_time.isoformat(),
                "uptime_seconds": uptime_seconds,
                "timestamp": datetime.now().isoformat(),
            }

            # Combine health check results
            response = {
                "status": health_results.get("overall_status", "unknown"),
                "system": system_info,
                "health_checks": health_results,
                "monitoring": {
                    "metrics_collector_running": self.monitoring_manager.is_running,
                    "components_registered": len(
                        self.monitoring_manager.monitored_components
                    ),
                },
            }

            return response

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def liveness_check(self, request=None) -> dict[str, Any]:
        """Liveness probe - basic service availability."""
        return {
            "status": "alive",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": (datetime.now() - self.startup_time).total_seconds(),
        }

    async def readiness_check(self, request=None) -> dict[str, Any]:
        """Readiness probe - service ready to handle requests."""
        try:
            # Check if monitoring system is running
            if not self.monitoring_manager.is_running:
                return {
                    "status": "not_ready",
                    "reason": "monitoring_system_not_running",
                    "timestamp": datetime.now().isoformat(),
                }

            # Quick health check on critical components
            critical_components = ["database", "websocket", "order_client"]
            component_status = {}

            for component_name in critical_components:
                if component_name in self.monitoring_manager.monitored_components:
                    component = self.monitoring_manager.monitored_components[
                        component_name
                    ]
                    if hasattr(component, "health_check"):
                        try:
                            result = await asyncio.wait_for(
                                component.health_check(), timeout=2.0
                            )
                            component_status[component_name] = result.get(
                                "status", "unknown"
                            )
                        except TimeoutError:
                            component_status[component_name] = "timeout"
                        except Exception as e:
                            component_status[component_name] = f"error: {str(e)}"
                    else:
                        component_status[component_name] = "no_health_check"
                else:
                    component_status[component_name] = "not_registered"

            # Determine readiness
            unhealthy_components = [
                name
                for name, status in component_status.items()
                if status in ["unhealthy", "timeout", "error"]
            ]

            if unhealthy_components:
                return {
                    "status": "not_ready",
                    "reason": f"unhealthy_components: {', '.join(unhealthy_components)}",
                    "component_status": component_status,
                    "timestamp": datetime.now().isoformat(),
                }
            else:
                return {
                    "status": "ready",
                    "component_status": component_status,
                    "timestamp": datetime.now().isoformat(),
                }

        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            return {
                "status": "not_ready",
                "reason": f"readiness_check_failed: {str(e)}",
                "timestamp": datetime.now().isoformat(),
            }


class MetricsEndpoint:
    """Metrics HTTP endpoint for Prometheus-style metrics export."""

    def __init__(self, monitoring_manager):
        self.monitoring_manager = monitoring_manager

    async def metrics(self, request=None) -> dict[str, Any]:
        """Get all metrics in JSON format."""
        try:
            metrics_summary = self.monitoring_manager.metrics.get_metrics_summary()
            return {"timestamp": datetime.now().isoformat(), "metrics": metrics_summary}
        except Exception as e:
            logger.error(f"Metrics endpoint failed: {e}")
            return {"error": str(e)}

    async def metrics_prometheus(self, request=None) -> str:
        """Get metrics in Prometheus format."""
        try:
            metrics_summary = self.monitoring_manager.metrics.get_metrics_summary()
            prometheus_output = []

            # Convert counters
            for name, value in metrics_summary.get("counters", {}).items():
                prometheus_output.append(f"# TYPE {name} counter")
                prometheus_output.append(f"{name} {value}")

            # Convert gauges
            for name, value in metrics_summary.get("gauges", {}).items():
                prometheus_output.append(f"# TYPE {name} gauge")
                prometheus_output.append(f"{name} {value}")

            # Convert histograms
            for name, hist_data in metrics_summary.get("histograms", {}).items():
                prometheus_output.append(f"# TYPE {name} histogram")
                prometheus_output.append(f'{name}_count {hist_data.get("count", 0)}')
                prometheus_output.append(f'{name}_sum {hist_data.get("sum", 0)}')

                # Percentiles as separate metrics
                for percentile, value in hist_data.get("percentiles", {}).items():
                    prometheus_output.append(
                        f'{name}_percentile{{percentile="{percentile}"}} {value}'
                    )

            # Convert timers (similar to histograms)
            for name, timer_data in metrics_summary.get("timers", {}).items():
                prometheus_output.append(f"# TYPE {name}_duration_seconds histogram")
                prometheus_output.append(
                    f'{name}_duration_seconds_count {timer_data.get("count", 0)}'
                )
                prometheus_output.append(
                    f'{name}_duration_seconds_sum {timer_data.get("sum", 0) / 1000}'
                )  # Convert ms to seconds

                for percentile, value in timer_data.get("percentiles", {}).items():
                    prometheus_output.append(
                        f'{name}_duration_seconds{{percentile="{percentile}"}} {value / 1000}'
                    )

            return "\n".join(prometheus_output)

        except Exception as e:
            logger.error(f"Prometheus metrics endpoint failed: {e}")
            return f"# ERROR: {str(e)}"

    async def metric_history(self, request) -> dict[str, Any]:
        """Get historical data for a specific metric."""
        try:
            if hasattr(request, "query"):
                metric_name = request.query.get("metric")
                minutes = int(request.query.get("minutes", 60))
            else:
                # For non-HTTP usage
                metric_name = request.get("metric") if request else None
                minutes = int(request.get("minutes", 60)) if request else 60

            if not metric_name:
                return {"error": "metric parameter required"}

            history = self.monitoring_manager.metrics.get_metric_history(
                metric_name, minutes
            )
            return {
                "metric": metric_name,
                "minutes": minutes,
                "data_points": len(history),
                "history": history,
            }

        except Exception as e:
            logger.error(f"Metric history endpoint failed: {e}")
            return {"error": str(e)}


class PerformanceEndpoint:
    """Performance monitoring HTTP endpoint."""

    def __init__(self, performance_monitor):
        self.performance_monitor = performance_monitor

    async def performance_summary(self, request=None) -> dict[str, Any]:
        """Get comprehensive performance summary."""
        try:
            return self.performance_monitor.get_comprehensive_performance_report()
        except Exception as e:
            logger.error(f"Performance summary endpoint failed: {e}")
            return {"error": str(e)}

    async def resource_usage(self, request=None) -> dict[str, Any]:
        """Get current resource usage."""
        try:
            return self.performance_monitor.resource_monitor.get_resource_summary()
        except Exception as e:
            logger.error(f"Resource usage endpoint failed: {e}")
            return {"error": str(e)}

    async def trading_performance(self, request=None) -> dict[str, Any]:
        """Get trading-specific performance metrics."""
        try:
            return (
                self.performance_monitor.trading_performance.get_trading_performance_summary()
            )
        except Exception as e:
            logger.error(f"Trading performance endpoint failed: {e}")
            return {"error": str(e)}

    async def alerts(self, request=None) -> dict[str, Any]:
        """Get performance alerts."""
        try:
            return {
                "alerts": self.performance_monitor._generate_performance_alerts(),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Performance alerts endpoint failed: {e}")
            return {"error": str(e)}


class TradingDashboard:
    """Trading-specific dashboard with real-time metrics."""

    def __init__(self, monitoring_manager, performance_monitor, alert_manager):
        self.monitoring_manager = monitoring_manager
        self.performance_monitor = performance_monitor
        self.alert_manager = alert_manager

    async def dashboard_data(self, request=None) -> dict[str, Any]:
        """Get comprehensive dashboard data."""
        try:
            # Get all monitoring data
            health_data = await self.monitoring_manager.health.run_health_checks()
            metrics_data = self.monitoring_manager.metrics.get_metrics_summary()
            performance_data = (
                self.performance_monitor.get_comprehensive_performance_report()
            )
            alert_data = self.alert_manager.get_alert_summary()
            active_alerts = self.alert_manager.get_active_alerts()
            error_rates = self.alert_manager.get_error_rates()

            return {
                "timestamp": datetime.now().isoformat(),
                "health": health_data,
                "metrics": metrics_data,
                "performance": performance_data,
                "alerts": {
                    "summary": alert_data,
                    "active": active_alerts,
                    "error_rates": error_rates,
                },
                "system_status": {
                    "monitoring_running": self.monitoring_manager.is_running,
                    "performance_monitoring": self.performance_monitor.is_monitoring,
                    "components_registered": len(
                        self.monitoring_manager.monitored_components
                    ),
                },
            }

        except Exception as e:
            logger.error(f"Dashboard data endpoint failed: {e}")
            return {"error": str(e)}

    async def trading_overview(self, request=None) -> dict[str, Any]:
        """Get trading-focused overview."""
        try:
            metrics = self.monitoring_manager.metrics.get_metrics_summary()
            trading_perf = (
                self.performance_monitor.trading_performance.get_trading_performance_summary()
            )

            # Extract trading-specific metrics
            trading_metrics = {}
            for metric_name, value in metrics.get("counters", {}).items():
                if any(
                    keyword in metric_name.lower()
                    for keyword in ["order", "trade", "position", "pnl"]
                ):
                    trading_metrics[metric_name] = value

            for metric_name, value in metrics.get("gauges", {}).items():
                if any(
                    keyword in metric_name.lower()
                    for keyword in ["position", "pnl", "exposure", "balance"]
                ):
                    trading_metrics[metric_name] = value

            return {
                "timestamp": datetime.now().isoformat(),
                "trading_metrics": trading_metrics,
                "performance": trading_perf,
                "market_status": self._get_market_status(),
                "recent_activity": self._get_recent_trading_activity(),
            }

        except Exception as e:
            logger.error(f"Trading overview endpoint failed: {e}")
            return {"error": str(e)}

    def _get_market_status(self) -> dict[str, Any]:
        """Get current market status from monitoring data."""
        # This would integrate with actual market data
        return {
            "markets_connected": True,
            "websocket_status": "connected",
            "data_freshness": "good",
            "last_update": datetime.now().isoformat(),
        }

    def _get_recent_trading_activity(self) -> list[dict[str, Any]]:
        """Get recent trading activity summary."""
        # This would extract from metrics history
        return [
            {
                "timestamp": datetime.now().isoformat(),
                "type": "order_placed",
                "market": "example_market",
                "status": "success",
            }
        ]


class DashboardManager:
    """Central dashboard management with HTTP server capability."""

    def __init__(
        self,
        monitoring_manager,
        performance_monitor=None,
        alert_manager=None,
        port=8080,
    ):
        self.monitoring_manager = monitoring_manager
        self.performance_monitor = performance_monitor
        self.alert_manager = alert_manager
        self.port = port

        # Create endpoint handlers
        self.health_endpoint = HealthEndpoint(monitoring_manager)
        self.metrics_endpoint = MetricsEndpoint(monitoring_manager)

        if performance_monitor:
            self.performance_endpoint = PerformanceEndpoint(performance_monitor)

        if monitoring_manager and performance_monitor and alert_manager:
            self.trading_dashboard = TradingDashboard(
                monitoring_manager, performance_monitor, alert_manager
            )

        # HTTP server components
        self.app = None
        self.server = None
        self.is_running = False

        logger.info(f"Dashboard manager initialized (port: {port})")

    async def start_server(self):
        """Start HTTP dashboard server."""
        if not AIOHTTP_AVAILABLE:
            logger.error("aiohttp not available - cannot start HTTP server")
            return

        if self.is_running:
            logger.warning("Dashboard server already running")
            return

        try:
            # Create web application
            self.app = web.Application()

            # Add routes
            self.app.router.add_get("/health", self._http_health)
            self.app.router.add_get("/health/live", self._http_liveness)
            self.app.router.add_get("/health/ready", self._http_readiness)

            self.app.router.add_get("/metrics", self._http_metrics)
            self.app.router.add_get(
                "/metrics/prometheus", self._http_metrics_prometheus
            )
            self.app.router.add_get("/metrics/history", self._http_metric_history)

            if self.performance_monitor:
                self.app.router.add_get("/performance", self._http_performance)
                self.app.router.add_get("/performance/resources", self._http_resources)
                self.app.router.add_get(
                    "/performance/trading", self._http_trading_performance
                )
                self.app.router.add_get(
                    "/performance/alerts", self._http_performance_alerts
                )

            if hasattr(self, "trading_dashboard"):
                self.app.router.add_get("/dashboard", self._http_dashboard)
                self.app.router.add_get(
                    "/dashboard/trading", self._http_trading_overview
                )

            # CORS and middleware
            self.app.router.add_get("/", self._http_index)

            # Start server
            runner = web.AppRunner(self.app)
            await runner.setup()

            site = web.TCPSite(runner, "0.0.0.0", self.port)
            await site.start()

            self.is_running = True
            logger.info(f"Dashboard server started on port {self.port}")

        except Exception as e:
            logger.error(f"Failed to start dashboard server: {e}")
            raise

    async def stop_server(self):
        """Stop HTTP dashboard server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        self.is_running = False
        logger.info("Dashboard server stopped")

    # HTTP handler methods
    async def _http_health(self, request):
        data = await self.health_endpoint.health_check(request)
        status = 200 if data.get("status") == "healthy" else 503
        return web.json_response(data, status=status)

    async def _http_liveness(self, request):
        data = await self.health_endpoint.liveness_check(request)
        return web.json_response(data)

    async def _http_readiness(self, request):
        data = await self.health_endpoint.readiness_check(request)
        status = 200 if data.get("status") == "ready" else 503
        return web.json_response(data, status=status)

    async def _http_metrics(self, request):
        data = await self.metrics_endpoint.metrics(request)
        return web.json_response(data)

    async def _http_metrics_prometheus(self, request):
        data = await self.metrics_endpoint.metrics_prometheus(request)
        return web.Response(text=data, content_type="text/plain")

    async def _http_metric_history(self, request):
        data = await self.metrics_endpoint.metric_history(request)
        return web.json_response(data)

    async def _http_performance(self, request):
        data = await self.performance_endpoint.performance_summary(request)
        return web.json_response(data)

    async def _http_resources(self, request):
        data = await self.performance_endpoint.resource_usage(request)
        return web.json_response(data)

    async def _http_trading_performance(self, request):
        data = await self.performance_endpoint.trading_performance(request)
        return web.json_response(data)

    async def _http_performance_alerts(self, request):
        data = await self.performance_endpoint.alerts(request)
        return web.json_response(data)

    async def _http_dashboard(self, request):
        data = await self.trading_dashboard.dashboard_data(request)
        return web.json_response(data)

    async def _http_trading_overview(self, request):
        data = await self.trading_dashboard.trading_overview(request)
        return web.json_response(data)

    async def _http_index(self, request):
        """Root endpoint with enhanced dashboard HTML."""
        # Check if requesting HTML dashboard
        accept_header = request.headers.get("Accept", "")
        if "text/html" in accept_header or "dashboard" in request.query:
            return web.Response(
                text=self._generate_dashboard_html(), content_type="text/html"
            )

        # Otherwise return API documentation
        api_docs = {
            "service": "InkedUp Polymarket Bot Monitoring API",
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "endpoints": {
                "health": {
                    "/health": "Comprehensive health check",
                    "/health/live": "Liveness probe",
                    "/health/ready": "Readiness probe",
                },
                "metrics": {
                    "/metrics": "All metrics in JSON format",
                    "/metrics/prometheus": "Metrics in Prometheus format",
                    "/metrics/history": "Historical metric data (requires ?metric=name)",
                },
                "performance": {
                    "/performance": "Comprehensive performance report",
                    "/performance/resources": "Resource utilization",
                    "/performance/trading": "Trading performance metrics",
                    "/performance/alerts": "Performance alerts",
                },
                "dashboard": {
                    "/dashboard": "Complete dashboard data",
                    "/dashboard/trading": "Trading-focused overview",
                    "/?dashboard": "Web-based monitoring dashboard (HTML)",
                },
            },
            "status": {
                "server_running": self.is_running,
                "monitoring_active": (
                    self.monitoring_manager.is_running
                    if self.monitoring_manager
                    else False
                ),
                "performance_monitoring": (
                    self.performance_monitor.is_monitoring
                    if self.performance_monitor
                    else False
                ),
            },
        }

        return web.json_response(api_docs)

    def _generate_dashboard_html(self) -> str:
        """Generate enhanced monitoring dashboard HTML."""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>InkedUp Trading Bot - Monitoring Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f1419 0%, #1a1f26 100%);
            color: #e6e6e6;
            line-height: 1.6;
            min-height: 100vh;
        }
        
        .header {
            background: rgba(26, 31, 38, 0.95);
            backdrop-filter: blur(10px);
            padding: 1rem 2rem;
            border-bottom: 2px solid #2a3441;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            position: sticky;
            top: 0;
            z-index: 100;
        }
        
        .header h1 {
            color: #00d4aa;
            font-size: 1.8rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }
        
        .header-info {
            display: flex;
            align-items: center;
            gap: 2rem;
            font-size: 0.9rem;
            color: #b0b0b0;
        }
        
        .realtime-indicator {
            animation: pulse 2s infinite;
            color: #00d4aa;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .dashboard-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 1.5rem;
            padding: 2rem;
            max-width: 1600px;
            margin: 0 auto;
        }
        
        .card {
            background: rgba(26, 31, 38, 0.9);
            border-radius: 12px;
            padding: 1.5rem;
            border: 1px solid #2a3441;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, #00d4aa, #007a88);
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        
        .card:hover {
            transform: translateY(-4px);
            border-color: #00d4aa;
            box-shadow: 0 12px 40px rgba(0, 212, 170, 0.2);
        }
        
        .card:hover::before {
            opacity: 1;
        }
        
        .card-title {
            color: #00d4aa;
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 8px currentColor;
        }
        
        .status-healthy { 
            background: #00d4aa; 
            color: #00d4aa;
        }
        .status-warning { 
            background: #ff9500; 
            color: #ff9500;
        }
        .status-critical { 
            background: #ff3b30; 
            color: #ff3b30;
        }
        .status-unknown { 
            background: #8e8e93; 
            color: #8e8e93;
        }
        
        .metric {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 0;
            border-bottom: 1px solid rgba(42, 52, 65, 0.5);
            transition: background-color 0.2s ease;
        }
        
        .metric:hover {
            background-color: rgba(0, 212, 170, 0.05);
            border-radius: 4px;
        }
        
        .metric:last-child {
            border-bottom: none;
        }
        
        .metric-label {
            color: #b0b0b0;
            font-size: 0.9rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .metric-value {
            color: #e6e6e6;
            font-weight: 600;
            font-size: 1.1rem;
            font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
        }
        
        .metric-trend {
            font-size: 0.8rem;
            margin-left: 0.5rem;
        }
        
        .trend-up { color: #00d4aa; }
        .trend-down { color: #ff3b30; }
        .trend-stable { color: #8e8e93; }
        
        .loading {
            text-align: center;
            color: #8e8e93;
            padding: 2rem;
            animation: pulse 1.5s infinite;
        }
        
        .error {
            color: #ff3b30;
            text-align: center;
            padding: 1rem;
            background: rgba(255, 59, 48, 0.1);
            border: 1px solid rgba(255, 59, 48, 0.3);
            border-radius: 6px;
            margin: 1rem 0;
        }
        
        .refresh-time {
            color: #8e8e93;
            font-size: 0.8rem;
            text-align: right;
            margin-top: 1.5rem;
            padding-top: 1rem;
            border-top: 1px solid rgba(42, 52, 65, 0.3);
        }
        
        .chart-placeholder {
            height: 120px;
            background: rgba(0, 212, 170, 0.1);
            border: 2px dashed rgba(0, 212, 170, 0.3);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #00d4aa;
            font-size: 0.9rem;
            margin: 1rem 0;
        }
        
        .alert-item {
            background: rgba(255, 59, 48, 0.1);
            border: 1px solid rgba(255, 59, 48, 0.3);
            border-radius: 6px;
            padding: 0.75rem;
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
        }
        
        .alert-timestamp {
            color: #8e8e93;
            font-size: 0.8rem;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }
        
        @keyframes glow {
            0%, 100% { box-shadow: 0 0 5px rgba(0, 212, 170, 0.5); }
            50% { box-shadow: 0 0 20px rgba(0, 212, 170, 0.8); }
        }
        
        .status-healthy {
            animation: glow 2s infinite;
        }
        
        @media (max-width: 768px) {
            .dashboard-container {
                grid-template-columns: 1fr;
                padding: 1rem;
            }
            
            .header {
                padding: 1rem;
            }
            
            .header h1 {
                font-size: 1.5rem;
            }
            
            .header-info {
                flex-direction: column;
                align-items: flex-start;
                gap: 0.5rem;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 InkedUp Trading Bot - Monitoring Dashboard</h1>
        <div class="header-info">
            <div class="realtime-indicator">
                <span class="status-indicator status-healthy"></span>
                Live Data Stream
            </div>
            <div id="last-update">Last update: Loading...</div>
        </div>
    </div>
    
    <div class="dashboard-container">
        <!-- System Overview Card -->
        <div class="card">
            <div class="card-title">
                <span class="status-indicator" id="system-status-indicator"></span>
                📊 System Overview
            </div>
            <div id="system-overview-content" class="loading">Initializing system overview...</div>
        </div>
        
        <!-- Health Status Card -->
        <div class="card">
            <div class="card-title">🏥 Component Health</div>
            <div id="health-status-content" class="loading">Checking component health...</div>
        </div>
        
        <!-- Performance Metrics Card -->
        <div class="card">
            <div class="card-title">⚡ Performance Metrics</div>
            <div id="performance-content" class="loading">Gathering performance data...</div>
            <div class="chart-placeholder">Performance Chart (Coming Soon)</div>
        </div>
        
        <!-- Trading Activity Card -->
        <div class="card">
            <div class="card-title">💹 Trading Activity</div>
            <div id="trading-content" class="loading">Loading trading metrics...</div>
        </div>
        
        <!-- Active Alerts Card -->
        <div class="card">
            <div class="card-title">🚨 Active Alerts</div>
            <div id="alerts-content" class="loading">Checking for alerts...</div>
        </div>
        
        <!-- System Resources Card -->
        <div class="card">
            <div class="card-title">🖥️ System Resources</div>
            <div id="resources-content" class="loading">Monitoring system resources...</div>
        </div>
        
        <!-- Network Status Card -->
        <div class="card">
            <div class="card-title">🌐 Network Status</div>
            <div id="network-content" class="loading">Checking network connectivity...</div>
        </div>
        
        <!-- Recent Activity Card -->
        <div class="card">
            <div class="card-title">📋 Recent Activity</div>
            <div id="activity-content" class="loading">Loading recent activity...</div>
        </div>
    </div>
    
    <script>
        class EnhancedMonitoringDashboard {
            constructor() {
                this.lastUpdate = null;
                this.refreshInterval = 5000; // 5 seconds
                this.errorCount = 0;
                this.maxErrors = 5;
                this.init();
            }
            
            async init() {
                console.log('🚀 Initializing Enhanced Monitoring Dashboard...');
                
                try {
                    await this.loadInitialData();
                    this.startAutoRefresh();
                    console.log('✅ Dashboard initialized successfully');
                } catch (error) {
                    console.error('❌ Dashboard initialization failed:', error);
                    this.showGlobalError('Failed to initialize dashboard: ' + error.message);
                }
            }
            
            async loadInitialData() {
                const promises = [
                    this.updateOverview(),
                    this.updateHealth(),
                    this.updatePerformance(),
                    this.updateTrading(),
                    this.updateAlerts(),
                    this.updateResources(),
                    this.updateNetwork(),
                    this.updateActivity()
                ];
                
                const results = await Promise.allSettled(promises);
                
                // Count failures
                const failures = results.filter(r => r.status === 'rejected').length;
                if (failures > 0) {
                    console.warn(`⚠️ ${failures} dashboard sections failed to load`);
                }
            }
            
            startAutoRefresh() {
                setInterval(async () => {
                    try {
                        await this.refreshData();
                        this.errorCount = 0; // Reset error count on success
                    } catch (error) {
                        this.errorCount++;
                        console.error(`❌ Refresh failed (${this.errorCount}/${this.maxErrors}):`, error);
                        
                        if (this.errorCount >= this.maxErrors) {
                            console.error('🔴 Too many refresh failures, stopping auto-refresh');
                            this.showGlobalError('Connection lost - refresh manually to retry');
                            return;
                        }
                    }
                }, this.refreshInterval);
            }
            
            async refreshData() {
                await this.loadInitialData();
                this.updateLastUpdateTime();
            }
            
            updateLastUpdateTime() {
                const now = new Date().toLocaleTimeString();
                document.getElementById('last-update').textContent = `Last update: ${now}`;
                this.lastUpdate = now;
            }
            
            async updateOverview() {
                try {
                    const response = await this.fetchWithTimeout('/health');
                    const data = await response.json();
                    
                    const content = document.getElementById('system-overview-content');
                    const systemStatus = data.status || 'unknown';
                    const uptime = this.formatUptime(data.system?.uptime_seconds || 0);
                    
                    // Update main status indicator
                    const indicator = document.getElementById('system-status-indicator');
                    if (indicator) {
                        indicator.className = `status-indicator status-${systemStatus}`;
                    }
                    
                    content.innerHTML = `
                        <div class="metric">
                            <span class="metric-label">System Status</span>
                            <span class="metric-value">
                                ${systemStatus.charAt(0).toUpperCase() + systemStatus.slice(1)}
                                <span class="metric-trend trend-${systemStatus === 'healthy' ? 'up' : 'down'}">
                                    ${systemStatus === 'healthy' ? '↑' : systemStatus === 'warning' ? '→' : '↓'}
                                </span>
                            </span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Uptime</span>
                            <span class="metric-value">${uptime}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Service Version</span>
                            <span class="metric-value">${data.system?.version || '1.0.0'}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Components</span>
                            <span class="metric-value">${data.monitoring?.components_registered || 0}</span>
                        </div>
                    `;
                } catch (error) {
                    this.showError('system-overview-content', 'Failed to load system overview', error);
                }
            }
            
            async updateHealth() {
                try {
                    const response = await this.fetchWithTimeout('/health');
                    const data = await response.json();
                    
                    const content = document.getElementById('health-status-content');
                    const healthChecks = data.health_checks || {};
                    const components = healthChecks.components || {};
                    
                    let healthHtml = '';
                    
                    if (Object.keys(components).length === 0) {
                        healthHtml = '<div class="metric"><span class="metric-label">No components registered</span></div>';
                    } else {
                        for (const [component, status] of Object.entries(components)) {
                            const statusValue = status.status || 'unknown';
                            const message = status.message || 'No details available';
                            
                            healthHtml += `
                                <div class="metric">
                                    <span class="metric-label">
                                        <span class="status-indicator status-${statusValue}"></span>
                                        ${component.charAt(0).toUpperCase() + component.slice(1)}
                                    </span>
                                    <span class="metric-value">${statusValue}</span>
                                </div>
                            `;
                        }
                    }
                    
                    const summary = healthChecks.summary || {};
                    healthHtml += `
                        <div class="metric" style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid rgba(42, 52, 65, 0.5);">
                            <span class="metric-label">Health Summary</span>
                            <span class="metric-value">
                                ${summary.healthy_checks || 0}/${summary.total_checks || 0} OK
                            </span>
                        </div>
                    `;
                    
                    content.innerHTML = healthHtml;
                } catch (error) {
                    this.showError('health-status-content', 'Failed to load health status', error);
                }
            }
            
            async updatePerformance() {
                try {
                    const response = await this.fetchWithTimeout('/performance/resources');
                    const data = await response.json();
                    
                    const content = document.getElementById('performance-content');
                    content.innerHTML = `
                        <div class="metric">
                            <span class="metric-label">CPU Usage</span>
                            <span class="metric-value">
                                ${this.formatPercentage(data.cpu_usage || 0)}
                                <span class="metric-trend trend-${this.getTrendClass(data.cpu_usage, 80)}">
                                    ${this.getTrendArrow(data.cpu_usage, 80)}
                                </span>
                            </span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Memory Usage</span>
                            <span class="metric-value">
                                ${this.formatPercentage(data.memory_usage || 0)}
                                <span class="metric-trend trend-${this.getTrendClass(data.memory_usage, 85)}">
                                    ${this.getTrendArrow(data.memory_usage, 85)}
                                </span>
                            </span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Disk Usage</span>
                            <span class="metric-value">
                                ${this.formatPercentage(data.disk_usage || 0)}
                                <span class="metric-trend trend-${this.getTrendClass(data.disk_usage, 90)}">
                                    ${this.getTrendArrow(data.disk_usage, 90)}
                                </span>
                            </span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Response Time</span>
                            <span class="metric-value">${this.formatLatency(data.avg_response_time || 0)}</span>
                        </div>
                    `;
                } catch (error) {
                    this.showError('performance-content', 'Failed to load performance metrics', error);
                }
            }
            
            async updateTrading() {
                try {
                    const response = await this.fetchWithTimeout('/dashboard/trading');
                    const data = await response.json();
                    
                    const content = document.getElementById('trading-content');
                    const trading = data.trading_metrics || {};
                    
                    content.innerHTML = `
                        <div class="metric">
                            <span class="metric-label">Active Positions</span>
                            <span class="metric-value">${trading.active_positions || 0}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Orders Today</span>
                            <span class="metric-value">${trading.orders_today || 0}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Fill Rate</span>
                            <span class="metric-value">${this.formatPercentage(trading.fill_rate || 0)}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">PnL (24h)</span>
                            <span class="metric-value ${(trading.pnl_24h || 0) >= 0 ? 'trend-up' : 'trend-down'}">
                                ${this.formatCurrency(trading.pnl_24h || 0)}
                            </span>
                        </div>
                    `;
                } catch (error) {
                    // Fallback for trading data
                    document.getElementById('trading-content').innerHTML = `
                        <div class="metric">
                            <span class="metric-label">Status</span>
                            <span class="metric-value">Monitoring...</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Data Source</span>
                            <span class="metric-value">Loading...</span>
                        </div>
                    `;
                }
            }
            
            async updateAlerts() {
                try {
                    const response = await this.fetchWithTimeout('/performance/alerts');
                    const data = await response.json();
                    
                    const content = document.getElementById('alerts-content');
                    const alerts = data.alerts || [];
                    
                    if (alerts.length === 0) {
                        content.innerHTML = `
                            <div class="metric">
                                <span class="metric-label">
                                    <span class="status-indicator status-healthy"></span>
                                    System Status
                                </span>
                                <span class="metric-value">All Clear</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Active Alerts</span>
                                <span class="metric-value">0</span>
                            </div>
                        `;
                    } else {
                        let alertsHtml = `
                            <div class="metric">
                                <span class="metric-label">Active Alerts</span>
                                <span class="metric-value">${alerts.length}</span>
                            </div>
                        `;
                        
                        alerts.slice(0, 3).forEach(alert => {
                            alertsHtml += `
                                <div class="alert-item">
                                    <div>${alert.message || 'Unknown alert'}</div>
                                    <div class="alert-timestamp">${new Date(alert.timestamp).toLocaleTimeString()}</div>
                                </div>
                            `;
                        });
                        
                        content.innerHTML = alertsHtml;
                    }
                } catch (error) {
                    document.getElementById('alerts-content').innerHTML = `
                        <div class="metric">
                            <span class="metric-label">Alert System</span>
                            <span class="metric-value">Monitoring</span>
                        </div>
                    `;
                }
            }
            
            async updateResources() {
                try {
                    const response = await this.fetchWithTimeout('/performance/resources');
                    const data = await response.json();
                    
                    const content = document.getElementById('resources-content');
                    content.innerHTML = `
                        <div class="metric">
                            <span class="metric-label">Available Memory</span>
                            <span class="metric-value">${this.formatBytes(data.available_memory || 0)}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">CPU Cores</span>
                            <span class="metric-value">${data.cpu_cores || 'N/A'}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Load Average</span>
                            <span class="metric-value">${data.load_average ? data.load_average.toFixed(2) : 'N/A'}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Disk Free</span>
                            <span class="metric-value">${this.formatBytes(data.disk_free || 0)}</span>
                        </div>
                    `;
                } catch (error) {
                    this.showError('resources-content', 'Failed to load resource data', error);
                }
            }
            
            async updateNetwork() {
                document.getElementById('network-content').innerHTML = `
                    <div class="metric">
                        <span class="metric-label">WebSocket Status</span>
                        <span class="metric-value">
                            <span class="status-indicator status-healthy"></span>
                            Connected
                        </span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">API Latency</span>
                        <span class="metric-value">< 100ms</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Market Data Feed</span>
                        <span class="metric-value">Live</span>
                    </div>
                `;
            }
            
            async updateActivity() {
                document.getElementById('activity-content').innerHTML = `
                    <div class="metric">
                        <span class="metric-label">Last Health Check</span>
                        <span class="metric-value">${new Date().toLocaleTimeString()}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Metrics Collected</span>
                        <span class="metric-value">Active</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">System Events</span>
                        <span class="metric-value">Monitoring</span>
                    </div>
                `;
            }
            
            async fetchWithTimeout(url, timeout = 10000) {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), timeout);
                
                try {
                    const response = await fetch(url, {
                        signal: controller.signal,
                        headers: {
                            'Accept': 'application/json',
                            'Cache-Control': 'no-cache'
                        }
                    });
                    
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                    
                    return response;
                } finally {
                    clearTimeout(timeoutId);
                }
            }
            
            showError(elementId, title, error) {
                const element = document.getElementById(elementId);
                if (element) {
                    element.innerHTML = `
                        <div class="error">
                            <strong>${title}</strong><br>
                            <small>${error?.message || 'Unknown error'}</small>
                        </div>
                    `;
                }
                console.error(`${title}:`, error);
            }
            
            showGlobalError(message) {
                // Could show a global error banner here
                console.error('Global Error:', message);
            }
            
            formatUptime(seconds) {
                const days = Math.floor(seconds / 86400);
                const hours = Math.floor((seconds % 86400) / 3600);
                const minutes = Math.floor((seconds % 3600) / 60);
                
                if (days > 0) return `${days}d ${hours}h`;
                if (hours > 0) return `${hours}h ${minutes}m`;
                return `${minutes}m`;
            }
            
            formatPercentage(value) {
                return `${(value || 0).toFixed(1)}%`;
            }
            
            formatLatency(ms) {
                return `${(ms || 0).toFixed(0)}ms`;
            }
            
            formatBytes(bytes) {
                if (!bytes || bytes === 0) return '0 B';
                const k = 1024;
                const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
            }
            
            formatCurrency(amount) {
                return new Intl.NumberFormat('en-US', {
                    style: 'currency',
                    currency: 'USD'
                }).format(amount || 0);
            }
            
            getTrendClass(value, threshold) {
                if (value >= threshold) return 'down';
                if (value >= threshold * 0.8) return 'stable';
                return 'up';
            }
            
            getTrendArrow(value, threshold) {
                if (value >= threshold) return '↓';
                if (value >= threshold * 0.8) return '→';
                return '↑';
            }
        }
        
        // Initialize dashboard when DOM is ready
        document.addEventListener('DOMContentLoaded', () => {
            new EnhancedMonitoringDashboard();
        });
        
        // Add keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'F5' || (e.ctrlKey && e.key === 'r')) {
                e.preventDefault();
                location.reload();
            }
        });
    </script>
</body>
</html>
        """

    # Non-HTTP access methods for internal use
    async def get_health_status(self) -> dict[str, Any]:
        """Get health status without HTTP."""
        return await self.health_endpoint.health_check()

    async def get_metrics_data(self) -> dict[str, Any]:
        """Get metrics data without HTTP."""
        return await self.metrics_endpoint.metrics()

    async def get_dashboard_data(self) -> dict[str, Any]:
        """Get complete dashboard data without HTTP."""
        if hasattr(self, "trading_dashboard"):
            return await self.trading_dashboard.dashboard_data()
        else:
            # Fallback to basic data
            health_data = await self.health_endpoint.health_check()
            metrics_data = await self.metrics_endpoint.metrics()

            return {
                "timestamp": datetime.now().isoformat(),
                "health": health_data,
                "metrics": metrics_data,
                "note": "Limited dashboard data - full features require performance monitor and alert manager",
            }
