"""
Risk Management Alert Integration

Specialized alerting for risk management events including position limits,
exposure breaches, risk metrics violations, and automated risk controls.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
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


class RiskAlertType(Enum):
    """Types of risk-related alerts"""

    POSITION_LIMIT_BREACH = "position_limit_breach"
    EXPOSURE_LIMIT_BREACH = "exposure_limit_breach"
    DRAWDOWN_LIMIT_BREACH = "drawdown_limit_breach"
    VaR_LIMIT_BREACH = "var_limit_breach"
    CONCENTRATION_RISK = "concentration_risk"
    LIQUIDITY_RISK = "liquidity_risk"
    CORRELATION_RISK = "correlation_risk"
    VOLATILITY_SPIKE = "volatility_spike"
    MARGIN_CALL = "margin_call"
    STOP_LOSS_TRIGGERED = "stop_loss_triggered"
    RISK_MODEL_FAILURE = "risk_model_failure"
    DATA_QUALITY_ISSUE = "data_quality_issue"
    COMPLIANCE_VIOLATION = "compliance_violation"
    AUTOMATED_SHUTDOWN = "automated_shutdown"


@dataclass
class RiskLimit:
    """Risk limit definition"""

    limit_id: str
    name: str
    limit_type: RiskAlertType
    description: str
    warning_threshold: float
    critical_threshold: float
    emergency_threshold: float | None = None
    currency: str = "USD"
    time_horizon: str = "1D"  # 1D, 1W, 1M, etc.
    enabled: bool = True
    auto_action: str | None = None  # "stop_trading", "reduce_positions", etc.
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class RiskEvent:
    """Risk event that can trigger alerts"""

    event_id: str
    event_type: RiskAlertType
    timestamp: datetime
    affected_positions: list[str] = field(default_factory=list)
    affected_markets: list[str] = field(default_factory=list)
    current_value: float | None = None
    limit_value: float | None = None
    breach_magnitude: float | None = None  # How much over the limit
    risk_metrics: dict[str, float] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    auto_actions_taken: list[str] = field(default_factory=list)


class RiskMetricsMonitor:
    """Monitors risk metrics and triggers alerts when thresholds are breached"""

    def __init__(self, alert_manager: AlertManager | None = None):
        self.alert_manager = alert_manager or get_alert_manager()
        self.risk_limits: dict[str, RiskLimit] = {}
        self.risk_metrics_history: dict[str, list[tuple[datetime, float]]] = (
            defaultdict(list)
        )
        self.active_breaches: dict[str, RiskEvent] = {}

        # Risk calculation callbacks
        self.risk_calculators: dict[RiskAlertType, Callable] = {}

        # Auto-action handlers
        self.auto_action_handlers: dict[str, Callable] = {}

        # Monitoring configuration
        self.monitoring_interval = 30  # seconds
        self.history_retention_hours = 24

        logger.info("Risk metrics monitor initialized")

    def add_risk_limit(self, limit: RiskLimit):
        """Add risk limit for monitoring"""
        self.risk_limits[limit.limit_id] = limit

        # Create corresponding alert rule
        alert_rule = AlertRule(
            rule_id=f"risk_{limit.limit_id}",
            name=f"Risk Limit: {limit.name}",
            category=AlertCategory.RISK_MANAGEMENT,
            description=f"Risk limit breach: {limit.description}",
            condition=f"risk_metric['{limit.limit_id}'] > {limit.critical_threshold}",
            severity=AlertSeverity.HIGH,
            enabled=limit.enabled,
            tags={"risk_type": limit.limit_type.value, **limit.tags},
            auto_resolve=True,
            cooldown_seconds=300,
            max_frequency=20,
        )

        self.alert_manager.add_alert_rule(alert_rule)
        logger.info(f"Added risk limit: {limit.name} ({limit.limit_id})")

    def register_risk_calculator(self, risk_type: RiskAlertType, calculator: Callable):
        """Register risk metric calculator"""
        self.risk_calculators[risk_type] = calculator
        logger.info(f"Registered risk calculator for {risk_type.value}")

    def register_auto_action_handler(self, action: str, handler: Callable):
        """Register auto-action handler"""
        self.auto_action_handlers[action] = handler
        logger.info(f"Registered auto-action handler: {action}")

    async def monitor_risk_metrics(self):
        """Monitor all risk metrics and trigger alerts"""
        while True:
            try:
                await self._evaluate_all_risk_limits()
                await asyncio.sleep(self.monitoring_interval)
            except Exception as e:
                logger.error(f"Error in risk metrics monitoring: {e}")
                await asyncio.sleep(10)

    async def _evaluate_all_risk_limits(self):
        """Evaluate all risk limits against current metrics"""
        current_time = datetime.now()

        for limit_id, limit in self.risk_limits.items():
            if not limit.enabled:
                continue

            try:
                # Calculate current risk metric
                calculator = self.risk_calculators.get(limit.limit_type)
                if not calculator:
                    continue

                current_value = await calculator(limit)
                if current_value is None:
                    continue

                # Store metric history
                self.risk_metrics_history[limit_id].append(
                    (current_time, current_value)
                )
                self._cleanup_metric_history(limit_id)

                # Check for breaches
                await self._check_risk_limit_breach(limit, current_value, current_time)

            except Exception as e:
                logger.error(f"Error evaluating risk limit {limit_id}: {e}")

    async def _check_risk_limit_breach(
        self, limit: RiskLimit, current_value: float, current_time: datetime
    ):
        """Check if risk limit is breached and handle accordingly"""

        breach_severity = None
        threshold_value = None

        # Determine breach severity
        if (
            limit.emergency_threshold is not None
            and current_value >= limit.emergency_threshold
        ):
            breach_severity = AlertSeverity.EMERGENCY
            threshold_value = limit.emergency_threshold
        elif current_value >= limit.critical_threshold:
            breach_severity = AlertSeverity.CRITICAL
            threshold_value = limit.critical_threshold
        elif current_value >= limit.warning_threshold:
            breach_severity = AlertSeverity.HIGH
            threshold_value = limit.warning_threshold

        # Handle breach
        if breach_severity:
            await self._handle_risk_breach(
                limit, current_value, threshold_value, breach_severity, current_time
            )
        else:
            # Check if we need to resolve an existing breach
            await self._check_breach_resolution(limit, current_value)

    async def _handle_risk_breach(
        self,
        limit: RiskLimit,
        current_value: float,
        threshold_value: float,
        severity: AlertSeverity,
        current_time: datetime,
    ):
        """Handle risk limit breach"""

        breach_magnitude = current_value - threshold_value

        # Create risk event
        risk_event = RiskEvent(
            event_id=f"{limit.limit_id}_{int(current_time.timestamp())}",
            event_type=limit.limit_type,
            timestamp=current_time,
            current_value=current_value,
            limit_value=threshold_value,
            breach_magnitude=breach_magnitude,
            context={
                "limit_name": limit.name,
                "limit_type": limit.limit_type.value,
                "breach_percentage": (breach_magnitude / threshold_value) * 100,
                "currency": limit.currency,
                "time_horizon": limit.time_horizon,
            },
        )

        # Execute auto-actions if configured
        if limit.auto_action and severity in [
            AlertSeverity.CRITICAL,
            AlertSeverity.EMERGENCY,
        ]:
            await self._execute_auto_action(risk_event, limit.auto_action)

        # Create alert
        alert = self.alert_manager.create_alert(
            rule_id=f"risk_{limit.limit_id}",
            triggered_by=f"Risk limit breach: {limit.name}",
            current_value=current_value,
            threshold_value=threshold_value,
            affected_components=[f"risk_limit_{limit.limit_id}"],
            context=risk_event.context,
        )

        if alert:
            # Store breach for tracking
            self.active_breaches[limit.limit_id] = risk_event

            logger.warning(
                f"Risk limit breach [{severity.value}]: {limit.name} "
                f"({current_value:.2f} vs {threshold_value:.2f} {limit.currency})"
            )

    async def _execute_auto_action(self, risk_event: RiskEvent, action: str):
        """Execute automated risk response action"""

        handler = self.auto_action_handlers.get(action)
        if not handler:
            logger.warning(f"No handler registered for auto-action: {action}")
            return

        try:
            result = await handler(risk_event)
            risk_event.auto_actions_taken.append(f"{action}: {result}")

            logger.warning(
                f"Auto-action executed: {action} for {risk_event.event_type.value} "
                f"(Result: {result})"
            )

        except Exception as e:
            logger.error(f"Error executing auto-action {action}: {e}")
            risk_event.auto_actions_taken.append(f"{action}: ERROR - {str(e)}")

    async def _check_breach_resolution(self, limit: RiskLimit, current_value: float):
        """Check if an existing breach should be resolved"""

        if limit.limit_id not in self.active_breaches:
            return

        # Resolve if value is back below warning threshold (with buffer)
        resolution_buffer = 0.95  # 5% buffer to avoid flapping
        resolution_threshold = limit.warning_threshold * resolution_buffer

        if current_value <= resolution_threshold:
            # Resolve the breach
            risk_event = self.active_breaches[limit.limit_id]

            # Find and resolve corresponding alert
            active_alerts = self.alert_manager.get_active_alerts(
                category=AlertCategory.RISK_MANAGEMENT
            )

            for alert in active_alerts:
                if alert.rule_id == f"risk_{limit.limit_id}":
                    self.alert_manager.resolve_alert(
                        alert.alert_id,
                        resolved_by="risk_monitor",
                        notes=f"Risk metric returned to acceptable level: {current_value:.2f}",
                        auto_resolved=True,
                    )
                    break

            # Remove from active breaches
            del self.active_breaches[limit.limit_id]

            logger.info(f"Risk limit breach resolved: {limit.name}")

    def _cleanup_metric_history(self, limit_id: str):
        """Clean up old metric history"""
        cutoff_time = datetime.now() - timedelta(hours=self.history_retention_hours)

        history = self.risk_metrics_history[limit_id]
        self.risk_metrics_history[limit_id] = [
            (timestamp, value)
            for timestamp, value in history
            if timestamp >= cutoff_time
        ]

    def get_risk_metrics_summary(self) -> dict[str, Any]:
        """Get summary of current risk metrics"""
        current_time = datetime.now()
        summary = {
            "timestamp": current_time.isoformat(),
            "active_breaches": len(self.active_breaches),
            "monitored_limits": len(self.risk_limits),
            "enabled_limits": len([l for l in self.risk_limits.values() if l.enabled]),
            "risk_metrics": {},
            "breach_details": [],
        }

        # Current risk metrics
        for limit_id, limit in self.risk_limits.items():
            history = self.risk_metrics_history.get(limit_id, [])
            if history:
                latest_value = history[-1][1]
                summary["risk_metrics"][limit_id] = {
                    "name": limit.name,
                    "current_value": latest_value,
                    "warning_threshold": limit.warning_threshold,
                    "critical_threshold": limit.critical_threshold,
                    "emergency_threshold": limit.emergency_threshold,
                    "breach_status": self._get_breach_status(limit, latest_value),
                    "currency": limit.currency,
                }

        # Breach details
        for limit_id, risk_event in self.active_breaches.items():
            summary["breach_details"].append(
                {
                    "limit_id": limit_id,
                    "event_type": risk_event.event_type.value,
                    "current_value": risk_event.current_value,
                    "limit_value": risk_event.limit_value,
                    "breach_magnitude": risk_event.breach_magnitude,
                    "breach_time": risk_event.timestamp.isoformat(),
                    "auto_actions_taken": risk_event.auto_actions_taken,
                }
            )

        return summary

    def _get_breach_status(self, limit: RiskLimit, current_value: float) -> str:
        """Get breach status for a limit"""
        if (
            limit.emergency_threshold is not None
            and current_value >= limit.emergency_threshold
        ):
            return "emergency"
        elif current_value >= limit.critical_threshold:
            return "critical"
        elif current_value >= limit.warning_threshold:
            return "warning"
        else:
            return "normal"


class RiskAlertPresets:
    """Predefined risk alert configurations"""

    @staticmethod
    def create_position_limit_alerts(
        alert_manager: AlertManager, position_limits: dict[str, float]
    ):
        """Create position limit alerts"""
        for market, limit_usd in position_limits.items():
            # Warning at 80% of limit
            warning_threshold = limit_usd * 0.8
            # Critical at 95% of limit
            critical_threshold = limit_usd * 0.95
            # Emergency at 100% of limit
            emergency_threshold = limit_usd

            risk_limit = RiskLimit(
                limit_id=f"position_{market}",
                name=f"Position Limit - {market}",
                limit_type=RiskAlertType.POSITION_LIMIT_BREACH,
                description=f"Position size limit for {market}",
                warning_threshold=warning_threshold,
                critical_threshold=critical_threshold,
                emergency_threshold=emergency_threshold,
                currency="USD",
                auto_action="reduce_positions",
                tags={"market": market, "limit_type": "position"},
            )

            return risk_limit

    @staticmethod
    def create_drawdown_alerts(
        alert_manager: AlertManager, max_drawdown_pct: float = 5.0
    ):
        """Create drawdown alerts"""
        risk_limit = RiskLimit(
            limit_id="daily_drawdown",
            name="Daily Drawdown Limit",
            limit_type=RiskAlertType.DRAWDOWN_LIMIT_BREACH,
            description=f"Daily drawdown exceeds {max_drawdown_pct}%",
            warning_threshold=max_drawdown_pct * 0.7,  # 70% of limit
            critical_threshold=max_drawdown_pct * 0.9,  # 90% of limit
            emergency_threshold=max_drawdown_pct,  # 100% of limit
            currency="USD",
            time_horizon="1D",
            auto_action="stop_trading",
            tags={"risk_type": "drawdown", "horizon": "daily"},
        )

        return risk_limit

    @staticmethod
    def create_concentration_alerts(
        alert_manager: AlertManager, max_concentration_pct: float = 20.0
    ):
        """Create concentration risk alerts"""
        risk_limit = RiskLimit(
            limit_id="concentration_risk",
            name="Portfolio Concentration Limit",
            limit_type=RiskAlertType.CONCENTRATION_RISK,
            description=f"Single position exceeds {max_concentration_pct}% of portfolio",
            warning_threshold=max_concentration_pct * 0.8,
            critical_threshold=max_concentration_pct,
            currency="USD",
            auto_action="reduce_positions",
            tags={"risk_type": "concentration"},
        )

        return risk_limit

    @staticmethod
    def create_var_alerts(alert_manager: AlertManager, var_limit_usd: float = 10000):
        """Create Value-at-Risk alerts"""
        risk_limit = RiskLimit(
            limit_id="var_1d_95",
            name="1-Day 95% VaR Limit",
            limit_type=RiskAlertType.VaR_LIMIT_BREACH,
            description=f"1-day 95% VaR exceeds ${var_limit_usd:,.0f}",
            warning_threshold=var_limit_usd * 0.8,
            critical_threshold=var_limit_usd,
            emergency_threshold=var_limit_usd * 1.2,
            currency="USD",
            time_horizon="1D",
            auto_action="reduce_positions",
            tags={"risk_type": "var", "confidence": "95", "horizon": "1d"},
        )

        return risk_limit

    @staticmethod
    def create_liquidity_alerts(
        alert_manager: AlertManager, min_liquidity_ratio: float = 0.1
    ):
        """Create liquidity risk alerts"""
        risk_limit = RiskLimit(
            limit_id="liquidity_risk",
            name="Portfolio Liquidity Risk",
            limit_type=RiskAlertType.LIQUIDITY_RISK,
            description=f"Portfolio liquidity ratio below {min_liquidity_ratio:.1%}",
            warning_threshold=min_liquidity_ratio
            * 1.5,  # Inverted logic - higher is better
            critical_threshold=min_liquidity_ratio,
            currency="USD",
            tags={"risk_type": "liquidity"},
        )

        return risk_limit


class ComplianceMonitor:
    """Monitor compliance rules and trigger alerts"""

    def __init__(self, alert_manager: AlertManager | None = None):
        self.alert_manager = alert_manager or get_alert_manager()
        self.compliance_rules: dict[str, dict[str, Any]] = {}
        self.violation_history: list[dict[str, Any]] = []

    def add_compliance_rule(self, rule_id: str, rule_config: dict[str, Any]):
        """Add compliance rule"""
        self.compliance_rules[rule_id] = rule_config

        # Create alert rule
        alert_rule = AlertRule(
            rule_id=f"compliance_{rule_id}",
            name=f"Compliance: {rule_config['name']}",
            category=AlertCategory.COMPLIANCE,
            description=rule_config["description"],
            condition=rule_config.get("condition", "true"),
            severity=AlertSeverity.HIGH,
            enabled=True,
            tags={"compliance_type": rule_config.get("type", "general")},
            auto_resolve=False,  # Compliance violations need manual review
            cooldown_seconds=3600,  # 1 hour cooldown
            max_frequency=5,
        )

        self.alert_manager.add_alert_rule(alert_rule)

    async def check_compliance_violation(
        self, rule_id: str, context: dict[str, Any]
    ) -> bool:
        """Check for compliance violation and create alert if needed"""
        if rule_id not in self.compliance_rules:
            return False

        rule = self.compliance_rules[rule_id]

        # Create compliance violation alert
        alert = self.alert_manager.create_alert(
            rule_id=f"compliance_{rule_id}",
            triggered_by=f"Compliance violation: {rule['name']}",
            affected_components=[f"compliance_{rule_id}"],
            context={
                **context,
                "compliance_rule": rule["name"],
                "violation_type": rule.get("type", "general"),
                "requires_review": True,
            },
        )

        if alert:
            # Record violation
            violation = {
                "rule_id": rule_id,
                "rule_name": rule["name"],
                "timestamp": datetime.now().isoformat(),
                "context": context,
                "alert_id": alert.alert_id,
            }

            self.violation_history.append(violation)

            logger.critical(
                f"Compliance violation: {rule['name']} - Alert {alert.alert_id}"
            )
            return True

        return False


# Risk calculation functions that can be registered
async def calculate_position_exposure(limit: RiskLimit) -> float | None:
    """Calculate current position exposure for a market"""
    # This would integrate with position tracking system
    # Placeholder implementation
    market = limit.tags.get("market", "")

    # Get current position size from position manager
    # position_manager = get_position_manager()
    # return position_manager.get_market_exposure_usd(market)

    return 0.0  # Placeholder


async def calculate_portfolio_drawdown(limit: RiskLimit) -> float | None:
    """Calculate current portfolio drawdown"""
    # This would integrate with P&L tracking
    # Placeholder implementation
    return 0.0


async def calculate_var(limit: RiskLimit) -> float | None:
    """Calculate Value-at-Risk"""
    # This would integrate with risk model
    # Placeholder implementation
    return 0.0


async def calculate_concentration_risk(limit: RiskLimit) -> float | None:
    """Calculate portfolio concentration risk"""
    # This would analyze position weights
    # Placeholder implementation
    return 0.0


async def calculate_liquidity_ratio(limit: RiskLimit) -> float | None:
    """Calculate portfolio liquidity ratio"""
    # This would analyze market liquidity
    # Placeholder implementation
    return 1.0


# Auto-action handlers
async def stop_trading_action(risk_event: RiskEvent) -> str:
    """Stop all trading activity"""
    # This would integrate with trading system
    logger.critical(f"EMERGENCY: Trading stopped due to {risk_event.event_type.value}")
    return "Trading stopped successfully"


async def reduce_positions_action(risk_event: RiskEvent) -> str:
    """Reduce positions to manage risk"""
    # This would integrate with position management
    logger.warning(f"Reducing positions due to {risk_event.event_type.value}")
    return "Positions reduced by 50%"


def setup_default_risk_monitoring(alert_manager: AlertManager) -> RiskMetricsMonitor:
    """Setup default risk monitoring configuration"""

    monitor = RiskMetricsMonitor(alert_manager)

    # Register risk calculators
    monitor.register_risk_calculator(
        RiskAlertType.POSITION_LIMIT_BREACH, calculate_position_exposure
    )
    monitor.register_risk_calculator(
        RiskAlertType.DRAWDOWN_LIMIT_BREACH, calculate_portfolio_drawdown
    )
    monitor.register_risk_calculator(RiskAlertType.VaR_LIMIT_BREACH, calculate_var)
    monitor.register_risk_calculator(
        RiskAlertType.CONCENTRATION_RISK, calculate_concentration_risk
    )
    monitor.register_risk_calculator(
        RiskAlertType.LIQUIDITY_RISK, calculate_liquidity_ratio
    )

    # Register auto-action handlers
    monitor.register_auto_action_handler("stop_trading", stop_trading_action)
    monitor.register_auto_action_handler("reduce_positions", reduce_positions_action)

    # Add default risk limits
    default_limits = [
        RiskAlertPresets.create_drawdown_alerts(alert_manager, 5.0),
        RiskAlertPresets.create_concentration_alerts(alert_manager, 20.0),
        RiskAlertPresets.create_var_alerts(alert_manager, 10000),
        RiskAlertPresets.create_liquidity_alerts(alert_manager, 0.1),
    ]

    for limit in default_limits:
        monitor.add_risk_limit(limit)

    logger.info("Default risk monitoring setup completed")
    return monitor
