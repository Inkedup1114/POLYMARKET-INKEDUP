"""
Operational Issue Monitoring and Alerting

Comprehensive monitoring for operational issues including trading anomalies,
data quality problems, connectivity issues, configuration drift, and
business process failures.
"""

import asyncio
import hashlib
import json
import logging
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from .core import (
    AlertCategory,
    AlertManager,
    AlertRule,
    AlertSeverity,
    get_alert_manager,
)

logger = logging.getLogger(__name__)


class OperationalIssueType(Enum):
    """Types of operational issues"""

    TRADING_ANOMALY = "trading_anomaly"
    DATA_QUALITY = "data_quality"
    CONNECTIVITY_ISSUE = "connectivity_issue"
    CONFIGURATION_DRIFT = "configuration_drift"
    BUSINESS_PROCESS_FAILURE = "business_process_failure"
    API_DEGRADATION = "api_degradation"
    MARKET_DATA_STALE = "market_data_stale"
    ORDER_EXECUTION_DELAY = "order_execution_delay"
    POSITION_RECONCILIATION = "position_reconciliation"
    PRICE_ANOMALY = "price_anomaly"
    VOLUME_ANOMALY = "volume_anomaly"
    LATENCY_SPIKE = "latency_spike"
    AUTHENTICATION_FAILURE = "auth_failure"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    COMPLIANCE_ISSUE = "compliance_issue"


class AlertFrequency(Enum):
    """Alert frequency patterns"""

    ISOLATED = "isolated"  # Single occurrence
    INTERMITTENT = "intermittent"  # Occasional occurrences
    PERSISTENT = "persistent"  # Continuous issue
    ESCALATING = "escalating"  # Getting worse over time
    BURST = "burst"  # Many occurrences in short time


@dataclass
class OperationalEvent:
    """Operational event that can trigger alerts"""

    event_id: str
    issue_type: OperationalIssueType
    component: str
    timestamp: datetime
    severity: AlertSeverity
    description: str
    details: dict[str, Any] = field(default_factory=dict)
    affected_markets: list[str] = field(default_factory=list)
    affected_orders: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
    correlation_id: str | None = None


@dataclass
class OperationalPattern:
    """Detected operational pattern"""

    pattern_id: str
    issue_type: OperationalIssueType
    frequency: AlertFrequency
    first_occurrence: datetime
    last_occurrence: datetime
    event_count: int
    affected_components: set[str]
    pattern_signature: str
    confidence_score: float
    suggested_investigation: list[str] = field(default_factory=list)


@dataclass
class BusinessProcessMonitor:
    """Monitor for business process health"""

    process_name: str
    description: str
    expected_frequency: timedelta  # How often process should run
    max_duration: timedelta  # Maximum acceptable duration
    last_execution: datetime | None = None
    last_duration: timedelta | None = None
    failure_count: int = 0
    enabled: bool = True
    alerts_enabled: bool = True


class TradingAnomalyDetector:
    """Detects trading anomalies and unusual patterns"""

    def __init__(self):
        self.order_history: deque = deque(maxlen=10000)
        self.fill_history: deque = deque(maxlen=10000)
        self.baseline_metrics: dict[str, dict[str, float]] = defaultdict(dict)

        # Anomaly detection parameters
        self.lookback_minutes = 60
        self.anomaly_threshold = 2.5  # Standard deviations

        logger.info("Trading anomaly detector initialized")

    def record_order_event(
        self,
        order_id: str,
        event_type: str,
        market: str,
        order_type: str,
        quantity: float,
        price: float,
        timestamp: datetime | None = None,
    ):
        """Record order event for analysis"""
        if timestamp is None:
            timestamp = datetime.now()

        event = {
            "order_id": order_id,
            "event_type": event_type,  # "placed", "filled", "cancelled", "rejected"
            "market": market,
            "order_type": order_type,
            "quantity": quantity,
            "price": price,
            "timestamp": timestamp,
            "value": quantity * price,
        }

        self.order_history.append(event)

        # Check for anomalies
        asyncio.create_task(self._check_order_anomalies(event))

    def record_fill_event(
        self,
        order_id: str,
        fill_id: str,
        market: str,
        quantity: float,
        price: float,
        timestamp: datetime | None = None,
    ):
        """Record fill event for analysis"""
        if timestamp is None:
            timestamp = datetime.now()

        event = {
            "order_id": order_id,
            "fill_id": fill_id,
            "market": market,
            "quantity": quantity,
            "price": price,
            "timestamp": timestamp,
            "value": quantity * price,
        }

        self.fill_history.append(event)

        # Check for fill anomalies
        asyncio.create_task(self._check_fill_anomalies(event))

    async def _check_order_anomalies(self, event: dict[str, Any]):
        """Check for order-related anomalies"""
        cutoff_time = event["timestamp"] - timedelta(minutes=self.lookback_minutes)

        # Get recent orders for this market
        recent_orders = [
            o
            for o in self.order_history
            if o["market"] == event["market"] and o["timestamp"] >= cutoff_time
        ]

        if len(recent_orders) < 10:  # Need enough data
            return

        # Check order size anomaly
        order_values = [
            o["value"] for o in recent_orders if o["event_type"] == "placed"
        ]
        if order_values:
            await self._check_value_anomaly(
                event,
                order_values,
                "order_size",
                f"Unusually large order size in {event['market']}",
            )

        # Check order frequency anomaly
        order_times = [
            o["timestamp"] for o in recent_orders if o["event_type"] == "placed"
        ]
        if len(order_times) > 5:
            intervals = []
            for i in range(1, len(order_times)):
                interval = (order_times[i] - order_times[i - 1]).total_seconds()
                intervals.append(interval)

            if intervals:
                avg_interval = statistics.mean(intervals)
                recent_interval = (event["timestamp"] - order_times[-2]).total_seconds()

                # Check for burst of orders (very short interval)
                if (
                    recent_interval < avg_interval * 0.1 and recent_interval < 5
                ):  # Less than 5 seconds
                    await self._create_operational_alert(
                        OperationalIssueType.TRADING_ANOMALY,
                        "order_burst",
                        f"Burst of orders detected in {event['market']}",
                        AlertSeverity.MEDIUM,
                        {
                            "market": event["market"],
                            "recent_interval": recent_interval,
                            "average_interval": avg_interval,
                            "order_count_last_minute": len(
                                [
                                    o
                                    for o in recent_orders
                                    if (
                                        event["timestamp"] - o["timestamp"]
                                    ).total_seconds()
                                    < 60
                                ]
                            ),
                        },
                    )

    async def _check_fill_anomalies(self, event: dict[str, Any]):
        """Check for fill-related anomalies"""
        cutoff_time = event["timestamp"] - timedelta(minutes=self.lookback_minutes)

        # Get recent fills for this market
        recent_fills = [
            f
            for f in self.fill_history
            if f["market"] == event["market"] and f["timestamp"] >= cutoff_time
        ]

        if len(recent_fills) < 5:
            return

        # Check fill price anomaly
        fill_prices = [f["price"] for f in recent_fills]
        await self._check_value_anomaly(
            event, fill_prices, "fill_price", f"Unusual fill price in {event['market']}"
        )

        # Check fill size anomaly
        fill_values = [f["value"] for f in recent_fills]
        await self._check_value_anomaly(
            event, fill_values, "fill_size", f"Unusual fill size in {event['market']}"
        )

    async def _check_value_anomaly(
        self,
        event: dict[str, Any],
        values: list[float],
        metric_name: str,
        description: str,
    ):
        """Check if a value is anomalous compared to recent history"""
        if len(values) < 5:
            return

        current_value = event.get("value", event.get("price", 0))
        if current_value == 0:
            return

        mean_value = statistics.mean(values)
        if mean_value == 0:
            return

        try:
            std_dev = statistics.stdev(values)
            if std_dev == 0:
                return

            z_score = abs(current_value - mean_value) / std_dev

            if z_score > self.anomaly_threshold:
                severity = AlertSeverity.HIGH if z_score > 4.0 else AlertSeverity.MEDIUM

                await self._create_operational_alert(
                    OperationalIssueType.TRADING_ANOMALY,
                    metric_name,
                    description,
                    severity,
                    {
                        "market": event["market"],
                        "current_value": current_value,
                        "mean_value": mean_value,
                        "std_dev": std_dev,
                        "z_score": z_score,
                        "anomaly_threshold": self.anomaly_threshold,
                    },
                )
        except statistics.StatisticsError:
            pass  # Skip if can't calculate standard deviation

    async def _create_operational_alert(
        self,
        issue_type: OperationalIssueType,
        alert_name: str,
        description: str,
        severity: AlertSeverity,
        details: dict[str, Any],
    ):
        """Create operational alert"""
        # This would integrate with the main operational monitor
        logger.warning(f"Trading anomaly detected: {alert_name} - {description}")


class DataQualityMonitor:
    """Monitors data quality issues"""

    def __init__(self):
        self.data_sources: dict[str, dict[str, Any]] = {}
        self.quality_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Quality thresholds
        self.staleness_threshold_seconds = 30
        self.completeness_threshold = 0.95
        self.accuracy_threshold = 0.98

        logger.info("Data quality monitor initialized")

    def register_data_source(
        self,
        source_name: str,
        expected_fields: list[str],
        update_frequency_seconds: int,
        critical: bool = True,
    ):
        """Register data source for monitoring"""
        self.data_sources[source_name] = {
            "expected_fields": expected_fields,
            "update_frequency": update_frequency_seconds,
            "critical": critical,
            "last_update": None,
            "last_data": None,
            "quality_score": 1.0,
        }

        logger.info(f"Registered data source: {source_name}")

    async def check_data_update(
        self,
        source_name: str,
        data: dict[str, Any],
        timestamp: datetime | None = None,
    ):
        """Check data update for quality issues"""
        if source_name not in self.data_sources:
            logger.warning(f"Unknown data source: {source_name}")
            return

        if timestamp is None:
            timestamp = datetime.now()

        source_info = self.data_sources[source_name]
        source_info["last_update"] = timestamp
        source_info["last_data"] = data

        # Check data quality
        quality_issues = []

        # Check completeness
        completeness_score = await self._check_data_completeness(source_name, data)
        if completeness_score < self.completeness_threshold:
            quality_issues.append(
                {
                    "type": "completeness",
                    "score": completeness_score,
                    "threshold": self.completeness_threshold,
                }
            )

        # Check consistency
        consistency_score = await self._check_data_consistency(source_name, data)
        if consistency_score < self.accuracy_threshold:
            quality_issues.append(
                {
                    "type": "consistency",
                    "score": consistency_score,
                    "threshold": self.accuracy_threshold,
                }
            )

        # Update quality score
        overall_score = min(completeness_score, consistency_score)
        source_info["quality_score"] = overall_score

        # Record quality metrics
        self.quality_history[source_name].append(
            {
                "timestamp": timestamp,
                "completeness": completeness_score,
                "consistency": consistency_score,
                "overall": overall_score,
                "issues": quality_issues,
            }
        )

        # Create alerts for quality issues
        if quality_issues:
            await self._create_data_quality_alert(
                source_name, quality_issues, source_info
            )

    async def check_data_staleness(self):
        """Check for stale data across all sources"""
        current_time = datetime.now()

        for source_name, source_info in self.data_sources.items():
            if not source_info["last_update"]:
                continue

            staleness_seconds = (
                current_time - source_info["last_update"]
            ).total_seconds()
            expected_frequency = source_info["update_frequency"]

            # Check if data is stale
            if staleness_seconds > max(
                expected_frequency * 2, self.staleness_threshold_seconds
            ):
                severity = (
                    AlertSeverity.CRITICAL
                    if source_info["critical"]
                    else AlertSeverity.HIGH
                )

                await self._create_operational_alert(
                    OperationalIssueType.MARKET_DATA_STALE,
                    f"data_stale_{source_name}",
                    f"Data source {source_name} is stale",
                    severity,
                    {
                        "source": source_name,
                        "staleness_seconds": staleness_seconds,
                        "expected_frequency": expected_frequency,
                        "last_update": source_info["last_update"].isoformat(),
                        "critical": source_info["critical"],
                    },
                )

    async def _check_data_completeness(
        self, source_name: str, data: dict[str, Any]
    ) -> float:
        """Check data completeness"""
        source_info = self.data_sources[source_name]
        expected_fields = source_info["expected_fields"]

        if not expected_fields:
            return 1.0

        present_fields = sum(
            1 for field in expected_fields if field in data and data[field] is not None
        )
        return present_fields / len(expected_fields)

    async def _check_data_consistency(
        self, source_name: str, data: dict[str, Any]
    ) -> float:
        """Check data consistency against historical patterns"""
        history = self.quality_history[source_name]
        if len(history) < 10:
            return 1.0  # Not enough history

        # Simple consistency check - could be enhanced with more sophisticated logic
        consistency_score = 1.0

        # Check for reasonable value ranges
        for key, value in data.items():
            if isinstance(value, (int, float)):
                recent_values = []
                for record in list(history)[-10:]:  # Last 10 records
                    if "data" in record and key in record["data"]:
                        recent_values.append(record["data"][key])

                if recent_values:
                    mean_val = statistics.mean(recent_values)
                    if mean_val != 0:
                        deviation = abs(value - mean_val) / mean_val
                        if deviation > 2.0:  # More than 200% deviation
                            consistency_score *= 0.8

        return max(0.0, consistency_score)

    async def _create_data_quality_alert(
        self,
        source_name: str,
        issues: list[dict[str, Any]],
        source_info: dict[str, Any],
    ):
        """Create data quality alert"""
        severity = (
            AlertSeverity.CRITICAL if source_info["critical"] else AlertSeverity.HIGH
        )

        await self._create_operational_alert(
            OperationalIssueType.DATA_QUALITY,
            f"data_quality_{source_name}",
            f"Data quality issues in {source_name}",
            severity,
            {
                "source": source_name,
                "issues": issues,
                "overall_score": source_info["quality_score"],
                "critical": source_info["critical"],
            },
        )

    async def _create_operational_alert(
        self,
        issue_type: OperationalIssueType,
        alert_name: str,
        description: str,
        severity: AlertSeverity,
        details: dict[str, Any],
    ):
        """Create operational alert"""
        logger.warning(f"Data quality issue: {alert_name} - {description}")


class ConnectivityMonitor:
    """Monitors connectivity to external services"""

    def __init__(self):
        self.endpoints: dict[str, dict[str, Any]] = {}
        self.connectivity_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=100)
        )

        logger.info("Connectivity monitor initialized")

    def register_endpoint(
        self,
        name: str,
        url: str,
        method: str = "GET",
        timeout_seconds: int = 10,
        critical: bool = True,
        headers: dict[str, str] | None = None,
    ):
        """Register endpoint for monitoring"""
        self.endpoints[name] = {
            "url": url,
            "method": method,
            "timeout": timeout_seconds,
            "critical": critical,
            "headers": headers or {},
            "last_check": None,
            "status": "unknown",
            "response_time": None,
            "consecutive_failures": 0,
        }

        logger.info(f"Registered endpoint: {name} ({url})")

    async def check_connectivity(self, endpoint_name: str | None = None):
        """Check connectivity to endpoints"""
        endpoints_to_check = (
            [endpoint_name] if endpoint_name else list(self.endpoints.keys())
        )

        for name in endpoints_to_check:
            if name not in self.endpoints:
                continue

            endpoint = self.endpoints[name]

            try:
                # Perform connectivity check
                start_time = datetime.now()
                success, response_time, error_message = await self._check_endpoint(
                    endpoint
                )

                # Update endpoint status
                endpoint["last_check"] = start_time
                endpoint["response_time"] = response_time
                endpoint["status"] = "healthy" if success else "failed"

                if success:
                    endpoint["consecutive_failures"] = 0
                else:
                    endpoint["consecutive_failures"] += 1

                # Record connectivity history
                self.connectivity_history[name].append(
                    {
                        "timestamp": start_time,
                        "success": success,
                        "response_time": response_time,
                        "error": error_message,
                    }
                )

                # Create alerts for connectivity issues
                if not success:
                    await self._handle_connectivity_failure(
                        name, endpoint, error_message
                    )

            except Exception as e:
                logger.error(f"Error checking connectivity for {name}: {e}")
                endpoint["status"] = "error"
                endpoint["consecutive_failures"] += 1

    async def _check_endpoint(
        self, endpoint: dict[str, Any]
    ) -> tuple[bool, float | None, str | None]:
        """Check individual endpoint"""
        import aiohttp

        start_time = datetime.now()

        try:
            timeout = aiohttp.ClientTimeout(total=endpoint["timeout"])

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    endpoint["method"], endpoint["url"], headers=endpoint["headers"]
                ) as response:
                    response_time = (datetime.now() - start_time).total_seconds() * 1000

                    if response.status < 400:
                        return True, response_time, None
                    else:
                        return False, response_time, f"HTTP {response.status}"

        except TimeoutError:
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            return False, response_time, "Timeout"

        except Exception as e:
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            return False, response_time, str(e)

    async def _handle_connectivity_failure(
        self, name: str, endpoint: dict[str, Any], error: str
    ):
        """Handle connectivity failure"""
        consecutive_failures = endpoint["consecutive_failures"]

        # Determine severity based on consecutive failures and criticality
        if consecutive_failures >= 5 and endpoint["critical"]:
            severity = AlertSeverity.CRITICAL
        elif consecutive_failures >= 3:
            severity = AlertSeverity.HIGH
        else:
            severity = AlertSeverity.MEDIUM

        await self._create_operational_alert(
            OperationalIssueType.CONNECTIVITY_ISSUE,
            f"connectivity_{name}",
            f"Connectivity issue with {name}",
            severity,
            {
                "endpoint": name,
                "url": endpoint["url"],
                "error": error,
                "consecutive_failures": consecutive_failures,
                "critical": endpoint["critical"],
                "response_time": endpoint.get("response_time"),
                "last_successful": self._get_last_successful_check(name),
            },
        )

    def _get_last_successful_check(self, endpoint_name: str) -> str | None:
        """Get timestamp of last successful check"""
        history = self.connectivity_history[endpoint_name]

        for record in reversed(history):
            if record["success"]:
                return record["timestamp"].isoformat()

        return None

    async def _create_operational_alert(
        self,
        issue_type: OperationalIssueType,
        alert_name: str,
        description: str,
        severity: AlertSeverity,
        details: dict[str, Any],
    ):
        """Create operational alert"""
        logger.warning(f"Connectivity issue: {alert_name} - {description}")


class OperationalMonitor:
    """
    Main operational monitoring system

    Coordinates monitoring of trading anomalies, data quality, connectivity,
    and other operational issues with intelligent alerting.
    """

    def __init__(self, alert_manager: AlertManager | None = None):
        self.alert_manager = alert_manager or get_alert_manager()

        # Sub-monitors
        self.trading_detector = TradingAnomalyDetector()
        self.data_monitor = DataQualityMonitor()
        self.connectivity_monitor = ConnectivityMonitor()

        # Operational events and patterns
        self.operational_events: deque = deque(maxlen=10000)
        self.detected_patterns: dict[str, OperationalPattern] = {}

        # Business process monitors
        self.business_processes: dict[str, BusinessProcessMonitor] = {}

        # Monitoring state
        self.running = False
        self.monitoring_tasks: list[asyncio.Task] = []

        # Pattern detection settings
        self.pattern_detection_interval = 300  # 5 minutes
        self.pattern_confidence_threshold = 0.7

        # Setup default operational rules
        self._setup_operational_rules()

        logger.info("Operational monitor initialized")

    def _setup_operational_rules(self):
        """Setup default operational alert rules"""

        # Trading anomaly rule
        trading_rule = AlertRule(
            rule_id="operational_trading_anomaly",
            name="Trading Anomaly Detected",
            category=AlertCategory.OPERATIONAL_ISSUE,
            description="Unusual trading pattern detected",
            condition="trading_anomaly detected",
            severity=AlertSeverity.MEDIUM,
            enabled=True,
            tags={"type": "trading", "component": "anomaly_detector"},
            auto_resolve=False,
            cooldown_seconds=1800,  # 30 minutes
            max_frequency=10,
        )
        self.alert_manager.add_alert_rule(trading_rule)

        # Data quality rule
        data_quality_rule = AlertRule(
            rule_id="operational_data_quality",
            name="Data Quality Issue",
            category=AlertCategory.DATA_QUALITY,
            description="Data quality below acceptable threshold",
            condition="data_quality_score < threshold",
            severity=AlertSeverity.HIGH,
            enabled=True,
            tags={"type": "data_quality", "component": "data_monitor"},
            auto_resolve=True,
            cooldown_seconds=600,  # 10 minutes
            max_frequency=20,
        )
        self.alert_manager.add_alert_rule(data_quality_rule)

        # Connectivity rule
        connectivity_rule = AlertRule(
            rule_id="operational_connectivity",
            name="Connectivity Issue",
            category=AlertCategory.NETWORK,
            description="External service connectivity problem",
            condition="endpoint_unreachable",
            severity=AlertSeverity.HIGH,
            enabled=True,
            tags={"type": "connectivity", "component": "connectivity_monitor"},
            auto_resolve=True,
            cooldown_seconds=300,  # 5 minutes
            max_frequency=30,
        )
        self.alert_manager.add_alert_rule(connectivity_rule)

        # Business process rule
        business_process_rule = AlertRule(
            rule_id="operational_business_process",
            name="Business Process Failure",
            category=AlertCategory.OPERATIONAL_ISSUE,
            description="Critical business process failed or delayed",
            condition="business_process_failure",
            severity=AlertSeverity.HIGH,
            enabled=True,
            tags={"type": "business_process", "component": "process_monitor"},
            auto_resolve=True,
            cooldown_seconds=900,  # 15 minutes
            max_frequency=15,
        )
        self.alert_manager.add_alert_rule(business_process_rule)

    async def start_monitoring(self):
        """Start operational monitoring"""
        if self.running:
            return

        self.running = True

        # Start monitoring tasks
        self.monitoring_tasks = [
            asyncio.create_task(self._data_staleness_loop()),
            asyncio.create_task(self._connectivity_loop()),
            asyncio.create_task(self._business_process_loop()),
            asyncio.create_task(self._pattern_detection_loop()),
            asyncio.create_task(self._event_cleanup_loop()),
        ]

        logger.info("Operational monitoring started")

    async def stop_monitoring(self):
        """Stop operational monitoring"""
        if not self.running:
            return

        self.running = False

        # Cancel monitoring tasks
        for task in self.monitoring_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.monitoring_tasks.clear()
        logger.info("Operational monitoring stopped")

    async def _data_staleness_loop(self):
        """Monitor data staleness"""
        while self.running:
            try:
                await self.data_monitor.check_data_staleness()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in data staleness monitoring: {e}")
                await asyncio.sleep(30)

    async def _connectivity_loop(self):
        """Monitor connectivity"""
        while self.running:
            try:
                await self.connectivity_monitor.check_connectivity()
                await asyncio.sleep(120)  # Check every 2 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in connectivity monitoring: {e}")
                await asyncio.sleep(60)

    async def _business_process_loop(self):
        """Monitor business processes"""
        while self.running:
            try:
                await self._check_business_processes()
                await asyncio.sleep(180)  # Check every 3 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in business process monitoring: {e}")
                await asyncio.sleep(60)

    async def _pattern_detection_loop(self):
        """Detect operational patterns"""
        while self.running:
            try:
                await self._detect_operational_patterns()
                await asyncio.sleep(self.pattern_detection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in pattern detection: {e}")
                await asyncio.sleep(120)

    async def _event_cleanup_loop(self):
        """Clean up old events"""
        while self.running:
            try:
                await self._cleanup_old_events()
                await asyncio.sleep(3600)  # Clean every hour
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in event cleanup: {e}")
                await asyncio.sleep(1800)

    def record_operational_event(
        self,
        issue_type: OperationalIssueType,
        component: str,
        description: str,
        severity: AlertSeverity,
        details: dict[str, Any] | None = None,
        affected_markets: list[str] | None = None,
        affected_orders: list[str] | None = None,
    ):
        """Record operational event"""

        event = OperationalEvent(
            event_id=f"op_{int(datetime.now().timestamp() * 1000000)}",
            issue_type=issue_type,
            component=component,
            timestamp=datetime.now(),
            severity=severity,
            description=description,
            details=details or {},
            affected_markets=affected_markets or [],
            affected_orders=affected_orders or [],
        )

        self.operational_events.append(event)

        # Create alert
        asyncio.create_task(self._create_operational_alert(event))

    async def _create_operational_alert(self, event: OperationalEvent):
        """Create alert from operational event"""

        # Determine rule ID based on issue type
        rule_mapping = {
            OperationalIssueType.TRADING_ANOMALY: "operational_trading_anomaly",
            OperationalIssueType.DATA_QUALITY: "operational_data_quality",
            OperationalIssueType.CONNECTIVITY_ISSUE: "operational_connectivity",
            OperationalIssueType.BUSINESS_PROCESS_FAILURE: "operational_business_process",
        }

        rule_id = rule_mapping.get(event.issue_type, "operational_generic")

        # Create alert context
        context = {
            "event_id": event.event_id,
            "issue_type": event.issue_type.value,
            "component": event.component,
            "description": event.description,
            "severity": event.severity.value,
            "affected_markets": event.affected_markets,
            "affected_orders": event.affected_orders,
            "details": event.details,
            "metrics": event.metrics,
            "correlation_id": event.correlation_id,
        }

        alert = self.alert_manager.create_alert(
            rule_id=rule_id,
            triggered_by=f"Operational event: {event.issue_type.value}",
            affected_components=[f"{event.component}_{event.issue_type.value}"],
            context=context,
        )

        if alert:
            logger.warning(
                f"Operational alert created: {event.description} ({event.issue_type.value})"
            )

    def add_business_process(self, process: BusinessProcessMonitor):
        """Add business process for monitoring"""
        self.business_processes[process.process_name] = process
        logger.info(f"Added business process monitor: {process.process_name}")

    def record_business_process_execution(
        self, process_name: str, start_time: datetime, end_time: datetime, success: bool
    ):
        """Record business process execution"""
        if process_name not in self.business_processes:
            return

        process = self.business_processes[process_name]
        duration = end_time - start_time

        process.last_execution = end_time
        process.last_duration = duration

        if success:
            process.failure_count = 0
        else:
            process.failure_count += 1

            # Create alert for process failure
            if process.alerts_enabled:
                self.record_operational_event(
                    OperationalIssueType.BUSINESS_PROCESS_FAILURE,
                    process_name,
                    f"Business process {process_name} failed",
                    AlertSeverity.HIGH,
                    {
                        "process": process_name,
                        "failure_count": process.failure_count,
                        "duration": duration.total_seconds(),
                        "expected_frequency": process.expected_frequency.total_seconds(),
                    },
                )

    async def _check_business_processes(self):
        """Check business process health"""
        current_time = datetime.now()

        for process_name, process in self.business_processes.items():
            if not process.enabled or not process.alerts_enabled:
                continue

            # Check if process is overdue
            if process.last_execution:
                time_since_last = current_time - process.last_execution
                if time_since_last > process.expected_frequency * 1.5:  # 50% tolerance
                    self.record_operational_event(
                        OperationalIssueType.BUSINESS_PROCESS_FAILURE,
                        process_name,
                        f"Business process {process_name} is overdue",
                        AlertSeverity.HIGH,
                        {
                            "process": process_name,
                            "overdue_minutes": time_since_last.total_seconds() / 60,
                            "expected_frequency_minutes": process.expected_frequency.total_seconds()
                            / 60,
                            "last_execution": process.last_execution.isoformat(),
                        },
                    )

            # Check if last execution took too long
            if process.last_duration and process.last_duration > process.max_duration:
                self.record_operational_event(
                    OperationalIssueType.BUSINESS_PROCESS_FAILURE,
                    process_name,
                    f"Business process {process_name} exceeded maximum duration",
                    AlertSeverity.MEDIUM,
                    {
                        "process": process_name,
                        "actual_duration_minutes": process.last_duration.total_seconds()
                        / 60,
                        "max_duration_minutes": process.max_duration.total_seconds()
                        / 60,
                    },
                )

    async def _detect_operational_patterns(self):
        """Detect patterns in operational events"""
        if len(self.operational_events) < 10:
            return

        # Group events by issue type and component
        event_groups = defaultdict(list)

        cutoff_time = datetime.now() - timedelta(hours=24)  # Look at last 24 hours

        for event in self.operational_events:
            if event.timestamp >= cutoff_time:
                group_key = f"{event.issue_type.value}_{event.component}"
                event_groups[group_key].append(event)

        # Analyze each group for patterns
        for group_key, events in event_groups.items():
            if len(events) < 3:  # Need at least 3 events
                continue

            pattern = await self._analyze_event_pattern(group_key, events)
            if (
                pattern
                and pattern.confidence_score >= self.pattern_confidence_threshold
            ):
                self.detected_patterns[pattern.pattern_id] = pattern

                # Create pattern alert if it's a new concerning pattern
                if (
                    pattern.frequency
                    in [AlertFrequency.PERSISTENT, AlertFrequency.ESCALATING]
                    and pattern.event_count > 5
                ):
                    await self._create_pattern_alert(pattern)

    async def _analyze_event_pattern(
        self, group_key: str, events: list[OperationalEvent]
    ) -> OperationalPattern | None:
        """Analyze events for patterns"""

        events = sorted(events, key=lambda e: e.timestamp)
        first_event = events[0]
        last_event = events[-1]

        # Calculate time intervals between events
        intervals = []
        for i in range(1, len(events)):
            interval = (events[i].timestamp - events[i - 1].timestamp).total_seconds()
            intervals.append(interval)

        # Determine frequency pattern
        frequency = AlertFrequency.ISOLATED
        if len(events) > 10:
            avg_interval = statistics.mean(intervals)
            if avg_interval < 300:  # Less than 5 minutes
                frequency = AlertFrequency.BURST
            elif avg_interval < 3600:  # Less than 1 hour
                frequency = AlertFrequency.PERSISTENT
        elif len(events) > 3:
            frequency = AlertFrequency.INTERMITTENT

        # Check if escalating (intervals getting shorter)
        if len(intervals) > 3:
            recent_avg = statistics.mean(intervals[-3:])
            early_avg = statistics.mean(intervals[:3])
            if recent_avg < early_avg * 0.5:  # Recent intervals 50% shorter
                frequency = AlertFrequency.ESCALATING

        # Calculate confidence score
        confidence = min(1.0, len(events) / 10.0)  # More events = higher confidence

        # Create pattern signature
        signature_data = {
            "issue_type": first_event.issue_type.value,
            "component": first_event.component,
            "event_count": len(events),
            "frequency": frequency.value,
        }
        signature = hashlib.md5(
            json.dumps(signature_data, sort_keys=True).encode()
        ).hexdigest()[:8]

        pattern = OperationalPattern(
            pattern_id=f"pattern_{signature}",
            issue_type=first_event.issue_type,
            frequency=frequency,
            first_occurrence=first_event.timestamp,
            last_occurrence=last_event.timestamp,
            event_count=len(events),
            affected_components={event.component for event in events},
            pattern_signature=signature,
            confidence_score=confidence,
            suggested_investigation=self._generate_investigation_suggestions(
                first_event.issue_type, frequency, len(events)
            ),
        )

        return pattern

    def _generate_investigation_suggestions(
        self,
        issue_type: OperationalIssueType,
        frequency: AlertFrequency,
        event_count: int,
    ) -> list[str]:
        """Generate investigation suggestions based on pattern"""

        suggestions = []

        if issue_type == OperationalIssueType.TRADING_ANOMALY:
            suggestions.extend(
                [
                    "Review recent trading algorithm changes",
                    "Check for unusual market conditions",
                    "Analyze order flow patterns",
                    "Verify risk management settings",
                ]
            )

            if frequency == AlertFrequency.BURST:
                suggestions.append("Investigate potential algorithm malfunction")
            elif frequency == AlertFrequency.ESCALATING:
                suggestions.append("Check for feedback loop in trading logic")

        elif issue_type == OperationalIssueType.DATA_QUALITY:
            suggestions.extend(
                [
                    "Verify data source connectivity",
                    "Check data transformation logic",
                    "Review data validation rules",
                    "Investigate upstream data provider issues",
                ]
            )

            if event_count > 10:
                suggestions.append("Consider switching to backup data source")

        elif issue_type == OperationalIssueType.CONNECTIVITY_ISSUE:
            suggestions.extend(
                [
                    "Check network connectivity",
                    "Verify API credentials and permissions",
                    "Review rate limiting settings",
                    "Test connection from different network",
                ]
            )

            if frequency == AlertFrequency.PERSISTENT:
                suggestions.append("Contact service provider support")

        return suggestions

    async def _create_pattern_alert(self, pattern: OperationalPattern):
        """Create alert for detected pattern"""

        alert = self.alert_manager.create_alert(
            rule_id="operational_pattern_detected",
            triggered_by=f"Operational pattern detected: {pattern.pattern_id}",
            affected_components=[f"pattern_{pattern.issue_type.value}"],
            context={
                "pattern_id": pattern.pattern_id,
                "issue_type": pattern.issue_type.value,
                "frequency": pattern.frequency.value,
                "event_count": pattern.event_count,
                "confidence_score": pattern.confidence_score,
                "affected_components": list(pattern.affected_components),
                "first_occurrence": pattern.first_occurrence.isoformat(),
                "last_occurrence": pattern.last_occurrence.isoformat(),
                "suggested_investigation": pattern.suggested_investigation,
            },
        )

        if alert:
            logger.warning(
                f"Operational pattern detected: {pattern.issue_type.value} "
                f"({pattern.frequency.value}, {pattern.event_count} events, "
                f"{pattern.confidence_score:.1%} confidence)"
            )

    async def _cleanup_old_events(self):
        """Clean up old operational events and patterns"""
        cutoff_time = datetime.now() - timedelta(hours=48)  # Keep 48 hours

        # Clean events (deque automatically limits size, but we can clean by time)
        # Note: deque doesn't support removal by condition efficiently,
        # so we rely on maxlen for now

        # Clean old patterns
        old_patterns = [
            pid
            for pid, pattern in self.detected_patterns.items()
            if pattern.last_occurrence < cutoff_time
        ]

        for pid in old_patterns:
            del self.detected_patterns[pid]

        if old_patterns:
            logger.debug(f"Cleaned {len(old_patterns)} old operational patterns")

    def get_operational_summary(self) -> dict[str, Any]:
        """Get operational monitoring summary"""

        recent_events = [
            event
            for event in self.operational_events
            if (datetime.now() - event.timestamp).total_seconds() < 3600  # Last hour
        ]

        # Count events by type
        event_counts = defaultdict(int)
        for event in recent_events:
            event_counts[event.issue_type.value] += 1

        # Count patterns by frequency
        pattern_counts = defaultdict(int)
        for pattern in self.detected_patterns.values():
            pattern_counts[pattern.frequency.value] += 1

        return {
            "timestamp": datetime.now().isoformat(),
            "monitoring_running": self.running,
            "recent_events_count": len(recent_events),
            "total_events": len(self.operational_events),
            "detected_patterns": len(self.detected_patterns),
            "business_processes": len(self.business_processes),
            "event_counts_by_type": dict(event_counts),
            "pattern_counts_by_frequency": dict(pattern_counts),
            "data_sources": len(self.data_monitor.data_sources),
            "monitored_endpoints": len(self.connectivity_monitor.endpoints),
            "system_health": self._assess_overall_health(),
        }

    def _assess_overall_health(self) -> str:
        """Assess overall operational health"""
        recent_events = [
            event
            for event in self.operational_events
            if (datetime.now() - event.timestamp).total_seconds()
            < 1800  # Last 30 minutes
        ]

        critical_events = [
            e for e in recent_events if e.severity == AlertSeverity.CRITICAL
        ]
        high_events = [e for e in recent_events if e.severity == AlertSeverity.HIGH]

        # Count concerning patterns
        concerning_patterns = [
            p
            for p in self.detected_patterns.values()
            if p.frequency in [AlertFrequency.PERSISTENT, AlertFrequency.ESCALATING]
        ]

        if critical_events or concerning_patterns:
            return "critical"
        elif high_events or len(recent_events) > 20:
            return "degraded"
        elif len(recent_events) > 5:
            return "warning"
        else:
            return "healthy"


# Global operational monitor instance
_operational_monitor = None


def get_operational_monitor() -> OperationalMonitor:
    """Get global operational monitor instance"""
    global _operational_monitor

    if _operational_monitor is None:
        _operational_monitor = OperationalMonitor()

    return _operational_monitor


def initialize_operational_monitoring() -> OperationalMonitor:
    """Initialize operational monitoring system"""
    global _operational_monitor

    _operational_monitor = OperationalMonitor()
    logger.info("Operational monitoring system initialized")

    return _operational_monitor
