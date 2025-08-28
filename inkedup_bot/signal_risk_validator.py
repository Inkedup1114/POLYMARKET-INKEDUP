"""
Signal risk validation module for comprehensive risk assessment integration.

This module provides risk-based validation of trading signals including:
- Portfolio risk assessment
- Position sizing validation
- Exposure limit checks
- Risk-adjusted signal scoring
- Dynamic risk thresholds
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .signals import TradingSignal

logger = logging.getLogger("signal_risk_validator")


class RiskLevel(str, Enum):
    """Risk level classifications."""

    VERY_LOW = "very_low"  # Very low risk
    LOW = "low"  # Low risk
    MODERATE = "moderate"  # Moderate risk
    HIGH = "high"  # High risk
    EXTREME = "extreme"  # Extreme risk


class RiskType(str, Enum):
    """Types of risk factors."""

    POSITION_SIZE = "position_size"  # Position size risk
    PORTFOLIO_CONCENTRATION = "portfolio_concentration"  # Concentration risk
    MARKET_EXPOSURE = "market_exposure"  # Market exposure risk
    CORRELATION = "correlation"  # Correlation risk
    LIQUIDITY = "liquidity"  # Liquidity risk
    VOLATILITY = "volatility"  # Volatility risk
    LEVERAGE = "leverage"  # Leverage risk
    DRAWDOWN = "drawdown"  # Drawdown risk


@dataclass
class RiskMetrics:
    """Risk metrics for a trading signal."""

    signal_id: str
    overall_risk_level: RiskLevel
    overall_risk_score: float  # 0-100, higher = more risky

    # Individual risk components
    position_size_risk: float = 0.0
    concentration_risk: float = 0.0
    market_exposure_risk: float = 0.0
    correlation_risk: float = 0.0
    liquidity_risk: float = 0.0
    volatility_risk: float = 0.0

    # Risk factors
    risk_factors: list[str] = field(default_factory=list)
    risk_warnings: list[str] = field(default_factory=list)

    # Portfolio impact
    portfolio_risk_impact: float = 0.0
    max_loss_estimate: float = 0.0
    var_impact: float | None = None  # Value at Risk impact

    timestamp: float = field(default_factory=time.time)


@dataclass
class PortfolioState:
    """Current portfolio state for risk calculations."""

    total_capital: float
    available_capital: float
    total_positions_value: float
    cash_balance: float

    # Position tracking
    positions: dict[str, float] = field(default_factory=dict)  # token_id -> size
    market_exposures: dict[str, float] = field(
        default_factory=dict
    )  # market -> total exposure

    # Risk tracking
    current_var: float = 0.0  # Current Value at Risk
    max_drawdown: float = 0.0  # Maximum drawdown
    daily_pnl: float = 0.0  # Current day P&L

    # Limits
    max_position_size: float = 10000.0
    max_market_exposure: float = 0.4  # 40% of portfolio
    max_concentration: float = 0.25  # 25% in single position
    max_daily_loss: float = 1000.0  # Daily loss limit

    # Correlation matrix (simplified)
    correlations: dict[tuple[str, str], float] = field(default_factory=dict)


@dataclass
class RiskConfig:
    """Configuration for risk validation."""

    # Risk scoring weights
    position_size_weight: float = 0.25
    concentration_weight: float = 0.20
    market_exposure_weight: float = 0.20
    correlation_weight: float = 0.15
    liquidity_weight: float = 0.10
    volatility_weight: float = 0.10

    # Risk thresholds
    low_risk_threshold: float = 25.0  # Below 25 = low risk
    moderate_risk_threshold: float = 50.0  # Below 50 = moderate risk
    high_risk_threshold: float = 75.0  # Below 75 = high risk

    # Position size limits (as % of portfolio)
    max_single_position_pct: float = 0.10  # 10% max single position
    conservative_position_pct: float = 0.05  # 5% conservative limit

    # Market exposure limits (as % of portfolio)
    max_market_exposure_pct: float = 0.40  # 40% max market exposure
    conservative_market_pct: float = 0.25  # 25% conservative limit

    # Concentration limits
    max_concentration_pct: float = 0.25  # 25% max concentration

    # Volatility-based adjustments
    high_vol_multiplier: float = 1.5  # Increase risk score for high vol
    low_vol_multiplier: float = 0.8  # Decrease risk score for low vol

    # Correlation adjustments
    high_correlation_threshold: float = 0.7  # High correlation threshold
    correlation_penalty: float = 1.3  # Risk multiplier for correlated positions


class SignalRiskValidator:
    """
    Comprehensive risk validator for trading signals.

    Evaluates signals against portfolio risk limits, position sizing rules,
    and dynamic risk thresholds based on current market conditions.
    """

    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()

        # Portfolio state tracking
        self._portfolio_state: PortfolioState | None = None

        # Risk history tracking
        self._risk_history: dict[str, list[RiskMetrics]] = defaultdict(list)

        # Dynamic risk adjustments
        self._risk_adjustments: dict[str, float] = {}  # market -> risk multiplier

        # Statistics
        self._validation_stats = {
            "signals_assessed": 0,
            "high_risk_signals": 0,
            "rejected_signals": 0,
            "risk_warnings": 0,
            "avg_risk_score": 0.0,
        }

        logger.info("SignalRiskValidator initialized")

    def set_portfolio_state(self, portfolio_state: PortfolioState) -> None:
        """Update current portfolio state."""
        self._portfolio_state = portfolio_state
        logger.debug("Portfolio state updated")

    def validate_signal_risk(
        self,
        signal: TradingSignal,
        market_volatility: float | None = None,
        market_liquidity: float | None = None,
    ) -> RiskMetrics:
        """
        Validate risk metrics for a trading signal.

        Args:
            signal: Trading signal to assess
            market_volatility: Current market volatility (optional)
            market_liquidity: Current market liquidity score (optional)

        Returns:
            RiskMetrics with comprehensive risk assessment
        """
        if not self._portfolio_state:
            logger.warning("No portfolio state available for risk assessment")
            return self._create_default_risk_metrics(signal)

        # Initialize risk metrics
        risk_metrics = RiskMetrics(
            signal_id=signal.signal_id or f"signal_{int(time.time())}",
            overall_risk_level=RiskLevel.LOW,
            overall_risk_score=0.0,
        )

        try:
            # Calculate individual risk components
            self._calculate_position_size_risk(signal, risk_metrics)
            self._calculate_concentration_risk(signal, risk_metrics)
            self._calculate_market_exposure_risk(signal, risk_metrics)
            self._calculate_correlation_risk(signal, risk_metrics)

            # Market condition risks
            if market_liquidity is not None:
                self._calculate_liquidity_risk(signal, market_liquidity, risk_metrics)

            if market_volatility is not None:
                self._calculate_volatility_risk(signal, market_volatility, risk_metrics)

            # Calculate overall risk score
            self._calculate_overall_risk_score(risk_metrics)

            # Determine risk level
            self._determine_risk_level(risk_metrics)

            # Calculate portfolio impact
            self._calculate_portfolio_impact(signal, risk_metrics)

            # Apply dynamic adjustments
            self._apply_dynamic_adjustments(signal, risk_metrics)

            # Generate risk factors and warnings
            self._generate_risk_factors(risk_metrics)

            # Store in history
            self._store_risk_history(risk_metrics)

            # Update statistics
            self._update_validation_stats(risk_metrics)

        except Exception as e:
            logger.error(f"Error in risk validation: {e}")
            risk_metrics.overall_risk_level = RiskLevel.EXTREME
            risk_metrics.overall_risk_score = 100.0
            risk_metrics.risk_factors.append(f"Risk calculation error: {str(e)}")

        return risk_metrics

    def _create_default_risk_metrics(self, signal: TradingSignal) -> RiskMetrics:
        """Create default risk metrics when portfolio state unavailable."""
        return RiskMetrics(
            signal_id=signal.signal_id or f"signal_{int(time.time())}",
            overall_risk_level=RiskLevel.MODERATE,
            overall_risk_score=50.0,
            risk_warnings=[
                "Portfolio state unavailable - using default risk assessment"
            ],
        )

    def _calculate_position_size_risk(
        self, signal: TradingSignal, risk_metrics: RiskMetrics
    ) -> None:
        """Calculate position size risk component."""
        portfolio = self._portfolio_state
        if portfolio is None:
            raise ValueError(
                "Portfolio state not available for position size validation"
            )

        position_value = signal.price * signal.size

        # Calculate position size as percentage of portfolio
        position_pct = position_value / portfolio.total_capital

        # Risk scoring based on position size
        if position_pct <= self.config.conservative_position_pct:
            risk_score = 10.0  # Low risk
        elif position_pct <= self.config.max_single_position_pct:
            # Linear scaling between conservative and max
            ratio = (position_pct - self.config.conservative_position_pct) / (
                self.config.max_single_position_pct
                - self.config.conservative_position_pct
            )
            risk_score = 10.0 + (ratio * 40.0)  # 10-50 range
        else:
            # Exponential increase for oversized positions
            excess_ratio = position_pct / self.config.max_single_position_pct
            risk_score = min(100.0, 50.0 * (excess_ratio**2))

        risk_metrics.position_size_risk = risk_score

        if position_pct > self.config.max_single_position_pct:
            risk_metrics.risk_factors.append("OVERSIZED_POSITION")
        elif position_pct > self.config.conservative_position_pct * 2:
            risk_metrics.risk_warnings.append(
                f"Large position size: {position_pct:.1%} of portfolio"
            )

    def _calculate_concentration_risk(
        self, signal: TradingSignal, risk_metrics: RiskMetrics
    ) -> None:
        """Calculate concentration risk component."""
        portfolio = self._portfolio_state
        if portfolio is None:
            raise ValueError(
                "Portfolio state not available for concentration risk validation"
            )

        # Current exposure to this token
        current_exposure = portfolio.positions.get(signal.token_id, 0.0)
        new_exposure = current_exposure + (
            signal.size if signal.side == "buy" else -signal.size
        )

        # Concentration as percentage of portfolio
        concentration_pct = abs(new_exposure * signal.price) / portfolio.total_capital

        # Risk scoring
        if concentration_pct <= self.config.max_concentration_pct * 0.5:
            risk_score = 5.0
        elif concentration_pct <= self.config.max_concentration_pct:
            ratio = concentration_pct / self.config.max_concentration_pct
            risk_score = 5.0 + (ratio * 45.0)  # 5-50 range
        else:
            excess_ratio = concentration_pct / self.config.max_concentration_pct
            risk_score = min(100.0, 50.0 * (excess_ratio**1.5))

        risk_metrics.concentration_risk = risk_score

        if concentration_pct > self.config.max_concentration_pct:
            risk_metrics.risk_factors.append("HIGH_CONCENTRATION")

    def _calculate_market_exposure_risk(
        self, signal: TradingSignal, risk_metrics: RiskMetrics
    ) -> None:
        """Calculate market exposure risk component."""
        portfolio = self._portfolio_state
        if portfolio is None:
            raise ValueError(
                "Portfolio state not available for market exposure risk validation"
            )

        # Current market exposure
        current_exposure = portfolio.market_exposures.get(signal.market_slug, 0.0)
        position_value = signal.price * signal.size
        new_exposure = current_exposure + position_value

        # Market exposure as percentage of portfolio
        exposure_pct = new_exposure / portfolio.total_capital

        # Risk scoring
        if exposure_pct <= self.config.conservative_market_pct:
            risk_score = 8.0
        elif exposure_pct <= self.config.max_market_exposure_pct:
            ratio = (exposure_pct - self.config.conservative_market_pct) / (
                self.config.max_market_exposure_pct
                - self.config.conservative_market_pct
            )
            risk_score = 8.0 + (ratio * 42.0)  # 8-50 range
        else:
            excess_ratio = exposure_pct / self.config.max_market_exposure_pct
            risk_score = min(100.0, 50.0 * (excess_ratio**1.8))

        risk_metrics.market_exposure_risk = risk_score

        if exposure_pct > self.config.max_market_exposure_pct:
            risk_metrics.risk_factors.append("EXCESSIVE_MARKET_EXPOSURE")

    def _calculate_correlation_risk(
        self, signal: TradingSignal, risk_metrics: RiskMetrics
    ) -> None:
        """Calculate correlation risk component."""
        portfolio = self._portfolio_state
        if portfolio is None:
            raise ValueError(
                "Portfolio state not available for correlation risk validation"
            )

        risk_score = 0.0

        # Check correlations with existing positions
        high_correlation_count = 0
        total_correlated_exposure = 0.0

        for token_id, position_size in portfolio.positions.items():
            if abs(position_size) < 0.01:  # Skip tiny positions
                continue

            correlation_key = tuple(sorted([signal.token_id, token_id]))
            # Type assertion to help mypy understand the tuple type
            correlation = (
                portfolio.correlations.get(correlation_key, 0.0)
                if len(correlation_key) == 2
                else 0.0
            )

            if abs(correlation) >= self.config.high_correlation_threshold:
                high_correlation_count += 1
                total_correlated_exposure += abs(position_size * signal.price)

        if high_correlation_count > 0:
            correlation_exposure_pct = (
                total_correlated_exposure / portfolio.total_capital
            )
            risk_score = min(
                80.0, high_correlation_count * 15.0 + correlation_exposure_pct * 100.0
            )

            if high_correlation_count >= 3:
                risk_metrics.risk_factors.append("HIGH_CORRELATION_CLUSTER")
            elif high_correlation_count >= 2:
                risk_metrics.risk_warnings.append(
                    f"Correlated with {high_correlation_count} positions"
                )

        risk_metrics.correlation_risk = risk_score

    def _calculate_liquidity_risk(
        self, signal: TradingSignal, liquidity_score: float, risk_metrics: RiskMetrics
    ) -> None:
        """Calculate liquidity risk component."""
        # Liquidity score should be 0-100, higher = better liquidity
        if liquidity_score >= 80:
            risk_score = 5.0  # Very liquid
        elif liquidity_score >= 60:
            risk_score = 15.0  # Good liquidity
        elif liquidity_score >= 40:
            risk_score = 35.0  # Moderate liquidity
        elif liquidity_score >= 20:
            risk_score = 65.0  # Poor liquidity
        else:
            risk_score = 90.0  # Very poor liquidity

        # Adjust based on position size (larger positions need more liquidity)
        position_value = signal.price * signal.size
        size_multiplier = min(2.0, position_value / 1000.0)  # Scale with position size
        risk_score *= size_multiplier

        risk_metrics.liquidity_risk = min(100.0, risk_score)

        if liquidity_score < 30:
            risk_metrics.risk_factors.append("LOW_LIQUIDITY")
        elif liquidity_score < 50:
            risk_metrics.risk_warnings.append("Limited liquidity")

    def _calculate_volatility_risk(
        self, signal: TradingSignal, volatility: float, risk_metrics: RiskMetrics
    ) -> None:
        """Calculate volatility risk component."""
        # Volatility as percentage (e.g., 0.20 = 20%)
        if volatility <= 0.05:  # <= 5%
            risk_score = 10.0
        elif volatility <= 0.15:  # <= 15%
            risk_score = 25.0
        elif volatility <= 0.30:  # <= 30%
            risk_score = 50.0
        elif volatility <= 0.50:  # <= 50%
            risk_score = 75.0
        else:  # > 50%
            risk_score = 95.0

        # Adjust based on position size
        position_value = signal.price * signal.size
        portfolio = self._portfolio_state
        if portfolio is not None and (
            position_value > portfolio.total_capital * 0.05
        ):  # > 5% of portfolio
            risk_score *= 1.2

        risk_metrics.volatility_risk = min(100.0, risk_score)

        if volatility > 0.40:
            risk_metrics.risk_factors.append("EXTREME_VOLATILITY")
        elif volatility > 0.25:
            risk_metrics.risk_warnings.append("High volatility market")

    def _calculate_overall_risk_score(self, risk_metrics: RiskMetrics) -> None:
        """Calculate weighted overall risk score."""
        config = self.config

        overall_score = (
            risk_metrics.position_size_risk * config.position_size_weight
            + risk_metrics.concentration_risk * config.concentration_weight
            + risk_metrics.market_exposure_risk * config.market_exposure_weight
            + risk_metrics.correlation_risk * config.correlation_weight
            + risk_metrics.liquidity_risk * config.liquidity_weight
            + risk_metrics.volatility_risk * config.volatility_weight
        )

        risk_metrics.overall_risk_score = min(100.0, overall_score)

    def _determine_risk_level(self, risk_metrics: RiskMetrics) -> None:
        """Determine overall risk level classification."""
        score = risk_metrics.overall_risk_score

        if score < self.config.low_risk_threshold:
            risk_metrics.overall_risk_level = (
                RiskLevel.VERY_LOW if score < 15 else RiskLevel.LOW
            )
        elif score < self.config.moderate_risk_threshold:
            risk_metrics.overall_risk_level = RiskLevel.MODERATE
        elif score < self.config.high_risk_threshold:
            risk_metrics.overall_risk_level = RiskLevel.HIGH
        else:
            risk_metrics.overall_risk_level = RiskLevel.EXTREME

    def _calculate_portfolio_impact(
        self, signal: TradingSignal, risk_metrics: RiskMetrics
    ) -> None:
        """Calculate impact on portfolio risk."""
        position_value = signal.price * signal.size
        portfolio = self._portfolio_state

        portfolio = self._portfolio_state
        if portfolio is None:
            raise ValueError("Portfolio state not available for VaR risk validation")

        # Simple VaR impact estimation (placeholder)
        current_var = portfolio.current_var
        position_var_contribution = position_value * 0.02  # 2% daily VaR assumption

        risk_metrics.var_impact = position_var_contribution
        risk_metrics.portfolio_risk_impact = (
            position_var_contribution / current_var if current_var > 0 else 0
        )

        # Maximum loss estimate (simplified)
        # This would typically use more sophisticated models
        risk_metrics.max_loss_estimate = position_value * 0.20  # Assume max 20% loss

    def _apply_dynamic_adjustments(
        self, signal: TradingSignal, risk_metrics: RiskMetrics
    ) -> None:
        """Apply dynamic risk adjustments based on current conditions."""
        market_multiplier = self._risk_adjustments.get(signal.market_slug, 1.0)

        if market_multiplier != 1.0:
            risk_metrics.overall_risk_score *= market_multiplier
            risk_metrics.overall_risk_score = min(
                100.0, risk_metrics.overall_risk_score
            )

            # Re-determine risk level after adjustment
            self._determine_risk_level(risk_metrics)

            if market_multiplier > 1.2:
                risk_metrics.risk_warnings.append(
                    f"Market risk adjustment applied: {market_multiplier:.1f}x"
                )

    def _generate_risk_factors(self, risk_metrics: RiskMetrics) -> None:
        """Generate additional risk factors based on analysis."""
        # Check for multiple high-risk components
        high_risk_components = []

        if risk_metrics.position_size_risk > 60:
            high_risk_components.append("position_size")
        if risk_metrics.concentration_risk > 60:
            high_risk_components.append("concentration")
        if risk_metrics.market_exposure_risk > 60:
            high_risk_components.append("market_exposure")
        if risk_metrics.correlation_risk > 60:
            high_risk_components.append("correlation")
        if risk_metrics.liquidity_risk > 60:
            high_risk_components.append("liquidity")
        if risk_metrics.volatility_risk > 60:
            high_risk_components.append("volatility")

        if len(high_risk_components) >= 3:
            risk_metrics.risk_factors.append("MULTIPLE_HIGH_RISK_FACTORS")
        elif len(high_risk_components) >= 2:
            risk_metrics.risk_warnings.append("Multiple elevated risk factors")

        # Portfolio-level checks
        portfolio = self._portfolio_state
        if portfolio is None:
            raise ValueError(
                "Portfolio state not available for advanced risk validation"
            )

        if portfolio.daily_pnl < -portfolio.max_daily_loss * 0.8:
            risk_metrics.risk_factors.append("APPROACHING_DAILY_LOSS_LIMIT")

    def _store_risk_history(self, risk_metrics: RiskMetrics) -> None:
        """Store risk metrics in history."""
        signal_id = risk_metrics.signal_id
        self._risk_history[signal_id].append(risk_metrics)

        # Keep only last 100 entries per signal
        if len(self._risk_history[signal_id]) > 100:
            self._risk_history[signal_id] = self._risk_history[signal_id][-100:]

    def _update_validation_stats(self, risk_metrics: RiskMetrics) -> None:
        """Update validation statistics."""
        stats = self._validation_stats

        stats["signals_assessed"] += 1

        if risk_metrics.overall_risk_level in [RiskLevel.HIGH, RiskLevel.EXTREME]:
            stats["high_risk_signals"] += 1

        if risk_metrics.overall_risk_level == RiskLevel.EXTREME:
            stats["rejected_signals"] += 1

        if risk_metrics.risk_warnings:
            stats["risk_warnings"] += len(risk_metrics.risk_warnings)

        # Update average risk score
        current_avg = stats["avg_risk_score"]
        count = stats["signals_assessed"]
        stats["avg_risk_score"] = (
            (current_avg * (count - 1)) + risk_metrics.overall_risk_score
        ) / count

    def set_market_risk_adjustment(
        self, market_slug: str, risk_multiplier: float
    ) -> None:
        """Set dynamic risk adjustment for a specific market."""
        self._risk_adjustments[market_slug] = risk_multiplier
        logger.info(f"Set risk adjustment for {market_slug}: {risk_multiplier}x")

    def clear_market_risk_adjustment(self, market_slug: str) -> None:
        """Clear risk adjustment for a market."""
        if market_slug in self._risk_adjustments:
            del self._risk_adjustments[market_slug]
            logger.info(f"Cleared risk adjustment for {market_slug}")

    def is_signal_acceptable(
        self,
        risk_metrics: RiskMetrics,
        max_acceptable_level: RiskLevel = RiskLevel.HIGH,
    ) -> bool:
        """Check if signal is acceptable based on risk level."""
        risk_levels = [
            RiskLevel.VERY_LOW,
            RiskLevel.LOW,
            RiskLevel.MODERATE,
            RiskLevel.HIGH,
            RiskLevel.EXTREME,
        ]

        signal_level_index = risk_levels.index(risk_metrics.overall_risk_level)
        max_level_index = risk_levels.index(max_acceptable_level)

        return signal_level_index <= max_level_index

    def get_validation_stats(self) -> dict[str, Any]:
        """Get validation statistics."""
        return self._validation_stats.copy()

    def get_risk_history(self, signal_id: str) -> list[RiskMetrics]:
        """Get risk history for a signal."""
        return self._risk_history.get(signal_id, []).copy()


# Utility functions


def create_portfolio_state(total_capital: float, **kwargs: Any) -> PortfolioState:
    """
    Convenience function to create PortfolioState.

    Args:
        total_capital: Total portfolio capital
        **kwargs: Additional portfolio state parameters

    Returns:
        PortfolioState object
    """
    return PortfolioState(
        total_capital=total_capital,
        available_capital=kwargs.get("available_capital", total_capital * 0.8),
        total_positions_value=kwargs.get("total_positions_value", 0.0),
        cash_balance=kwargs.get("cash_balance", total_capital * 0.2),
        **{
            k: v
            for k, v in kwargs.items()
            if k not in ["available_capital", "total_positions_value", "cash_balance"]
        },
    )


def assess_signal_risk(
    signal: TradingSignal,
    portfolio_state: PortfolioState,
    config: RiskConfig | None = None,
) -> RiskMetrics:
    """
    Convenience function to assess signal risk.

    Args:
        signal: Trading signal to assess
        portfolio_state: Current portfolio state
        config: Optional risk configuration

    Returns:
        RiskMetrics with risk assessment
    """
    validator = SignalRiskValidator(config)
    validator.set_portfolio_state(portfolio_state)
    return validator.validate_signal_risk(signal)
