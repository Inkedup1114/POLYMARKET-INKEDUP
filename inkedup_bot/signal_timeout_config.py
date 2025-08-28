"""
Advanced signal timeout configuration system with market-aware and strategy-specific settings.

This module provides a comprehensive configuration system for signal timeouts that adapts to:
- Market conditions and volatility
- Strategy types and requirements
- Time-of-day and market session patterns
- Historical performance data
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from datetime import time as dt_time
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("signal_timeout_config")


class TimeSession(str, Enum):
    """Trading session types affecting timeout behavior with fine-grained periods."""

    PRE_MARKET_EARLY = "pre_market_early"  # 4-6 AM
    PRE_MARKET_LATE = "pre_market_late"  # 6-9 AM
    MARKET_OPEN_FIRST = "market_open_first"  # First 15 minutes
    MARKET_OPEN_EARLY = "market_open_early"  # First hour
    MORNING_SESSION = "morning_session"  # 10 AM - 12 PM
    MIDDAY_SESSION = "midday_session"  # 12 PM - 2 PM
    AFTERNOON_SESSION = "afternoon_session"  # 2 PM - 3 PM
    MARKET_CLOSE_LATE = "market_close_late"  # Last hour
    MARKET_CLOSE_FINAL = "market_close_final"  # Last 15 minutes
    AFTER_HOURS_EARLY = "after_hours_early"  # 4-6 PM
    AFTER_HOURS_LATE = "after_hours_late"  # 6-8 PM
    EVENING_SESSION = "evening_session"  # 8 PM - 12 AM
    OVERNIGHT_EARLY = "overnight_early"  # 12 AM - 4 AM
    OVERNIGHT_LATE = "overnight_late"  # 4 AM - 6 AM
    WEEKEND = "weekend"  # Saturday/Sunday


class StrategyType(str, Enum):
    """Strategy classifications for timeout configuration with sub-categories."""

    # Arbitrage strategies (ultra-fast execution)
    PURE_ARBITRAGE = "pure_arbitrage"  # Pure arbitrage opportunities
    CROSS_MARKET_ARB = "cross_market_arbitrage"  # Cross-market arbitrage
    TEMPORAL_ARB = "temporal_arbitrage"  # Time-based arbitrage

    # Market making strategies
    MARKET_MAKING_TIGHT = "market_making_tight"  # Tight spread MM
    MARKET_MAKING_WIDE = "market_making_wide"  # Wide spread MM
    INVENTORY_MANAGEMENT = "inventory_management"  # Inventory-based MM

    # Momentum strategies
    SHORT_MOMENTUM = "short_momentum"  # Intraday momentum
    MEDIUM_MOMENTUM = "medium_momentum"  # Multi-day momentum
    TREND_FOLLOWING = "trend_following"  # Longer-term trends

    # Mean reversion strategies
    FAST_REVERSION = "fast_reversion"  # Quick mean reversion
    SLOW_REVERSION = "slow_reversion"  # Long-term reversion
    STATISTICAL_REV = "statistical_reversion"  # Stats-based reversion

    # Event-driven strategies
    NEWS_REACTION = "news_reaction"  # Immediate news reaction
    EARNINGS_DRIVEN = "earnings_driven"  # Earnings-based
    EVENT_ANTICIPATION = "event_anticipation"  # Pre-event positioning

    # Complex strategies
    MULTI_LEG_SPREAD = "multi_leg_spread"  # Complex spread strategies
    PORTFOLIO_HEDGE = "portfolio_hedge"  # Portfolio hedging
    RISK_PARITY = "risk_parity"  # Risk parity strategies

    # High-frequency strategies
    MICRO_STRUCTURE = "micro_structure"  # Microstructure-based
    LATENCY_ARBITRAGE = "latency_arbitrage"  # Latency-based
    ORDER_FLOW = "order_flow"  # Order flow strategies


@dataclass
class TimeoutRule:
    """Individual timeout rule with conditions and multipliers."""

    name: str
    description: str
    conditions: dict[str, Any]
    timeout_multiplier: float
    max_timeout: float | None = None
    min_timeout: float | None = None
    priority: int = 0  # Higher number = higher priority


@dataclass
class GranularTimeoutConfig:
    """Ultra-granular timeout configuration for specific conditions."""

    # Time-based granularity (seconds)
    base_timeout_seconds: float
    min_timeout_seconds: float = 1.0
    max_timeout_seconds: float = 300.0

    # Sub-second precision for high-frequency strategies
    microsecond_precision: bool = False

    # Strategy-specific timeouts with priority tiers
    strategy_timeouts: dict[StrategyType, dict[str, float]] = field(
        default_factory=lambda: {
            # Ultra-fast arbitrage strategies
            StrategyType.PURE_ARBITRAGE: {
                "critical": 0.5,
                "high": 1.0,
                "normal": 2.0,
                "low": 5.0,
            },
            StrategyType.LATENCY_ARBITRAGE: {
                "critical": 0.2,
                "high": 0.5,
                "normal": 1.0,
                "low": 2.0,
            },
            StrategyType.CROSS_MARKET_ARB: {
                "critical": 1.0,
                "high": 2.0,
                "normal": 4.0,
                "low": 8.0,
            },
            # Market making strategies
            StrategyType.MARKET_MAKING_TIGHT: {
                "critical": 2.0,
                "high": 5.0,
                "normal": 10.0,
                "low": 20.0,
            },
            StrategyType.MARKET_MAKING_WIDE: {
                "critical": 5.0,
                "high": 10.0,
                "normal": 20.0,
                "low": 40.0,
            },
            # Momentum strategies
            StrategyType.SHORT_MOMENTUM: {
                "critical": 3.0,
                "high": 8.0,
                "normal": 15.0,
                "low": 30.0,
            },
            StrategyType.MEDIUM_MOMENTUM: {
                "critical": 10.0,
                "high": 30.0,
                "normal": 60.0,
                "low": 120.0,
            },
            # Mean reversion strategies
            StrategyType.FAST_REVERSION: {
                "critical": 2.0,
                "high": 5.0,
                "normal": 12.0,
                "low": 25.0,
            },
            StrategyType.SLOW_REVERSION: {
                "critical": 15.0,
                "high": 45.0,
                "normal": 90.0,
                "low": 180.0,
            },
            # Event-driven strategies
            StrategyType.NEWS_REACTION: {
                "critical": 1.0,
                "high": 3.0,
                "normal": 8.0,
                "low": 15.0,
            },
            StrategyType.EVENT_ANTICIPATION: {
                "critical": 30.0,
                "high": 60.0,
                "normal": 120.0,
                "low": 300.0,
            },
        }
    )

    # Session-specific multipliers with granular time periods
    session_multipliers: dict[TimeSession, float] = field(
        default_factory=lambda: {
            TimeSession.PRE_MARKET_EARLY: 1.5,  # Less liquid, longer timeouts
            TimeSession.PRE_MARKET_LATE: 1.2,
            TimeSession.MARKET_OPEN_FIRST: 0.7,  # High volatility, shorter timeouts
            TimeSession.MARKET_OPEN_EARLY: 0.8,
            TimeSession.MORNING_SESSION: 1.0,  # Normal conditions
            TimeSession.MIDDAY_SESSION: 1.1,  # Slightly less active
            TimeSession.AFTERNOON_SESSION: 0.9,  # Active period
            TimeSession.MARKET_CLOSE_LATE: 0.8,  # High activity
            TimeSession.MARKET_CLOSE_FINAL: 0.6,  # Very active, short timeouts
            TimeSession.AFTER_HOURS_EARLY: 1.3,
            TimeSession.AFTER_HOURS_LATE: 1.4,
            TimeSession.EVENING_SESSION: 1.6,
            TimeSession.OVERNIGHT_EARLY: 2.0,  # Low activity, longer timeouts
            TimeSession.OVERNIGHT_LATE: 1.8,
            TimeSession.WEEKEND: 2.5,  # Minimal activity
        }
    )

    # Market condition adjustments
    volatility_multipliers: dict[str, float] = field(
        default_factory=lambda: {
            "ultra_low": 1.8,  # VIX < 12
            "low": 1.4,  # VIX 12-16
            "normal": 1.0,  # VIX 16-25
            "elevated": 0.8,  # VIX 25-35
            "high": 0.6,  # VIX 35-50
            "extreme": 0.4,  # VIX > 50
        }
    )

    # Signal priority multipliers (more granular)
    priority_multipliers: dict[str, float] = field(
        default_factory=lambda: {
            "emergency": 0.1,  # Immediate execution required
            "critical": 0.3,  # Very time-sensitive
            "urgent": 0.5,  # Important but not critical
            "high": 0.7,  # Above normal priority
            "normal": 1.0,  # Standard timeout
            "low": 1.5,  # Can wait longer
            "deferred": 2.0,  # Low priority signals
            "background": 3.0,  # Background processing
        }
    )


@dataclass
class SessionTimeoutConfig:
    """Enhanced timeout configuration for specific trading sessions."""

    session: TimeSession
    base_multiplier: float = 1.0
    strategy_multipliers: dict[StrategyType, float] = field(default_factory=dict)
    volatility_adjustments: dict[str, float] = field(default_factory=dict)
    max_concurrent_signals: int = 10
    priority_boost_factor: float = 1.0

    # Enhanced granular configuration
    granular_config: GranularTimeoutConfig | None = None


@dataclass
class MarketSectorConfig:
    """Configuration specific to market sectors."""

    sector_name: str
    base_timeout_seconds: float
    volatility_sensitivity: float = 1.0  # Multiplier for volatility adjustments
    liquidity_factor: float = 1.0  # Higher = longer timeouts for less liquid markets
    complexity_factor: float = 1.0  # Higher = longer timeouts for complex strategies


class AdvancedTimeoutConfigManager:
    """
    Advanced timeout configuration manager with adaptive learning capabilities.

    Features:
    - Time-of-day aware timeout adjustment
    - Strategy-specific timeout profiles
    - Market sector considerations
    - Volatility-based dynamic adjustments
    - Performance feedback integration
    - Rule-based timeout logic
    """

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or Path("config/signal_timeouts.json")

        # Default configurations
        self._session_configs: dict[TimeSession, SessionTimeoutConfig] = {}
        self._sector_configs: dict[str, MarketSectorConfig] = {}
        self._strategy_base_timeouts: dict[StrategyType, float] = {}
        self._timeout_rules: list[TimeoutRule] = []

        # Performance tracking for adaptive learning
        self._performance_history: dict[str, list[dict[str, Any]]] = {}
        self._success_rates: dict[str, float] = {}

        # Initialize default configurations
        self._initialize_default_configs()

        # Load configuration if file exists
        if self.config_path.exists():
            self.load_configuration()

        logger.info(
            f"AdvancedTimeoutConfigManager initialized with config: {self.config_path}"
        )

    def _initialize_default_configs(self) -> None:
        """Initialize default timeout configurations."""

        # Default session configurations (using granular time sessions)
        self._session_configs = {
            TimeSession.PRE_MARKET_EARLY: SessionTimeoutConfig(
                session=TimeSession.PRE_MARKET_EARLY,
                base_multiplier=1.8,  # Very long timeouts early pre-market
                max_concurrent_signals=3,
            ),
            TimeSession.PRE_MARKET_LATE: SessionTimeoutConfig(
                session=TimeSession.PRE_MARKET_LATE,
                base_multiplier=1.3,  # Moderate timeouts late pre-market
                max_concurrent_signals=8,
            ),
            TimeSession.MARKET_OPEN_FIRST: SessionTimeoutConfig(
                session=TimeSession.MARKET_OPEN_FIRST,
                base_multiplier=0.5,  # Very short timeouts first 15 min (high volatility)
                max_concurrent_signals=25,
            ),
            TimeSession.MARKET_OPEN_EARLY: SessionTimeoutConfig(
                session=TimeSession.MARKET_OPEN_EARLY,
                base_multiplier=0.7,  # Short timeouts first hour
                max_concurrent_signals=20,
            ),
            TimeSession.MORNING_SESSION: SessionTimeoutConfig(
                session=TimeSession.MORNING_SESSION,
                base_multiplier=1.0,  # Standard timeouts
                max_concurrent_signals=15,
            ),
            TimeSession.MIDDAY_SESSION: SessionTimeoutConfig(
                session=TimeSession.MIDDAY_SESSION,
                base_multiplier=1.1,  # Slightly longer midday
                max_concurrent_signals=12,
            ),
            TimeSession.AFTERNOON_SESSION: SessionTimeoutConfig(
                session=TimeSession.AFTERNOON_SESSION,
                base_multiplier=0.9,  # Active afternoon session
                max_concurrent_signals=18,
            ),
            TimeSession.MARKET_CLOSE_LATE: SessionTimeoutConfig(
                session=TimeSession.MARKET_CLOSE_LATE,
                base_multiplier=0.8,  # Shorter timeouts near close
                max_concurrent_signals=15,
            ),
            TimeSession.MARKET_CLOSE_FINAL: SessionTimeoutConfig(
                session=TimeSession.MARKET_CLOSE_FINAL,
                base_multiplier=0.4,  # Very short for final 15 min
                max_concurrent_signals=30,
            ),
            TimeSession.AFTER_HOURS_EARLY: SessionTimeoutConfig(
                session=TimeSession.AFTER_HOURS_EARLY,
                base_multiplier=1.6,  # Longer timeouts after hours
                max_concurrent_signals=8,
            ),
            TimeSession.AFTER_HOURS_LATE: SessionTimeoutConfig(
                session=TimeSession.AFTER_HOURS_LATE,
                base_multiplier=1.8,  # Even longer later
                max_concurrent_signals=5,
            ),
            TimeSession.EVENING_SESSION: SessionTimeoutConfig(
                session=TimeSession.EVENING_SESSION,
                base_multiplier=2.2,  # Long timeouts evening
                max_concurrent_signals=3,
            ),
            TimeSession.OVERNIGHT_EARLY: SessionTimeoutConfig(
                session=TimeSession.OVERNIGHT_EARLY,
                base_multiplier=2.8,  # Very long overnight
                max_concurrent_signals=2,
            ),
            TimeSession.OVERNIGHT_LATE: SessionTimeoutConfig(
                session=TimeSession.OVERNIGHT_LATE,
                base_multiplier=2.5,  # Long but slightly shorter
                max_concurrent_signals=2,
            ),
            TimeSession.WEEKEND: SessionTimeoutConfig(
                session=TimeSession.WEEKEND,
                base_multiplier=3.5,  # Longest timeouts on weekend
                max_concurrent_signals=1,
            ),
        }

        # Default strategy base timeouts with granular categories (in seconds)
        self._strategy_base_timeouts = {
            # Ultra-fast arbitrage strategies
            StrategyType.PURE_ARBITRAGE: 2.0,  # Immediate execution
            StrategyType.LATENCY_ARBITRAGE: 1.0,  # Ultra-fast
            StrategyType.CROSS_MARKET_ARB: 4.0,  # Cross-market timing
            StrategyType.TEMPORAL_ARB: 3.0,  # Time-based arbitrage
            # Market making strategies
            StrategyType.MARKET_MAKING_TIGHT: 15.0,  # Tight spreads need speed
            StrategyType.MARKET_MAKING_WIDE: 45.0,  # Wide spreads can wait
            StrategyType.INVENTORY_MANAGEMENT: 30.0,  # Inventory-based timing
            # Momentum strategies
            StrategyType.SHORT_MOMENTUM: 8.0,  # Very fast for intraday
            StrategyType.MEDIUM_MOMENTUM: 35.0,  # Multi-day positioning
            StrategyType.TREND_FOLLOWING: 90.0,  # Longer-term trends
            # Mean reversion strategies
            StrategyType.FAST_REVERSION: 12.0,  # Quick reversions
            StrategyType.SLOW_REVERSION: 120.0,  # Long-term reversions
            StrategyType.STATISTICAL_REV: 60.0,  # Statistical timing
            # Event-driven strategies
            StrategyType.NEWS_REACTION: 5.0,  # Immediate news response
            StrategyType.EARNINGS_DRIVEN: 20.0,  # Earnings timing
            StrategyType.EVENT_ANTICIPATION: 180.0,  # Pre-positioning
            # Complex strategies
            StrategyType.MULTI_LEG_SPREAD: 25.0,  # Complex execution
            StrategyType.PORTFOLIO_HEDGE: 60.0,  # Portfolio timing
            StrategyType.RISK_PARITY: 90.0,  # Risk management
            # High-frequency strategies
            StrategyType.MICRO_STRUCTURE: 3.0,  # Microstructure timing
            StrategyType.ORDER_FLOW: 6.0,  # Order flow analysis
        }

        # Default market sector configurations
        self._sector_configs = {
            "politics": MarketSectorConfig(
                sector_name="politics",
                base_timeout_seconds=30.0,
                volatility_sensitivity=1.2,
                complexity_factor=1.3,
            ),
            "sports": MarketSectorConfig(
                sector_name="sports",
                base_timeout_seconds=25.0,
                volatility_sensitivity=0.8,
                liquidity_factor=1.1,
            ),
            "crypto": MarketSectorConfig(
                sector_name="crypto",
                base_timeout_seconds=15.0,
                volatility_sensitivity=1.5,
                liquidity_factor=0.9,
            ),
            "economics": MarketSectorConfig(
                sector_name="economics",
                base_timeout_seconds=45.0,
                volatility_sensitivity=1.1,
                complexity_factor=1.4,
            ),
        }

        # Initialize default timeout rules
        self._initialize_default_rules()

    def _initialize_default_rules(self) -> None:
        """Initialize default timeout rules."""

        self._timeout_rules = [
            # Volatility-based rules
            TimeoutRule(
                name="high_volatility_reduction",
                description="Reduce timeout in high volatility conditions",
                conditions={"volatility_score": {"min": 0.7}},
                timeout_multiplier=0.5,
                priority=100,
            ),
            TimeoutRule(
                name="low_volatility_extension",
                description="Extend timeout in low volatility conditions",
                conditions={"volatility_score": {"max": 0.2}},
                timeout_multiplier=1.5,
                priority=90,
            ),
            # Signal count-based rules
            TimeoutRule(
                name="high_signal_load_reduction",
                description="Reduce timeout when many signals are queued",
                conditions={"pending_signals": {"min": 10}},
                timeout_multiplier=0.7,
                priority=80,
            ),
            # Priority-based rules
            TimeoutRule(
                name="critical_priority_boost",
                description="Significantly reduce timeout for critical signals",
                conditions={"priority": "critical"},
                timeout_multiplier=0.3,
                max_timeout=10.0,
                priority=200,
            ),
            TimeoutRule(
                name="low_priority_extension",
                description="Extend timeout for low priority signals",
                conditions={"priority": "low"},
                timeout_multiplier=2.0,
                priority=50,
            ),
            # Strategy-specific rules
            TimeoutRule(
                name="arbitrage_fast_execution",
                description="Very short timeouts for arbitrage opportunities",
                conditions={"strategy_type": "arbitrage"},
                timeout_multiplier=0.4,
                max_timeout=8.0,
                priority=150,
            ),
            TimeoutRule(
                name="statistical_patience",
                description="Allow longer timeouts for statistical strategies",
                conditions={"strategy_type": "statistical"},
                timeout_multiplier=1.8,
                priority=60,
            ),
            # Market condition rules
            TimeoutRule(
                name="market_open_urgency",
                description="Reduce timeouts at market open",
                conditions={"time_session": "market_open"},
                timeout_multiplier=0.6,
                priority=120,
            ),
            TimeoutRule(
                name="after_hours_patience",
                description="Extend timeouts after hours",
                conditions={"time_session": "after_hours"},
                timeout_multiplier=2.5,
                priority=110,
            ),
            # Performance-based rules
            TimeoutRule(
                name="poor_performance_reduction",
                description="Reduce timeout for strategies with poor recent performance",
                conditions={"recent_success_rate": {"max": 0.5}},
                timeout_multiplier=0.8,
                priority=70,
            ),
            TimeoutRule(
                name="excellent_performance_boost",
                description="Extend timeout for high-performing strategies",
                conditions={"recent_success_rate": {"min": 0.9}},
                timeout_multiplier=1.3,
                priority=75,
            ),
        ]

        # Sort rules by priority (descending)
        self._timeout_rules.sort(key=lambda r: r.priority, reverse=True)

    def calculate_timeout(
        self,
        base_timeout: float,
        strategy_type: StrategyType | None = None,
        market_sector: str | None = None,
        priority: str = "normal",
        volatility_score: float = 0.0,
        pending_signals: int = 0,
        current_time: datetime | None = None,
        signal_context: dict[str, Any] | None = None,
    ) -> float:
        """
        Calculate optimal timeout based on multiple factors and rules.

        Args:
            base_timeout: Base timeout value
            strategy_type: Type of trading strategy
            market_sector: Market sector classification
            priority: Signal priority level
            volatility_score: Current market volatility (0.0 to 1.0)
            pending_signals: Number of pending signals
            current_time: Current timestamp (defaults to now)
            signal_context: Additional context for rule evaluation

        Returns:
            Calculated timeout in seconds
        """
        if current_time is None:
            current_time = datetime.now(UTC)

        # Use granular configuration approach for enhanced precision
        if (
            strategy_type
            and hasattr(self, "_use_granular_config")
            and self._use_granular_config
        ):
            return self._calculate_granular_timeout(
                strategy_type, priority, current_time, volatility_score, signal_context
            )

        # Start with base timeout
        calculated_timeout = base_timeout

        # Apply strategy-specific base timeout if available
        if strategy_type and strategy_type in self._strategy_base_timeouts:
            calculated_timeout = self._strategy_base_timeouts[strategy_type]

        # Apply session multiplier with enhanced granularity
        session = self._get_current_session(current_time)
        session_config = self._session_configs.get(session)
        if session_config:
            calculated_timeout *= session_config.base_multiplier

            # Use granular config if available
            if session_config.granular_config:
                granular = session_config.granular_config
                session_mult = granular.session_multipliers.get(session, 1.0)
                calculated_timeout *= session_mult

        # Apply sector configuration
        if market_sector and market_sector in self._sector_configs:
            sector_config = self._sector_configs[market_sector]
            calculated_timeout = max(
                calculated_timeout, sector_config.base_timeout_seconds
            )
            calculated_timeout *= (
                sector_config.volatility_sensitivity * volatility_score + 1.0
            )
            calculated_timeout *= sector_config.complexity_factor

        # Apply timeout rules
        rule_context = {
            "strategy_type": strategy_type.value if strategy_type else None,
            "market_sector": market_sector,
            "priority": priority,
            "volatility_score": volatility_score,
            "pending_signals": pending_signals,
            "time_session": session.value,
            "current_time": current_time,
            **(signal_context or {}),
        }

        # Calculate success rate for performance-based rules
        if strategy_type:
            strategy_key = f"{strategy_type.value}_{market_sector or 'default'}"
            rule_context["recent_success_rate"] = self._get_recent_success_rate(
                strategy_key
            )

        # Apply rules in priority order
        applied_rules = []
        for rule in self._timeout_rules:
            if self._rule_matches(rule, rule_context):
                calculated_timeout *= rule.timeout_multiplier
                applied_rules.append(rule.name)

                # Apply rule-specific limits
                if rule.max_timeout is not None:
                    calculated_timeout = min(calculated_timeout, rule.max_timeout)
                if rule.min_timeout is not None:
                    calculated_timeout = max(calculated_timeout, rule.min_timeout)

        # Final bounds checking
        calculated_timeout = max(calculated_timeout, 1.0)  # Minimum 1 second
        calculated_timeout = min(calculated_timeout, 300.0)  # Maximum 5 minutes

        logger.debug(
            f"Timeout calculated: {calculated_timeout:.2f}s "
            f"(base: {base_timeout:.2f}s, rules: {applied_rules})"
        )

        return calculated_timeout

    def _get_current_session(self, current_time: datetime) -> TimeSession:
        """Determine current trading session based on time."""
        # Convert to market timezone (assuming US Eastern)
        market_time = current_time.time()

        # Define session boundaries (US Eastern time)
        if dt_time(4, 0) <= market_time < dt_time(9, 30):
            return TimeSession.PRE_MARKET_LATE
        elif dt_time(9, 30) <= market_time < dt_time(10, 30):
            return TimeSession.MARKET_OPEN_EARLY
        elif dt_time(10, 30) <= market_time < dt_time(15, 0):
            return TimeSession.MIDDAY_SESSION
        elif dt_time(15, 0) <= market_time < dt_time(16, 0):
            return TimeSession.MARKET_CLOSE_LATE
        elif dt_time(16, 0) <= market_time < dt_time(20, 0):
            return TimeSession.AFTER_HOURS_EARLY
        else:
            return TimeSession.OVERNIGHT_EARLY

    def _calculate_granular_timeout(
        self,
        strategy_type: StrategyType,
        priority: str,
        current_time: datetime,
        volatility_score: float,
        signal_context: dict[str, Any] | None = None,
    ) -> float:
        """Calculate timeout using ultra-granular configuration approach."""

        # Create default granular config if not exists
        granular_config = GranularTimeoutConfig(base_timeout_seconds=30.0)

        # Get strategy-specific timeout based on priority
        if strategy_type in granular_config.strategy_timeouts:
            strategy_timeouts = granular_config.strategy_timeouts[strategy_type]
            calculated_timeout = strategy_timeouts.get(
                priority, strategy_timeouts.get("normal", 30.0)
            )
        else:
            calculated_timeout = granular_config.base_timeout_seconds

        # Apply granular session multiplier
        session = self._get_granular_session(current_time)
        session_multiplier = granular_config.session_multipliers.get(session, 1.0)
        calculated_timeout *= session_multiplier

        # Apply granular priority multiplier
        priority_multiplier = granular_config.priority_multipliers.get(priority, 1.0)
        calculated_timeout *= priority_multiplier

        # Apply volatility adjustment with granular levels
        volatility_level = self._get_volatility_level(volatility_score)
        volatility_multiplier = granular_config.volatility_multipliers.get(
            volatility_level, 1.0
        )
        calculated_timeout *= volatility_multiplier

        # Apply bounds
        calculated_timeout = max(
            calculated_timeout, granular_config.min_timeout_seconds
        )
        calculated_timeout = min(
            calculated_timeout, granular_config.max_timeout_seconds
        )

        # Sub-second precision for high-frequency strategies
        if granular_config.microsecond_precision and calculated_timeout < 1.0:
            calculated_timeout = round(calculated_timeout, 6)  # Microsecond precision
        else:
            calculated_timeout = round(calculated_timeout, 3)  # Millisecond precision

        return calculated_timeout

    def _get_granular_session(self, current_time: datetime) -> TimeSession:
        """Get granular trading session with fine-grained time periods."""
        market_time = current_time.time()
        weekday = current_time.weekday()

        # Weekend handling
        if weekday >= 5:  # Saturday = 5, Sunday = 6
            return TimeSession.WEEKEND

        # Fine-grained session detection
        if dt_time(4, 0) <= market_time < dt_time(6, 0):
            return TimeSession.PRE_MARKET_EARLY
        elif dt_time(6, 0) <= market_time < dt_time(9, 30):
            return TimeSession.PRE_MARKET_LATE
        elif dt_time(9, 30) <= market_time < dt_time(9, 45):
            return TimeSession.MARKET_OPEN_FIRST
        elif dt_time(9, 45) <= market_time < dt_time(10, 30):
            return TimeSession.MARKET_OPEN_EARLY
        elif dt_time(10, 30) <= market_time < dt_time(12, 0):
            return TimeSession.MORNING_SESSION
        elif dt_time(12, 0) <= market_time < dt_time(14, 0):
            return TimeSession.MIDDAY_SESSION
        elif dt_time(14, 0) <= market_time < dt_time(15, 0):
            return TimeSession.AFTERNOON_SESSION
        elif dt_time(15, 0) <= market_time < dt_time(15, 45):
            return TimeSession.MARKET_CLOSE_LATE
        elif dt_time(15, 45) <= market_time < dt_time(16, 0):
            return TimeSession.MARKET_CLOSE_FINAL
        elif dt_time(16, 0) <= market_time < dt_time(18, 0):
            return TimeSession.AFTER_HOURS_EARLY
        elif dt_time(18, 0) <= market_time < dt_time(20, 0):
            return TimeSession.AFTER_HOURS_LATE
        elif dt_time(20, 0) <= market_time < dt_time(23, 59, 59):
            return TimeSession.EVENING_SESSION
        elif dt_time(0, 0) <= market_time < dt_time(2, 0):
            return TimeSession.OVERNIGHT_EARLY
        else:
            return TimeSession.OVERNIGHT_LATE

    def _get_volatility_level(self, volatility_score: float) -> str:
        """Convert volatility score to granular volatility level."""
        if volatility_score < 0.1:
            return "ultra_low"
        elif volatility_score < 0.2:
            return "low"
        elif volatility_score < 0.4:
            return "normal"
        elif volatility_score < 0.6:
            return "elevated"
        elif volatility_score < 0.8:
            return "high"
        else:
            return "extreme"

    def enable_granular_mode(self, enabled: bool = True) -> None:
        """Enable or disable granular timeout calculations."""
        self._use_granular_config = enabled
        logger.info(f"Granular timeout mode {'enabled' if enabled else 'disabled'}")

    def _rule_matches(self, rule: TimeoutRule, context: dict[str, Any]) -> bool:
        """Check if a timeout rule matches the current context."""
        for condition_key, condition_value in rule.conditions.items():
            context_value = context.get(condition_key)

            if context_value is None:
                continue

            # Handle different condition types
            if isinstance(condition_value, dict):
                # Range conditions (min/max)
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

    def _get_recent_success_rate(
        self, strategy_key: str, lookback_hours: int = 24
    ) -> float:
        """Get recent success rate for performance-based rules."""
        if strategy_key not in self._performance_history:
            return 0.5  # Default neutral success rate

        recent_history = self._performance_history[strategy_key]
        if not recent_history:
            return 0.5

        # Filter to recent history
        cutoff_time = datetime.now(UTC).timestamp() - (lookback_hours * 3600)
        recent_signals = [
            signal
            for signal in recent_history
            if signal.get("timestamp", 0) > cutoff_time
        ]

        if not recent_signals:
            return 0.5

        success_count = sum(
            1 for signal in recent_signals if signal.get("success", False)
        )
        return success_count / len(recent_signals)

    def record_signal_outcome(
        self,
        strategy_type: StrategyType | None,
        market_sector: str | None,
        success: bool,
        execution_time: float,
        timeout_used: float,
        additional_context: dict[str, Any] | None = None,
    ) -> None:
        """Record signal execution outcome for adaptive learning."""
        if not strategy_type:
            return

        strategy_key = f"{strategy_type.value}_{market_sector or 'default'}"

        outcome_record = {
            "timestamp": datetime.now(UTC).timestamp(),
            "success": success,
            "execution_time": execution_time,
            "timeout_used": timeout_used,
            "timeout_efficiency": (
                execution_time / timeout_used if timeout_used > 0 else 0
            ),
            **(additional_context or {}),
        }

        if strategy_key not in self._performance_history:
            self._performance_history[strategy_key] = []

        self._performance_history[strategy_key].append(outcome_record)

        # Keep only recent history (last 1000 records per strategy)
        if len(self._performance_history[strategy_key]) > 1000:
            self._performance_history[strategy_key] = self._performance_history[
                strategy_key
            ][-1000:]

        # Update success rate cache
        self._success_rates[strategy_key] = self._get_recent_success_rate(strategy_key)

    def get_optimal_max_concurrent(self, current_time: datetime | None = None) -> int:
        """Get optimal maximum concurrent signals based on current session."""
        if current_time is None:
            current_time = datetime.now(UTC)

        session = self._get_current_session(current_time)
        session_config = self._session_configs.get(session)

        return session_config.max_concurrent_signals if session_config else 10

    def add_custom_rule(self, rule: TimeoutRule) -> None:
        """Add a custom timeout rule."""
        self._timeout_rules.append(rule)
        # Re-sort by priority
        self._timeout_rules.sort(key=lambda r: r.priority, reverse=True)
        logger.info(f"Added custom timeout rule: {rule.name}")

    def save_configuration(self) -> None:
        """Save current configuration to file."""
        config_data = {
            "session_configs": {
                session.value: {
                    "base_multiplier": config.base_multiplier,
                    "max_concurrent_signals": config.max_concurrent_signals,
                    "priority_boost_factor": config.priority_boost_factor,
                    "strategy_multipliers": {
                        k.value if isinstance(k, StrategyType) else k: v
                        for k, v in config.strategy_multipliers.items()
                    },
                    "volatility_adjustments": config.volatility_adjustments,
                }
                for session, config in self._session_configs.items()
            },
            "strategy_base_timeouts": {
                strategy.value: timeout
                for strategy, timeout in self._strategy_base_timeouts.items()
            },
            "sector_configs": {
                sector: {
                    "base_timeout_seconds": config.base_timeout_seconds,
                    "volatility_sensitivity": config.volatility_sensitivity,
                    "liquidity_factor": config.liquidity_factor,
                    "complexity_factor": config.complexity_factor,
                }
                for sector, config in self._sector_configs.items()
            },
            "timeout_rules": [
                {
                    "name": rule.name,
                    "description": rule.description,
                    "conditions": rule.conditions,
                    "timeout_multiplier": rule.timeout_multiplier,
                    "max_timeout": rule.max_timeout,
                    "min_timeout": rule.min_timeout,
                    "priority": rule.priority,
                }
                for rule in self._timeout_rules
            ],
        }

        # Ensure config directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Save configuration
        with open(self.config_path, "w") as f:
            json.dump(config_data, f, indent=2, default=str)

        logger.info(f"Configuration saved to {self.config_path}")

    def load_configuration(self) -> None:
        """Load configuration from file."""
        try:
            with open(self.config_path) as f:
                config_data = json.load(f)

            # Load session configs
            if "session_configs" in config_data:
                for session_name, session_data in config_data[
                    "session_configs"
                ].items():
                    session = TimeSession(session_name)
                    self._session_configs[session] = SessionTimeoutConfig(
                        session=session,
                        base_multiplier=session_data.get("base_multiplier", 1.0),
                        max_concurrent_signals=session_data.get(
                            "max_concurrent_signals", 10
                        ),
                        priority_boost_factor=session_data.get(
                            "priority_boost_factor", 1.0
                        ),
                        strategy_multipliers={
                            StrategyType(k): v
                            for k, v in session_data.get(
                                "strategy_multipliers", {}
                            ).items()
                        },
                        volatility_adjustments=session_data.get(
                            "volatility_adjustments", {}
                        ),
                    )

            # Load strategy timeouts
            if "strategy_base_timeouts" in config_data:
                self._strategy_base_timeouts = {
                    StrategyType(k): v
                    for k, v in config_data["strategy_base_timeouts"].items()
                }

            # Load sector configs
            if "sector_configs" in config_data:
                for sector_name, sector_data in config_data["sector_configs"].items():
                    self._sector_configs[sector_name] = MarketSectorConfig(
                        sector_name=sector_name,
                        base_timeout_seconds=sector_data.get(
                            "base_timeout_seconds", 30.0
                        ),
                        volatility_sensitivity=sector_data.get(
                            "volatility_sensitivity", 1.0
                        ),
                        liquidity_factor=sector_data.get("liquidity_factor", 1.0),
                        complexity_factor=sector_data.get("complexity_factor", 1.0),
                    )

            # Load timeout rules
            if "timeout_rules" in config_data:
                self._timeout_rules = [
                    TimeoutRule(
                        name=rule_data["name"],
                        description=rule_data["description"],
                        conditions=rule_data["conditions"],
                        timeout_multiplier=rule_data["timeout_multiplier"],
                        max_timeout=rule_data.get("max_timeout"),
                        min_timeout=rule_data.get("min_timeout"),
                        priority=rule_data.get("priority", 0),
                    )
                    for rule_data in config_data["timeout_rules"]
                ]
                # Sort by priority
                self._timeout_rules.sort(key=lambda r: r.priority, reverse=True)

            logger.info(f"Configuration loaded from {self.config_path}")

        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            logger.info("Using default configuration")

    def get_performance_summary(self) -> dict[str, Any]:
        """Get performance summary for all tracked strategies."""
        summary = {}

        for strategy_key, history in self._performance_history.items():
            if not history:
                continue

            recent_history = history[-100:]  # Last 100 signals

            success_rate = sum(
                1 for h in recent_history if h.get("success", False)
            ) / len(recent_history)
            avg_execution_time = sum(
                h.get("execution_time", 0) for h in recent_history
            ) / len(recent_history)
            avg_timeout_efficiency = sum(
                h.get("timeout_efficiency", 0) for h in recent_history
            ) / len(recent_history)

            summary[strategy_key] = {
                "total_signals": len(history),
                "recent_success_rate": success_rate,
                "avg_execution_time": avg_execution_time,
                "timeout_efficiency": avg_timeout_efficiency,
                "last_signal": (
                    max(h.get("timestamp", 0) for h in recent_history)
                    if recent_history
                    else 0
                ),
            }

        return summary
