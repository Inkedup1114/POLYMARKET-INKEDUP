"""
Performance Metrics Integration

Unified integration system for connecting performance metrics tracking
to all major bot components with automatic instrumentation, monitoring,
and reporting capabilities.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from typing import Any

from .database_performance_metrics import DatabasePerformanceTracker
from .error_rate_tracking import ErrorRateTracker
from .order_execution_metrics import OrderExecutionPerformanceTracker
from .performance_dashboard import (
    DashboardServer,
    PerformanceDashboard,
    create_performance_dashboard,
)
from .performance_metrics import ComponentType, MetricType, PerformanceMetricsTracker
from .signal_processing_metrics import SignalProcessingPerformanceTracker
from .throughput_metrics import ThroughputTracker

logger = logging.getLogger(__name__)


@dataclass
class PerformanceConfig:
    """Configuration for performance metrics integration"""

    enable_dashboard: bool = True
    dashboard_host: str = "localhost"
    dashboard_port: int = 8080
    metrics_retention_hours: int = 24
    enable_real_time_alerts: bool = True
    update_interval_seconds: float = 5.0
    enable_automatic_instrumentation: bool = True
    log_performance_summaries: bool = True
    summary_interval_minutes: int = 15


class PerformanceIntegrationManager:
    """
    Central manager for performance metrics integration

    Provides unified interface for connecting performance tracking to all
    bot components with automatic instrumentation and monitoring.
    """

    def __init__(self, config: PerformanceConfig | None = None):
        self.config = config or PerformanceConfig()

        # Initialize all trackers
        self.performance_tracker = PerformanceMetricsTracker(
            retention_seconds=self.config.metrics_retention_hours * 3600
        )

        self.signal_tracker = SignalProcessingPerformanceTracker(
            performance_tracker=self.performance_tracker
        )

        self.order_tracker = OrderExecutionPerformanceTracker(
            performance_tracker=self.performance_tracker
        )

        self.database_tracker = DatabasePerformanceTracker(
            retention_seconds=self.config.metrics_retention_hours * 3600
        )

        self.throughput_tracker = ThroughputTracker(
            retention_hours=self.config.metrics_retention_hours
        )

        self.error_tracker = ErrorRateTracker(
            retention_hours=self.config.metrics_retention_hours * 3
        )

        # Cross-tracker integration
        self.error_tracker.set_throughput_tracker(self.throughput_tracker)

        # Dashboard and server
        self.dashboard: PerformanceDashboard | None = None
        self.dashboard_server: DashboardServer | None = None

        # Component integrations
        self.component_integrations: dict[str, Any] = {}

        # Background tasks
        self.background_tasks: list[asyncio.Task] = []
        self.running = False

        # Performance summary logging
        self.last_summary_time = datetime.now()

        logger.info("Performance integration manager initialized")

    async def start(self):
        """Start all performance tracking systems"""
        if self.running:
            return

        self.running = True

        # Start individual trackers
        self.throughput_tracker.start_background_calculations()
        self.error_tracker.start_background_analysis()

        # Create and start dashboard
        if self.config.enable_dashboard:
            self.dashboard, self.dashboard_server = create_performance_dashboard(
                performance_tracker=self.performance_tracker,
                signal_tracker=self.signal_tracker,
                order_tracker=self.order_tracker,
                database_tracker=self.database_tracker,
                start_server=True,
                server_host=self.config.dashboard_host,
                server_port=self.config.dashboard_port,
            )

            logger.info(
                f"Performance dashboard available at http://{self.config.dashboard_host}:{self.config.dashboard_port}"
            )

        # Start background monitoring tasks
        if self.config.log_performance_summaries:
            task = asyncio.create_task(self._performance_summary_loop())
            self.background_tasks.append(task)

        if self.config.enable_real_time_alerts:
            task = asyncio.create_task(self._alert_monitoring_loop())
            self.background_tasks.append(task)

        logger.info("Performance tracking systems started")

    async def stop(self):
        """Stop all performance tracking systems"""
        if not self.running:
            return

        self.running = False

        # Cancel background tasks
        for task in self.background_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.background_tasks.clear()

        # Stop trackers
        self.throughput_tracker.stop_background_calculations()
        self.error_tracker.stop_background_analysis()

        # Stop dashboard
        if self.dashboard:
            self.dashboard.stop_real_time_updates()

        if self.dashboard_server:
            self.dashboard_server.stop()

        logger.info("Performance tracking systems stopped")

    async def _performance_summary_loop(self):
        """Background loop for logging performance summaries"""
        while self.running:
            try:
                await asyncio.sleep(self.config.summary_interval_minutes * 60)
                if self.running:
                    self._log_performance_summary()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in performance summary loop: {e}")
                await asyncio.sleep(60)  # Wait a minute on error

    async def _alert_monitoring_loop(self):
        """Background loop for monitoring alerts"""
        while self.running:
            try:
                await asyncio.sleep(30)  # Check alerts every 30 seconds
                if self.running:
                    self._check_and_log_alerts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in alert monitoring loop: {e}")
                await asyncio.sleep(30)

    def _log_performance_summary(self):
        """Log comprehensive performance summary"""
        try:
            current_time = datetime.now()

            # Get summaries from all trackers
            signal_summary = self.signal_tracker.get_performance_summary(
                minutes=self.config.summary_interval_minutes
            )

            order_summary = self.order_tracker.get_execution_summary(
                minutes=self.config.summary_interval_minutes
            )

            database_summary = self.database_tracker.get_database_health_summary()

            throughput_summary = self.throughput_tracker.get_system_throughput_health()

            error_summary = self.error_tracker.get_system_error_health()

            # Log comprehensive summary
            logger.info(
                f"=== PERFORMANCE SUMMARY ({self.config.summary_interval_minutes} min) ===\n"
                f"Signal Processing: {signal_summary.get('total_signals', 0)} signals, "
                f"{signal_summary.get('avg_processing_time_ms', 0):.1f}ms avg\n"
                f"Order Execution: {order_summary.get('total_orders', 0)} orders, "
                f"{order_summary.get('fill_rate', 0)*100:.1f}% fill rate\n"
                f"Database Health: {database_summary.get('overall_health', 'unknown')}, "
                f"{database_summary.get('query_performance', {}).get('total_queries', 0)} queries\n"
                f"Throughput: {throughput_summary.get('total_throughput_rate', 0):.1f}/s total rate\n"
                f"Error Rate: {error_summary.get('total_error_rate', 0):.2f}/min, "
                f"Health: {error_summary.get('overall_health', 'unknown')}\n"
                f"================================================="
            )

            self.last_summary_time = current_time

        except Exception as e:
            logger.error(f"Error generating performance summary: {e}")

    def _check_and_log_alerts(self):
        """Check for active alerts and log important ones"""
        try:
            # Get active error alerts
            error_alerts = self.error_tracker.get_active_alerts()
            critical_alerts = [
                alert
                for alert in error_alerts
                if alert["severity"] in ["critical", "high"]
                and not alert["acknowledged"]
            ]

            if critical_alerts:
                for alert in critical_alerts[:5]:  # Log top 5 critical alerts
                    logger.warning(
                        f"CRITICAL ALERT: {alert['component']} - {alert['message']} "
                        f"(Rate: {alert['error_rate']:.1f}/min)"
                    )

        except Exception as e:
            logger.error(f"Error checking alerts: {e}")

    # Component Integration Methods

    def integrate_order_client(self, order_client: Any) -> "OrderClientIntegration":
        """Integrate performance tracking with order client"""
        integration = OrderClientIntegration(
            order_client=order_client,
            order_tracker=self.order_tracker,
            throughput_tracker=self.throughput_tracker,
            error_tracker=self.error_tracker,
        )

        self.component_integrations["order_client"] = integration
        return integration

    def integrate_signal_processor(
        self, signal_processor: Any
    ) -> "SignalProcessorIntegration":
        """Integrate performance tracking with signal processor"""
        integration = SignalProcessorIntegration(
            signal_processor=signal_processor,
            signal_tracker=self.signal_tracker,
            throughput_tracker=self.throughput_tracker,
            error_tracker=self.error_tracker,
        )

        self.component_integrations["signal_processor"] = integration
        return integration

    def integrate_database_manager(
        self, database_manager: Any
    ) -> "DatabaseIntegration":
        """Integrate performance tracking with database manager"""
        integration = DatabaseIntegration(
            database_manager=database_manager,
            database_tracker=self.database_tracker,
            throughput_tracker=self.throughput_tracker,
            error_tracker=self.error_tracker,
        )

        self.component_integrations["database"] = integration
        return integration

    def integrate_websocket_manager(
        self, websocket_manager: Any
    ) -> "WebSocketIntegration":
        """Integrate performance tracking with WebSocket manager"""
        integration = WebSocketIntegration(
            websocket_manager=websocket_manager,
            throughput_tracker=self.throughput_tracker,
            error_tracker=self.error_tracker,
            performance_tracker=self.performance_tracker,
        )

        self.component_integrations["websocket"] = integration
        return integration

    def integrate_strategy_manager(
        self, strategy_manager: Any
    ) -> "StrategyIntegration":
        """Integrate performance tracking with strategy manager"""
        integration = StrategyIntegration(
            strategy_manager=strategy_manager,
            signal_tracker=self.signal_tracker,
            throughput_tracker=self.throughput_tracker,
            error_tracker=self.error_tracker,
            performance_tracker=self.performance_tracker,
        )

        self.component_integrations["strategy"] = integration
        return integration

    # Unified Performance Tracking Methods

    def track_operation(self, component: ComponentType, operation: str):
        """Decorator for tracking operation performance across all metrics"""

        def decorator(func):
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.perf_counter()

                try:
                    result = func(*args, **kwargs)

                    # Record success metrics
                    execution_time_ms = (time.perf_counter() - start_time) * 1000
                    self.performance_tracker.record_metric(
                        component, MetricType.LATENCY, operation, execution_time_ms
                    )
                    self.throughput_tracker.record_event(component, operation)
                    self.error_tracker.record_success(component, operation)

                    return result

                except Exception as e:
                    # Record error metrics
                    self.error_tracker.record_error(component, operation, e)
                    self.throughput_tracker.record_event(
                        component, f"{operation}_error"
                    )
                    raise

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.perf_counter()

                try:
                    result = await func(*args, **kwargs)

                    # Record success metrics
                    execution_time_ms = (time.perf_counter() - start_time) * 1000
                    self.performance_tracker.record_metric(
                        component, MetricType.LATENCY, operation, execution_time_ms
                    )
                    self.throughput_tracker.record_event(component, operation)
                    self.error_tracker.record_success(component, operation)

                    return result

                except Exception as e:
                    # Record error metrics
                    self.error_tracker.record_error(component, operation, e)
                    self.throughput_tracker.record_event(
                        component, f"{operation}_error"
                    )
                    raise

            return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

        return decorator

    @asynccontextmanager
    async def track_operation_context(self, component: ComponentType, operation: str):
        """Async context manager for tracking operation performance"""
        start_time = time.perf_counter()

        try:
            yield

            # Record success metrics
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            self.performance_tracker.record_metric(
                component, MetricType.LATENCY, operation, execution_time_ms
            )
            self.throughput_tracker.record_event(component, operation)
            self.error_tracker.record_success(component, operation)

        except Exception as e:
            # Record error metrics
            self.error_tracker.record_error(component, operation, e)
            self.throughput_tracker.record_event(component, f"{operation}_error")
            raise

    def get_comprehensive_performance_report(self) -> dict[str, Any]:
        """Get comprehensive performance report across all systems"""
        try:
            return {
                "timestamp": datetime.now().isoformat(),
                "signal_processing": self.signal_tracker.get_performance_summary(60),
                "order_execution": self.order_tracker.get_execution_summary(60),
                "database_performance": self.database_tracker.get_database_health_summary(),
                "system_throughput": self.throughput_tracker.get_system_throughput_health(),
                "error_analysis": self.error_tracker.get_system_error_health(),
                "component_integrations": list(self.component_integrations.keys()),
                "dashboard_url": (
                    f"http://{self.config.dashboard_host}:{self.config.dashboard_port}"
                    if self.config.enable_dashboard
                    else None
                ),
            }
        except Exception as e:
            logger.error(f"Error generating comprehensive performance report: {e}")
            return {"error": str(e), "timestamp": datetime.now().isoformat()}


# Component Integration Classes


class OrderClientIntegration:
    """Integration wrapper for order client performance tracking"""

    def __init__(
        self,
        order_client: Any,
        order_tracker: OrderExecutionPerformanceTracker,
        throughput_tracker: ThroughputTracker,
        error_tracker: ErrorRateTracker,
    ):
        self.order_client = order_client
        self.order_tracker = order_tracker
        self.throughput_tracker = throughput_tracker
        self.error_tracker = error_tracker

        # Apply automatic instrumentation if enabled
        self._apply_instrumentation()

    def _apply_instrumentation(self):
        """Apply automatic performance instrumentation to order client methods"""
        methods_to_instrument = [
            "place_order",
            "cancel_order",
            "get_order_status",
            "get_orders",
            "get_positions",
            "get_balance",
            "connect",
            "disconnect",
        ]

        for method_name in methods_to_instrument:
            if hasattr(self.order_client, method_name):
                original_method = getattr(self.order_client, method_name)
                instrumented_method = self._instrument_method(
                    method_name, original_method
                )
                setattr(self.order_client, method_name, instrumented_method)

    def _instrument_method(self, method_name: str, original_method: Callable):
        """Instrument individual method with performance tracking"""

        @wraps(original_method)
        def wrapper(*args, **kwargs):
            with self.order_tracker.track_order_operation(method_name) as context:
                try:
                    result = original_method(*args, **kwargs)
                    self.throughput_tracker.record_event(
                        ComponentType.ORDER_CLIENT, method_name
                    )
                    self.error_tracker.record_success(
                        ComponentType.ORDER_CLIENT, method_name
                    )
                    return result
                except Exception as e:
                    self.error_tracker.record_error(
                        ComponentType.ORDER_CLIENT, method_name, e
                    )
                    raise

        return wrapper


class SignalProcessorIntegration:
    """Integration wrapper for signal processor performance tracking"""

    def __init__(
        self,
        signal_processor: Any,
        signal_tracker: SignalProcessingPerformanceTracker,
        throughput_tracker: ThroughputTracker,
        error_tracker: ErrorRateTracker,
    ):
        self.signal_processor = signal_processor
        self.signal_tracker = signal_tracker
        self.throughput_tracker = throughput_tracker
        self.error_tracker = error_tracker

        self._apply_instrumentation()

    def _apply_instrumentation(self):
        """Apply automatic performance instrumentation to signal processor methods"""
        methods_to_instrument = [
            "process_market_data",
            "generate_signal",
            "calculate_indicators",
            "update_strategy_state",
            "validate_signal",
        ]

        for method_name in methods_to_instrument:
            if hasattr(self.signal_processor, method_name):
                original_method = getattr(self.signal_processor, method_name)
                instrumented_method = self._instrument_method(
                    method_name, original_method
                )
                setattr(self.signal_processor, method_name, instrumented_method)

    def _instrument_method(self, method_name: str, original_method: Callable):
        """Instrument individual method with performance tracking"""

        @wraps(original_method)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()

            try:
                result = original_method(*args, **kwargs)

                processing_time_ms = (time.perf_counter() - start_time) * 1000

                # Record in signal tracker
                if method_name == "process_market_data":
                    market = kwargs.get("market", "unknown")
                    self.signal_tracker.record_market_data_processing(
                        market=market,
                        data_type="market_data",
                        processing_time_ms=processing_time_ms,
                        data_age_ms=0,  # Would need to calculate from data
                        records_processed=1,
                    )
                elif method_name == "generate_signal":
                    strategy = kwargs.get("strategy", "unknown")
                    self.signal_tracker.record_signal_generation(
                        strategy=strategy,
                        market=kwargs.get("market", "unknown"),
                        signal_type="trading_signal",
                        processing_time_ms=processing_time_ms,
                        signal_strength=0.5,  # Would extract from result
                    )

                self.throughput_tracker.record_event(
                    ComponentType.SIGNAL_PROCESSOR, method_name
                )
                self.error_tracker.record_success(
                    ComponentType.SIGNAL_PROCESSOR, method_name
                )

                return result

            except Exception as e:
                self.error_tracker.record_error(
                    ComponentType.SIGNAL_PROCESSOR, method_name, e
                )
                raise

        return wrapper


class DatabaseIntegration:
    """Integration wrapper for database performance tracking"""

    def __init__(
        self,
        database_manager: Any,
        database_tracker: DatabasePerformanceTracker,
        throughput_tracker: ThroughputTracker,
        error_tracker: ErrorRateTracker,
    ):
        self.database_manager = database_manager
        self.database_tracker = database_tracker
        self.throughput_tracker = throughput_tracker
        self.error_tracker = error_tracker

        self._apply_instrumentation()

    def _apply_instrumentation(self):
        """Apply automatic performance instrumentation to database methods"""
        methods_to_instrument = [
            "execute_query",
            "execute_many",
            "fetch_one",
            "fetch_all",
            "begin_transaction",
            "commit_transaction",
            "rollback_transaction",
            "connect",
            "disconnect",
            "get_connection",
        ]

        for method_name in methods_to_instrument:
            if hasattr(self.database_manager, method_name):
                original_method = getattr(self.database_manager, method_name)
                instrumented_method = self._instrument_method(
                    method_name, original_method
                )
                setattr(self.database_manager, method_name, instrumented_method)

    def _instrument_method(self, method_name: str, original_method: Callable):
        """Instrument individual method with performance tracking"""

        @wraps(original_method)
        def wrapper(*args, **kwargs):
            query = args[0] if args else kwargs.get("query", "unknown_query")

            with self.database_tracker.track_query(query) as context:
                try:
                    result = original_method(*args, **kwargs)
                    self.throughput_tracker.record_event(
                        ComponentType.DATABASE, method_name
                    )
                    self.error_tracker.record_success(
                        ComponentType.DATABASE, method_name
                    )
                    return result
                except Exception as e:
                    self.error_tracker.record_error(
                        ComponentType.DATABASE, method_name, e
                    )
                    raise

        return wrapper


class WebSocketIntegration:
    """Integration wrapper for WebSocket performance tracking"""

    def __init__(
        self,
        websocket_manager: Any,
        throughput_tracker: ThroughputTracker,
        error_tracker: ErrorRateTracker,
        performance_tracker: PerformanceMetricsTracker,
    ):
        self.websocket_manager = websocket_manager
        self.throughput_tracker = throughput_tracker
        self.error_tracker = error_tracker
        self.performance_tracker = performance_tracker

        self._apply_instrumentation()

    def _apply_instrumentation(self):
        """Apply automatic performance instrumentation to WebSocket methods"""
        methods_to_instrument = [
            "connect",
            "disconnect",
            "send_message",
            "on_message",
            "subscribe",
            "unsubscribe",
            "reconnect",
        ]

        for method_name in methods_to_instrument:
            if hasattr(self.websocket_manager, method_name):
                original_method = getattr(self.websocket_manager, method_name)
                instrumented_method = self._instrument_method(
                    method_name, original_method
                )
                setattr(self.websocket_manager, method_name, instrumented_method)

    def _instrument_method(self, method_name: str, original_method: Callable):
        """Instrument individual method with performance tracking"""

        @wraps(original_method)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()

            try:
                result = original_method(*args, **kwargs)

                execution_time_ms = (time.perf_counter() - start_time) * 1000
                self.performance_tracker.record_metric(
                    ComponentType.WEBSOCKET,
                    MetricType.LATENCY,
                    method_name,
                    execution_time_ms,
                )

                # Record message size for throughput tracking if available
                message_size = None
                if method_name in ["send_message", "on_message"] and args:
                    message = args[0]
                    if hasattr(message, "__len__"):
                        message_size = len(str(message))

                self.throughput_tracker.record_event(
                    ComponentType.WEBSOCKET, method_name, bytes_size=message_size
                )
                self.error_tracker.record_success(ComponentType.WEBSOCKET, method_name)

                return result

            except Exception as e:
                self.error_tracker.record_error(ComponentType.WEBSOCKET, method_name, e)
                raise

        return wrapper


class StrategyIntegration:
    """Integration wrapper for strategy performance tracking"""

    def __init__(
        self,
        strategy_manager: Any,
        signal_tracker: SignalProcessingPerformanceTracker,
        throughput_tracker: ThroughputTracker,
        error_tracker: ErrorRateTracker,
        performance_tracker: PerformanceMetricsTracker,
    ):
        self.strategy_manager = strategy_manager
        self.signal_tracker = signal_tracker
        self.throughput_tracker = throughput_tracker
        self.error_tracker = error_tracker
        self.performance_tracker = performance_tracker

        self._apply_instrumentation()

    def _apply_instrumentation(self):
        """Apply automatic performance instrumentation to strategy methods"""
        methods_to_instrument = [
            "execute_strategy",
            "calculate_signals",
            "update_positions",
            "assess_risk",
            "validate_opportunity",
            "place_trades",
        ]

        for method_name in methods_to_instrument:
            if hasattr(self.strategy_manager, method_name):
                original_method = getattr(self.strategy_manager, method_name)
                instrumented_method = self._instrument_method(
                    method_name, original_method
                )
                setattr(self.strategy_manager, method_name, instrumented_method)

    def _instrument_method(self, method_name: str, original_method: Callable):
        """Instrument individual method with performance tracking"""

        @wraps(original_method)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()

            try:
                result = original_method(*args, **kwargs)

                processing_time_ms = (time.perf_counter() - start_time) * 1000

                # Record strategy-specific metrics
                if method_name in ["calculate_signals", "execute_strategy"]:
                    strategy_name = kwargs.get(
                        "strategy", getattr(self.strategy_manager, "name", "unknown")
                    )
                    self.signal_tracker.record_strategy_calculation(
                        strategy=strategy_name,
                        market=kwargs.get("market", "unknown"),
                        calculation_time_ms=processing_time_ms,
                        indicators_count=1,
                        signals_generated=1 if result else 0,
                    )

                self.performance_tracker.record_metric(
                    ComponentType.SIGNAL_PROCESSOR,
                    MetricType.LATENCY,
                    method_name,
                    processing_time_ms,
                )
                self.throughput_tracker.record_event(
                    ComponentType.SIGNAL_PROCESSOR, method_name
                )
                self.error_tracker.record_success(
                    ComponentType.SIGNAL_PROCESSOR, method_name
                )

                return result

            except Exception as e:
                self.error_tracker.record_error(
                    ComponentType.SIGNAL_PROCESSOR, method_name, e
                )
                raise

        return wrapper


# Global integration manager instance
_integration_manager = None


def get_performance_integration_manager() -> PerformanceIntegrationManager:
    """Get global performance integration manager instance"""
    global _integration_manager

    if _integration_manager is None:
        _integration_manager = PerformanceIntegrationManager()

    return _integration_manager


def initialize_performance_integration(
    config: PerformanceConfig | None = None,
) -> PerformanceIntegrationManager:
    """Initialize global performance integration system"""
    global _integration_manager

    if _integration_manager is not None:
        # Stop existing manager
        import asyncio

        if asyncio.get_event_loop().is_running():
            asyncio.create_task(_integration_manager.stop())

    _integration_manager = PerformanceIntegrationManager(config)
    logger.info("Global performance integration system initialized")

    return _integration_manager
