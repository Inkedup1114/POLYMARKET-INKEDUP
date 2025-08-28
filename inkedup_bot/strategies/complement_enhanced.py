"""
Enhanced Complement arbitrage strategy for the InkedUp Polymarket bot.

This module implements a comprehensive complement arbitrage strategy with dynamic
thresholds based on market volatility and liquidity, proper risk management, 
position sizing, and performance tracking. Addresses the key limitation of fixed
1% thresholds that may miss opportunities in volatile markets.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..position_sizing import KellyCriterionPositionSizer
from ..signals import ComplementSignal, OutcomeType, SignalAction, TradingSignal
from .base import Strategy

log = logging.getLogger(__name__)


@dataclass
class MarketConditions:
    """Market condition analysis for dynamic threshold adjustment."""

    volatility_score: float  # 0.0-1.0 scale
    liquidity_score: float  # 0.0-1.0 scale
    price_stability: float  # 0.0-1.0 scale
    market_momentum: float  # -1.0 to 1.0 scale
    confidence_level: float  # 0.0-1.0 composite score
    recommendation: str  # conservative, normal, aggressive


@dataclass
class DynamicThresholds:
    """Dynamic threshold configuration based on market conditions."""

    min_deviation: float
    max_deviation: float
    position_multiplier: float
    confidence_score: float
    volatility_adjustment: float


@dataclass
class StrategyMetrics:
    """Performance metrics for the complement arbitrage strategy."""

    signals_generated: int = 0
    signals_executed: int = 0
    total_profit_loss: float = 0.0
    total_volume: float = 0.0
    win_rate: float = 0.0
    avg_deviation: float = 0.0
    max_deviation: float = 0.0
    last_updated: float = field(default_factory=time.time)

    def update_signal_generated(self, deviation: float):
        """Update metrics when a signal is generated."""
        self.signals_generated += 1
        self.avg_deviation = (
            self.avg_deviation * (self.signals_generated - 1) + abs(deviation)
        ) / self.signals_generated
        self.max_deviation = max(self.max_deviation, abs(deviation))
        self.last_updated = time.time()

    def update_signal_executed(self, volume: float, profit_loss: float = 0.0):
        """Update metrics when a signal is executed."""
        self.signals_executed += 1
        self.total_volume += volume
        self.total_profit_loss += profit_loss
        self.last_updated = time.time()

        # Update win rate (simplified - assumes positive P&L is a win)
        if self.signals_executed > 0:
            wins = 1 if profit_loss > 0 else 0
            self.win_rate = (
                self.win_rate * (self.signals_executed - 1) + wins
            ) / self.signals_executed


class EnhancedComplementArbStrategy(Strategy):
    """
    Enhanced complement arbitrage strategy with comprehensive risk management.

    Features:
    - Proper base class inheritance and integration
    - Risk-based position sizing
    - Liquidity validation
    - Position tracking and limits
    - Performance metrics
    - Comprehensive error handling
    - Integration with risk management systems
    """

    def __init__(
        self,
        base_min_threshold: float = 0.005,  # More aggressive base: 0.5%
        base_max_threshold: float = 0.25,  # Extended max: 25%
        base_trade_size: float = 15.0,  # Increased base size
        max_trade_size: float = 150.0,  # Higher max size
        size_scaling_factor: float = 75.0,  # Higher scaling for larger deviations
        min_liquidity_usd: float = 100.0,
        max_position_per_market: float = 500.0,
        max_total_exposure: float = 1000.0,
        risk_adjustment_enabled: bool = True,
        position_decay_hours: float = 24.0,
        enable_performance_tracking: bool = True,
        max_concurrent_positions: int = 10,
        # Dynamic threshold parameters
        volatility_sensitivity: float = 0.6,  # How much volatility affects thresholds
        liquidity_factor: float = 1.5,  # Liquidity impact on position sizing
        market_history_window: int = 50,  # Price history for volatility analysis
        dynamic_thresholds_enabled: bool = True,  # Enable/disable dynamic thresholds
        min_confidence_threshold: float = 0.6,  # Minimum confidence for trading
    ) -> None:
        """
        Initialize enhanced complement arbitrage strategy with dynamic thresholds.

        Args:
            base_min_threshold: Base minimum deviation threshold (adjusted dynamically)
            base_max_threshold: Base maximum deviation threshold (adjusted for liquidity)
            base_trade_size: Base position size in USD
            max_trade_size: Maximum position size in USD
            size_scaling_factor: Factor to scale position size with deviation magnitude
            min_liquidity_usd: Minimum liquidity required in USD
            max_position_per_market: Maximum position size per market in USD
            max_total_exposure: Maximum total strategy exposure in USD
            risk_adjustment_enabled: Whether to enable risk-based sizing
            position_decay_hours: Hours after which to decay position tracking
            enable_performance_tracking: Whether to track performance metrics
            max_concurrent_positions: Maximum concurrent positions
            volatility_sensitivity: How much market volatility affects threshold adjustment
            liquidity_factor: Impact of liquidity on position sizing
            market_history_window: Number of price points to track for analysis
            dynamic_thresholds_enabled: Whether to use dynamic threshold calculation
            min_confidence_threshold: Minimum confidence level required for trading
        """
        # Core threshold parameters (now dynamic)
        self.base_min_threshold = base_min_threshold
        self.base_max_threshold = base_max_threshold
        self.base_trade_size = base_trade_size
        self.max_trade_size = max_trade_size
        self.size_scaling_factor = size_scaling_factor
        self.min_liquidity_usd = min_liquidity_usd
        self.max_position_per_market = max_position_per_market
        self.max_total_exposure = max_total_exposure
        self.risk_adjustment_enabled = risk_adjustment_enabled
        self.position_decay_hours = position_decay_hours
        self.enable_performance_tracking = enable_performance_tracking
        self.max_concurrent_positions = max_concurrent_positions

        # Dynamic threshold parameters
        self.volatility_sensitivity = volatility_sensitivity
        self.liquidity_factor = liquidity_factor
        self.market_history_window = market_history_window
        self.dynamic_thresholds_enabled = dynamic_thresholds_enabled
        self.min_confidence_threshold = min_confidence_threshold

        # Strategy state
        self.active_positions: dict[str, dict[str, Any]] = {}
        self.metrics = StrategyMetrics() if enable_performance_tracking else None
        self.risk_manager: Any | None = None
        self.state_manager: Any | None = None

        # Kelly Criterion position sizing
        self.kelly_sizer = KellyCriterionPositionSizer()
        self.available_capital = 10000.0  # Default $10k capital allocation

        # Market analysis tracking for dynamic thresholds
        self.price_history: Dict[str, deque] = {}
        self.volume_history: Dict[str, deque] = {}
        self.deviation_history: Dict[str, deque] = {}
        self.threshold_adjustments = 0

        log.info(
            f"EnhancedComplementArbStrategy initialized: "
            f"base_threshold={base_min_threshold:.3f}-{base_max_threshold:.3f}, "
            f"base_size={base_trade_size}, max_size={max_trade_size}, "
            f"min_liquidity={min_liquidity_usd}, dynamic_thresholds={dynamic_thresholds_enabled}, "
            f"volatility_sensitivity={volatility_sensitivity:.2f}, risk_enabled={risk_adjustment_enabled}"
        )

    def set_risk_manager(self, risk_manager: Any) -> None:
        """Set risk manager for position and exposure validation."""
        self.risk_manager = risk_manager
        log.debug("Risk manager attached to ComplementArbStrategy")

    def set_state_manager(self, state_manager: Any) -> None:
        """Set state manager for position tracking."""
        self.state_manager = state_manager
        log.debug("State manager attached to ComplementArbStrategy")

    def evaluate(self, rows: list[dict[str, Any]]) -> list[TradingSignal]:
        """
        Evaluate market data and generate complement arbitrage signals.

        This method implements the Strategy base class interface.

        Args:
            rows: List of market data rows from scanner

        Returns:
            List of trading signals
        """
        signals = []

        try:
            # Clean up old positions
            self._cleanup_expired_positions()

            # Process each market row for complement opportunities
            for row in rows:
                complement_signal = self._extract_complement_signal(row)
                if complement_signal:
                    new_signals = self.on_complement(complement_signal)
                    signals.extend(new_signals)

        except Exception as e:
            log.error(f"Error in ComplementArbStrategy.evaluate: {e}")

        return signals

    def on_complement(self, signal: ComplementSignal) -> list[TradingSignal]:
        """
        Process complement signal and generate trading signals for arbitrage opportunities.

        Args:
            signal: ComplementSignal containing market data and deviation information

        Returns:
            List of TradingSignal objects for arbitrage trades, or empty list if no opportunity
        """
        try:
            return self._analyze_arbitrage_opportunity(signal)
        except Exception as e:
            log.error(
                f"Error processing complement signal for {signal.market_slug}: {e}"
            )
            return []

    def _extract_complement_signal(
        self, row: dict[str, Any]
    ) -> ComplementSignal | None:
        """
        Extract complement signal from market data row.

        Args:
            row: Market data row

        Returns:
            ComplementSignal if valid complement data exists, None otherwise
        """
        try:
            # Extract required fields
            market_slug = row.get("market_slug")
            yes_token_id = row.get("yes_token_id")
            no_token_id = row.get("no_token_id")
            yes_price = row.get("yes_price")
            no_price = row.get("no_price")

            if not all([market_slug, yes_token_id, no_token_id]):
                return None

            if yes_price is None or no_price is None:
                return None

            # Calculate complement deviation
            complement_sum = yes_price + no_price
            complement_deviation = complement_sum - 1.0

            return ComplementSignal(
                market_slug=market_slug,
                yes_token_id=yes_token_id,
                no_token_id=no_token_id,
                yes_price=yes_price,
                no_price=no_price,
                complement_deviation=complement_deviation,
            )

        except Exception as e:
            log.warning(f"Error extracting complement signal from row: {e}")
            return None

    def _analyze_arbitrage_opportunity(
        self, signal: ComplementSignal
    ) -> list[TradingSignal]:
        """
        Analyze the complement signal for arbitrage opportunities with dynamic thresholds.

        Args:
            signal: ComplementSignal to analyze

        Returns:
            List of TradingSignal objects for arbitrage trades
        """
        # Validate input data
        if not self._validate_signal_data(signal):
            return []

        deviation = signal.complement_deviation
        market_slug = signal.market_slug

        # Update market history for dynamic analysis
        self._update_market_history(signal)

        # Calculate dynamic thresholds if enabled
        if self.dynamic_thresholds_enabled:
            market_conditions = self._analyze_market_conditions(signal)
            dynamic_thresholds = self._calculate_dynamic_thresholds(market_conditions)

            min_threshold = dynamic_thresholds.min_deviation
            max_threshold = dynamic_thresholds.max_deviation

            # Check confidence level
            if market_conditions.confidence_level < self.min_confidence_threshold:
                log.debug(
                    f"Market confidence {market_conditions.confidence_level:.3f} below threshold "
                    f"{self.min_confidence_threshold:.3f} for {market_slug}"
                )
                return []
        else:
            # Use static thresholds
            min_threshold = self.base_min_threshold
            max_threshold = self.base_max_threshold

        # Check if deviation meets dynamic/static threshold
        if abs(deviation) < min_threshold:
            log.debug(
                f"Deviation {deviation:.4f} below {'dynamic' if self.dynamic_thresholds_enabled else 'static'} "
                f"threshold {min_threshold:.4f} for market {market_slug}"
            )
            return []

        # Check if deviation exceeds maximum threshold (safety limit)
        if abs(deviation) > max_threshold:
            log.warning(
                f"Deviation {deviation:.4f} exceeds maximum threshold {max_threshold:.4f} "
                f"for market {market_slug} - skipping for safety"
            )
            return []

        # Check liquidity requirements
        if not self._check_liquidity_requirements(signal):
            return []

        # Check position limits
        if not self._check_position_limits(signal):
            return []

        # Check risk management constraints
        if not self._check_risk_constraints(signal):
            return []

        # Calculate position size with dynamic and risk adjustments
        if self.dynamic_thresholds_enabled:
            position_size = self._calculate_position_size_with_risk(
                signal, dynamic_thresholds
            )
        else:
            position_size = self._calculate_position_size_with_risk(signal)

        if position_size <= 0:
            log.debug(f"Position size {position_size} too small for {market_slug}")
            return []

        # Generate trading signals based on deviation direction
        signals = []

        if deviation > 0:  # Yes + No > 1.0 - Sell both outcomes
            signals.extend(self._generate_sell_both_signals(signal, position_size))
        else:  # Yes + No < 1.0 - Buy both outcomes
            signals.extend(self._generate_buy_both_signals(signal, position_size))

        # Track position and update metrics
        if signals:
            self._track_position(signal, position_size, len(signals))

            if self.metrics:
                self.metrics.update_signal_generated(deviation)

            # Enhanced logging with dynamic threshold info
            threshold_info = ""
            if self.dynamic_thresholds_enabled:
                threshold_info = (
                    f", dynamic_min={min_threshold:.4f}, volatility={market_conditions.volatility_score:.3f}, "
                    f"liquidity={market_conditions.liquidity_score:.3f}, confidence={market_conditions.confidence_level:.3f}"
                )
            else:
                threshold_info = f", static_min={min_threshold:.4f}"

            log.info(
                f"Generated {len(signals)} arbitrage signals for {market_slug}: "
                f"deviation={deviation:.4f}, size={position_size:.2f}, "
                f"yes_price={signal.yes_price:.3f}, no_price={signal.no_price:.3f}"
                f"{threshold_info}"
            )

        return signals

    def _validate_signal_data(self, signal: ComplementSignal) -> bool:
        """
        Validate that the signal contains valid data for arbitrage analysis.

        Args:
            signal: ComplementSignal to validate

        Returns:
            True if signal is valid, False otherwise
        """
        if not signal.market_slug:
            log.warning("Invalid signal: missing market_slug")
            return False

        if not signal.yes_token_id or not signal.no_token_id:
            log.warning(f"Invalid signal for {signal.market_slug}: missing token IDs")
            return False

        if signal.yes_price is None or signal.no_price is None:
            log.warning(f"Invalid signal for {signal.market_slug}: missing prices")
            return False

        if signal.yes_price <= 0 or signal.yes_price >= 1:
            log.warning(
                f"Invalid yes_price {signal.yes_price} for {signal.market_slug}"
            )
            return False

        if signal.no_price <= 0 or signal.no_price >= 1:
            log.warning(f"Invalid no_price {signal.no_price} for {signal.market_slug}")
            return False

        return True

    def _check_liquidity_requirements(self, signal: ComplementSignal) -> bool:
        """
        Check if the market has sufficient liquidity for trading.

        Args:
            signal: ComplementSignal to check

        Returns:
            True if liquidity requirements are met, False otherwise
        """
        if self.min_liquidity_usd <= 0:
            return True  # No liquidity check required

        try:
            # Estimate liquidity based on prices and typical market depth
            # This is a simplified check - in production, you'd want actual order book depth
            yes_implied_liquidity = signal.yes_price * 1000  # Simplified estimate
            no_implied_liquidity = signal.no_price * 1000  # Simplified estimate

            min_liquidity = min(yes_implied_liquidity, no_implied_liquidity)

            if min_liquidity < self.min_liquidity_usd:
                log.debug(
                    f"Insufficient liquidity for {signal.market_slug}: "
                    f"{min_liquidity:.2f} < {self.min_liquidity_usd:.2f}"
                )
                return False

            return True

        except Exception as e:
            log.warning(f"Error checking liquidity for {signal.market_slug}: {e}")
            return False

    def _check_position_limits(self, signal: ComplementSignal) -> bool:
        """
        Check position limits before creating new positions.

        Args:
            signal: ComplementSignal to check

        Returns:
            True if position limits allow trading, False otherwise
        """
        market_slug = signal.market_slug

        # Check maximum concurrent positions
        if len(self.active_positions) >= self.max_concurrent_positions:
            log.debug(f"Max concurrent positions reached: {len(self.active_positions)}")
            return False

        # Check per-market position limit
        current_market_exposure = 0.0
        for pos_data in self.active_positions.values():
            if pos_data.get("market_slug") == market_slug:
                current_market_exposure += pos_data.get("total_size", 0.0)

        if current_market_exposure >= self.max_position_per_market:
            log.debug(
                f"Market position limit reached for {market_slug}: "
                f"{current_market_exposure:.2f} >= {self.max_position_per_market:.2f}"
            )
            return False

        # Check total strategy exposure
        total_exposure = sum(
            pos.get("total_size", 0.0) for pos in self.active_positions.values()
        )

        if total_exposure >= self.max_total_exposure:
            log.debug(
                f"Total strategy exposure limit reached: "
                f"{total_exposure:.2f} >= {self.max_total_exposure:.2f}"
            )
            return False

        return True

    def _check_risk_constraints(self, signal: ComplementSignal) -> bool:
        """
        Check risk management constraints.

        Args:
            signal: ComplementSignal to check

        Returns:
            True if risk constraints allow trading, False otherwise
        """
        if not self.risk_manager:
            return True  # No risk manager, allow trade

        try:
            # Check if risk manager allows this market
            market_slug = signal.market_slug

            # Get current exposures from risk manager
            if hasattr(self.risk_manager, "get_market_exposure"):
                market_exposure = self.risk_manager.get_market_exposure(market_slug)
                market_limit = getattr(
                    self.risk_manager, "per_market_risk_cap", float("inf")
                )

                if market_exposure >= market_limit:
                    log.debug(
                        f"Risk manager blocks {market_slug}: exposure {market_exposure} >= limit {market_limit}"
                    )
                    return False

            # Check total exposure
            if hasattr(self.risk_manager, "get_total_exposure"):
                total_exposure = self.risk_manager.get_total_exposure()
                total_limit = getattr(
                    self.risk_manager, "global_risk_cap", float("inf")
                )

                if total_exposure >= total_limit:
                    log.debug(
                        f"Risk manager blocks trade: total exposure {total_exposure} >= limit {total_limit}"
                    )
                    return False

            return True

        except Exception as e:
            log.error(f"Error checking risk constraints: {e}")
            return False  # Be conservative on errors

    def _calculate_position_size_with_risk(
        self,
        signal: ComplementSignal,
        dynamic_thresholds: Optional[DynamicThresholds] = None,
    ) -> float:
        """
        Calculate position size with Kelly Criterion and risk adjustments.

        Args:
            signal: ComplementSignal with market data
            dynamic_thresholds: Optional dynamic threshold parameters

        Returns:
            Kelly-adjusted position size in USD
        """
        deviation = abs(signal.complement_deviation)

        # Base size scaled by deviation magnitude (fallback calculation)
        base_size = self.base_trade_size + (deviation * self.size_scaling_factor)

        # Apply dynamic threshold multiplier if available
        if dynamic_thresholds:
            base_size *= dynamic_thresholds.position_multiplier

        # Use Kelly Criterion for optimal position sizing
        try:
            # Determine trade type for Kelly tracking
            trade_type = "sell_both" if signal.complement_deviation > 0 else "buy_both"

            # Calculate confidence score from signal strength and dynamic conditions
            confidence_score = self._calculate_confidence_score(
                signal, dynamic_thresholds
            )

            # Get Kelly-optimized position size
            kelly_size, reason, metrics = self.kelly_sizer.calculate_position_size(
                strategy_name="complement_arbitrage",
                market_slug=signal.market_slug,
                trade_type=trade_type,
                base_size_usd=base_size,
                available_capital=self.available_capital,
                confidence_score=confidence_score,
                deviation_magnitude=deviation,
            )

            log.debug(
                f"Kelly sizing for {signal.market_slug}: {kelly_size:.2f} USD ({reason})"
            )

            # Apply additional risk adjustments if enabled
            if self.risk_adjustment_enabled:
                kelly_size = self._apply_risk_adjustments(kelly_size, signal)

            # Apply maximum size limit
            size = min(kelly_size, self.max_trade_size)

        except Exception as e:
            log.warning(
                f"Kelly sizing failed for {signal.market_slug}: {e}, using fallback"
            )
            # Fallback to original calculation
            if self.risk_adjustment_enabled:
                base_size = self._apply_risk_adjustments(base_size, signal)
            size = min(base_size, self.max_trade_size)

        # Ensure minimum viable size
        size = max(size, 1.0)

        return round(size, 2)

    def _calculate_confidence_score(
        self,
        signal: ComplementSignal,
        dynamic_thresholds: Optional[DynamicThresholds] = None,
    ) -> float:
        """
        Calculate confidence score for Kelly Criterion based on signal strength and market conditions.

        Args:
            signal: ComplementSignal with market data
            dynamic_thresholds: Optional dynamic threshold parameters

        Returns:
            Confidence score between 0.0 and 1.0
        """
        try:
            deviation_magnitude = abs(signal.complement_deviation)

            # Base confidence from deviation strength
            # Larger deviations indicate stronger arbitrage opportunities
            base_confidence = min(
                1.0, deviation_magnitude / 0.05
            )  # 5% deviation = 100% confidence

            # Market condition adjustments if available
            if dynamic_thresholds:
                # Higher market confidence boosts our confidence
                condition_boost = dynamic_thresholds.confidence_score * 0.3
                base_confidence = min(1.0, base_confidence + condition_boost)

            # Price validity check - prices too close to 0 or 1 are less reliable
            yes_validity = (
                min(signal.yes_price, 1 - signal.yes_price) * 2
            )  # 0.5 = max validity
            no_validity = min(signal.no_price, 1 - signal.no_price) * 2
            price_validity = (yes_validity + no_validity) / 2

            # Combine factors
            confidence = base_confidence * (0.7 + price_validity * 0.3)

            return max(0.1, min(1.0, confidence))  # Bound between 0.1 and 1.0

        except Exception as e:
            log.warning(f"Error calculating confidence score: {e}")
            return 0.5  # Default moderate confidence

    def _apply_risk_adjustments(
        self, base_size: float, signal: ComplementSignal
    ) -> float:
        """
        Apply risk-based adjustments to position size.

        Args:
            base_size: Base position size before adjustments
            signal: ComplementSignal with market data

        Returns:
            Risk-adjusted position size
        """
        adjusted_size = base_size

        try:
            # Adjust for current strategy exposure
            total_exposure = sum(
                pos.get("total_size", 0.0) for pos in self.active_positions.values()
            )
            exposure_ratio = (
                total_exposure / self.max_total_exposure
                if self.max_total_exposure > 0
                else 0.0
            )

            if exposure_ratio > 0.5:  # If more than 50% exposed, reduce size
                size_reduction = min(0.5, exposure_ratio - 0.5)  # Max 50% reduction
                adjusted_size *= 1.0 - size_reduction
                log.debug(
                    f"Risk adjustment: reduced size by {size_reduction:.1%} due to exposure"
                )

            # Adjust for deviation magnitude (higher deviation = higher confidence = larger size)
            deviation = abs(signal.complement_deviation)
            if deviation > self.base_min_threshold * 3:  # Strong signal
                size_multiplier = min(1.5, 1.0 + deviation * 2)  # Max 50% increase
                adjusted_size *= size_multiplier
                log.debug(
                    f"Risk adjustment: increased size by {size_multiplier:.1%} due to strong signal"
                )

            # Adjust based on market-specific factors
            market_positions = sum(
                1
                for pos in self.active_positions.values()
                if pos.get("market_slug") == signal.market_slug
            )

            if market_positions > 0:  # Already have positions in this market
                adjusted_size *= 0.7  # Reduce size by 30%
                log.debug(
                    "Risk adjustment: reduced size due to existing market positions"
                )

        except Exception as e:
            log.error(f"Error applying risk adjustments: {e}")
            # Return base size if adjustments fail
            return base_size

        return max(adjusted_size, 1.0)  # Ensure minimum size

    def _generate_sell_both_signals(
        self, signal: ComplementSignal, position_size: float
    ) -> list[TradingSignal]:
        """
        Generate sell signals for both outcomes when Yes + No > 1.0.

        Args:
            signal: ComplementSignal with market data
            position_size: Position size for each trade

        Returns:
            List containing sell signals for both Yes and No outcomes
        """
        signals = []

        # Sell Yes outcome
        yes_signal = TradingSignal(
            market_slug=signal.market_slug,
            token_id=signal.yes_token_id,
            side=SignalAction.SELL.value,
            price=signal.yes_price,
            size=self._convert_usd_to_shares(position_size, signal.yes_price),
            outcome_type=OutcomeType.YES.value,
            signal_id=f"complement_arb_sell_yes_{signal.market_slug}_{int(signal.complement_deviation * 10000)}_{int(time.time() * 1000)}",
        )
        signals.append(yes_signal)

        # Sell No outcome
        no_signal = TradingSignal(
            market_slug=signal.market_slug,
            token_id=signal.no_token_id,
            side=SignalAction.SELL.value,
            price=signal.no_price,
            size=self._convert_usd_to_shares(position_size, signal.no_price),
            outcome_type=OutcomeType.NO.value,
            signal_id=f"complement_arb_sell_no_{signal.market_slug}_{int(signal.complement_deviation * 10000)}_{int(time.time() * 1000)}",
        )
        signals.append(no_signal)

        return signals

    def _generate_buy_both_signals(
        self, signal: ComplementSignal, position_size: float
    ) -> list[TradingSignal]:
        """
        Generate buy signals for both outcomes when Yes + No < 1.0.

        Args:
            signal: ComplementSignal with market data
            position_size: Position size for each trade

        Returns:
            List containing buy signals for both Yes and No outcomes
        """
        signals = []

        # Buy Yes outcome
        yes_signal = TradingSignal(
            market_slug=signal.market_slug,
            token_id=signal.yes_token_id,
            side=SignalAction.BUY.value,
            price=signal.yes_price,
            size=self._convert_usd_to_shares(position_size, signal.yes_price),
            outcome_type=OutcomeType.YES.value,
            signal_id=f"complement_arb_buy_yes_{signal.market_slug}_{int(abs(signal.complement_deviation) * 10000)}_{int(time.time() * 1000)}",
        )
        signals.append(yes_signal)

        # Buy No outcome
        no_signal = TradingSignal(
            market_slug=signal.market_slug,
            token_id=signal.no_token_id,
            side=SignalAction.BUY.value,
            price=signal.no_price,
            size=self._convert_usd_to_shares(position_size, signal.no_price),
            outcome_type=OutcomeType.NO.value,
            signal_id=f"complement_arb_buy_no_{signal.market_slug}_{int(abs(signal.complement_deviation) * 10000)}_{int(time.time() * 1000)}",
        )
        signals.append(no_signal)

        return signals

    def _convert_usd_to_shares(self, usd_amount: float, price: float) -> float:
        """
        Convert USD amount to number of shares based on price.

        Args:
            usd_amount: Amount in USD to invest
            price: Price per share

        Returns:
            Number of shares to trade
        """
        if price <= 0:
            log.warning(f"Invalid price {price} for USD conversion")
            return 0.0

        shares = usd_amount / price
        return round(shares, 4)  # Round to 4 decimal places for precision

    def _track_position(
        self, signal: ComplementSignal, position_size: float, signal_count: int
    ) -> None:
        """
        Track position for risk management and performance analysis.

        Args:
            signal: ComplementSignal that generated the position
            position_size: Size of each individual position
            signal_count: Number of signals generated (usually 2 for complement arb)
        """
        position_id = f"{signal.market_slug}_{int(time.time())}"

        position_data = {
            "market_slug": signal.market_slug,
            "position_size": position_size,
            "total_size": position_size * signal_count,
            "deviation": signal.complement_deviation,
            "yes_price": signal.yes_price,
            "no_price": signal.no_price,
            "timestamp": time.time(),
            "signal_count": signal_count,
        }

        self.active_positions[position_id] = position_data

        log.debug(f"Tracking position {position_id}: {position_data}")

    def _cleanup_expired_positions(self) -> None:
        """Clean up expired position tracking data."""
        if self.position_decay_hours <= 0:
            return

        current_time = time.time()
        decay_seconds = self.position_decay_hours * 3600

        expired_positions = [
            pos_id
            for pos_id, pos_data in self.active_positions.items()
            if current_time - pos_data.get("timestamp", 0) > decay_seconds
        ]

        for pos_id in expired_positions:
            del self.active_positions[pos_id]

        if expired_positions:
            log.debug(f"Cleaned up {len(expired_positions)} expired positions")

    def _update_market_history(self, signal: ComplementSignal) -> None:
        """Update historical data for dynamic threshold analysis."""
        market_slug = signal.market_slug

        # Initialize history tracking for new markets
        if market_slug not in self.price_history:
            self.price_history[market_slug] = deque(maxlen=self.market_history_window)
            self.volume_history[market_slug] = deque(maxlen=self.market_history_window)
            self.deviation_history[market_slug] = deque(
                maxlen=self.market_history_window
            )

        # Add current data points
        price_point = {
            "timestamp": time.time(),
            "yes_price": signal.yes_price,
            "no_price": signal.no_price,
            "sum": signal.yes_price + signal.no_price,
        }

        self.price_history[market_slug].append(price_point)
        self.deviation_history[market_slug].append(signal.complement_deviation)

        # Add volume if available (placeholder for future enhancement)
        volume_point = getattr(signal, "volume", 0.0)
        self.volume_history[market_slug].append(volume_point)

    def _analyze_market_conditions(self, signal: ComplementSignal) -> MarketConditions:
        """
        Analyze current market conditions for dynamic threshold calculation.

        Args:
            signal: Current market signal

        Returns:
            MarketConditions object with analysis results
        """
        market_slug = signal.market_slug

        # Calculate individual condition scores
        volatility_score = self._calculate_volatility_score(market_slug)
        liquidity_score = self._estimate_liquidity_score(signal)
        price_stability = self._calculate_price_stability(market_slug)
        market_momentum = self._calculate_market_momentum(market_slug)

        # Calculate composite confidence level
        confidence_level = (
            volatility_score * 0.25
            + liquidity_score * 0.35
            + price_stability * 0.25
            + abs(market_momentum) * 0.15  # Strong momentum in either direction is good
        )

        # Generate trading recommendation
        recommendation = self._generate_market_recommendation(
            volatility_score, liquidity_score, price_stability
        )

        return MarketConditions(
            volatility_score=volatility_score,
            liquidity_score=liquidity_score,
            price_stability=price_stability,
            market_momentum=market_momentum,
            confidence_level=confidence_level,
            recommendation=recommendation,
        )

    def _calculate_volatility_score(self, market_slug: str) -> float:
        """Calculate market volatility score from price history."""
        if (
            market_slug not in self.price_history
            or len(self.price_history[market_slug]) < 3
        ):
            return 0.3  # Default low volatility for new markets

        history = list(self.price_history[market_slug])

        # Calculate price change variance
        price_changes = []
        for i in range(1, len(history)):
            prev_sum = history[i - 1]["sum"]
            curr_sum = history[i]["sum"]
            if prev_sum > 0:
                change = abs(curr_sum - prev_sum) / prev_sum
                price_changes.append(change)

        if not price_changes:
            return 0.3

        # Calculate volatility metrics
        avg_change = sum(price_changes) / len(price_changes)
        max_change = max(price_changes)

        # Normalize to 0-1 scale with proper scaling
        volatility_score = min(1.0, (avg_change * 15) + (max_change * 0.1))

        return volatility_score

    def _estimate_liquidity_score(self, signal: ComplementSignal) -> float:
        """
        Estimate liquidity score based on available market data.
        """
        yes_price = signal.yes_price
        no_price = signal.no_price

        # Markets with prices near extremes (0 or 1) typically have lower liquidity
        yes_liquidity = min(yes_price, 1 - yes_price) * 4  # Scale to 0-2
        no_liquidity = min(no_price, 1 - no_price) * 4

        # Average and bound to 0-1
        liquidity_score = (yes_liquidity + no_liquidity) / 4
        return min(1.0, max(0.1, liquidity_score))

    def _calculate_price_stability(self, market_slug: str) -> float:
        """Calculate price stability score based on deviation history."""
        if (
            market_slug not in self.deviation_history
            or len(self.deviation_history[market_slug]) < 3
        ):
            return 0.5  # Default medium stability

        deviations = list(self.deviation_history[market_slug])

        # Calculate variance in deviations
        mean_dev = sum(abs(d) for d in deviations) / len(deviations)
        variance = sum((abs(d) - mean_dev) ** 2 for d in deviations) / len(deviations)

        # Lower variance = higher stability
        stability = max(0.0, 1.0 - variance * 50)  # Scale factor for normalization
        return min(1.0, stability)

    def _calculate_market_momentum(self, market_slug: str) -> float:
        """Calculate market momentum based on recent price trends."""
        if (
            market_slug not in self.price_history
            or len(self.price_history[market_slug]) < 5
        ):
            return 0.0  # No momentum for insufficient data

        history = list(self.price_history[market_slug])
        recent_points = history[-5:]  # Use last 5 data points

        # Calculate trend in price sums
        trend_sum = 0
        for i in range(1, len(recent_points)):
            prev_sum = recent_points[i - 1]["sum"]
            curr_sum = recent_points[i]["sum"]
            if prev_sum > 0:
                trend_sum += (curr_sum - prev_sum) / prev_sum

        # Normalize to -1 to 1 scale
        momentum = max(-1.0, min(1.0, trend_sum * 5))  # Scale factor
        return momentum

    def _generate_market_recommendation(
        self, volatility: float, liquidity: float, stability: float
    ) -> str:
        """Generate trading recommendation based on market conditions."""
        # Higher volatility and liquidity = more aggressive
        # Lower stability = more opportunities but also more risk
        composite_score = (
            volatility * 0.4
            + liquidity * 0.4
            + (1 - stability) * 0.2  # Instability creates opportunities
        )

        if composite_score > 0.7:
            return "aggressive"
        elif composite_score > 0.4:
            return "normal"
        else:
            return "conservative"

    def _calculate_dynamic_thresholds(
        self, conditions: MarketConditions
    ) -> DynamicThresholds:
        """
        Calculate dynamic thresholds based on current market conditions.

        Args:
            conditions: Current market condition analysis

        Returns:
            DynamicThresholds with adjusted parameters
        """
        # Volatility-based threshold adjustment
        # Higher volatility = lower minimum threshold to catch more opportunities
        volatility_adjustment = 1.0 - (
            conditions.volatility_score * self.volatility_sensitivity
        )
        volatility_adjustment = max(
            0.2, min(1.8, volatility_adjustment)
        )  # Bound 0.2-1.8

        # Liquidity-based adjustment for position sizing
        liquidity_adjustment = 0.5 + (
            conditions.liquidity_score * self.liquidity_factor
        )
        liquidity_adjustment = max(0.5, min(2.5, liquidity_adjustment))  # Bound 0.5-2.5

        # Stability-based adjustment
        # Less stable markets need slightly higher thresholds for safety
        stability_adjustment = 0.8 + (conditions.price_stability * 0.4)  # 0.8-1.2 range

        # Calculate dynamic thresholds
        min_deviation = (
            self.base_min_threshold * volatility_adjustment * stability_adjustment
        )
        min_deviation = max(0.001, min(0.025, min_deviation))  # Bound 0.1%-2.5%

        max_deviation = self.base_max_threshold * (
            1.0 + conditions.liquidity_score * 0.2
        )
        max_deviation = max(0.15, min(0.4, max_deviation))  # Bound 15%-40%

        # Position multiplier based on all conditions
        position_multiplier = liquidity_adjustment * (
            1.0 + conditions.volatility_score * 0.3
        )
        position_multiplier = max(0.3, min(3.0, position_multiplier))

        # Track adjustments
        self.threshold_adjustments += 1

        log.debug(
            f"Dynamic thresholds calculated: min={min_deviation:.4f}, max={max_deviation:.4f}, "
            f"pos_mult={position_multiplier:.2f}, volatility={conditions.volatility_score:.3f}, "
            f"liquidity={conditions.liquidity_score:.3f}, stability={conditions.price_stability:.3f}"
        )

        return DynamicThresholds(
            min_deviation=min_deviation,
            max_deviation=max_deviation,
            position_multiplier=position_multiplier,
            confidence_score=conditions.confidence_level,
            volatility_adjustment=volatility_adjustment,
        )

    def get_strategy_metrics(self) -> dict[str, Any]:
        """
        Get comprehensive strategy configuration and performance metrics.

        Returns:
            Dictionary containing strategy configuration and metrics
        """
        metrics_data = {
            "strategy_name": "EnhancedComplementArbStrategy",
            "base_min_threshold": self.base_min_threshold,
            "base_max_threshold": self.base_max_threshold,
            "base_trade_size": self.base_trade_size,
            "max_trade_size": self.max_trade_size,
            "size_scaling_factor": self.size_scaling_factor,
            "min_liquidity_usd": self.min_liquidity_usd,
            "max_position_per_market": self.max_position_per_market,
            "max_total_exposure": self.max_total_exposure,
            "risk_adjustment_enabled": self.risk_adjustment_enabled,
            "max_concurrent_positions": self.max_concurrent_positions,
            "active_positions_count": len(self.active_positions),
            "current_exposure": sum(
                pos.get("total_size", 0.0) for pos in self.active_positions.values()
            ),
            # Dynamic threshold configuration
            "dynamic_thresholds_enabled": self.dynamic_thresholds_enabled,
            "volatility_sensitivity": self.volatility_sensitivity,
            "liquidity_factor": self.liquidity_factor,
            "market_history_window": self.market_history_window,
            "min_confidence_threshold": self.min_confidence_threshold,
            "threshold_adjustments_made": self.threshold_adjustments,
            "markets_tracked": len(self.price_history),
            # Kelly Criterion information
            "available_capital": self.available_capital,
            "kelly_statistics": self.get_kelly_statistics(),
        }

        # Add performance metrics if available
        if self.metrics:
            metrics_data.update(
                {
                    "performance_metrics": {
                        "signals_generated": self.metrics.signals_generated,
                        "signals_executed": self.metrics.signals_executed,
                        "total_profit_loss": self.metrics.total_profit_loss,
                        "total_volume": self.metrics.total_volume,
                        "win_rate": self.metrics.win_rate,
                        "avg_deviation": self.metrics.avg_deviation,
                        "max_deviation": self.metrics.max_deviation,
                        "last_updated": self.metrics.last_updated,
                    }
                }
            )

        return metrics_data

    def reset_metrics(self) -> None:
        """Reset performance metrics."""
        if self.metrics:
            self.metrics = StrategyMetrics()
            log.info("Strategy metrics reset")

    def get_active_positions(self) -> dict[str, dict[str, Any]]:
        """Get current active positions."""
        import copy

        return copy.deepcopy(self.active_positions)

    def clear_positions(self) -> None:
        """Clear all tracked positions (for testing/reset)."""
        self.active_positions.clear()
        log.info("All tracked positions cleared")

    def get_market_analysis(self, market_slug: str) -> Optional[Dict[str, Any]]:
        """Get detailed analysis for a specific market."""
        if market_slug not in self.price_history:
            return None

        return {
            "market_slug": market_slug,
            "price_history_points": len(self.price_history[market_slug]),
            "volume_history_points": len(self.volume_history[market_slug]),
            "deviation_history_points": len(self.deviation_history[market_slug]),
            "recent_volatility": self._calculate_volatility_score(market_slug),
            "price_stability": self._calculate_price_stability(market_slug),
            "market_momentum": self._calculate_market_momentum(market_slug),
        }

    def reset_market_history(self, market_slug: Optional[str] = None) -> None:
        """Reset market history for a specific market or all markets."""
        if market_slug:
            if market_slug in self.price_history:
                del self.price_history[market_slug]
            if market_slug in self.volume_history:
                del self.volume_history[market_slug]
            if market_slug in self.deviation_history:
                del self.deviation_history[market_slug]
            log.info(f"Market history reset for {market_slug}")
        else:
            self.price_history.clear()
            self.volume_history.clear()
            self.deviation_history.clear()
            self.threshold_adjustments = 0
            log.info("All market history reset")

    def record_trade_outcome(
        self,
        market_slug: str,
        trade_type: str,
        profit_loss: float,
        position_size: float,
    ) -> None:
        """
        Record trade outcome for Kelly Criterion learning.

        Args:
            market_slug: Market identifier
            trade_type: Type of trade ("sell_both" or "buy_both")
            profit_loss: Realized profit or loss in USD
            position_size: Size of the position in USD
        """
        try:
            self.kelly_sizer.record_trade_outcome(
                strategy_name="complement_arbitrage",
                market_slug=market_slug,
                trade_type=trade_type,
                position_size_usd=position_size,
                profit_loss_usd=profit_loss,
            )

            # Also update strategy metrics
            if self.metrics:
                self.metrics.update_signal_executed(position_size, profit_loss)

            log.debug(
                f"Recorded trade outcome for {market_slug}: P&L=${profit_loss:.2f}, "
                f"size=${position_size:.2f}, type={trade_type}"
            )

        except Exception as e:
            log.error(f"Failed to record trade outcome: {e}")

    def get_kelly_statistics(self) -> Dict[str, Any]:
        """Get Kelly Criterion statistics for the strategy."""
        try:
            kelly_stats = self.kelly_sizer._get_strategy_statistics(
                "complement_arbitrage"
            )
            return {
                "total_trades": kelly_stats.total_trades,
                "win_rate": kelly_stats.win_rate,
                "avg_profit_loss_ratio": kelly_stats.profit_loss_ratio,
                "kelly_fraction": kelly_stats.kelly_fraction,
                "total_profit_loss": kelly_stats.total_profit + kelly_stats.total_loss,
            }
        except Exception as e:
            log.error(f"Failed to get Kelly statistics: {e}")
            return {}

    def set_available_capital(self, capital: float) -> None:
        """Set available capital for position sizing."""
        if capital > 0:
            self.available_capital = capital
            log.info(f"Available capital set to ${capital:,.2f}")
        else:
            log.warning(f"Invalid capital amount: {capital}")

    def update_capital_from_pnl(self, realized_pnl: float) -> None:
        """Update available capital based on realized P&L."""
        self.available_capital += realized_pnl
        log.debug(
            f"Capital updated by ${realized_pnl:+.2f}, new total: ${self.available_capital:,.2f}"
        )
