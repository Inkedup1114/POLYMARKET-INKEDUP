"""
Alert Escalation Policies and Routing

Comprehensive alert escalation system with time-based escalation,
intelligent routing, on-call scheduling, and automated escalation
based on severity and response times.
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from datetime import time as dt_time
from enum import Enum
from typing import Any

from .core import (
    Alert,
    AlertManager,
    AlertSeverity,
    AlertStatus,
    NotificationTarget,
    get_alert_manager,
)
from .notifications import NotificationManager, get_notification_manager

logger = logging.getLogger(__name__)


class EscalationTrigger(Enum):
    """What triggers escalation"""

    TIME_BASED = "time_based"  # Time since alert creation
    NO_ACKNOWLEDGMENT = "no_ack"  # No acknowledgment after time
    NO_RESOLUTION = "no_resolution"  # No resolution after time
    SEVERITY_BASED = "severity"  # Immediate based on severity
    MANUAL = "manual"  # Manual escalation
    REPEAT_OCCURRENCE = "repeat"  # Repeated same alert


class EscalationAction(Enum):
    """Types of escalation actions"""

    NOTIFY_ADDITIONAL = "notify_additional"  # Notify more people
    INCREASE_FREQUENCY = "increase_freq"  # Send more frequent notifications
    CHANGE_CHANNELS = "change_channels"  # Use different communication channels
    PAGE_ONCALL = "page_oncall"  # Page on-call person
    ESCALATE_MANAGEMENT = "escalate_mgmt"  # Escalate to management
    AUTO_RESOLVE = "auto_resolve"  # Attempt automatic resolution
    SUPPRESS_SIMILAR = "suppress_similar"  # Suppress similar alerts


@dataclass
class EscalationLevel:
    """Single level in escalation chain"""

    level: int
    name: str
    description: str
    trigger_delay_minutes: int
    actions: list[EscalationAction]
    notification_targets: list[str]  # Target IDs
    notification_channels: list[str] = field(default_factory=list)  # Override channels
    repeat_interval_minutes: int | None = None  # How often to repeat notifications
    max_repeats: int = 3
    conditions: dict[str, Any] = field(default_factory=dict)  # Additional conditions
    enabled: bool = True


@dataclass
class EscalationPolicy:
    """Complete escalation policy definition"""

    policy_id: str
    name: str
    description: str
    levels: list[EscalationLevel]
    enabled: bool = True
    applies_to_severities: list[AlertSeverity] = field(
        default_factory=list
    )  # Empty = all
    applies_to_categories: list[str] = field(default_factory=list)  # Empty = all
    business_hours_only: bool = False
    weekend_policy: str | None = None  # Different policy for weekends
    holiday_policy: str | None = None  # Different policy for holidays
    tags: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class OnCallSchedule:
    """On-call scheduling information"""

    schedule_id: str
    name: str
    timezone: str = "UTC"
    rotations: list[dict[str, Any]] = field(default_factory=list)
    # Each rotation: {"start_time": "09:00", "end_time": "17:00", "days": [0,1,2,3,4], "person": "user_id"}
    overrides: list[dict[str, Any]] = field(default_factory=list)
    # Each override: {"start_datetime": "2024-01-01T09:00:00", "end_datetime": "2024-01-01T17:00:00", "person": "user_id"}
    enabled: bool = True


@dataclass
class EscalationExecution:
    """Tracks execution of escalation for a specific alert"""

    execution_id: str
    alert_id: str
    policy_id: str
    current_level: int
    started_at: datetime
    last_escalation: datetime | None = None
    next_escalation: datetime | None = None
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    notifications_sent: list[str] = field(
        default_factory=list
    )  # Notification record IDs
    acknowledged: bool = False
    completed: bool = False
    completion_reason: str | None = None


class OnCallManager:
    """Manages on-call schedules and determines current on-call person"""

    def __init__(self):
        self.schedules: dict[str, OnCallSchedule] = {}
        self.schedule_cache: dict[str, tuple[datetime, str | None]] = {}
        self.cache_ttl_minutes = 5  # Cache on-call lookups for 5 minutes

    def add_schedule(self, schedule: OnCallSchedule):
        """Add on-call schedule"""
        self.schedules[schedule.schedule_id] = schedule
        logger.info(f"Added on-call schedule: {schedule.name}")

    def get_current_oncall(
        self, schedule_id: str, timestamp: datetime | None = None
    ) -> str | None:
        """Get current on-call person for schedule"""
        if timestamp is None:
            timestamp = datetime.now()

        # Check cache
        cache_key = f"{schedule_id}_{timestamp.strftime('%Y%m%d_%H%M')}"
        if cache_key in self.schedule_cache:
            cache_time, cached_person = self.schedule_cache[cache_key]
            if (timestamp - cache_time).total_seconds() < self.cache_ttl_minutes * 60:
                return cached_person

        schedule = self.schedules.get(schedule_id)
        if not schedule or not schedule.enabled:
            return None

        # Check overrides first
        oncall_person = self._check_overrides(schedule, timestamp)
        if oncall_person:
            self.schedule_cache[cache_key] = (timestamp, oncall_person)
            return oncall_person

        # Check regular rotations
        oncall_person = self._check_rotations(schedule, timestamp)
        self.schedule_cache[cache_key] = (timestamp, oncall_person)
        return oncall_person

    def _check_overrides(
        self, schedule: OnCallSchedule, timestamp: datetime
    ) -> str | None:
        """Check if there's an override for this time"""
        for override in schedule.overrides:
            start_time = datetime.fromisoformat(override["start_datetime"])
            end_time = datetime.fromisoformat(override["end_datetime"])

            if start_time <= timestamp <= end_time:
                return override["person"]

        return None

    def _check_rotations(
        self, schedule: OnCallSchedule, timestamp: datetime
    ) -> str | None:
        """Check regular rotations for current on-call"""
        current_weekday = timestamp.weekday()  # 0 = Monday
        current_time = timestamp.time()

        for rotation in schedule.rotations:
            # Check if current day is covered
            if current_weekday not in rotation.get("days", []):
                continue

            # Check if current time is covered
            start_time = dt_time.fromisoformat(rotation["start_time"])
            end_time = dt_time.fromisoformat(rotation["end_time"])

            if start_time <= current_time <= end_time:
                return rotation["person"]

        return None

    def get_oncall_targets(
        self, schedule_id: str, notification_targets: dict[str, NotificationTarget]
    ) -> list[NotificationTarget]:
        """Get notification targets for current on-call person"""
        oncall_person = self.get_current_oncall(schedule_id)
        if not oncall_person:
            return []

        # Find notification targets for this person
        person_targets = []
        for target in notification_targets.values():
            if target.tags.get("person_id") == oncall_person:
                person_targets.append(target)

        return person_targets


class EscalationRouter:
    """Routes alerts through escalation policies"""

    def __init__(
        self,
        alert_manager: AlertManager | None = None,
        notification_manager: NotificationManager | None = None,
    ):
        self.alert_manager = alert_manager or get_alert_manager()
        self.notification_manager = notification_manager or get_notification_manager()
        self.oncall_manager = OnCallManager()

        self.escalation_policies: dict[str, EscalationPolicy] = {}
        self.active_escalations: dict[str, EscalationExecution] = (
            {}
        )  # alert_id -> execution
        self.escalation_history: deque = deque(maxlen=1000)

        # Policy matching cache
        self.policy_cache: dict[str, list[str]] = {}  # alert signature -> policy IDs

        logger.info("Escalation router initialized")

    def add_escalation_policy(self, policy: EscalationPolicy):
        """Add escalation policy"""
        self.escalation_policies[policy.policy_id] = policy
        self._clear_policy_cache()
        logger.info(f"Added escalation policy: {policy.name}")

    def add_oncall_schedule(self, schedule: OnCallSchedule):
        """Add on-call schedule"""
        self.oncall_manager.add_schedule(schedule)

    async def process_alert_for_escalation(
        self, alert: Alert
    ) -> EscalationExecution | None:
        """Process new alert and start escalation if needed"""

        # Find matching escalation policies
        matching_policies = self._find_matching_policies(alert)
        if not matching_policies:
            return None

        # Use first matching policy (could implement priority in future)
        policy = matching_policies[0]

        # Create escalation execution
        execution = EscalationExecution(
            execution_id=f"esc_{alert.alert_id}_{int(datetime.now().timestamp())}",
            alert_id=alert.alert_id,
            policy_id=policy.policy_id,
            current_level=0,
            started_at=datetime.now(),
        )

        # Calculate first escalation time
        if policy.levels:
            first_level = policy.levels[0]
            execution.next_escalation = execution.started_at + timedelta(
                minutes=first_level.trigger_delay_minutes
            )

        self.active_escalations[alert.alert_id] = execution

        logger.info(
            f"Started escalation for alert {alert.alert_id} using policy {policy.name}"
        )

        # Check if immediate escalation is needed (e.g., EMERGENCY severity)
        if self._should_escalate_immediately(alert, policy):
            await self._execute_escalation_level(execution, 0)

        return execution

    async def process_escalation_queue(self):
        """Process pending escalations"""
        current_time = datetime.now()

        escalations_to_process = []
        for execution in self.active_escalations.values():
            if (
                not execution.completed
                and execution.next_escalation
                and current_time >= execution.next_escalation
            ):
                escalations_to_process.append(execution)

        for execution in escalations_to_process:
            await self._process_escalation_execution(execution, current_time)

    async def _process_escalation_execution(
        self, execution: EscalationExecution, current_time: datetime
    ):
        """Process single escalation execution"""
        policy = self.escalation_policies.get(execution.policy_id)
        if not policy or not policy.enabled:
            execution.completed = True
            execution.completion_reason = "Policy disabled or not found"
            return

        # Check if escalation should continue
        alert = self._get_alert(execution.alert_id)
        if not alert:
            execution.completed = True
            execution.completion_reason = "Alert not found"
            return

        # Check if alert is resolved or acknowledged
        if alert.status in [AlertStatus.RESOLVED, AlertStatus.CLOSED]:
            execution.completed = True
            execution.completion_reason = f"Alert {alert.status.value}"
            return

        if (
            alert.status == AlertStatus.ACKNOWLEDGED
            and not self._should_continue_after_ack(policy, execution)
        ):
            execution.completed = True
            execution.completion_reason = "Alert acknowledged"
            return

        # Execute current level
        if execution.current_level < len(policy.levels):
            await self._execute_escalation_level(execution, execution.current_level)
        else:
            execution.completed = True
            execution.completion_reason = "All escalation levels completed"

    async def _execute_escalation_level(
        self, execution: EscalationExecution, level_index: int
    ):
        """Execute specific escalation level"""
        policy = self.escalation_policies[execution.policy_id]
        level = policy.levels[level_index]

        if not level.enabled:
            # Skip to next level
            await self._schedule_next_level(execution, level_index + 1)
            return

        alert = self._get_alert(execution.alert_id)
        if not alert:
            return

        logger.info(
            f"Executing escalation level {level_index + 1} ({level.name}) for alert {alert.alert_id}"
        )

        # Execute actions
        for action in level.actions:
            await self._execute_escalation_action(execution, level, action, alert)

        # Send notifications
        await self._send_escalation_notifications(execution, level, alert)

        # Update execution state
        execution.current_level = level_index
        execution.last_escalation = datetime.now()

        # Record action
        action_record = {
            "level": level_index + 1,
            "level_name": level.name,
            "timestamp": datetime.now().isoformat(),
            "actions": [action.value for action in level.actions],
        }
        execution.actions_taken.append(action_record)

        # Schedule next level if needed
        await self._schedule_next_level(execution, level_index + 1)

    async def _execute_escalation_action(
        self,
        execution: EscalationExecution,
        level: EscalationLevel,
        action: EscalationAction,
        alert: Alert,
    ):
        """Execute specific escalation action"""

        if action == EscalationAction.PAGE_ONCALL:
            # Find on-call person and add to notification targets
            oncall_targets = self._get_oncall_notification_targets(level)
            # This would be implemented to add oncall targets to notifications

        elif action == EscalationAction.SUPPRESS_SIMILAR:
            # Suppress similar alerts
            await self._suppress_similar_alerts(alert)

        elif action == EscalationAction.AUTO_RESOLVE:
            # Attempt automatic resolution
            await self._attempt_auto_resolution(alert)

        elif action == EscalationAction.ESCALATE_MANAGEMENT:
            # Add management to notification targets
            mgmt_targets = self._get_management_targets()
            # This would be implemented to notify management

        # Other actions would be implemented here

        logger.debug(
            f"Executed escalation action {action.value} for alert {alert.alert_id}"
        )

    async def _send_escalation_notifications(
        self, execution: EscalationExecution, level: EscalationLevel, alert: Alert
    ):
        """Send notifications for escalation level"""

        # Get notification targets
        targets = []
        for target_id in level.notification_targets:
            # This would lookup actual notification targets
            # targets.append(notification_manager.get_target(target_id))
            pass

        # Add on-call targets if needed
        if EscalationAction.PAGE_ONCALL in level.actions:
            oncall_targets = self._get_oncall_notification_targets(level)
            targets.extend(oncall_targets)

        # Send notifications
        notification_records = []
        for target in targets:
            # Create escalation-specific template or use default
            template_id = f"escalation_level_{level.level}" if level.level > 1 else None

            record = await self.notification_manager.send_notification(
                target, alert, template_id
            )
            if record:
                notification_records.append(record.record_id)

        execution.notifications_sent.extend(notification_records)

    async def _schedule_next_level(
        self, execution: EscalationExecution, next_level_index: int
    ):
        """Schedule next escalation level"""
        policy = self.escalation_policies[execution.policy_id]

        if next_level_index >= len(policy.levels):
            # No more levels
            execution.completed = True
            execution.completion_reason = "All levels completed"
            return

        next_level = policy.levels[next_level_index]
        execution.next_escalation = datetime.now() + timedelta(
            minutes=next_level.trigger_delay_minutes
        )

        logger.debug(
            f"Scheduled next escalation level {next_level_index + 1} at {execution.next_escalation}"
        )

    def _find_matching_policies(self, alert: Alert) -> list[EscalationPolicy]:
        """Find escalation policies that match the alert"""

        # Create alert signature for caching
        alert_signature = f"{alert.severity.value}_{alert.category.value}_{','.join(sorted(alert.tags.keys()))}"

        if alert_signature in self.policy_cache:
            policy_ids = self.policy_cache[alert_signature]
            return [
                self.escalation_policies[pid]
                for pid in policy_ids
                if pid in self.escalation_policies
            ]

        matching_policies = []

        for policy in self.escalation_policies.values():
            if not policy.enabled:
                continue

            # Check severity filter
            if (
                policy.applies_to_severities
                and alert.severity not in policy.applies_to_severities
            ):
                continue

            # Check category filter
            if (
                policy.applies_to_categories
                and alert.category.value not in policy.applies_to_categories
            ):
                continue

            # Check business hours restriction
            if policy.business_hours_only and not self._is_business_hours():
                continue

            # Check tag matching
            if not self._tags_match(policy.tags, alert.tags):
                continue

            matching_policies.append(policy)

        # Cache result
        self.policy_cache[alert_signature] = [p.policy_id for p in matching_policies]

        return matching_policies

    def _should_escalate_immediately(
        self, alert: Alert, policy: EscalationPolicy
    ) -> bool:
        """Check if alert should escalate immediately"""

        # Emergency severity always escalates immediately
        if alert.severity == AlertSeverity.EMERGENCY:
            return True

        # Check if first level has zero delay
        if policy.levels and policy.levels[0].trigger_delay_minutes == 0:
            return True

        return False

    def _should_continue_after_ack(
        self, policy: EscalationPolicy, execution: EscalationExecution
    ) -> bool:
        """Check if escalation should continue after acknowledgment"""

        # Check current level configuration
        if execution.current_level < len(policy.levels):
            level = policy.levels[execution.current_level]
            return level.conditions.get("continue_after_ack", False)

        return False

    def _get_alert(self, alert_id: str) -> Alert | None:
        """Get alert by ID"""
        # This would get alert from alert manager
        active_alerts = self.alert_manager.get_active_alerts()
        for alert in active_alerts:
            if alert.alert_id == alert_id:
                return alert
        return None

    def _get_oncall_notification_targets(
        self, level: EscalationLevel
    ) -> list[NotificationTarget]:
        """Get notification targets for on-call person"""
        # This would be implemented to get actual on-call targets
        return []

    def _get_management_targets(self) -> list[NotificationTarget]:
        """Get management notification targets"""
        # This would be implemented to get management targets
        return []

    async def _suppress_similar_alerts(self, alert: Alert):
        """Suppress similar alerts"""
        # This would implement logic to suppress similar alerts
        logger.info(f"Suppressing similar alerts to {alert.alert_id}")

    async def _attempt_auto_resolution(self, alert: Alert):
        """Attempt automatic resolution of alert"""
        # This would implement auto-resolution logic
        logger.info(f"Attempting auto-resolution of alert {alert.alert_id}")

    def _is_business_hours(self) -> bool:
        """Check if current time is business hours"""
        now = datetime.now()
        # Simple business hours check (9 AM - 5 PM, Monday-Friday)
        return now.weekday() < 5 and 9 <= now.hour <= 17

    def _tags_match(
        self, policy_tags: dict[str, str], alert_tags: dict[str, str]
    ) -> bool:
        """Check if policy tags match alert tags"""
        for key, value in policy_tags.items():
            if alert_tags.get(key) != value:
                return False
        return True

    def _clear_policy_cache(self):
        """Clear policy matching cache"""
        self.policy_cache.clear()

    def acknowledge_escalation(self, alert_id: str, acknowledged_by: str):
        """Acknowledge escalation (may stop or modify escalation)"""
        if alert_id in self.active_escalations:
            execution = self.active_escalations[alert_id]
            execution.acknowledged = True

            # Check if escalation should stop
            policy = self.escalation_policies.get(execution.policy_id)
            if policy and not self._should_continue_after_ack(policy, execution):
                execution.completed = True
                execution.completion_reason = f"Acknowledged by {acknowledged_by}"

            logger.info(
                f"Escalation acknowledged for alert {alert_id} by {acknowledged_by}"
            )

    def stop_escalation(self, alert_id: str, reason: str = "Manual stop"):
        """Manually stop escalation"""
        if alert_id in self.active_escalations:
            execution = self.active_escalations[alert_id]
            execution.completed = True
            execution.completion_reason = reason

            logger.info(f"Escalation stopped for alert {alert_id}: {reason}")

    def get_active_escalations(self) -> list[dict[str, Any]]:
        """Get currently active escalations"""
        active = []

        for execution in self.active_escalations.values():
            if not execution.completed:
                active.append(
                    {
                        "execution_id": execution.execution_id,
                        "alert_id": execution.alert_id,
                        "policy_id": execution.policy_id,
                        "current_level": execution.current_level + 1,
                        "started_at": execution.started_at.isoformat(),
                        "last_escalation": (
                            execution.last_escalation.isoformat()
                            if execution.last_escalation
                            else None
                        ),
                        "next_escalation": (
                            execution.next_escalation.isoformat()
                            if execution.next_escalation
                            else None
                        ),
                        "actions_taken": len(execution.actions_taken),
                        "notifications_sent": len(execution.notifications_sent),
                        "acknowledged": execution.acknowledged,
                    }
                )

        return active

    def get_escalation_statistics(self) -> dict[str, Any]:
        """Get escalation statistics"""
        total_escalations = len(self.escalation_history) + len(self.active_escalations)
        active_escalations = len(
            [e for e in self.active_escalations.values() if not e.completed]
        )

        # Count escalations by policy
        policy_stats = defaultdict(int)
        for execution in self.active_escalations.values():
            policy_stats[execution.policy_id] += 1

        return {
            "total_escalations": total_escalations,
            "active_escalations": active_escalations,
            "completed_escalations": len(self.escalation_history),
            "escalation_policies": len(self.escalation_policies),
            "oncall_schedules": len(self.oncall_manager.schedules),
            "policy_usage": dict(policy_stats),
            "timestamp": datetime.now().isoformat(),
        }


class EscalationPolicyBuilder:
    """Helper class for building escalation policies"""

    @staticmethod
    def create_basic_escalation_policy(
        policy_id: str,
        name: str,
        primary_targets: list[str],
        manager_targets: list[str],
        oncall_schedule_id: str | None = None,
    ) -> EscalationPolicy:
        """Create basic 3-level escalation policy"""

        levels = [
            EscalationLevel(
                level=1,
                name="Initial Notification",
                description="Notify primary responders",
                trigger_delay_minutes=0,
                actions=[EscalationAction.NOTIFY_ADDITIONAL],
                notification_targets=primary_targets,
                repeat_interval_minutes=15,
                max_repeats=2,
            ),
            EscalationLevel(
                level=2,
                name="Escalate to On-Call",
                description="Page on-call person and increase notification frequency",
                trigger_delay_minutes=15,
                actions=[
                    EscalationAction.PAGE_ONCALL,
                    EscalationAction.INCREASE_FREQUENCY,
                ],
                notification_targets=primary_targets,
                repeat_interval_minutes=5,
                max_repeats=5,
            ),
            EscalationLevel(
                level=3,
                name="Management Escalation",
                description="Escalate to management and suppress similar alerts",
                trigger_delay_minutes=30,
                actions=[
                    EscalationAction.ESCALATE_MANAGEMENT,
                    EscalationAction.SUPPRESS_SIMILAR,
                ],
                notification_targets=manager_targets,
                repeat_interval_minutes=10,
                max_repeats=3,
            ),
        ]

        return EscalationPolicy(
            policy_id=policy_id,
            name=name,
            description=f"Standard escalation policy: {name}",
            levels=levels,
            applies_to_severities=[
                AlertSeverity.HIGH,
                AlertSeverity.CRITICAL,
                AlertSeverity.EMERGENCY,
            ],
            business_hours_only=False,
        )

    @staticmethod
    def create_emergency_escalation_policy(
        policy_id: str, name: str, all_targets: list[str]
    ) -> EscalationPolicy:
        """Create immediate escalation policy for emergencies"""

        levels = [
            EscalationLevel(
                level=1,
                name="Emergency Response",
                description="Immediate notification to all responders",
                trigger_delay_minutes=0,
                actions=[
                    EscalationAction.NOTIFY_ADDITIONAL,
                    EscalationAction.PAGE_ONCALL,
                    EscalationAction.CHANGE_CHANNELS,
                ],
                notification_targets=all_targets,
                repeat_interval_minutes=2,
                max_repeats=10,
            )
        ]

        return EscalationPolicy(
            policy_id=policy_id,
            name=name,
            description=f"Emergency escalation policy: {name}",
            levels=levels,
            applies_to_severities=[AlertSeverity.EMERGENCY],
            business_hours_only=False,
        )

    @staticmethod
    def create_business_hours_policy(
        policy_id: str,
        name: str,
        business_targets: list[str],
        after_hours_targets: list[str],
    ) -> EscalationPolicy:
        """Create policy with different behavior for business hours"""

        levels = [
            EscalationLevel(
                level=1,
                name="Business Hours Response",
                description="Standard business hours escalation",
                trigger_delay_minutes=5,
                actions=[EscalationAction.NOTIFY_ADDITIONAL],
                notification_targets=business_targets,
                conditions={"business_hours_only": True},
            ),
            EscalationLevel(
                level=2,
                name="Manager Escalation",
                description="Escalate to managers during business hours",
                trigger_delay_minutes=30,
                actions=[EscalationAction.ESCALATE_MANAGEMENT],
                notification_targets=business_targets,
                conditions={"business_hours_only": True},
            ),
        ]

        return EscalationPolicy(
            policy_id=policy_id,
            name=name,
            description=f"Business hours escalation policy: {name}",
            levels=levels,
            applies_to_severities=[AlertSeverity.MEDIUM, AlertSeverity.HIGH],
            business_hours_only=True,
        )


# Global escalation router instance
_escalation_router = None


def get_escalation_router() -> EscalationRouter:
    """Get global escalation router instance"""
    global _escalation_router

    if _escalation_router is None:
        _escalation_router = EscalationRouter()

    return _escalation_router


def initialize_escalation_system(
    policies_config: list[dict[str, Any]], schedules_config: list[dict[str, Any]]
) -> EscalationRouter:
    """Initialize escalation system with configuration"""
    global _escalation_router

    _escalation_router = EscalationRouter()

    # Add escalation policies
    for policy_config in policies_config:
        # Convert config to EscalationPolicy object
        levels = []
        for level_config in policy_config.get("levels", []):
            level = EscalationLevel(**level_config)
            levels.append(level)

        policy = EscalationPolicy(
            policy_id=policy_config["policy_id"],
            name=policy_config["name"],
            description=policy_config["description"],
            levels=levels,
            enabled=policy_config.get("enabled", True),
            applies_to_severities=[
                AlertSeverity(s) for s in policy_config.get("applies_to_severities", [])
            ],
            applies_to_categories=policy_config.get("applies_to_categories", []),
            business_hours_only=policy_config.get("business_hours_only", False),
        )

        _escalation_router.add_escalation_policy(policy)

    # Add on-call schedules
    for schedule_config in schedules_config:
        schedule = OnCallSchedule(**schedule_config)
        _escalation_router.add_oncall_schedule(schedule)

    logger.info("Escalation system initialized")
    return _escalation_router
