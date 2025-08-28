"""
Enhanced trading engine with advanced signal timeout handling and market-aware processing.

This module extends the existing trading engine with sophisticated signal management features:
- Market volatility-aware timeout adjustment
- Advanced signal interference prevention
- Comprehensive cleanup management
- Adaptive timeout configuration
- Performance monitoring and alerting
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .config import BotConfig
from .engine import TradingEngine
from .enhanced_signal_manager import (
    EnhancedSignalManager,
    EnhancedSignalManagerConfig,
    MarketCondition,
    SignalPriority,
)
from .order_client import OrderClient
from .risk import RiskManager
from .signal_cleanup_manager import CleanupConfig, SignalCleanupManager
from .signal_timeout_config import (
    AdvancedTimeoutConfigManager,
    StrategyType,
    TimeoutRule,
)
from .signals import TradingSignal
from .state import StateManager

logger = logging.getLogger("enhanced_trading_engine")


class EnhancedTradingEngine(TradingEngine):
    """
    Enhanced trading engine with advanced signal processing capabilities.

    Key enhancements over base TradingEngine:
    - Market volatility-aware signal timeout adjustment
    - Advanced signal interference detection and prevention
    - Intelligent cleanup management
    - Adaptive timeout configuration based on market conditions
    - Comprehensive performance monitoring and alerting
    - Strategy-specific timeout optimization
    """

    def __init__(self, cfg: BotConfig):
        # Initialize base components
        self.cfg = cfg
        self.state = StateManager()
        self.order_client = OrderClient(self.cfg, self.state)
        self.risk = RiskManager(self.cfg, self.order_client, self.state)
        self._initialized = False

        # Enhanced signal management components
        self._init_enhanced_signal_management()

        # Market data tracking for volatility analysis
        self._market_data_history: dict[str, list[Any]] = {}
        self._last_market_update: dict[str, float] = {}

        # Performance tracking
        self._strategy_performance: dict[str, dict[str, Any]] = {}

        logger.info("EnhancedTradingEngine initialized with advanced signal management")

    def _init_enhanced_signal_management(self) -> None:
        """Initialize enhanced signal management components."""

        # Enhanced signal manager configuration
        enhanced_config = EnhancedSignalManagerConfig(
            # Base timeout settings from config
            default_signal_timeout=getattr(
                self.cfg, "signal_default_timeout_seconds", 30.0
            ),
            spread_signal_timeout=getattr(
                self.cfg, "signal_spread_timeout_seconds", 15.0
            ),
            complement_signal_timeout=getattr(
                self.cfg, "signal_complement_timeout_seconds", 45.0
            ),
            market_making_signal_timeout=getattr(
                self.cfg, "signal_market_making_timeout_seconds", 60.0
            ),
            # Enhanced features
            enable_interference_detection=getattr(
                self.cfg, "signal_enable_interference_detection", True
            ),
            enable_performance_tracking=getattr(
                self.cfg, "signal_enable_performance_tracking", True
            ),
            enable_market_condition_tracking=getattr(
                self.cfg, "signal_enable_market_condition_tracking", True
            ),
            # Cleanup settings
            cleanup_interval=getattr(self.cfg, "signal_cleanup_interval_seconds", 5.0),
            max_concurrent_signals=getattr(self.cfg, "signal_max_concurrent", 15),
            # Interference prevention
            max_signals_per_token=getattr(self.cfg, "signal_max_per_token", 3),
            min_signal_spacing_seconds=getattr(
                self.cfg, "signal_min_spacing_seconds", 1.0
            ),
            # Performance thresholds
            alert_high_expiration_rate=getattr(
                self.cfg, "signal_alert_expiration_rate", 0.3
            ),
            alert_long_queue_wait=getattr(self.cfg, "signal_alert_queue_wait", 5.0),
        )

        # Initialize enhanced signal manager
        self.enhanced_signal_manager = EnhancedSignalManager(enhanced_config)
        self.enhanced_signal_manager.set_signal_processor(self._process_enhanced_signal)

        # Initialize cleanup manager
        cleanup_config = CleanupConfig(
            cleanup_interval_seconds=getattr(self.cfg, "cleanup_interval_seconds", 5.0),
            enable_interference_detection=enhanced_config.enable_interference_detection,
            enable_performance_tracking=enhanced_config.enable_performance_tracking,
            max_signals_per_token=enhanced_config.max_signals_per_token,
        )
        self.cleanup_manager = SignalCleanupManager(cleanup_config)

        # Initialize advanced timeout configuration
        timeout_config_path = getattr(self.cfg, "signal_timeout_config_path", None)
        self.timeout_config_manager = AdvancedTimeoutConfigManager(
            config_path=timeout_config_path
        )

        # Set the enhanced signal processor
        self.signal_manager = self.enhanced_signal_manager

    async def initialize(self) -> None:
        """Initialize the enhanced trading engine."""
        if self._initialized:
            return

        # Initialize base components
        await self.state.initialize_async()

        # Start enhanced signal management
        await self.enhanced_signal_manager.start()
        await self.cleanup_manager.start()

        # Load timeout configuration
        if hasattr(self.cfg, "signal_timeout_config_file"):
            try:
                self.timeout_config_manager.load_configuration()
            except Exception as e:
                logger.warning(f"Failed to load timeout configuration: {e}")

        self._initialized = True
        logger.info("EnhancedTradingEngine initialized with advanced signal processing")

    async def shutdown(self) -> None:
        """Shutdown the enhanced trading engine."""
        if self._initialized:
            await self.enhanced_signal_manager.stop()
            await self.cleanup_manager.stop()

            # Save timeout configuration with learned optimizations
            try:
                self.timeout_config_manager.save_configuration()
                logger.info("Saved optimized timeout configuration")
            except Exception as e:
                logger.error(f"Failed to save timeout configuration: {e}")

            logger.info("EnhancedTradingEngine shutdown complete")

    async def process_signal_enhanced(
        self,
        signal: TradingSignal,
        priority: SignalPriority = SignalPriority.NORMAL,
        strategy_type: StrategyType | None = None,
        market_sector: str | None = None,
        strategy_name: str = "",
        signal_source: str = "",
        execution_context: dict[str, Any] | None = None,
    ) -> str:
        """
        Process a trading signal with enhanced timeout and interference management.

        Args:
            signal: The trading signal to process
            priority: Signal priority level
            strategy_type: Type of strategy generating the signal
            market_sector: Market sector classification
            strategy_name: Name of the strategy
            signal_source: Source system generating the signal
            execution_context: Additional execution context

        Returns:
            Signal ID for tracking
        """
        # Ensure engine is initialized
        if not self._initialized:
            await self.initialize()

        # Update market data for volatility tracking
        self._update_market_data(signal)

        # Check for signal interference before submission
        interference_check = self.cleanup_manager.check_interference_risk(signal)

        if interference_check["interference_level"].value in ["high", "critical"]:
            logger.warning(
                f"Signal blocked due to {interference_check['interference_level'].value} interference risk: "
                f"{interference_check['details']}"
            )
            # Could raise exception or return error signal_id
            raise ValueError(
                f"Signal interference detected: {interference_check['interference_level'].value}"
            )

        # Submit signal with enhanced tracking
        try:
            signal_id = await self.enhanced_signal_manager.submit_enhanced_signal(
                signal=signal,
                priority=priority,
                strategy_name=strategy_name,
                market_sector=market_sector or self._infer_market_sector(signal),
                signal_source=signal_source,
                execution_context=execution_context,
            )

            logger.debug(f"Enhanced signal submitted: {signal_id}")
            return signal_id

        except Exception as e:
            logger.error(f"Failed to submit enhanced signal: {e}")
            # Fallback to basic signal processing if enhanced processing fails
            return self.process_signal(signal)

    def _update_market_data(self, signal: TradingSignal) -> None:
        """Update market data tracking for volatility analysis."""
        token_id = signal.token_id
        current_time = asyncio.get_event_loop().time()

        # Initialize tracking if needed
        if token_id not in self._market_data_history:
            self._market_data_history[token_id] = []

        # Add current price point
        self._market_data_history[token_id].append(
            {
                "timestamp": current_time,
                "price": signal.price,
                "size": signal.size,
                "side": signal.side,
            }
        )

        # Keep only recent history (last 100 points)
        if len(self._market_data_history[token_id]) > 100:
            self._market_data_history[token_id] = self._market_data_history[token_id][
                -100:
            ]

        # Update the enhanced signal manager's market data
        self.enhanced_signal_manager.update_market_data(
            token_id, signal.price, current_time
        )

        self._last_market_update[token_id] = current_time

    def _infer_market_sector(self, signal: TradingSignal) -> str:
        """Infer market sector from signal characteristics."""
        market_slug = signal.market_slug.lower()

        # Simple classification based on market slug keywords
        if any(
            keyword in market_slug
            for keyword in ["election", "politics", "president", "vote"]
        ):
            return "politics"
        elif any(
            keyword in market_slug
            for keyword in ["crypto", "bitcoin", "ethereum", "btc", "eth"]
        ):
            return "crypto"
        elif any(
            keyword in market_slug
            for keyword in ["sports", "nfl", "nba", "soccer", "football"]
        ):
            return "sports"
        elif any(
            keyword in market_slug
            for keyword in ["economics", "gdp", "inflation", "fed", "rate"]
        ):
            return "economics"
        else:
            return "general"

    def _process_enhanced_signal(self, signal: TradingSignal) -> None:
        """Enhanced signal processor with performance tracking."""
        start_time = asyncio.get_event_loop().time()
        success = False
        error_message = None

        try:
            # Process signal using base implementation
            self._process_signal_direct(signal)
            success = True

        except Exception as e:
            error_message = str(e)
            logger.error(f"Enhanced signal processing failed: {e}")
            raise

        finally:
            # Record performance for adaptive learning
            end_time = asyncio.get_event_loop().time()
            execution_time = end_time - start_time

            self._record_signal_performance(
                signal, success, execution_time, error_message
            )

    def _record_signal_performance(
        self,
        signal: TradingSignal,
        success: bool,
        execution_time: float,
        error_message: str | None = None,
    ) -> None:
        """Record signal processing performance for optimization."""
        strategy_key = f"{signal.market_slug}_{self._infer_market_sector(signal)}"

        if strategy_key not in self._strategy_performance:
            self._strategy_performance[strategy_key] = {
                "total_signals": 0,
                "successful_signals": 0,
                "avg_execution_time": 0.0,
                "recent_outcomes": [],
            }

        perf = self._strategy_performance[strategy_key]
        perf["total_signals"] += 1

        if success:
            perf["successful_signals"] += 1

        # Update average execution time
        perf["avg_execution_time"] = (
            perf["avg_execution_time"] * (perf["total_signals"] - 1) + execution_time
        ) / perf["total_signals"]

        # Track recent outcomes for adaptive timeout adjustment
        perf["recent_outcomes"].append(
            {
                "timestamp": asyncio.get_event_loop().time(),
                "success": success,
                "execution_time": execution_time,
                "error": error_message,
            }
        )

        # Keep only recent outcomes (last 50)
        if len(perf["recent_outcomes"]) > 50:
            perf["recent_outcomes"] = perf["recent_outcomes"][-50:]

        # Report to timeout configuration manager for adaptive learning
        try:
            strategy_type = self._infer_strategy_type(signal)
            market_sector = self._infer_market_sector(signal)

            # Calculate timeout used (estimate based on default)
            timeout_used = self.timeout_config_manager.calculate_timeout(
                base_timeout=30.0,  # Default base timeout
                strategy_type=strategy_type,
                market_sector=market_sector,
            )

            self.timeout_config_manager.record_signal_outcome(
                strategy_type=strategy_type,
                market_sector=market_sector,
                success=success,
                execution_time=execution_time,
                timeout_used=timeout_used,
                additional_context={
                    "error_message": error_message,
                    "market_slug": signal.market_slug,
                    "token_id": signal.token_id,
                },
            )
        except Exception as e:
            logger.debug(f"Failed to record timeout optimization data: {e}")

    def _infer_strategy_type(self, signal: TradingSignal) -> StrategyType | None:
        """Infer strategy type from signal characteristics."""
        market_slug = signal.market_slug.lower()

        # Simple inference based on market characteristics
        if "arb" in market_slug or "arbitrage" in market_slug:
            return StrategyType.PURE_ARBITRAGE
        elif "mm" in market_slug or "market" in market_slug:
            return StrategyType.MARKET_MAKING_TIGHT
        elif "momentum" in market_slug or "trend" in market_slug:
            return StrategyType.SHORT_MOMENTUM
        elif "reversion" in market_slug or "mean" in market_slug:
            return StrategyType.FAST_REVERSION
        elif "news" in market_slug or "event" in market_slug:
            return StrategyType.NEWS_REACTION
        elif "stat" in market_slug or "statistical" in market_slug:
            return StrategyType.STATISTICAL_REV
        elif "pairs" in market_slug or "relative" in market_slug:
            return StrategyType.MULTI_LEG_SPREAD
        elif "vol" in market_slug or "volatility" in market_slug:
            return StrategyType.MICRO_STRUCTURE
        else:
            return None  # Unknown strategy type

    # Backward compatibility methods
    def process_signal(self, signal: TradingSignal) -> str:
        """Process signal with basic timeout handling (backward compatibility)."""
        if not self._initialized:
            self._ensure_initialized()

        # Use enhanced processing with default parameters
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.process_signal_enhanced(signal))
        except RuntimeError:
            # Fallback to basic processing if no event loop
            return self.enhanced_signal_manager.submit_signal(signal)

    def get_signal_processing_metrics(self) -> dict[str, Any]:
        """Get comprehensive signal processing metrics."""
        base_metrics = self.enhanced_signal_manager.get_metrics()
        cleanup_metrics = self.cleanup_manager.get_cleanup_metrics()
        interference_report = self.cleanup_manager.get_interference_report()
        performance_summary = self.timeout_config_manager.get_performance_summary()

        return {
            "signal_manager": base_metrics,
            "cleanup_manager": cleanup_metrics,
            "interference_analysis": interference_report,
            "timeout_optimization": performance_summary,
            "strategy_performance": self._get_strategy_performance_summary(),
        }

    def _get_strategy_performance_summary(self) -> dict[str, Any]:
        """Get summary of strategy performance."""
        summary = {}

        for strategy_key, perf in self._strategy_performance.items():
            success_rate = (
                perf["successful_signals"] / perf["total_signals"]
                if perf["total_signals"] > 0
                else 0.0
            )

            summary[strategy_key] = {
                "total_signals": perf["total_signals"],
                "success_rate": success_rate,
                "avg_execution_time": perf["avg_execution_time"],
                "recent_signals": len(perf["recent_outcomes"]),
            }

        return summary

    def add_custom_timeout_rule(self, rule: TimeoutRule) -> None:
        """Add a custom timeout rule for specific conditions."""
        self.timeout_config_manager.add_custom_rule(rule)
        logger.info(f"Added custom timeout rule: {rule.name}")

    def force_signal_cleanup(
        self, market_slug: str | None = None, token_id: str | None = None
    ) -> None:
        """Force cleanup of signals for specific market or token."""
        # This would trigger immediate cleanup for specified signals
        logger.info(
            f"Forcing signal cleanup for market: {market_slug}, token: {token_id}"
        )

        # Implementation would depend on cleanup manager's capabilities
        # For now, log the request
        if market_slug:
            logger.info(f"Cleanup requested for market: {market_slug}")
        if token_id:
            logger.info(f"Cleanup requested for token: {token_id}")

    def get_market_volatility_report(self) -> dict[str, Any]:
        """Get current market volatility analysis."""
        report = {}

        for token_id, history in self._market_data_history.items():
            if len(history) < 2:
                continue

            recent_prices = [
                point["price"] for point in history[-10:]
            ]  # Last 10 prices

            if len(recent_prices) >= 2:
                # Calculate volatility metrics
                price_changes = []
                for i in range(1, len(recent_prices)):
                    change = (
                        abs(recent_prices[i] - recent_prices[i - 1])
                        / recent_prices[i - 1]
                    )
                    price_changes.append(change)

                avg_volatility = sum(price_changes) / len(price_changes)
                max_change = max(price_changes)

                # Determine market condition
                if avg_volatility > 0.05:
                    condition = MarketCondition.VOLATILE
                elif avg_volatility < 0.01:
                    condition = MarketCondition.STABLE
                else:
                    condition = MarketCondition.NORMAL

                report[token_id] = {
                    "avg_volatility": avg_volatility,
                    "max_change": max_change,
                    "market_condition": condition.value,
                    "data_points": len(history),
                    "last_update": self._last_market_update.get(token_id, 0),
                }

        return report
