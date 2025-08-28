"""
Enhanced base strategy class with integrated performance tracking.

This module provides an enhanced base class for trading strategies that automatically
tracks performance metrics, execution statistics, and provides comprehensive analysis.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any

from ..performance_tracking import PerformanceTracker
from ..signals import TradingSignal

logger = logging.getLogger(__name__)


class PerformanceAwareStrategy(ABC):
    """
    Enhanced base strategy class with integrated performance tracking.

    This class automatically tracks:
    - Signal generation and execution
    - Trade outcomes and P&L
    - Win/loss ratios
    - Execution statistics
    - Strategy-specific metrics
    """

    def __init__(
        self,
        strategy_name: str,
        config: dict[str, Any] = None,
        performance_tracker: PerformanceTracker | None = None,
    ):
        self.strategy_name = strategy_name
        self.config = config or {}
        self.performance_tracker = performance_tracker

        # Strategy-specific configuration
        self.enabled = self.config.get("enabled", True)
        self.max_position_size = self.config.get("max_position_size", 1000.0)
        self.risk_limit_per_trade = self.config.get("risk_limit_per_trade", 100.0)

        # Internal tracking
        self._signals_generated = 0
        self._last_signal_time = 0.0
        self._active_signals: dict[str, TradingSignal] = {}

        logger.info(f"Strategy {strategy_name} initialized with performance tracking")

    @abstractmethod
    def evaluate(self, market_data: dict[str, Any]) -> list[TradingSignal]:
        """
        Evaluate market data and generate trading signals.

        Args:
            market_data: Current market data including prices, volumes, etc.

        Returns:
            List of TradingSignal objects for execution
        """
        pass

    def generate_signals(self, market_data: dict[str, Any]) -> list[TradingSignal]:
        """
        Wrapper for signal generation that includes performance tracking.

        Args:
            market_data: Current market data

        Returns:
            List of validated trading signals with tracking
        """
        if not self.enabled:
            return []

        try:
            # Generate signals using strategy logic
            signals = self.evaluate(market_data)

            # Filter and validate signals
            validated_signals = self._validate_signals(signals)

            # Track signal generation
            for signal in validated_signals:
                self._track_signal_generation(signal)

            return validated_signals

        except Exception as e:
            logger.error(f"Error generating signals for {self.strategy_name}: {e}")
            return []

    def _validate_signals(self, signals: list[TradingSignal]) -> list[TradingSignal]:
        """
        Validate signals before execution.

        Args:
            signals: Raw signals from strategy

        Returns:
            Validated signals that pass risk checks
        """
        validated = []

        for signal in signals:
            # Basic validation
            if not self._is_valid_signal(signal):
                continue

            # Risk validation
            if not self._passes_risk_checks(signal):
                continue

            # Generate unique signal ID if not present
            if not signal.signal_id:
                signal.signal_id = (
                    f"{self.strategy_name}_{int(time.time() * 1000)}_{len(validated)}"
                )

            validated.append(signal)

        return validated

    def _is_valid_signal(self, signal: TradingSignal) -> bool:
        """Basic signal validation."""
        if not signal.market_slug or not signal.token_id:
            logger.warning("Invalid signal: missing market_slug or token_id")
            return False

        if signal.price <= 0 or signal.size <= 0:
            logger.warning(f"Invalid signal: price={signal.price}, size={signal.size}")
            return False

        if signal.side not in ["buy", "sell"]:
            logger.warning(f"Invalid signal: invalid side={signal.side}")
            return False

        return True

    def _passes_risk_checks(self, signal: TradingSignal) -> bool:
        """Risk validation for signals."""
        # Check position size limits
        notional_value = signal.price * signal.size
        if notional_value > self.risk_limit_per_trade:
            logger.warning(
                f"Signal exceeds risk limit: {notional_value} > {self.risk_limit_per_trade}"
            )
            return False

        # Check maximum position size
        if signal.size > self.max_position_size:
            logger.warning(
                f"Signal exceeds max position size: {signal.size} > {self.max_position_size}"
            )
            return False

        return True

    def _track_signal_generation(self, signal: TradingSignal):
        """Track signal generation for performance analysis."""
        self._signals_generated += 1
        self._last_signal_time = time.time()
        self._active_signals[signal.signal_id] = signal

        # Record with performance tracker if available
        if self.performance_tracker:
            self.performance_tracker.record_signal_generated(signal, self.strategy_name)

        logger.debug(f"Generated signal {signal.signal_id} for {self.strategy_name}")

    def on_trade_executed(
        self,
        signal_id: str,
        executed_price: float,
        executed_size: float,
        fees: float = 0.0,
        execution_timestamp: float | None = None,
    ):
        """
        Callback when a trade is executed.

        Args:
            signal_id: ID of the signal that was executed
            executed_price: Actual execution price
            executed_size: Actual execution size
            fees: Trading fees paid
            execution_timestamp: When the trade was executed
        """
        if self.performance_tracker:
            self.performance_tracker.record_trade_execution(
                signal_id, executed_price, executed_size, fees, execution_timestamp
            )

        logger.info(f"Trade executed for {signal_id}: {executed_size}@{executed_price}")

    def on_trade_completed(
        self,
        signal_id: str,
        exit_price: float,
        realized_pnl: float,
        exit_timestamp: float | None = None,
    ):
        """
        Callback when a trade is completed/closed.

        Args:
            signal_id: ID of the signal/trade
            exit_price: Final exit price
            realized_pnl: Realized profit/loss
            exit_timestamp: When the position was closed
        """
        if self.performance_tracker:
            self.performance_tracker.record_trade_outcome(
                signal_id, exit_price, realized_pnl, exit_timestamp
            )

        # Remove from active signals
        if signal_id in self._active_signals:
            del self._active_signals[signal_id]

        logger.info(f"Trade completed for {signal_id}: PnL={realized_pnl}")

    def get_strategy_performance(self):
        """Get performance metrics for this strategy."""
        if not self.performance_tracker:
            return None

        return self.performance_tracker.get_strategy_performance(self.strategy_name)

    def get_active_signals(self) -> dict[str, TradingSignal]:
        """Get currently active signals."""
        return self._active_signals.copy()

    def get_strategy_stats(self) -> dict[str, Any]:
        """Get basic strategy statistics."""
        return {
            "strategy_name": self.strategy_name,
            "enabled": self.enabled,
            "signals_generated": self._signals_generated,
            "active_signals": len(self._active_signals),
            "last_signal_time": self._last_signal_time,
            "config": self.config,
        }


class ComplementArbStrategy(PerformanceAwareStrategy):
    """
    Enhanced complement arbitrage strategy with performance tracking.
    """

    def __init__(
        self,
        config: dict[str, Any] = None,
        performance_tracker: PerformanceTracker | None = None,
    ):
        super().__init__("complement_arbitrage", config, performance_tracker)

        # Strategy-specific parameters
        self.min_deviation_threshold = self.config.get("min_deviation_threshold", 0.01)
        self.max_deviation_threshold = self.config.get("max_deviation_threshold", 0.20)
        self.base_trade_size = self.config.get("base_trade_size", 10.0)
        self.max_trade_size = self.config.get("max_trade_size", 100.0)
        self.size_scaling_factor = self.config.get("size_scaling_factor", 50.0)

    def evaluate(self, market_data: dict[str, Any]) -> list[TradingSignal]:
        """Evaluate markets for complement arbitrage opportunities."""
        signals = []

        # Get market snapshots
        market_snapshots = market_data.get("market_snapshots", [])

        for market in market_snapshots:
            # Find Yes/No token pairs
            yes_data = None
            no_data = None

            for token in market.get("tokens", []):
                if token.get("outcome") == "yes":
                    yes_data = token
                elif token.get("outcome") == "no":
                    no_data = token

            if not yes_data or not no_data:
                continue

            # Calculate complement deviation
            yes_price = yes_data.get("price", 0)
            no_price = no_data.get("price", 0)

            if yes_price <= 0 or no_price <= 0:
                continue

            total_price = yes_price + no_price
            deviation = abs(total_price - 1.0)

            # Check if deviation exceeds threshold
            if (
                deviation < self.min_deviation_threshold
                or deviation > self.max_deviation_threshold
            ):
                continue

            # Calculate position size based on deviation
            size_multiplier = min(
                deviation * self.size_scaling_factor,
                self.max_trade_size / self.base_trade_size,
            )
            position_size = self.base_trade_size * size_multiplier

            # Determine trade direction
            if total_price > 1.0:
                # Sell both (prices too high)
                signals.extend(
                    [
                        TradingSignal(
                            market_slug=market["slug"],
                            token_id=yes_data["token_id"],
                            side="sell",
                            price=yes_price,
                            size=position_size,
                            outcome_type="yes",
                        ),
                        TradingSignal(
                            market_slug=market["slug"],
                            token_id=no_data["token_id"],
                            side="sell",
                            price=no_price,
                            size=position_size,
                            outcome_type="no",
                        ),
                    ]
                )
            else:
                # Buy both (prices too low)
                signals.extend(
                    [
                        TradingSignal(
                            market_slug=market["slug"],
                            token_id=yes_data["token_id"],
                            side="buy",
                            price=yes_price,
                            size=position_size,
                            outcome_type="yes",
                        ),
                        TradingSignal(
                            market_slug=market["slug"],
                            token_id=no_data["token_id"],
                            side="buy",
                            price=no_price,
                            size=position_size,
                            outcome_type="no",
                        ),
                    ]
                )

        return signals


class SpreadArbStrategy(PerformanceAwareStrategy):
    """
    Enhanced spread arbitrage strategy with performance tracking.
    """

    def __init__(
        self,
        config: dict[str, Any] = None,
        performance_tracker: PerformanceTracker | None = None,
    ):
        super().__init__("spread_arbitrage", config, performance_tracker)

        # Strategy-specific parameters
        self.min_spread = self.config.get("min_spread", 0.01)
        self.max_spread = self.config.get("max_spread", 0.50)
        self.trade_size = self.config.get("trade_size", 10.0)

    def evaluate(self, market_data: dict[str, Any]) -> list[TradingSignal]:
        """Evaluate markets for spread arbitrage opportunities."""
        signals = []

        market_snapshots = market_data.get("market_snapshots", [])

        for market in market_snapshots:
            for token in market.get("tokens", []):
                # Get bid/ask data
                best_bid = token.get("best_bid", 0)
                best_ask = token.get("best_ask", 0)

                if best_bid <= 0 or best_ask <= 0 or best_ask <= best_bid:
                    continue

                # Calculate spread
                spread = best_ask - best_bid
                spread_pct = spread / best_ask if best_ask > 0 else 0

                # Check if spread exceeds thresholds
                if spread_pct < self.min_spread or spread_pct > self.max_spread:
                    continue

                # Generate signals to capture spread
                signals.extend(
                    [
                        TradingSignal(
                            market_slug=market["slug"],
                            token_id=token["token_id"],
                            side="buy",
                            price=best_bid,
                            size=self.trade_size,
                            outcome_type=token.get("outcome"),
                        ),
                        TradingSignal(
                            market_slug=market["slug"],
                            token_id=token["token_id"],
                            side="sell",
                            price=best_ask,
                            size=self.trade_size,
                            outcome_type=token.get("outcome"),
                        ),
                    ]
                )

        return signals


class MarketMakingStrategy(PerformanceAwareStrategy):
    """
    Enhanced market making strategy with performance tracking.
    """

    def __init__(
        self,
        config: dict[str, Any] = None,
        performance_tracker: PerformanceTracker | None = None,
    ):
        super().__init__("market_making", config, performance_tracker)

        # Strategy-specific parameters
        self.spread_bps = self.config.get("spread_bps", 50)  # 50 basis points
        self.quote_size = self.config.get("quote_size", 25.0)
        self.max_inventory = self.config.get("max_inventory", 200.0)
        self.skew_factor = self.config.get("skew_factor", 0.1)

        # Track current inventory
        self.inventory = defaultdict(float)  # token_id -> position

    def evaluate(self, market_data: dict[str, Any]) -> list[TradingSignal]:
        """Generate market making quotes."""
        signals = []

        market_snapshots = market_data.get("market_snapshots", [])

        for market in market_snapshots:
            for token in market.get("tokens", []):
                token_id = token["token_id"]
                mid_price = token.get("mid_price", 0)

                if mid_price <= 0:
                    continue

                # Calculate spread
                spread = (self.spread_bps / 10000) * mid_price

                # Apply inventory skew
                current_inventory = self.inventory[token_id]
                skew = (
                    self.skew_factor * (current_inventory / self.max_inventory)
                    if self.max_inventory > 0
                    else 0
                )

                # Calculate bid/ask prices with skew
                bid_price = mid_price - spread / 2 - skew
                ask_price = mid_price + spread / 2 - skew

                # Ensure prices are within bounds
                bid_price = max(0.01, min(0.99, bid_price))
                ask_price = max(0.01, min(0.99, ask_price))

                # Only quote if we haven't exceeded inventory limits
                if abs(current_inventory) < self.max_inventory:
                    signals.extend(
                        [
                            TradingSignal(
                                market_slug=market["slug"],
                                token_id=token_id,
                                side="buy",
                                price=bid_price,
                                size=self.quote_size,
                                outcome_type=token.get("outcome"),
                            ),
                            TradingSignal(
                                market_slug=market["slug"],
                                token_id=token_id,
                                side="sell",
                                price=ask_price,
                                size=self.quote_size,
                                outcome_type=token.get("outcome"),
                            ),
                        ]
                    )

        return signals

    def on_trade_executed(
        self,
        signal_id: str,
        executed_price: float,
        executed_size: float,
        fees: float = 0.0,
        execution_timestamp: float | None = None,
    ):
        """Update inventory when trades are executed."""
        super().on_trade_executed(
            signal_id, executed_price, executed_size, fees, execution_timestamp
        )

        # Update inventory tracking
        if signal_id in self._active_signals:
            signal = self._active_signals[signal_id]
            inventory_change = executed_size if signal.side == "buy" else -executed_size
            self.inventory[signal.token_id] += inventory_change
