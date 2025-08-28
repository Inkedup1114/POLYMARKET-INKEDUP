"""
Critical alert system for risk management failures and database outages.

Provides comprehensive notification and alerting capabilities for risk system
degradation, including fallback mode transitions and database connectivity issues.
"""

from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

log = logging.getLogger("risk_alerts")


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertCategory(Enum):
    """Alert categories for organization and filtering."""

    DATABASE_FAILURE = "database_failure"
    RISK_SYSTEM_MODE_CHANGE = "risk_system_mode_change"
    POSITION_RECONCILIATION = "position_reconciliation"
    TRADING_HALT = "trading_halt"
    EXPOSURE_LIMIT_BREACH = "exposure_limit_breach"
    SYSTEM_HEALTH = "system_health"


@dataclass
class Alert:
    """Immutable alert data structure."""

    timestamp: float
    severity: AlertSeverity
    category: AlertCategory
    title: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    alert_id: str = field(default="")

    def __post_init__(self):
        if not self.alert_id:
            # Generate unique alert ID
            object.__setattr__(
                self,
                "alert_id",
                f"{self.category.value}_{self.severity.value}_{int(self.timestamp)}",
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert alert to dictionary for serialization."""
        return {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp,
            "severity": self.severity.value,
            "category": self.category.value,
            "title": self.title,
            "message": self.message,
            "context": self.context,
            "human_time": datetime.fromtimestamp(self.timestamp, tz=UTC).isoformat(),
        }

    def to_json(self) -> str:
        """Convert alert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


@runtime_checkable
class AlertHandler(Protocol):
    """Protocol for alert handlers."""

    async def handle_alert(self, alert: Alert) -> bool:
        """Handle an alert. Returns True if handled successfully."""
        ...


class ConsoleAlertHandler:
    """Logs alerts to console with colored output."""

    COLORS = {
        AlertSeverity.INFO: "\033[94m",  # Blue
        AlertSeverity.WARNING: "\033[93m",  # Yellow
        AlertSeverity.CRITICAL: "\033[91m",  # Red
        AlertSeverity.EMERGENCY: "\033[95m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, colored: bool = True):
        self.colored = colored

    async def handle_alert(self, alert: Alert) -> bool:
        """Log alert to console with appropriate formatting."""
        try:
            color = self.COLORS.get(alert.severity, "") if self.colored else ""
            reset = self.RESET if self.colored else ""

            timestamp_str = datetime.fromtimestamp(alert.timestamp, tz=UTC).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )

            header = f"{color}[{alert.severity.value.upper()}] {alert.category.value} - {timestamp_str}{reset}"
            title_line = f"{color}TITLE: {alert.title}{reset}"
            message_line = f"{color}MESSAGE: {alert.message}{reset}"

            log.critical(header)
            log.critical(title_line)
            log.critical(message_line)

            if alert.context:
                context_str = json.dumps(alert.context, indent=2)
                log.critical(f"{color}CONTEXT: {context_str}{reset}")

            # Also log to appropriate level based on severity
            if alert.severity == AlertSeverity.EMERGENCY:
                log.critical(f"EMERGENCY ALERT: {alert.title}")
            elif alert.severity == AlertSeverity.CRITICAL:
                log.error(f"CRITICAL ALERT: {alert.title}")
            elif alert.severity == AlertSeverity.WARNING:
                log.warning(f"WARNING ALERT: {alert.title}")
            else:
                log.info(f"INFO ALERT: {alert.title}")

            return True

        except Exception as e:
            log.error(f"Failed to handle console alert: {e}")
            return False


class FileAlertHandler:
    """Writes alerts to a log file."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    async def handle_alert(self, alert: Alert) -> bool:
        """Write alert to file."""
        try:
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(alert.to_json() + "\n")
            return True
        except Exception as e:
            log.error(f"Failed to write alert to file {self.file_path}: {e}")
            return False


class EmailAlertHandler:
    """Sends alerts via email (for critical/emergency alerts)."""

    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        to_emails: list[str],
        min_severity: AlertSeverity = AlertSeverity.CRITICAL,
    ):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.to_emails = to_emails
        self.min_severity = min_severity
        self.last_email_time: dict[str, float] = {}
        self.email_cooldown = 300  # 5 minutes between duplicate alerts

    async def handle_alert(self, alert: Alert) -> bool:
        """Send alert via email if severity meets threshold."""
        try:
            # Check if severity meets minimum threshold
            severity_levels = {
                AlertSeverity.INFO: 0,
                AlertSeverity.WARNING: 1,
                AlertSeverity.CRITICAL: 2,
                AlertSeverity.EMERGENCY: 3,
            }

            if severity_levels[alert.severity] < severity_levels[self.min_severity]:
                return True  # Not an error, just not sent

            # Check cooldown to prevent spam
            alert_key = f"{alert.category.value}_{alert.severity.value}"
            current_time = time.time()

            if alert_key in self.last_email_time:
                if current_time - self.last_email_time[alert_key] < self.email_cooldown:
                    log.debug(f"Email alert {alert_key} in cooldown period")
                    return True

            # Send email
            await self._send_email(alert)
            self.last_email_time[alert_key] = current_time

            return True

        except Exception as e:
            log.error(f"Failed to send email alert: {e}")
            return False

    async def _send_email(self, alert: Alert) -> None:
        """Send the actual email."""
        # Run in thread pool to avoid blocking
        await asyncio.get_event_loop().run_in_executor(
            None, self._send_email_sync, alert
        )

    def _send_email_sync(self, alert: Alert) -> None:
        """Synchronous email sending."""
        subject = f"[POLYMARKET BOT {alert.severity.value.upper()}] {alert.title}"

        # Create HTML content
        html_content = f"""
        <html>
        <body>
            <h2 style="color: {'red' if alert.severity.value in ['critical', 'emergency'] else 'orange'};">
                {alert.title}
            </h2>
            <p><strong>Severity:</strong> {alert.severity.value.upper()}</p>
            <p><strong>Category:</strong> {alert.category.value}</p>
            <p><strong>Time:</strong> {datetime.fromtimestamp(alert.timestamp, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")}</p>
            <h3>Message:</h3>
            <p>{alert.message}</p>
            
            {f'''
            <h3>Context:</h3>
            <pre>{json.dumps(alert.context, indent=2)}</pre>
            ''' if alert.context else ''}
        </body>
        </html>
        """

        # Create multipart message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = ", ".join(self.to_emails)

        # Create HTML part
        html_part = MIMEText(html_content, "html")
        msg.attach(html_part)

        # Send email
        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)


class WebhookAlertHandler:
    """Sends alerts to a webhook URL (e.g., Slack, Discord, Teams)."""

    def __init__(
        self, webhook_url: str, min_severity: AlertSeverity = AlertSeverity.WARNING
    ):
        self.webhook_url = webhook_url
        self.min_severity = min_severity

    async def handle_alert(self, alert: Alert) -> bool:
        """Send alert to webhook."""
        try:
            import aiohttp

            # Check severity threshold
            severity_levels = {
                AlertSeverity.INFO: 0,
                AlertSeverity.WARNING: 1,
                AlertSeverity.CRITICAL: 2,
                AlertSeverity.EMERGENCY: 3,
            }

            if severity_levels[alert.severity] < severity_levels[self.min_severity]:
                return True

            # Create payload (Slack format)
            payload = {
                "text": f"Polymarket Bot Alert: {alert.title}",
                "attachments": [
                    {
                        "color": self._get_color(alert.severity),
                        "fields": [
                            {
                                "title": "Severity",
                                "value": alert.severity.value.upper(),
                                "short": True,
                            },
                            {
                                "title": "Category",
                                "value": alert.category.value,
                                "short": True,
                            },
                            {
                                "title": "Message",
                                "value": alert.message,
                                "short": False,
                            },
                        ],
                        "footer": "Polymarket Risk System",
                        "ts": int(alert.timestamp),
                    }
                ],
            }

            if alert.context:
                payload["attachments"][0]["fields"].append(
                    {
                        "title": "Context",
                        "value": f"```{json.dumps(alert.context, indent=2)}```",
                        "short": False,
                    }
                )

            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status == 200:
                        return True
                    else:
                        log.error(f"Webhook returned status {response.status}")
                        return False

        except ImportError:
            log.error("aiohttp not available for webhook alerts")
            return False
        except Exception as e:
            log.error(f"Failed to send webhook alert: {e}")
            return False

    def _get_color(self, severity: AlertSeverity) -> str:
        """Get color for Slack attachment based on severity."""
        colors = {
            AlertSeverity.INFO: "good",
            AlertSeverity.WARNING: "warning",
            AlertSeverity.CRITICAL: "danger",
            AlertSeverity.EMERGENCY: "#800080",  # Purple
        }
        return colors.get(severity, "warning")


class RiskAlertManager:
    """
    Central alert management system for risk system events.

    Features:
    - Multiple alert handlers (console, file, email, webhook)
    - Alert deduplication and rate limiting
    - Configurable severity thresholds
    - Async/non-blocking alert delivery
    - Alert history and statistics
    """

    def __init__(self):
        self.handlers: list[AlertHandler] = []
        self.alert_history: list[Alert] = []
        self.alert_counts: dict[str, int] = {}
        self.max_history_size = 1000
        self.deduplication_window = 60  # seconds
        self._last_alerts: dict[str, float] = {}

    def add_handler(self, handler: AlertHandler) -> None:
        """Add an alert handler."""
        self.handlers.append(handler)
        log.info(f"Added alert handler: {type(handler).__name__}")

    def add_console_handler(self, colored: bool = True) -> None:
        """Add console alert handler."""
        self.add_handler(ConsoleAlertHandler(colored=colored))

    def add_file_handler(self, file_path: str | Path) -> None:
        """Add file alert handler."""
        self.add_handler(FileAlertHandler(file_path))

    def add_email_handler(
        self,
        smtp_server: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        to_emails: list[str],
        min_severity: AlertSeverity = AlertSeverity.CRITICAL,
    ) -> None:
        """Add email alert handler."""
        handler = EmailAlertHandler(
            smtp_server,
            smtp_port,
            username,
            password,
            from_email,
            to_emails,
            min_severity,
        )
        self.add_handler(handler)

    def add_webhook_handler(
        self, webhook_url: str, min_severity: AlertSeverity = AlertSeverity.WARNING
    ) -> None:
        """Add webhook alert handler."""
        self.add_handler(WebhookAlertHandler(webhook_url, min_severity))

    async def send_alert(
        self,
        severity: AlertSeverity,
        category: AlertCategory,
        title: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> Alert:
        """Send an alert through all configured handlers."""
        alert = Alert(
            timestamp=time.time(),
            severity=severity,
            category=category,
            title=title,
            message=message,
            context=context or {},
        )

        # Check for deduplication
        alert_key = f"{category.value}_{severity.value}_{title}"
        current_time = time.time()

        if alert_key in self._last_alerts:
            if current_time - self._last_alerts[alert_key] < self.deduplication_window:
                log.debug(f"Skipping duplicate alert: {alert_key}")
                return alert

        self._last_alerts[alert_key] = current_time

        # Add to history
        self.alert_history.append(alert)
        if len(self.alert_history) > self.max_history_size:
            self.alert_history.pop(0)

        # Update counts
        count_key = f"{category.value}_{severity.value}"
        self.alert_counts[count_key] = self.alert_counts.get(count_key, 0) + 1

        # Send to all handlers (non-blocking)
        tasks = []
        for handler in self.handlers:
            task = asyncio.create_task(self._handle_alert_safe(handler, alert))
            tasks.append(task)

        # Wait for all handlers to complete (but don't raise exceptions)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        return alert

    async def _handle_alert_safe(self, handler: AlertHandler, alert: Alert) -> None:
        """Safely handle an alert, catching and logging exceptions."""
        try:
            success = await handler.handle_alert(alert)
            if not success:
                log.warning(
                    f"Handler {type(handler).__name__} failed to handle alert {alert.alert_id}"
                )
        except Exception as e:
            log.error(f"Exception in alert handler {type(handler).__name__}: {e}")

    def get_alert_statistics(self) -> dict[str, Any]:
        """Get alert statistics."""
        return {
            "total_alerts": len(self.alert_history),
            "alert_counts": self.alert_counts.copy(),
            "handlers_count": len(self.handlers),
            "last_alert": (
                self.alert_history[-1].to_dict() if self.alert_history else None
            ),
            "recent_alerts": [alert.to_dict() for alert in self.alert_history[-10:]],
        }

    def clear_history(self) -> None:
        """Clear alert history and statistics."""
        self.alert_history.clear()
        self.alert_counts.clear()
        self._last_alerts.clear()
        log.info("Alert history cleared")

    # Convenience methods for common alert scenarios
    async def database_failure_alert(
        self,
        operation: str,
        error: str,
        failure_count: int,
        context: dict[str, Any] | None = None,
    ) -> Alert:
        """Send database failure alert."""
        severity = (
            AlertSeverity.CRITICAL if failure_count >= 3 else AlertSeverity.WARNING
        )

        return await self.send_alert(
            severity=severity,
            category=AlertCategory.DATABASE_FAILURE,
            title=f"Database Failure in {operation}",
            message=f"Database operation '{operation}' failed: {error}. Failure count: {failure_count}",
            context={
                "operation": operation,
                "error": str(error),
                "failure_count": failure_count,
                **(context or {}),
            },
        )

    async def risk_mode_change_alert(
        self,
        old_mode: str,
        new_mode: str,
        reason: str,
        context: dict[str, Any] | None = None,
    ) -> Alert:
        """Send risk system mode change alert."""
        severity = (
            AlertSeverity.EMERGENCY
            if new_mode == "emergency_halt"
            else AlertSeverity.CRITICAL
        )

        return await self.send_alert(
            severity=severity,
            category=AlertCategory.RISK_SYSTEM_MODE_CHANGE,
            title=f"Risk System Mode Changed: {old_mode} → {new_mode}",
            message=f"Risk system switched from {old_mode} to {new_mode}. Reason: {reason}",
            context={
                "old_mode": old_mode,
                "new_mode": new_mode,
                "reason": reason,
                **(context or {}),
            },
        )

    async def trading_halt_alert(
        self, reason: str, context: dict[str, Any] | None = None
    ) -> Alert:
        """Send trading halt alert."""
        return await self.send_alert(
            severity=AlertSeverity.EMERGENCY,
            category=AlertCategory.TRADING_HALT,
            title="Trading Halted",
            message=f"All trading activity has been suspended. Reason: {reason}",
            context={"reason": reason, **(context or {})},
        )

    async def exposure_breach_alert(
        self,
        limit_type: str,
        current_value: float,
        limit_value: float,
        context: dict[str, Any] | None = None,
    ) -> Alert:
        """Send exposure limit breach alert."""
        return await self.send_alert(
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.EXPOSURE_LIMIT_BREACH,
            title=f"{limit_type} Limit Breached",
            message=f"{limit_type} exposure limit exceeded: ${current_value:,.2f} > ${limit_value:,.2f}",
            context={
                "limit_type": limit_type,
                "current_value": current_value,
                "limit_value": limit_value,
                "breach_amount": current_value - limit_value,
                "breach_percentage": (
                    ((current_value - limit_value) / limit_value * 100)
                    if limit_value > 0
                    else 0
                ),
                **(context or {}),
            },
        )
