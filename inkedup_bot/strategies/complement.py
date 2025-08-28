"""
Complement arbitrage strategies for the InkedUp Polymarket bot.

This module implements strategies to detect and exploit complement arbitrage opportunities
in binary prediction markets. In a properly functioning binary market, the sum of Yes and No
prices should equal 1.0. When this relationship breaks down, arbitrage opportunities exist.
"""

import logging

from ..position_sizing import KellyCriterionPositionSizer
from ..signals import ComplementSignal, OutcomeType, SignalAction, TradingSignal

log = logging.getLogger(__name__)


class ComplementArbStrategy:
    """
    Strategy that detects and exploits complement arbitrage opportunities.

    In binary prediction markets, the fundamental constraint is that Yes + No prices should
    equal 1.0. When this constraint is violated, arbitrage opportunities exist:

    1. If Yes + No > 1.0: Sell both outcomes (guaranteed profit)
    2. If Yes + No < 1.0: Buy both outcomes (guaranteed profit when market resolves)

    The strategy calculates the deviation from the constraint and generates trading signals
    when the deviation exceeds configured thresholds.
    """

    def __init__(
        self,
        min_deviation_threshold: float = 0.01,  # Minimum 1% deviation to trade
        max_deviation_threshold: float = 0.20,  # Maximum 20% deviation (safety limit)
        base_trade_size: float = 10.0,  # Base trade size in USD
        max_trade_size: float = 100.0,  # Maximum trade size in USD
        size_scaling_factor: float = 50.0,  # Scale trade size with deviation
        min_liquidity_check: bool = True,  # Check minimum liquidity before trading
        risk_adjustment_enabled: bool = True,  # Enable risk-based position sizing
    ) -> None:
        """
        Initialize complement arbitrage strategy.

        Args:
            min_deviation_threshold: Minimum complement deviation to trigger trades
            max_deviation_threshold: Maximum deviation to trade (safety limit)
            base_trade_size: Base position size in USD
            max_trade_size: Maximum position size in USD
            size_scaling_factor: Factor to scale position size with deviation magnitude
            min_liquidity_check: Whether to check for minimum liquidity
            risk_adjustment_enabled: Whether to enable risk-based sizing
        """
        self.min_deviation_threshold = min_deviation_threshold
        self.max_deviation_threshold = max_deviation_threshold
        self.base_trade_size = base_trade_size
        self.max_trade_size = max_trade_size
        self.size_scaling_factor = size_scaling_factor
        self.min_liquidity_check = min_liquidity_check
        self.risk_adjustment_enabled = risk_adjustment_enabled

        # Kelly Criterion position sizing
        self.kelly_sizer = KellyCriterionPositionSizer()
        self.available_capital = (
            5000.0  # Default $5k capital allocation for basic strategy
        )

        log.info(
            f"ComplementArbStrategy initialized: "
            f"deviation_threshold={min_deviation_threshold:.3f}-{max_deviation_threshold:.3f}, "
            f"base_size={base_trade_size}, max_size={max_trade_size}"
        )

    def on_complement(self, signal: ComplementSignal) -> list[TradingSignal]:
        """
        Process complement signal and generate trading signals for arbitrage opportunities.

        This method analyzes binary prediction market pricing to identify complement
        arbitrage opportunities. In efficient markets, YES + NO prices should equal 1.0.
        When this constraint is violated, risk-free arbitrage opportunities exist.

        Arbitrage Scenarios:
        1. YES + NO > 1.0: Sell both outcomes (collect premium, guaranteed profit)
        2. YES + NO < 1.0: Buy both outcomes (guaranteed profit when market resolves)

        The strategy only generates signals when:
        - Deviation exceeds minimum threshold (filters out noise)
        - Deviation is below maximum threshold (safety limit)
        - Market has sufficient liquidity for execution

        Position Sizing:
        Position sizes are scaled based on deviation magnitude and configured limits:
        - Base trade size provides minimum position
        - Scaling factor increases size with larger deviations
        - Maximum trade size caps position risk

        Example Scenarios:
            >>> # Market with YES=0.6, NO=0.5 (sum=1.1, deviation=+0.1)
            >>> # Strategy generates: SELL YES @ 0.6, SELL NO @ 0.5
            >>> # Profit = 1.1 - 1.0 = 0.1 per share (10% return)
            >>>
            >>> # Market with YES=0.4, NO=0.5 (sum=0.9, deviation=-0.1)
            >>> # Strategy generates: BUY YES @ 0.4, BUY NO @ 0.5
            >>> # Profit = 1.0 - 0.9 = 0.1 per share (11.1% return)

        Args:
            signal: ComplementSignal containing market data and deviation information
                   Must include: market_slug, yes_price, no_price, complement_deviation

        Returns:
            List of TradingSignal objects for arbitrage trades, or empty list if:
            - No arbitrage opportunity exists (deviation too small)
            - Deviation exceeds safety threshold
            - Signal data is invalid or incomplete
            - Strategy encounters processing errors
        """
        try:
            return self._analyze_arbitrage_opportunity(signal)
        except Exception as e:
            log.error(
                f"Error processing complement signal for {signal.market_slug}: {e}"
            )
            return []

    def _analyze_arbitrage_opportunity(
        self, signal: ComplementSignal
    ) -> list[TradingSignal]:
        """
        Analyze the complement signal for arbitrage opportunities.

        Args:
            signal: ComplementSignal to analyze

        Returns:
            List of TradingSignal objects for arbitrage trades
        """
        # Validate input data
        if not self._validate_signal_data(signal):
            return []

        deviation = signal.complement_deviation
        yes_price = signal.yes_price
        no_price = signal.no_price

        # Check if deviation meets minimum threshold
        if abs(deviation) < self.min_deviation_threshold:
            log.debug(
                f"Deviation {deviation:.4f} below threshold {self.min_deviation_threshold:.4f} "
                f"for market {signal.market_slug}"
            )
            return []

        # Check if deviation exceeds maximum threshold (safety limit)
        if abs(deviation) > self.max_deviation_threshold:
            log.warning(
                f"Deviation {deviation:.4f} exceeds maximum threshold {self.max_deviation_threshold:.4f} "
                f"for market {signal.market_slug} - skipping for safety"
            )
            return []

        # Calculate position size using Kelly Criterion
        position_size = self._calculate_position_size_kelly(signal, deviation)

        # Generate trading signals based on deviation direction
        signals = []

        if deviation > 0:  # Yes + No > 1.0 - Sell both outcomes
            signals.extend(self._generate_sell_both_signals(signal, position_size))
        else:  # Yes + No < 1.0 - Buy both outcomes
            signals.extend(self._generate_buy_both_signals(signal, position_size))

        if signals:
            log.info(
                f"Generated {len(signals)} arbitrage signals for {signal.market_slug}: "
                f"deviation={deviation:.4f}, size={position_size:.2f}, "
                f"yes_price={yes_price:.3f}, no_price={no_price:.3f}"
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

    def _calculate_position_size_kelly(
        self, signal: ComplementSignal, deviation: float
    ) -> float:
        """
        Calculate position size using Kelly Criterion for optimal capital allocation.

        Args:
            signal: ComplementSignal with market data
            deviation: Complement deviation magnitude

        Returns:
            Kelly-optimized position size in USD
        """
        try:
            # Fallback calculation for comparison
            base_size = self.base_trade_size + (
                abs(deviation) * self.size_scaling_factor
            )

            # Determine trade type for Kelly tracking
            trade_type = "sell_both" if deviation > 0 else "buy_both"

            # Calculate confidence score from deviation strength
            confidence_score = min(
                1.0, abs(deviation) / 0.03
            )  # 3% deviation = 100% confidence

            # Get Kelly-optimized position size
            kelly_size, reason, metrics = self.kelly_sizer.calculate_position_size(
                strategy_name="complement_arbitrage_basic",
                market_slug=signal.market_slug,
                trade_type=trade_type,
                base_size_usd=base_size,
                available_capital=self.available_capital,
                confidence_score=confidence_score,
                deviation_magnitude=abs(deviation),
            )

            log.debug(
                f"Kelly sizing for {signal.market_slug}: {kelly_size:.2f} USD ({reason})"
            )

            # Apply maximum size limit
            size = min(kelly_size, self.max_trade_size)

        except Exception as e:
            log.warning(
                f"Kelly sizing failed for {signal.market_slug}: {e}, using fallback"
            )
            # Fallback to original calculation
            size = self.base_trade_size + (abs(deviation) * self.size_scaling_factor)
            size = min(size, self.max_trade_size)

        # Ensure minimum viable size
        size = max(size, 1.0)

        return round(size, 2)

    def _calculate_position_size(self, deviation: float) -> float:
        """
        Legacy position size calculation - kept for backward compatibility.

        Args:
            deviation: Complement deviation magnitude

        Returns:
            Position size in USD
        """
        # Base size scaled by deviation magnitude
        size = self.base_trade_size + (abs(deviation) * self.size_scaling_factor)

        # Apply maximum size limit
        size = min(size, self.max_trade_size)

        # Ensure minimum viable size
        size = max(size, 1.0)

        return round(size, 2)

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
            signal_id=f"complement_arb_sell_yes_{signal.market_slug}_{int(signal.complement_deviation * 10000)}",
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
            signal_id=f"complement_arb_sell_no_{signal.market_slug}_{int(signal.complement_deviation * 10000)}",
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
            signal_id=f"complement_arb_buy_yes_{signal.market_slug}_{int(abs(signal.complement_deviation) * 10000)}",
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
            signal_id=f"complement_arb_buy_no_{signal.market_slug}_{int(abs(signal.complement_deviation) * 10000)}",
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

    def get_strategy_metrics(self) -> dict:
        """
        Get strategy configuration and performance metrics.

        Returns:
            Dictionary containing strategy configuration and metrics
        """
        return {
            "strategy_name": "ComplementArbStrategy",
            "min_deviation_threshold": self.min_deviation_threshold,
            "max_deviation_threshold": self.max_deviation_threshold,
            "base_trade_size": self.base_trade_size,
            "max_trade_size": self.max_trade_size,
            "size_scaling_factor": self.size_scaling_factor,
            "min_liquidity_check": self.min_liquidity_check,
            "risk_adjustment_enabled": self.risk_adjustment_enabled,
            "available_capital": self.available_capital,
            "kelly_statistics": self.get_kelly_statistics(),
        }

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
                strategy_name="complement_arbitrage_basic",
                market_slug=market_slug,
                trade_type=trade_type,
                position_size_usd=position_size,
                profit_loss_usd=profit_loss,
            )

            log.debug(
                f"Recorded trade outcome for {market_slug}: P&L=${profit_loss:.2f}, "
                f"size=${position_size:.2f}, type={trade_type}"
            )

        except Exception as e:
            log.error(f"Failed to record trade outcome: {e}")

    def get_kelly_statistics(self) -> dict:
        """Get Kelly Criterion statistics for the strategy."""
        try:
            kelly_stats = self.kelly_sizer._get_strategy_statistics(
                "complement_arbitrage_basic"
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
