"""
Trading strategy performance integration module.

This module provides seamless integration between the trading strategy performance tracking system
and the existing order client, state management, and signal processing components.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from .order_client import OrderClient
from .performance_tracking import PerformanceTracker
from .signals import TradingSignal
from .strategies.enhanced_base import PerformanceAwareStrategy

logger = logging.getLogger("strategy_performance_integration")


class PerformanceIntegratedOrderClient:
    """Enhanced order client with integrated strategy performance tracking."""

    def __init__(
        self, order_client: OrderClient, performance_tracker: PerformanceTracker
    ):
        self.order_client = order_client
        self.performance_tracker = performance_tracker

        # Track pending orders and their signal IDs
        self._pending_orders: dict[str, str] = {}  # order_id -> signal_id
        self._signal_orders: dict[str, list[str]] = {}  # signal_id -> [order_ids]

        logger.info("PerformanceIntegratedOrderClient initialized")

    def place_limit(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        time_in_force: str,
        market_slug: str,
        outcome_type: str,
        notional_value: float,
        risk_manager: Any,
        signal_id: str | None = None,
    ) -> str | None:
        """Place a limit order with performance tracking."""

        try:
            # Place the order using the original order client
            order_id = self.order_client.place_limit(
                token_id,
                side,
                price,
                size,
                time_in_force,
                market_slug,
                outcome_type,
                notional_value,
                risk_manager,
            )

            if order_id and signal_id:
                # Track the relationship between order and signal
                self._pending_orders[order_id] = signal_id

                if signal_id not in self._signal_orders:
                    self._signal_orders[signal_id] = []
                self._signal_orders[signal_id].append(order_id)

                logger.debug(f"Order {order_id} placed for signal {signal_id}")

            return order_id

        except Exception as e:
            logger.error(f"Error placing order for signal {signal_id}: {e}")
            return None

    def on_order_filled(
        self,
        order_id: str,
        fill_price: float,
        fill_size: float,
        fees: float = 0.0,
        fill_timestamp: float | None = None,
    ):
        """Handle order fill notifications with performance tracking."""

        if order_id in self._pending_orders:
            signal_id = self._pending_orders[order_id]

            # Record trade execution
            self.performance_tracker.record_trade_execution(
                signal_id=signal_id,
                executed_price=fill_price,
                executed_size=fill_size,
                fees=fees,
                execution_timestamp=fill_timestamp,
            )

            logger.info(
                f"Recorded fill for order {order_id}, signal {signal_id}: "
                f"{fill_size}@{fill_price}"
            )

            # Remove from pending orders
            del self._pending_orders[order_id]
        else:
            logger.warning(f"Received fill for unknown order {order_id}")

    def on_position_closed(
        self,
        signal_id: str,
        exit_price: float,
        realized_pnl: float,
        exit_timestamp: float | None = None,
    ):
        """Handle position closure with performance tracking."""

        self.performance_tracker.record_trade_outcome(
            signal_id=signal_id,
            exit_price=exit_price,
            realized_pnl=realized_pnl,
            exit_timestamp=exit_timestamp,
        )

        # Clean up signal tracking
        if signal_id in self._signal_orders:
            del self._signal_orders[signal_id]

        logger.info(
            f"Recorded position closure for signal {signal_id}: PnL={realized_pnl}"
        )

    def get_pending_orders(self) -> dict[str, str]:
        """Get currently pending orders mapped to their signal IDs."""
        return self._pending_orders.copy()

    def get_signal_orders(self, signal_id: str) -> list[str]:
        """Get all order IDs associated with a signal."""
        return self._signal_orders.get(signal_id, [])


class StrategyManager:
    """
    Centralized strategy manager with performance tracking.

    This class manages multiple trading strategies and provides centralized
    performance tracking, execution coordination, and risk management.
    """

    def __init__(
        self,
        performance_tracker: PerformanceTracker,
        order_client: PerformanceIntegratedOrderClient,
    ):
        self.performance_tracker = performance_tracker
        self.order_client = order_client

        # Strategy registry
        self._strategies: dict[str, PerformanceAwareStrategy] = {}
        self._strategy_configs: dict[str, dict[str, Any]] = {}

        # Execution tracking
        self._active_signals: dict[str, TradingSignal] = {}
        self._strategy_signals: dict[str, list[str]] = defaultdict(
            list
        )  # strategy -> [signal_ids]

        # Performance tracking
        self._last_evaluation_time = 0.0
        self._evaluation_count = 0

        logger.info("StrategyManager initialized")

    def register_strategy(
        self, strategy: PerformanceAwareStrategy, config: dict[str, Any] = None
    ):
        """Register a trading strategy with the manager."""

        strategy_name = strategy.strategy_name

        # Set the performance tracker reference
        strategy.performance_tracker = self.performance_tracker

        # Register strategy
        self._strategies[strategy_name] = strategy
        self._strategy_configs[strategy_name] = config or {}
        self._strategy_signals[strategy_name] = []

        logger.info(f"Registered strategy: {strategy_name}")

    def unregister_strategy(self, strategy_name: str):
        """Unregister a trading strategy."""

        if strategy_name in self._strategies:
            del self._strategies[strategy_name]
            del self._strategy_configs[strategy_name]
            del self._strategy_signals[strategy_name]

            logger.info(f"Unregistered strategy: {strategy_name}")

    def evaluate_all_strategies(
        self, market_data: dict[str, Any]
    ) -> dict[str, list[TradingSignal]]:
        """Evaluate all registered strategies and return generated signals."""

        self._evaluation_count += 1
        self._last_evaluation_time = time.time()

        all_signals = {}

        for strategy_name, strategy in self._strategies.items():
            try:
                # Generate signals from strategy
                signals = strategy.generate_signals(market_data)
                all_signals[strategy_name] = signals

                # Track signal IDs for this strategy
                for signal in signals:
                    if signal.signal_id:
                        self._active_signals[signal.signal_id] = signal
                        self._strategy_signals[strategy_name].append(signal.signal_id)

                logger.debug(
                    f"Strategy {strategy_name} generated {len(signals)} signals"
                )

            except Exception as e:
                logger.error(f"Error evaluating strategy {strategy_name}: {e}")
                all_signals[strategy_name] = []

        return all_signals

    def execute_signals(
        self, strategy_signals: dict[str, list[TradingSignal]], risk_manager: Any = None
    ) -> dict[str, list[str | None]]:
        """Execute signals from all strategies."""

        execution_results = {}

        for strategy_name, signals in strategy_signals.items():
            order_ids = []

            for signal in signals:
                try:
                    # Execute the signal
                    order_id = self.order_client.place_limit(
                        token_id=signal.token_id,
                        side=signal.side,
                        price=signal.price,
                        size=signal.size,
                        time_in_force="GTC",  # Default to Good Till Cancelled
                        market_slug=signal.market_slug,
                        outcome_type=signal.outcome_type or "",
                        notional_value=signal.price * signal.size,
                        risk_manager=risk_manager,
                        signal_id=signal.signal_id,
                    )

                    order_ids.append(order_id)

                    if order_id:
                        logger.info(
                            f"Executed signal {signal.signal_id} from {strategy_name}: Order {order_id}"
                        )

                except Exception as e:
                    logger.error(
                        f"Error executing signal {signal.signal_id} from {strategy_name}: {e}"
                    )
                    order_ids.append(None)

            execution_results[strategy_name] = order_ids

        return execution_results

    def get_strategy_performance_summary(self) -> dict[str, dict[str, Any]]:
        """Get performance summary for all strategies."""

        summary = {}

        for strategy_name in self._strategies.keys():
            performance = self.performance_tracker.get_strategy_performance(
                strategy_name
            )

            if performance:
                summary[strategy_name] = {
                    "total_trades": performance.total_trades,
                    "win_rate": round(performance.win_rate * 100, 2),
                    "net_profit": round(performance.net_profit, 2),
                    "profit_factor": round(performance.profit_factor, 3),
                    "max_drawdown": round(performance.max_drawdown_percent, 2),
                    "avg_trade": round(performance.avg_trade, 3),
                    "sharpe_ratio": round(
                        self.performance_tracker.calculate_risk_metrics(
                            strategy_name
                        ).get("sharpe_ratio", 0)
                        or 0,
                        3,
                    ),
                }
            else:
                summary[strategy_name] = {"status": "no_data"}

        return summary

    def get_active_strategies(self) -> list[str]:
        """Get list of active strategy names."""
        return [name for name, strategy in self._strategies.items() if strategy.enabled]

    def enable_strategy(self, strategy_name: str):
        """Enable a strategy."""
        if strategy_name in self._strategies:
            self._strategies[strategy_name].enabled = True
            logger.info(f"Enabled strategy: {strategy_name}")

    def disable_strategy(self, strategy_name: str):
        """Disable a strategy."""
        if strategy_name in self._strategies:
            self._strategies[strategy_name].enabled = False
            logger.info(f"Disabled strategy: {strategy_name}")

    def get_manager_stats(self) -> dict[str, Any]:
        """Get strategy manager statistics."""

        active_strategies = len(self.get_active_strategies())
        total_signals = len(self._active_signals)

        return {
            "total_strategies": len(self._strategies),
            "active_strategies": active_strategies,
            "total_active_signals": total_signals,
            "evaluation_count": self._evaluation_count,
            "last_evaluation_time": self._last_evaluation_time,
            "strategies": list(self._strategies.keys()),
        }


class PerformanceDashboard:
    """Real-time performance dashboard for monitoring trading strategies."""

    def __init__(
        self, strategy_manager: StrategyManager, performance_tracker: PerformanceTracker
    ):
        self.strategy_manager = strategy_manager
        self.performance_tracker = performance_tracker

        # Dashboard state
        self._last_update = 0.0
        self._update_interval = 30.0  # 30 seconds

        logger.info("PerformanceDashboard initialized")

    async def start_monitoring(self):
        """Start real-time performance monitoring."""

        # Start performance tracker
        await self.performance_tracker.start_tracking()

        logger.info("Performance monitoring started")

    async def stop_monitoring(self):
        """Stop performance monitoring."""

        await self.performance_tracker.stop_tracking()

        logger.info("Performance monitoring stopped")

    def get_dashboard_data(self) -> dict[str, Any]:
        """Get comprehensive dashboard data."""

        current_time = time.time()

        dashboard_data = {
            "timestamp": current_time,
            "summary": self.performance_tracker.get_performance_summary(),
            "strategy_performance": self.strategy_manager.get_strategy_performance_summary(),
            "manager_stats": self.strategy_manager.get_manager_stats(),
            "top_performers": self.performance_tracker.get_strategy_ranking(
                "net_profit"
            )[:5],
            "recent_trades": [
                {
                    "signal_id": trade.signal_id,
                    "strategy": trade.strategy_name,
                    "side": trade.side,
                    "size": trade.executed_size,
                    "price": trade.executed_price,
                    "pnl": trade.realized_pnl,
                    "timestamp": trade.execution_timestamp,
                }
                for trade in self.performance_tracker.get_trade_history(limit=20)
                if trade.realized_pnl is not None
            ],
        }

        self._last_update = current_time
        return dashboard_data

    def generate_performance_alert(self, strategy_name: str) -> dict[str, Any] | None:
        """Generate performance alerts for a strategy."""

        performance = self.performance_tracker.get_strategy_performance(strategy_name)

        if not performance:
            return None

        alerts = []

        # Check for concerning performance metrics
        if performance.win_rate < 0.3 and performance.total_trades >= 10:
            alerts.append(
                {
                    "type": "low_win_rate",
                    "severity": "high",
                    "message": f"Low win rate: {performance.win_rate*100:.1f}%",
                }
            )

        if performance.max_drawdown_percent > 25:
            alerts.append(
                {
                    "type": "high_drawdown",
                    "severity": "high",
                    "message": f"High drawdown: {performance.max_drawdown_percent:.1f}%",
                }
            )

        if performance.profit_factor < 0.8 and performance.total_trades >= 5:
            alerts.append(
                {
                    "type": "negative_expectancy",
                    "severity": "critical",
                    "message": f"Negative expected value: profit factor {performance.profit_factor:.2f}",
                }
            )

        if alerts:
            return {
                "strategy_name": strategy_name,
                "alerts": alerts,
                "timestamp": time.time(),
            }

        return None
