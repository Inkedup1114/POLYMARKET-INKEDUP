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
        signals = []
        market_snapshots = data.get("market_snapshots", [])

        for market in market_snapshots:
            best_yes_price = market["yes_price"]
            best_no_price = market["no_price"]

            spread = (best_yes_price + best_no_price) - 1

            if spread > self.min_spread:
                market_slug = market["market_slug"]
                logger.info(
                    f"Arbitrage opportunity found in {market_slug} (spread: {spread:.4f})"
                )

                outcomes = market.get("outcomes", [])
                if len(outcomes) < 2:
                    logger.warning(
                        f"Market {market_slug} has fewer than 2 outcomes; skipping arbitrage signal."
                    )
                    continue
        market_snapshots = data.get("market_snapshots", [])

        for market in market_snapshots:
            best_yes_price = market["yes_price"]
            best_no_price = market["no_price"]

            spread = (best_yes_price + best_no_price) - 1

            # Removed redundant commented-out spread calculation

            if spread > self.min_spread:
                market_slug = market["market_slug"]
                logger.info(
                    f"Arbitrage opportunity found in {market_slug} (spread: {spread:.4f})"
                )

                outcomes = market.get("outcomes", [])
                if not isinstance(outcomes, list) or len(outcomes) < 2:
                    logger.warning(
                        f"Market {market_slug} has fewer than 2 outcomes; skipping arbitrage signal."
                    )
                    continue
                yes_token = outcomes[0].get("id")
                no_token = outcomes[1].get("id")
                if yes_token is None or no_token is None:
                    logger.warning(
                        f"Market {market_slug} outcome tokens missing; skipping arbitrage signal."
                    )
                    continue
                signals.append(
                    TradingSignal(
                        market_slug=market_slug,
                        token_id=yes_token,
                        side=SignalAction.SELL.value,
                        price=best_yes_price,
                        size=self.trade_size,
                        outcome_type=OutcomeType.YES,
                    )
                )
                signals.append(
                    TradingSignal(
                        market_slug=market_slug,
                        token_id=no_token,
                        side=SignalAction.SELL.value,
                        price=best_no_price,
                        size=self.trade_size,
                        outcome_type=OutcomeType.NO,
                    )
                )

        return signals
