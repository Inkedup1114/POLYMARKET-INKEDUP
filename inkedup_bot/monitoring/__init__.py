"""
Production monitoring system for InkedUp Polymarket bot.

This module provides comprehensive monitoring capabilities including:
- System health checks
- Metrics collection and aggregation
- Performance monitoring
- Error rate tracking
- Database connection monitoring
- Trading performance analytics
"""

from .alerts import (
    Alert,
    AlertLevel,
    AlertManager,
    ErrorRateAlert,
    PerformanceAlert,
    ThresholdAlert,
)
from .core import HealthChecker, MetricsCollector, MonitoringManager
from .dashboard import (
    DashboardManager,
    HealthEndpoint,
    MetricsEndpoint,
    PerformanceEndpoint,
    TradingDashboard,
)
from .health import (
    ComponentHealth,
    DatabaseHealthCheck,
    HealthCheck,
    HealthStatus,
    OrderClientHealthCheck,
    SystemHealth,
    WebSocketHealthCheck,
)
from .metrics import (
    Counter,
    DatabaseMetrics,
    Gauge,
    Histogram,
    Metric,
    MetricType,
    SystemMetrics,
    Timer,
    TradingMetrics,
)
from .performance import (
    LatencyTracker,
    PerformanceMonitor,
    ResourceMonitor,
    ThroughputMonitor,
    TradingPerformanceTracker,
)

__all__ = [
    # Core monitoring
    "MonitoringManager",
    "MetricsCollector",
    "HealthChecker",
    # Health checks
    "HealthCheck",
    "HealthStatus",
    "ComponentHealth",
    "SystemHealth",
    "DatabaseHealthCheck",
    "WebSocketHealthCheck",
    "OrderClientHealthCheck",
    # Metrics
    "MetricType",
    "Metric",
    "Counter",
    "Gauge",
    "Histogram",
    "Timer",
    "TradingMetrics",
    "SystemMetrics",
    "DatabaseMetrics",
    # Performance monitoring
    "PerformanceMonitor",
    "LatencyTracker",
    "ThroughputMonitor",
    "ResourceMonitor",
    "TradingPerformanceTracker",
    # Alerts
    "AlertLevel",
    "Alert",
    "AlertManager",
    "ThresholdAlert",
    "ErrorRateAlert",
    "PerformanceAlert",
    # Dashboard
    "DashboardManager",
    "HealthEndpoint",
    "MetricsEndpoint",
    "PerformanceEndpoint",
    "TradingDashboard",
]
