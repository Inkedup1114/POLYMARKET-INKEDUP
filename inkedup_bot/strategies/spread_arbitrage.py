from __future__ import annotations

from typing import Any

from loguru import logger

from ..signals import OutcomeType, SignalAction, TradingSignal


class SpreadArb:
    """
    Identifies arbitrage opportunities based on market spread.
    If the spread between the best 'Yes' and 'No' prices exceeds a configured threshold,
    it generates 'SELL' signals for both outcomes.
    """

    def __init__(self, strategy_config: dict[str, Any]) -> None:
        self.min_spread = strategy_config.get("min_spread", 0.01)
        self.trade_size = strategy_config.get("trade_size", 1.0)

    def evaluate(self, data: dict[str, Any]) -> list[TradingSignal]:
        """
        Evaluate market data for spread arbitrage opportunities.

        Args:
            data: Dictionary containing market_snapshots

        Returns:
            List of TradingSignal objects for arbitrage opportunities
        """
        signals = []
        market_snapshots = data.get("market_snapshots", [])

        for market in market_snapshots:
            arbitrage_signals = self._evaluate_market_for_arbitrage(market)
            signals.extend(arbitrage_signals)

        return signals

    def _evaluate_market_for_arbitrage(
        self, market: dict[str, Any]
    ) -> list[TradingSignal]:
        """
        Evaluate a single market for spread arbitrage opportunities.

        Args:
            market: Market data containing prices and outcome information

        Returns:
            List of TradingSignal objects for this market (empty if no opportunity)
        """
        # Extract market data
        market_slug = market.get("market_slug")
        if not market_slug:
            logger.warning("Market missing market_slug; skipping")
            return []

        # Extract and validate prices
        best_yes_price = market.get("yes_price")
        best_no_price = market.get("no_price")

        if best_yes_price is None or best_no_price is None:
            logger.warning(f"Market {market_slug} missing price data; skipping")
            return []

        # Calculate spread
        spread = (best_yes_price + best_no_price) - 1

        # Check if spread meets arbitrage threshold
        if spread <= self.min_spread:
            logger.debug(
                f"Market {market_slug} spread {spread:.4f} below threshold {self.min_spread:.4f}"
            )
            return []

        # Log arbitrage opportunity
        logger.info(
            f"Arbitrage opportunity found in {market_slug} (spread: {spread:.4f})"
        )

        # Validate and extract outcome tokens
        outcomes = market.get("outcomes", [])
        validation_result = self._validate_market_outcomes(market_slug, outcomes)
        if not validation_result:
            return []

        yes_token, no_token = validation_result

        # Generate arbitrage signals
        return self._generate_arbitrage_signals(
            market_slug=market_slug,
            yes_token=yes_token,
            no_token=no_token,
            best_yes_price=best_yes_price,
            best_no_price=best_no_price,
        )

    def _validate_market_outcomes(
        self, market_slug: str, outcomes: Any
    ) -> tuple[str, str] | None:
        """
        Validate market outcomes and extract token IDs.

        Args:
            market_slug: Market identifier for logging
            outcomes: Market outcomes data

        Returns:
            Tuple of (yes_token_id, no_token_id) if valid, None otherwise
        """
        if not isinstance(outcomes, list):
            logger.warning(
                f"Market {market_slug} outcomes is not a list; skipping arbitrage signal"
            )
            return None

        if len(outcomes) < 2:
            logger.warning(
                f"Market {market_slug} has fewer than 2 outcomes; skipping arbitrage signal"
            )
            return None

        yes_token = outcomes[0].get("id")
        no_token = outcomes[1].get("id")

        if yes_token is None or no_token is None:
            logger.warning(
                f"Market {market_slug} outcome tokens missing; skipping arbitrage signal"
            )
            return None

        return yes_token, no_token

    def _generate_arbitrage_signals(
        self,
        market_slug: str,
        yes_token: str,
        no_token: str,
        best_yes_price: float,
        best_no_price: float,
    ) -> list[TradingSignal]:
        """
        Generate trading signals for a spread arbitrage opportunity.

        Args:
            market_slug: Market identifier
            yes_token: Yes outcome token ID
            no_token: No outcome token ID
            best_yes_price: Best Yes price
            best_no_price: Best No price

        Returns:
            List containing Yes and No sell signals
        """
        signals = []

        # Generate Yes outcome sell signal
        signals.append(
            TradingSignal(
                market_slug=market_slug,
                token_id=yes_token,
                side=SignalAction.SELL.value,
                price=best_yes_price,
                size=self.trade_size,
                outcome_type=OutcomeType.YES,
                signal_id=f"spread_arb_yes_{market_slug}_{int(best_yes_price * 10000)}",
            )
        )

        # Generate No outcome sell signal
        signals.append(
            TradingSignal(
                market_slug=market_slug,
                token_id=no_token,
                side=SignalAction.SELL.value,
                price=best_no_price,
                size=self.trade_size,
                outcome_type=OutcomeType.NO,
                signal_id=f"spread_arb_no_{market_slug}_{int(best_no_price * 10000)}",
            )
        )

        logger.debug(
            f"Generated {len(signals)} arbitrage signals for {market_slug}: "
            f"YES@{best_yes_price:.3f}, NO@{best_no_price:.3f}"
        )

        return signals

    def get_strategy_config(self) -> dict[str, Any]:
        """
        Get current strategy configuration.

        Returns:
            Dictionary with strategy parameters
        """
        return {
            "strategy_name": "SpreadArb",
            "min_spread": self.min_spread,
            "trade_size": self.trade_size,
        }

    def update_config(self, new_config: dict[str, Any]) -> None:
        """
        Update strategy configuration.

        Args:
            new_config: Dictionary with new configuration parameters
        """
        if "min_spread" in new_config:
            self.min_spread = new_config["min_spread"]
            logger.info(f"Updated min_spread to {self.min_spread}")

        if "trade_size" in new_config:
            self.trade_size = new_config["trade_size"]
            logger.info(f"Updated trade_size to {self.trade_size}")
