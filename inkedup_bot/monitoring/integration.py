"""
Monitoring system integration with all bot components.

This module provides the main integration layer that connects the monitoring
system with all bot components including database, WebSocket, order client,
and trading strategies.
"""

import logging
from datetime import datetime
from typing import Any

from .alerts import AlertManager, ErrorRateAlert, PerformanceAlert, ThresholdAlert
from .core import MonitoringConfig, MonitoringManager
from .dashboard import DashboardManager
from .health import (
    ComponentHealth,
    DatabaseHealthCheck,
    OrderClientHealthCheck,
    SystemHealth,
    SystemResourceHealthCheck,
    WebSocketHealthCheck,
)
from .metrics import DatabaseMetrics, TradingMetrics
from .performance import PerformanceMonitor

logger = logging.getLogger(__name__)


class DatabaseMonitoringIntegration:
    """Integration layer for database monitoring."""

    def __init__(self, database_manager, monitoring_manager: MonitoringManager):
        self.database_manager = database_manager
        self.monitoring_manager = monitoring_manager
        self.db_metrics = DatabaseMetrics()

        # Setup database health checks
        self.health_check = DatabaseHealthCheck(
            database_path=getattr(database_manager, "database_path", "bot_data.db"),
            name="database",
        )

        # Register health check
        monitoring_manager.health.register_health_check(
            "database", self._database_health_check
        )

        logger.info("Database monitoring integration initialized")

    async def _database_health_check(self):
        """Database health check wrapper."""
        result = await self.health_check.run_check()
        return {
            "status": result.status.value,
            "message": result.message,
            "details": result.details,
            "duration_ms": result.duration_ms,
        }

    def record_query(self, query_type: str, duration: float, success: bool = True):
        """Record database query metrics."""
        self.db_metrics.record_query(query_type, duration, success)

        # Record in main metrics system
        tags = {"type": query_type, "success": str(success)}
        self.monitoring_manager.metrics.record_timer(
            "db_query_duration", duration, tags
        )
        self.monitoring_manager.metrics.record_counter("db_queries_total", 1, tags)

    def record_transaction(self, duration: float, success: bool = True):
        """Record database transaction metrics."""
        self.db_metrics.record_transaction(duration, success)

        # Record in main metrics system
        tags = {"success": str(success)}
        self.monitoring_manager.metrics.record_timer(
            "db_transaction_duration", duration, tags
        )
        self.monitoring_manager.metrics.record_counter("db_transactions_total", 1, tags)

    def update_connection_count(self, active_connections: int):
        """Update database connection count."""
        self.db_metrics.update_connection_count(active_connections)
        self.monitoring_manager.metrics.record_gauge(
            "db_connections_active", active_connections
        )

    def get_database_metrics(self) -> dict[str, Any]:
        """Get comprehensive database metrics."""
        db_metrics_dict = {}
        for name, metric in self.db_metrics.get_all_metrics().items():
            summary = metric.get_summary()
            db_metrics_dict[name] = {
                "type": summary.metric_type.value,
                "count": summary.count,
                "value": (
                    summary.sum
                    if summary.metric_type.value == "counter"
                    else getattr(metric, "get_value", lambda: 0)()
                ),
                "last_updated": summary.last_updated,
            }

        return {
            "timestamp": datetime.now().isoformat(),
            "metrics": db_metrics_dict,
            "health": "healthy",  # Would be updated based on health checks
        }


class WebSocketMonitoringIntegration:
    """Integration layer for WebSocket monitoring."""

    def __init__(self, ws_manager, monitoring_manager: MonitoringManager):
        self.ws_manager = ws_manager
        self.monitoring_manager = monitoring_manager

        # Setup WebSocket health check
        self.health_check = WebSocketHealthCheck(ws_manager, "websocket")
        monitoring_manager.health.register_health_check(
            "websocket", self._websocket_health_check
        )

        # Hook into WebSocket callbacks if available
        self._setup_websocket_callbacks()

        logger.info("WebSocket monitoring integration initialized")

    async def _websocket_health_check(self):
        """WebSocket health check wrapper."""
        result = await self.health_check.run_check()
        return {
            "status": result.status.value,
            "message": result.message,
            "details": result.details,
            "duration_ms": result.duration_ms,
        }

    def _setup_websocket_callbacks(self):
        """Setup WebSocket event callbacks for monitoring."""
        if hasattr(self.ws_manager, "add_connect_callback"):
            self.ws_manager.add_connect_callback(self._on_connect)

        if hasattr(self.ws_manager, "add_disconnect_callback"):
            self.ws_manager.add_disconnect_callback(self._on_disconnect)

        if hasattr(self.ws_manager, "add_error_callback"):
            self.ws_manager.add_error_callback(self._on_error)

        if hasattr(self.ws_manager, "add_message_callback"):
            self.ws_manager.add_message_callback(self._on_message)

    def _on_connect(self):
        """WebSocket connection established."""
        self.monitoring_manager.metrics.record_counter(
            "websocket_connections", 1, {"event": "connect"}
        )

    def _on_disconnect(self, reason=None):
        """WebSocket disconnection."""
        tags = {"event": "disconnect"}
        if reason:
            tags["reason"] = str(reason)
        self.monitoring_manager.metrics.record_counter(
            "websocket_disconnections", 1, tags
        )

    def _on_error(self, error):
        """WebSocket error occurred."""
        tags = {"event": "error", "error_type": type(error).__name__}
        self.monitoring_manager.metrics.record_counter("websocket_errors", 1, tags)

    def _on_message(self, message_data):
        """WebSocket message received."""
        self.monitoring_manager.metrics.record_counter(
            "websocket_messages", 1, {"event": "message"}
        )

        # Record message processing time if available
        if isinstance(message_data, dict) and "processing_time" in message_data:
            self.monitoring_manager.metrics.record_timer(
                "websocket_message_processing", message_data["processing_time"]
            )


class OrderClientMonitoringIntegration:
    """Integration layer for order client monitoring."""

    def __init__(
        self,
        order_client,
        monitoring_manager: MonitoringManager,
        performance_monitor: PerformanceMonitor,
    ):
        self.order_client = order_client
        self.monitoring_manager = monitoring_manager
        self.performance_monitor = performance_monitor
        self.trading_metrics = TradingMetrics()

        # Setup health check
        self.health_check = OrderClientHealthCheck(order_client, "order_client")
        monitoring_manager.health.register_health_check(
            "order_client", self._order_client_health_check
        )

        logger.info("Order client monitoring integration initialized")

    async def _order_client_health_check(self):
        """Order client health check wrapper."""
        result = await self.health_check.run_check()
        return {
            "status": result.status.value,
            "message": result.message,
            "details": result.details,
            "duration_ms": result.duration_ms,
        }

    def record_order_placed(
        self,
        order_id: str,
        order_type: str,
        market: str,
        amount: float,
        placement_time: float,
    ):
        """Record order placement event."""
        # Trading metrics
        self.trading_metrics.record_order_placed(order_type, market, amount)

        # Performance tracking
        self.performance_monitor.trading_performance.record_order_performance(
            order_id=order_id,
            market=market,
            order_type=order_type,
            placement_latency=placement_time,
        )

        # Main metrics
        tags = {"type": order_type, "market": market}
        self.monitoring_manager.metrics.record_counter("orders_placed", 1, tags)
        self.monitoring_manager.metrics.record_timer(
            "order_placement_time", placement_time, tags
        )

    def record_order_filled(
        self,
        order_id: str,
        order_type: str,
        market: str,
        fill_time: float,
        expected_price: float,
        actual_price: float,
    ):
        """Record order fill event."""
        # Trading metrics
        self.trading_metrics.record_order_filled(order_type, market, fill_time)

        # Performance tracking with slippage
        self.performance_monitor.trading_performance.record_order_performance(
            order_id=order_id,
            market=market,
            order_type=order_type,
            placement_latency=0,  # Already recorded at placement
            fill_time=fill_time,
            expected_price=expected_price,
            actual_price=actual_price,
        )

        # Main metrics
        tags = {"type": order_type, "market": market}
        self.monitoring_manager.metrics.record_counter("orders_filled", 1, tags)
        self.monitoring_manager.metrics.record_timer("order_fill_time", fill_time, tags)

        # Slippage tracking
        slippage = abs(actual_price - expected_price) / expected_price * 100
        self.monitoring_manager.metrics.record_histogram(
            "order_slippage", slippage, tags
        )

    def record_order_cancelled(
        self, order_id: str, order_type: str, market: str, reason: str
    ):
        """Record order cancellation event."""
        tags = {"type": order_type, "market": market, "reason": reason}
        self.monitoring_manager.metrics.record_counter("orders_cancelled", 1, tags)

    def record_order_failed(
        self,
        order_id: str,
        order_type: str,
        market: str,
        error_type: str,
        error_message: str,
    ):
        """Record order failure event."""
        tags = {"type": order_type, "market": market, "error_type": error_type}
        self.monitoring_manager.metrics.record_counter("orders_failed", 1, tags)

    def update_position_metrics(
        self,
        total_positions: int,
        realized_pnl: float,
        unrealized_pnl: float,
        total_exposure: float,
    ):
        """Update position and P&L metrics."""
        self.trading_metrics.record_pnl_update(
            realized_pnl, unrealized_pnl, total_exposure
        )

        # Main metrics
        self.monitoring_manager.metrics.record_gauge(
            "current_positions", total_positions
        )
        self.monitoring_manager.metrics.record_gauge("realized_pnl", realized_pnl)
        self.monitoring_manager.metrics.record_gauge("unrealized_pnl", unrealized_pnl)
        self.monitoring_manager.metrics.record_gauge("total_exposure", total_exposure)


class StrategyMonitoringIntegration:
    """Integration layer for strategy monitoring."""

    def __init__(
        self,
        monitoring_manager: MonitoringManager,
        performance_monitor: PerformanceMonitor,
    ):
        self.monitoring_manager = monitoring_manager
        self.performance_monitor = performance_monitor

        logger.info("Strategy monitoring integration initialized")

    def record_strategy_execution(
        self,
        strategy_name: str,
        signal_type: str,
        execution_time: float,
        success: bool,
        metadata: dict[str, Any] | None = None,
    ):
        """Record strategy execution metrics."""
        # Performance tracking
        self.performance_monitor.trading_performance.record_strategy_performance(
            strategy_name=strategy_name,
            execution_time=execution_time,
            signal_type=signal_type,
            success=success,
        )

        # Main metrics
        tags = {
            "strategy": strategy_name,
            "signal_type": signal_type,
            "success": str(success),
        }
        self.monitoring_manager.metrics.record_counter("strategy_signals", 1, tags)
        self.monitoring_manager.metrics.record_timer(
            "strategy_execution_time", execution_time, tags
        )

        if metadata:
            for key, value in metadata.items():
                if isinstance(value, (int, float)):
                    self.monitoring_manager.metrics.record_gauge(
                        f"strategy_{key}", value, tags
                    )

    def record_signal_generated(
        self, strategy_name: str, signal_type: str, market: str, confidence: float
    ):
        """Record strategy signal generation."""
        tags = {"strategy": strategy_name, "signal_type": signal_type, "market": market}

        self.monitoring_manager.metrics.record_counter(
            "strategy_signals_generated", 1, tags
        )
        self.monitoring_manager.metrics.record_histogram(
            "signal_confidence", confidence, tags
        )


class ProductionMonitoringSystem:
    """Main production monitoring system coordinator."""

    def __init__(
        self,
        config: MonitoringConfig | None = None,
        enable_http_server: bool = True,
        http_port: int = 8080,
    ):
        """Initialize the complete monitoring system."""

        # Core monitoring components
        self.config = config or MonitoringConfig()
        self.monitoring_manager = MonitoringManager(self.config)
        self.performance_monitor = PerformanceMonitor(
            self.config.metrics_collection_interval
        )
        self.alert_manager = AlertManager()

        # System health monitoring
        self.system_health = SystemHealth()
        self._setup_system_health_checks()

        # Dashboard and HTTP endpoints
        self.dashboard_manager = DashboardManager(
            monitoring_manager=self.monitoring_manager,
            performance_monitor=self.performance_monitor,
            alert_manager=self.alert_manager,
            port=http_port,
        )
        self.enable_http_server = enable_http_server

        # Component integrations (will be set when components are registered)
        self.database_integration: DatabaseMonitoringIntegration | None = None
        self.websocket_integration: WebSocketMonitoringIntegration | None = None
        self.order_client_integration: OrderClientMonitoringIntegration | None = None
        self.strategy_integration: StrategyMonitoringIntegration | None = None

        # Setup default alerts
        self._setup_default_alerts()

        logger.info("Production monitoring system initialized")

    async def start(self):
        """Start the complete monitoring system."""
        logger.info("Starting production monitoring system...")

        # Start core monitoring
        await self.monitoring_manager.start()
        await self.performance_monitor.start_monitoring()

        # Start HTTP server if enabled
        if self.enable_http_server:
            try:
                await self.dashboard_manager.start_server()
            except Exception as e:
                logger.error(f"Failed to start HTTP server: {e}")

        logger.info("Production monitoring system started successfully")

    async def stop(self):
        """Stop the monitoring system."""
        logger.info("Stopping production monitoring system...")

        # Stop HTTP server
        if self.dashboard_manager.is_running:
            await self.dashboard_manager.stop_server()

        # Stop monitoring components
        await self.performance_monitor.stop_monitoring()
        await self.monitoring_manager.stop()

        logger.info("Production monitoring system stopped")

    def register_database(self, database_manager):
        """Register database for monitoring."""
        self.database_integration = DatabaseMonitoringIntegration(
            database_manager, self.monitoring_manager
        )
        self.monitoring_manager.register_component("database", database_manager)
        logger.info("Database registered for monitoring")

    def register_websocket(self, ws_manager):
        """Register WebSocket manager for monitoring."""
        self.websocket_integration = WebSocketMonitoringIntegration(
            ws_manager, self.monitoring_manager
        )
        self.monitoring_manager.register_component("websocket", ws_manager)
        logger.info("WebSocket manager registered for monitoring")

    def register_order_client(self, order_client):
        """Register order client for monitoring."""
        self.order_client_integration = OrderClientMonitoringIntegration(
            order_client, self.monitoring_manager, self.performance_monitor
        )
        self.monitoring_manager.register_component("order_client", order_client)
        logger.info("Order client registered for monitoring")

    def register_strategy(self, strategy_name: str, strategy_instance=None):
        """Register trading strategy for monitoring."""
        if not self.strategy_integration:
            self.strategy_integration = StrategyMonitoringIntegration(
                self.monitoring_manager, self.performance_monitor
            )

        if strategy_instance:
            self.monitoring_manager.register_component(
                f"strategy_{strategy_name}", strategy_instance
            )

        logger.info(f"Strategy '{strategy_name}' registered for monitoring")

    def get_system_status(self) -> dict[str, Any]:
        """Get comprehensive system status."""
        return {
            "timestamp": datetime.now().isoformat(),
            "monitoring_system": self.monitoring_manager.get_system_status(),
            "performance": self.performance_monitor.get_comprehensive_performance_report(),
            "alerts": self.alert_manager.get_alert_summary(),
            "active_alerts": self.alert_manager.get_active_alerts(),
            "integrations": {
                "database": self.database_integration is not None,
                "websocket": self.websocket_integration is not None,
                "order_client": self.order_client_integration is not None,
                "strategy": self.strategy_integration is not None,
            },
            "http_server": {
                "enabled": self.enable_http_server,
                "running": self.dashboard_manager.is_running,
                "port": self.dashboard_manager.port,
            },
        }

    def _setup_system_health_checks(self):
        """Setup system-level health checks."""
        # System resources health check
        system_component = ComponentHealth("system")
        system_component.add_health_check(SystemResourceHealthCheck())
        self.system_health.add_component(system_component)

        # Register with main health checker
        self.monitoring_manager.health.register_health_check(
            "system_resources", lambda: self._system_health_check()
        )

    async def _system_health_check(self):
        """System health check wrapper."""
        try:
            # Get system health
            health_data = await self.system_health.get_system_health()

            return {
                "status": health_data["overall_status"],
                "message": f"System health: {health_data['overall_status']}",
                "details": health_data,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"System health check failed: {str(e)}",
                "details": {"error": str(e)},
            }

    def _setup_default_alerts(self):
        """Setup default alert rules."""
        # CPU threshold alerts
        cpu_alert = ThresholdAlert(
            name="cpu_usage",
            component="system",
            metric_name="cpu_percent",
            warning_threshold=75.0,
            critical_threshold=90.0,
            comparison="greater_than",
            duration_seconds=60,
        )
        self.alert_manager.add_threshold_alert(cpu_alert)

        # Memory threshold alerts
        memory_alert = ThresholdAlert(
            name="memory_usage",
            component="system",
            metric_name="memory_percent",
            warning_threshold=80.0,
            critical_threshold=95.0,
            comparison="greater_than",
            duration_seconds=60,
        )
        self.alert_manager.add_threshold_alert(memory_alert)

        # Error rate alerts for critical operations
        order_error_alert = ErrorRateAlert(
            name="order_errors",
            component="order_client",
            operation="place_order",
            warning_rate=5.0,
            critical_rate=15.0,
            min_events=10,
            duration_minutes=2,
        )
        self.alert_manager.add_error_rate_alert(order_error_alert)

        # Performance alerts
        latency_alert = PerformanceAlert(
            name="order_latency",
            component="order_client",
            metric_type="latency",
            warning_threshold=1000.0,  # 1 second
            critical_threshold=5000.0,  # 5 seconds
            percentile=95.0,
            duration_minutes=3,
        )
        self.alert_manager.add_performance_alert(latency_alert)

        logger.info("Default alerts configured")


# Global monitoring system instance
_monitoring_system: ProductionMonitoringSystem | None = None


def initialize_monitoring(
    config: MonitoringConfig | None = None,
    enable_http_server: bool = True,
    http_port: int = 8080,
) -> ProductionMonitoringSystem:
    """Initialize the global monitoring system."""
    global _monitoring_system

    if _monitoring_system is not None:
        logger.warning("Monitoring system already initialized")
        return _monitoring_system

    _monitoring_system = ProductionMonitoringSystem(
        config=config, enable_http_server=enable_http_server, http_port=http_port
    )

    logger.info("Global monitoring system initialized")
    return _monitoring_system


def get_monitoring_system() -> ProductionMonitoringSystem | None:
    """Get the global monitoring system instance."""
    return _monitoring_system
