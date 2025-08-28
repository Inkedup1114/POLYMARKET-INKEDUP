"""
Multiple Notification Channels

Comprehensive notification system supporting email, SMS, Slack, webhooks,
and other communication channels with rate limiting, formatting, and
delivery tracking.
"""

import asyncio
import json
import logging
import smtplib
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.mime.multipart import MimeMultipart
from email.mime.text import MimeText
from enum import Enum
from typing import Any

import aiohttp

from .core import Alert, AlertSeverity, NotificationChannel, NotificationTarget

logger = logging.getLogger(__name__)


class NotificationStatus(Enum):
    """Notification delivery status"""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    FILTERED = "filtered"
    RETRYING = "retrying"


@dataclass
class NotificationRecord:
    """Record of a sent notification"""

    record_id: str
    alert_id: str
    target_id: str
    channel: NotificationChannel
    status: NotificationStatus
    created_at: datetime
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    error_message: str | None = None
    retry_count: int = 0
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationTemplate:
    """Template for formatting notifications"""

    template_id: str
    name: str
    channel: NotificationChannel
    subject_template: str
    body_template: str
    format_type: str = "text"  # text, html, markdown, json
    enabled: bool = True
    tags: dict[str, str] = field(default_factory=dict)


class NotificationChannelBase(ABC):
    """Base class for notification channels"""

    def __init__(self, channel: NotificationChannel, config: dict[str, Any]):
        self.channel = channel
        self.config = config
        self.rate_limits: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.delivery_stats = {
            "sent": 0,
            "delivered": 0,
            "failed": 0,
            "rate_limited": 0,
        }

    @abstractmethod
    async def send_notification(
        self,
        target: NotificationTarget,
        alert: Alert,
        template: NotificationTemplate | None = None,
    ) -> NotificationRecord:
        """Send notification through this channel"""
        pass

    def check_rate_limit(self, target: NotificationTarget) -> bool:
        """Check if target has exceeded rate limit"""
        if target.rate_limit <= 0:
            return True  # No rate limiting

        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Clean old entries
        target_rates = self.rate_limits[target.target_id]
        while target_rates and target_rates[0] < one_hour_ago:
            target_rates.popleft()

        # Check if under limit
        return len(target_rates) < target.rate_limit

    def record_send_attempt(self, target: NotificationTarget):
        """Record a send attempt for rate limiting"""
        self.rate_limits[target.target_id].append(datetime.now())

    def format_message(
        self, alert: Alert, template: NotificationTemplate | None = None
    ) -> dict[str, str]:
        """Format alert message using template"""
        if template:
            # Use custom template
            subject = self._apply_template(template.subject_template, alert)
            body = self._apply_template(template.body_template, alert)
        else:
            # Use default formatting
            subject = f"[{alert.severity.value.upper()}] {alert.name}"
            body = self._format_default_message(alert)

        return {"subject": subject, "body": body}

    def _apply_template(self, template: str, alert: Alert) -> str:
        """Apply template variables to create message"""
        replacements = {
            "alert_id": alert.alert_id,
            "alert_name": alert.name,
            "alert_description": alert.description,
            "severity": alert.severity.value,
            "category": alert.category.value,
            "status": alert.status.value,
            "created_at": alert.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "current_value": (
                str(alert.current_value) if alert.current_value is not None else "N/A"
            ),
            "threshold_value": (
                str(alert.threshold_value)
                if alert.threshold_value is not None
                else "N/A"
            ),
            "affected_components": ", ".join(alert.affected_components),
            "triggered_by": alert.triggered_by,
        }

        # Add context variables
        for key, value in alert.context.items():
            replacements[f"context.{key}"] = str(value)

        # Add tag variables
        for key, value in alert.tags.items():
            replacements[f"tag.{key}"] = str(value)

        # Replace variables in template
        message = template
        for key, value in replacements.items():
            message = message.replace(f"{{{key}}}", value)

        return message

    def _format_default_message(self, alert: Alert) -> str:
        """Create default message format"""
        lines = [
            f"Alert: {alert.name}",
            f"Severity: {alert.severity.value.upper()}",
            f"Category: {alert.category.value}",
            f"Description: {alert.description}",
            f"Triggered by: {alert.triggered_by}",
            f"Created: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ]

        if alert.current_value is not None:
            lines.append(f"Current Value: {alert.current_value}")

        if alert.threshold_value is not None:
            lines.append(f"Threshold: {alert.threshold_value}")

        if alert.affected_components:
            lines.append(f"Affected Components: {', '.join(alert.affected_components)}")

        if alert.context:
            lines.append("Context:")
            for key, value in alert.context.items():
                lines.append(f"  {key}: {value}")

        return "\n".join(lines)


class EmailNotificationChannel(NotificationChannelBase):
    """Email notification channel"""

    def __init__(self, config: dict[str, Any]):
        super().__init__(NotificationChannel.EMAIL, config)
        self.smtp_server = config.get("smtp_server", "localhost")
        self.smtp_port = config.get("smtp_port", 587)
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.from_email = config.get("from_email", "alerts@trading-bot.com")
        self.use_tls = config.get("use_tls", True)

    async def send_notification(
        self,
        target: NotificationTarget,
        alert: Alert,
        template: NotificationTemplate | None = None,
    ) -> NotificationRecord:
        """Send email notification"""

        record = NotificationRecord(
            record_id=f"email_{alert.alert_id}_{target.target_id}",
            alert_id=alert.alert_id,
            target_id=target.target_id,
            channel=NotificationChannel.EMAIL,
            status=NotificationStatus.PENDING,
            created_at=datetime.now(),
        )

        try:
            # Check rate limit
            if not self.check_rate_limit(target):
                record.status = NotificationStatus.RATE_LIMITED
                self.delivery_stats["rate_limited"] += 1
                return record

            # Format message
            message_parts = self.format_message(alert, template)

            # Create email message
            msg = MimeMultipart()
            msg["From"] = self.from_email
            msg["To"] = target.address
            msg["Subject"] = message_parts["subject"]

            # Add body
            if template and template.format_type == "html":
                msg.attach(MimeText(message_parts["body"], "html"))
            else:
                msg.attach(MimeText(message_parts["body"], "plain"))

            # Send email
            await self._send_smtp_email(msg, target.address)

            record.status = NotificationStatus.SENT
            record.sent_at = datetime.now()
            self.record_send_attempt(target)
            self.delivery_stats["sent"] += 1

            logger.info(
                f"Email notification sent to {target.address} for alert {alert.alert_id}"
            )

        except Exception as e:
            record.status = NotificationStatus.FAILED
            record.error_message = str(e)
            self.delivery_stats["failed"] += 1
            logger.error(f"Failed to send email notification: {e}")

        return record

    async def _send_smtp_email(self, msg: MimeMultipart, to_address: str):
        """Send email via SMTP"""

        def send_sync():
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            if self.use_tls:
                server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
            server.send_message(msg)
            server.quit()

        # Run SMTP in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, send_sync)


class SlackNotificationChannel(NotificationChannelBase):
    """Slack notification channel"""

    def __init__(self, config: dict[str, Any]):
        super().__init__(NotificationChannel.SLACK, config)
        self.webhook_url = config.get("webhook_url", "")
        self.bot_token = config.get("bot_token", "")
        self.default_channel = config.get("default_channel", "#alerts")

    async def send_notification(
        self,
        target: NotificationTarget,
        alert: Alert,
        template: NotificationTemplate | None = None,
    ) -> NotificationRecord:
        """Send Slack notification"""

        record = NotificationRecord(
            record_id=f"slack_{alert.alert_id}_{target.target_id}",
            alert_id=alert.alert_id,
            target_id=target.target_id,
            channel=NotificationChannel.SLACK,
            status=NotificationStatus.PENDING,
            created_at=datetime.now(),
        )

        try:
            # Check rate limit
            if not self.check_rate_limit(target):
                record.status = NotificationStatus.RATE_LIMITED
                self.delivery_stats["rate_limited"] += 1
                return record

            # Create Slack message
            slack_message = self._create_slack_message(alert, target, template)

            # Send via webhook or API
            if self.webhook_url:
                await self._send_webhook_message(slack_message)
            elif self.bot_token:
                await self._send_api_message(
                    slack_message, target.address or self.default_channel
                )
            else:
                raise ValueError("No Slack webhook URL or bot token configured")

            record.status = NotificationStatus.SENT
            record.sent_at = datetime.now()
            self.record_send_attempt(target)
            self.delivery_stats["sent"] += 1

            logger.info(f"Slack notification sent for alert {alert.alert_id}")

        except Exception as e:
            record.status = NotificationStatus.FAILED
            record.error_message = str(e)
            self.delivery_stats["failed"] += 1
            logger.error(f"Failed to send Slack notification: {e}")

        return record

    def _create_slack_message(
        self,
        alert: Alert,
        target: NotificationTarget,
        template: NotificationTemplate | None = None,
    ) -> dict[str, Any]:
        """Create Slack message payload"""

        # Severity colors
        color_map = {
            AlertSeverity.INFO: "#36a64f",  # Green
            AlertSeverity.LOW: "#439fe0",  # Blue
            AlertSeverity.MEDIUM: "#ff9500",  # Orange
            AlertSeverity.HIGH: "#ff6b35",  # Red-orange
            AlertSeverity.CRITICAL: "#e01e37",  # Red
            AlertSeverity.EMERGENCY: "#8b0000",  # Dark red
        }

        color = color_map.get(alert.severity, "#808080")

        if template:
            # Use custom template
            message_parts = self.format_message(alert, template)
            text = message_parts["body"]
        else:
            # Create rich Slack message
            text = f"*{alert.name}*\n{alert.description}"

        # Create attachment with alert details
        attachment = {
            "color": color,
            "title": f"{alert.severity.value.upper()} Alert",
            "text": text,
            "fields": [
                {"title": "Alert ID", "value": alert.alert_id, "short": True},
                {"title": "Category", "value": alert.category.value, "short": True},
                {"title": "Triggered By", "value": alert.triggered_by, "short": False},
            ],
            "timestamp": int(alert.created_at.timestamp()),
            "footer": "Trading Bot Alerts",
            "footer_icon": "https://slack.com/img/icons/app-57.png",
        }

        # Add current value if available
        if alert.current_value is not None:
            attachment["fields"].append(
                {
                    "title": "Current Value",
                    "value": str(alert.current_value),
                    "short": True,
                }
            )

        # Add threshold if available
        if alert.threshold_value is not None:
            attachment["fields"].append(
                {
                    "title": "Threshold",
                    "value": str(alert.threshold_value),
                    "short": True,
                }
            )

        # Add affected components
        if alert.affected_components:
            attachment["fields"].append(
                {
                    "title": "Affected Components",
                    "value": ", ".join(alert.affected_components),
                    "short": False,
                }
            )

        return {"text": f"Alert: {alert.name}", "attachments": [attachment]}

    async def _send_webhook_message(self, message: dict[str, Any]):
        """Send message via webhook"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.webhook_url,
                json=message,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status != 200:
                    raise Exception(
                        f"Slack webhook failed with status {response.status}"
                    )

    async def _send_api_message(self, message: dict[str, Any], channel: str):
        """Send message via Slack API"""
        url = "https://slack.com/api/chat.postMessage"
        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json",
        }

        payload = {"channel": channel, **message}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Slack API failed with status {response.status}")


class SMSNotificationChannel(NotificationChannelBase):
    """SMS notification channel (via Twilio or similar)"""

    def __init__(self, config: dict[str, Any]):
        super().__init__(NotificationChannel.SMS, config)
        self.service_type = config.get("service_type", "twilio")
        self.account_sid = config.get("account_sid", "")
        self.auth_token = config.get("auth_token", "")
        self.from_number = config.get("from_number", "")
        self.api_url = config.get("api_url", "")

    async def send_notification(
        self,
        target: NotificationTarget,
        alert: Alert,
        template: NotificationTemplate | None = None,
    ) -> NotificationRecord:
        """Send SMS notification"""

        record = NotificationRecord(
            record_id=f"sms_{alert.alert_id}_{target.target_id}",
            alert_id=alert.alert_id,
            target_id=target.target_id,
            channel=NotificationChannel.SMS,
            status=NotificationStatus.PENDING,
            created_at=datetime.now(),
        )

        try:
            # Check rate limit
            if not self.check_rate_limit(target):
                record.status = NotificationStatus.RATE_LIMITED
                self.delivery_stats["rate_limited"] += 1
                return record

            # Format message (SMS has length limits)
            message_text = self._format_sms_message(alert, template)

            # Send SMS based on service type
            if self.service_type == "twilio":
                await self._send_twilio_sms(target.address, message_text)
            else:
                await self._send_generic_sms(target.address, message_text)

            record.status = NotificationStatus.SENT
            record.sent_at = datetime.now()
            self.record_send_attempt(target)
            self.delivery_stats["sent"] += 1

            logger.info(
                f"SMS notification sent to {target.address} for alert {alert.alert_id}"
            )

        except Exception as e:
            record.status = NotificationStatus.FAILED
            record.error_message = str(e)
            self.delivery_stats["failed"] += 1
            logger.error(f"Failed to send SMS notification: {e}")

        return record

    def _format_sms_message(
        self, alert: Alert, template: NotificationTemplate | None = None
    ) -> str:
        """Format message for SMS (with length limits)"""
        if template:
            message = self.format_message(alert, template)["body"]
        else:
            # Create concise SMS message
            message = (
                f"ALERT [{alert.severity.value.upper()}]: {alert.name}\n"
                f"{alert.description[:100]}..."
                f"\nTriggered: {alert.created_at.strftime('%H:%M UTC')}"
            )

        # Truncate to SMS length limit (160 chars for single SMS)
        if len(message) > 155:
            message = message[:152] + "..."

        return message

    async def _send_twilio_sms(self, to_number: str, message: str):
        """Send SMS via Twilio API"""
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"

        auth = aiohttp.BasicAuth(self.account_sid, self.auth_token)
        data = {"From": self.from_number, "To": to_number, "Body": message}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, auth=auth, data=data) as response:
                if response.status not in [200, 201]:
                    error_text = await response.text()
                    raise Exception(
                        f"Twilio SMS failed: {response.status} - {error_text}"
                    )

    async def _send_generic_sms(self, to_number: str, message: str):
        """Send SMS via generic API"""
        if not self.api_url:
            raise ValueError("No SMS API URL configured")

        payload = {"to": to_number, "from": self.from_number, "message": message}

        async with aiohttp.ClientSession() as session:
            async with session.post(self.api_url, json=payload) as response:
                if response.status != 200:
                    raise Exception(f"SMS API failed with status {response.status}")


class WebhookNotificationChannel(NotificationChannelBase):
    """Webhook notification channel"""

    def __init__(self, config: dict[str, Any]):
        super().__init__(NotificationChannel.WEBHOOK, config)
        self.timeout = config.get("timeout", 30)
        self.headers = config.get("headers", {})
        self.verify_ssl = config.get("verify_ssl", True)

    async def send_notification(
        self,
        target: NotificationTarget,
        alert: Alert,
        template: NotificationTemplate | None = None,
    ) -> NotificationRecord:
        """Send webhook notification"""

        record = NotificationRecord(
            record_id=f"webhook_{alert.alert_id}_{target.target_id}",
            alert_id=alert.alert_id,
            target_id=target.target_id,
            channel=NotificationChannel.WEBHOOK,
            status=NotificationStatus.PENDING,
            created_at=datetime.now(),
        )

        try:
            # Check rate limit
            if not self.check_rate_limit(target):
                record.status = NotificationStatus.RATE_LIMITED
                self.delivery_stats["rate_limited"] += 1
                return record

            # Create webhook payload
            payload = self._create_webhook_payload(alert, template)

            # Send webhook
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            connector = aiohttp.TCPConnector(verify_ssl=self.verify_ssl)

            async with aiohttp.ClientSession(
                timeout=timeout, connector=connector
            ) as session:
                async with session.post(
                    target.address, json=payload, headers=self.headers
                ) as response:
                    if response.status not in [200, 201, 202, 204]:
                        error_text = await response.text()
                        raise Exception(
                            f"Webhook failed: {response.status} - {error_text}"
                        )

            record.status = NotificationStatus.SENT
            record.sent_at = datetime.now()
            self.record_send_attempt(target)
            self.delivery_stats["sent"] += 1

            logger.info(
                f"Webhook notification sent to {target.address} for alert {alert.alert_id}"
            )

        except Exception as e:
            record.status = NotificationStatus.FAILED
            record.error_message = str(e)
            self.delivery_stats["failed"] += 1
            logger.error(f"Failed to send webhook notification: {e}")

        return record

    def _create_webhook_payload(
        self, alert: Alert, template: NotificationTemplate | None = None
    ) -> dict[str, Any]:
        """Create webhook payload"""
        if template and template.format_type == "json":
            # Use custom JSON template
            message_parts = self.format_message(alert, template)
            try:
                return json.loads(message_parts["body"])
            except json.JSONDecodeError:
                # Fall back to default if template is invalid
                pass

        # Default webhook payload
        return {
            "alert_id": alert.alert_id,
            "alert_name": alert.name,
            "description": alert.description,
            "severity": alert.severity.value,
            "category": alert.category.value,
            "status": alert.status.value,
            "created_at": alert.created_at.isoformat(),
            "updated_at": alert.updated_at.isoformat(),
            "triggered_by": alert.triggered_by,
            "current_value": alert.current_value,
            "threshold_value": alert.threshold_value,
            "affected_components": alert.affected_components,
            "context": alert.context,
            "tags": alert.tags,
        }


class NotificationManager:
    """
    Manages notification delivery across multiple channels

    Handles routing, rate limiting, retry logic, and delivery tracking
    for all notification channels.
    """

    def __init__(self):
        self.channels: dict[NotificationChannel, NotificationChannelBase] = {}
        self.templates: dict[str, NotificationTemplate] = {}
        self.notification_records: deque = deque(maxlen=10000)
        self.retry_queue: list[NotificationRecord] = []

        # Delivery tracking
        self.delivery_stats = {
            "total_sent": 0,
            "total_delivered": 0,
            "total_failed": 0,
            "channel_stats": defaultdict(lambda: {"sent": 0, "failed": 0}),
        }

        logger.info("Notification manager initialized")

    def add_channel(self, channel_type: NotificationChannel, config: dict[str, Any]):
        """Add notification channel"""
        if channel_type == NotificationChannel.EMAIL:
            channel = EmailNotificationChannel(config)
        elif channel_type == NotificationChannel.SLACK:
            channel = SlackNotificationChannel(config)
        elif channel_type == NotificationChannel.SMS:
            channel = SMSNotificationChannel(config)
        elif channel_type == NotificationChannel.WEBHOOK:
            channel = WebhookNotificationChannel(config)
        else:
            raise ValueError(f"Unsupported notification channel: {channel_type}")

        self.channels[channel_type] = channel
        logger.info(f"Added notification channel: {channel_type.value}")

    def add_template(self, template: NotificationTemplate):
        """Add notification template"""
        self.templates[template.template_id] = template
        logger.info(f"Added notification template: {template.name}")

    async def send_notification(
        self,
        target: NotificationTarget,
        alert: Alert,
        template_id: str | None = None,
    ) -> NotificationRecord | None:
        """Send notification to target"""

        # Check if channel is available
        if target.channel not in self.channels:
            logger.error(f"No channel configured for {target.channel.value}")
            return None

        # Check filters
        if not self._passes_filters(target, alert):
            logger.debug(
                f"Alert {alert.alert_id} filtered out for target {target.name}"
            )
            return None

        # Get template
        template = None
        if template_id and template_id in self.templates:
            template = self.templates[template_id]

        # Send notification
        channel = self.channels[target.channel]
        record = await channel.send_notification(target, alert, template)

        # Store record
        self.notification_records.append(record)

        # Update stats
        self._update_delivery_stats(record)

        # Handle retries if failed
        if record.status == NotificationStatus.FAILED and record.retry_count < 3:
            self.retry_queue.append(record)

        return record

    async def send_to_multiple_targets(
        self,
        targets: list[NotificationTarget],
        alert: Alert,
        template_id: str | None = None,
    ) -> list[NotificationRecord]:
        """Send notification to multiple targets"""
        tasks = []
        for target in targets:
            task = asyncio.create_task(
                self.send_notification(target, alert, template_id)
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        records = []
        for result in results:
            if isinstance(result, NotificationRecord):
                records.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Error sending notification: {result}")

        return records

    async def process_retry_queue(self):
        """Process failed notifications for retry"""
        retry_records = []

        for record in self.retry_queue:
            # Wait before retrying (exponential backoff)
            retry_delay = min(300, 30 * (2**record.retry_count))  # Max 5 minutes
            time_since_last = (datetime.now() - record.created_at).total_seconds()

            if time_since_last >= retry_delay:
                retry_records.append(record)

        for record in retry_records:
            if record.target_id and record.channel in self.channels:
                # Find target (this would need target lookup in real implementation)
                # For now, skip retry if we can't find target
                pass

            self.retry_queue.remove(record)

    def _passes_filters(self, target: NotificationTarget, alert: Alert) -> bool:
        """Check if alert passes target filters"""

        # Check if target is enabled
        if not target.enabled:
            return False

        # Check severity filter
        if target.severity_filter and alert.severity not in target.severity_filter:
            return False

        # Check category filter
        if target.category_filter and alert.category not in target.category_filter:
            return False

        # Check time restrictions (business hours, etc.)
        if target.time_restrictions:
            if not self._check_time_restrictions(target.time_restrictions):
                return False

        return True

    def _check_time_restrictions(self, restrictions: dict[str, Any]) -> bool:
        """Check time-based restrictions"""
        now = datetime.now()

        # Business hours check
        if restrictions.get("business_hours_only", False):
            if now.weekday() >= 5:  # Weekend
                return False
            if not (9 <= now.hour <= 17):  # Outside business hours
                return False

        # Custom hour restrictions
        if "allowed_hours" in restrictions:
            allowed_hours = restrictions["allowed_hours"]
            if now.hour not in allowed_hours:
                return False

        # Quiet hours
        if "quiet_hours" in restrictions:
            quiet_start, quiet_end = restrictions["quiet_hours"]
            if quiet_start <= now.hour <= quiet_end:
                return False

        return True

    def _update_delivery_stats(self, record: NotificationRecord):
        """Update delivery statistics"""
        channel_name = record.channel.value

        if record.status == NotificationStatus.SENT:
            self.delivery_stats["total_sent"] += 1
            self.delivery_stats["channel_stats"][channel_name]["sent"] += 1
        elif record.status == NotificationStatus.FAILED:
            self.delivery_stats["total_failed"] += 1
            self.delivery_stats["channel_stats"][channel_name]["failed"] += 1

    def get_delivery_stats(self) -> dict[str, Any]:
        """Get notification delivery statistics"""
        return {
            "total_notifications": len(self.notification_records),
            "pending_retries": len(self.retry_queue),
            **self.delivery_stats,
            "timestamp": datetime.now().isoformat(),
        }

    def get_recent_notifications(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent notification records"""
        recent = list(self.notification_records)[-limit:]

        return [
            {
                "record_id": record.record_id,
                "alert_id": record.alert_id,
                "target_id": record.target_id,
                "channel": record.channel.value,
                "status": record.status.value,
                "created_at": record.created_at.isoformat(),
                "sent_at": record.sent_at.isoformat() if record.sent_at else None,
                "error_message": record.error_message,
                "retry_count": record.retry_count,
            }
            for record in recent
        ]


# Global notification manager instance
_notification_manager = None


def get_notification_manager() -> NotificationManager:
    """Get global notification manager instance"""
    global _notification_manager

    if _notification_manager is None:
        _notification_manager = NotificationManager()

    return _notification_manager


def initialize_notification_system(config: dict[str, Any]) -> NotificationManager:
    """Initialize notification system with configuration"""
    global _notification_manager

    _notification_manager = NotificationManager()

    # Add configured channels
    for channel_name, channel_config in config.get("channels", {}).items():
        try:
            channel_type = NotificationChannel(channel_name)
            _notification_manager.add_channel(channel_type, channel_config)
        except ValueError:
            logger.warning(f"Unknown notification channel: {channel_name}")

    # Add templates
    for template_config in config.get("templates", []):
        template = NotificationTemplate(**template_config)
        _notification_manager.add_template(template)

    logger.info("Notification system initialized")
    return _notification_manager
