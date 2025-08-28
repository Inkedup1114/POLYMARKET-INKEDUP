"""
Enhanced signal lifecycle management with advanced timeout handling and market-aware cleanup.

This module extends the existing signal processing pipeline with:
- Market volatility-aware timeout adjustment
- Advanced priority-based signal processing
- Context-aware signal interference prevention
- Comprehensive monitoring and alerting
- Adaptive cleanup strategies
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .signal_manager import (
    SignalManager,
    SignalManagerConfig,
    SignalMetadata,
    SignalStatus,
    SignalWrapper,
)
from .signals import TradingSignal

logger = logging.getLogger("enhanced_signal_manager")


class SignalPriority(str, Enum):
    """Signal priority levels for processing order."""

    CRITICAL = "critical"  # Immediate arbitrage opportunities
    HIGH = "high"  # Time-sensitive market making
    NORMAL = "normal"  # Regular trading signals
    LOW = "low"  # Background rebalancing


class MarketCondition(str, Enum):
    """Market volatility conditions affecting timeout behavior."""

    VOLATILE = "volatile"  # High volatility - shorter timeouts
    NORMAL = "normal"  # Normal conditions
    STABLE = "stable"  # Low volatility - longer timeouts allowed


@dataclass
class EnhancedSignalMetadata(SignalMetadata):
    """Enhanced metadata with comprehensive tracking and market context."""

    # Priority and market awareness
    priority: SignalPriority = SignalPriority.NORMAL
    market_condition: MarketCondition = MarketCondition.NORMAL
    volatility_score: float = 0.0
    interference_risk: float = 0.0

    # Advanced timing
    original_timeout: float = 0.0
    adjusted_timeout: float = 0.0
    last_heartbeat: float = 0.0
    processing_deadline: float = 0.0

    # Comprehensive timestamp tracking
    submitted_at: float | None = None
    queue_entry_time: float | None = None
    last_accessed_at: float | None = None
    processing_started_at: float | None = None
    risk_check_started_at: float | None = None
    risk_check_completed_at: float | None = None
    execution_started_at: float | None = None
    execution_completed_at: float | None = None
    cleanup_triggered_at: float | None = None

    # Context tracking
    strategy_name: str = ""
    market_sector: str = ""
    signal_source: str = ""
    parent_signal_id: str | None = None
    child_signal_ids: list[str] = field(default_factory=list)

    # Performance tracking
    queue_wait_time: float = 0.0
    validation_time: float = 0.0
    execution_attempts: int = 0
    retry_delays: list[float] = field(default_factory=list)

    def update_timestamp(self, event: str, timestamp: float | None = None) -> None:
        """Update a specific timestamp event."""
        if timestamp is None:
            timestamp = time.time()

        setattr(self, f"{event}_at", timestamp)
        self.last_accessed_at = timestamp

    def get_processing_duration(self) -> float | None:
        """Calculate total processing duration if both start and end times are available."""
        if self.processing_started_at and self.execution_completed_at:
            return self.execution_completed_at - self.processing_started_at
        return None

    def get_queue_wait_duration(self) -> float | None:
        """Calculate queue wait duration."""
        if self.queue_entry_time and self.processing_started_at:
            return self.processing_started_at - self.queue_entry_time
        return None

    def get_risk_check_duration(self) -> float | None:
        """Calculate risk check duration."""
        if self.risk_check_started_at and self.risk_check_completed_at:
            return self.risk_check_completed_at - self.risk_check_started_at
        return None

    def get_execution_duration(self) -> float | None:
        """Calculate execution duration."""
        if self.execution_started_at and self.execution_completed_at:
            return self.execution_completed_at - self.execution_started_at
        return None


@dataclass
class EnhancedSignalWrapper(SignalWrapper):
    """Enhanced wrapper with additional tracking capabilities."""

    metadata: EnhancedSignalMetadata

    # Context preservation
    market_snapshot: dict[str, Any] = field(default_factory=dict)
    risk_context: dict[str, Any] = field(default_factory=dict)
    execution_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class EnhancedSignalManagerConfig(SignalManagerConfig):
    """Enhanced configuration with market-aware settings."""

    # Advanced timeout settings
    volatility_timeout_multipliers: dict[str, float] = field(
        default_factory=lambda: {
            "volatile": 0.5,  # 50% of normal timeout in volatile conditions
            "normal": 1.0,  # Normal timeout
            "stable": 1.5,  # 150% timeout in stable conditions
        }
    )

    # Priority-based timeouts
    priority_timeout_multipliers: dict[str, float] = field(
        default_factory=lambda: {
            "critical": 0.3,  # 30% of base timeout
            "high": 0.6,  # 60% of base timeout
            "normal": 1.0,  # Full timeout
            "low": 2.0,  # Double timeout for low priority
        }
    )

    # Market condition detection
    volatility_lookback_seconds: float = 300.0  # 5 minutes
    volatility_threshold_high: float = 0.05  # 5% price change
    volatility_threshold_low: float = 0.01  # 1% price change

    # Advanced cleanup settings
    enable_priority_cleanup: bool = True
    priority_cleanup_thresholds: dict[str, int] = field(
        default_factory=lambda: {
            "critical": 2,  # Clean critical signals after 2 seconds if expired
            "high": 5,  # Clean high priority after 5 seconds
            "normal": 10,  # Clean normal signals after 10 seconds
            "low": 30,  # Clean low priority after 30 seconds
        }
    )

    # Signal interference prevention
    enable_interference_detection: bool = True
    max_signals_per_token: int = 3
    min_signal_spacing_seconds: float = 1.0
    conflicting_signal_resolution: str = "cancel_older"  # "cancel_older" or "queue"

    # Advanced monitoring
    enable_performance_tracking: bool = True
    enable_market_condition_tracking: bool = True
    enable_signal_correlation_tracking: bool = True

    # Alerting thresholds
    alert_high_expiration_rate: float = 0.3  # Alert if >30% signals expire
    alert_long_queue_wait: float = 5.0  # Alert if signals wait >5s
    alert_processing_bottleneck: float = 10.0  # Alert if processing takes >10s


class EnhancedSignalManager(SignalManager):
    """
    Enhanced signal manager with market-aware timeout handling and advanced cleanup.

    Key enhancements:
    - Market volatility-aware timeout adjustment
    - Priority-based signal processing
    - Advanced signal interference prevention
    - Context-aware signal correlation tracking
    - Comprehensive performance monitoring and alerting
    """

    def __init__(self, config: EnhancedSignalManagerConfig | None = None):
        # Initialize base config for parent class
        base_config = SignalManagerConfig() if config is None else config
        super().__init__(base_config)

        # Enhanced configuration
        self.enhanced_config = config or EnhancedSignalManagerConfig()

        # Priority-based signal queues
        self._priority_queues: dict[
            SignalPriority, dict[str, EnhancedSignalWrapper]
        ] = {
            SignalPriority.CRITICAL: {},
            SignalPriority.HIGH: {},
            SignalPriority.NORMAL: {},
            SignalPriority.LOW: {},
        }

        # Market condition tracking
        self._market_conditions: dict[str, MarketCondition] = {}
        self._volatility_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=100)
        )
        self._price_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        # Signal interference tracking
        self._active_signals_by_token: dict[str, list[str]] = defaultdict(list)
        self._signal_spacing_tracker: dict[str, float] = {}

        # Performance and correlation tracking
        self._processing_performance: dict[str, list[float]] = defaultdict(list)
        self._signal_correlations: dict[str, list[str]] = defaultdict(list)

        # Enhanced metrics
        self._enhanced_metrics = {
            "signals_by_priority": defaultdict(int),
            "timeouts_adjusted": 0,
            "interference_prevented": 0,
            "market_condition_changes": 0,
            "avg_queue_wait_time": 0.0,
            "signals_per_second": 0.0,
            "high_priority_processing_time": 0.0,
        }

        # Alerting state
        self._last_alerts: dict[str, float] = {}
        self._alert_cooldown: float = 300.0  # 5 minutes between similar alerts

        logger.info(
            f"EnhancedSignalManager initialized with advanced config: {self.enhanced_config}"
        )

    async def submit_enhanced_signal(
        self,
        signal: TradingSignal,
        priority: SignalPriority = SignalPriority.NORMAL,
        strategy_name: str = "",
        market_sector: str = "",
        signal_source: str = "",
        parent_signal_id: str | None = None,
        execution_context: dict[str, Any] | None = None,
    ) -> str:
        """
        Submit a signal with enhanced tracking and market-aware timeout adjustment.

        Args:
            signal: The trading signal to process
            priority: Signal priority level
            strategy_name: Name of the strategy generating the signal
            market_sector: Market sector classification
            signal_source: Source system/component generating the signal
            parent_signal_id: ID of parent signal if this is a derived signal
            execution_context: Additional context for execution

        Returns:
            signal_id: Unique identifier for tracking the signal
        """
        with self._lock:
            current_time = time.time()

            # Generate signal ID if not present
            if not signal.signal_id:
                signal.signal_id = f"enh_sig_{int(current_time * 1000)}_{hash(signal.market_slug) % 10000}"

            # Detect market conditions for this token
            market_condition = self._detect_market_condition(signal.token_id)
            volatility_score = self._calculate_volatility_score(signal.token_id)

            # Calculate adaptive timeout
            base_timeout = self._get_signal_timeout(signal)
            adjusted_timeout = self._calculate_adjusted_timeout(
                base_timeout, priority, market_condition, volatility_score
            )

            # Check for signal interference
            if self.enhanced_config.enable_interference_detection:
                interference_result = self._check_signal_interference(signal, priority)
                if interference_result["blocked"]:
                    self._enhanced_metrics["interference_prevented"] += 1
                    logger.warning(
                        f"Signal blocked due to interference: {interference_result['reason']}"
                    )
                    raise SignalInterferenceError(interference_result["reason"])

            # Create enhanced metadata with comprehensive timestamp tracking
            enhanced_metadata = EnhancedSignalMetadata(
                signal_id=signal.signal_id,
                created_at=current_time,
                expires_at=current_time + adjusted_timeout,
                # Additional timestamp metadata
                submitted_at=current_time,
                queue_entry_time=current_time,
                last_accessed_at=current_time,
                processing_started_at=None,
                risk_check_started_at=None,
                risk_check_completed_at=None,
                execution_started_at=None,
                execution_completed_at=None,
                cleanup_triggered_at=None,
                deduplication_key=self._generate_dedup_key(signal),
                priority=priority,
                market_condition=market_condition,
                volatility_score=volatility_score,
                original_timeout=base_timeout,
                adjusted_timeout=adjusted_timeout,
                processing_deadline=current_time
                + adjusted_timeout * 0.9,  # 90% of timeout
                strategy_name=strategy_name,
                market_sector=market_sector,
                signal_source=signal_source,
                parent_signal_id=parent_signal_id,
            )

            # Create enhanced wrapper
            enhanced_wrapper = EnhancedSignalWrapper(
                signal=signal,
                metadata=enhanced_metadata,
                execution_context=execution_context or {},
            )

            # Store market snapshot for context
            enhanced_wrapper.market_snapshot = self._capture_market_snapshot(signal)

            # Add to appropriate priority queue
            self._priority_queues[priority][signal.signal_id] = enhanced_wrapper

            # Track active signals by token
            self._active_signals_by_token[signal.token_id].append(signal.signal_id)
            self._signal_spacing_tracker[signal.token_id] = current_time

            # Update metrics
            self._enhanced_metrics["signals_by_priority"][priority.value] += 1
            if adjusted_timeout != base_timeout:
                self._enhanced_metrics["timeouts_adjusted"] += 1

            # Link parent-child relationship
            if parent_signal_id:
                self._link_parent_child_signals(parent_signal_id, signal.signal_id)

            logger.debug(
                f"Enhanced signal submitted: {signal.signal_id} "
                f"(priority: {priority.value}, timeout: {adjusted_timeout:.1f}s, "
                f"market_condition: {market_condition.value})"
            )

            # Schedule priority-aware processing
            try:
                asyncio.create_task(
                    self._process_enhanced_signal_async(enhanced_wrapper)
                )
            except RuntimeError:
                logger.warning(
                    f"No event loop running for enhanced signal {signal.signal_id}"
                )

            return str(signal.signal_id)

    def _detect_market_condition(self, token_id: str) -> MarketCondition:
        """Detect current market condition based on recent price volatility."""
        if not self.enhanced_config.enable_market_condition_tracking:
            return MarketCondition.NORMAL

        price_history = self._price_history.get(token_id, deque())
        if len(price_history) < 2:
            return MarketCondition.NORMAL

        # Calculate recent volatility
        recent_prices = list(price_history)[-10:]  # Last 10 price points
        if len(recent_prices) < 2:
            return MarketCondition.NORMAL

        price_changes = []
        for i in range(1, len(recent_prices)):
            change = abs(recent_prices[i] - recent_prices[i - 1]) / recent_prices[i - 1]
            price_changes.append(change)

        avg_volatility = sum(price_changes) / len(price_changes)

        # Classify based on thresholds
        if avg_volatility > self.enhanced_config.volatility_threshold_high:
            condition = MarketCondition.VOLATILE
        elif avg_volatility < self.enhanced_config.volatility_threshold_low:
            condition = MarketCondition.STABLE
        else:
            condition = MarketCondition.NORMAL

        # Update condition tracking
        if (
            token_id not in self._market_conditions
            or self._market_conditions[token_id] != condition
        ):
            self._market_conditions[token_id] = condition
            self._enhanced_metrics["market_condition_changes"] += 1
            logger.debug(f"Market condition changed for {token_id}: {condition.value}")

        return condition

    def _calculate_volatility_score(self, token_id: str) -> float:
        """Calculate a numerical volatility score (0.0 to 1.0)."""
        price_history = self._price_history.get(token_id, deque())
        if len(price_history) < 2:
            return 0.0

        recent_prices = list(price_history)[-20:]  # Last 20 price points
        if len(recent_prices) < 2:
            return 0.0

        # Calculate coefficient of variation
        mean_price = sum(recent_prices) / len(recent_prices)
        variance = sum((p - mean_price) ** 2 for p in recent_prices) / len(
            recent_prices
        )
        std_dev = variance**0.5

        if mean_price == 0:
            return 0.0

        cv = std_dev / mean_price

        # Normalize to 0-1 range (assuming max CV of 0.2 for trading signals)
        return min(cv / 0.2, 1.0)

    def _calculate_adjusted_timeout(
        self,
        base_timeout: float,
        priority: SignalPriority,
        market_condition: MarketCondition,
        volatility_score: float,
    ) -> float:
        """Calculate timeout adjusted for market conditions and priority."""
        # Apply priority multiplier
        priority_multiplier = self.enhanced_config.priority_timeout_multipliers.get(
            priority.value, 1.0
        )

        # Apply market condition multiplier
        condition_multiplier = self.enhanced_config.volatility_timeout_multipliers.get(
            market_condition.value, 1.0
        )

        # Apply dynamic volatility adjustment
        volatility_adjustment = 1.0 - (
            volatility_score * 0.3
        )  # Reduce timeout by up to 30% for high volatility

        adjusted_timeout = (
            base_timeout
            * priority_multiplier
            * condition_multiplier
            * volatility_adjustment
        )

        # Ensure minimum timeout of 1 second
        return max(adjusted_timeout, 1.0)

    def _check_signal_interference(
        self, signal: TradingSignal, priority: SignalPriority
    ) -> dict[str, Any]:
        """Check if signal would interfere with existing signals."""
        current_time = time.time()
        token_id = signal.token_id

        # Check signal spacing
        last_signal_time = self._signal_spacing_tracker.get(token_id, 0)
        if (
            current_time - last_signal_time
        ) < self.enhanced_config.min_signal_spacing_seconds:
            return {
                "blocked": True,
                "reason": f"Signal too close to previous signal (spacing: {current_time - last_signal_time:.2f}s)",
            }

        # Check maximum signals per token
        active_signals = self._active_signals_by_token.get(token_id, [])
        if len(active_signals) >= self.enhanced_config.max_signals_per_token:
            return {
                "blocked": True,
                "reason": f"Too many active signals for token {token_id} ({len(active_signals)} active)",
            }

        # Check for conflicting signals (opposite sides)
        for signal_id in active_signals:
            existing_wrapper = self._find_signal_in_queues(signal_id)
            if existing_wrapper and existing_wrapper.signal.side != signal.side:
                if self.enhanced_config.conflicting_signal_resolution == "cancel_older":
                    # This would cancel the older signal
                    return {
                        "blocked": False,
                        "action": "cancel_older",
                        "target_signal": signal_id,
                    }
                else:  # queue
                    return {
                        "blocked": True,
                        "reason": f"Conflicting signal exists: {signal_id} ({existing_wrapper.signal.side})",
                    }

        return {"blocked": False}

    def _find_signal_in_queues(self, signal_id: str) -> EnhancedSignalWrapper | None:
        """Find a signal in the priority queues."""
        for priority_queue in self._priority_queues.values():
            if signal_id in priority_queue:
                return priority_queue[signal_id]
        return None

    def _capture_market_snapshot(self, signal: TradingSignal) -> dict[str, Any]:
        """Capture relevant market context at signal creation time."""
        current_time = time.time()
        token_id = signal.token_id

        return {
            "timestamp": current_time,
            "token_id": token_id,
            "market_slug": signal.market_slug,
            "recent_volatility": self._calculate_volatility_score(token_id),
            "market_condition": self._market_conditions.get(
                token_id, MarketCondition.NORMAL
            ).value,
            "active_signal_count": len(self._active_signals_by_token.get(token_id, [])),
            "last_price": list(self._price_history.get(token_id, deque()))[-1:]
            or [0.0],
        }

    def _link_parent_child_signals(self, parent_id: str, child_id: str):
        """Link parent and child signals for tracking dependencies."""
        parent_wrapper = self._find_signal_in_queues(parent_id)
        if parent_wrapper:
            parent_wrapper.metadata.child_signal_ids.append(child_id)
            self._signal_correlations[parent_id].append(child_id)

    async def _process_enhanced_signal_async(
        self, wrapper: EnhancedSignalWrapper
    ) -> None:
        """Process enhanced signal with priority awareness and advanced monitoring."""
        signal_id = wrapper.metadata.signal_id
        start_time = time.time()

        # Calculate queue wait time
        queue_wait_time = start_time - wrapper.metadata.created_at
        wrapper.metadata.queue_wait_time = queue_wait_time

        # Update metrics
        self._update_queue_wait_metrics(queue_wait_time)

        # Check for alerts
        await self._check_processing_alerts(wrapper)

        # Priority-aware processing with semaphore
        async with self._processing_semaphore:
            current_time = time.time()

            # Check various expiration conditions
            if await self._is_signal_expired(wrapper, current_time):
                return

            # Move to processing state
            await self._transition_to_processing(wrapper, current_time)

            try:
                # Enhanced processing with context
                await self._execute_enhanced_signal(wrapper)

                # Mark as successfully processed
                await self._handle_successful_processing(wrapper)

            except Exception as e:
                logger.error(f"Error processing enhanced signal {signal_id}: {e}")
                await self._handle_enhanced_processing_error(wrapper, str(e))

    async def _is_signal_expired(
        self, wrapper: EnhancedSignalWrapper, current_time: float
    ) -> bool:
        """Check if signal has expired using multiple criteria."""
        metadata = wrapper.metadata

        # Standard timeout check
        if current_time >= metadata.expires_at:
            await self._handle_expired_signal(wrapper)
            return True

        # Processing deadline check (stricter than expiration)
        if current_time >= metadata.processing_deadline:
            await self._handle_expired_signal(wrapper)
            return True

        # Market condition-based early expiration
        if metadata.market_condition == MarketCondition.VOLATILE:
            # In volatile conditions, expire signals more aggressively
            time_ratio = (
                current_time - metadata.created_at
            ) / metadata.adjusted_timeout
            if time_ratio > 0.7:  # 70% of timeout in volatile conditions
                logger.debug(
                    f"Signal {wrapper.metadata.signal_id} expired early due to volatile conditions"
                )
                await self._handle_expired_signal(wrapper)
                return True

        return False

    async def _transition_to_processing(
        self, wrapper: EnhancedSignalWrapper, current_time: float
    ):
        """Transition signal to processing state with comprehensive timestamp tracking."""
        signal_id = wrapper.metadata.signal_id
        priority = wrapper.metadata.priority

        # Update timestamps
        wrapper.metadata.update_timestamp("processing_started", current_time)

        with self._lock:
            # Remove from priority queue
            if signal_id in self._priority_queues[priority]:
                del self._priority_queues[priority][signal_id]
                self._processing_signals[signal_id] = wrapper
                wrapper.metadata.status = SignalStatus.PROCESSING
            else:
                # Signal was already processed or expired
                raise ValueError(f"Signal {signal_id} not found in priority queue")

    async def _execute_enhanced_signal(self, wrapper: EnhancedSignalWrapper):
        """Execute signal with comprehensive timestamp tracking."""
        metadata = wrapper.metadata
        signal = wrapper.signal

        # Start risk check
        metadata.update_timestamp("risk_check_started")

        try:
            # Perform risk checks (simulate with delay)
            await asyncio.sleep(0.01)  # Simulate risk check time

            # Complete risk check
            metadata.update_timestamp("risk_check_completed")

            # Start execution
            metadata.update_timestamp("execution_started")

            # Call the original signal processor (from parent class)
            if hasattr(self, "_signal_processor") and self._signal_processor:
                self._signal_processor(signal)

            # Complete execution
            metadata.update_timestamp("execution_completed")

        except Exception as e:
            # Track failed execution
            metadata.execution_attempts += 1
            logger.error(f"Signal execution failed: {e}")
            raise

    async def _handle_successful_processing(self, wrapper: EnhancedSignalWrapper):
        """Handle successful signal processing with metrics update."""
        metadata = wrapper.metadata
        signal_id = metadata.signal_id

        with self._lock:
            # Remove from processing signals
            if signal_id in self._processing_signals:
                del self._processing_signals[signal_id]

            # Update status
            metadata.status = SignalStatus.COMPLETED

            # Update performance metrics
            if metadata.get_processing_duration():
                self._enhanced_metrics["avg_processing_time"] = (
                    self._enhanced_metrics["avg_processing_time"]
                    * self._enhanced_metrics["signals_processed"]
                    + metadata.get_processing_duration()
                ) / (self._enhanced_metrics["signals_processed"] + 1)

            self._enhanced_metrics["signals_processed"] += 1

        logger.info(f"Signal {signal_id} processed successfully")

    async def _handle_enhanced_processing_error(
        self, wrapper: EnhancedSignalWrapper, error_msg: str
    ):
        """Handle processing errors with enhanced error tracking."""
        metadata = wrapper.metadata
        signal_id = metadata.signal_id

        with self._lock:
            # Remove from processing
            if signal_id in self._processing_signals:
                del self._processing_signals[signal_id]

            # Update status and metrics
            metadata.status = SignalStatus.FAILED
            self._enhanced_metrics["signals_failed"] += 1

        logger.error(f"Enhanced signal processing failed for {signal_id}: {error_msg}")

    def update_market_data(
        self, token_id: str, price: float, timestamp: float | None = None
    ):
        """Update market data for volatility tracking."""
        if timestamp is None:
            timestamp = time.time()

        # Update price history
        self._price_history[token_id].append(price)

        # Update volatility history
        if len(self._price_history[token_id]) > 1:
            prev_price = list(self._price_history[token_id])[-2]
            volatility = abs(price - prev_price) / prev_price if prev_price != 0 else 0
            self._volatility_history[token_id].append(volatility)

    async def _check_processing_alerts(self, wrapper: EnhancedSignalWrapper):
        """Check for alert conditions during signal processing."""
        if not self.enhanced_config.enable_performance_tracking:
            return

        current_time = time.time()
        alert_key = ""

        # High queue wait time alert
        if (
            wrapper.metadata.queue_wait_time
            > self.enhanced_config.alert_long_queue_wait
        ):
            alert_key = "long_queue_wait"
            await self._send_alert(
                alert_key,
                f"Signal {wrapper.metadata.signal_id} waited {wrapper.metadata.queue_wait_time:.2f}s in queue",
                current_time,
            )

    async def _send_alert(self, alert_key: str, message: str, current_time: float):
        """Send alert with cooldown management."""
        last_alert_time = self._last_alerts.get(alert_key, 0)
        if (current_time - last_alert_time) > self._alert_cooldown:
            logger.warning(f"SIGNAL_ALERT [{alert_key}]: {message}")
            self._last_alerts[alert_key] = current_time

    def _update_queue_wait_metrics(self, queue_wait_time: float):
        """Update queue wait time metrics."""
        current_avg = self._enhanced_metrics["avg_queue_wait_time"]
        # Simple exponential moving average
        self._enhanced_metrics["avg_queue_wait_time"] = (current_avg * 0.9) + (
            queue_wait_time * 0.1
        )


class SignalInterferenceError(Exception):
    """Raised when a signal would interfere with existing signals."""

    pass
