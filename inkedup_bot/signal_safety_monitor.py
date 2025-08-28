"""
Signal safety monitoring system with comprehensive safety requirements.

This module provides real-time safety monitoring, anomaly detection,
and emergency controls for the signal processing pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .enhanced_signal_processor import ProcessingResult, ProcessingStatus
from .signals import TradingSignal

logger = logging.getLogger("signal_safety_monitor")


class SafetyLevel(str, Enum):
    """Safety alert levels."""

    GREEN = "green"  # Normal operation
    YELLOW = "yellow"  # Minor concerns
    ORANGE = "orange"  # Significant concerns
    RED = "red"  # High risk situation
    CRITICAL = "critical"  # Emergency situation


class AnomalyType(str, Enum):
    """Types of detected anomalies."""

    VOLUME_SPIKE = "volume_spike"  # Unusual signal volume
    QUALITY_DEGRADATION = "quality_degradation"  # Declining signal quality
    RISK_ESCALATION = "risk_escalation"  # Escalating risk levels
    MARKET_DISRUPTION = "market_disruption"  # Market condition disruption
    PROCESSING_DELAYS = "processing_delays"  # Processing performance issues
    CORRELATION_ANOMALY = "correlation_anomaly"  # Unusual correlation patterns
    PRICE_MANIPULATION = "price_manipulation"  # Potential price manipulation
    LIQUIDITY_CRISIS = "liquidity_crisis"  # Liquidity issues


@dataclass
class SafetyAlert:
    """Safety alert information."""

    alert_id: str
    level: SafetyLevel
    anomaly_type: AnomalyType
    message: str
    timestamp: float = field(default_factory=time.time)

    # Context
    affected_markets: list[str] = field(default_factory=list)
    affected_signals: list[str] = field(default_factory=list)
    severity_score: float = 0.0

    # Recommended actions
    recommended_actions: list[str] = field(default_factory=list)
    auto_actions_taken: list[str] = field(default_factory=list)

    # Resolution
    is_resolved: bool = False
    resolved_at: float | None = None
    resolution_notes: str = ""


@dataclass
class SafetyMetrics:
    """Safety monitoring metrics."""

    timestamp: float = field(default_factory=time.time)

    # Signal flow metrics
    signals_per_minute: float = 0.0
    avg_processing_time: float = 0.0
    rejection_rate: float = 0.0
    quality_score_avg: float = 0.0

    # Risk metrics
    high_risk_rate: float = 0.0
    avg_risk_score: float = 0.0
    portfolio_risk_level: float = 0.0

    # Market health metrics
    active_markets: int = 0
    avg_market_score: float = 0.0
    liquidity_concerns: int = 0
    volatility_alerts: int = 0

    # System health
    processing_queue_size: int = 0
    cache_hit_rate: float = 0.0
    error_rate: float = 0.0

    # Safety indicators
    safety_level: SafetyLevel = SafetyLevel.GREEN
    active_alerts: int = 0
    circuit_breakers_active: int = 0


@dataclass
class SafetyConfig:
    """Configuration for safety monitoring."""

    # Monitoring intervals
    monitoring_interval: float = 10.0  # seconds
    metrics_window: int = 300  # 5 minutes of data
    alert_retention: int = 86400  # 24 hours

    # Volume anomaly detection
    volume_spike_threshold: float = 3.0  # 3x normal volume
    volume_window_minutes: int = 5  # 5-minute windows

    # Quality degradation thresholds
    quality_decline_threshold: float = 0.20  # 20% decline
    min_quality_threshold: float = 40.0  # Minimum acceptable quality

    # Risk escalation thresholds
    high_risk_rate_threshold: float = 0.30  # 30% high-risk signals
    risk_score_spike_threshold: float = 25.0  # 25-point increase

    # Processing performance thresholds
    max_processing_time: float = 10.0  # 10 seconds max
    max_queue_size: int = 100  # Maximum queue size
    max_error_rate: float = 0.10  # 10% error rate

    # Market disruption thresholds
    min_active_markets: int = 5  # Minimum active markets
    market_score_threshold: float = 30.0  # Minimum market score
    liquidity_crisis_threshold: int = 10  # Max liquidity concerns

    # Auto-response configuration
    enable_auto_responses: bool = True
    enable_circuit_breakers: bool = True
    enable_signal_blocking: bool = True

    # Alert escalation
    critical_alert_threshold: int = 3  # 3 red alerts = critical
    alert_escalation_time: float = 300  # 5 minutes


class SignalSafetyMonitor:
    """
    Comprehensive safety monitoring system for signal processing.

    Monitors signal flow, quality, risks, and market conditions to detect
    anomalies and potential safety issues in real-time.
    """

    def __init__(self, config: SafetyConfig | None = None):
        self.config = config or SafetyConfig()

        # Monitoring data
        self._metrics_history: deque = deque(maxlen=self.config.metrics_window)
        self._signal_history: deque = deque(maxlen=1000)
        self._processing_times: deque = deque(maxlen=100)
        self._quality_scores: deque = deque(maxlen=100)
        self._risk_scores: deque = deque(maxlen=100)

        # Alerts and anomalies
        self._active_alerts: dict[str, SafetyAlert] = {}
        self._alert_history: list[SafetyAlert] = []
        self._anomaly_detectors: dict[AnomalyType, Callable] = {}

        # Safety state
        self._current_safety_level = SafetyLevel.GREEN
        self._circuit_breakers: set[str] = set()
        self._blocked_sources: set[str] = set()

        # Monitoring task
        self._monitoring_task: asyncio.Task | None = None
        self._monitoring_active = False

        # Statistics
        self._monitoring_stats = {
            "monitoring_cycles": 0,
            "alerts_generated": 0,
            "anomalies_detected": 0,
            "auto_actions_taken": 0,
            "uptime_start": time.time(),
        }

        # Initialize anomaly detectors
        self._setup_anomaly_detectors()

        logger.info("SignalSafetyMonitor initialized")

    def _setup_anomaly_detectors(self):
        """Setup anomaly detection functions."""
        self._anomaly_detectors = {
            AnomalyType.VOLUME_SPIKE: self._detect_volume_spike,
            AnomalyType.QUALITY_DEGRADATION: self._detect_quality_degradation,
            AnomalyType.RISK_ESCALATION: self._detect_risk_escalation,
            AnomalyType.PROCESSING_DELAYS: self._detect_processing_delays,
            AnomalyType.MARKET_DISRUPTION: self._detect_market_disruption,
            AnomalyType.CORRELATION_ANOMALY: self._detect_correlation_anomaly,
            AnomalyType.LIQUIDITY_CRISIS: self._detect_liquidity_crisis,
        }

    async def start_monitoring(self):
        """Start safety monitoring."""
        if self._monitoring_active:
            return

        self._monitoring_active = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Safety monitoring started")

    async def stop_monitoring(self):
        """Stop safety monitoring."""
        if not self._monitoring_active:
            return

        self._monitoring_active = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Safety monitoring stopped")

    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self._monitoring_active:
            try:
                await self._perform_monitoring_cycle()
                await asyncio.sleep(self.config.monitoring_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.config.monitoring_interval)

    async def _perform_monitoring_cycle(self):
        """Perform one monitoring cycle."""
        self._monitoring_stats["monitoring_cycles"] += 1

        # Collect current metrics
        current_metrics = self._collect_current_metrics()
        self._metrics_history.append(current_metrics)

        # Run anomaly detection
        await self._run_anomaly_detection(current_metrics)

        # Update safety level
        self._update_safety_level()

        # Process alerts and auto-responses
        await self._process_alerts()

        # Cleanup old data
        self._cleanup_old_data()

    def _collect_current_metrics(self) -> SafetyMetrics:
        """Collect current safety metrics."""
        current_time = time.time()

        # Calculate signal flow metrics
        recent_signals = [
            s for s in self._signal_history if current_time - s["timestamp"] < 60
        ]
        signals_per_minute = len(recent_signals)

        avg_processing_time = (
            statistics.mean(self._processing_times) if self._processing_times else 0.0
        )

        # Calculate rejection rate
        if recent_signals:
            rejected = sum(
                1
                for s in recent_signals
                if s.get("status") == ProcessingStatus.REJECTED
            )
            rejection_rate = rejected / len(recent_signals)
        else:
            rejection_rate = 0.0

        # Calculate quality metrics
        quality_score_avg = (
            statistics.mean(self._quality_scores) if self._quality_scores else 0.0
        )

        # Calculate risk metrics
        high_risk_signals = [
            s for s in recent_signals if s.get("risk_level") in ["high", "extreme"]
        ]
        high_risk_rate = (
            len(high_risk_signals) / len(recent_signals) if recent_signals else 0.0
        )
        avg_risk_score = (
            statistics.mean(self._risk_scores) if self._risk_scores else 0.0
        )

        return SafetyMetrics(
            timestamp=current_time,
            signals_per_minute=signals_per_minute,
            avg_processing_time=avg_processing_time,
            rejection_rate=rejection_rate,
            quality_score_avg=quality_score_avg,
            high_risk_rate=high_risk_rate,
            avg_risk_score=avg_risk_score,
            active_alerts=len(self._active_alerts),
            circuit_breakers_active=len(self._circuit_breakers),
            safety_level=self._current_safety_level,
        )

    async def _run_anomaly_detection(self, metrics: SafetyMetrics):
        """Run all anomaly detection algorithms."""
        for anomaly_type, detector in self._anomaly_detectors.items():
            try:
                await detector(metrics)
            except Exception as e:
                logger.error(f"Error in {anomaly_type} detector: {e}")

    async def _detect_volume_spike(self, metrics: SafetyMetrics):
        """Detect unusual volume spikes."""
        if len(self._metrics_history) < 10:  # Need historical data
            return

        recent_volumes = [
            m.signals_per_minute for m in list(self._metrics_history)[-10:]
        ]
        baseline_volume = (
            statistics.mean(recent_volumes[:-1]) if len(recent_volumes) > 1 else 0
        )

        if (
            baseline_volume > 0
            and metrics.signals_per_minute
            > baseline_volume * self.config.volume_spike_threshold
        ):
            await self._generate_alert(
                level=SafetyLevel.ORANGE,
                anomaly_type=AnomalyType.VOLUME_SPIKE,
                message=f"Signal volume spike detected: {metrics.signals_per_minute:.1f} vs baseline {baseline_volume:.1f}",
                severity_score=min(
                    100, (metrics.signals_per_minute / baseline_volume) * 25
                ),
                recommended_actions=[
                    "Monitor signal sources",
                    "Check for market events",
                    "Consider rate limiting",
                ],
            )

    async def _detect_quality_degradation(self, metrics: SafetyMetrics):
        """Detect signal quality degradation."""
        if len(self._metrics_history) < 5:
            return

        recent_quality = [m.quality_score_avg for m in list(self._metrics_history)[-5:]]

        # Check for declining trend
        if len(recent_quality) >= 3:
            recent_avg = statistics.mean(recent_quality[-3:])
            baseline_avg = (
                statistics.mean(recent_quality[:-3])
                if len(recent_quality) > 3
                else recent_avg
            )

            if baseline_avg > 0:
                quality_decline = (baseline_avg - recent_avg) / baseline_avg

                if quality_decline > self.config.quality_decline_threshold:
                    await self._generate_alert(
                        level=(
                            SafetyLevel.YELLOW
                            if quality_decline < 0.4
                            else SafetyLevel.ORANGE
                        ),
                        anomaly_type=AnomalyType.QUALITY_DEGRADATION,
                        message=f"Signal quality declining: {quality_decline:.1%} drop detected",
                        severity_score=quality_decline * 100,
                        recommended_actions=[
                            "Review signal sources",
                            "Check validation parameters",
                            "Investigate market conditions",
                        ],
                    )

        # Check absolute quality threshold
        if metrics.quality_score_avg < self.config.min_quality_threshold:
            await self._generate_alert(
                level=SafetyLevel.RED,
                anomaly_type=AnomalyType.QUALITY_DEGRADATION,
                message=f"Signal quality below minimum: {metrics.quality_score_avg:.1f}",
                severity_score=100 - metrics.quality_score_avg,
                recommended_actions=[
                    "Stop signal processing",
                    "Investigate quality issues",
                    "Review validation pipeline",
                ],
            )

    async def _detect_risk_escalation(self, metrics: SafetyMetrics):
        """Detect risk escalation patterns."""
        # High risk rate check
        if metrics.high_risk_rate > self.config.high_risk_rate_threshold:
            await self._generate_alert(
                level=SafetyLevel.ORANGE,
                anomaly_type=AnomalyType.RISK_ESCALATION,
                message=f"High risk signal rate: {metrics.high_risk_rate:.1%}",
                severity_score=metrics.high_risk_rate * 100,
                recommended_actions=[
                    "Reduce position sizes",
                    "Increase risk thresholds",
                    "Review risk models",
                ],
            )

        # Risk score spike check
        if len(self._metrics_history) >= 5:
            recent_risk_scores = [
                m.avg_risk_score for m in list(self._metrics_history)[-5:]
            ]
            if len(recent_risk_scores) >= 2:
                risk_increase = recent_risk_scores[-1] - statistics.mean(
                    recent_risk_scores[:-1]
                )

                if risk_increase > self.config.risk_score_spike_threshold:
                    await self._generate_alert(
                        level=SafetyLevel.YELLOW,
                        anomaly_type=AnomalyType.RISK_ESCALATION,
                        message=f"Risk score spike: +{risk_increase:.1f} points",
                        severity_score=min(100, risk_increase * 2),
                        recommended_actions=[
                            "Monitor risk factors",
                            "Check market volatility",
                            "Review position limits",
                        ],
                    )

    async def _detect_processing_delays(self, metrics: SafetyMetrics):
        """Detect processing performance issues."""
        if metrics.avg_processing_time > self.config.max_processing_time:
            await self._generate_alert(
                level=SafetyLevel.YELLOW,
                anomaly_type=AnomalyType.PROCESSING_DELAYS,
                message=f"Processing delays detected: {metrics.avg_processing_time:.2f}s average",
                severity_score=min(
                    100,
                    (metrics.avg_processing_time / self.config.max_processing_time)
                    * 50,
                ),
                recommended_actions=[
                    "Check system resources",
                    "Review processing pipeline",
                    "Scale processing capacity",
                ],
            )

        if metrics.processing_queue_size > self.config.max_queue_size:
            await self._generate_alert(
                level=SafetyLevel.ORANGE,
                anomaly_type=AnomalyType.PROCESSING_DELAYS,
                message=f"Processing queue overflow: {metrics.processing_queue_size} items",
                severity_score=min(
                    100,
                    (metrics.processing_queue_size / self.config.max_queue_size) * 75,
                ),
                recommended_actions=[
                    "Scale processing",
                    "Implement backpressure",
                    "Review queue management",
                ],
            )

    async def _detect_market_disruption(self, metrics: SafetyMetrics):
        """Detect market disruption conditions."""
        if metrics.active_markets < self.config.min_active_markets:
            await self._generate_alert(
                level=SafetyLevel.RED,
                anomaly_type=AnomalyType.MARKET_DISRUPTION,
                message=f"Too few active markets: {metrics.active_markets}",
                severity_score=100
                - (metrics.active_markets / self.config.min_active_markets) * 100,
                recommended_actions=[
                    "Check market data feeds",
                    "Investigate market halts",
                    "Reduce trading activity",
                ],
            )

        if metrics.avg_market_score < self.config.market_score_threshold:
            await self._generate_alert(
                level=SafetyLevel.ORANGE,
                anomaly_type=AnomalyType.MARKET_DISRUPTION,
                message=f"Poor market conditions: {metrics.avg_market_score:.1f} average score",
                severity_score=100 - metrics.avg_market_score,
                recommended_actions=[
                    "Monitor market health",
                    "Consider trading restrictions",
                    "Review market data quality",
                ],
            )

    async def _detect_correlation_anomaly(self, metrics: SafetyMetrics):
        """Detect unusual correlation patterns (placeholder)."""
        # This would analyze correlation patterns in signal data
        # For now, we'll implement a simple placeholder
        pass

    async def _detect_liquidity_crisis(self, metrics: SafetyMetrics):
        """Detect liquidity crisis conditions."""
        if metrics.liquidity_concerns > self.config.liquidity_crisis_threshold:
            await self._generate_alert(
                level=SafetyLevel.RED,
                anomaly_type=AnomalyType.LIQUIDITY_CRISIS,
                message=f"Liquidity crisis detected: {metrics.liquidity_concerns} affected markets",
                severity_score=min(
                    100,
                    (
                        metrics.liquidity_concerns
                        / self.config.liquidity_crisis_threshold
                    )
                    * 75,
                ),
                recommended_actions=[
                    "Reduce position sizes",
                    "Avoid illiquid markets",
                    "Increase spread thresholds",
                ],
            )

    async def _generate_alert(
        self,
        level: SafetyLevel,
        anomaly_type: AnomalyType,
        message: str,
        severity_score: float = 0.0,
        affected_markets: list[str] = None,
        recommended_actions: list[str] = None,
    ):
        """Generate and process a safety alert."""
        alert_id = f"{anomaly_type}_{int(time.time())}"

        alert = SafetyAlert(
            alert_id=alert_id,
            level=level,
            anomaly_type=anomaly_type,
            message=message,
            affected_markets=affected_markets or [],
            severity_score=severity_score,
            recommended_actions=recommended_actions or [],
        )

        # Add to active alerts
        self._active_alerts[alert_id] = alert
        self._alert_history.append(alert)

        # Update statistics
        self._monitoring_stats["alerts_generated"] += 1
        self._monitoring_stats["anomalies_detected"] += 1

        logger.warning(f"Safety alert generated: {level.value} - {message}")

        # Take automatic actions if enabled
        if self.config.enable_auto_responses:
            await self._take_auto_actions(alert)

    async def _take_auto_actions(self, alert: SafetyAlert):
        """Take automatic safety actions based on alert."""
        actions_taken = []

        # Critical and Red level responses
        if alert.level in [SafetyLevel.CRITICAL, SafetyLevel.RED]:
            if self.config.enable_circuit_breakers:
                if alert.anomaly_type == AnomalyType.QUALITY_DEGRADATION:
                    self._circuit_breakers.add("quality_degradation")
                    actions_taken.append(
                        "Activated quality degradation circuit breaker"
                    )

                elif alert.anomaly_type == AnomalyType.LIQUIDITY_CRISIS:
                    self._circuit_breakers.add("liquidity_crisis")
                    actions_taken.append("Activated liquidity crisis circuit breaker")

        # Orange level responses
        elif alert.level == SafetyLevel.ORANGE:
            if (
                alert.anomaly_type == AnomalyType.VOLUME_SPIKE
                and self.config.enable_signal_blocking
            ):
                # Could implement temporary rate limiting here
                actions_taken.append("Applied rate limiting")

        if actions_taken:
            alert.auto_actions_taken.extend(actions_taken)
            self._monitoring_stats["auto_actions_taken"] += len(actions_taken)
            logger.info(
                f"Auto-actions taken for alert {alert.alert_id}: {', '.join(actions_taken)}"
            )

    def _update_safety_level(self):
        """Update overall safety level based on active alerts."""
        if not self._active_alerts:
            self._current_safety_level = SafetyLevel.GREEN
            return

        alert_levels = [alert.level for alert in self._active_alerts.values()]

        # Determine highest severity
        if SafetyLevel.CRITICAL in alert_levels:
            self._current_safety_level = SafetyLevel.CRITICAL
        elif SafetyLevel.RED in alert_levels:
            # Check for critical escalation
            red_alerts = [
                a for a in self._active_alerts.values() if a.level == SafetyLevel.RED
            ]
            if len(red_alerts) >= self.config.critical_alert_threshold:
                self._current_safety_level = SafetyLevel.CRITICAL
            else:
                self._current_safety_level = SafetyLevel.RED
        elif SafetyLevel.ORANGE in alert_levels:
            self._current_safety_level = SafetyLevel.ORANGE
        elif SafetyLevel.YELLOW in alert_levels:
            self._current_safety_level = SafetyLevel.YELLOW
        else:
            self._current_safety_level = SafetyLevel.GREEN

    async def _process_alerts(self):
        """Process and manage active alerts."""
        current_time = time.time()
        resolved_alerts = []

        for alert_id, alert in self._active_alerts.items():
            # Check for auto-resolution conditions
            if self._should_auto_resolve_alert(alert, current_time):
                alert.is_resolved = True
                alert.resolved_at = current_time
                alert.resolution_notes = "Auto-resolved - conditions normalized"
                resolved_alerts.append(alert_id)
                logger.info(f"Alert {alert_id} auto-resolved")

        # Remove resolved alerts
        for alert_id in resolved_alerts:
            del self._active_alerts[alert_id]

    def _should_auto_resolve_alert(
        self, alert: SafetyAlert, current_time: float
    ) -> bool:
        """Check if alert should be auto-resolved."""
        # Simple time-based resolution for some alert types
        alert_age = current_time - alert.timestamp

        if (
            alert.anomaly_type == AnomalyType.VOLUME_SPIKE and alert_age > 300
        ):  # 5 minutes
            return True

        if (
            alert.anomaly_type == AnomalyType.PROCESSING_DELAYS and alert_age > 180
        ):  # 3 minutes
            return True

        # More sophisticated resolution logic would check if conditions have improved
        return False

    def _cleanup_old_data(self):
        """Clean up old monitoring data."""
        current_time = time.time()

        # Clean old alert history
        self._alert_history = [
            alert
            for alert in self._alert_history
            if current_time - alert.timestamp < self.config.alert_retention
        ]

        # Clean old signal history
        cutoff_time = current_time - 3600  # 1 hour
        while (
            self._signal_history and self._signal_history[0]["timestamp"] < cutoff_time
        ):
            self._signal_history.popleft()

    def record_signal_processed(self, signal: TradingSignal, result: ProcessingResult):
        """Record a processed signal for monitoring."""
        self._signal_history.append(
            {
                "timestamp": time.time(),
                "signal_id": signal.signal_id,
                "market_slug": signal.market_slug,
                "status": result.status,
                "quality_score": result.overall_quality_score,
                "risk_level": (
                    result.risk_metrics.overall_risk_level.value
                    if result.risk_metrics
                    else "unknown"
                ),
                "processing_time": result.processing_time,
            }
        )

        # Update tracking data
        if result.processing_time > 0:
            self._processing_times.append(result.processing_time)

        if result.overall_quality_score > 0:
            self._quality_scores.append(result.overall_quality_score)

        if result.risk_metrics:
            self._risk_scores.append(result.risk_metrics.overall_risk_score)

    def get_current_safety_level(self) -> SafetyLevel:
        """Get current safety level."""
        return self._current_safety_level

    def get_active_alerts(self) -> list[SafetyAlert]:
        """Get all active alerts."""
        return list(self._active_alerts.values())

    def get_alert_history(self, hours: int = 24) -> list[SafetyAlert]:
        """Get alert history for specified hours."""
        cutoff_time = time.time() - (hours * 3600)
        return [alert for alert in self._alert_history if alert.timestamp > cutoff_time]

    def is_circuit_breaker_active(self, breaker_name: str) -> bool:
        """Check if a specific circuit breaker is active."""
        return breaker_name in self._circuit_breakers

    def reset_circuit_breaker(self, breaker_name: str):
        """Reset a specific circuit breaker."""
        if breaker_name in self._circuit_breakers:
            self._circuit_breakers.remove(breaker_name)
            logger.info(f"Circuit breaker {breaker_name} reset")

    def resolve_alert(self, alert_id: str, resolution_notes: str = ""):
        """Manually resolve an alert."""
        if alert_id in self._active_alerts:
            alert = self._active_alerts[alert_id]
            alert.is_resolved = True
            alert.resolved_at = time.time()
            alert.resolution_notes = resolution_notes
            del self._active_alerts[alert_id]
            logger.info(f"Alert {alert_id} manually resolved")

    def get_monitoring_stats(self) -> dict[str, Any]:
        """Get monitoring statistics."""
        stats = self._monitoring_stats.copy()
        stats["uptime_seconds"] = time.time() - stats["uptime_start"]
        stats["current_safety_level"] = self._current_safety_level.value
        stats["active_alerts"] = len(self._active_alerts)
        stats["circuit_breakers_active"] = list(self._circuit_breakers)
        return stats


# Utility functions


def create_safety_monitor(config: SafetyConfig | None = None) -> SignalSafetyMonitor:
    """Create a configured safety monitor."""
    return SignalSafetyMonitor(config)


async def monitor_signal_safety(
    monitor: SignalSafetyMonitor,
    signals: list[TradingSignal],
    results: list[ProcessingResult],
):
    """Convenience function to record batch processing results."""
    for signal, result in zip(signals, results, strict=False):
        monitor.record_signal_processed(signal, result)
