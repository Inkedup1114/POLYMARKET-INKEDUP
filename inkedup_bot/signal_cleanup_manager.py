"""
Advanced signal cleanup manager with intelligent cleanup strategies and stale signal prevention.

This module provides sophisticated cleanup mechanisms to ensure old signals don't interfere
with current trading decisions while maintaining system performance and memory efficiency.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import psutil

from .enhanced_signal_manager import EnhancedSignalWrapper, SignalPriority
from .signal_manager import SignalStatus
from .signals import TradingSignal

logger = logging.getLogger("signal_cleanup_manager")


class CleanupStrategy(str, Enum):
    """Different cleanup strategies for different signal types."""

    IMMEDIATE = "immediate"  # Clean up immediately after expiration
    DELAYED = "delayed"  # Keep for analysis before cleaning
    ARCHIVAL = "archival"  # Archive for long-term analysis
    PRIORITY_BASED = "priority"  # Clean based on priority levels
    PERFORMANCE_BASED = "performance"  # Clean based on historical performance


class SignalInterferenceLevel(str, Enum):
    """Levels of signal interference risk."""

    NONE = "none"  # No interference risk
    LOW = "low"  # Minimal interference risk
    MODERATE = "moderate"  # Some interference risk
    HIGH = "high"  # High interference risk
    CRITICAL = "critical"  # Critical interference risk


@dataclass
class CleanupRule:
    """Rule defining when and how to clean up signals."""

    name: str
    description: str
    strategy: CleanupStrategy
    conditions: dict[str, Any]
    cleanup_delay: float = 0.0
    archive_before_cleanup: bool = False
    priority: int = 0


@dataclass
class SignalAnalytics:
    """Analytics data for signal behavior and interference tracking."""

    signal_id: str
    created_at: float
    last_accessed: float
    access_count: int = 0
    interference_score: float = 0.0
    market_impact_score: float = 0.0
    correlation_signals: set[str] = field(default_factory=set)
    blocking_signals: set[str] = field(default_factory=set)


@dataclass
class CleanupConfig:
    """Configuration for signal cleanup behavior."""

    # Basic cleanup settings
    cleanup_interval_seconds: float = 5.0
    batch_cleanup_size: int = 50
    max_cleanup_duration_seconds: float = 2.0

    # Memory management
    max_expired_signals_memory: int = 1000
    max_failed_signals_memory: int = 500
    max_analytics_history: int = 5000

    # Interference detection
    enable_interference_detection: bool = True
    interference_detection_window: float = 60.0  # seconds
    interference_correlation_threshold: float = 0.7

    # Performance optimization
    enable_batch_operations: bool = True
    enable_predictive_cleanup: bool = True
    cleanup_performance_tracking: bool = True

    # Cleanup strategies by signal type
    cleanup_strategies: dict[SignalPriority, CleanupStrategy] = field(
        default_factory=lambda: {
            SignalPriority.CRITICAL: CleanupStrategy.IMMEDIATE,
            SignalPriority.HIGH: CleanupStrategy.DELAYED,
            SignalPriority.NORMAL: CleanupStrategy.PRIORITY_BASED,
            SignalPriority.LOW: CleanupStrategy.ARCHIVAL,
        }
    )


class SignalCleanupManager:
    """
    Advanced signal cleanup manager with intelligent cleanup strategies.

    Features:
    - Intelligent cleanup timing based on signal characteristics
    - Interference detection and prevention
    - Performance-based cleanup decisions
    - Memory-efficient batch operations
    - Predictive cleanup for performance optimization
    - Comprehensive analytics and monitoring
    """

    def __init__(self, config: CleanupConfig | None = None):
        self.config = config or CleanupConfig()

        # Signal storage and tracking
        self._signals_analytics: dict[str, SignalAnalytics] = {}
        self._pending_cleanup: dict[str, float] = {}  # signal_id -> cleanup_time
        self._cleanup_archive: deque = deque(maxlen=self.config.max_analytics_history)

        # Interference tracking
        self._token_signal_map: dict[str, set[str]] = defaultdict(set)
        self._market_signal_map: dict[str, set[str]] = defaultdict(set)
        self._signal_correlations: dict[str, set[str]] = defaultdict(set)

        # Performance tracking
        self._cleanup_metrics = {
            "total_cleaned": 0,
            "interference_prevented": 0,
            "cleanup_time_avg": 0.0,
            "memory_saved": 0,
            "predictive_cleanups": 0,
            "batch_operations": 0,
        }

        # Background tasks
        self._cleanup_task: asyncio.Task | None = None
        self._interference_task: asyncio.Task | None = None
        self._running = False

        # Initialize cleanup rules
        self._cleanup_rules: list[CleanupRule] = []
        self._initialize_cleanup_rules()

        logger.info("SignalCleanupManager initialized")

    def _initialize_cleanup_rules(self):
        """Initialize default cleanup rules."""

        self._cleanup_rules = [
            # Immediate cleanup rules
            CleanupRule(
                name="critical_expired_immediate",
                description="Immediately clean expired critical signals",
                strategy=CleanupStrategy.IMMEDIATE,
                conditions={
                    "status": SignalStatus.EXPIRED,
                    "priority": SignalPriority.CRITICAL,
                },
                cleanup_delay=0.0,
                priority=1000,
            ),
            # Interference prevention rules
            CleanupRule(
                name="high_interference_cleanup",
                description="Clean signals causing high interference",
                strategy=CleanupStrategy.IMMEDIATE,
                conditions={"interference_level": SignalInterferenceLevel.HIGH},
                cleanup_delay=1.0,
                priority=900,
            ),
            # Memory pressure rules
            CleanupRule(
                name="memory_pressure_cleanup",
                description="Aggressive cleanup under memory pressure",
                strategy=CleanupStrategy.PRIORITY_BASED,
                conditions={"memory_pressure": True},
                cleanup_delay=2.0,
                priority=800,
            ),
            # Age-based cleanup rules
            CleanupRule(
                name="old_expired_cleanup",
                description="Clean old expired signals",
                strategy=CleanupStrategy.DELAYED,
                conditions={"status": SignalStatus.EXPIRED, "age_seconds": {"min": 30}},
                cleanup_delay=5.0,
                archive_before_cleanup=True,
                priority=700,
            ),
            # Failed signal cleanup
            CleanupRule(
                name="failed_signal_cleanup",
                description="Clean failed signals after analysis period",
                strategy=CleanupStrategy.ARCHIVAL,
                conditions={"status": SignalStatus.FAILED, "age_seconds": {"min": 60}},
                cleanup_delay=10.0,
                archive_before_cleanup=True,
                priority=600,
            ),
            # Performance-based cleanup
            CleanupRule(
                name="poor_performance_cleanup",
                description="Clean signals from poorly performing strategies",
                strategy=CleanupStrategy.PERFORMANCE_BASED,
                conditions={
                    "strategy_success_rate": {"max": 0.3},
                    "age_seconds": {"min": 20},
                },
                cleanup_delay=15.0,
                priority=500,
            ),
            # System load-based cleanup
            CleanupRule(
                name="high_load_cleanup",
                description="Aggressive cleanup during high system load",
                strategy=CleanupStrategy.IMMEDIATE,
                conditions={"system_load": {"min": 0.8}, "age_seconds": {"min": 5}},
                cleanup_delay=0.5,
                priority=900,
            ),
            # Memory pressure cleanup
            CleanupRule(
                name="memory_pressure_cleanup",
                description="Clean signals when memory usage is high",
                strategy=CleanupStrategy.IMMEDIATE,
                conditions={"memory_usage": {"min": 0.85}, "age_seconds": {"min": 3}},
                cleanup_delay=0.2,
                priority=950,
            ),
            # Default cleanup rule
            CleanupRule(
                name="general_cleanup",
                description="General cleanup for old signals",
                strategy=CleanupStrategy.DELAYED,
                conditions={"age_seconds": {"min": 300}},  # 5 minutes old
                cleanup_delay=30.0,
                archive_before_cleanup=True,
                priority=100,
            ),
        ]

        # Sort rules by priority (descending)
        self._cleanup_rules.sort(key=lambda r: r.priority, reverse=True)

    async def start(self):
        """Start the cleanup manager background tasks."""
        if self._running:
            logger.warning("SignalCleanupManager already running")
            return

        self._running = True
        logger.info("Starting SignalCleanupManager")

        # Start background tasks
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        if self.config.enable_interference_detection:
            self._interference_task = asyncio.create_task(
                self._interference_detection_loop()
            )

    async def stop(self):
        """Stop the cleanup manager and cleanup resources."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping SignalCleanupManager")

        # Cancel background tasks
        tasks = [self._cleanup_task, self._interference_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        logger.info("SignalCleanupManager stopped")

    def register_signal(
        self,
        signal_wrapper: EnhancedSignalWrapper,
        context: dict[str, Any] | None = None,
    ):
        """Register a signal for cleanup tracking."""
        signal_id = signal_wrapper.metadata.signal_id
        current_time = time.time()

        # Create analytics entry
        analytics = SignalAnalytics(
            signal_id=signal_id, created_at=current_time, last_accessed=current_time
        )

        self._signals_analytics[signal_id] = analytics

        # Update tracking maps
        token_id = signal_wrapper.signal.token_id
        market_slug = signal_wrapper.signal.market_slug

        self._token_signal_map[token_id].add(signal_id)
        self._market_signal_map[market_slug].add(signal_id)

        # Calculate initial interference score
        interference_score = self._calculate_interference_score(signal_wrapper)
        analytics.interference_score = interference_score

        logger.debug(f"Registered signal for cleanup tracking: {signal_id}")

    def unregister_signal(self, signal_id: str):
        """Unregister a signal from cleanup tracking."""
        if signal_id not in self._signals_analytics:
            return

        analytics = self._signals_analytics[signal_id]

        # Remove from tracking maps
        for token_signals in self._token_signal_map.values():
            token_signals.discard(signal_id)
        for market_signals in self._market_signal_map.values():
            market_signals.discard(signal_id)

        # Remove correlations
        for correlated_id in analytics.correlation_signals:
            self._signal_correlations[correlated_id].discard(signal_id)

        # Archive analytics before removal
        self._cleanup_archive.append(
            {
                "signal_id": signal_id,
                "cleanup_time": time.time(),
                "analytics": analytics,
                "reason": "manual_unregister",
            }
        )

        # Remove from tracking
        del self._signals_analytics[signal_id]
        self._pending_cleanup.pop(signal_id, None)

        self._cleanup_metrics["total_cleaned"] += 1

        logger.debug(f"Unregistered signal from cleanup tracking: {signal_id}")

    def signal_accessed(self, signal_id: str):
        """Record that a signal was accessed."""
        if signal_id in self._signals_analytics:
            analytics = self._signals_analytics[signal_id]
            analytics.last_accessed = time.time()
            analytics.access_count += 1

    def check_interference_risk(
        self, signal: TradingSignal, target_signals: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Check if a signal would interfere with existing signals.

        Returns detailed interference analysis.
        """
        if not self.config.enable_interference_detection:
            return {"interference_level": SignalInterferenceLevel.NONE, "details": []}

        token_id = signal.token_id
        market_slug = signal.market_slug
        current_time = time.time()

        # Get related signals
        if target_signals is None:
            related_signals = self._token_signal_map.get(
                token_id, set()
            ) | self._market_signal_map.get(market_slug, set())
        else:
            related_signals = set(target_signals)

        interference_details = []
        max_interference = SignalInterferenceLevel.NONE

        for related_id in related_signals:
            if related_id not in self._signals_analytics:
                continue

            analytics = self._signals_analytics[related_id]

            # Check timing interference
            time_diff = abs(current_time - analytics.created_at)
            if time_diff < self.config.interference_detection_window:
                interference_level = self._assess_signal_interference(
                    signal, related_id
                )

                if interference_level != SignalInterferenceLevel.NONE:
                    interference_details.append(
                        {
                            "signal_id": related_id,
                            "interference_level": interference_level,
                            "time_diff": time_diff,
                            "interference_score": analytics.interference_score,
                        }
                    )

                    # Update max interference level
                    if self._interference_level_value(
                        interference_level
                    ) > self._interference_level_value(max_interference):
                        max_interference = interference_level

        return {
            "interference_level": max_interference,
            "details": interference_details,
            "related_signals_count": len(related_signals),
        }

    def _assess_signal_interference(
        self, signal: TradingSignal, related_signal_id: str
    ) -> SignalInterferenceLevel:
        """Enhanced assessment of interference between two signals with multiple factors."""
        if related_signal_id not in self._signals_analytics:
            return SignalInterferenceLevel.NONE

        analytics = self._signals_analytics[related_signal_id]

        # Initialize interference factors
        interference_factors = {
            "token_conflict": 0.0,
            "market_conflict": 0.0,
            "side_conflict": 0.0,
            "price_conflict": 0.0,
            "timing_conflict": 0.0,
            "strategy_conflict": 0.0,
            "volume_conflict": 0.0,
        }

        # Token-level interference (highest priority)
        if analytics.signal_id in self._token_signal_map.get(signal.token_id, set()):
            interference_factors["token_conflict"] = 0.8

            # Check for opposite sides (critical interference)
            if hasattr(signal, "side") and hasattr(analytics, "side"):
                if signal.side != analytics.side:
                    interference_factors["side_conflict"] = 0.9

            # Price competition assessment
            if hasattr(signal, "price") and hasattr(analytics, "price"):
                price_diff = (
                    abs(signal.price - analytics.price) / signal.price
                    if signal.price > 0
                    else 0
                )
                if price_diff < 0.01:  # Prices within 1%
                    interference_factors["price_conflict"] = 0.7
                elif price_diff < 0.05:  # Prices within 5%
                    interference_factors["price_conflict"] = 0.4

            # Volume competition
            if hasattr(signal, "size") and hasattr(analytics, "size"):
                combined_volume = signal.size + analytics.size
                market_capacity = self._estimate_market_capacity(signal.token_id)
                if market_capacity > 0 and combined_volume > market_capacity * 0.8:
                    interference_factors["volume_conflict"] = 0.6

        # Market-level interference
        elif analytics.signal_id in self._market_signal_map.get(
            signal.market_slug, set()
        ):
            interference_factors["market_conflict"] = 0.4

        # Timing interference (signals too close in time)
        time_diff = abs(analytics.created_at - time.time())
        if time_diff < 5.0:  # Within 5 seconds
            interference_factors["timing_conflict"] = 0.5
        elif time_diff < 30.0:  # Within 30 seconds
            interference_factors["timing_conflict"] = 0.3

        # Strategy interference (conflicting strategies)
        strategy_interference = self._assess_strategy_interference(signal, analytics)
        interference_factors["strategy_conflict"] = strategy_interference

        # Calculate overall interference score
        weighted_score = (
            interference_factors["token_conflict"] * 0.3
            + interference_factors["side_conflict"] * 0.25
            + interference_factors["price_conflict"] * 0.15
            + interference_factors["market_conflict"] * 0.1
            + interference_factors["timing_conflict"] * 0.05
            + interference_factors["strategy_conflict"] * 0.1
            + interference_factors["volume_conflict"] * 0.05
        )

        # Update analytics with detailed interference data
        analytics.interference_factors = interference_factors
        analytics.interference_score = weighted_score

        # Convert to interference level
        return self._convert_score_to_interference_level(weighted_score)

    def _assess_strategy_interference(
        self, signal: TradingSignal, analytics: SignalAnalytics
    ) -> float:
        """Assess interference between different trading strategies."""
        # Get strategy types if available
        signal_strategy = getattr(signal, "strategy_type", None)
        analytics_strategy = getattr(analytics, "strategy_type", None)

        if not signal_strategy or not analytics_strategy:
            return 0.0

        # Define strategy conflict matrix
        conflict_matrix = {
            (
                "arbitrage",
                "arbitrage",
            ): 0.8,  # High conflict - competing for same opportunity
            (
                "arbitrage",
                "market_making",
            ): 0.6,  # Moderate conflict - arbitrage affects spreads
            (
                "market_making",
                "market_making",
            ): 0.7,  # High conflict - competing for liquidity
            (
                "momentum",
                "mean_reversion",
            ): 0.9,  # Very high conflict - opposite directions
            ("news_based", "news_based"): 0.8,  # High conflict - same event
        }

        strategy_pair = (signal_strategy, analytics_strategy)
        reverse_pair = (analytics_strategy, signal_strategy)

        return conflict_matrix.get(
            strategy_pair, conflict_matrix.get(reverse_pair, 0.2)
        )

    def _estimate_market_capacity(self, token_id: str) -> float:
        """Estimate market capacity for a given token."""
        # This would typically use real market data
        # For now, return a default estimate
        default_capacity = 10000.0  # Default market capacity

        # Could be enhanced with:
        # - Historical volume data
        # - Current order book depth
        # - Market liquidity metrics

        return default_capacity

    def _convert_score_to_interference_level(
        self, score: float
    ) -> SignalInterferenceLevel:
        """Convert numerical interference score to interference level enum."""
        if score >= 0.8:
            return SignalInterferenceLevel.CRITICAL
        elif score >= 0.6:
            return SignalInterferenceLevel.HIGH
        elif score >= 0.4:
            return SignalInterferenceLevel.MODERATE
        elif score >= 0.2:
            return SignalInterferenceLevel.LOW
        else:
            return SignalInterferenceLevel.NONE

    def _interference_level_value(self, level: SignalInterferenceLevel) -> int:
        """Convert interference level to numerical value for comparison."""
        level_values = {
            SignalInterferenceLevel.NONE: 0,
            SignalInterferenceLevel.LOW: 1,
            SignalInterferenceLevel.MODERATE: 2,
            SignalInterferenceLevel.HIGH: 3,
            SignalInterferenceLevel.CRITICAL: 4,
        }
        return level_values.get(level, 0)

    def _calculate_interference_score(
        self, signal_wrapper: EnhancedSignalWrapper
    ) -> float:
        """Calculate interference score for a signal based on various factors."""
        signal = signal_wrapper.signal
        metadata = signal_wrapper.metadata

        score = 0.0

        # Priority factor (higher priority = more interference potential)
        priority_scores = {
            SignalPriority.CRITICAL: 0.8,
            SignalPriority.HIGH: 0.6,
            SignalPriority.NORMAL: 0.4,
            SignalPriority.LOW: 0.2,
        }
        score += priority_scores.get(metadata.priority, 0.4)

        # Size factor (larger size = more interference potential)
        size_factor = min(signal.size / 1000.0, 0.3)  # Cap at 0.3
        score += size_factor

        # Market volatility factor
        volatility_factor = metadata.volatility_score * 0.3
        score += volatility_factor

        # Time-to-expiration factor
        current_time = time.time()
        time_to_expiration = metadata.expires_at - current_time
        if time_to_expiration > 0:
            urgency_factor = max(
                0, 0.2 - (time_to_expiration / 100.0)
            )  # More urgent = more interference
            score += urgency_factor

        return min(score, 1.0)  # Cap at 1.0

    async def _cleanup_loop(self):
        """Main cleanup loop."""
        while self._running:
            try:
                start_time = time.time()

                # Perform cleanup batch
                await self._perform_cleanup_batch()

                # Update performance metrics
                cleanup_duration = time.time() - start_time
                self._update_cleanup_metrics(cleanup_duration)

                # Wait for next iteration
                await asyncio.sleep(self.config.cleanup_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(self.config.cleanup_interval_seconds)

    async def _perform_cleanup_batch(self):
        """Perform a batch of cleanup operations."""
        current_time = time.time()
        cleanup_candidates = []

        # Find cleanup candidates
        for signal_id, analytics in list(self._signals_analytics.items()):
            cleanup_rule = self._get_applicable_cleanup_rule(
                signal_id, analytics, current_time
            )

            if cleanup_rule:
                # Use adaptive cleanup delay based on system conditions
                adaptive_delay = self._get_adaptive_cleanup_delay(
                    cleanup_rule.cleanup_delay
                )
                cleanup_time = analytics.created_at + adaptive_delay
                if current_time >= cleanup_time:
                    cleanup_candidates.append((signal_id, cleanup_rule))

        # Sort by priority and limit batch size
        cleanup_candidates.sort(key=lambda x: x[1].priority, reverse=True)
        batch = cleanup_candidates[: self.config.batch_cleanup_size]

        # Perform cleanup
        for signal_id, cleanup_rule in batch:
            await self._cleanup_signal(signal_id, cleanup_rule)

        if batch:
            self._cleanup_metrics["batch_operations"] += 1
            logger.debug(f"Cleaned up {len(batch)} signals in batch")

    def _get_applicable_cleanup_rule(
        self, signal_id: str, analytics: SignalAnalytics, current_time: float
    ) -> CleanupRule | None:
        """Get the applicable cleanup rule for a signal with system-aware context."""
        signal_age = current_time - analytics.created_at

        rule_context = {
            "signal_id": signal_id,
            # System metrics for load-based cleanup
            "system_load": self._get_system_load(),
            "memory_usage": self._get_memory_usage(),
            "process_memory_mb": self._get_process_memory_usage(),
            "age_seconds": signal_age,
            "access_count": analytics.access_count,
            "last_accessed_ago": current_time - analytics.last_accessed,
            "interference_score": analytics.interference_score,
            "interference_level": self._get_interference_level_from_score(
                analytics.interference_score
            ),
        }

        # Check rules in priority order
        for rule in self._cleanup_rules:
            if self._rule_matches_context(rule, rule_context):
                return rule

        return None

    def _get_interference_level_from_score(
        self, score: float
    ) -> SignalInterferenceLevel:
        """Convert interference score to interference level."""
        if score >= 0.8:
            return SignalInterferenceLevel.CRITICAL
        elif score >= 0.6:
            return SignalInterferenceLevel.HIGH
        elif score >= 0.4:
            return SignalInterferenceLevel.MODERATE
        elif score >= 0.2:
            return SignalInterferenceLevel.LOW
        else:
            return SignalInterferenceLevel.NONE

    def _rule_matches_context(self, rule: CleanupRule, context: dict[str, Any]) -> bool:
        """Check if a cleanup rule matches the given context."""
        for condition_key, condition_value in rule.conditions.items():
            context_value = context.get(condition_key)

            if context_value is None:
                continue

            # Handle different condition types
            if isinstance(condition_value, dict):
                # Range conditions
                if "min" in condition_value:
                    if context_value < condition_value["min"]:
                        return False
                if "max" in condition_value:
                    if context_value > condition_value["max"]:
                        return False
            else:
                # Exact match conditions
                if context_value != condition_value:
                    return False

        return True

    async def _cleanup_signal(self, signal_id: str, cleanup_rule: CleanupRule):
        """Clean up a specific signal according to the cleanup rule."""
        if signal_id not in self._signals_analytics:
            return

        analytics = self._signals_analytics[signal_id]

        # Archive if required
        if cleanup_rule.archive_before_cleanup:
            self._cleanup_archive.append(
                {
                    "signal_id": signal_id,
                    "cleanup_time": time.time(),
                    "analytics": analytics,
                    "cleanup_rule": cleanup_rule.name,
                    "reason": "rule_based_cleanup",
                }
            )

        # Perform the actual cleanup
        self.unregister_signal(signal_id)

        logger.debug(f"Cleaned up signal {signal_id} using rule: {cleanup_rule.name}")

    async def _interference_detection_loop(self):
        """Background task for interference detection and prevention."""
        while self._running:
            try:
                await self._detect_and_prevent_interference()
                await asyncio.sleep(
                    self.config.interference_detection_window / 4
                )  # Check 4x per window
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in interference detection: {e}")
                await asyncio.sleep(5.0)

    async def _detect_and_prevent_interference(self):
        """Detect and prevent signal interference."""
        current_time = time.time()
        interference_cases = []

        # Analyze signal correlations for interference
        for signal_id, analytics in list(self._signals_analytics.items()):
            if analytics.interference_score > 0.6:  # High interference potential
                # Check for recent similar signals
                interference_risk = self._analyze_interference_risk(
                    signal_id, current_time
                )

                if interference_risk["level"] in [
                    SignalInterferenceLevel.HIGH,
                    SignalInterferenceLevel.CRITICAL,
                ]:
                    interference_cases.append(
                        {"signal_id": signal_id, "risk": interference_risk}
                    )

        # Take action on high-risk interference cases
        for case in interference_cases:
            signal_id = case["signal_id"]
            risk_level = case["risk"]["level"]

            if risk_level == SignalInterferenceLevel.CRITICAL:
                # Immediate cleanup for critical interference
                await self._cleanup_signal(
                    signal_id,
                    CleanupRule(
                        name="critical_interference",
                        description="Critical interference prevention",
                        strategy=CleanupStrategy.IMMEDIATE,
                        conditions={},
                    ),
                )

                self._cleanup_metrics["interference_prevented"] += 1
                logger.warning(
                    f"Cleaned up signal {signal_id} due to critical interference risk"
                )

    def _analyze_interference_risk(
        self, signal_id: str, current_time: float
    ) -> dict[str, Any]:
        """Analyze interference risk for a specific signal."""
        if signal_id not in self._signals_analytics:
            return {"level": SignalInterferenceLevel.NONE}

        analytics = self._signals_analytics[signal_id]
        risk_factors = []

        # Check age vs access pattern
        signal_age = current_time - analytics.created_at
        time_since_access = current_time - analytics.last_accessed

        if signal_age > 30 and time_since_access > 20:  # Old and unused
            risk_factors.append("stale_signal")

        if analytics.access_count == 0 and signal_age > 10:  # Never accessed
            risk_factors.append("unused_signal")

        # Calculate overall risk level
        base_risk = analytics.interference_score
        risk_multiplier = 1.0

        if "stale_signal" in risk_factors:
            risk_multiplier += 0.3
        if "unused_signal" in risk_factors:
            risk_multiplier += 0.4

        final_risk_score = min(base_risk * risk_multiplier, 1.0)

        # Convert to risk level
        if final_risk_score >= 0.8:
            risk_level = SignalInterferenceLevel.CRITICAL
        elif final_risk_score >= 0.6:
            risk_level = SignalInterferenceLevel.HIGH
        elif final_risk_score >= 0.4:
            risk_level = SignalInterferenceLevel.MODERATE
        elif final_risk_score >= 0.2:
            risk_level = SignalInterferenceLevel.LOW
        else:
            risk_level = SignalInterferenceLevel.NONE

        return {"level": risk_level, "score": final_risk_score, "factors": risk_factors}

    def _update_cleanup_metrics(self, cleanup_duration: float):
        """Update cleanup performance metrics."""
        current_avg = self._cleanup_metrics["cleanup_time_avg"]
        # Exponential moving average
        self._cleanup_metrics["cleanup_time_avg"] = (current_avg * 0.9) + (
            cleanup_duration * 0.1
        )

    def _get_system_load(self) -> float:
        """Get current system load (CPU usage)."""
        try:
            return psutil.cpu_percent(interval=0.1) / 100.0
        except Exception as e:
            logger.warning(f"Failed to get system load: {e}")
            return 0.5  # Default to moderate load if unable to determine

    def _get_memory_usage(self) -> float:
        """Get current memory usage as a percentage."""
        try:
            memory = psutil.virtual_memory()
            return memory.percent / 100.0
        except Exception as e:
            logger.warning(f"Failed to get memory usage: {e}")
            return 0.5  # Default to moderate usage if unable to determine

    def _get_process_memory_usage(self) -> float:
        """Get current process memory usage in MB."""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except Exception as e:
            logger.warning(f"Failed to get process memory usage: {e}")
            return 0.0

    def _should_trigger_aggressive_cleanup(self) -> bool:
        """Determine if aggressive cleanup should be triggered based on system metrics."""
        system_load = self._get_system_load()
        memory_usage = self._get_memory_usage()

        # Trigger aggressive cleanup if system is under pressure
        if system_load > 0.8 or memory_usage > 0.85:
            logger.warning(
                f"Triggering aggressive cleanup - Load: {system_load:.2f}, Memory: {memory_usage:.2f}"
            )
            return True

        # Also consider number of active signals
        if len(self._signals_analytics) > self.config.max_concurrent_signals * 0.9:
            logger.info("Triggering cleanup due to high signal count")
            return True

        return False

    def _get_adaptive_cleanup_delay(self, base_delay: float) -> float:
        """Calculate adaptive cleanup delay based on system conditions."""
        system_load = self._get_system_load()
        memory_usage = self._get_memory_usage()

        # Reduce delay under system pressure
        if system_load > 0.7 or memory_usage > 0.8:
            return base_delay * 0.3  # Reduce delay significantly
        elif system_load > 0.5 or memory_usage > 0.6:
            return base_delay * 0.6  # Moderate reduction
        else:
            return base_delay  # Normal delay

    def get_cleanup_metrics(self) -> dict[str, Any]:
        """Get comprehensive cleanup metrics including system information."""
        return {
            **self._cleanup_metrics,
            "active_signals": len(self._signals_analytics),
            "pending_cleanup": len(self._pending_cleanup),
            "archive_size": len(self._cleanup_archive),
            "token_maps": len(self._token_signal_map),
            "market_maps": len(self._market_signal_map),
            # System metrics
            "system_load": self._get_system_load(),
            "memory_usage": self._get_memory_usage(),
            "process_memory_mb": self._get_process_memory_usage(),
            "aggressive_cleanup_triggered": self._should_trigger_aggressive_cleanup(),
        }

    def get_interference_report(self) -> dict[str, Any]:
        """Get comprehensive interference analysis report."""
        current_time = time.time()
        report = {
            "total_signals": len(self._signals_analytics),
            "interference_levels": {
                level.value: 0 for level in SignalInterferenceLevel
            },
            "high_risk_signals": [],
            "token_distribution": {},
            "market_distribution": {},
        }

        for signal_id, analytics in self._signals_analytics.items():
            # Analyze current interference risk
            risk_analysis = self._analyze_interference_risk(signal_id, current_time)
            risk_level = risk_analysis["level"]

            report["interference_levels"][risk_level.value] += 1

            if risk_level in [
                SignalInterferenceLevel.HIGH,
                SignalInterferenceLevel.CRITICAL,
            ]:
                report["high_risk_signals"].append(
                    {
                        "signal_id": signal_id,
                        "risk_level": risk_level.value,
                        "risk_score": risk_analysis["score"],
                        "age_seconds": current_time - analytics.created_at,
                        "access_count": analytics.access_count,
                    }
                )

        # Token and market distribution
        for token_id, signal_set in self._token_signal_map.items():
            if signal_set:  # Only include active tokens
                report["token_distribution"][token_id] = len(signal_set)

        for market_slug, signal_set in self._market_signal_map.items():
            if signal_set:  # Only include active markets
                report["market_distribution"][market_slug] = len(signal_set)

        return report

    def prevent_signal_interference(
        self, incoming_signal: TradingSignal
    ) -> dict[str, Any]:
        """Proactively prevent signal interference by analyzing and potentially blocking signals."""
        current_time = time.time()
        prevention_result = {
            "blocked": False,
            "reason": "",
            "conflicting_signals": [],
            "recommended_actions": [],
            "interference_score": 0.0,
        }

        # Check for immediate conflicts
        immediate_conflicts = self._find_immediate_conflicts(
            incoming_signal, current_time
        )
        if immediate_conflicts:
            prevention_result["blocked"] = True
            prevention_result["reason"] = "Immediate signal conflicts detected"
            prevention_result["conflicting_signals"] = immediate_conflicts

            # Suggest remediation
            prevention_result["recommended_actions"] = [
                "Wait for conflicting signals to complete",
                "Cancel lower priority conflicting signals",
                "Adjust signal parameters to reduce conflict",
            ]

        # Check for capacity constraints
        capacity_issue = self._check_market_capacity_constraints(incoming_signal)
        if capacity_issue:
            if not prevention_result["blocked"]:
                prevention_result["blocked"] = True
                prevention_result["reason"] = "Market capacity constraints"
            prevention_result["recommended_actions"].append(
                "Reduce signal size or delay execution"
            )

        # Calculate overall interference score
        interference_score = self._calculate_proactive_interference_score(
            incoming_signal
        )
        prevention_result["interference_score"] = interference_score

        # Block if interference score is too high
        if interference_score > 0.8 and not prevention_result["blocked"]:
            prevention_result["blocked"] = True
            prevention_result["reason"] = "High interference risk detected"

        # Add monitoring recommendations
        if interference_score > 0.6:
            prevention_result["recommended_actions"].append(
                "Monitor signal closely for conflicts"
            )

        return prevention_result

    def _find_immediate_conflicts(
        self, signal: TradingSignal, current_time: float
    ) -> list[dict[str, Any]]:
        """Find signals that would immediately conflict with the incoming signal."""
        conflicts = []

        # Check token-level conflicts
        token_signals = self._token_signal_map.get(signal.token_id, set())
        for signal_id in token_signals:
            if signal_id in self._signals_analytics:
                analytics = self._signals_analytics[signal_id]

                # Check for critical conflicts
                conflict_level = self._assess_signal_interference(signal, signal_id)
                if conflict_level in [
                    SignalInterferenceLevel.HIGH,
                    SignalInterferenceLevel.CRITICAL,
                ]:
                    conflicts.append(
                        {
                            "signal_id": signal_id,
                            "conflict_type": "token_level",
                            "conflict_level": conflict_level.value,
                            "created_at": analytics.created_at,
                            "age_seconds": current_time - analytics.created_at,
                        }
                    )

        return conflicts

    def _check_market_capacity_constraints(self, signal: TradingSignal) -> bool:
        """Check if signal would exceed market capacity constraints."""
        token_capacity = self._estimate_market_capacity(signal.token_id)

        # Calculate total pending volume for this token
        total_pending_volume = 0.0
        token_signals = self._token_signal_map.get(signal.token_id, set())

        for signal_id in token_signals:
            if signal_id in self._signals_analytics:
                analytics = self._signals_analytics[signal_id]
                # Assume analytics has access to signal size
                signal_size = getattr(analytics, "signal_size", 0.0)
                total_pending_volume += signal_size

        # Add incoming signal size
        total_pending_volume += signal.size

        # Check if total exceeds capacity
        return total_pending_volume > token_capacity * 0.9  # 90% capacity threshold

    def _calculate_proactive_interference_score(self, signal: TradingSignal) -> float:
        """Calculate interference score for proactive prevention."""
        score = 0.0
        current_time = time.time()

        # Token density factor
        token_signals = len(self._token_signal_map.get(signal.token_id, set()))
        if token_signals > 0:
            score += min(token_signals * 0.1, 0.4)  # Max 0.4 for token density

        # Market density factor
        market_signals = len(self._market_signal_map.get(signal.market_slug, set()))
        if market_signals > 0:
            score += min(market_signals * 0.05, 0.2)  # Max 0.2 for market density

        # Recent activity factor
        recent_signals = 0
        for analytics in self._signals_analytics.values():
            if current_time - analytics.created_at < 30.0:  # Signals in last 30 seconds
                recent_signals += 1

        if recent_signals > 0:
            score += min(recent_signals * 0.05, 0.3)  # Max 0.3 for recent activity

        # Price volatility impact
        volatility_impact = self._assess_price_volatility_impact(signal)
        score += volatility_impact * 0.1  # Max 0.1 contribution

        return min(score, 1.0)  # Cap at 1.0

    def _assess_price_volatility_impact(self, signal: TradingSignal) -> float:
        """Assess how the signal might impact price volatility."""
        # Simple volatility assessment based on signal characteristics
        impact = 0.0

        # Large orders have higher impact
        if signal.size > 1000:
            impact += 0.3
        elif signal.size > 500:
            impact += 0.2
        elif signal.size > 100:
            impact += 0.1

        # Market orders have higher impact than limit orders
        if hasattr(signal, "order_type") and signal.order_type == "market":
            impact += 0.2

        return min(impact, 1.0)

    def auto_resolve_conflicts(self, signal: TradingSignal) -> dict[str, Any]:
        """Automatically resolve signal conflicts using predefined strategies."""
        resolution_result = {
            "resolved": False,
            "actions_taken": [],
            "signals_cancelled": [],
            "signals_modified": [],
            "message": "",
        }

        # Find conflicts
        conflicts = self._find_immediate_conflicts(signal, time.time())

        if not conflicts:
            resolution_result["resolved"] = True
            resolution_result["message"] = "No conflicts found"
            return resolution_result

        # Apply resolution strategies
        for conflict in conflicts:
            signal_id = conflict["signal_id"]

            # Strategy 1: Cancel lower priority signals
            if self._should_cancel_for_priority(signal, signal_id):
                self._cancel_signal(signal_id)
                resolution_result["signals_cancelled"].append(signal_id)
                resolution_result["actions_taken"].append(
                    f"Cancelled lower priority signal {signal_id}"
                )

        # Check if all conflicts resolved
        remaining_conflicts = self._find_immediate_conflicts(signal, time.time())
        if not remaining_conflicts:
            resolution_result["resolved"] = True
            resolution_result["message"] = "All conflicts resolved successfully"
        else:
            resolution_result["message"] = (
                f"{len(remaining_conflicts)} conflicts remain unresolved"
            )

        return resolution_result

    def _should_cancel_for_priority(
        self, incoming_signal: TradingSignal, existing_signal_id: str
    ) -> bool:
        """Determine if existing signal should be cancelled for higher priority incoming signal."""
        if existing_signal_id not in self._signals_analytics:
            return False

        existing_analytics = self._signals_analytics[existing_signal_id]

        # Get priorities (assuming incoming signal has higher priority)
        incoming_priority = getattr(incoming_signal, "priority", "normal")
        existing_priority = getattr(existing_analytics, "priority", "normal")

        priority_levels = {
            "low": 1,
            "normal": 2,
            "high": 3,
            "critical": 4,
            "emergency": 5,
        }

        incoming_level = priority_levels.get(incoming_priority, 2)
        existing_level = priority_levels.get(existing_priority, 2)

        return incoming_level > existing_level

    def _cancel_signal(self, signal_id: str) -> None:
        """Cancel a signal and perform cleanup."""
        if signal_id in self._signals_analytics:
            analytics = self._signals_analytics[signal_id]
            analytics.status = "cancelled"
            analytics.cleanup_triggered_at = time.time()

            # Schedule for immediate cleanup
            self._pending_cleanup[signal_id] = time.time()

            self._cleanup_metrics["signals_cancelled"] += 1
            logger.info(f"Signal {signal_id} cancelled due to conflict resolution")
