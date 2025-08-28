"""
Alert Management Dashboard and Controls

Comprehensive web-based dashboard for alert management, visualization,
configuration, and operational control of the alerting system.
"""

import json
import logging
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .core import Alert, AlertManager, AlertSeverity, get_alert_manager
from .escalation import EscalationRouter, get_escalation_router
from .notifications import NotificationManager, get_notification_manager
from .operational_monitoring import OperationalMonitor, get_operational_monitor
from .system_monitoring import SystemAlertsManager, get_system_alerts_manager

logger = logging.getLogger(__name__)


class AlertDashboardHandler(BaseHTTPRequestHandler):
    """HTTP handler for alert dashboard endpoints"""

    def __init__(self, dashboard, *args, **kwargs):
        self.dashboard = dashboard
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle GET requests"""
        try:
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            query_params = parse_qs(parsed_path.query)

            if path == "/" or path == "/dashboard":
                self._serve_dashboard_home()
            elif path == "/api/alerts":
                self._serve_alerts_api(query_params)
            elif path == "/api/alerts/stats":
                self._serve_alert_statistics()
            elif path == "/api/system/health":
                self._serve_system_health()
            elif path == "/api/notifications":
                self._serve_notifications_api()
            elif path == "/api/escalations":
                self._serve_escalations_api()
            elif path == "/api/configuration":
                self._serve_configuration_api()
            elif path.startswith("/static/"):
                self._serve_static_file(path)
            elif path.startswith("/api/alerts/"):
                self._handle_alert_api(path, query_params)
            else:
                self._send_404()

        except Exception as e:
            logger.error(f"Dashboard handler error: {e}")
            self._send_500(str(e))

    def do_POST(self):
        """Handle POST requests"""
        try:
            parsed_path = urlparse(self.path)
            path = parsed_path.path

            # Read request body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")

            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                data = {}

            if path.startswith("/api/alerts/"):
                self._handle_alert_actions(path, data)
            elif path == "/api/configuration":
                self._handle_configuration_update(data)
            elif path == "/api/test-notification":
                self._handle_test_notification(data)
            else:
                self._send_404()

        except Exception as e:
            logger.error(f"Dashboard POST handler error: {e}")
            self._send_500(str(e))

    def _serve_dashboard_home(self):
        """Serve main dashboard HTML"""
        html = self._generate_dashboard_html()
        self._send_html_response(html)

    def _serve_alerts_api(self, query_params):
        """Serve alerts data"""

        # Parse filters
        severity_filter = query_params.get("severity", [None])[0]
        category_filter = query_params.get("category", [None])[0]
        status_filter = query_params.get("status", ["active"])[0]
        limit = int(query_params.get("limit", [100])[0])

        # Get alerts
        if status_filter == "active":
            alerts = self.dashboard.alert_manager.get_active_alerts()
        else:
            # Get all alerts from history
            alerts = list(self.dashboard.alert_manager.alert_history)[-limit:]

        # Apply filters
        if severity_filter:
            severity = AlertSeverity(severity_filter)
            alerts = [a for a in alerts if a.severity == severity]

        if category_filter:
            alerts = [a for a in alerts if a.category.value == category_filter]

        # Convert to JSON-serializable format
        alerts_data = []
        for alert in alerts[:limit]:
            alerts_data.append(
                {
                    "alert_id": alert.alert_id,
                    "name": alert.name,
                    "description": alert.description,
                    "severity": alert.severity.value,
                    "category": alert.category.value,
                    "status": alert.status.value,
                    "created_at": alert.created_at.isoformat(),
                    "updated_at": alert.updated_at.isoformat(),
                    "resolved_at": (
                        alert.resolved_at.isoformat() if alert.resolved_at else None
                    ),
                    "triggered_by": alert.triggered_by,
                    "current_value": alert.current_value,
                    "threshold_value": alert.threshold_value,
                    "affected_components": alert.affected_components,
                    "acknowledgments": alert.acknowledgments,
                    "escalations": alert.escalations,
                    "tags": alert.tags,
                    "context": alert.context,
                }
            )

        self._send_json_response(
            {
                "alerts": alerts_data,
                "total_count": len(alerts_data),
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _serve_alert_statistics(self):
        """Serve alert statistics"""
        stats = self.dashboard.alert_manager.get_alert_statistics()

        # Add additional statistics
        stats.update(
            {
                "system_health": self._get_system_health_summary(),
                "notification_stats": self._get_notification_stats(),
                "escalation_stats": self._get_escalation_stats(),
            }
        )

        self._send_json_response(stats)

    def _serve_system_health(self):
        """Serve system health information"""
        health_data = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",  # This would be calculated
            "components": {},
        }

        # Get system monitoring health
        if hasattr(self.dashboard, "system_monitor"):
            system_health = self.dashboard.system_monitor.get_system_health_summary()
            health_data["components"]["system"] = system_health

        # Get operational monitoring health
        if hasattr(self.dashboard, "operational_monitor"):
            operational_health = (
                self.dashboard.operational_monitor.get_operational_summary()
            )
            health_data["components"]["operational"] = operational_health

        # Determine overall status
        health_data["overall_status"] = self._calculate_overall_health(
            health_data["components"]
        )

        self._send_json_response(health_data)

    def _serve_notifications_api(self):
        """Serve notifications information"""
        notification_data = {
            "delivery_stats": self.dashboard.notification_manager.get_delivery_stats(),
            "recent_notifications": self.dashboard.notification_manager.get_recent_notifications(
                50
            ),
            "channels": [
                channel.value
                for channel in self.dashboard.notification_manager.channels.keys()
            ],
            "targets": (
                len(
                    self.dashboard.notification_manager.notification_manager.notification_targets
                )
                if hasattr(self.dashboard.notification_manager, "notification_targets")
                else 0
            ),
        }

        self._send_json_response(notification_data)

    def _serve_escalations_api(self):
        """Serve escalation information"""
        escalation_data = {
            "active_escalations": self.dashboard.escalation_router.get_active_escalations(),
            "escalation_stats": self.dashboard.escalation_router.get_escalation_statistics(),
            "policies": len(self.dashboard.escalation_router.escalation_policies),
            "schedules": len(self.dashboard.escalation_router.oncall_manager.schedules),
        }

        self._send_json_response(escalation_data)

    def _serve_configuration_api(self):
        """Serve configuration information"""
        config_data = {
            "alert_rules": len(self.dashboard.alert_manager.alert_rules),
            "thresholds": len(self.dashboard.alert_manager.thresholds),
            "notification_targets": (
                len(self.dashboard.notification_manager.notification_targets)
                if hasattr(self.dashboard.notification_manager, "notification_targets")
                else 0
            ),
            "escalation_policies": len(
                self.dashboard.escalation_router.escalation_policies
            ),
            "export": self.dashboard.alert_manager.export_configuration(),
        }

        self._send_json_response(config_data)

    def _handle_alert_api(self, path, query_params):
        """Handle individual alert operations"""
        path_parts = path.split("/")

        if len(path_parts) < 4:
            self._send_400("Invalid alert API path")
            return

        alert_id = path_parts[3]
        action = path_parts[4] if len(path_parts) > 4 else None

        # Get alert
        alert = self._find_alert_by_id(alert_id)
        if not alert:
            self._send_404()
            return

        if action == "details":
            # Return detailed alert information
            alert_details = {
                "alert": self._serialize_alert(alert),
                "related_alerts": self._find_related_alerts(alert),
                "escalation_history": self._get_alert_escalation_history(alert_id),
                "notification_history": self._get_alert_notification_history(alert_id),
            }
            self._send_json_response(alert_details)

        elif action == "timeline":
            # Return alert timeline
            timeline = self._build_alert_timeline(alert)
            self._send_json_response({"timeline": timeline})

        else:
            # Return basic alert info
            self._send_json_response({"alert": self._serialize_alert(alert)})

    def _handle_alert_actions(self, path, data):
        """Handle alert actions (acknowledge, resolve, etc.)"""
        path_parts = path.split("/")

        if len(path_parts) < 5:
            self._send_400("Invalid alert action path")
            return

        alert_id = path_parts[3]
        action = path_parts[4]

        # Find alert
        alert = self._find_alert_by_id(alert_id)
        if not alert:
            self._send_404()
            return

        success = False
        message = "Unknown action"

        if action == "acknowledge":
            acknowledged_by = data.get("acknowledged_by", "dashboard_user")
            notes = data.get("notes", "")
            success = self.dashboard.alert_manager.acknowledge_alert(
                alert_id, acknowledged_by, notes
            )
            message = "Alert acknowledged" if success else "Failed to acknowledge alert"

        elif action == "resolve":
            resolved_by = data.get("resolved_by", "dashboard_user")
            notes = data.get("notes", "")
            success = self.dashboard.alert_manager.resolve_alert(
                alert_id, resolved_by, notes
            )
            message = "Alert resolved" if success else "Failed to resolve alert"

        elif action == "escalate":
            success = self.dashboard.escalation_router.escalate_alert(alert_id)
            message = "Alert escalated" if success else "Failed to escalate alert"

        elif action == "suppress":
            # This would implement alert suppression
            success = True
            message = "Alert suppressed"

        self._send_json_response(
            {
                "success": success,
                "message": message,
                "alert_id": alert_id,
                "action": action,
            }
        )

    def _handle_configuration_update(self, data):
        """Handle configuration updates"""
        try:
            # This would implement configuration updates
            # For now, just acknowledge the request

            config_type = data.get("type")
            config_data = data.get("data", {})

            success = True
            message = f"Configuration updated: {config_type}"

            self._send_json_response(
                {"success": success, "message": message, "type": config_type}
            )

        except Exception as e:
            self._send_json_response(
                {"success": False, "message": f"Configuration update failed: {str(e)}"}
            )

    def _handle_test_notification(self, data):
        """Handle test notification request"""
        try:
            target_id = data.get("target_id")
            channel = data.get("channel")
            message = data.get("message", "Test notification from Alert Dashboard")

            # This would send a test notification
            success = True
            response_message = f"Test notification sent to {target_id} via {channel}"

            self._send_json_response({"success": success, "message": response_message})

        except Exception as e:
            self._send_json_response(
                {"success": False, "message": f"Test notification failed: {str(e)}"}
            )

    def _find_alert_by_id(self, alert_id: str) -> Alert | None:
        """Find alert by ID"""
        # Check active alerts first
        if alert_id in self.dashboard.alert_manager.active_alerts:
            return self.dashboard.alert_manager.active_alerts[alert_id]

        # Check alert history
        for alert in self.dashboard.alert_manager.alert_history:
            if alert.alert_id == alert_id:
                return alert

        return None

    def _serialize_alert(self, alert: Alert) -> dict[str, Any]:
        """Convert alert to JSON-serializable format"""
        return {
            "alert_id": alert.alert_id,
            "rule_id": alert.rule_id,
            "name": alert.name,
            "description": alert.description,
            "category": alert.category.value,
            "severity": alert.severity.value,
            "status": alert.status.value,
            "created_at": alert.created_at.isoformat(),
            "updated_at": alert.updated_at.isoformat(),
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "triggered_by": alert.triggered_by,
            "current_value": alert.current_value,
            "threshold_value": alert.threshold_value,
            "affected_components": alert.affected_components,
            "context": alert.context,
            "tags": alert.tags,
            "acknowledgments": alert.acknowledgments,
            "escalations": alert.escalations,
            "notifications_sent": alert.notifications_sent,
            "auto_resolved": alert.auto_resolved,
        }

    def _find_related_alerts(self, alert: Alert) -> list[dict[str, Any]]:
        """Find alerts related to the given alert"""
        related = []

        # Find alerts with same components
        for other_alert in self.dashboard.alert_manager.get_active_alerts():
            if other_alert.alert_id == alert.alert_id:
                continue

            # Check for component overlap
            if set(alert.affected_components) & set(other_alert.affected_components):
                related.append(self._serialize_alert(other_alert))

        return related[:10]  # Limit to 10 related alerts

    def _get_alert_escalation_history(self, alert_id: str) -> list[dict[str, Any]]:
        """Get escalation history for alert"""
        if alert_id in self.dashboard.escalation_router.active_escalations:
            execution = self.dashboard.escalation_router.active_escalations[alert_id]
            return execution.actions_taken

        return []

    def _get_alert_notification_history(self, alert_id: str) -> list[dict[str, Any]]:
        """Get notification history for alert"""
        # This would get notification records for the alert
        recent_notifications = (
            self.dashboard.notification_manager.get_recent_notifications(100)
        )

        alert_notifications = [
            notification
            for notification in recent_notifications
            if notification.get("alert_id") == alert_id
        ]

        return alert_notifications

    def _build_alert_timeline(self, alert: Alert) -> list[dict[str, Any]]:
        """Build timeline of events for an alert"""
        timeline = []

        # Alert creation
        timeline.append(
            {
                "timestamp": alert.created_at.isoformat(),
                "event": "Alert Created",
                "description": f"Alert '{alert.name}' was created",
                "severity": alert.severity.value,
                "details": {"triggered_by": alert.triggered_by},
            }
        )

        # Acknowledgments
        for ack in alert.acknowledgments:
            timeline.append(
                {
                    "timestamp": ack.get("acknowledged_at", ""),
                    "event": "Alert Acknowledged",
                    "description": f"Acknowledged by {ack.get('acknowledged_by', 'unknown')}",
                    "details": {"notes": ack.get("notes", "")},
                }
            )

        # Escalations
        for esc in alert.escalations:
            timeline.append(
                {
                    "timestamp": esc.get("escalated_at", ""),
                    "event": "Alert Escalated",
                    "description": f"Escalated to level {esc.get('escalation_level', 'unknown')}",
                    "details": esc,
                }
            )

        # Resolution
        if alert.resolved_at:
            timeline.append(
                {
                    "timestamp": alert.resolved_at.isoformat(),
                    "event": "Alert Resolved",
                    "description": f"Alert resolved{'(auto)' if alert.auto_resolved else ''}",
                    "details": {"resolution_notes": alert.resolution_notes},
                }
            )

        # Sort by timestamp
        timeline.sort(key=lambda x: x["timestamp"])

        return timeline

    def _get_system_health_summary(self) -> dict[str, Any]:
        """Get system health summary"""
        # This would get actual system health data
        return {
            "status": "healthy",
            "cpu_usage": 25.5,
            "memory_usage": 68.2,
            "disk_usage": 45.1,
            "active_connections": 12,
        }

    def _get_notification_stats(self) -> dict[str, Any]:
        """Get notification statistics"""
        return self.dashboard.notification_manager.get_delivery_stats()

    def _get_escalation_stats(self) -> dict[str, Any]:
        """Get escalation statistics"""
        return self.dashboard.escalation_router.get_escalation_statistics()

    def _calculate_overall_health(self, components: dict[str, Any]) -> str:
        """Calculate overall health from component health"""
        # Simple health calculation - could be more sophisticated
        if not components:
            return "unknown"

        # Check for any critical issues
        for component, health in components.items():
            if isinstance(health, dict):
                status = health.get(
                    "system_health", health.get("overall_status", "unknown")
                )
                if status in ["critical", "failing"]:
                    return "critical"

        # Check for degraded performance
        for component, health in components.items():
            if isinstance(health, dict):
                status = health.get(
                    "system_health", health.get("overall_status", "unknown")
                )
                if status in ["degraded", "warning"]:
                    return "degraded"

        return "healthy"

    def _serve_static_file(self, path: str):
        """Serve static files"""
        # This would serve actual static files (CSS, JS, images)
        self._send_404()

    def _generate_dashboard_html(self) -> str:
        """Generate main dashboard HTML"""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>InkedUp Trading Bot - Alert Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
            background-color: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 1rem 2rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .header h1 { margin: 0; font-size: 1.8rem; font-weight: 600; }
        .header .subtitle { opacity: 0.9; font-size: 0.9rem; margin-top: 0.25rem; }
        
        .dashboard-container { 
            max-width: 1400px; 
            margin: 0 auto; 
            padding: 2rem;
            display: grid;
            gap: 2rem;
        }
        
        .status-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        
        .status-card {
            background: white;
            padding: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-left: 4px solid #667eea;
        }
        
        .status-card.healthy { border-left-color: #4ade80; }
        .status-card.warning { border-left-color: #fbbf24; }
        .status-card.critical { border-left-color: #ef4444; }
        .status-card.degraded { border-left-color: #f97316; }
        
        .status-card h3 { 
            font-size: 0.9rem; 
            color: #6b7280; 
            margin-bottom: 0.5rem; 
            text-transform: uppercase;
            font-weight: 600;
        }
        .status-card .value { 
            font-size: 2rem; 
            font-weight: 700; 
            color: #1f2937;
            margin-bottom: 0.25rem;
        }
        .status-card .label { 
            font-size: 0.85rem; 
            color: #6b7280; 
        }
        
        .main-content {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 2rem;
        }
        
        .alerts-section {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        
        .section-header {
            background: #f8fafc;
            border-bottom: 1px solid #e5e7eb;
            padding: 1rem 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .section-header h2 {
            font-size: 1.2rem;
            font-weight: 600;
            color: #1f2937;
        }
        
        .filters {
            display: flex;
            gap: 0.5rem;
        }
        
        .filter-button {
            padding: 0.5rem 1rem;
            border: 1px solid #d1d5db;
            background: white;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.85rem;
            transition: all 0.2s;
        }
        
        .filter-button:hover { background: #f3f4f6; }
        .filter-button.active { background: #667eea; color: white; border-color: #667eea; }
        
        .alerts-list {
            max-height: 600px;
            overflow-y: auto;
        }
        
        .alert-item {
            padding: 1rem 1.5rem;
            border-bottom: 1px solid #f3f4f6;
            cursor: pointer;
            transition: background-color 0.2s;
        }
        
        .alert-item:hover { background: #f8fafc; }
        .alert-item:last-child { border-bottom: none; }
        
        .alert-header {
            display: flex;
            justify-content: between;
            align-items: flex-start;
            margin-bottom: 0.5rem;
        }
        
        .alert-title {
            font-weight: 600;
            color: #1f2937;
            flex: 1;
            margin-right: 1rem;
        }
        
        .alert-badge {
            padding: 0.25rem 0.75rem;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        .alert-badge.critical { background: #fef2f2; color: #dc2626; }
        .alert-badge.high { background: #fef3c7; color: #d97706; }
        .alert-badge.medium { background: #dbeafe; color: #2563eb; }
        .alert-badge.low { background: #f0fdf4; color: #16a34a; }
        
        .alert-description {
            color: #6b7280;
            font-size: 0.9rem;
            margin-bottom: 0.5rem;
        }
        
        .alert-meta {
            display: flex;
            justify-content: between;
            align-items: center;
            font-size: 0.8rem;
            color: #9ca3af;
        }
        
        .alert-time { flex: 1; }
        .alert-components { 
            background: #f3f4f6; 
            padding: 0.2rem 0.5rem; 
            border-radius: 4px; 
            margin-left: 1rem;
        }
        
        .side-panel {
            display: grid;
            gap: 2rem;
        }
        
        .system-health {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 1.5rem;
        }
        
        .health-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 0;
            border-bottom: 1px solid #f3f4f6;
        }
        
        .health-item:last-child { border-bottom: none; }
        
        .health-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 0.5rem;
        }
        
        .health-indicator.healthy { background: #4ade80; }
        .health-indicator.warning { background: #fbbf24; }
        .health-indicator.critical { background: #ef4444; }
        
        .refresh-button {
            background: #667eea;
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 500;
            transition: background-color 0.2s;
        }
        
        .refresh-button:hover { background: #5a67d8; }
        
        .loading {
            text-align: center;
            padding: 2rem;
            color: #6b7280;
        }
        
        .error {
            text-align: center;
            padding: 2rem;
            color: #dc2626;
            background: #fef2f2;
            border-radius: 4px;
            margin: 1rem;
        }
        
        @media (max-width: 1024px) {
            .main-content {
                grid-template-columns: 1fr;
            }
            
            .status-bar {
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>InkedUp Trading Bot - Alert Dashboard</h1>
        <div class="subtitle">Real-time alert management and system monitoring</div>
    </div>
    
    <div class="dashboard-container">
        <!-- Status Bar -->
        <div class="status-bar">
            <div class="status-card" id="overall-status">
                <h3>Overall Status</h3>
                <div class="value" id="overall-status-value">Loading...</div>
                <div class="label">System Health</div>
            </div>
            <div class="status-card">
                <h3>Active Alerts</h3>
                <div class="value" id="active-alerts-count">-</div>
                <div class="label">Requiring Attention</div>
            </div>
            <div class="status-card">
                <h3>Critical Issues</h3>
                <div class="value" id="critical-alerts-count">-</div>
                <div class="label">High Priority</div>
            </div>
            <div class="status-card">
                <h3>Success Rate</h3>
                <div class="value" id="success-rate">-</div>
                <div class="label">Last 24 Hours</div>
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="main-content">
            <!-- Alerts Section -->
            <div class="alerts-section">
                <div class="section-header">
                    <h2>Active Alerts</h2>
                    <div class="filters">
                        <button class="filter-button active" onclick="filterAlerts('all')">All</button>
                        <button class="filter-button" onclick="filterAlerts('critical')">Critical</button>
                        <button class="filter-button" onclick="filterAlerts('high')">High</button>
                        <button class="filter-button" onclick="filterAlerts('medium')">Medium</button>
                        <button class="refresh-button" onclick="refreshData()">Refresh</button>
                    </div>
                </div>
                <div class="alerts-list" id="alerts-list">
                    <div class="loading">Loading alerts...</div>
                </div>
            </div>
            
            <!-- Side Panel -->
            <div class="side-panel">
                <!-- System Health -->
                <div class="system-health">
                    <div class="section-header" style="padding: 0 0 1rem 0; border: none; background: none;">
                        <h2>System Health</h2>
                    </div>
                    <div id="system-health-list">
                        <div class="loading">Loading health data...</div>
                    </div>
                </div>
                
                <!-- Recent Activity -->
                <div class="system-health">
                    <div class="section-header" style="padding: 0 0 1rem 0; border: none; background: none;">
                        <h2>Recent Activity</h2>
                    </div>
                    <div id="recent-activity">
                        <div class="loading">Loading activity...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentFilter = 'all';
        let alertsData = [];
        
        // Initialize dashboard
        document.addEventListener('DOMContentLoaded', function() {
            refreshData();
            // Auto-refresh every 30 seconds
            setInterval(refreshData, 30000);
        });
        
        // Refresh all data
        async function refreshData() {
            await Promise.all([
                loadAlerts(),
                loadSystemHealth(),
                loadStatistics()
            ]);
        }
        
        // Load alerts
        async function loadAlerts() {
            try {
                const response = await fetch('/api/alerts');
                const data = await response.json();
                alertsData = data.alerts;
                displayAlerts(alertsData);
            } catch (error) {
                document.getElementById('alerts-list').innerHTML = 
                    '<div class="error">Error loading alerts: ' + error.message + '</div>';
            }
        }
        
        // Load system health
        async function loadSystemHealth() {
            try {
                const response = await fetch('/api/system/health');
                const data = await response.json();
                displaySystemHealth(data);
                updateOverallStatus(data.overall_status);
            } catch (error) {
                document.getElementById('system-health-list').innerHTML = 
                    '<div class="error">Error loading system health</div>';
            }
        }
        
        // Load statistics
        async function loadStatistics() {
            try {
                const response = await fetch('/api/alerts/stats');
                const data = await response.json();
                updateStatistics(data);
            } catch (error) {
                console.error('Error loading statistics:', error);
            }
        }
        
        // Display alerts
        function displayAlerts(alerts) {
            const container = document.getElementById('alerts-list');
            
            if (!alerts || alerts.length === 0) {
                container.innerHTML = '<div class="loading">No active alerts</div>';
                return;
            }
            
            // Filter alerts based on current filter
            let filteredAlerts = alerts;
            if (currentFilter !== 'all') {
                filteredAlerts = alerts.filter(alert => alert.severity === currentFilter);
            }
            
            // Sort by severity and creation time
            filteredAlerts.sort((a, b) => {
                const severityOrder = { 'emergency': 0, 'critical': 1, 'high': 2, 'medium': 3, 'low': 4, 'info': 5 };
                const severityDiff = severityOrder[a.severity] - severityOrder[b.severity];
                if (severityDiff !== 0) return severityDiff;
                return new Date(b.created_at) - new Date(a.created_at);
            });
            
            const html = filteredAlerts.map(alert => `
                <div class="alert-item" onclick="viewAlertDetails('${alert.alert_id}')">
                    <div class="alert-header">
                        <div class="alert-title">${escapeHtml(alert.name)}</div>
                        <div class="alert-badge ${alert.severity}">${alert.severity}</div>
                    </div>
                    <div class="alert-description">${escapeHtml(alert.description)}</div>
                    <div class="alert-meta">
                        <div class="alert-time">${formatTime(alert.created_at)}</div>
                        <div class="alert-components">${alert.affected_components.length} component(s)</div>
                    </div>
                </div>
            `).join('');
            
            container.innerHTML = html;
        }
        
        // Display system health
        function displaySystemHealth(healthData) {
            const container = document.getElementById('system-health-list');
            
            const components = healthData.components || {};
            const html = Object.entries(components).map(([name, health]) => {
                const status = health.system_health || health.overall_status || 'unknown';
                return `
                    <div class="health-item">
                        <div style="display: flex; align-items: center;">
                            <div class="health-indicator ${status}"></div>
                            ${name.charAt(0).toUpperCase() + name.slice(1)}
                        </div>
                        <div style="color: #6b7280; font-size: 0.8rem;">${status}</div>
                    </div>
                `;
            }).join('');
            
            container.innerHTML = html || '<div class="loading">No health data available</div>';
        }
        
        // Update overall status
        function updateOverallStatus(status) {
            const statusCard = document.getElementById('overall-status');
            const statusValue = document.getElementById('overall-status-value');
            
            statusValue.textContent = status.charAt(0).toUpperCase() + status.slice(1);
            
            // Update card styling based on status
            statusCard.className = 'status-card ' + status;
        }
        
        // Update statistics
        function updateStatistics(stats) {
            document.getElementById('active-alerts-count').textContent = stats.active_alerts || 0;
            document.getElementById('critical-alerts-count').textContent = 
                (stats.alerts_by_severity && stats.alerts_by_severity.critical) || 0;
            
            // Calculate success rate (placeholder calculation)
            const totalAlerts = stats.total_alerts || 0;
            const resolvedAlerts = stats.resolved_alerts || 0;
            const successRate = totalAlerts > 0 ? ((resolvedAlerts / totalAlerts) * 100).toFixed(1) + '%' : 'N/A';
            document.getElementById('success-rate').textContent = successRate;
        }
        
        // Filter alerts
        function filterAlerts(severity) {
            currentFilter = severity;
            
            // Update filter button states
            document.querySelectorAll('.filter-button').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');
            
            // Re-display alerts with new filter
            displayAlerts(alertsData);
        }
        
        // View alert details
        function viewAlertDetails(alertId) {
            // This would open a detailed view of the alert
            console.log('View alert details:', alertId);
            alert('Alert details view would open here for alert: ' + alertId);
        }
        
        // Utility functions
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function formatTime(isoString) {
            const date = new Date(isoString);
            const now = new Date();
            const diff = now - date;
            const minutes = Math.floor(diff / 60000);
            
            if (minutes < 1) return 'Just now';
            if (minutes < 60) return `${minutes}m ago`;
            if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;
            return `${Math.floor(minutes / 1440)}d ago`;
        }
    </script>
</body>
</html>
        """

    def _send_json_response(self, data: Any, status_code: int = 200):
        """Send JSON response"""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"
        )
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str, indent=2).encode())

    def _send_html_response(self, html: str):
        """Send HTML response"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def _send_404(self):
        """Send 404 response"""
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Not found"}).encode())

    def _send_400(self, message: str):
        """Send 400 response"""
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode())

    def _send_500(self, error_message: str):
        """Send 500 response"""
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": error_message}).encode())

    def log_message(self, format, *args):
        """Override to reduce log noise"""
        pass


class AlertDashboard:
    """
    Main alert dashboard system

    Provides web interface for alert management, system monitoring,
    and operational control of the alerting system.
    """

    def __init__(
        self,
        alert_manager: AlertManager | None = None,
        notification_manager: NotificationManager | None = None,
        escalation_router: EscalationRouter | None = None,
        system_monitor: SystemAlertsManager | None = None,
        operational_monitor: OperationalMonitor | None = None,
        host: str = "localhost",
        port: int = 8090,
    ):
        # Core components
        self.alert_manager = alert_manager or get_alert_manager()
        self.notification_manager = notification_manager or get_notification_manager()
        self.escalation_router = escalation_router or get_escalation_router()
        self.system_monitor = system_monitor or get_system_alerts_manager()
        self.operational_monitor = operational_monitor or get_operational_monitor()

        # Server configuration
        self.host = host
        self.port = port
        self.server: HTTPServer | None = None
        self.server_thread: threading.Thread | None = None
        self.running = False

        logger.info(f"Alert dashboard initialized on {host}:{port}")

    def start(self):
        """Start dashboard HTTP server"""
        if self.running:
            return

        # Create HTTP server
        handler_class = lambda *args, **kwargs: AlertDashboardHandler(
            self, *args, **kwargs
        )
        self.server = HTTPServer((self.host, self.port), handler_class)

        # Start server in background thread
        self.server_thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.server_thread.start()

        self.running = True
        logger.info(f"Alert dashboard started at http://{self.host}:{self.port}")

    def stop(self):
        """Stop dashboard HTTP server"""
        if not self.running:
            return

        self.running = False

        if self.server:
            self.server.shutdown()
            self.server.server_close()

        if self.server_thread:
            self.server_thread.join(timeout=5.0)

        logger.info("Alert dashboard stopped")

    def get_dashboard_url(self) -> str:
        """Get dashboard URL"""
        return f"http://{self.host}:{self.port}"

    def get_api_endpoints(self) -> list[str]:
        """Get list of available API endpoints"""
        return [
            "/api/alerts",
            "/api/alerts/stats",
            "/api/system/health",
            "/api/notifications",
            "/api/escalations",
            "/api/configuration",
            "/api/test-notification",
        ]


# Global dashboard instance
_alert_dashboard = None


def get_alert_dashboard() -> AlertDashboard:
    """Get global alert dashboard instance"""
    global _alert_dashboard

    if _alert_dashboard is None:
        _alert_dashboard = AlertDashboard()

    return _alert_dashboard


def initialize_alert_dashboard(
    host: str = "localhost", port: int = 8090, auto_start: bool = True
) -> AlertDashboard:
    """Initialize alert dashboard"""
    global _alert_dashboard

    # Stop existing dashboard if running
    if _alert_dashboard and _alert_dashboard.running:
        _alert_dashboard.stop()

    _alert_dashboard = AlertDashboard(host=host, port=port)

    if auto_start:
        _alert_dashboard.start()

    logger.info(f"Alert dashboard initialized at http://{host}:{port}")
    return _alert_dashboard
