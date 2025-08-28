#!/usr/bin/env python3
"""
Production Monitoring System Demonstration.

This script demonstrates the comprehensive monitoring system including:
1. Health checks for all components
2. Metrics collection and aggregation
3. Performance monitoring and analytics
4. Error rate tracking and alerting
5. Operational dashboards and endpoints
6. Database connection monitoring
7. Trading performance metrics
"""

import asyncio
import os
import random
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# Mock imports for demo purposes
class MockDatabase:
    def __init__(self):
        self.database_path = "demo_bot.db"
        self.connection_count = 0

    async def health_check(self):
        return {
            "status": "healthy",
            "message": "Database connection is healthy",
            "details": {"connections": self.connection_count},
        }


class MockWebSocketManager:
    def __init__(self):
        self.connection_state = "connected"
        self.is_running = True
        self.callbacks = {}

    def add_connect_callback(self, callback):
        self.callbacks.setdefault("connect", []).append(callback)

    def add_disconnect_callback(self, callback):
        self.callbacks.setdefault("disconnect", []).append(callback)

    def add_error_callback(self, callback):
        self.callbacks.setdefault("error", []).append(callback)

    def add_message_callback(self, callback):
        self.callbacks.setdefault("message", []).append(callback)

    async def health_check(self):
        return {
            "status": "healthy",
            "message": "WebSocket connection is active",
            "details": {"state": self.connection_state},
        }


class MockOrderClient:
    def __init__(self):
        self.client_ready = True
        self.exception_stats = {"recent_exceptions_1h": 2, "total_exception_types": 3}

    async def health_check(self):
        return {
            "status": "healthy",
            "message": "Order client is ready",
            "details": {"ready": self.client_ready},
        }

    def get_exception_statistics(self):
        return self.exception_stats

    def get_recent_exception_details(self, minutes):
        return []


# Import monitoring system
try:
    from inkedup_bot.monitoring.integration import (
        MonitoringConfig,
        ProductionMonitoringSystem,
    )

    MONITORING_AVAILABLE = True
except ImportError as e:
    print(f"Monitoring system import failed: {e}")
    MONITORING_AVAILABLE = False


async def demonstrate_monitoring_system():
    """Demonstrate the complete production monitoring system."""

    print("🚀 Production Monitoring System Demonstration")
    print("=" * 60)

    if not MONITORING_AVAILABLE:
        print("⚠️  Monitoring system not available - showing conceptual demonstration")
        await demonstrate_monitoring_concepts()
        return

    # Initialize monitoring system
    config = MonitoringConfig(
        health_check_interval=10.0,
        metrics_collection_interval=5.0,
        performance_sampling_rate=1.0,
        enable_persistent_metrics=True,
    )

    monitoring_system = ProductionMonitoringSystem(
        config=config, enable_http_server=True, http_port=8080
    )

    print("✅ Monitoring system initialized")

    # Create mock components
    mock_db = MockDatabase()
    mock_ws = MockWebSocketManager()
    mock_order_client = MockOrderClient()

    # Register components
    monitoring_system.register_database(mock_db)
    monitoring_system.register_websocket(mock_ws)
    monitoring_system.register_order_client(mock_order_client)
    monitoring_system.register_strategy("arbitrage")
    monitoring_system.register_strategy("momentum")

    print("✅ Components registered for monitoring")

    try:
        # Start monitoring system
        await monitoring_system.start()
        print("✅ Monitoring system started")

        # Demonstrate monitoring features
        await demonstrate_health_checks(monitoring_system)
        await demonstrate_metrics_collection(monitoring_system)
        await demonstrate_performance_monitoring(monitoring_system)
        await demonstrate_error_tracking(monitoring_system)
        await demonstrate_alerts(monitoring_system)
        await demonstrate_dashboards(monitoring_system)

    finally:
        # Stop monitoring system
        await monitoring_system.stop()
        print("✅ Monitoring system stopped")


async def demonstrate_health_checks(monitoring_system):
    """Demonstrate comprehensive health checks."""

    print("\n🏥 1. HEALTH CHECK SYSTEM DEMONSTRATION")
    print("=" * 50)

    # Run health checks
    print("Running comprehensive health checks...")

    health_status = monitoring_system.get_system_status()
    health_data = health_status.get("monitoring_system", {}).get("health", {})

    print(
        f"✅ Overall Health Status: {health_data.get('overall_status', 'unknown').upper()}"
    )

    # Show component health
    components = health_data.get("components", {})
    print(f"📊 Component Health Summary ({len(components)} components):")

    for component, status in components.items():
        status_emoji = (
            "✅"
            if status.get("status") == "healthy"
            else "⚠️" if status.get("status") == "warning" else "❌"
        )
        print(f"   {status_emoji} {component}: {status.get('status', 'unknown')}")
        if status.get("message"):
            print(f"      └─ {status['message']}")

    # Show health check summary
    summary = health_data.get("summary", {})
    print("\n📈 Health Check Statistics:")
    print(f"   Total checks: {summary.get('total_checks', 0)}")
    print(f"   Healthy: {summary.get('healthy_checks', 0)}")
    print(f"   Warnings: {summary.get('warning_checks', 0)}")
    print(f"   Unhealthy: {summary.get('unhealthy_checks', 0)}")


async def demonstrate_metrics_collection(monitoring_system):
    """Demonstrate comprehensive metrics collection."""

    print("\n📊 2. METRICS COLLECTION DEMONSTRATION")
    print("=" * 50)

    # Simulate some trading activity
    print("Simulating trading activity for metrics collection...")

    # Record various events
    for i in range(20):
        # Simulate order placement
        if monitoring_system.order_client_integration:
            monitoring_system.order_client_integration.record_order_placed(
                order_id=f"order_{i}",
                order_type="limit",
                market=f"market_{i % 3}",
                amount=100.0 + random.random() * 900,
                placement_time=random.uniform(50, 200),  # 50-200ms
            )

            # Some orders get filled
            if random.random() > 0.3:
                monitoring_system.order_client_integration.record_order_filled(
                    order_id=f"order_{i}",
                    order_type="limit",
                    market=f"market_{i % 3}",
                    fill_time=random.uniform(1000, 5000),  # 1-5 seconds
                    expected_price=100.0,
                    actual_price=100.0 + random.uniform(-0.5, 0.5),
                )

        # Simulate database queries
        if monitoring_system.database_integration:
            monitoring_system.database_integration.record_query(
                query_type="SELECT",
                duration=random.uniform(10, 100),  # 10-100ms
                success=random.random() > 0.05,  # 95% success rate
            )

        # Simulate strategy execution
        if monitoring_system.strategy_integration:
            monitoring_system.strategy_integration.record_strategy_execution(
                strategy_name=random.choice(["arbitrage", "momentum"]),
                signal_type=random.choice(["buy", "sell", "hold"]),
                execution_time=random.uniform(20, 150),  # 20-150ms
                success=random.random() > 0.1,  # 90% success rate
            )

        await asyncio.sleep(0.1)  # Small delay

    # Get metrics summary
    print("\n📈 Collected Metrics Summary:")

    system_status = monitoring_system.get_system_status()
    metrics_data = system_status.get("monitoring_system", {}).get("metrics", {})

    # Show counters
    counters = metrics_data.get("counters", {})
    if counters:
        print("   📊 Counters:")
        for name, value in list(counters.items())[:5]:  # Show first 5
            print(f"      {name}: {value}")
        if len(counters) > 5:
            print(f"      ... and {len(counters) - 5} more")

    # Show gauges
    gauges = metrics_data.get("gauges", {})
    if gauges:
        print("   🎯 Gauges:")
        for name, value in list(gauges.items())[:3]:  # Show first 3
            print(f"      {name}: {value}")

    # Show timers
    timers = metrics_data.get("timers", {})
    if timers:
        print("   ⏱️  Timers:")
        for name, timer_data in list(timers.items())[:3]:  # Show first 3
            percentiles = timer_data.get("percentiles", {})
            p95 = percentiles.get(95, 0)
            print(
                f"      {name}: {timer_data.get('mean', 0):.2f}ms avg, {p95:.2f}ms p95"
            )


async def demonstrate_performance_monitoring(monitoring_system):
    """Demonstrate performance monitoring capabilities."""

    print("\n⚡ 3. PERFORMANCE MONITORING DEMONSTRATION")
    print("=" * 50)

    # Get performance data
    system_status = monitoring_system.get_system_status()
    performance_data = system_status.get("performance", {})

    # Show system resources
    system_resources = performance_data.get("system_resources", {})
    if system_resources:
        current = system_resources.get("current", {})
        print("🖥️  Current System Resources:")
        print(f"   CPU Usage: {current.get('cpu_percent', 0):.1f}%")
        print(f"   Memory Usage: {current.get('memory_percent', 0):.1f}%")
        print(f"   Memory (Process): {current.get('memory_mb', 0):.1f}MB")
        print(f"   Open Connections: {current.get('open_connections', 0)}")

        # Show alerts if any
        alerts = system_resources.get("alerts", [])
        if alerts:
            print("   🚨 Resource Alerts:")
            for alert in alerts:
                print(f"      ⚠️  {alert}")

    # Show trading performance
    trading_perf = performance_data.get("trading_performance", {})
    if trading_perf:
        print("\n📈 Trading Performance Metrics:")

        # Latency metrics
        latency_metrics = trading_perf.get("latency_metrics", {})
        for metric_name, latency_data in latency_metrics.items():
            if latency_data.get("count", 0) > 0:
                percentiles = latency_data.get("percentiles", {})
                print(f"   🎯 {metric_name}:")
                print(f"      Mean: {latency_data.get('mean', 0):.2f}ms")
                print(f"      P95: {percentiles.get(95, 0):.2f}ms")
                print(f"      Count: {latency_data.get('count', 0)}")

        # Fill rates
        fill_rates = trading_perf.get("fill_rates", {})
        if fill_rates:
            print("   📊 Order Fill Rates:")
            for market, fill_data in fill_rates.items():
                print(
                    f"      {market}: {fill_data.get('fill_rate_under_10s', 0):.1f}% under 10s"
                )

        # Slippage analysis
        slippage = trading_perf.get("slippage_analysis", {})
        if slippage:
            print("   💰 Price Slippage Analysis:")
            for market, slip_data in slippage.items():
                print(
                    f"      {market}: {slip_data.get('average_slippage', 0):.3f}% avg"
                )


async def demonstrate_error_tracking(monitoring_system):
    """Demonstrate error rate tracking and analysis."""

    print("\n🔍 4. ERROR TRACKING AND ANALYSIS DEMONSTRATION")
    print("=" * 50)

    # Simulate some errors
    print("Simulating various error scenarios...")

    for i in range(30):
        # Record events with some failures
        success = random.random() > 0.15  # 85% success rate

        monitoring_system.alert_manager.record_event(
            component="order_client",
            operation="place_order",
            success=success,
            duration_ms=random.uniform(50, 200),
            tags={"market": f"market_{i % 3}"},
        )

        # Database operations
        db_success = random.random() > 0.05  # 95% success rate
        monitoring_system.alert_manager.record_event(
            component="database",
            operation="query",
            success=db_success,
            duration_ms=random.uniform(10, 100),
        )

        await asyncio.sleep(0.05)

    # Get error rates
    print("\n📊 Error Rate Analysis:")
    error_rates = monitoring_system.alert_manager.get_error_rates()

    for operation, error_data in error_rates.items():
        error_rate = error_data.get("error_rate_percent", 0)
        total_events = error_data.get("total_events", 0)
        trend = error_data.get("trend", "unknown")

        status_emoji = "🔴" if error_rate > 10 else "🟡" if error_rate > 5 else "🟢"
        print(f"   {status_emoji} {operation}:")
        print(f"      Error Rate: {error_rate:.2f}%")
        print(f"      Total Events: {total_events}")
        print(f"      Trend: {trend}")
        print(f"      Errors: {error_data.get('total_errors', 0)}")


async def demonstrate_alerts(monitoring_system):
    """Demonstrate alerting system."""

    print("\n🚨 5. ALERTING SYSTEM DEMONSTRATION")
    print("=" * 50)

    # Get current alerts
    alert_summary = monitoring_system.alert_manager.get_alert_summary()
    active_alerts = monitoring_system.alert_manager.get_active_alerts()

    print("📋 Alert System Status:")
    print(
        f"   Total Active Alerts: {alert_summary.get('active_alerts', {}).get('total', 0)}"
    )

    alert_by_level = alert_summary.get("active_alerts", {}).get("by_level", {})
    if alert_by_level:
        for level, count in alert_by_level.items():
            emoji = {
                "critical": "🔴",
                "error": "🟠",
                "warning": "🟡",
                "info": "🔵",
            }.get(level, "⚪")
            print(f"   {emoji} {level.upper()}: {count}")

    # Show configured alerts
    configured = alert_summary.get("configured_alerts", {})
    print("\n⚙️  Configured Alert Rules:")
    print(f"   Threshold Alerts: {configured.get('threshold_alerts', 0)}")
    print(f"   Error Rate Alerts: {configured.get('error_rate_alerts', 0)}")
    print(f"   Performance Alerts: {configured.get('performance_alerts', 0)}")

    # Show active alerts if any
    if active_alerts:
        print("\n🚨 Active Alerts:")
        for alert in active_alerts[:3]:  # Show first 3
            level_emoji = {
                "critical": "🔴",
                "error": "🟠",
                "warning": "🟡",
                "info": "🔵",
            }.get(alert.get("level"), "⚪")
            print(f"   {level_emoji} {alert.get('title', 'Unknown')}")
            print(f"      Component: {alert.get('component', 'unknown')}")
            print(f"      Message: {alert.get('message', 'No message')}")
            print(f"      Occurrences: {alert.get('occurrence_count', 1)}")
    else:
        print("\n✅ No active alerts - system is healthy!")


async def demonstrate_dashboards(monitoring_system):
    """Demonstrate dashboard and API endpoints."""

    print("\n📊 6. OPERATIONAL DASHBOARDS DEMONSTRATION")
    print("=" * 50)

    # Show HTTP server status
    http_info = monitoring_system.get_system_status().get("http_server", {})

    print("🌐 HTTP Dashboard Server:")
    print(f"   Enabled: {http_info.get('enabled', False)}")
    print(f"   Running: {http_info.get('running', False)}")
    print(f"   Port: {http_info.get('port', 8080)}")

    if http_info.get("running"):
        base_url = f"http://localhost:{http_info.get('port', 8080)}"
        print("\n📋 Available Endpoints:")
        print(f"   🏥 Health Check: {base_url}/health")
        print(f"   📊 Metrics: {base_url}/metrics")
        print(f"   ⚡ Performance: {base_url}/performance")
        print(f"   📈 Dashboard: {base_url}/dashboard")
        print(f"   🎯 Trading Overview: {base_url}/dashboard/trading")
        print(f"   📖 API Documentation: {base_url}/")

    # Get dashboard data directly
    try:
        dashboard_data = await monitoring_system.dashboard_manager.get_dashboard_data()

        print("\n📊 Dashboard Data Summary:")
        health = dashboard_data.get("health", {})
        print(f"   Overall Health: {health.get('overall_status', 'unknown').upper()}")

        metrics = dashboard_data.get("metrics", {})
        print(
            f"   Metrics Collected: {len(metrics.get('counters', {})) + len(metrics.get('gauges', {}))}"
        )

        alerts = dashboard_data.get("alerts", {})
        active_count = (
            alerts.get("summary", {}).get("active_alerts", {}).get("total", 0)
        )
        print(f"   Active Alerts: {active_count}")

    except Exception as e:
        print(f"   ⚠️  Dashboard data unavailable: {e}")


async def demonstrate_monitoring_concepts():
    """Demonstrate monitoring system concepts when full system isn't available."""

    print("📋 MONITORING SYSTEM CONCEPTS DEMONSTRATION")
    print("=" * 60)

    print("\n✨ Core Monitoring Components:")
    print("   🏗️  MonitoringManager - Central coordination and metrics collection")
    print("   🏥 HealthChecker - Comprehensive health monitoring for all components")
    print(
        "   📊 MetricsCollector - Time-series metrics with counters, gauges, histograms"
    )
    print("   ⚡ PerformanceMonitor - Latency tracking and resource utilization")
    print(
        "   🚨 AlertManager - Intelligent alerting with threshold and error rate detection"
    )
    print("   📊 DashboardManager - HTTP endpoints and operational dashboards")

    print("\n🏥 Health Check System:")
    print("   ✅ Database connectivity and performance validation")
    print("   ✅ WebSocket connection status and message flow monitoring")
    print("   ✅ Order client readiness and exception tracking")
    print("   ✅ System resource utilization (CPU, memory, disk)")
    print("   ✅ Component-specific health with automatic recovery suggestions")

    print("\n📊 Metrics Collection Framework:")
    print("   📈 Trading Metrics:")
    print("      • Orders placed/filled/cancelled/failed with timing")
    print("      • Position tracking and P&L monitoring")
    print("      • Slippage analysis and fill rate tracking")
    print("      • Strategy performance with success rates")

    print("   🖥️  System Metrics:")
    print("      • CPU, memory, disk, and network utilization")
    print("      • Process-specific resource consumption")
    print("      • HTTP request timing and error rates")
    print("      • Database query performance and connection pooling")

    print("   🕐 Time-Series Support:")
    print("      • Counters for monotonically increasing values")
    print("      • Gauges for current point-in-time values")
    print("      • Histograms for value distribution analysis")
    print("      • Timers with percentile calculations (P50, P90, P95, P99)")

    print("\n⚡ Performance Monitoring:")
    print("   📊 Latency Tracking:")
    print("      • Order placement latency with percentile analysis")
    print("      • Market data processing latency")
    print("      • Strategy execution timing")
    print("      • Database query performance")

    print("   🔄 Throughput Monitoring:")
    print("      • Orders per second across different markets")
    print("      • Market data update rates")
    print("      • Trade execution throughput")
    print("      • System event processing rates")

    print("   💻 Resource Monitoring:")
    print("      • Real-time CPU and memory utilization")
    print("      • Disk I/O and network traffic analysis")
    print("      • Process-specific resource consumption")
    print("      • Resource trend analysis and alerting")

    print("\n🚨 Error Tracking and Alerting:")
    print("   📊 Error Rate Analysis:")
    print("      • Component-specific error rates with trend analysis")
    print("      • Configurable time windows and minimum event thresholds")
    print("      • Error classification and pattern detection")
    print("      • Automatic recovery suggestions")

    print("   🔔 Alert Types:")
    print("      • Threshold Alerts - CPU, memory, latency thresholds")
    print("      • Error Rate Alerts - Sustained error rate violations")
    print("      • Performance Alerts - Latency degradation detection")
    print("      • Custom Alerts - Business logic specific conditions")

    print("   🎛️  Alert Management:")
    print("      • Alert acknowledgment and resolution tracking")
    print("      • Alert suppression and escalation rules")
    print("      • Integration with external notification systems")
    print("      • Historical alert analysis and reporting")

    print("\n📊 Operational Dashboards:")
    print("   🌐 HTTP API Endpoints:")
    print("      • /health - Comprehensive health status")
    print("      • /metrics - Real-time metrics in JSON/Prometheus format")
    print("      • /performance - Performance analytics and trends")
    print("      • /dashboard - Complete operational overview")

    print("   📱 Real-Time Monitoring:")
    print("      • Live system health with component status")
    print("      • Trading performance metrics and analytics")
    print("      • Resource utilization trends and forecasting")
    print("      • Active alert management and resolution")

    print("\n🔧 Integration Capabilities:")
    print("   🗄️  Database Monitoring:")
    print("      • Connection health and query performance")
    print("      • Transaction timing and rollback tracking")
    print("      • Lock wait analysis and deadlock detection")
    print("      • Database-specific metrics and alerts")

    print("   🔌 WebSocket Monitoring:")
    print("      • Connection state tracking and stability")
    print("      • Message throughput and processing latency")
    print("      • Reconnection success rates and timing")
    print("      • Subscription state preservation")

    print("   📈 Trading System Integration:")
    print("      • Order lifecycle tracking and analysis")
    print("      • Strategy performance monitoring")
    print("      • Risk metric calculation and alerting")
    print("      • Market data quality assessment")

    print("\n🎯 PRODUCTION READY FEATURES:")
    print("   ✅ Zero-downtime monitoring with async architecture")
    print("   ✅ High-performance metrics collection with minimal overhead")
    print("   ✅ Configurable retention policies and data management")
    print("   ✅ Prometheus compatibility for external monitoring systems")
    print("   ✅ Comprehensive error handling with graceful degradation")
    print("   ✅ Extensible architecture for custom metrics and alerts")
    print("   ✅ Production-grade logging and debugging capabilities")
    print("   ✅ Multi-component health correlation and root cause analysis")

    print("\n🚀 The monitoring system provides enterprise-grade observability")
    print("   for high-frequency trading operations with comprehensive")
    print("   health checks, performance analytics, and intelligent alerting!")


async def main():
    """Main demonstration function."""

    print("🎯 InkedUp Polymarket Bot - Production Monitoring System")
    print("=" * 60)
    print(f"Demo started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        await demonstrate_monitoring_system()
    except KeyboardInterrupt:
        print("\n\n⚡ Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed with error: {e}")
        import traceback

        traceback.print_exc()

    print(f"\n🏁 Demo completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
