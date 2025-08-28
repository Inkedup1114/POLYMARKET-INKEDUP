"""
Core Alerting Infrastructure

Comprehensive alerting system with configurable thresholds, multiple notification
channels, escalation policies, and integration with risk management systems.
"""

import asyncio
import logging
import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertCategory(Enum):
    """Categories of alerts"""

    RISK_MANAGEMENT = "risk_management"
    SYSTEM_FAILURE = "system_failure"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    OPERATIONAL_ISSUE = "operational_issue"
    SECURITY = "security"
    DATA_QUALITY = "data_quality"
    COMPLIANCE = "compliance"
    NETWORK = "network"
    DATABASE = "database"
    TRADING = "trading"


class AlertStatus(Enum):
    """Alert status states"""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"
    CLOSED = "closed"


class NotificationChannel(Enum):
    """Available notification channels"""

    EMAIL = "email"
    SMS = "sms"
    SLACK = "slack"
    WEBHOOK = "webhook"
    PUSH_NOTIFICATION = "push"
    PHONE_CALL = "phone"
    PAGERDUTY = "pagerduty"
    DISCORD = "discord"


@dataclass
class AlertThreshold:
    """Configurable alert threshold"""

    name: str
    metric_name: str
    operator: str  # >, <, >=, <=, ==, !=
    warning_value: float | None = None
    critical_value: float | None = None
    emergency_value: float | None = None
    duration_seconds: int = 60  # How long condition must persist
    evaluation_interval: int = 30  # How often to check
    enabled: bool = True
    description: str = ""
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class AlertRule:
    """Alert rule definition"""

    rule_id: str
    name: str
    category: AlertCategory
    description: str
    condition: str  # Condition expression
    severity: AlertSeverity
    thresholds: list[AlertThreshold] = field(default_factory=list)
    enabled: bool = True
    tags: dict[str, str] = field(default_factory=dict)
    suppression_rules: list[str] = field(
        default_factory=list
    )  # Rule IDs to suppress when this fires
    dependencies: list[str] = field(default_factory=list)  # Dependencies on other rules
    cooldown_seconds: int = 300  # Minimum time between same alerts
    max_frequency: int = 10  # Maximum alerts per hour
    auto_resolve: bool = True  # Auto-resolve when condition clears
    escalation_policy_id: str | None = None


@dataclass
class Alert:
    """Individual alert instance"""

    alert_id: str
    rule_id: str
    name: str
    description: str
    category: AlertCategory
    severity: AlertSeverity
    status: AlertStatus
    created_at: datetime
    updated_at: datetime
    triggered_by: str  # What triggered the alert
    current_value: float | None = None
    threshold_value: float | None = None
    affected_components: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
    acknowledgments: list[dict[str, Any]] = field(default_factory=list)
    escalations: list[dict[str, Any]] = field(default_factory=list)
    notifications_sent: list[dict[str, Any]] = field(default_factory=list)
    resolved_at: datetime | None = None
    resolution_notes: str | None = None
    auto_resolved: bool = False
    parent_alert_id: str | None = None  # For grouped/correlated alerts
    child_alert_ids: list[str] = field(default_factory=list)


@dataclass
class NotificationTarget:
    """Notification target configuration"""

    target_id: str
    name: str
    channel: NotificationChannel
    address: str  # Email, phone, webhook URL, etc.
    enabled: bool = True
    severity_filter: list[AlertSeverity] = field(
        default_factory=list
    )  # Empty means all
    category_filter: list[AlertCategory] = field(
        default_factory=list
    )  # Empty means all
    time_restrictions: dict[str, Any] = field(
        default_factory=dict
    )  # Business hours, etc.
    rate_limit: int = 10  # Max notifications per hour
    escalation_delay: int = 0  # Delay before using this target (for escalation)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class EscalationPolicy:
    """Alert escalation policy"""

    policy_id: str
    name: str
    description: str
    enabled: bool = True
    escalation_levels: list[dict[str, Any]] = field(default_factory=list)
    # Each level: {"delay_minutes": int, "targets": List[str], "repeat_count": int}
    auto_escalate: bool = True
    escalation_timeout: int = 30  # Minutes before escalating
    max_escalation_level: int = 3
    business_hours_only: bool = False
    weekend_policy: str | None = None  # Different policy for weekends


class AlertConditionEvaluator:
    """Evaluates alert conditions against metrics"""

    def __init__(self):
        self.operators = {
            ">": lambda x, y: x > y,
            "<": lambda x, y: x < y,
            ">=": lambda x, y: x >= y,
            "<=": lambda x, y: x <= y,
            "==": lambda x, y: x == y,
            "!=": lambda x, y: x != y,
            "contains": lambda x, y: y in str(x),
            "not_contains": lambda x, y: y not in str(x),
            "regex": lambda x, y: bool(__import__("re").match(y, str(x))),
            "between": lambda x, y: (
                y[0] <= x <= y[1]
                if isinstance(y, (list, tuple)) and len(y) == 2
                else False
            ),
        }

    def evaluate_threshold(
        self, threshold: AlertThreshold, current_value: Any
    ) -> AlertSeverity | None:
        """Evaluate a threshold against current value"""
        if not threshold.enabled or current_value is None:
            return None

        operator_func = self.operators.get(threshold.operator)
        if not operator_func:
            logger.error(f"Unknown operator: {threshold.operator}")
            return None

        try:
            # Check emergency threshold first
            if threshold.emergency_value is not None and operator_func(
                current_value, threshold.emergency_value
            ):
                return AlertSeverity.EMERGENCY

            # Check critical threshold
            if threshold.critical_value is not None and operator_func(
                current_value, threshold.critical_value
            ):
                return AlertSeverity.CRITICAL

            # Check warning threshold
            if threshold.warning_value is not None and operator_func(
                current_value, threshold.warning_value
            ):
                return AlertSeverity.HIGH  # Warning maps to HIGH

            return None

        except Exception as e:
            logger.error(f"Error evaluating threshold {threshold.name}: {e}")
            return None

    def evaluate_condition(self, condition: str, context: dict[str, Any]) -> bool:
        """Evaluate complex condition expression"""
        try:
            # Simple expression evaluator - in production, use a proper expression parser
            # This is a simplified version for demonstration

            # Replace variables in context
            for key, value in context.items():
                condition = condition.replace(f"{{{key}}}", str(value))

            # Evaluate basic mathematical expressions
            # WARNING: In production, use a safe expression evaluator
            return eval(condition)

        except Exception as e:
            logger.error(f"Error evaluating condition '{condition}': {e}")
            return False


class AlertCorrelationEngine:
    """Correlates related alerts to reduce noise"""

    def __init__(self, correlation_window: int = 300):
        self.correlation_window = correlation_window  # seconds
        self.correlation_rules = []
        self.recent_alerts = deque(maxlen=1000)

    def add_correlation_rule(self, rule: dict[str, Any]):
        """Add alert correlation rule"""
        self.correlation_rules.append(rule)

    def correlate_alert(self, alert: Alert) -> str | None:
        """Check if alert should be correlated with existing alerts"""
        current_time = alert.created_at
        cutoff_time = current_time - timedelta(seconds=self.correlation_window)

        # Get recent alerts within correlation window
        recent_alerts = [
            a
            for a in self.recent_alerts
            if a.created_at >= cutoff_time and a.status == AlertStatus.ACTIVE
        ]

        # Apply correlation rules
        for rule in self.correlation_rules:
            parent_alert = self._apply_correlation_rule(alert, recent_alerts, rule)
            if parent_alert:
                return parent_alert.alert_id

        # Add alert to recent alerts for future correlation
        self.recent_alerts.append(alert)
        return None

    def _apply_correlation_rule(
        self, alert: Alert, recent_alerts: list[Alert], rule: dict[str, Any]
    ) -> Alert | None:
        """Apply specific correlation rule"""
        rule_type = rule.get("type")

        if rule_type == "same_component":
            # Correlate alerts affecting the same component
            for recent_alert in recent_alerts:
                if (
                    set(alert.affected_components)
                    & set(recent_alert.affected_components)
                    and alert.category == recent_alert.category
                ):
                    return recent_alert

        elif rule_type == "cascading":
            # Correlate alerts that might be cascading effects
            cascading_categories = rule.get("categories", [])
            if alert.category.value in cascading_categories:
                for recent_alert in recent_alerts:
                    if (
                        recent_alert.category.value in cascading_categories
                        and recent_alert.severity.value in ["critical", "emergency"]
                    ):
                        return recent_alert

        elif rule_type == "pattern":
            # Correlate alerts matching specific patterns
            pattern = rule.get("pattern", {})
            for recent_alert in recent_alerts:
                if self._matches_pattern(alert, recent_alert, pattern):
                    return recent_alert

        return None

    def _matches_pattern(
        self, alert: Alert, recent_alert: Alert, pattern: dict[str, Any]
    ) -> bool:
        """Check if alerts match correlation pattern"""
        # Check tag patterns
        tag_patterns = pattern.get("tags", {})
        for key, value in tag_patterns.items():
            if (
                alert.tags.get(key) != recent_alert.tags.get(key)
                or alert.tags.get(key) != value
            ):
                return False

        # Check severity patterns
        severity_pattern = pattern.get("severity")
        if severity_pattern and alert.severity != recent_alert.severity:
            return False

        # Check description patterns
        description_pattern = pattern.get("description_contains")
        if (
            description_pattern
            and description_pattern not in alert.description.lower()
            or description_pattern not in recent_alert.description.lower()
        ):
            return False

        return True


class AlertManager:
    """
    Core alert management system

    Manages alert lifecycle, rules, thresholds, and coordination with
    notification and escalation systems.
    """

    def __init__(self, max_alerts: int = 10000):
        self.max_alerts = max_alerts
        self.lock = threading.RLock()

        # Alert storage
        self.active_alerts: dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=max_alerts)
        self.alert_rules: dict[str, AlertRule] = {}
        self.thresholds: dict[str, AlertThreshold] = {}

        # Escalation and notification
        self.notification_targets: dict[str, NotificationTarget] = {}
        self.escalation_policies: dict[str, EscalationPolicy] = {}

        # Alert processing
        self.condition_evaluator = AlertConditionEvaluator()
        self.correlation_engine = AlertCorrelationEngine()

        # Alert suppression and rate limiting
        self.suppressed_rules: set[str] = set()
        self.rule_cooldowns: dict[str, datetime] = {}
        self.rule_frequencies: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        # Background processing
        self.background_tasks: list[asyncio.Task] = []
        self.running = False

        # Metrics and statistics
        self.alert_stats = {
            "total_alerts": 0,
            "alerts_by_severity": defaultdict(int),
            "alerts_by_category": defaultdict(int),
            "resolved_alerts": 0,
            "escalated_alerts": 0,
            "suppressed_alerts": 0,
        }

        logger.info("Alert manager initialized")

    async def start(self):
        """Start alert manager background tasks"""
        if self.running:
            return

        self.running = True

        # Start background tasks
        self.background_tasks = [
            asyncio.create_task(self._alert_evaluation_loop()),
            asyncio.create_task(self._escalation_loop()),
            asyncio.create_task(self._cleanup_loop()),
            asyncio.create_task(self._statistics_loop()),
        ]

        logger.info("Alert manager started")

    async def stop(self):
        """Stop alert manager"""
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
        logger.info("Alert manager stopped")

    async def _alert_evaluation_loop(self):
        """Background loop for evaluating alert conditions"""
        while self.running:
            try:
                await self._evaluate_all_rules()
                await asyncio.sleep(30)  # Evaluate every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in alert evaluation loop: {e}")
                await asyncio.sleep(10)

    async def _escalation_loop(self):
        """Background loop for handling alert escalations"""
        while self.running:
            try:
                await self._process_escalations()
                await asyncio.sleep(60)  # Check escalations every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in escalation loop: {e}")
                await asyncio.sleep(30)

    async def _cleanup_loop(self):
        """Background loop for cleaning up old alerts"""
        while self.running:
            try:
                await self._cleanup_old_alerts()
                await asyncio.sleep(3600)  # Cleanup every hour
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(600)

    async def _statistics_loop(self):
        """Background loop for updating alert statistics"""
        while self.running:
            try:
                self._update_alert_statistics()
                await asyncio.sleep(300)  # Update stats every 5 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in statistics loop: {e}")
                await asyncio.sleep(60)

    def add_alert_rule(self, rule: AlertRule):
        """Add new alert rule"""
        with self.lock:
            self.alert_rules[rule.rule_id] = rule
            logger.info(f"Added alert rule: {rule.name} ({rule.rule_id})")

    def add_threshold(self, threshold: AlertThreshold):
        """Add alert threshold"""
        with self.lock:
            self.thresholds[threshold.name] = threshold
            logger.info(f"Added alert threshold: {threshold.name}")

    def add_notification_target(self, target: NotificationTarget):
        """Add notification target"""
        with self.lock:
            self.notification_targets[target.target_id] = target
            logger.info(
                f"Added notification target: {target.name} ({target.channel.value})"
            )

    def add_escalation_policy(self, policy: EscalationPolicy):
        """Add escalation policy"""
        with self.lock:
            self.escalation_policies[policy.policy_id] = policy
            logger.info(f"Added escalation policy: {policy.name}")

    def create_alert(
        self,
        rule_id: str,
        triggered_by: str,
        current_value: float | None = None,
        threshold_value: float | None = None,
        affected_components: list[str] = None,
        context: dict[str, Any] = None,
    ) -> Alert | None:
        """Create new alert"""

        with self.lock:
            if rule_id not in self.alert_rules:
                logger.error(f"Unknown alert rule: {rule_id}")
                return None

            rule = self.alert_rules[rule_id]

            if not rule.enabled:
                return None

            # Check cooldown
            if self._is_rule_in_cooldown(rule_id):
                return None

            # Check frequency limits
            if self._is_rule_frequency_exceeded(rule_id):
                logger.warning(f"Rule {rule_id} frequency limit exceeded")
                return None

            # Check suppression
            if rule_id in self.suppressed_rules:
                self.alert_stats["suppressed_alerts"] += 1
                return None

            # Create alert
            alert = Alert(
                alert_id=str(uuid.uuid4()),
                rule_id=rule_id,
                name=rule.name,
                description=rule.description,
                category=rule.category,
                severity=rule.severity,
                status=AlertStatus.ACTIVE,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                triggered_by=triggered_by,
                current_value=current_value,
                threshold_value=threshold_value,
                affected_components=affected_components or [],
                context=context or {},
                tags=rule.tags.copy(),
            )

            # Check for correlation
            parent_alert_id = self.correlation_engine.correlate_alert(alert)
            if parent_alert_id:
                alert.parent_alert_id = parent_alert_id
                if parent_alert_id in self.active_alerts:
                    self.active_alerts[parent_alert_id].child_alert_ids.append(
                        alert.alert_id
                    )

            # Store alert
            self.active_alerts[alert.alert_id] = alert
            self.alert_history.append(alert)

            # Update cooldown and frequency tracking
            self.rule_cooldowns[rule_id] = datetime.now()
            self.rule_frequencies[rule_id].append(datetime.now())

            # Update statistics
            self.alert_stats["total_alerts"] += 1
            self.alert_stats["alerts_by_severity"][rule.severity.value] += 1
            self.alert_stats["alerts_by_category"][rule.category.value] += 1

            # Apply suppression rules
            for suppress_rule_id in rule.suppression_rules:
                self.suppressed_rules.add(suppress_rule_id)

            logger.warning(
                f"Alert created: {alert.name} ({alert.severity.value}) - {alert.alert_id}"
            )

            return alert

    def acknowledge_alert(
        self, alert_id: str, acknowledged_by: str, notes: str = ""
    ) -> bool:
        """Acknowledge an alert"""

        with self.lock:
            if alert_id not in self.active_alerts:
                return False

            alert = self.active_alerts[alert_id]
            if alert.status != AlertStatus.ACTIVE:
                return False

            alert.status = AlertStatus.ACKNOWLEDGED
            alert.updated_at = datetime.now()

            acknowledgment = {
                "acknowledged_by": acknowledged_by,
                "acknowledged_at": datetime.now().isoformat(),
                "notes": notes,
            }
            alert.acknowledgments.append(acknowledgment)

            logger.info(f"Alert acknowledged: {alert.name} by {acknowledged_by}")

            return True

    def resolve_alert(
        self,
        alert_id: str,
        resolved_by: str = "system",
        notes: str = "",
        auto_resolved: bool = False,
    ) -> bool:
        """Resolve an alert"""

        with self.lock:
            if alert_id not in self.active_alerts:
                return False

            alert = self.active_alerts[alert_id]

            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now()
            alert.updated_at = datetime.now()
            alert.resolution_notes = notes
            alert.auto_resolved = auto_resolved

            # Remove from active alerts
            del self.active_alerts[alert_id]

            # Update statistics
            self.alert_stats["resolved_alerts"] += 1

            # Clear suppression rules if this alert was suppressing others
            rule = self.alert_rules.get(alert.rule_id)
            if rule:
                for suppress_rule_id in rule.suppression_rules:
                    self.suppressed_rules.discard(suppress_rule_id)

            logger.info(f"Alert resolved: {alert.name} by {resolved_by}")

            return True

    def escalate_alert(self, alert_id: str) -> bool:
        """Escalate an alert"""

        with self.lock:
            if alert_id not in self.active_alerts:
                return False

            alert = self.active_alerts[alert_id]
            rule = self.alert_rules.get(alert.rule_id)

            if not rule or not rule.escalation_policy_id:
                return False

            policy = self.escalation_policies.get(rule.escalation_policy_id)
            if not policy:
                return False

            alert.status = AlertStatus.ESCALATED
            alert.updated_at = datetime.now()

            escalation = {
                "escalated_at": datetime.now().isoformat(),
                "escalation_level": len(alert.escalations) + 1,
                "policy_id": policy.policy_id,
            }
            alert.escalations.append(escalation)

            self.alert_stats["escalated_alerts"] += 1

            logger.warning(
                f"Alert escalated: {alert.name} (level {escalation['escalation_level']})"
            )

            return True

    def _is_rule_in_cooldown(self, rule_id: str) -> bool:
        """Check if rule is in cooldown period"""
        if rule_id not in self.rule_cooldowns:
            return False

        rule = self.alert_rules.get(rule_id)
        if not rule:
            return False

        cooldown_end = self.rule_cooldowns[rule_id] + timedelta(
            seconds=rule.cooldown_seconds
        )
        return datetime.now() < cooldown_end

    def _is_rule_frequency_exceeded(self, rule_id: str) -> bool:
        """Check if rule frequency limit is exceeded"""
        rule = self.alert_rules.get(rule_id)
        if not rule:
            return False

        # Count alerts in last hour
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_alerts = [
            alert_time
            for alert_time in self.rule_frequencies[rule_id]
            if alert_time >= one_hour_ago
        ]

        return len(recent_alerts) >= rule.max_frequency

    async def _evaluate_all_rules(self):
        """Evaluate all alert rules"""
        # This would be implemented to check metrics against thresholds
        # and create alerts when conditions are met
        pass

    async def _process_escalations(self):
        """Process pending escalations"""
        current_time = datetime.now()

        with self.lock:
            for alert_id, alert in list(self.active_alerts.items()):
                if alert.status in [AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]:
                    rule = self.alert_rules.get(alert.rule_id)
                    if not rule or not rule.escalation_policy_id:
                        continue

                    policy = self.escalation_policies.get(rule.escalation_policy_id)
                    if not policy or not policy.enabled:
                        continue

                    # Check if escalation is needed
                    time_since_creation = (
                        current_time - alert.created_at
                    ).total_seconds() / 60
                    time_since_last_escalation = 0

                    if alert.escalations:
                        last_escalation_time = datetime.fromisoformat(
                            alert.escalations[-1]["escalated_at"]
                        )
                        time_since_last_escalation = (
                            current_time - last_escalation_time
                        ).total_seconds() / 60

                    should_escalate = False

                    if (
                        not alert.escalations
                        and time_since_creation >= policy.escalation_timeout
                    ):
                        should_escalate = True
                    elif (
                        alert.escalations
                        and len(alert.escalations) < policy.max_escalation_level
                        and time_since_last_escalation >= policy.escalation_timeout
                    ):
                        should_escalate = True

                    if should_escalate:
                        self.escalate_alert(alert_id)

    async def _cleanup_old_alerts(self):
        """Clean up old resolved alerts"""
        cutoff_time = datetime.now() - timedelta(hours=24)  # Keep 24 hours of history

        with self.lock:
            # Clean alert history
            while (
                self.alert_history
                and len(self.alert_history) > 0
                and self.alert_history[0].created_at < cutoff_time
                and self.alert_history[0].status == AlertStatus.RESOLVED
            ):
                self.alert_history.popleft()

            # Clean frequency tracking
            for rule_id, frequencies in self.rule_frequencies.items():
                while frequencies and frequencies[0] < cutoff_time:
                    frequencies.popleft()

    def _update_alert_statistics(self):
        """Update alert statistics"""
        with self.lock:
            # Reset counters that should be recalculated
            self.alert_stats["alerts_by_severity"].clear()
            self.alert_stats["alerts_by_category"].clear()

            # Count active alerts by severity and category
            for alert in self.active_alerts.values():
                self.alert_stats["alerts_by_severity"][alert.severity.value] += 1
                self.alert_stats["alerts_by_category"][alert.category.value] += 1

    def get_active_alerts(
        self,
        severity: AlertSeverity | None = None,
        category: AlertCategory | None = None,
    ) -> list[Alert]:
        """Get active alerts with optional filtering"""

        with self.lock:
            alerts = list(self.active_alerts.values())

            if severity:
                alerts = [a for a in alerts if a.severity == severity]

            if category:
                alerts = [a for a in alerts if a.category == category]

            return sorted(alerts, key=lambda x: x.created_at, reverse=True)

    def get_alert_statistics(self) -> dict[str, Any]:
        """Get alert statistics"""

        with self.lock:
            return {
                "active_alerts": len(self.active_alerts),
                "total_alerts": self.alert_stats["total_alerts"],
                "resolved_alerts": self.alert_stats["resolved_alerts"],
                "escalated_alerts": self.alert_stats["escalated_alerts"],
                "suppressed_alerts": self.alert_stats["suppressed_alerts"],
                "alerts_by_severity": dict(self.alert_stats["alerts_by_severity"]),
                "alerts_by_category": dict(self.alert_stats["alerts_by_category"]),
                "suppressed_rules": len(self.suppressed_rules),
                "total_rules": len(self.alert_rules),
                "notification_targets": len(self.notification_targets),
                "escalation_policies": len(self.escalation_policies),
                "timestamp": datetime.now().isoformat(),
            }

    def export_configuration(self) -> dict[str, Any]:
        """Export alert configuration"""

        with self.lock:
            return {
                "rules": {
                    rule_id: {
                        "name": rule.name,
                        "category": rule.category.value,
                        "severity": rule.severity.value,
                        "enabled": rule.enabled,
                        "description": rule.description,
                        "condition": rule.condition,
                        "tags": rule.tags,
                        "cooldown_seconds": rule.cooldown_seconds,
                        "max_frequency": rule.max_frequency,
                        "escalation_policy_id": rule.escalation_policy_id,
                    }
                    for rule_id, rule in self.alert_rules.items()
                },
                "thresholds": {
                    name: {
                        "metric_name": threshold.metric_name,
                        "operator": threshold.operator,
                        "warning_value": threshold.warning_value,
                        "critical_value": threshold.critical_value,
                        "emergency_value": threshold.emergency_value,
                        "duration_seconds": threshold.duration_seconds,
                        "enabled": threshold.enabled,
                        "description": threshold.description,
                    }
                    for name, threshold in self.thresholds.items()
                },
                "notification_targets": {
                    target_id: {
                        "name": target.name,
                        "channel": target.channel.value,
                        "address": target.address,
                        "enabled": target.enabled,
                        "severity_filter": [s.value for s in target.severity_filter],
                        "category_filter": [c.value for c in target.category_filter],
                        "rate_limit": target.rate_limit,
                        "escalation_delay": target.escalation_delay,
                    }
                    for target_id, target in self.notification_targets.items()
                },
                "escalation_policies": {
                    policy_id: {
                        "name": policy.name,
                        "description": policy.description,
                        "enabled": policy.enabled,
                        "escalation_levels": policy.escalation_levels,
                        "escalation_timeout": policy.escalation_timeout,
                        "max_escalation_level": policy.max_escalation_level,
                        "business_hours_only": policy.business_hours_only,
                    }
                    for policy_id, policy in self.escalation_policies.items()
                },
            }


# Global alert manager instance
_alert_manager = None


def get_alert_manager() -> AlertManager:
    """Get global alert manager instance"""
    global _alert_manager

    if _alert_manager is None:
        _alert_manager = AlertManager()

    return _alert_manager


def initialize_alerting_system() -> AlertManager:
    """Initialize global alerting system"""
    global _alert_manager

    if _alert_manager is not None:
        # Stop existing manager
        import asyncio

        if asyncio.get_event_loop().is_running():
            asyncio.create_task(_alert_manager.stop())

    _alert_manager = AlertManager()
    logger.info("Global alerting system initialized")

    return _alert_manager
