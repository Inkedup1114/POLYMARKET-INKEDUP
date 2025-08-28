"""
Performance Dashboards with Real-time Visualization

Comprehensive performance monitoring dashboards providing real-time metrics
visualization, system health status, and operational insights.
"""

import json
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .database_performance_metrics import DatabasePerformanceTracker
from .order_execution_metrics import OrderExecutionPerformanceTracker
from .performance_metrics import PerformanceMetricsTracker
from .signal_processing_metrics import SignalProcessingPerformanceTracker

logger = logging.getLogger(__name__)


class DashboardType(Enum):
    """Types of performance dashboards available"""

    SYSTEM_OVERVIEW = "system_overview"
    TRADING_PERFORMANCE = "trading_performance"
    DATABASE_METRICS = "database_metrics"
    SIGNAL_PROCESSING = "signal_processing"
    ORDER_EXECUTION = "order_execution"
    REAL_TIME_ALERTS = "real_time_alerts"


@dataclass
class DashboardMetric:
    """Individual dashboard metric for visualization"""

    name: str
    value: float
    unit: str
    timestamp: datetime
    component: str
    metric_type: str
    threshold_warning: float | None = None
    threshold_critical: float | None = None
    trend: str | None = None  # "up", "down", "stable"


@dataclass
class DashboardAlert:
    """Dashboard alert for real-time monitoring"""

    id: str
    severity: str  # "info", "warning", "error", "critical"
    component: str
    message: str
    timestamp: datetime
    resolved: bool = False
    acknowledged: bool = False


class PerformanceDashboard:
    """
    Real-time performance dashboard with comprehensive metrics visualization

    Provides HTTP endpoints for accessing performance data, system health,
    and operational metrics with real-time updates.
    """

    def __init__(
        self,
        performance_tracker: PerformanceMetricsTracker | None = None,
        signal_tracker: SignalProcessingPerformanceTracker | None = None,
        order_tracker: OrderExecutionPerformanceTracker | None = None,
        database_tracker: DatabasePerformanceTracker | None = None,
        update_interval_seconds: float = 5.0,
    ):
        # Performance trackers
        self.performance_tracker = performance_tracker or PerformanceMetricsTracker()
        self.signal_tracker = signal_tracker
        self.order_tracker = order_tracker
        self.database_tracker = database_tracker

        # Dashboard configuration
        self.update_interval_seconds = update_interval_seconds
        self.lock = threading.RLock()

        # Real-time data storage
        self.current_metrics: dict[str, DashboardMetric] = {}
        self.metric_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.active_alerts: dict[str, DashboardAlert] = {}
        self.alert_history: deque = deque(maxlen=10000)

        # Dashboard data caches
        self.dashboard_cache: dict[DashboardType, dict[str, Any]] = {}
        self.cache_timestamps: dict[DashboardType, datetime] = {}
        self.cache_ttl_seconds = 2.0  # Cache TTL for performance

        # Background update thread
        self.update_thread = None
        self.running = False

        # Thresholds for alerts
        self.thresholds = {
            "cpu_usage": {"warning": 75.0, "critical": 90.0},
            "memory_usage": {"warning": 80.0, "critical": 95.0},
            "query_latency": {"warning": 100.0, "critical": 500.0},
            "order_latency": {"warning": 50.0, "critical": 200.0},
            "error_rate": {"warning": 5.0, "critical": 15.0},
            "connection_pool_utilization": {"warning": 80.0, "critical": 95.0},
        }

        logger.info("Performance dashboard initialized")

    def start_real_time_updates(self):
        """Start background thread for real-time dashboard updates"""
        if self.running:
            return

        self.running = True
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
        logger.info("Real-time dashboard updates started")

    def stop_real_time_updates(self):
        """Stop background updates"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=2.0)
        logger.info("Real-time dashboard updates stopped")

    def _update_loop(self):
        """Background update loop for real-time metrics"""
        while self.running:
            try:
                self._update_all_metrics()
                self._check_alert_conditions()
                time.sleep(self.update_interval_seconds)
            except Exception as e:
                logger.error(f"Error in dashboard update loop: {e}")
                time.sleep(1.0)  # Brief pause on error

    def _update_all_metrics(self):
        """Update all dashboard metrics from trackers"""
        timestamp = datetime.now()

        with self.lock:
            # Update system metrics
            self._update_system_metrics(timestamp)

            # Update component-specific metrics
            if self.signal_tracker:
                self._update_signal_processing_metrics(timestamp)

            if self.order_tracker:
                self._update_order_execution_metrics(timestamp)

            if self.database_tracker:
                self._update_database_metrics(timestamp)

            # Clear dashboard caches to ensure fresh data
            self.dashboard_cache.clear()
            self.cache_timestamps.clear()

    def _update_system_metrics(self, timestamp: datetime):
        """Update system performance metrics"""
        try:
            # Get latest metrics from performance tracker
            recent_metrics = self.performance_tracker.get_recent_metrics(
                60
            )  # Last minute

            # Process CPU metrics
            cpu_metrics = [
                m for m in recent_metrics if "cpu" in m.get("metric_name", "").lower()
            ]
            if cpu_metrics:
                latest_cpu = cpu_metrics[-1]["value"]
                self._update_metric(
                    "system_cpu_usage",
                    latest_cpu,
                    "%",
                    timestamp,
                    "system",
                    "gauge",
                    self.thresholds["cpu_usage"]["warning"],
                    self.thresholds["cpu_usage"]["critical"],
                )

            # Process memory metrics
            memory_metrics = [
                m
                for m in recent_metrics
                if "memory" in m.get("metric_name", "").lower()
            ]
            if memory_metrics:
                latest_memory = memory_metrics[-1]["value"]
                self._update_metric(
                    "system_memory_usage",
                    latest_memory,
                    "%",
                    timestamp,
                    "system",
                    "gauge",
                    self.thresholds["memory_usage"]["warning"],
                    self.thresholds["memory_usage"]["critical"],
                )

        except Exception as e:
            logger.error(f"Error updating system metrics: {e}")

    def _update_signal_processing_metrics(self, timestamp: datetime):
        """Update signal processing performance metrics"""
        if not self.signal_tracker:
            return

        try:
            # Get signal processing statistics
            stats = self.signal_tracker.get_performance_summary(minutes=10)

            if stats.get("total_signals", 0) > 0:
                # Average processing time
                avg_time = stats.get("avg_processing_time_ms", 0)
                self._update_metric(
                    "signal_avg_processing_time",
                    avg_time,
                    "ms",
                    timestamp,
                    "signal_processor",
                    "gauge",
                )

                # Signal throughput
                throughput = stats.get("signals_per_minute", 0)
                self._update_metric(
                    "signal_throughput",
                    throughput,
                    "signals/min",
                    timestamp,
                    "signal_processor",
                    "gauge",
                )

                # Success rate
                success_rate = stats.get("success_rate", 0) * 100
                self._update_metric(
                    "signal_success_rate",
                    success_rate,
                    "%",
                    timestamp,
                    "signal_processor",
                    "gauge",
                )

        except Exception as e:
            logger.error(f"Error updating signal processing metrics: {e}")

    def _update_order_execution_metrics(self, timestamp: datetime):
        """Update order execution performance metrics"""
        if not self.order_tracker:
            return

        try:
            # Get order execution statistics
            stats = self.order_tracker.get_execution_summary(minutes=10)

            if stats.get("total_orders", 0) > 0:
                # Average execution time
                avg_time = stats.get("avg_execution_time_ms", 0)
                self._update_metric(
                    "order_avg_execution_time",
                    avg_time,
                    "ms",
                    timestamp,
                    "order_client",
                    "gauge",
                    self.thresholds["order_latency"]["warning"],
                    self.thresholds["order_latency"]["critical"],
                )

                # Fill rate
                fill_rate = stats.get("fill_rate", 0) * 100
                self._update_metric(
                    "order_fill_rate",
                    fill_rate,
                    "%",
                    timestamp,
                    "order_client",
                    "gauge",
                )

                # Average slippage
                avg_slippage = stats.get("avg_slippage_bps", 0)
                self._update_metric(
                    "order_avg_slippage",
                    avg_slippage,
                    "bps",
                    timestamp,
                    "order_client",
                    "gauge",
                )

        except Exception as e:
            logger.error(f"Error updating order execution metrics: {e}")

    def _update_database_metrics(self, timestamp: datetime):
        """Update database performance metrics"""
        if not self.database_tracker:
            return

        try:
            # Get database statistics
            query_stats = self.database_tracker.get_query_performance_stats(minutes=10)
            pool_health = self.database_tracker.get_connection_pool_health()

            if query_stats.get("total_queries", 0) > 0:
                # Average query time
                avg_time = query_stats["execution_time_stats"]["avg_ms"]
                self._update_metric(
                    "database_avg_query_time",
                    avg_time,
                    "ms",
                    timestamp,
                    "database",
                    "gauge",
                    self.thresholds["query_latency"]["warning"],
                    self.thresholds["query_latency"]["critical"],
                )

                # Query success rate
                success_rate = query_stats.get("success_rate", 0) * 100
                self._update_metric(
                    "database_success_rate",
                    success_rate,
                    "%",
                    timestamp,
                    "database",
                    "gauge",
                )

                # Queries per minute
                qpm = query_stats["total_queries"] / query_stats["time_range_minutes"]
                self._update_metric(
                    "database_queries_per_minute",
                    qpm,
                    "qpm",
                    timestamp,
                    "database",
                    "gauge",
                )

            # Connection pool utilization
            if pool_health:
                for pool_id, health in pool_health.items():
                    utilization = health.get("utilization", 0) * 100
                    self._update_metric(
                        f"database_pool_{pool_id}_utilization",
                        utilization,
                        "%",
                        timestamp,
                        "database",
                        "gauge",
                        self.thresholds["connection_pool_utilization"]["warning"],
                        self.thresholds["connection_pool_utilization"]["critical"],
                    )

        except Exception as e:
            logger.error(f"Error updating database metrics: {e}")

    def _update_metric(
        self,
        name: str,
        value: float,
        unit: str,
        timestamp: datetime,
        component: str,
        metric_type: str,
        threshold_warning: float | None = None,
        threshold_critical: float | None = None,
    ):
        """Update individual metric with trend calculation"""

        # Calculate trend
        trend = None
        if name in self.metric_history and len(self.metric_history[name]) > 0:
            previous_value = self.metric_history[name][-1].value
            if value > previous_value * 1.05:  # 5% increase
                trend = "up"
            elif value < previous_value * 0.95:  # 5% decrease
                trend = "down"
            else:
                trend = "stable"

        # Create metric
        metric = DashboardMetric(
            name=name,
            value=value,
            unit=unit,
            timestamp=timestamp,
            component=component,
            metric_type=metric_type,
            threshold_warning=threshold_warning,
            threshold_critical=threshold_critical,
            trend=trend,
        )

        # Update current metrics and history
        self.current_metrics[name] = metric
        self.metric_history[name].append(metric)

    def _check_alert_conditions(self):
        """Check metrics against thresholds and generate alerts"""
        timestamp = datetime.now()

        for metric_name, metric in self.current_metrics.items():
            if not metric.threshold_warning and not metric.threshold_critical:
                continue

            alert_id = f"threshold_{metric.component}_{metric_name}"
            current_alert = self.active_alerts.get(alert_id)

            # Check critical threshold
            if metric.threshold_critical and metric.value >= metric.threshold_critical:
                if not current_alert or current_alert.severity != "critical":
                    self._create_alert(
                        alert_id,
                        "critical",
                        metric.component,
                        f"{metric_name} is critically high: {metric.value:.1f}{metric.unit} "
                        f"(threshold: {metric.threshold_critical}{metric.unit})",
                        timestamp,
                    )

            # Check warning threshold
            elif metric.threshold_warning and metric.value >= metric.threshold_warning:
                if not current_alert or current_alert.severity == "info":
                    self._create_alert(
                        alert_id,
                        "warning",
                        metric.component,
                        f"{metric_name} is above warning threshold: {metric.value:.1f}{metric.unit} "
                        f"(threshold: {metric.threshold_warning}{metric.unit})",
                        timestamp,
                    )

            # Clear alert if value is back to normal
            else:
                if current_alert and not current_alert.resolved:
                    self._resolve_alert(alert_id, timestamp)

    def _create_alert(
        self,
        alert_id: str,
        severity: str,
        component: str,
        message: str,
        timestamp: datetime,
    ):
        """Create new alert"""
        alert = DashboardAlert(
            id=alert_id,
            severity=severity,
            component=component,
            message=message,
            timestamp=timestamp,
        )

        self.active_alerts[alert_id] = alert
        self.alert_history.append(alert)

        logger.warning(f"Dashboard alert [{severity}]: {message}")

    def _resolve_alert(self, alert_id: str, timestamp: datetime):
        """Resolve existing alert"""
        if alert_id in self.active_alerts:
            self.active_alerts[alert_id].resolved = True
            logger.info(f"Dashboard alert resolved: {alert_id}")

    def get_dashboard_data(
        self, dashboard_type: DashboardType, force_refresh: bool = False
    ) -> dict[str, Any]:
        """Get dashboard data with caching"""

        # Check cache
        if not force_refresh and dashboard_type in self.dashboard_cache:
            cache_time = self.cache_timestamps.get(dashboard_type)
            if (
                cache_time
                and (datetime.now() - cache_time).total_seconds()
                < self.cache_ttl_seconds
            ):
                return self.dashboard_cache[dashboard_type]

        # Generate fresh data
        if dashboard_type == DashboardType.SYSTEM_OVERVIEW:
            data = self._generate_system_overview()
        elif dashboard_type == DashboardType.TRADING_PERFORMANCE:
            data = self._generate_trading_performance()
        elif dashboard_type == DashboardType.DATABASE_METRICS:
            data = self._generate_database_metrics()
        elif dashboard_type == DashboardType.SIGNAL_PROCESSING:
            data = self._generate_signal_processing_dashboard()
        elif dashboard_type == DashboardType.ORDER_EXECUTION:
            data = self._generate_order_execution_dashboard()
        elif dashboard_type == DashboardType.REAL_TIME_ALERTS:
            data = self._generate_alerts_dashboard()
        else:
            data = {"error": f"Unknown dashboard type: {dashboard_type}"}

        # Cache the data
        self.dashboard_cache[dashboard_type] = data
        self.cache_timestamps[dashboard_type] = datetime.now()

        return data

    def _generate_system_overview(self) -> dict[str, Any]:
        """Generate system overview dashboard"""
        system_metrics = {
            name: asdict(metric)
            for name, metric in self.current_metrics.items()
            if metric.component == "system"
        }

        active_alerts = [
            asdict(alert) for alert in self.active_alerts.values() if not alert.resolved
        ]

        return {
            "dashboard_type": "system_overview",
            "timestamp": datetime.now().isoformat(),
            "system_health": self._calculate_system_health(),
            "metrics": system_metrics,
            "active_alerts_count": len(active_alerts),
            "alerts": active_alerts[:10],  # Last 10 alerts
            "components_status": self._get_components_status(),
        }

    def _generate_trading_performance(self) -> dict[str, Any]:
        """Generate trading performance dashboard"""
        trading_metrics = {
            name: asdict(metric)
            for name, metric in self.current_metrics.items()
            if metric.component in ["order_client", "signal_processor"]
        }

        # Get historical data for charts
        charts_data = {}
        for metric_name in [
            "order_avg_execution_time",
            "order_fill_rate",
            "signal_throughput",
        ]:
            if metric_name in self.metric_history:
                history = list(self.metric_history[metric_name])[-50:]  # Last 50 points
                charts_data[metric_name] = [
                    {"timestamp": m.timestamp.isoformat(), "value": m.value}
                    for m in history
                ]

        return {
            "dashboard_type": "trading_performance",
            "timestamp": datetime.now().isoformat(),
            "metrics": trading_metrics,
            "charts": charts_data,
            "performance_summary": self._calculate_trading_performance_summary(),
        }

    def _generate_database_metrics(self) -> dict[str, Any]:
        """Generate database metrics dashboard"""
        database_metrics = {
            name: asdict(metric)
            for name, metric in self.current_metrics.items()
            if metric.component == "database"
        }

        # Additional database health information
        database_health = {}
        if self.database_tracker:
            database_health = self.database_tracker.get_database_health_summary()

        return {
            "dashboard_type": "database_metrics",
            "timestamp": datetime.now().isoformat(),
            "metrics": database_metrics,
            "health_summary": database_health,
            "connection_pools": self._get_connection_pool_details(),
        }

    def _generate_signal_processing_dashboard(self) -> dict[str, Any]:
        """Generate signal processing dashboard"""
        signal_metrics = {
            name: asdict(metric)
            for name, metric in self.current_metrics.items()
            if metric.component == "signal_processor"
        }

        performance_summary = {}
        if self.signal_tracker:
            performance_summary = self.signal_tracker.get_performance_summary(60)

        return {
            "dashboard_type": "signal_processing",
            "timestamp": datetime.now().isoformat(),
            "metrics": signal_metrics,
            "performance_summary": performance_summary,
            "recent_signals": self._get_recent_signal_activity(),
        }

    def _generate_order_execution_dashboard(self) -> dict[str, Any]:
        """Generate order execution dashboard"""
        order_metrics = {
            name: asdict(metric)
            for name, metric in self.current_metrics.items()
            if metric.component == "order_client"
        }

        execution_summary = {}
        if self.order_tracker:
            execution_summary = self.order_tracker.get_execution_summary(60)

        return {
            "dashboard_type": "order_execution",
            "timestamp": datetime.now().isoformat(),
            "metrics": order_metrics,
            "execution_summary": execution_summary,
            "recent_orders": self._get_recent_order_activity(),
        }

    def _generate_alerts_dashboard(self) -> dict[str, Any]:
        """Generate real-time alerts dashboard"""
        active_alerts = [asdict(alert) for alert in self.active_alerts.values()]
        recent_alerts = list(self.alert_history)[-100:]  # Last 100 alerts

        alert_stats = {
            "total_active": len(active_alerts),
            "critical": len([a for a in active_alerts if a["severity"] == "critical"]),
            "warning": len([a for a in active_alerts if a["severity"] == "warning"]),
            "info": len([a for a in active_alerts if a["severity"] == "info"]),
        }

        return {
            "dashboard_type": "real_time_alerts",
            "timestamp": datetime.now().isoformat(),
            "alert_statistics": alert_stats,
            "active_alerts": active_alerts,
            "recent_alerts": [asdict(alert) for alert in recent_alerts],
        }

    def _calculate_system_health(self) -> str:
        """Calculate overall system health status"""
        critical_alerts = [
            a
            for a in self.active_alerts.values()
            if a.severity == "critical" and not a.resolved
        ]
        warning_alerts = [
            a
            for a in self.active_alerts.values()
            if a.severity == "warning" and not a.resolved
        ]

        if critical_alerts:
            return "critical"
        elif warning_alerts:
            return "warning"
        else:
            return "healthy"

    def _get_components_status(self) -> dict[str, str]:
        """Get status of all monitored components"""
        components = {}

        for metric_name, metric in self.current_metrics.items():
            component = metric.component
            if component not in components:
                components[component] = "healthy"

            # Check if this metric indicates problems
            if metric.threshold_critical and metric.value >= metric.threshold_critical:
                components[component] = "critical"
            elif (
                metric.threshold_warning
                and metric.value >= metric.threshold_warning
                and components[component] == "healthy"
            ):
                components[component] = "warning"

        return components

    def _calculate_trading_performance_summary(self) -> dict[str, Any]:
        """Calculate trading performance summary"""
        summary = {
            "overall_performance": "unknown",
            "key_metrics": {},
            "recommendations": [],
        }

        # Analyze key metrics
        order_latency = self.current_metrics.get("order_avg_execution_time")
        fill_rate = self.current_metrics.get("order_fill_rate")
        signal_throughput = self.current_metrics.get("signal_throughput")

        if order_latency:
            summary["key_metrics"]["execution_latency"] = f"{order_latency.value:.1f}ms"
            if order_latency.value > 100:
                summary["recommendations"].append(
                    "Consider optimizing order execution latency"
                )

        if fill_rate:
            summary["key_metrics"]["fill_rate"] = f"{fill_rate.value:.1f}%"
            if fill_rate.value < 90:
                summary["recommendations"].append("Investigate low order fill rates")

        if signal_throughput:
            summary["key_metrics"][
                "signal_throughput"
            ] = f"{signal_throughput.value:.1f}/min"

        return summary

    def _get_connection_pool_details(self) -> dict[str, Any]:
        """Get detailed connection pool information"""
        if not self.database_tracker:
            return {}

        return self.database_tracker.get_connection_pool_health()

    def _get_recent_signal_activity(self) -> list[dict[str, Any]]:
        """Get recent signal processing activity"""
        if not self.signal_tracker:
            return []

        # This would get recent signal data from the tracker
        return []  # Placeholder

    def _get_recent_order_activity(self) -> list[dict[str, Any]]:
        """Get recent order execution activity"""
        if not self.order_tracker:
            return []

        # This would get recent order data from the tracker
        return []  # Placeholder


class DashboardHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler for dashboard endpoints"""

    def __init__(self, dashboard: PerformanceDashboard, *args, **kwargs):
        self.dashboard = dashboard
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle GET requests for dashboard data"""
        try:
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            query_params = parse_qs(parsed_path.query)

            if path == "/":
                self._serve_dashboard_index()
            elif path.startswith("/api/dashboard/"):
                dashboard_type = path.split("/")[-1]
                self._serve_dashboard_data(dashboard_type, query_params)
            elif path == "/api/metrics":
                self._serve_all_metrics()
            elif path == "/api/health":
                self._serve_health_check()
            elif path.startswith("/static/"):
                self._serve_static_file(path)
            else:
                self._send_404()

        except Exception as e:
            logger.error(f"Dashboard HTTP handler error: {e}")
            self._send_500(str(e))

    def _serve_dashboard_index(self):
        """Serve main dashboard HTML page"""
        html = self._generate_dashboard_html()
        self._send_json_response({"html": html})

    def _serve_dashboard_data(
        self, dashboard_type: str, query_params: dict[str, list[str]]
    ):
        """Serve dashboard data as JSON"""
        try:
            dashboard_enum = DashboardType(dashboard_type)
            force_refresh = query_params.get("refresh", ["false"])[0].lower() == "true"

            data = self.dashboard.get_dashboard_data(dashboard_enum, force_refresh)
            self._send_json_response(data)

        except ValueError:
            self._send_json_response(
                {"error": f"Unknown dashboard type: {dashboard_type}"}, 400
            )

    def _serve_all_metrics(self):
        """Serve all current metrics"""
        metrics = {
            name: asdict(metric)
            for name, metric in self.dashboard.current_metrics.items()
        }
        self._send_json_response(
            {"metrics": metrics, "timestamp": datetime.now().isoformat()}
        )

    def _serve_health_check(self):
        """Serve health check endpoint"""
        health = {
            "status": self.dashboard._calculate_system_health(),
            "timestamp": datetime.now().isoformat(),
            "components": self.dashboard._get_components_status(),
            "active_alerts": len(
                [a for a in self.dashboard.active_alerts.values() if not a.resolved]
            ),
        }
        self._send_json_response(health)

    def _serve_static_file(self, path: str):
        """Serve static files (placeholder)"""
        self._send_404()

    def _send_json_response(self, data: Any, status_code: int = 200):
        """Send JSON response"""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def _send_404(self):
        """Send 404 response"""
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Not found"}).encode())

    def _send_500(self, error_message: str):
        """Send 500 response"""
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": error_message}).encode())

    def _generate_dashboard_html(self) -> str:
        """Generate basic dashboard HTML"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Performance Dashboard</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .dashboard { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
                .metric-card { border: 1px solid #ddd; padding: 15px; border-radius: 5px; }
                .metric-value { font-size: 2em; font-weight: bold; }
                .metric-trend.up { color: green; }
                .metric-trend.down { color: red; }
                .metric-trend.stable { color: blue; }
                .alert.critical { background-color: #ffebee; border-left: 4px solid #f44336; }
                .alert.warning { background-color: #fff3e0; border-left: 4px solid #ff9800; }
                .alert.info { background-color: #e3f2fd; border-left: 4px solid #2196f3; }
            </style>
        </head>
        <body>
            <h1>InkedUp Trading Bot - Performance Dashboard</h1>
            <div id="dashboard-content">
                <p>Loading dashboard data...</p>
            </div>
            <script>
                // Basic JavaScript for dashboard functionality
                async function loadDashboard() {
                    try {
                        const response = await fetch('/api/dashboard/system_overview');
                        const data = await response.json();
                        updateDashboard(data);
                    } catch (error) {
                        console.error('Error loading dashboard:', error);
                        document.getElementById('dashboard-content').innerHTML = 
                            '<p style="color: red;">Error loading dashboard data</p>';
                    }
                }
                
                function updateDashboard(data) {
                    const content = document.getElementById('dashboard-content');
                    let html = '<div class="dashboard">';
                    
                    // System health
                    html += `<div class="metric-card">
                        <h3>System Health</h3>
                        <div class="metric-value" style="color: ${data.system_health === 'healthy' ? 'green' : 
                            data.system_health === 'warning' ? 'orange' : 'red'}">${data.system_health.toUpperCase()}</div>
                    </div>`;
                    
                    // Metrics
                    Object.entries(data.metrics || {}).forEach(([name, metric]) => {
                        html += `<div class="metric-card">
                            <h3>${name.replace(/_/g, ' ').toUpperCase()}</h3>
                            <div class="metric-value">${metric.value.toFixed(2)} ${metric.unit}</div>
                            <div class="metric-trend ${metric.trend || ''}">${metric.trend || ''}</div>
                        </div>`;
                    });
                    
                    // Alerts
                    if (data.alerts && data.alerts.length > 0) {
                        html += '<div class="metric-card"><h3>Active Alerts</h3>';
                        data.alerts.forEach(alert => {
                            html += `<div class="alert ${alert.severity}">
                                <strong>${alert.severity.toUpperCase()}</strong>: ${alert.message}
                            </div>`;
                        });
                        html += '</div>';
                    }
                    
                    html += '</div>';
                    content.innerHTML = html;
                }
                
                // Load dashboard on page load and refresh every 5 seconds
                loadDashboard();
                setInterval(loadDashboard, 5000);
            </script>
        </body>
        </html>
        """

    def log_message(self, format, *args):
        """Override to reduce log noise"""
        pass


class DashboardServer:
    """HTTP server for performance dashboard"""

    def __init__(
        self, dashboard: PerformanceDashboard, host: str = "localhost", port: int = 8080
    ):
        self.dashboard = dashboard
        self.host = host
        self.port = port
        self.server = None
        self.server_thread = None

    def start(self):
        """Start dashboard HTTP server"""
        handler_class = lambda *args, **kwargs: DashboardHTTPHandler(
            self.dashboard, *args, **kwargs
        )

        self.server = HTTPServer((self.host, self.port), handler_class)
        self.server_thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.server_thread.start()

        logger.info(f"Dashboard server started at http://{self.host}:{self.port}")

    def stop(self):
        """Stop dashboard HTTP server"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()

        if self.server_thread:
            self.server_thread.join(timeout=2.0)

        logger.info("Dashboard server stopped")


def create_performance_dashboard(
    performance_tracker: PerformanceMetricsTracker | None = None,
    signal_tracker: SignalProcessingPerformanceTracker | None = None,
    order_tracker: OrderExecutionPerformanceTracker | None = None,
    database_tracker: DatabasePerformanceTracker | None = None,
    start_server: bool = True,
    server_host: str = "localhost",
    server_port: int = 8080,
) -> Tuple[PerformanceDashboard, DashboardServer | None]:
    """
    Create and optionally start performance dashboard with HTTP server

    Returns:
        Tuple of (dashboard, server) where server is None if start_server=False
    """
    dashboard = PerformanceDashboard(
        performance_tracker=performance_tracker,
        signal_tracker=signal_tracker,
        order_tracker=order_tracker,
        database_tracker=database_tracker,
    )

    dashboard.start_real_time_updates()

    server = None
    if start_server:
        server = DashboardServer(dashboard, server_host, server_port)
        server.start()

    return dashboard, server
