"""
Comprehensive performance tracking system for trading strategies.

This module provides detailed performance analysis including:
- Strategy effectiveness metrics
- Win/loss ratio tracking
- Profit/loss calculations
- Execution statistics
- Performance comparison across strategies
- Risk-adjusted returns
- Time-based performance analysis
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .signals import TradingSignal

logger = logging.getLogger("performance_tracking")


class TradeStatus(str, Enum):
    """Status of individual trades."""

    PENDING = "pending"  # Signal generated, not yet executed
    EXECUTED = "executed"  # Order successfully placed
    FILLED = "filled"  # Order completely filled
    PARTIAL_FILL = "partial"  # Order partially filled
    CANCELLED = "cancelled"  # Order cancelled
    REJECTED = "rejected"  # Order rejected
    EXPIRED = "expired"  # Order expired


class TradeOutcome(str, Enum):
    """Final outcome classification for trades."""

    WIN = "win"  # Profitable trade
    LOSS = "loss"  # Losing trade
    BREAKEVEN = "breakeven"  # No profit or loss
    PENDING = "pending"  # Trade still open/unresolved


@dataclass
class TradeExecution:
    """Detailed execution information for a trade."""

    signal_id: str
    strategy_name: str
    market_slug: str
    token_id: str
    side: str  # "buy" or "sell"

    # Execution details
    intended_price: float
    intended_size: float
    executed_price: float
    executed_size: float
    execution_timestamp: float

    # Financial tracking
    notional_value: float  # executed_price * executed_size
    fees_paid: float = 0.0
    slippage: float = 0.0  # difference between intended and executed price

    # Status tracking
    status: TradeStatus = TradeStatus.PENDING
    outcome: TradeOutcome = TradeOutcome.PENDING

    # Performance metrics (filled when trade completes)
    realized_pnl: float | None = None
    unrealized_pnl: float | None = None
    holding_period: float | None = None  # seconds
    exit_price: float | None = None
    exit_timestamp: float | None = None

    # Risk metrics
    max_drawdown: float | None = None
    max_favorable_excursion: float | None = None


@dataclass
class StrategyPerformanceMetrics:
    """Comprehensive performance metrics for a strategy."""

    strategy_name: str

    # Trade counts
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0

    # Financial performance
    total_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    gross_profit: float = 0.0  # Sum of all winning trades
    gross_loss: float = 0.0  # Sum of all losing trades
    total_fees: float = 0.0
    net_profit: float = 0.0  # total_pnl - total_fees

    # Ratios and percentages
    win_rate: float = 0.0  # winning_trades / total_trades
    loss_rate: float = 0.0  # losing_trades / total_trades
    profit_factor: float = 0.0  # gross_profit / abs(gross_loss)
    avg_win: float = 0.0  # gross_profit / winning_trades
    avg_loss: float = 0.0  # gross_loss / losing_trades
    avg_trade: float = 0.0  # total_pnl / total_trades

    # Risk metrics
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None

    # Execution metrics
    avg_slippage: float = 0.0
    avg_holding_period: float = 0.0
    fill_rate: float = 0.0  # filled_trades / total_trades
    avg_trade_size: float = 0.0

    # Time-based metrics
    trades_per_day: float = 0.0
    best_day_pnl: float = 0.0
    worst_day_pnl: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # Market exposure
    total_volume: float = 0.0
    avg_position_size: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0

    # Timestamps
    first_trade_time: float | None = None
    last_trade_time: float | None = None
    last_updated: float = field(default_factory=time.time)


@dataclass
class PerformanceSnapshot:
    """Point-in-time performance snapshot for time series analysis."""

    timestamp: float
    strategy_name: str
    equity_value: float
    drawdown: float
    daily_pnl: float
    trade_count: int
    win_rate: float


class PerformanceTracker:
    """
    Comprehensive performance tracking system for trading strategies.

    Features:
    - Real-time trade execution tracking
    - Detailed P&L calculations
    - Win/loss ratio analysis
    - Risk-adjusted performance metrics
    - Strategy comparison and ranking
    - Historical performance analysis
    - Drawdown and risk monitoring
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

        # Core data structures
        self._trade_executions: dict[str, TradeExecution] = {}  # signal_id -> execution
        self._strategy_metrics: dict[str, StrategyPerformanceMetrics] = {}
        self._performance_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=10000)
        )

        # Position tracking
        self._open_positions: dict[str, dict[str, Any]] = (
            {}
        )  # strategy -> {token -> position}
        self._position_history: dict[str, list[dict[str, Any]]] = defaultdict(list)

        # Performance snapshots for time series
        self._performance_snapshots: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=5000)
        )

        # Market data for P&L calculations
        self._market_prices: dict[str, float] = {}  # token_id -> current_price

        # Configuration
        self._risk_free_rate = self.config.get("risk_free_rate", 0.02)  # 2% annual
        self._snapshot_interval = self.config.get("snapshot_interval", 300)  # 5 minutes

        # Background tasks
        self._snapshot_task: asyncio.Task | None = None
        self._tracking_active = False

        logger.info("PerformanceTracker initialized")

    async def start_tracking(self):
        """Start background performance tracking."""
        if self._tracking_active:
            return

        self._tracking_active = True
        self._snapshot_task = asyncio.create_task(self._snapshot_loop())
        logger.info("Performance tracking started")

    async def stop_tracking(self):
        """Stop background performance tracking."""
        if not self._tracking_active:
            return

        self._tracking_active = False
        if self._snapshot_task:
            self._snapshot_task.cancel()
            try:
                await self._snapshot_task
            except asyncio.CancelledError:
                pass

        logger.info("Performance tracking stopped")

    async def _snapshot_loop(self):
        """Background loop for taking performance snapshots."""
        try:
            while self._tracking_active:
                await self._take_performance_snapshots()
                await asyncio.sleep(self._snapshot_interval)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in performance snapshot loop: {e}")

    def record_signal_generated(self, signal: TradingSignal, strategy_name: str):
        """Record that a trading signal was generated by a strategy."""
        signal_id = signal.signal_id or f"{strategy_name}_{int(time.time() * 1000)}"
        signal.signal_id = signal_id

        # Initialize trade execution record
        execution = TradeExecution(
            signal_id=signal_id,
            strategy_name=strategy_name,
            market_slug=signal.market_slug,
            token_id=signal.token_id,
            side=signal.side,
            intended_price=signal.price,
            intended_size=signal.size,
            executed_price=0.0,  # Will be updated when executed
            executed_size=0.0,  # Will be updated when executed
            execution_timestamp=time.time(),
            notional_value=signal.price * signal.size,
            status=TradeStatus.PENDING,
        )

        self._trade_executions[signal_id] = execution
        self._ensure_strategy_metrics(strategy_name)

        logger.debug(
            f"Recorded signal generation: {signal_id} for strategy {strategy_name}"
        )

    def record_trade_execution(
        self,
        signal_id: str,
        executed_price: float,
        executed_size: float,
        fees: float = 0.0,
        execution_timestamp: float | None = None,
    ):
        """Record the successful execution of a trade."""
        if signal_id not in self._trade_executions:
            logger.warning(f"Unknown signal_id for execution: {signal_id}")
            return

        execution = self._trade_executions[signal_id]
        execution.executed_price = executed_price
        execution.executed_size = executed_size
        execution.fees_paid = fees
        execution.execution_timestamp = execution_timestamp or time.time()
        execution.notional_value = executed_price * executed_size
        execution.slippage = (
            abs(executed_price - execution.intended_price) / execution.intended_price
        )
        execution.status = TradeStatus.FILLED

        # Update strategy metrics
        self._update_execution_metrics(execution)

        # Track position
        self._update_position_tracking(execution)

        logger.info(
            f"Recorded trade execution: {signal_id} at {executed_price} for {executed_size}"
        )

    def record_trade_outcome(
        self,
        signal_id: str,
        exit_price: float,
        realized_pnl: float,
        exit_timestamp: float | None = None,
    ):
        """Record the final outcome of a trade when position is closed."""
        if signal_id not in self._trade_executions:
            logger.warning(f"Unknown signal_id for outcome: {signal_id}")
            return

        execution = self._trade_executions[signal_id]
        execution.exit_price = exit_price
        execution.exit_timestamp = exit_timestamp or time.time()
        execution.realized_pnl = realized_pnl
        execution.holding_period = (
            execution.exit_timestamp - execution.execution_timestamp
        )

        # Classify outcome
        if realized_pnl > 0.01:  # Account for small rounding errors
            execution.outcome = TradeOutcome.WIN
        elif realized_pnl < -0.01:
            execution.outcome = TradeOutcome.LOSS
        else:
            execution.outcome = TradeOutcome.BREAKEVEN

        # Update strategy performance metrics
        self._update_outcome_metrics(execution)

        # Update position tracking
        self._close_position_tracking(execution)

        logger.info(
            f"Recorded trade outcome: {signal_id} - {execution.outcome.value} with PnL {realized_pnl}"
        )

    def update_market_price(self, token_id: str, price: float):
        """Update current market price for unrealized P&L calculations."""
        self._market_prices[token_id] = price

        # Update unrealized P&L for open positions
        self._update_unrealized_pnl()

    def _ensure_strategy_metrics(self, strategy_name: str):
        """Ensure strategy metrics object exists."""
        if strategy_name not in self._strategy_metrics:
            self._strategy_metrics[strategy_name] = StrategyPerformanceMetrics(
                strategy_name=strategy_name
            )

    def _update_execution_metrics(self, execution: TradeExecution):
        """Update strategy metrics based on trade execution."""
        metrics = self._strategy_metrics[execution.strategy_name]

        metrics.total_trades += 1
        metrics.total_volume += execution.notional_value
        metrics.total_fees += execution.fees_paid
        metrics.avg_slippage = (
            metrics.avg_slippage * (metrics.total_trades - 1) + execution.slippage
        ) / metrics.total_trades

        if metrics.first_trade_time is None:
            metrics.first_trade_time = execution.execution_timestamp
        metrics.last_trade_time = execution.execution_timestamp

        metrics.avg_trade_size = metrics.total_volume / metrics.total_trades
        metrics.fill_rate = (
            len(
                [
                    e
                    for e in self._trade_executions.values()
                    if e.strategy_name == execution.strategy_name
                    and e.status == TradeStatus.FILLED
                ]
            )
            / metrics.total_trades
        )

        metrics.last_updated = time.time()

    def _update_outcome_metrics(self, execution: TradeExecution):
        """Update strategy metrics based on trade outcome."""
        metrics = self._strategy_metrics[execution.strategy_name]
        pnl = execution.realized_pnl

        # Update P&L tracking
        metrics.total_pnl += pnl
        metrics.realized_pnl += pnl
        metrics.net_profit = metrics.total_pnl - metrics.total_fees

        # Update win/loss counts and amounts
        if execution.outcome == TradeOutcome.WIN:
            metrics.winning_trades += 1
            metrics.gross_profit += pnl
            metrics.consecutive_wins += 1
            metrics.consecutive_losses = 0
            metrics.max_consecutive_wins = max(
                metrics.max_consecutive_wins, metrics.consecutive_wins
            )
            if pnl > metrics.largest_win:
                metrics.largest_win = pnl
        elif execution.outcome == TradeOutcome.LOSS:
            metrics.losing_trades += 1
            metrics.gross_loss += abs(pnl)  # Store as positive value
            metrics.consecutive_losses += 1
            metrics.consecutive_wins = 0
            metrics.max_consecutive_losses = max(
                metrics.max_consecutive_losses, metrics.consecutive_losses
            )
            if pnl < metrics.largest_loss:
                metrics.largest_loss = pnl
        else:
            metrics.breakeven_trades += 1
            metrics.consecutive_wins = 0
            metrics.consecutive_losses = 0

        # Update ratios
        if metrics.total_trades > 0:
            metrics.win_rate = metrics.winning_trades / metrics.total_trades
            metrics.loss_rate = metrics.losing_trades / metrics.total_trades
            metrics.avg_trade = metrics.total_pnl / metrics.total_trades

        if metrics.winning_trades > 0:
            metrics.avg_win = metrics.gross_profit / metrics.winning_trades

        if metrics.losing_trades > 0:
            metrics.avg_loss = metrics.gross_loss / metrics.losing_trades

        if metrics.gross_loss > 0:
            metrics.profit_factor = metrics.gross_profit / metrics.gross_loss

        # Update holding period
        if execution.holding_period:
            total_holding_time = sum(
                e.holding_period
                for e in self._trade_executions.values()
                if e.strategy_name == execution.strategy_name and e.holding_period
            )
            completed_trades = len(
                [
                    e
                    for e in self._trade_executions.values()
                    if e.strategy_name == execution.strategy_name and e.holding_period
                ]
            )
            metrics.avg_holding_period = (
                total_holding_time / completed_trades if completed_trades > 0 else 0
            )

        metrics.last_updated = time.time()

        # Update drawdown tracking
        self._update_drawdown_metrics(metrics)

    def _update_position_tracking(self, execution: TradeExecution):
        """Track open positions for unrealized P&L calculation."""
        strategy_name = execution.strategy_name
        token_id = execution.token_id

        if strategy_name not in self._open_positions:
            self._open_positions[strategy_name] = {}

        if token_id not in self._open_positions[strategy_name]:
            self._open_positions[strategy_name][token_id] = {
                "quantity": 0.0,
                "avg_price": 0.0,
                "total_cost": 0.0,
                "last_updated": time.time(),
            }

        position = self._open_positions[strategy_name][token_id]

        # Update position based on trade side
        trade_quantity = (
            execution.executed_size
            if execution.side == "buy"
            else -execution.executed_size
        )

        if position["quantity"] == 0:
            # Opening new position
            position["quantity"] = trade_quantity
            position["avg_price"] = execution.executed_price
            position["total_cost"] = execution.notional_value
        else:
            # Adding to existing position
            new_total_cost = position["total_cost"] + execution.notional_value
            new_quantity = position["quantity"] + trade_quantity

            if new_quantity != 0:
                position["avg_price"] = new_total_cost / abs(new_quantity)
            position["quantity"] = new_quantity
            position["total_cost"] = new_total_cost

        position["last_updated"] = time.time()

    def _close_position_tracking(self, execution: TradeExecution):
        """Update position tracking when a trade is closed."""
        strategy_name = execution.strategy_name
        token_id = execution.token_id

        if (
            strategy_name in self._open_positions
            and token_id in self._open_positions[strategy_name]
        ):
            position = self._open_positions[strategy_name][token_id]

            # Record position in history before closing
            self._position_history[strategy_name].append(
                {
                    "token_id": token_id,
                    "open_time": execution.execution_timestamp,
                    "close_time": execution.exit_timestamp,
                    "quantity": position["quantity"],
                    "avg_price": position["avg_price"],
                    "exit_price": execution.exit_price,
                    "realized_pnl": execution.realized_pnl,
                    "holding_period": execution.holding_period,
                }
            )

            # Close position
            del self._open_positions[strategy_name][token_id]

    def _update_unrealized_pnl(self):
        """Update unrealized P&L for all open positions."""
        for strategy_name, positions in self._open_positions.items():
            metrics = self._strategy_metrics[strategy_name]
            total_unrealized = 0.0

            for token_id, position in positions.items():
                if token_id in self._market_prices:
                    current_price = self._market_prices[token_id]
                    unrealized_pnl = (current_price - position["avg_price"]) * position[
                        "quantity"
                    ]
                    total_unrealized += unrealized_pnl

            metrics.unrealized_pnl = total_unrealized
            metrics.last_updated = time.time()

    def _update_drawdown_metrics(self, metrics: StrategyPerformanceMetrics):
        """Update drawdown metrics for a strategy."""
        # Get equity curve
        strategy_executions = [
            e
            for e in self._trade_executions.values()
            if e.strategy_name == metrics.strategy_name and e.realized_pnl is not None
        ]

        if not strategy_executions:
            return

        # Sort by execution time
        strategy_executions.sort(key=lambda x: x.execution_timestamp)

        # Calculate running equity
        running_equity = 0.0
        peak_equity = 0.0
        max_drawdown = 0.0

        for execution in strategy_executions:
            running_equity += execution.realized_pnl
            peak_equity = max(peak_equity, running_equity)

            current_drawdown = peak_equity - running_equity
            max_drawdown = max(max_drawdown, current_drawdown)

        metrics.max_drawdown = max_drawdown
        if peak_equity > 0:
            metrics.max_drawdown_percent = (max_drawdown / peak_equity) * 100

    async def _take_performance_snapshots(self):
        """Take performance snapshots for time series analysis."""
        current_time = time.time()

        for strategy_name, metrics in self._strategy_metrics.items():
            # Calculate daily P&L
            daily_pnl = self._calculate_daily_pnl(strategy_name)

            # Calculate current equity (realized + unrealized)
            equity_value = metrics.realized_pnl + metrics.unrealized_pnl

            # Calculate current drawdown percentage
            drawdown_pct = metrics.max_drawdown_percent

            snapshot = PerformanceSnapshot(
                timestamp=current_time,
                strategy_name=strategy_name,
                equity_value=equity_value,
                drawdown=drawdown_pct,
                daily_pnl=daily_pnl,
                trade_count=metrics.total_trades,
                win_rate=metrics.win_rate,
            )

            self._performance_snapshots[strategy_name].append(snapshot)

    def _calculate_daily_pnl(self, strategy_name: str) -> float:
        """Calculate P&L for the current day."""
        today_start = (
            datetime.now()
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )

        daily_pnl = 0.0
        for execution in self._trade_executions.values():
            if (
                execution.strategy_name == strategy_name
                and execution.realized_pnl is not None
                and execution.exit_timestamp
                and execution.exit_timestamp >= today_start
            ):
                daily_pnl += execution.realized_pnl

        return daily_pnl

    def get_strategy_performance(
        self, strategy_name: str
    ) -> StrategyPerformanceMetrics | None:
        """Get comprehensive performance metrics for a strategy."""
        return self._strategy_metrics.get(strategy_name)

    def get_all_strategies_performance(self) -> dict[str, StrategyPerformanceMetrics]:
        """Get performance metrics for all strategies."""
        return self._strategy_metrics.copy()

    def get_strategy_ranking(
        self, metric: str = "net_profit"
    ) -> list[tuple[str, float]]:
        """Get strategies ranked by a specific performance metric."""
        rankings = []

        for strategy_name, metrics in self._strategy_metrics.items():
            if hasattr(metrics, metric):
                value = getattr(metrics, metric)
                rankings.append((strategy_name, value))

        # Sort by metric value (descending)
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings

    def get_performance_summary(self) -> dict[str, Any]:
        """Get overall performance summary across all strategies."""
        if not self._strategy_metrics:
            return {"total_strategies": 0, "message": "No strategy data available"}

        # Aggregate metrics across all strategies
        total_trades = sum(m.total_trades for m in self._strategy_metrics.values())
        total_pnl = sum(m.total_pnl for m in self._strategy_metrics.values())
        total_fees = sum(m.total_fees for m in self._strategy_metrics.values())
        total_volume = sum(m.total_volume for m in self._strategy_metrics.values())

        winning_strategies = len(
            [m for m in self._strategy_metrics.values() if m.net_profit > 0]
        )

        best_strategy = max(
            self._strategy_metrics.items(), key=lambda x: x[1].net_profit
        )
        worst_strategy = min(
            self._strategy_metrics.items(), key=lambda x: x[1].net_profit
        )

        return {
            "total_strategies": len(self._strategy_metrics),
            "winning_strategies": winning_strategies,
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "total_fees": total_fees,
            "net_profit": total_pnl - total_fees,
            "total_volume": total_volume,
            "best_strategy": {
                "name": best_strategy[0],
                "net_profit": best_strategy[1].net_profit,
                "win_rate": best_strategy[1].win_rate,
            },
            "worst_strategy": {
                "name": worst_strategy[0],
                "net_profit": worst_strategy[1].net_profit,
                "win_rate": worst_strategy[1].win_rate,
            },
            "overall_win_rate": (
                sum(m.winning_trades for m in self._strategy_metrics.values())
                / total_trades
                if total_trades > 0
                else 0.0
            ),
        }

    def get_trade_history(
        self, strategy_name: str | None = None, limit: int = 100
    ) -> list[TradeExecution]:
        """Get trade execution history, optionally filtered by strategy."""
        executions = list(self._trade_executions.values())

        if strategy_name:
            executions = [e for e in executions if e.strategy_name == strategy_name]

        # Sort by execution time (most recent first)
        executions.sort(key=lambda x: x.execution_timestamp, reverse=True)

        return executions[:limit]

    def calculate_risk_metrics(self, strategy_name: str) -> dict[str, float | None]:
        """Calculate advanced risk metrics for a strategy."""
        metrics = self._strategy_metrics.get(strategy_name)
        if not metrics:
            return {}

        # Get trade returns
        returns = []
        for execution in self._trade_executions.values():
            if (
                execution.strategy_name == strategy_name
                and execution.realized_pnl is not None
                and execution.notional_value > 0
            ):
                returns.append(execution.realized_pnl / execution.notional_value)

        if not returns:
            return {"sharpe_ratio": None, "sortino_ratio": None, "calmar_ratio": None}

        # Calculate Sharpe ratio
        if len(returns) > 1:
            import statistics

            mean_return = statistics.mean(returns)
            std_return = statistics.stdev(returns)

            if std_return > 0:
                daily_risk_free_rate = self._risk_free_rate / 365
                sharpe_ratio = (mean_return - daily_risk_free_rate) / std_return
            else:
                sharpe_ratio = None
        else:
            sharpe_ratio = None

        # Calculate Sortino ratio (using downside deviation)
        negative_returns = [r for r in returns if r < 0]
        if negative_returns and len(negative_returns) > 1:
            import statistics

            downside_deviation = statistics.stdev(negative_returns)
            daily_risk_free_rate = self._risk_free_rate / 365
            if downside_deviation > 0:
                sortino_ratio = (
                    statistics.mean(returns) - daily_risk_free_rate
                ) / downside_deviation
            else:
                sortino_ratio = None
        else:
            sortino_ratio = None

        # Calculate Calmar ratio
        if metrics.max_drawdown > 0 and metrics.total_trades > 0:
            annualized_return = metrics.avg_trade * 252  # Assuming daily trading
            calmar_ratio = annualized_return / (metrics.max_drawdown / 100)
        else:
            calmar_ratio = None

        return {
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "calmar_ratio": calmar_ratio,
        }
