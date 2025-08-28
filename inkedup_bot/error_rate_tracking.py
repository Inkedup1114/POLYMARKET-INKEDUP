"""
Comprehensive Error Rate Tracking

Advanced error rate monitoring and analysis system for tracking failures,
exceptions, and error patterns across all bot components with predictive
alerting and root cause analysis.
"""

import hashlib
import logging
import re
import threading
import time
import traceback
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any

from .performance_metrics import ComponentType, MetricType, PerformanceMetricsTracker
from .throughput_metrics import ThroughputTracker

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Categories of errors for classification"""

    NETWORK = "network"
    DATABASE = "database"
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    PARSING = "parsing"
    CALCULATION = "calculation"
    SYSTEM = "system"
    EXTERNAL_API = "external_api"
    UNKNOWN = "unknown"


@dataclass
class ErrorEvent:
    """Individual error event record"""

    error_id: str
    component: ComponentType
    operation: str
    error_type: str
    error_message: str
    error_category: ErrorCategory
    severity: ErrorSeverity
    timestamp: datetime
    stack_trace: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    recovery_attempted: bool = False
    recovery_successful: bool = False
    user_impact: str = "unknown"  # "none", "low", "medium", "high"


@dataclass
class ErrorPattern:
    """Identified error pattern for analysis"""

    pattern_id: str
    pattern_hash: str
    description: str
    error_type: str
    component: ComponentType
    occurrences: int
    first_seen: datetime
    last_seen: datetime
    frequency_per_hour: float
    similar_errors: list[str] = field(default_factory=list)
    potential_causes: list[str] = field(default_factory=list)
    suggested_fixes: list[str] = field(default_factory=list)


@dataclass
class ComponentErrorStats:
    """Error statistics for a specific component"""

    component: ComponentType
    total_errors: int
    error_rate_per_minute: float
    error_rate_per_hour: float
    success_rate: float
    most_common_errors: list[tuple[str, int]]
    error_trend: str  # "increasing", "decreasing", "stable"
    time_range_minutes: int
    last_error_time: datetime | None = None
    error_burst_detected: bool = False
    health_status: str = "healthy"  # "healthy", "degraded", "failing"


@dataclass
class ErrorAlert:
    """Error rate alert"""

    alert_id: str
    component: ComponentType
    alert_type: str  # "rate_threshold", "error_burst", "pattern_detected"
    severity: ErrorSeverity
    message: str
    error_rate: float
    threshold: float
    timestamp: datetime
    acknowledged: bool = False
    resolved: bool = False
    auto_resolved: bool = False


class ErrorRateTracker:
    """
    Comprehensive error rate tracking and analysis system

    Monitors error rates, identifies patterns, provides predictive alerting,
    and offers root cause analysis across all system components.
    """

    def __init__(self, retention_hours: int = 72):
        self.retention_hours = retention_hours
        self.retention_seconds = retention_hours * 3600
        self.lock = threading.RLock()

        # Error storage
        self.errors: deque = deque(maxlen=50000)  # Last 50k errors
        self.errors_by_component: dict[ComponentType, deque] = defaultdict(
            lambda: deque(maxlen=10000)
        )

        # Error patterns and analysis
        self.error_patterns: dict[str, ErrorPattern] = {}
        self.error_fingerprints: dict[str, list[str]] = defaultdict(
            list
        )  # Hash -> error_ids

        # Component statistics
        self.component_stats: dict[ComponentType, ComponentErrorStats] = {}

        # Success/failure counters for rate calculation
        self.operation_counters: dict[tuple[ComponentType, str], dict[str, int]] = (
            defaultdict(lambda: {"success": 0, "failure": 0, "last_reset": time.time()})
        )

        # Alert management
        self.active_alerts: dict[str, ErrorAlert] = {}
        self.alert_history: deque = deque(maxlen=1000)

        # Error rate thresholds (errors per minute)
        self.rate_thresholds = {
            ComponentType.ORDER_CLIENT: {"warning": 5.0, "critical": 15.0},
            ComponentType.DATABASE: {"warning": 10.0, "critical": 30.0},
            ComponentType.WEBSOCKET: {"warning": 20.0, "critical": 50.0},
            ComponentType.SIGNAL_PROCESSOR: {"warning": 10.0, "critical": 25.0},
            ComponentType.MARKET_DATA: {"warning": 15.0, "critical": 40.0},
            ComponentType.SYSTEM: {"warning": 5.0, "critical": 20.0},
        }

        # Error burst detection
        self.burst_detection_window = 60  # seconds
        self.burst_threshold_multiplier = 3.0  # 3x normal rate

        # Performance integration
        self.performance_tracker = PerformanceMetricsTracker(self.retention_seconds)
        self.throughput_tracker: ThroughputTracker | None = None

        # Background analysis thread
        self.analysis_thread = None
        self.running = False

        logger.info("Error rate tracker initialized")

    def start_background_analysis(self):
        """Start background thread for error analysis"""
        if self.running:
            return

        self.running = True
        self.analysis_thread = threading.Thread(target=self._analysis_loop, daemon=True)
        self.analysis_thread.start()
        logger.info("Error rate analysis thread started")

    def stop_background_analysis(self):
        """Stop background analysis"""
        self.running = False
        if self.analysis_thread:
            self.analysis_thread.join(timeout=2.0)
        logger.info("Error rate analysis stopped")

    def set_throughput_tracker(self, throughput_tracker: ThroughputTracker):
        """Set throughput tracker for correlation analysis"""
        self.throughput_tracker = throughput_tracker

    def _analysis_loop(self):
        """Background loop for error analysis"""
        while self.running:
            try:
                self._update_component_stats()
                self._detect_error_patterns()
                self._check_error_rate_alerts()
                self._detect_error_bursts()
                self._cleanup_old_errors()
                time.sleep(10.0)  # Analysis every 10 seconds
            except Exception as e:
                logger.error(f"Error in error analysis loop: {e}")
                time.sleep(5.0)

    def record_error(
        self,
        component: ComponentType,
        operation: str,
        error: Exception,
        context: dict[str, Any] | None = None,
        recovery_attempted: bool = False,
        recovery_successful: bool = False,
        user_impact: str = "unknown",
    ):
        """Record an error event"""

        error_type = type(error).__name__
        error_message = str(error)
        stack_trace = traceback.format_exc()

        # Generate error ID
        error_content = f"{component.value}_{operation}_{error_type}_{error_message}"
        error_id = hashlib.md5(error_content.encode()).hexdigest()[:12]

        # Classify error
        error_category = self._classify_error(error_type, error_message, operation)
        severity = self._assess_error_severity(error, component, operation, user_impact)

        error_event = ErrorEvent(
            error_id=error_id,
            component=component,
            operation=operation,
            error_type=error_type,
            error_message=error_message,
            error_category=error_category,
            severity=severity,
            timestamp=datetime.now(),
            stack_trace=stack_trace,
            context=context or {},
            recovery_attempted=recovery_attempted,
            recovery_successful=recovery_successful,
            user_impact=user_impact,
        )

        with self.lock:
            self.errors.append(error_event)
            self.errors_by_component[component].append(error_event)

            # Update operation counters
            counter_key = (component, operation)
            self.operation_counters[counter_key]["failure"] += 1

            # Record in performance tracker
            self.performance_tracker.record_metric(
                component, MetricType.COUNTER, f"error_{error_category.value}", 1
            )

            # Add to error fingerprints for pattern detection
            error_fingerprint = self._generate_error_fingerprint(error_event)
            self.error_fingerprints[error_fingerprint].append(error_id)

        logger.error(
            f"Error recorded [{severity.value}]: {component.value}.{operation} - "
            f"{error_type}: {error_message[:100]}"
        )

    def record_success(self, component: ComponentType, operation: str):
        """Record a successful operation (for rate calculation)"""

        with self.lock:
            counter_key = (component, operation)
            self.operation_counters[counter_key]["success"] += 1

    def _classify_error(
        self, error_type: str, error_message: str, operation: str
    ) -> ErrorCategory:
        """Classify error into categories based on type and message"""

        error_type_lower = error_type.lower()
        message_lower = error_message.lower()
        operation_lower = operation.lower()

        # Network errors
        network_patterns = [
            "connection",
            "timeout",
            "network",
            "socket",
            "dns",
            "ssl",
            "tls",
            "request",
            "response",
            "http",
            "url",
            "proxy",
        ]
        if any(
            pattern in error_type_lower or pattern in message_lower
            for pattern in network_patterns
        ):
            return ErrorCategory.NETWORK

        # Database errors
        database_patterns = [
            "database",
            "sql",
            "connection",
            "query",
            "transaction",
            "lock",
            "integrity",
            "constraint",
            "table",
            "column",
        ]
        if (
            any(
                pattern in error_type_lower or pattern in message_lower
                for pattern in database_patterns
            )
            or "database" in operation_lower
        ):
            return ErrorCategory.DATABASE

        # Authentication errors
        auth_patterns = [
            "authentication",
            "authorization",
            "auth",
            "token",
            "credential",
            "permission",
            "access",
            "login",
            "unauthorized",
            "forbidden",
        ]
        if any(
            pattern in error_type_lower or pattern in message_lower
            for pattern in auth_patterns
        ):
            return ErrorCategory.AUTHENTICATION

        # Validation errors
        validation_patterns = [
            "validation",
            "invalid",
            "format",
            "parse",
            "schema",
            "type",
            "value",
            "range",
            "required",
            "missing",
        ]
        if any(
            pattern in error_type_lower or pattern in message_lower
            for pattern in validation_patterns
        ):
            return ErrorCategory.VALIDATION

        # Timeout errors
        if "timeout" in error_type_lower or "timeout" in message_lower:
            return ErrorCategory.TIMEOUT

        # Rate limit errors
        rate_limit_patterns = ["rate", "limit", "throttle", "quota", "429"]
        if any(
            pattern in error_type_lower or pattern in message_lower
            for pattern in rate_limit_patterns
        ):
            return ErrorCategory.RATE_LIMIT

        # Parsing errors
        parsing_patterns = ["parse", "json", "xml", "yaml", "decode", "encode"]
        if any(
            pattern in error_type_lower or pattern in message_lower
            for pattern in parsing_patterns
        ):
            return ErrorCategory.PARSING

        # Calculation errors
        calc_patterns = [
            "calculation",
            "math",
            "arithmetic",
            "division",
            "overflow",
            "underflow",
        ]
        if any(
            pattern in error_type_lower or pattern in message_lower
            for pattern in calc_patterns
        ):
            return ErrorCategory.CALCULATION

        # External API errors
        api_patterns = ["api", "service", "endpoint", "client", "server"]
        if any(
            pattern in error_type_lower or pattern in message_lower
            for pattern in api_patterns
        ):
            return ErrorCategory.EXTERNAL_API

        # System errors
        system_patterns = ["system", "memory", "disk", "cpu", "resource", "os"]
        if any(
            pattern in error_type_lower or pattern in message_lower
            for pattern in system_patterns
        ):
            return ErrorCategory.SYSTEM

        return ErrorCategory.UNKNOWN

    def _assess_error_severity(
        self,
        error: Exception,
        component: ComponentType,
        operation: str,
        user_impact: str,
    ) -> ErrorSeverity:
        """Assess error severity based on various factors"""

        # User impact assessment
        if user_impact == "high":
            return ErrorSeverity.CRITICAL
        elif user_impact == "medium":
            return ErrorSeverity.HIGH
        elif user_impact == "low":
            return ErrorSeverity.MEDIUM

        # Critical component operations
        critical_operations = [
            "place_order",
            "cancel_order",
            "process_fill",
            "update_position",
            "calculate_risk",
            "validate_trade",
            "authenticate",
            "connect",
        ]

        if operation.lower() in critical_operations:
            return ErrorSeverity.HIGH

        # Error type severity
        critical_error_types = [
            "SystemExit",
            "KeyboardInterrupt",
            "MemoryError",
            "SystemError",
            "OutOfMemoryError",
            "StackOverflowError",
        ]

        high_severity_types = [
            "ConnectionError",
            "TimeoutError",
            "AuthenticationError",
            "PermissionError",
            "DatabaseError",
            "TransactionError",
        ]

        error_type = type(error).__name__

        if error_type in critical_error_types:
            return ErrorSeverity.CRITICAL
        elif error_type in high_severity_types:
            return ErrorSeverity.HIGH
        elif "Error" in error_type:
            return ErrorSeverity.MEDIUM
        else:
            return ErrorSeverity.LOW

    def _generate_error_fingerprint(self, error_event: ErrorEvent) -> str:
        """Generate fingerprint for error pattern detection"""

        # Normalize error message by removing variable parts
        normalized_message = error_event.error_message

        # Remove numbers, timestamps, IDs
        normalized_message = re.sub(r"\d+", "N", normalized_message)
        normalized_message = re.sub(
            r"\b\w{8}-\w{4}-\w{4}-\w{4}-\w{12}\b", "UUID", normalized_message
        )
        normalized_message = re.sub(r"\b[a-f0-9]{32,64}\b", "HASH", normalized_message)

        # Create fingerprint components
        components = [
            error_event.component.value,
            error_event.operation,
            error_event.error_type,
            normalized_message[:200],  # Truncate long messages
            error_event.error_category.value,
        ]

        fingerprint_string = "|".join(components)
        return hashlib.md5(fingerprint_string.encode()).hexdigest()

    def _update_component_stats(self):
        """Update error statistics for all components"""
        current_time = datetime.now()

        for component in ComponentType:
            if component not in self.errors_by_component:
                continue

            component_errors = self.errors_by_component[component]
            if not component_errors:
                continue

            # Calculate statistics for different time windows
            stats_60min = self._calculate_component_error_stats(
                component, 60, current_time
            )

            self.component_stats[component] = stats_60min

    def _calculate_component_error_stats(
        self, component: ComponentType, minutes: int, current_time: datetime
    ) -> ComponentErrorStats:
        """Calculate error statistics for a component in given time window"""

        cutoff_time = current_time - timedelta(minutes=minutes)
        component_errors = self.errors_by_component[component]

        # Get errors in time window
        window_errors = [
            error for error in component_errors if error.timestamp >= cutoff_time
        ]

        total_errors = len(window_errors)
        error_rate_per_minute = total_errors / minutes if minutes > 0 else 0
        error_rate_per_hour = error_rate_per_minute * 60

        # Calculate success rate
        total_operations = 0
        successful_operations = 0

        for (comp, operation), counters in self.operation_counters.items():
            if comp == component:
                # Reset counters if they're too old
                if time.time() - counters["last_reset"] > 3600:  # 1 hour
                    counters["success"] = 0
                    counters["failure"] = 0
                    counters["last_reset"] = time.time()

                total_operations += counters["success"] + counters["failure"]
                successful_operations += counters["success"]

        success_rate = (
            successful_operations / total_operations if total_operations > 0 else 1.0
        )

        # Most common errors
        error_counter = Counter()
        for error in window_errors:
            error_counter[f"{error.error_type}: {error.error_message[:50]}"] += 1

        most_common_errors = error_counter.most_common(5)

        # Error trend analysis
        if minutes >= 30:  # Need enough data for trend
            half_window = minutes // 2
            first_half_errors = len(
                [
                    error
                    for error in window_errors
                    if error.timestamp >= current_time - timedelta(minutes=minutes)
                    and error.timestamp < current_time - timedelta(minutes=half_window)
                ]
            )
            second_half_errors = total_errors - first_half_errors

            if first_half_errors > 0:
                trend_ratio = second_half_errors / first_half_errors
                if trend_ratio > 1.5:
                    error_trend = "increasing"
                elif trend_ratio < 0.5:
                    error_trend = "decreasing"
                else:
                    error_trend = "stable"
            else:
                error_trend = "increasing" if second_half_errors > 0 else "stable"
        else:
            error_trend = "stable"

        # Burst detection
        error_burst_detected = self._detect_component_error_burst(
            component, current_time
        )

        # Health status
        thresholds = self.rate_thresholds.get(
            component, {"warning": 10.0, "critical": 30.0}
        )

        if error_rate_per_minute >= thresholds["critical"]:
            health_status = "failing"
        elif error_rate_per_minute >= thresholds["warning"]:
            health_status = "degraded"
        else:
            health_status = "healthy"

        # Last error time
        last_error_time = max(
            (error.timestamp for error in window_errors), default=None
        )

        return ComponentErrorStats(
            component=component,
            total_errors=total_errors,
            error_rate_per_minute=error_rate_per_minute,
            error_rate_per_hour=error_rate_per_hour,
            success_rate=success_rate,
            most_common_errors=most_common_errors,
            error_trend=error_trend,
            time_range_minutes=minutes,
            last_error_time=last_error_time,
            error_burst_detected=error_burst_detected,
            health_status=health_status,
        )

    def _detect_error_patterns(self):
        """Detect and analyze error patterns"""

        with self.lock:
            current_time = datetime.now()

            # Process error fingerprints
            for fingerprint, error_ids in self.error_fingerprints.items():
                if len(error_ids) < 3:  # Need at least 3 occurrences
                    continue

                if fingerprint in self.error_patterns:
                    # Update existing pattern
                    pattern = self.error_patterns[fingerprint]
                    pattern.occurrences = len(error_ids)
                    pattern.last_seen = current_time

                    # Recalculate frequency
                    time_span = (
                        current_time - pattern.first_seen
                    ).total_seconds() / 3600
                    pattern.frequency_per_hour = (
                        pattern.occurrences / time_span if time_span > 0 else 0
                    )
                else:
                    # Create new pattern
                    if error_ids:
                        # Get sample error to analyze
                        sample_error = next(
                            (
                                error
                                for error in self.errors
                                if error.error_id in error_ids
                            ),
                            None,
                        )

                        if sample_error:
                            pattern = self._create_error_pattern(
                                fingerprint, error_ids, sample_error
                            )
                            self.error_patterns[fingerprint] = pattern

    def _create_error_pattern(
        self, fingerprint: str, error_ids: list[str], sample_error: ErrorEvent
    ) -> ErrorPattern:
        """Create error pattern from fingerprint and sample error"""

        pattern_id = f"pattern_{fingerprint[:8]}"

        # Get all errors for this pattern
        pattern_errors = [error for error in self.errors if error.error_id in error_ids]

        first_seen = min(error.timestamp for error in pattern_errors)
        last_seen = max(error.timestamp for error in pattern_errors)
        occurrences = len(error_ids)

        time_span = (last_seen - first_seen).total_seconds() / 3600
        frequency_per_hour = occurrences / time_span if time_span > 0 else 0

        # Generate description
        description = f"{sample_error.error_type} in {sample_error.component.value}.{sample_error.operation}"

        # Analyze potential causes and fixes
        potential_causes, suggested_fixes = self._analyze_error_pattern(pattern_errors)

        return ErrorPattern(
            pattern_id=pattern_id,
            pattern_hash=fingerprint,
            description=description,
            error_type=sample_error.error_type,
            component=sample_error.component,
            occurrences=occurrences,
            first_seen=first_seen,
            last_seen=last_seen,
            frequency_per_hour=frequency_per_hour,
            potential_causes=potential_causes,
            suggested_fixes=suggested_fixes,
        )

    def _analyze_error_pattern(
        self, errors: list[ErrorEvent]
    ) -> tuple[list[str], list[str]]:
        """Analyze error pattern to suggest causes and fixes"""

        potential_causes = []
        suggested_fixes = []

        if not errors:
            return potential_causes, suggested_fixes

        sample_error = errors[0]
        error_category = sample_error.error_category

        # Category-specific analysis
        if error_category == ErrorCategory.NETWORK:
            potential_causes.extend(
                [
                    "Network connectivity issues",
                    "API endpoint unavailability",
                    "Firewall or proxy configuration",
                    "DNS resolution problems",
                ]
            )
            suggested_fixes.extend(
                [
                    "Implement retry logic with exponential backoff",
                    "Add connection pooling and keep-alive",
                    "Verify network configuration",
                    "Monitor API endpoint health",
                ]
            )

        elif error_category == ErrorCategory.DATABASE:
            potential_causes.extend(
                [
                    "Database connection pool exhaustion",
                    "Long-running queries causing locks",
                    "Database server overload",
                    "Schema or data integrity issues",
                ]
            )
            suggested_fixes.extend(
                [
                    "Increase connection pool size",
                    "Optimize database queries",
                    "Add query timeout handling",
                    "Review database indexes and schema",
                ]
            )

        elif error_category == ErrorCategory.TIMEOUT:
            potential_causes.extend(
                [
                    "Slow external service responses",
                    "Resource contention",
                    "Insufficient timeout values",
                    "Network latency issues",
                ]
            )
            suggested_fixes.extend(
                [
                    "Increase timeout values",
                    "Implement async processing",
                    "Add request queuing",
                    "Monitor resource usage",
                ]
            )

        elif error_category == ErrorCategory.RATE_LIMIT:
            potential_causes.extend(
                [
                    "Exceeding API rate limits",
                    "Insufficient request throttling",
                    "Multiple instances competing",
                    "Burst traffic patterns",
                ]
            )
            suggested_fixes.extend(
                [
                    "Implement request rate limiting",
                    "Add request queuing and batching",
                    "Use exponential backoff on rate limit hits",
                    "Monitor API usage quotas",
                ]
            )

        # Frequency-based analysis
        if len(errors) > 10:
            potential_causes.append("Systematic issue requiring immediate attention")
            suggested_fixes.append("Investigate root cause and implement permanent fix")

        return potential_causes, suggested_fixes

    def _check_error_rate_alerts(self):
        """Check error rates against thresholds and generate alerts"""
        current_time = datetime.now()

        for component, stats in self.component_stats.items():
            thresholds = self.rate_thresholds.get(
                component, {"warning": 10.0, "critical": 30.0}
            )

            alert_id = f"error_rate_{component.value}"
            current_alert = self.active_alerts.get(alert_id)

            # Check critical threshold
            if stats.error_rate_per_minute >= thresholds["critical"]:
                if (
                    not current_alert
                    or current_alert.severity != ErrorSeverity.CRITICAL
                ):
                    self._create_error_alert(
                        alert_id,
                        component,
                        "rate_threshold",
                        ErrorSeverity.CRITICAL,
                        f"{component.value} error rate critically high: "
                        f"{stats.error_rate_per_minute:.1f}/min (threshold: {thresholds['critical']}/min)",
                        stats.error_rate_per_minute,
                        thresholds["critical"],
                        current_time,
                    )

            # Check warning threshold
            elif stats.error_rate_per_minute >= thresholds["warning"]:
                if not current_alert or current_alert.severity == ErrorSeverity.LOW:
                    self._create_error_alert(
                        alert_id,
                        component,
                        "rate_threshold",
                        ErrorSeverity.HIGH,
                        f"{component.value} error rate above threshold: "
                        f"{stats.error_rate_per_minute:.1f}/min (threshold: {thresholds['warning']}/min)",
                        stats.error_rate_per_minute,
                        thresholds["warning"],
                        current_time,
                    )

            # Clear alert if rate is back to normal
            else:
                if current_alert and not current_alert.resolved:
                    self._resolve_error_alert(alert_id, current_time)

    def _detect_error_bursts(self):
        """Detect error bursts (sudden spikes in error rate)"""
        current_time = datetime.now()

        for component in ComponentType:
            if component not in self.errors_by_component:
                continue

            burst_detected = self._detect_component_error_burst(component, current_time)

            if burst_detected:
                alert_id = f"error_burst_{component.value}"
                if alert_id not in self.active_alerts:
                    recent_errors = self._get_recent_error_count(
                        component, self.burst_detection_window
                    )
                    self._create_error_alert(
                        alert_id,
                        component,
                        "error_burst",
                        ErrorSeverity.HIGH,
                        f"Error burst detected in {component.value}: "
                        f"{recent_errors} errors in {self.burst_detection_window}s",
                        recent_errors / (self.burst_detection_window / 60),
                        0,
                        current_time,
                    )

    def _detect_component_error_burst(
        self, component: ComponentType, current_time: datetime
    ) -> bool:
        """Detect error burst for specific component"""

        # Get recent and baseline error counts
        recent_count = self._get_recent_error_count(
            component, self.burst_detection_window
        )
        baseline_count = self._get_recent_error_count(
            component, self.burst_detection_window * 5
        )

        if baseline_count == 0:
            return recent_count > 5  # Absolute threshold for new errors

        baseline_rate = baseline_count / (self.burst_detection_window * 5)
        recent_rate = recent_count / self.burst_detection_window

        return recent_rate > baseline_rate * self.burst_threshold_multiplier

    def _get_recent_error_count(self, component: ComponentType, seconds: int) -> int:
        """Get error count for component in recent time window"""
        cutoff_time = datetime.now() - timedelta(seconds=seconds)

        component_errors = self.errors_by_component.get(component, deque())
        return sum(1 for error in component_errors if error.timestamp >= cutoff_time)

    def _create_error_alert(
        self,
        alert_id: str,
        component: ComponentType,
        alert_type: str,
        severity: ErrorSeverity,
        message: str,
        error_rate: float,
        threshold: float,
        timestamp: datetime,
    ):
        """Create error alert"""

        alert = ErrorAlert(
            alert_id=alert_id,
            component=component,
            alert_type=alert_type,
            severity=severity,
            message=message,
            error_rate=error_rate,
            threshold=threshold,
            timestamp=timestamp,
        )

        self.active_alerts[alert_id] = alert
        self.alert_history.append(alert)

        logger.warning(f"Error alert [{severity.value}]: {message}")

    def _resolve_error_alert(self, alert_id: str, timestamp: datetime):
        """Resolve error alert"""
        if alert_id in self.active_alerts:
            self.active_alerts[alert_id].resolved = True
            self.active_alerts[alert_id].auto_resolved = True
            logger.info(f"Error alert resolved: {alert_id}")

    def _cleanup_old_errors(self):
        """Remove errors older than retention period"""
        cutoff_time = datetime.now() - timedelta(seconds=self.retention_seconds)

        with self.lock:
            # Clean main errors deque
            while self.errors and self.errors[0].timestamp < cutoff_time:
                self.errors.popleft()

            # Clean component-specific errors
            for component_errors in self.errors_by_component.values():
                while component_errors and component_errors[0].timestamp < cutoff_time:
                    component_errors.popleft()

            # Clean error fingerprints
            valid_error_ids = {error.error_id for error in self.errors}
            for fingerprint in list(self.error_fingerprints.keys()):
                self.error_fingerprints[fingerprint] = [
                    error_id
                    for error_id in self.error_fingerprints[fingerprint]
                    if error_id in valid_error_ids
                ]
                if not self.error_fingerprints[fingerprint]:
                    del self.error_fingerprints[fingerprint]

    def get_error_rate_summary(
        self, component: ComponentType | None = None, minutes: int = 60
    ) -> dict[str, Any]:
        """Get error rate summary"""

        components_to_analyze = [component] if component else list(ComponentType)

        summary = {
            "time_range_minutes": minutes,
            "timestamp": datetime.now().isoformat(),
            "components": {},
        }

        for comp in components_to_analyze:
            if comp in self.component_stats:
                stats = self.component_stats[comp]
                summary["components"][comp.value] = {
                    "total_errors": stats.total_errors,
                    "error_rate_per_minute": stats.error_rate_per_minute,
                    "error_rate_per_hour": stats.error_rate_per_hour,
                    "success_rate": stats.success_rate,
                    "error_trend": stats.error_trend,
                    "health_status": stats.health_status,
                    "error_burst_detected": stats.error_burst_detected,
                    "most_common_errors": [
                        {"error": error, "count": count}
                        for error, count in stats.most_common_errors
                    ],
                    "last_error_time": (
                        stats.last_error_time.isoformat()
                        if stats.last_error_time
                        else None
                    ),
                }

        return summary

    def get_error_patterns(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get identified error patterns"""

        with self.lock:
            patterns = sorted(
                self.error_patterns.values(),
                key=lambda p: p.frequency_per_hour,
                reverse=True,
            )[:limit]

            return [
                {
                    "pattern_id": pattern.pattern_id,
                    "description": pattern.description,
                    "component": pattern.component.value,
                    "error_type": pattern.error_type,
                    "occurrences": pattern.occurrences,
                    "frequency_per_hour": pattern.frequency_per_hour,
                    "first_seen": pattern.first_seen.isoformat(),
                    "last_seen": pattern.last_seen.isoformat(),
                    "potential_causes": pattern.potential_causes,
                    "suggested_fixes": pattern.suggested_fixes,
                }
                for pattern in patterns
            ]

    def get_active_alerts(self) -> list[dict[str, Any]]:
        """Get active error alerts"""

        active_alerts = [
            alert for alert in self.active_alerts.values() if not alert.resolved
        ]

        return [
            {
                "alert_id": alert.alert_id,
                "component": alert.component.value,
                "alert_type": alert.alert_type,
                "severity": alert.severity.value,
                "message": alert.message,
                "error_rate": alert.error_rate,
                "threshold": alert.threshold,
                "timestamp": alert.timestamp.isoformat(),
                "acknowledged": alert.acknowledged,
            }
            for alert in active_alerts
        ]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an error alert"""

        if alert_id in self.active_alerts:
            self.active_alerts[alert_id].acknowledged = True
            logger.info(f"Error alert acknowledged: {alert_id}")
            return True

        return False

    def get_system_error_health(self) -> dict[str, Any]:
        """Get overall system error health assessment"""

        all_stats = list(self.component_stats.values())

        if not all_stats:
            return {
                "overall_health": "unknown",
                "total_error_rate": 0.0,
                "components_healthy": 0,
                "components_degraded": 0,
                "components_failing": 0,
                "active_alerts": 0,
                "error_patterns_detected": 0,
            }

        total_error_rate = sum(stats.error_rate_per_minute for stats in all_stats)
        components_healthy = len([s for s in all_stats if s.health_status == "healthy"])
        components_degraded = len(
            [s for s in all_stats if s.health_status == "degraded"]
        )
        components_failing = len([s for s in all_stats if s.health_status == "failing"])

        # Overall health assessment
        if components_failing > 0:
            overall_health = "critical"
        elif components_degraded > len(all_stats) // 2:
            overall_health = "degraded"
        elif components_degraded > 0:
            overall_health = "warning"
        else:
            overall_health = "healthy"

        active_alerts = len([a for a in self.active_alerts.values() if not a.resolved])

        return {
            "overall_health": overall_health,
            "total_error_rate": total_error_rate,
            "components_healthy": components_healthy,
            "components_degraded": components_degraded,
            "components_failing": components_failing,
            "active_alerts": active_alerts,
            "error_patterns_detected": len(self.error_patterns),
            "timestamp": datetime.now().isoformat(),
        }


# Decorator for automatic error tracking
def track_errors(
    component: ComponentType, operation: str, tracker: ErrorRateTracker | None = None
):
    """Decorator for automatic error tracking"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal tracker
            if tracker is None:
                tracker = get_error_rate_tracker()

            try:
                result = func(*args, **kwargs)
                tracker.record_success(component, operation)
                return result
            except Exception as e:
                # Extract context from function arguments if possible
                context = {}
                if hasattr(func, "__annotations__"):
                    try:
                        # Try to extract meaningful context
                        context = {"function": func.__name__, "args_count": len(args)}
                    except Exception as ctx_error:
                        # If context extraction fails, use basic info
                        context = {"context_error": str(ctx_error)}

                tracker.record_error(component, operation, e, context)
                raise

        return wrapper

    return decorator


# Context manager for error tracking
class ErrorTrackingContext:
    """Context manager for error tracking"""

    def __init__(
        self,
        component: ComponentType,
        operation: str,
        tracker: ErrorRateTracker | None = None,
        context: dict[str, Any] | None = None,
        user_impact: str = "unknown",
    ):
        self.component = component
        self.operation = operation
        self.tracker = tracker or get_error_rate_tracker()
        self.context = context
        self.user_impact = user_impact

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.tracker.record_error(
                self.component,
                self.operation,
                exc_val,
                self.context,
                user_impact=self.user_impact,
            )
        else:
            self.tracker.record_success(self.component, self.operation)


# Global error rate tracker instance
_error_rate_tracker = None


def get_error_rate_tracker() -> ErrorRateTracker:
    """Get global error rate tracker instance"""
    global _error_rate_tracker

    if _error_rate_tracker is None:
        _error_rate_tracker = ErrorRateTracker()
        _error_rate_tracker.start_background_analysis()

    return _error_rate_tracker


def initialize_error_rate_tracking(retention_hours: int = 72) -> ErrorRateTracker:
    """Initialize global error rate tracking"""
    global _error_rate_tracker

    if _error_rate_tracker is not None:
        _error_rate_tracker.stop_background_analysis()

    _error_rate_tracker = ErrorRateTracker(retention_hours)
    _error_rate_tracker.start_background_analysis()

    logger.info("Global error rate tracking initialized")

    return _error_rate_tracker
