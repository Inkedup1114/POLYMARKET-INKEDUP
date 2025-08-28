"""
Comprehensive Alerting System for InkedUp Trading Bot

Automated alerting system integrated with risk management, providing alerts for
risk breaches, system failures, performance degradation, and operational issues.

Features:
- Configurable thresholds and alert rules
- Multiple notification channels (email, SMS, Slack, webhooks)
- Alert escalation policies with on-call scheduling
- Risk management integration
- System failure and performance monitoring
- Operational issue detection
- Real-time dashboard and controls
- Integration with existing performance metrics

Usage:
    from inkedup_bot.alerting import AlertingSystem

    # Initialize complete alerting system
    alerting = AlertingSystem()
    await alerting.initialize()
    await alerting.start()

    # Access dashboard at http://localhost:8090
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .core import AlertManager, initialize_alerting_system
from .dashboard import AlertDashboard, initialize_alert_dashboard
from .escalation import EscalationRouter, initialize_escalation_system
from .notifications import NotificationManager, initialize_notification_system
from .operational_monitoring import (
    OperationalMonitor,
    initialize_operational_monitoring,
)
from .performance_integration import (
    PerformanceMetricsConnector,
    initialize_performance_integration,
)
from .risk_integration import RiskMetricsMonitor, setup_default_risk_monitoring
from .system_monitoring import SystemAlertsManager, initialize_system_monitoring

logger = logging.getLogger(__name__)


class AlertingSystem:
    """
    Complete alerting system for the InkedUp trading bot

    Integrates all alerting components into a unified system providing
    comprehensive monitoring and notification capabilities.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

        # Core components
        self.alert_manager: AlertManager | None = None
        self.notification_manager: NotificationManager | None = None
        self.escalation_router: EscalationRouter | None = None

        # Specialized monitors
        self.system_monitor: SystemAlertsManager | None = None
        self.operational_monitor: OperationalMonitor | None = None
        self.risk_monitor: RiskMetricsMonitor | None = None

        # Integration components
        self.performance_connector: PerformanceMetricsConnector | None = None
        self.dashboard: AlertDashboard | None = None

        # System state
        self.initialized = False
        self.running = False

        logger.info("Alerting system created")

    async def initialize(
        self,
        notification_config: dict[str, Any] | None = None,
        escalation_config: dict[str, Any] | None = None,
        dashboard_config: dict[str, Any] | None = None,
    ) -> bool:
        """Initialize all alerting components"""

        if self.initialized:
            logger.warning("Alerting system already initialized")
            return True

        try:
            # Initialize core alert manager
            self.alert_manager = initialize_alerting_system()

            # Initialize notification system
            notification_config = notification_config or self.config.get(
                "notifications", {}
            )
            self.notification_manager = initialize_notification_system(
                notification_config
            )

            # Initialize escalation system
            escalation_config = escalation_config or self.config.get("escalation", {})
            policies_config = escalation_config.get("policies", [])
            schedules_config = escalation_config.get("schedules", [])
            self.escalation_router = initialize_escalation_system(
                policies_config, schedules_config
            )

            # Initialize system monitoring
            system_thresholds = self.config.get("system_thresholds")
            self.system_monitor = initialize_system_monitoring(system_thresholds)

            # Initialize operational monitoring
            self.operational_monitor = initialize_operational_monitoring()

            # Initialize risk monitoring
            self.risk_monitor = setup_default_risk_monitoring(self.alert_manager)

            # Initialize performance integration
            self.performance_connector = await initialize_performance_integration(
                alert_manager=self.alert_manager,
                auto_start=False,  # We'll start it manually
            )

            # Initialize dashboard
            dashboard_config = dashboard_config or self.config.get("dashboard", {})
            dashboard_host = dashboard_config.get("host", "localhost")
            dashboard_port = dashboard_config.get("port", 8090)

            self.dashboard = initialize_alert_dashboard(
                host=dashboard_host,
                port=dashboard_port,
                auto_start=False,  # We'll start it manually
            )

            # Connect components
            await self._connect_components()

            self.initialized = True
            logger.info("Alerting system initialized successfully")

            return True

        except Exception as e:
            logger.error(f"Failed to initialize alerting system: {e}")
            return False

    async def start(self) -> bool:
        """Start all alerting system components"""

        if not self.initialized:
            logger.error("Alerting system must be initialized before starting")
            return False

        if self.running:
            logger.warning("Alerting system already running")
            return True

        try:
            # Start core alert manager
            await self.alert_manager.start()

            # Start system monitoring
            await self.system_monitor.start_monitoring()

            # Start operational monitoring
            await self.operational_monitor.start_monitoring()

            # Start risk monitoring
            asyncio.create_task(self.risk_monitor.monitor_risk_metrics())

            # Start performance integration
            await self.performance_connector.start_monitoring()

            # Start dashboard
            self.dashboard.start()

            self.running = True

            # Log system status
            await self._log_system_status()

            logger.info("Alerting system started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start alerting system: {e}")
            return False

    async def stop(self) -> bool:
        """Stop all alerting system components"""

        if not self.running:
            logger.warning("Alerting system not running")
            return True

        try:
            # Stop dashboard
            if self.dashboard:
                self.dashboard.stop()

            # Stop performance integration
            if self.performance_connector:
                await self.performance_connector.stop_monitoring()

            # Stop operational monitoring
            if self.operational_monitor:
                await self.operational_monitor.stop_monitoring()

            # Stop system monitoring
            if self.system_monitor:
                await self.system_monitor.stop_monitoring()

            # Stop core alert manager
            if self.alert_manager:
                await self.alert_manager.stop()

            self.running = False
            logger.info("Alerting system stopped successfully")

            return True

        except Exception as e:
            logger.error(f"Error stopping alerting system: {e}")
            return False

    async def _connect_components(self):
        """Connect all alerting components together"""

        # Connect system monitor to operational monitor
        if self.system_monitor and self.operational_monitor:
            # This would set up cross-component communication
            pass

        # Connect performance connector to monitors
        if self.performance_connector:
            if self.system_monitor:
                self.performance_connector.connect_system_monitor(self.system_monitor)
            if self.operational_monitor:
                self.performance_connector.connect_operational_monitor(
                    self.operational_monitor
                )
            if self.risk_monitor:
                self.performance_connector.connect_risk_monitor(self.risk_monitor)

        # Connect dashboard to all components
        if self.dashboard:
            self.dashboard.alert_manager = self.alert_manager
            self.dashboard.notification_manager = self.notification_manager
            self.dashboard.escalation_router = self.escalation_router
            self.dashboard.system_monitor = self.system_monitor
            self.dashboard.operational_monitor = self.operational_monitor

        logger.debug("Alerting components connected")

    async def _log_system_status(self):
        """Log comprehensive system status"""

        status_info = []

        if self.alert_manager:
            stats = self.alert_manager.get_alert_statistics()
            status_info.append(
                f"Alert Manager: {stats['total_rules']} rules, {stats['active_alerts']} active alerts"
            )

        if self.notification_manager:
            stats = self.notification_manager.get_delivery_stats()
            status_info.append(
                f"Notifications: {len(self.notification_manager.channels)} channels configured"
            )

        if self.dashboard:
            dashboard_url = self.dashboard.get_dashboard_url()
            status_info.append(f"Dashboard: {dashboard_url}")

        if self.performance_connector:
            integration_status = self.performance_connector.get_integration_status()
            connected_trackers = len(integration_status["connected_trackers"])
            status_info.append(
                f"Performance Integration: {connected_trackers} trackers connected"
            )

        logger.info("ALERTING SYSTEM STATUS:")
        for info in status_info:
            logger.info(f"  • {info}")

    def get_system_summary(self) -> dict[str, Any]:
        """Get comprehensive system summary"""

        summary = {
            "initialized": self.initialized,
            "running": self.running,
            "timestamp": datetime.now().isoformat(),
            "components": {},
        }

        # Alert manager stats
        if self.alert_manager:
            summary["components"][
                "alert_manager"
            ] = self.alert_manager.get_alert_statistics()

        # Notification stats
        if self.notification_manager:
            summary["components"][
                "notifications"
            ] = self.notification_manager.get_delivery_stats()

        # Escalation stats
        if self.escalation_router:
            summary["components"][
                "escalation"
            ] = self.escalation_router.get_escalation_statistics()

        # System health
        if self.system_monitor:
            summary["components"][
                "system_health"
            ] = self.system_monitor.get_system_health_summary()

        # Operational health
        if self.operational_monitor:
            summary["components"][
                "operational"
            ] = self.operational_monitor.get_operational_summary()

        # Risk monitoring
        if self.risk_monitor:
            summary["components"]["risk"] = self.risk_monitor.get_risk_metrics_summary()

        # Performance integration
        if self.performance_connector:
            summary["components"][
                "performance_integration"
            ] = self.performance_connector.get_integration_status()

        # Dashboard info
        if self.dashboard:
            summary["dashboard_url"] = self.dashboard.get_dashboard_url()
            summary["api_endpoints"] = self.dashboard.get_api_endpoints()

        return summary

    def create_test_alert(
        self,
        name: str = "Test Alert",
        description: str = "Test alert from alerting system",
        severity: str = "medium",
    ) -> str | None:
        """Create a test alert for testing purposes"""

        if not self.alert_manager:
            logger.error("Alert manager not initialized")
            return None

        try:
            # Create test alert rule if it doesn't exist
            test_rule_id = "test_alert_rule"

            if test_rule_id not in self.alert_manager.alert_rules:
                from .core import AlertCategory, AlertRule, AlertSeverity

                test_rule = AlertRule(
                    rule_id=test_rule_id,
                    name="Test Alert Rule",
                    category=AlertCategory.OPERATIONAL_ISSUE,
                    description="Rule for creating test alerts",
                    condition="manual_test",
                    severity=AlertSeverity.MEDIUM,
                    enabled=True,
                    tags={"type": "test"},
                    auto_resolve=False,
                    cooldown_seconds=60,
                    max_frequency=5,
                )

                self.alert_manager.add_alert_rule(test_rule)

            # Create test alert
            from .core import AlertSeverity

            severity_mapping = {
                "low": AlertSeverity.LOW,
                "medium": AlertSeverity.MEDIUM,
                "high": AlertSeverity.HIGH,
                "critical": AlertSeverity.CRITICAL,
                "emergency": AlertSeverity.EMERGENCY,
            }

            alert_severity = severity_mapping.get(
                severity.lower(), AlertSeverity.MEDIUM
            )

            alert = self.alert_manager.create_alert(
                rule_id=test_rule_id,
                triggered_by="Manual test",
                affected_components=["test_component"],
                context={
                    "test": True,
                    "created_by": "alerting_system",
                    "description": description,
                },
            )

            if alert:
                logger.info(f"Test alert created: {alert.alert_id}")
                return alert.alert_id
            else:
                logger.error("Failed to create test alert")
                return None

        except Exception as e:
            logger.error(f"Error creating test alert: {e}")
            return None


# Factory functions for easy initialization


def create_default_alerting_system() -> AlertingSystem:
    """Create alerting system with default configuration"""

    default_config = {
        "notifications": {
            "channels": {
                "email": {
                    "smtp_server": "localhost",
                    "smtp_port": 587,
                    "from_email": "alerts@trading-bot.com",
                    "use_tls": True,
                },
                "webhook": {"timeout": 30, "verify_ssl": True},
            }
        },
        "escalation": {"policies": [], "schedules": []},
        "dashboard": {"host": "localhost", "port": 8090},
        "system_thresholds": {
            "cpu_usage": {"warning": 75.0, "critical": 90.0, "emergency": 95.0},
            "memory_usage": {"warning": 80.0, "critical": 90.0, "emergency": 95.0},
            "disk_usage": {"warning": 85.0, "critical": 95.0, "emergency": 98.0},
        },
    }

    return AlertingSystem(default_config)


def create_production_alerting_system(
    email_config: dict[str, Any],
    slack_webhook_url: str | None = None,
    dashboard_port: int = 8090,
) -> AlertingSystem:
    """Create alerting system configured for production use"""

    production_config = {
        "notifications": {"channels": {"email": email_config}},
        "escalation": {
            "policies": [
                {
                    "policy_id": "standard_escalation",
                    "name": "Standard Escalation Policy",
                    "description": "Standard 3-level escalation",
                    "levels": [
                        {
                            "level": 1,
                            "name": "Initial Response",
                            "description": "Notify primary team",
                            "trigger_delay_minutes": 0,
                            "actions": ["notify_additional"],
                            "notification_targets": ["primary_team"],
                            "repeat_interval_minutes": 15,
                            "max_repeats": 2,
                            "enabled": True,
                        },
                        {
                            "level": 2,
                            "name": "Escalate to On-Call",
                            "description": "Page on-call engineer",
                            "trigger_delay_minutes": 15,
                            "actions": ["page_oncall", "increase_frequency"],
                            "notification_targets": ["oncall_team"],
                            "repeat_interval_minutes": 5,
                            "max_repeats": 5,
                            "enabled": True,
                        },
                        {
                            "level": 3,
                            "name": "Management Escalation",
                            "description": "Escalate to management",
                            "trigger_delay_minutes": 45,
                            "actions": ["escalate_management"],
                            "notification_targets": ["management"],
                            "repeat_interval_minutes": 10,
                            "max_repeats": 3,
                            "enabled": True,
                        },
                    ],
                    "enabled": True,
                    "applies_to_severities": ["high", "critical", "emergency"],
                    "escalation_timeout": 30,
                    "max_escalation_level": 3,
                }
            ],
            "schedules": [],
        },
        "dashboard": {
            "host": "0.0.0.0",  # Allow external access in production
            "port": dashboard_port,
        },
        "system_thresholds": {
            "cpu_usage": {"warning": 70.0, "critical": 85.0, "emergency": 95.0},
            "memory_usage": {"warning": 75.0, "critical": 85.0, "emergency": 95.0},
            "disk_usage": {"warning": 80.0, "critical": 90.0, "emergency": 95.0},
            "load_average": {"warning": 2.0, "critical": 4.0, "emergency": 8.0},
            "response_time": {
                "warning": 500.0,
                "critical": 2000.0,
                "emergency": 5000.0,
            },
        },
    }

    # Add Slack if configured
    if slack_webhook_url:
        production_config["notifications"]["channels"]["slack"] = {
            "webhook_url": slack_webhook_url
        }

    return AlertingSystem(production_config)


# Export main classes and functions
__all__ = [
    "AlertingSystem",
    "create_default_alerting_system",
    "create_production_alerting_system",
    "AlertManager",
    "NotificationManager",
    "EscalationRouter",
    "SystemAlertsManager",
    "OperationalMonitor",
    "RiskMetricsMonitor",
    "AlertDashboard",
    "PerformanceMetricsConnector",
]
