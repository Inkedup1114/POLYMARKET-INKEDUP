"""
Kelly Criterion Position Sizing for Optimal Capital Allocation.

This module implements Kelly Criterion-based position sizing to optimize risk-adjusted
returns by calculating position sizes that maximize long-term capital growth while
managing downside risk.

The Kelly formula determines the optimal fraction of capital to risk:
f* = (bp - q) / b

Where:
- f* = fraction of capital to bet (position size)
- b = odds received (payout ratio - 1)  
- p = probability of winning
- q = probability of losing (1 - p)

For trading applications, this is adapted to account for:
- Historical win rates and profit/loss ratios
- Market-specific success rates
- Risk adjustment factors
- Position sizing constraints

Key Features:
- Dynamic win rate tracking per strategy and market
- Risk-adjusted Kelly fraction calculation
- Position size optimization based on historical performance
- Conservative sizing with maximum limits for risk management
- Performance tracking and analysis capabilities
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


@dataclass
class TradeOutcome:
    """Record of a completed trade for Kelly Criterion analysis."""

    strategy_name: str
    market_slug: str
    trade_type: str  # e.g., "complement_arb", "spread_alert"
    position_size_usd: float
    profit_loss_usd: float
    win: bool
    trade_time: float
    deviation_at_entry: float = 0.0
    confidence_score: float = 0.0

    @property
    def profit_loss_ratio(self) -> float:
        """Calculate profit/loss as ratio of position size."""
        if self.position_size_usd == 0:
            return 0.0
        return self.profit_loss_usd / self.position_size_usd


@dataclass
class KellyStatistics:
    """Statistical data for Kelly Criterion calculation."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_profit: float = 0.0
    total_loss: float = 0.0
    win_rate: float = 0.0
    avg_win_amount: float = 0.0
    avg_loss_amount: float = 0.0
    profit_loss_ratio: float = 0.0  # Average win / Average loss
    kelly_fraction: float = 0.0
    recommended_size: float = 0.0
    last_updated: float = field(default_factory=time.time)

    def update_statistics(self, trades: List[TradeOutcome]) -> None:
        """Update statistics from trade history."""
        if not trades:
            return

        self.total_trades = len(trades)
        wins = [t for t in trades if t.win]
        losses = [t for t in trades if not t.win]

        self.winning_trades = len(wins)
        self.losing_trades = len(losses)

        if self.total_trades > 0:
            self.win_rate = self.winning_trades / self.total_trades

        if wins:
            win_amounts = [t.profit_loss_usd for t in wins]
            self.total_profit = sum(win_amounts)
            self.avg_win_amount = self.total_profit / len(wins)

        if losses:
            loss_amounts = [abs(t.profit_loss_usd) for t in losses]  # Make positive
            self.total_loss = sum(loss_amounts)
            self.avg_loss_amount = self.total_loss / len(losses)

        # Calculate profit/loss ratio
        if self.avg_loss_amount > 0:
            self.profit_loss_ratio = self.avg_win_amount / self.avg_loss_amount
        else:
            self.profit_loss_ratio = float("inf") if self.avg_win_amount > 0 else 0.0

        # Calculate Kelly fraction
        self.kelly_fraction = self._calculate_kelly_fraction()
        self.last_updated = time.time()

    def _calculate_kelly_fraction(self) -> float:
        """Calculate Kelly Criterion fraction."""
        if self.win_rate <= 0 or self.profit_loss_ratio <= 0:
            return 0.0

        # Kelly formula: f* = (bp - q) / b
        # where b = profit/loss ratio, p = win rate, q = 1 - win rate
        p = self.win_rate
        q = 1.0 - p
        b = self.profit_loss_ratio

        kelly = (b * p - q) / b

        # Kelly can be negative (indicating not to bet), we'll cap at 0
        return max(0.0, kelly)


class KellyCriterionPositionSizer:
    """
    Kelly Criterion-based position sizing system for optimal capital allocation.

    This class tracks trading performance across strategies and markets to calculate
    optimal position sizes using the Kelly Criterion. It adapts position sizes
    based on historical win rates and profit/loss ratios to maximize long-term growth.
    """

    def __init__(
        self,
        max_position_pct: float = 0.10,  # Maximum 10% of capital per position
        min_position_usd: float = 5.0,  # Minimum position size
        max_position_usd: float = 500.0,  # Maximum position size
        kelly_multiplier: float = 0.25,  # Conservative Kelly fraction (25%)
        min_trades_for_kelly: int = 20,  # Minimum trades before using Kelly
        history_window: int = 100,  # Number of recent trades to consider
        confidence_adjustment: bool = True,  # Adjust size based on confidence scores
        market_specific_sizing: bool = True,  # Use market-specific statistics
    ):
        """
        Initialize Kelly Criterion position sizer.

        Args:
            max_position_pct: Maximum percentage of capital per position
            min_position_usd: Minimum position size in USD
            max_position_usd: Maximum position size in USD
            kelly_multiplier: Fraction of Kelly recommendation to use (conservative)
            min_trades_for_kelly: Minimum trades needed before using Kelly sizing
            history_window: Number of recent trades to analyze
            confidence_adjustment: Whether to adjust sizes based on signal confidence
            market_specific_sizing: Whether to use market-specific Kelly calculations
        """
        self.max_position_pct = max_position_pct
        self.min_position_usd = min_position_usd
        self.max_position_usd = max_position_usd
        self.kelly_multiplier = kelly_multiplier
        self.min_trades_for_kelly = min_trades_for_kelly
        self.history_window = history_window
        self.confidence_adjustment = confidence_adjustment
        self.market_specific_sizing = market_specific_sizing

        # Trade history storage
        self.trade_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=history_window)
        )
        self.market_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=history_window)
        )

        # Cached statistics
        self.strategy_stats: Dict[str, KellyStatistics] = {}
        self.market_stats: Dict[str, KellyStatistics] = {}
        self.global_stats = KellyStatistics()

        # Performance tracking
        self.sizing_metrics = {
            "positions_sized": 0,
            "kelly_sizing_used": 0,
            "fallback_sizing_used": 0,
            "total_capital_allocated": 0.0,
            "avg_position_size": 0.0,
            "size_adjustments": 0,
        }

        log.info(
            f"KellyCriterionPositionSizer initialized: max_pct={max_position_pct:.1%}, "
            f"kelly_multiplier={kelly_multiplier:.2f}, min_trades={min_trades_for_kelly}"
        )

    def calculate_position_size(
        self,
        strategy_name: str,
        market_slug: str,
        trade_type: str,
        base_size_usd: float,
        available_capital: float,
        confidence_score: float = 0.5,
        deviation_magnitude: float = 0.0,
    ) -> Tuple[float, str, Dict]:
        """
        Calculate optimal position size using Kelly Criterion.

        Args:
            strategy_name: Name of the trading strategy
            market_slug: Market identifier
            trade_type: Type of trade (e.g., "complement_arb")
            base_size_usd: Original position size before Kelly adjustment
            available_capital: Total available capital
            confidence_score: Signal confidence (0.0-1.0)
            deviation_magnitude: Size of opportunity (for complement arb)

        Returns:
            Tuple of (position_size_usd, sizing_method, metadata_dict)
        """
        self.sizing_metrics["positions_sized"] += 1

        # Get relevant statistics
        strategy_stats = self._get_strategy_statistics(strategy_name)
        market_stats = (
            self._get_market_statistics(market_slug)
            if self.market_specific_sizing
            else None
        )

        # Determine which stats to use (market-specific if available, else strategy-level)
        primary_stats = (
            market_stats
            if (market_stats and market_stats.total_trades >= 10)
            else strategy_stats
        )

        # Check if we have enough data for Kelly sizing
        if primary_stats.total_trades >= self.min_trades_for_kelly:
            kelly_size = self._calculate_kelly_size(
                primary_stats, available_capital, confidence_score, deviation_magnitude
            )
            sizing_method = f"kelly_{primary_stats.total_trades}trades"
            self.sizing_metrics["kelly_sizing_used"] += 1
        else:
            # Fallback to traditional sizing with conservative adjustments
            kelly_size = self._calculate_fallback_size(
                base_size_usd, available_capital, confidence_score
            )
            sizing_method = f"fallback_{primary_stats.total_trades}trades"
            self.sizing_metrics["fallback_sizing_used"] += 1

        # Apply constraints and adjustments
        final_size = self._apply_sizing_constraints(kelly_size, available_capital)

        # Update metrics
        self.sizing_metrics["total_capital_allocated"] += final_size
        self._update_avg_position_size(final_size)

        # Prepare metadata
        metadata = {
            "kelly_fraction": primary_stats.kelly_fraction,
            "win_rate": primary_stats.win_rate,
            "profit_loss_ratio": primary_stats.profit_loss_ratio,
            "total_trades": primary_stats.total_trades,
            "confidence_score": confidence_score,
            "raw_kelly_size": kelly_size,
            "sizing_method": sizing_method,
            "capital_fraction": (
                final_size / available_capital if available_capital > 0 else 0.0
            ),
        }

        log.debug(
            f"Position sized for {strategy_name}:{market_slug} - "
            f"${final_size:.2f} ({sizing_method}, "
            f"kelly_frac={primary_stats.kelly_fraction:.3f}, "
            f"win_rate={primary_stats.win_rate:.2%})"
        )

        return final_size, sizing_method, metadata

    def _calculate_kelly_size(
        self,
        stats: KellyStatistics,
        available_capital: float,
        confidence_score: float,
        deviation_magnitude: float,
    ) -> float:
        """Calculate position size using Kelly Criterion."""
        if stats.kelly_fraction <= 0:
            return self.min_position_usd

        # Base Kelly size
        kelly_capital_fraction = stats.kelly_fraction * self.kelly_multiplier
        base_kelly_size = kelly_capital_fraction * available_capital

        # Confidence adjustment
        if self.confidence_adjustment and confidence_score > 0:
            # Adjust size based on signal confidence (0.5-1.5x multiplier)
            confidence_multiplier = 0.5 + confidence_score
            base_kelly_size *= confidence_multiplier

        # Opportunity size adjustment (for arbitrage strategies)
        if deviation_magnitude > 0:
            # Larger deviations warrant larger positions (within limits)
            deviation_multiplier = min(2.0, 1.0 + deviation_magnitude * 10)  # Cap at 2x
            base_kelly_size *= deviation_multiplier

        return base_kelly_size

    def _calculate_fallback_size(
        self, base_size: float, available_capital: float, confidence_score: float
    ) -> float:
        """Calculate position size using fallback method when insufficient Kelly data."""
        # Use conservative fraction of available capital
        conservative_fraction = 0.02  # 2% of capital as base
        fallback_size = available_capital * conservative_fraction

        # Blend with original base size
        blended_size = (fallback_size + base_size) / 2

        # Confidence adjustment
        if self.confidence_adjustment and confidence_score > 0:
            confidence_multiplier = 0.7 + (confidence_score * 0.6)  # 0.7-1.3x
            blended_size *= confidence_multiplier

        return blended_size

    def _apply_sizing_constraints(self, size: float, available_capital: float) -> float:
        """Apply minimum, maximum, and percentage constraints to position size."""
        # Apply minimum size
        size = max(size, self.min_position_usd)

        # Apply maximum size
        size = min(size, self.max_position_usd)

        # Apply maximum percentage of capital
        max_by_percentage = available_capital * self.max_position_pct
        if size > max_by_percentage:
            size = max_by_percentage
            self.sizing_metrics["size_adjustments"] += 1

        return round(size, 2)

    def record_trade_outcome(
        self,
        strategy_name: str,
        market_slug: str,
        trade_type: str,
        position_size_usd: float,
        profit_loss_usd: float,
        deviation_at_entry: float = 0.0,
        confidence_score: float = 0.0,
    ) -> None:
        """
        Record the outcome of a trade for Kelly Criterion analysis.

        Args:
            strategy_name: Name of the trading strategy
            market_slug: Market identifier
            trade_type: Type of trade
            position_size_usd: Position size that was used
            profit_loss_usd: Profit or loss from the trade (negative for losses)
            deviation_at_entry: Market deviation when trade was entered
            confidence_score: Signal confidence score
        """
        outcome = TradeOutcome(
            strategy_name=strategy_name,
            market_slug=market_slug,
            trade_type=trade_type,
            position_size_usd=position_size_usd,
            profit_loss_usd=profit_loss_usd,
            win=profit_loss_usd > 0,
            trade_time=time.time(),
            deviation_at_entry=deviation_at_entry,
            confidence_score=confidence_score,
        )

        # Store in appropriate histories
        self.trade_history[strategy_name].append(outcome)
        if self.market_specific_sizing:
            self.market_history[market_slug].append(outcome)

        # Invalidate cached statistics
        self._invalidate_statistics_cache(strategy_name, market_slug)

        log.debug(
            f"Trade outcome recorded: {strategy_name}:{market_slug} "
            f"${position_size_usd:.2f} → ${profit_loss_usd:+.2f} ({'WIN' if outcome.win else 'LOSS'})"
        )

    def _get_strategy_statistics(self, strategy_name: str) -> KellyStatistics:
        """Get or calculate statistics for a strategy."""
        if strategy_name not in self.strategy_stats:
            stats = KellyStatistics()
            trades = list(self.trade_history[strategy_name])
            stats.update_statistics(trades)
            self.strategy_stats[strategy_name] = stats

        return self.strategy_stats[strategy_name]

    def _get_market_statistics(self, market_slug: str) -> Optional[KellyStatistics]:
        """Get or calculate statistics for a specific market."""
        if not self.market_specific_sizing:
            return None

        if market_slug not in self.market_stats:
            stats = KellyStatistics()
            trades = list(self.market_history[market_slug])
            stats.update_statistics(trades)
            self.market_stats[market_slug] = stats

        return self.market_stats[market_slug]

    def _invalidate_statistics_cache(
        self, strategy_name: str, market_slug: str
    ) -> None:
        """Invalidate cached statistics after new trade data."""
        if strategy_name in self.strategy_stats:
            del self.strategy_stats[strategy_name]
        if market_slug in self.market_stats:
            del self.market_stats[market_slug]

    def _update_avg_position_size(self, size: float) -> None:
        """Update running average position size."""
        total_positions = self.sizing_metrics["positions_sized"]
        current_avg = self.sizing_metrics["avg_position_size"]

        self.sizing_metrics["avg_position_size"] = (
            current_avg * (total_positions - 1) + size
        ) / total_positions

    def get_sizing_statistics(self) -> Dict:
        """Get comprehensive position sizing statistics."""
        return {
            "configuration": {
                "max_position_pct": self.max_position_pct,
                "kelly_multiplier": self.kelly_multiplier,
                "min_trades_for_kelly": self.min_trades_for_kelly,
                "market_specific_sizing": self.market_specific_sizing,
            },
            "performance": self.sizing_metrics,
            "strategies_tracked": len(self.trade_history),
            "markets_tracked": len(self.market_history),
            "total_trade_outcomes": sum(
                len(hist) for hist in self.trade_history.values()
            ),
        }

    def get_strategy_performance(self, strategy_name: str) -> Optional[Dict]:
        """Get detailed performance statistics for a strategy."""
        if strategy_name not in self.trade_history:
            return None

        stats = self._get_strategy_statistics(strategy_name)
        trades = list(self.trade_history[strategy_name])

        return {
            "strategy_name": strategy_name,
            "statistics": stats,
            "trade_count": len(trades),
            "recent_trades": [
                {
                    "market": t.market_slug,
                    "size_usd": t.position_size_usd,
                    "pnl_usd": t.profit_loss_usd,
                    "win": t.win,
                    "time": t.trade_time,
                }
                for t in trades[-10:]  # Last 10 trades
            ],
        }

    def optimize_kelly_parameters(self) -> Dict:
        """Analyze performance and suggest Kelly parameter optimizations."""
        optimizations = {}

        for strategy_name, trades_deque in self.trade_history.items():
            trades = list(trades_deque)
            if len(trades) < 50:  # Need substantial data
                continue

            # Test different Kelly multipliers
            multipliers = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4]
            best_multiplier = self.kelly_multiplier
            best_return = -float("inf")

            for multiplier in multipliers:
                simulated_return = self._simulate_kelly_performance(trades, multiplier)
                if simulated_return > best_return:
                    best_return = simulated_return
                    best_multiplier = multiplier

            optimizations[strategy_name] = {
                "current_multiplier": self.kelly_multiplier,
                "optimal_multiplier": best_multiplier,
                "improvement_pct": (
                    (
                        best_return
                        / self._simulate_kelly_performance(
                            trades, self.kelly_multiplier
                        )
                    )
                    - 1
                )
                * 100,
                "trade_count": len(trades),
            }

        return optimizations

    def _simulate_kelly_performance(
        self, trades: List[TradeOutcome], kelly_multiplier: float
    ) -> float:
        """Simulate performance with different Kelly multiplier."""
        capital = 10000.0  # Starting capital for simulation

        for trade in trades:
            if capital <= 0:
                break

            # Calculate what position size would have been with this multiplier
            stats = KellyStatistics()
            stats.update_statistics(
                trades[: trades.index(trade)]
            )  # Use data available at time

            if stats.kelly_fraction > 0:
                position_fraction = stats.kelly_fraction * kelly_multiplier
                position_size = min(
                    capital * position_fraction, capital * 0.1
                )  # Cap at 10%
            else:
                position_size = capital * 0.01  # 1% fallback

            # Apply the trade outcome
            capital += position_size * trade.profit_loss_ratio

        return capital

    def reset_history(self, strategy_name: str = None, market_slug: str = None) -> None:
        """Reset trade history for debugging or strategy changes."""
        if strategy_name:
            if strategy_name in self.trade_history:
                self.trade_history[strategy_name].clear()
            if strategy_name in self.strategy_stats:
                del self.strategy_stats[strategy_name]
        elif market_slug:
            if market_slug in self.market_history:
                self.market_history[market_slug].clear()
            if market_slug in self.market_stats:
                del self.market_stats[market_slug]
        else:
            # Reset everything
            self.trade_history.clear()
            self.market_history.clear()
            self.strategy_stats.clear()
            self.market_stats.clear()

        log.info(f"Trade history reset for {strategy_name or market_slug or 'all'}")


# Global instance for easy access across strategies
_global_position_sizer: Optional[KellyCriterionPositionSizer] = None


def get_position_sizer() -> KellyCriterionPositionSizer:
    """Get or create global Kelly Criterion position sizer."""
    global _global_position_sizer
    if _global_position_sizer is None:
        _global_position_sizer = KellyCriterionPositionSizer()
    return _global_position_sizer


def set_position_sizer(sizer: KellyCriterionPositionSizer) -> None:
    """Set global position sizer instance."""
    global _global_position_sizer
    _global_position_sizer = sizer
