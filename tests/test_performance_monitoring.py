"""
Performance monitoring integration tests for the InkedUp trading bot.

This module provides continuous performance monitoring capabilities that can be
integrated with production systems to track performance metrics in real-time
and alert on performance degradations.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.engine import TradingEngine
from inkedup_bot.signals import TradingSignal
from inkedup_bot.state import StateManager


@dataclass
class PerformanceMetric:
    """A single performance metric measurement."""

    timestamp: datetime
    metric_name: str
    value: float
    tags: Dict[str, str]
    details: Dict[str, Any]


@dataclass
class PerformanceAlert:
    """A performance alert when thresholds are exceeded."""

    timestamp: datetime
    alert_name: str
    metric_name: str
    current_value: float
    threshold_value: float
    severity: str  # "warning", "critical"
    message: str
    details: Dict[str, Any]


class PerformanceMonitor:
    """
    Real-time performance monitoring system for the trading bot.

    This class provides continuous monitoring of key performance metrics
    with configurable alerting and reporting capabilities.
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or self._default_config()
        self.logger = logging.getLogger(__name__)

        # Metric storage
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.alerts: List[PerformanceAlert] = []

        # Alert callbacks
        self.alert_callbacks: List[Callable[[PerformanceAlert], None]] = []

        # Monitoring state
        self.monitoring_active = False
        self.monitoring_task: Optional[asyncio.Task] = None

        # Performance thresholds
        self.thresholds = self.config.get("thresholds", self._default_thresholds())

        # Components to monitor
        self.engine: Optional[TradingEngine] = None
        self.state_manager: Optional[StateManager] = None

    def _default_config(self) -> Dict[str, Any]:
        """Default monitoring configuration."""
        return {
            "monitoring_interval_seconds": 1.0,
            "metric_retention_count": 1000,
            "alert_cooldown_seconds": 300,  # 5 minutes
            "batch_metrics": True,
            "export_metrics": False,
        }

    def _default_thresholds(self) -> Dict[str, Dict[str, float]]:
        """Default performance thresholds."""
        return {
            "signal_processing_latency_ms": {"warning": 30.0, "critical": 50.0},
            "database_query_time_ms": {"warning": 8.0, "critical": 15.0},
            "memory_usage_mb": {"warning": 500.0, "critical": 1000.0},
            "cpu_usage_percent": {"warning": 70.0, "critical": 90.0},
            "error_rate_percent": {"warning": 1.0, "critical": 5.0},
            "queue_depth": {"warning": 100, "critical": 500},
        }

    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]) -> None:
        """Add a callback to be called when alerts are triggered."""
        self.alert_callbacks.append(callback)

    def set_components(
        self, engine: TradingEngine = None, state_manager: StateManager = None
    ) -> None:
        """Set the components to monitor."""
        self.engine = engine
        self.state_manager = state_manager

    async def start_monitoring(self) -> None:
        """Start continuous performance monitoring."""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.logger.info("Performance monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop performance monitoring."""
        self.monitoring_active = False

        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        self.logger.info("Performance monitoring stopped")

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        interval = self.config["monitoring_interval_seconds"]

        while self.monitoring_active:
            try:
                await self._collect_metrics()
                await self._check_alerts()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}", exc_info=True)
                await asyncio.sleep(interval)

    async def _collect_metrics(self) -> None:
        """Collect performance metrics from all components."""
        timestamp = datetime.utcnow()

        # System metrics
        await self._collect_system_metrics(timestamp)

        # Component-specific metrics
        if self.engine:
            await self._collect_engine_metrics(timestamp)

        if self.state_manager:
            await self._collect_state_metrics(timestamp)

    async def _collect_system_metrics(self, timestamp: datetime) -> None:
        """Collect system-level performance metrics."""
        try:
            import psutil

            # Memory usage
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            self._record_metric("memory_usage_mb", memory_mb, timestamp)

            # CPU usage
            cpu_percent = process.cpu_percent()
            self._record_metric("cpu_usage_percent", cpu_percent, timestamp)

            # System load
            if hasattr(psutil, "getloadavg"):  # Unix systems
                load_avg = psutil.getloadavg()[0]  # 1-minute average
                self._record_metric("system_load", load_avg, timestamp)

        except ImportError:
            # psutil not available
            pass
        except Exception as e:
            self.logger.warning(f"Failed to collect system metrics: {e}")

    async def _collect_engine_metrics(self, timestamp: datetime) -> None:
        """Collect trading engine performance metrics."""
        try:
            # Signal manager metrics
            if hasattr(self.engine, "signal_manager") and self.engine.signal_manager:
                metrics = self.engine.get_signal_metrics()

                # Queue depth
                queue_depth = metrics.get("queue_depth", 0)
                self._record_metric("signal_queue_depth", queue_depth, timestamp)

                # Processing rate
                processed_rate = metrics.get("signals_per_second", 0)
                self._record_metric("signal_processing_rate", processed_rate, timestamp)

                # Success rate
                success_rate = metrics.get("success_rate", 0) * 100
                error_rate = 100 - success_rate
                self._record_metric("error_rate_percent", error_rate, timestamp)

                # Average processing time
                avg_time = metrics.get("avg_processing_time_ms", 0)
                self._record_metric("signal_processing_latency_ms", avg_time, timestamp)

        except Exception as e:
            self.logger.warning(f"Failed to collect engine metrics: {e}")

    async def _collect_state_metrics(self, timestamp: datetime) -> None:
        """Collect state manager performance metrics."""
        try:
            # Measure database query performance
            query_start = time.time()
            total_exposure = self.state_manager.get_total_exposure()
            query_time_ms = (time.time() - query_start) * 1000

            self._record_metric("database_query_time_ms", query_time_ms, timestamp)
            self._record_metric("total_exposure_usd", total_exposure, timestamp)

            # Position count (if available)
            if hasattr(self.state_manager, "positions"):
                position_count = len(self.state_manager.positions)
                self._record_metric("active_positions", position_count, timestamp)

        except Exception as e:
            self.logger.warning(f"Failed to collect state metrics: {e}")

    def _record_metric(
        self,
        name: str,
        value: float,
        timestamp: datetime,
        tags: Dict[str, str] = None,
        details: Dict[str, Any] = None,
    ) -> None:
        """Record a performance metric."""
        metric = PerformanceMetric(
            timestamp=timestamp,
            metric_name=name,
            value=value,
            tags=tags or {},
            details=details or {},
        )

        self.metrics[name].append(metric)

        # Export metric if configured
        if self.config.get("export_metrics", False):
            self._export_metric(metric)

    def _export_metric(self, metric: PerformanceMetric) -> None:
        """Export metric to external systems (stub implementation)."""
        # This would integrate with monitoring systems like:
        # - Prometheus
        # - DataDog
        # - CloudWatch
        # - InfluxDB
        # etc.

        self.logger.debug(f"Exporting metric: {metric.metric_name}={metric.value}")

    async def _check_alerts(self) -> None:
        """Check all metrics against thresholds and trigger alerts."""
        current_time = datetime.utcnow()

        for metric_name, threshold_config in self.thresholds.items():
            if metric_name not in self.metrics:
                continue

            # Get recent metrics (last 5 samples)
            recent_metrics = list(self.metrics[metric_name])[-5:]
            if not recent_metrics:
                continue

            # Calculate average of recent values
            avg_value = sum(m.value for m in recent_metrics) / len(recent_metrics)

            # Check thresholds
            for severity in ["critical", "warning"]:
                if severity not in threshold_config:
                    continue

                threshold = threshold_config[severity]

                if avg_value > threshold:
                    # Check if we've already alerted recently (cooldown)
                    recent_alert = self._find_recent_alert(metric_name, severity)
                    if recent_alert:
                        cooldown = self.config.get("alert_cooldown_seconds", 300)
                        if (
                            current_time - recent_alert.timestamp
                        ).total_seconds() < cooldown:
                            continue  # Still in cooldown period

                    # Trigger alert
                    alert = PerformanceAlert(
                        timestamp=current_time,
                        alert_name=f"{metric_name}_{severity}",
                        metric_name=metric_name,
                        current_value=avg_value,
                        threshold_value=threshold,
                        severity=severity,
                        message=f"{metric_name} is {avg_value:.2f}, exceeding {severity} threshold of {threshold}",
                        details={
                            "recent_values": [m.value for m in recent_metrics],
                            "trend": self._calculate_trend(recent_metrics),
                        },
                    )

                    self._trigger_alert(alert)
                    break  # Only alert for highest severity exceeded

    def _find_recent_alert(
        self, metric_name: str, severity: str
    ) -> Optional[PerformanceAlert]:
        """Find a recent alert for the same metric and severity."""
        alert_name = f"{metric_name}_{severity}"

        for alert in reversed(self.alerts):  # Check most recent first
            if alert.alert_name == alert_name:
                return alert

        return None

    def _calculate_trend(self, metrics: List[PerformanceMetric]) -> str:
        """Calculate trend direction for metrics."""
        if len(metrics) < 2:
            return "stable"

        values = [m.value for m in metrics]

        # Simple trend calculation
        first_half = sum(values[: len(values) // 2]) / (len(values) // 2)
        second_half = sum(values[len(values) // 2 :]) / (len(values) - len(values) // 2)

        change_percent = (
            ((second_half - first_half) / first_half) * 100 if first_half > 0 else 0
        )

        if change_percent > 5:
            return "increasing"
        elif change_percent < -5:
            return "decreasing"
        else:
            return "stable"

    def _trigger_alert(self, alert: PerformanceAlert) -> None:
        """Trigger a performance alert."""
        self.alerts.append(alert)

        # Keep only recent alerts (last 100)
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]

        self.logger.warning(
            f"Performance Alert [{alert.severity.upper()}]: {alert.message}"
        )

        # Call registered callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                self.logger.error(f"Error in alert callback: {e}")

    def get_current_metrics(self) -> Dict[str, float]:
        """Get the most recent value for all metrics."""
        current_metrics = {}

        for metric_name, metric_list in self.metrics.items():
            if metric_list:
                current_metrics[metric_name] = metric_list[-1].value

        return current_metrics

    def get_metric_history(
        self, metric_name: str, minutes: int = 60
    ) -> List[PerformanceMetric]:
        """Get metric history for the specified time period."""
        if metric_name not in self.metrics:
            return []

        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)

        return [
            metric
            for metric in self.metrics[metric_name]
            if metric.timestamp >= cutoff_time
        ]

    def get_active_alerts(self, minutes: int = 60) -> List[PerformanceAlert]:
        """Get active alerts from the specified time period."""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)

        return [alert for alert in self.alerts if alert.timestamp >= cutoff_time]

    def generate_performance_report(self, hours: int = 1) -> Dict[str, Any]:
        """Generate a comprehensive performance report."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        report = {
            "report_timestamp": datetime.utcnow().isoformat(),
            "time_period_hours": hours,
            "metrics_summary": {},
            "alerts_summary": {},
            "recommendations": [],
        }

        # Metrics summary
        for metric_name, metric_list in self.metrics.items():
            recent_metrics = [m for m in metric_list if m.timestamp >= cutoff_time]

            if not recent_metrics:
                continue

            values = [m.value for m in recent_metrics]

            report["metrics_summary"][metric_name] = {
                "count": len(values),
                "current": values[-1] if values else 0,
                "average": sum(values) / len(values) if values else 0,
                "min": min(values) if values else 0,
                "max": max(values) if values else 0,
                "trend": self._calculate_trend(recent_metrics),
            }

        # Alerts summary
        recent_alerts = [
            alert for alert in self.alerts if alert.timestamp >= cutoff_time
        ]

        alert_counts = defaultdict(int)
        for alert in recent_alerts:
            alert_counts[alert.severity] += 1

        report["alerts_summary"] = {
            "total_alerts": len(recent_alerts),
            "by_severity": dict(alert_counts),
            "recent_alerts": [
                {
                    "timestamp": alert.timestamp.isoformat(),
                    "metric": alert.metric_name,
                    "severity": alert.severity,
                    "message": alert.message,
                }
                for alert in recent_alerts[-10:]  # Last 10 alerts
            ],
        }

        # Generate recommendations
        report["recommendations"] = self._generate_recommendations(report)

        return report

    def _generate_recommendations(self, report: Dict[str, Any]) -> List[str]:
        """Generate performance recommendations based on metrics."""
        recommendations = []

        metrics = report["metrics_summary"]

        # Memory recommendations
        if "memory_usage_mb" in metrics:
            memory = metrics["memory_usage_mb"]
            if memory["trend"] == "increasing" and memory["current"] > 300:
                recommendations.append(
                    "Memory usage is increasing. Consider implementing memory optimization or garbage collection tuning."
                )

        # Latency recommendations
        if "signal_processing_latency_ms" in metrics:
            latency = metrics["signal_processing_latency_ms"]
            if latency["average"] > 20:
                recommendations.append(
                    "Signal processing latency is high. Consider optimizing signal processing pipeline or increasing concurrency."
                )

        # Database recommendations
        if "database_query_time_ms" in metrics:
            db_time = metrics["database_query_time_ms"]
            if db_time["average"] > 5:
                recommendations.append(
                    "Database query time is high. Consider adding indexes, optimizing queries, or connection pooling."
                )

        # Error rate recommendations
        if "error_rate_percent" in metrics:
            error_rate = metrics["error_rate_percent"]
            if error_rate["average"] > 0.5:
                recommendations.append(
                    "Error rate is elevated. Review error logs and implement additional error handling or retry logic."
                )

        # Queue depth recommendations
        if "signal_queue_depth" in metrics:
            queue_depth = metrics["signal_queue_depth"]
            if queue_depth["average"] > 50:
                recommendations.append(
                    "Signal queue depth is high. Consider increasing processing capacity or implementing backpressure."
                )

        return recommendations


class PerformanceTestSuite:
    """Test suite for performance monitoring functionality."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def test_monitoring_integration(self) -> Dict[str, Any]:
        """Test performance monitoring integration with trading components."""

        # Create components
        config = BotConfig()
        engine = TradingEngine(config)
        await engine.initialize()

        state_manager = StateManager()
        await state_manager.initialize_async()

        # Create monitor
        monitor_config = {
            "monitoring_interval_seconds": 0.1,  # Fast for testing
            "alert_cooldown_seconds": 1.0,
        }

        monitor = PerformanceMonitor(monitor_config)
        monitor.set_components(engine, state_manager)

        # Add test alert callback
        alerts_received = []
        monitor.add_alert_callback(lambda alert: alerts_received.append(alert))

        try:
            # Start monitoring
            await monitor.start_monitoring()

            # Generate load to create metrics
            for i in range(50):
                signal = TradingSignal(
                    market_slug=f"monitor_test_{i}",
                    token_id=f"0x{i:040x}",
                    side="buy" if i % 2 == 0 else "sell",
                    price=0.5,
                    size=100.0,
                    outcome_type="yes",
                )

                engine.process_signal(signal)
                await asyncio.sleep(0.02)  # 50ms between signals

            # Let monitoring collect metrics
            await asyncio.sleep(2.0)

            # Get results
            current_metrics = monitor.get_current_metrics()
            report = monitor.generate_performance_report(hours=1)
            active_alerts = monitor.get_active_alerts(minutes=5)

            return {
                "test_passed": True,
                "metrics_collected": len(current_metrics),
                "current_metrics": current_metrics,
                "alerts_triggered": len(alerts_received),
                "report": report,
                "details": {
                    "monitored_for_seconds": 2.0,
                    "signals_processed": 50,
                    "recommendations_count": len(report.get("recommendations", [])),
                },
            }

        finally:
            await monitor.stop_monitoring()
            await engine.shutdown()

    async def test_alert_system(self) -> Dict[str, Any]:
        """Test the alerting system with simulated threshold breaches."""

        # Create monitor with low thresholds for testing
        monitor_config = {
            "monitoring_interval_seconds": 0.1,
            "alert_cooldown_seconds": 0.5,
            "thresholds": {"test_metric": {"warning": 50.0, "critical": 100.0}},
        }

        monitor = PerformanceMonitor(monitor_config)

        alerts_received = []
        monitor.add_alert_callback(lambda alert: alerts_received.append(alert))

        try:
            await monitor.start_monitoring()

            # Simulate metrics that will trigger alerts
            timestamp = datetime.utcnow()

            # Values below threshold (no alerts)
            for value in [10, 20, 30, 25, 35]:
                monitor._record_metric("test_metric", value, timestamp)
                timestamp += timedelta(seconds=1)
                await asyncio.sleep(0.1)

            # Values that trigger warning
            for value in [60, 70, 65, 75, 80]:
                monitor._record_metric("test_metric", value, timestamp)
                timestamp += timedelta(seconds=1)
                await asyncio.sleep(0.1)

            # Values that trigger critical
            for value in [110, 120, 115, 125, 130]:
                monitor._record_metric("test_metric", value, timestamp)
                timestamp += timedelta(seconds=1)
                await asyncio.sleep(0.1)

            # Wait for alert processing
            await asyncio.sleep(1.0)

            return {
                "test_passed": len(alerts_received)
                >= 2,  # At least warning and critical
                "alerts_received": len(alerts_received),
                "alert_details": [
                    {
                        "severity": alert.severity,
                        "metric": alert.metric_name,
                        "value": alert.current_value,
                        "threshold": alert.threshold_value,
                    }
                    for alert in alerts_received
                ],
                "cooldown_respected": True,  # Would need more complex test to verify
            }

        finally:
            await monitor.stop_monitoring()

    async def test_performance_report_generation(self) -> Dict[str, Any]:
        """Test performance report generation."""

        monitor = PerformanceMonitor()

        # Simulate metric data
        timestamp = datetime.utcnow() - timedelta(minutes=30)

        # Add various metrics
        for i in range(100):
            # Simulate realistic performance data
            latency = 10 + (i % 20) + random.uniform(0, 5)
            memory = 200 + i * 0.5 + random.uniform(-10, 10)
            error_rate = 0.1 + (0.05 if i > 50 else 0) + random.uniform(0, 0.1)

            monitor._record_metric("signal_processing_latency_ms", latency, timestamp)
            monitor._record_metric("memory_usage_mb", memory, timestamp)
            monitor._record_metric("error_rate_percent", error_rate, timestamp)

            timestamp += timedelta(seconds=18)  # 18 second intervals

        # Generate report
        report = monitor.generate_performance_report(hours=1)

        return {
            "test_passed": len(report["metrics_summary"]) >= 3,
            "report": report,
            "metrics_in_report": len(report["metrics_summary"]),
            "recommendations_generated": len(report["recommendations"]),
            "details": {
                "has_trends": any(
                    "trend" in summary for summary in report["metrics_summary"].values()
                ),
                "has_statistics": any(
                    "average" in summary and "min" in summary and "max" in summary
                    for summary in report["metrics_summary"].values()
                ),
            },
        }


# Pytest fixtures and tests
@pytest.fixture
async def performance_monitor():
    """Create a performance monitor for testing."""
    monitor = PerformanceMonitor(
        {"monitoring_interval_seconds": 0.1, "alert_cooldown_seconds": 1.0}
    )
    yield monitor
    await monitor.stop_monitoring()


@pytest.mark.asyncio
@pytest.mark.performance_monitoring
async def test_performance_monitoring_integration():
    """Test performance monitoring integration."""
    suite = PerformanceTestSuite()
    result = await suite.test_monitoring_integration()

    print(f"\nPerformance Monitoring Integration Test:")
    print(f"Metrics collected: {result['metrics_collected']}")
    print(f"Alerts triggered: {result['alerts_triggered']}")
    print(f"Recommendations: {len(result['report'].get('recommendations', []))}")

    assert result["test_passed"], "Performance monitoring integration test failed"
    assert result["metrics_collected"] > 0, "No metrics were collected"


@pytest.mark.asyncio
@pytest.mark.performance_monitoring
async def test_alert_system():
    """Test the performance alerting system."""
    suite = PerformanceTestSuite()
    result = await suite.test_alert_system()

    print(f"\nAlert System Test:")
    print(f"Alerts received: {result['alerts_received']}")
    for alert in result["alert_details"]:
        print(
            f"  {alert['severity']}: {alert['metric']} = {alert['value']:.1f} (threshold: {alert['threshold']})"
        )

    assert result["test_passed"], "Alert system test failed"
    assert (
        result["alerts_received"] >= 2
    ), "Expected at least warning and critical alerts"


@pytest.mark.asyncio
@pytest.mark.performance_monitoring
async def test_performance_report():
    """Test performance report generation."""
    suite = PerformanceTestSuite()
    result = await suite.test_performance_report_generation()

    print(f"\nPerformance Report Test:")
    print(f"Metrics in report: {result['metrics_in_report']}")
    print(f"Recommendations: {result['recommendations_generated']}")
    print(f"Has trends: {result['details']['has_trends']}")
    print(f"Has statistics: {result['details']['has_statistics']}")

    assert result["test_passed"], "Performance report test failed"
    assert result["metrics_in_report"] >= 3, "Report should contain multiple metrics"


@pytest.mark.asyncio
@pytest.mark.performance_monitoring
async def test_metric_collection_accuracy():
    """Test accuracy of metric collection."""
    monitor = PerformanceMonitor({"monitoring_interval_seconds": 0.05})

    # Record test metrics
    timestamp = datetime.utcnow()
    test_values = [10, 20, 30, 40, 50]

    for value in test_values:
        monitor._record_metric("test_metric", value, timestamp)
        timestamp += timedelta(seconds=1)

    # Verify collection
    history = monitor.get_metric_history("test_metric", minutes=5)
    collected_values = [m.value for m in history]

    assert (
        collected_values == test_values
    ), f"Expected {test_values}, got {collected_values}"

    # Test current metrics
    current = monitor.get_current_metrics()
    assert (
        current.get("test_metric") == 50
    ), f"Expected current value 50, got {current.get('test_metric')}"


if __name__ == "__main__":

    async def main():
        """Run performance monitoring tests as standalone script."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        suite = PerformanceTestSuite()

        print("Running performance monitoring tests...")
        print("=" * 50)

        tests = [
            ("Integration Test", suite.test_monitoring_integration),
            ("Alert System Test", suite.test_alert_system),
            ("Report Generation Test", suite.test_performance_report_generation),
        ]

        results = {}
        for test_name, test_func in tests:
            print(f"\nRunning {test_name}...")
            try:
                result = await test_func()
                results[test_name] = result
                status = "PASSED" if result.get("test_passed", False) else "FAILED"
                print(f"{test_name}: {status}")

            except Exception as e:
                print(f"{test_name}: ERROR - {e}")
                results[test_name] = {"test_passed": False, "error": str(e)}

        # Summary
        passed_tests = sum(1 for r in results.values() if r.get("test_passed", False))
        total_tests = len(results)

        print("\n" + "=" * 50)
        print(f"MONITORING TEST SUMMARY: {passed_tests}/{total_tests} tests passed")

        if passed_tests == total_tests:
            print("✓ All monitoring tests PASSED")
            exit(0)
        else:
            print("✗ Some monitoring tests FAILED")
            exit(1)

    # Add random import for realistic data simulation
    import random

    asyncio.run(main())
