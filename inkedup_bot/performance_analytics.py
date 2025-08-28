"""
Advanced performance analytics and reporting for trading strategies.

This module provides comprehensive analysis tools including:
- Strategy performance comparison
- Risk-adjusted returns analysis
- Time-series performance analysis
- Correlation analysis between strategies
- Performance attribution analysis
- Advanced statistical metrics
"""

from __future__ import annotations

import json
import logging
import statistics
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from typing import Any

import numpy as np

from .performance_tracking import (
    PerformanceTracker,
    StrategyPerformanceMetrics,
)

logger = logging.getLogger("performance_analytics")


class PerformanceAnalytics:
    """
    Advanced analytics engine for trading strategy performance analysis.

    Features:
    - Multi-strategy performance comparison
    - Risk-adjusted performance metrics
    - Correlation analysis
    - Performance attribution
    - Scenario analysis
    - Statistical significance testing
    """

    def __init__(self, performance_tracker: PerformanceTracker):
        self.tracker = performance_tracker

    def generate_performance_report(
        self,
        strategy_names: list[str] | None = None,
        time_period: tuple[float, float] | None = None,
    ) -> dict[str, Any]:
        """
        Generate comprehensive performance report.

        Args:
            strategy_names: List of strategies to include (all if None)
            time_period: (start_timestamp, end_timestamp) for analysis period

        Returns:
            Comprehensive performance report
        """
        strategies = strategy_names or list(self.tracker._strategy_metrics.keys())

        report = {
            "report_timestamp": datetime.now().isoformat(),
            "time_period": time_period,
            "strategies_analyzed": len(strategies),
            "individual_performance": {},
            "comparative_analysis": {},
            "portfolio_metrics": {},
            "risk_analysis": {},
            "recommendations": [],
        }

        # Individual strategy performance
        for strategy_name in strategies:
            metrics = self.tracker.get_strategy_performance(strategy_name)
            if metrics:
                report["individual_performance"][strategy_name] = (
                    self._analyze_strategy_performance(metrics)
                )

        # Comparative analysis
        if len(strategies) > 1:
            report["comparative_analysis"] = self._perform_comparative_analysis(
                strategies
            )

        # Portfolio-level metrics
        report["portfolio_metrics"] = self._calculate_portfolio_metrics(strategies)

        # Risk analysis
        report["risk_analysis"] = self._perform_risk_analysis(strategies)

        # Generate recommendations
        report["recommendations"] = self._generate_recommendations(strategies)

        return report

    def _analyze_strategy_performance(
        self, metrics: StrategyPerformanceMetrics
    ) -> dict[str, Any]:
        """Analyze individual strategy performance."""

        # Calculate additional derived metrics
        risk_metrics = self.tracker.calculate_risk_metrics(metrics.strategy_name)

        # Performance classification
        performance_grade = self._classify_performance(metrics)

        # Consistency metrics
        consistency = self._calculate_consistency_metrics(metrics.strategy_name)

        return {
            "basic_metrics": {
                "total_trades": metrics.total_trades,
                "win_rate": round(metrics.win_rate * 100, 2),
                "profit_factor": round(metrics.profit_factor, 3),
                "net_profit": round(metrics.net_profit, 2),
                "avg_trade": round(metrics.avg_trade, 3),
                "max_drawdown": round(metrics.max_drawdown, 2),
                "sharpe_ratio": round(risk_metrics.get("sharpe_ratio", 0) or 0, 3),
            },
            "performance_grade": performance_grade,
            "consistency_metrics": consistency,
            "risk_metrics": risk_metrics,
            "trading_frequency": self._calculate_trading_frequency(metrics),
            "performance_trend": self._analyze_performance_trend(metrics.strategy_name),
        }

    def _classify_performance(self, metrics: StrategyPerformanceMetrics) -> str:
        """Classify strategy performance into grades."""

        score = 0

        # Win rate scoring (30% weight)
        if metrics.win_rate >= 0.70:
            score += 30
        elif metrics.win_rate >= 0.60:
            score += 25
        elif metrics.win_rate >= 0.50:
            score += 20
        elif metrics.win_rate >= 0.40:
            score += 10

        # Profit factor scoring (25% weight)
        if metrics.profit_factor >= 2.0:
            score += 25
        elif metrics.profit_factor >= 1.5:
            score += 20
        elif metrics.profit_factor >= 1.2:
            score += 15
        elif metrics.profit_factor >= 1.0:
            score += 10

        # Net profit scoring (25% weight)
        if metrics.net_profit >= 1000:
            score += 25
        elif metrics.net_profit >= 500:
            score += 20
        elif metrics.net_profit >= 100:
            score += 15
        elif metrics.net_profit >= 0:
            score += 10

        # Drawdown scoring (20% weight) - lower is better
        if metrics.max_drawdown_percent <= 5:
            score += 20
        elif metrics.max_drawdown_percent <= 10:
            score += 15
        elif metrics.max_drawdown_percent <= 20:
            score += 10
        elif metrics.max_drawdown_percent <= 35:
            score += 5

        # Classify based on total score
        if score >= 85:
            return "A+"
        elif score >= 75:
            return "A"
        elif score >= 65:
            return "B+"
        elif score >= 55:
            return "B"
        elif score >= 45:
            return "C+"
        elif score >= 35:
            return "C"
        else:
            return "D"

    def _calculate_consistency_metrics(self, strategy_name: str) -> dict[str, float]:
        """Calculate consistency and reliability metrics."""

        # Get trade executions for this strategy
        executions = [
            e
            for e in self.tracker._trade_executions.values()
            if e.strategy_name == strategy_name and e.realized_pnl is not None
        ]

        if len(executions) < 5:
            return {"insufficient_data": True}

        # Calculate returns
        returns = [
            e.realized_pnl / e.notional_value
            for e in executions
            if e.notional_value > 0
        ]

        if not returns:
            return {"insufficient_data": True}

        # Statistical measures
        mean_return = statistics.mean(returns)
        std_return = statistics.stdev(returns) if len(returns) > 1 else 0

        # Consistency metrics
        positive_periods = len([r for r in returns if r > 0])
        consistency_ratio = positive_periods / len(returns)

        # Stability metrics
        coefficient_of_variation = (
            abs(std_return / mean_return) if mean_return != 0 else float("inf")
        )

        # Streaks analysis
        current_streak = 0
        max_win_streak = 0
        max_loss_streak = 0

        for execution in sorted(executions, key=lambda x: x.execution_timestamp):
            if execution.realized_pnl > 0:
                current_streak = current_streak + 1 if current_streak >= 0 else 1
                max_win_streak = max(max_win_streak, current_streak)
            else:
                current_streak = current_streak - 1 if current_streak <= 0 else -1
                max_loss_streak = max(max_loss_streak, abs(current_streak))

        return {
            "consistency_ratio": round(consistency_ratio, 3),
            "coefficient_of_variation": round(coefficient_of_variation, 3),
            "return_stability": (
                "High"
                if coefficient_of_variation < 1.0
                else "Medium" if coefficient_of_variation < 2.0 else "Low"
            ),
            "max_win_streak": max_win_streak,
            "max_loss_streak": max_loss_streak,
            "streak_ratio": round(max_win_streak / max(max_loss_streak, 1), 2),
        }

    def _calculate_trading_frequency(
        self, metrics: StrategyPerformanceMetrics
    ) -> dict[str, float]:
        """Calculate trading frequency metrics."""

        if not metrics.first_trade_time or not metrics.last_trade_time:
            return {"trades_per_day": 0, "avg_time_between_trades": 0}

        total_time_days = (metrics.last_trade_time - metrics.first_trade_time) / 86400
        trades_per_day = metrics.total_trades / max(total_time_days, 1)

        avg_time_between_trades = (
            total_time_days * 86400 / max(metrics.total_trades - 1, 1)
        )

        return {
            "trades_per_day": round(trades_per_day, 2),
            "avg_time_between_trades_hours": round(avg_time_between_trades / 3600, 2),
            "total_active_days": round(total_time_days, 1),
        }

    def _analyze_performance_trend(self, strategy_name: str) -> dict[str, Any]:
        """Analyze performance trends over time."""

        snapshots = list(self.tracker._performance_snapshots.get(strategy_name, []))

        if len(snapshots) < 10:
            return {"trend": "insufficient_data"}

        # Recent performance (last 30 snapshots)
        recent_snapshots = snapshots[-30:]
        equity_values = [s.equity_value for s in recent_snapshots]

        # Calculate trend
        if len(equity_values) > 1:
            trend_slope = (equity_values[-1] - equity_values[0]) / len(equity_values)

            if trend_slope > 5:
                trend = "strongly_positive"
            elif trend_slope > 1:
                trend = "positive"
            elif trend_slope > -1:
                trend = "stable"
            elif trend_slope > -5:
                trend = "negative"
            else:
                trend = "strongly_negative"
        else:
            trend = "stable"

        # Volatility analysis
        if len(equity_values) > 1:
            volatility = statistics.stdev(equity_values)
            mean_equity = statistics.mean(equity_values)
            volatility_ratio = volatility / abs(mean_equity) if mean_equity != 0 else 0
        else:
            volatility_ratio = 0

        return {
            "trend": trend,
            "trend_slope": round(trend_slope, 3) if "trend_slope" in locals() else 0,
            "volatility_ratio": round(volatility_ratio, 3),
            "recent_performance": {
                "start_equity": equity_values[0] if equity_values else 0,
                "end_equity": equity_values[-1] if equity_values else 0,
                "change_pct": (
                    round(
                        (
                            (equity_values[-1] - equity_values[0])
                            / abs(equity_values[0])
                            * 100
                        ),
                        2,
                    )
                    if equity_values and equity_values[0] != 0
                    else 0
                ),
            },
        }

    def _perform_comparative_analysis(
        self, strategy_names: list[str]
    ) -> dict[str, Any]:
        """Perform comparative analysis across multiple strategies."""

        strategy_metrics = {
            name: self.tracker.get_strategy_performance(name) for name in strategy_names
        }

        # Filter out None values
        strategy_metrics = {k: v for k, v in strategy_metrics.items() if v is not None}

        if len(strategy_metrics) < 2:
            return {"error": "Insufficient strategies for comparison"}

        # Performance rankings
        rankings = {
            "net_profit": sorted(
                strategy_metrics.items(), key=lambda x: x[1].net_profit, reverse=True
            ),
            "win_rate": sorted(
                strategy_metrics.items(), key=lambda x: x[1].win_rate, reverse=True
            ),
            "profit_factor": sorted(
                strategy_metrics.items(), key=lambda x: x[1].profit_factor, reverse=True
            ),
            "sharpe_ratio": [],
        }

        # Sharpe ratio ranking (requires calculation)
        sharpe_ratios = []
        for name, metrics in strategy_metrics.items():
            risk_metrics = self.tracker.calculate_risk_metrics(name)
            sharpe = risk_metrics.get("sharpe_ratio", 0) or 0
            sharpe_ratios.append((name, sharpe))

        rankings["sharpe_ratio"] = sorted(
            sharpe_ratios, key=lambda x: x[1], reverse=True
        )

        # Performance correlation analysis
        correlations = self._calculate_strategy_correlations(
            list(strategy_metrics.keys())
        )

        # Diversification analysis
        diversification_score = self._calculate_diversification_score(correlations)

        return {
            "rankings": {
                metric: [
                    (
                        name,
                        (
                            round(float(value), 3)
                            if isinstance(value, (int, float))
                            else value
                        ),
                    )
                    for name, value in ranking[:5]
                ]
                for metric, ranking in rankings.items()
            },
            "correlations": correlations,
            "diversification_score": diversification_score,
            "portfolio_composition_recommendation": self._recommend_portfolio_composition(
                strategy_metrics
            ),
        }

    def _calculate_strategy_correlations(
        self, strategy_names: list[str]
    ) -> dict[str, dict[str, float]]:
        """Calculate correlation matrix between strategies."""

        correlations = {}

        for strategy1 in strategy_names:
            correlations[strategy1] = {}

            for strategy2 in strategy_names:
                if strategy1 == strategy2:
                    correlations[strategy1][strategy2] = 1.0
                else:
                    correlation = self._calculate_pairwise_correlation(
                        strategy1, strategy2
                    )
                    correlations[strategy1][strategy2] = correlation

        return correlations

    def _calculate_pairwise_correlation(self, strategy1: str, strategy2: str) -> float:
        """Calculate correlation between two strategies' returns."""

        # Get daily returns for both strategies
        returns1 = self._get_daily_returns(strategy1)
        returns2 = self._get_daily_returns(strategy2)

        # Find common dates
        common_dates = set(returns1.keys()) & set(returns2.keys())

        if len(common_dates) < 5:
            return 0.0  # Insufficient data

        # Extract returns for common dates
        r1_values = [returns1[date] for date in sorted(common_dates)]
        r2_values = [returns2[date] for date in sorted(common_dates)]

        # Calculate correlation
        if (
            len(r1_values) > 1
            and statistics.stdev(r1_values) > 0
            and statistics.stdev(r2_values) > 0
        ):
            correlation = np.corrcoef(r1_values, r2_values)[0, 1]
            return round(float(correlation), 3)

        return 0.0

    def _get_daily_returns(self, strategy_name: str) -> dict[str, float]:
        """Get daily returns for a strategy."""

        daily_returns = defaultdict(float)

        # Get all executions for this strategy
        executions = [
            e
            for e in self.tracker._trade_executions.values()
            if e.strategy_name == strategy_name and e.realized_pnl is not None
        ]

        # Group by date
        for execution in executions:
            if execution.exit_timestamp:
                date_key = (
                    datetime.fromtimestamp(execution.exit_timestamp).date().isoformat()
                )
                daily_returns[date_key] += execution.realized_pnl

        return dict(daily_returns)

    def _calculate_diversification_score(
        self, correlations: dict[str, dict[str, float]]
    ) -> float:
        """Calculate portfolio diversification score (0-100)."""

        if not correlations:
            return 0.0

        # Average correlation (excluding self-correlations)
        total_correlations = 0
        count = 0

        for strategy1, corr_dict in correlations.items():
            for strategy2, correlation in corr_dict.items():
                if strategy1 != strategy2:
                    total_correlations += abs(correlation)
                    count += 1

        if count == 0:
            return 100.0

        avg_correlation = total_correlations / count

        # Convert to diversification score (lower correlation = higher diversification)
        diversification_score = (1 - avg_correlation) * 100
        return round(max(0, min(100, diversification_score)), 1)

    def _recommend_portfolio_composition(
        self, strategy_metrics: dict[str, StrategyPerformanceMetrics]
    ) -> dict[str, Any]:
        """Recommend optimal portfolio composition based on performance metrics."""

        # Score each strategy
        strategy_scores = {}

        for name, metrics in strategy_metrics.items():
            # Multi-factor scoring
            profit_score = min(metrics.net_profit / 1000, 1.0) * 30  # Max 30 points
            win_rate_score = metrics.win_rate * 25  # Max 25 points
            sharpe_score = (
                min(
                    max(
                        self.tracker.calculate_risk_metrics(name).get("sharpe_ratio", 0)
                        or 0,
                        0,
                    ),
                    2,
                )
                * 12.5
            )  # Max 25 points
            drawdown_score = (
                max(0, (50 - metrics.max_drawdown_percent) / 50) * 20
            )  # Max 20 points

            total_score = profit_score + win_rate_score + sharpe_score + drawdown_score
            strategy_scores[name] = total_score

        # Normalize scores to weights
        total_score = sum(strategy_scores.values())

        if total_score <= 0:
            # Equal weighting if no positive scores
            weights = {
                name: 1.0 / len(strategy_metrics) for name in strategy_metrics.keys()
            }
        else:
            weights = {
                name: score / total_score for name, score in strategy_scores.items()
            }

        # Apply minimum and maximum weight constraints
        min_weight = 0.05  # 5% minimum
        max_weight = 0.50  # 50% maximum

        adjusted_weights = {}
        for name, weight in weights.items():
            adjusted_weights[name] = max(min_weight, min(max_weight, weight))

        # Renormalize
        total_adjusted = sum(adjusted_weights.values())
        final_weights = {
            name: weight / total_adjusted for name, weight in adjusted_weights.items()
        }

        return {
            "recommended_weights": {
                name: round(weight * 100, 1) for name, weight in final_weights.items()
            },
            "rationale": "Weights based on net profit, win rate, risk-adjusted returns, and drawdown control",
            "rebalancing_frequency": "monthly",
        }

    def _calculate_portfolio_metrics(self, strategy_names: list[str]) -> dict[str, Any]:
        """Calculate portfolio-level metrics across all strategies."""

        # Aggregate metrics
        total_trades = sum(
            self.tracker._strategy_metrics[name].total_trades
            for name in strategy_names
            if name in self.tracker._strategy_metrics
        )

        total_pnl = sum(
            self.tracker._strategy_metrics[name].total_pnl
            for name in strategy_names
            if name in self.tracker._strategy_metrics
        )

        total_fees = sum(
            self.tracker._strategy_metrics[name].total_fees
            for name in strategy_names
            if name in self.tracker._strategy_metrics
        )

        # Portfolio win rate
        total_wins = sum(
            self.tracker._strategy_metrics[name].winning_trades
            for name in strategy_names
            if name in self.tracker._strategy_metrics
        )

        portfolio_win_rate = total_wins / total_trades if total_trades > 0 else 0

        return {
            "total_trades": total_trades,
            "total_pnl": round(total_pnl, 2),
            "total_fees": round(total_fees, 2),
            "net_profit": round(total_pnl - total_fees, 2),
            "portfolio_win_rate": round(portfolio_win_rate * 100, 2),
            "active_strategies": len(
                [
                    name
                    for name in strategy_names
                    if name in self.tracker._strategy_metrics
                ]
            ),
        }

    def _perform_risk_analysis(self, strategy_names: list[str]) -> dict[str, Any]:
        """Perform comprehensive risk analysis."""

        # Individual strategy risk metrics
        strategy_risks = {}
        for name in strategy_names:
            if name in self.tracker._strategy_metrics:
                metrics = self.tracker._strategy_metrics[name]
                risk_metrics = self.tracker.calculate_risk_metrics(name)

                strategy_risks[name] = {
                    "max_drawdown": metrics.max_drawdown,
                    "max_drawdown_pct": metrics.max_drawdown_percent,
                    "sharpe_ratio": risk_metrics.get("sharpe_ratio"),
                    "largest_loss": metrics.largest_loss,
                    "consecutive_losses": metrics.max_consecutive_losses,
                }

        # Portfolio risk assessment
        portfolio_risk = self._assess_portfolio_risk(strategy_names)

        return {
            "individual_risks": strategy_risks,
            "portfolio_risk": portfolio_risk,
            "risk_warnings": self._generate_risk_warnings(strategy_risks),
        }

    def _assess_portfolio_risk(self, strategy_names: list[str]) -> dict[str, Any]:
        """Assess overall portfolio risk."""

        max_drawdowns = []
        largest_losses = []

        for name in strategy_names:
            if name in self.tracker._strategy_metrics:
                metrics = self.tracker._strategy_metrics[name]
                max_drawdowns.append(metrics.max_drawdown_percent)
                largest_losses.append(abs(metrics.largest_loss))

        if not max_drawdowns:
            return {"risk_level": "unknown"}

        avg_drawdown = statistics.mean(max_drawdowns)
        max_single_loss = max(largest_losses) if largest_losses else 0

        # Risk classification
        if avg_drawdown <= 5 and max_single_loss <= 50:
            risk_level = "low"
        elif avg_drawdown <= 15 and max_single_loss <= 200:
            risk_level = "medium"
        elif avg_drawdown <= 30 and max_single_loss <= 500:
            risk_level = "high"
        else:
            risk_level = "very_high"

        return {
            "risk_level": risk_level,
            "avg_drawdown_pct": round(avg_drawdown, 2),
            "max_single_loss": round(max_single_loss, 2),
            "diversification_benefit": (
                "high"
                if len(strategy_names) >= 3
                else "medium" if len(strategy_names) == 2 else "low"
            ),
        }

    def _generate_risk_warnings(
        self, strategy_risks: dict[str, dict[str, Any]]
    ) -> list[str]:
        """Generate risk warnings based on analysis."""

        warnings = []

        for strategy_name, risks in strategy_risks.items():
            if risks["max_drawdown_pct"] > 25:
                warnings.append(
                    f"High drawdown risk in {strategy_name}: {risks['max_drawdown_pct']:.1f}%"
                )

            if risks["consecutive_losses"] > 5:
                warnings.append(
                    f"High consecutive loss risk in {strategy_name}: {risks['consecutive_losses']} losses"
                )

            if risks["largest_loss"] < -200:
                warnings.append(
                    f"Large single loss risk in {strategy_name}: ${abs(risks['largest_loss']):.2f}"
                )

        return warnings

    def _generate_recommendations(self, strategy_names: list[str]) -> list[str]:
        """Generate actionable recommendations based on analysis."""

        recommendations = []

        # Analyze each strategy
        for name in strategy_names:
            if name not in self.tracker._strategy_metrics:
                continue

            metrics = self.tracker._strategy_metrics[name]

            # Performance-based recommendations
            if metrics.win_rate < 0.4:
                recommendations.append(
                    f"Consider reviewing {name} strategy parameters - low win rate ({metrics.win_rate*100:.1f}%)"
                )

            if metrics.profit_factor < 1.0:
                recommendations.append(
                    f"Disable or modify {name} strategy - negative expected value"
                )

            if metrics.max_drawdown_percent > 20:
                recommendations.append(
                    f"Implement tighter risk controls for {name} - high drawdown risk"
                )

            if metrics.total_trades < 10:
                recommendations.append(
                    f"Gather more data for {name} before making decisions - insufficient sample size"
                )

        # Portfolio-level recommendations
        if len(strategy_names) < 3:
            recommendations.append(
                "Consider adding more strategies for better diversification"
            )

        return recommendations

    def export_performance_data(self, filename: str = None) -> str:
        """Export performance data to JSON file."""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = filename or f"performance_data_{timestamp}.json"

        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "strategies": {},
            "trade_history": [],
        }

        # Export strategy metrics
        for name, metrics in self.tracker._strategy_metrics.items():
            export_data["strategies"][name] = asdict(metrics)

        # Export trade history
        for execution in self.tracker._trade_executions.values():
            export_data["trade_history"].append(asdict(execution))

        # Write to file
        with open(filename, "w") as f:
            json.dump(export_data, f, indent=2, default=str)

        logger.info(f"Performance data exported to {filename}")
        return filename
