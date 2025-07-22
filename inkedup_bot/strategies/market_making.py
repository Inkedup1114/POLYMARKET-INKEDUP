from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from ..signals import SignalAction, TradingSignal
from ..utils import best_bid_ask, calc_spread_bps

log = logging.getLogger("market_making")


@dataclass(slots=True)
class MarketMakingConfig:
    """Configuration for market making strategy."""

    target_spread_bps: float = 50.0  # Target spread in basis points
    max_position_size: float = 100.0  # Maximum position size in USD
    quote_size: float = 10.0  # Size of quotes in USD
    min_spread_bps: float = 20.0  # Minimum spread to maintain
    max_spread_bps: float = 5000.0  # Maximum spread before withdrawing
    inventory_skew_factor: float = 0.1  # How much to skew quotes based on inventory
    edge_bps: float = 5.0  # Edge to add to fair value
    min_liquidity: float = 1000.0  # Minimum market liquidity to trade
    enabled_markets: list[str] | None = None  # List of market slugs to make markets in


class MarketMakingStrategy:
    """
    Market making strategy that provides liquidity by placing buy and sell orders.

    The strategy:
    1. Calculates fair value based on current market state
    2. Places bid/ask orders around fair value with target spread
    3. Manages inventory by skewing quotes when holding positions
    4. Withdraws quotes when spreads are too tight or wide
    5. Implements proper risk management through position limits
    """

    def __init__(self, config: MarketMakingConfig):
        self.config = config
        self.positions: dict[str, float] = {}  # token_id -> position in USD
        self.active_orders: dict[str, list[str]] = {}  # token_id -> list of order_ids

    def evaluate(self, market_data: dict[str, Any]) -> list[TradingSignal]:
        """
        Generate market making signals based on current market state.

        Args:
            market_data: Dictionary containing market snapshots and order book data

        Returns:
            List of TradingSignal objects for bid/ask placement
        """
        signals: list[TradingSignal] = []
        market_snapshots = market_data.get("market_snapshots", [])

        for market in market_snapshots:
            market_slug = market.get("market_slug")

            # Skip if market not in enabled list (if specified)
            if (
                self.config.enabled_markets
                and market_slug not in self.config.enabled_markets
            ):
                continue

            # Check minimum liquidity requirement
            liquidity = market.get("liquidity", 0)
            if liquidity < self.config.min_liquidity:
                log.debug(
                    f"Skipping {market_slug}: insufficient liquidity ({liquidity})"
                )
                continue

            market_signals = self._process_market(market)
            signals.extend(market_signals)

        return signals

    def _process_market(self, market: dict[str, Any]) -> list[TradingSignal]:
        """Process a single market for market making opportunities."""
        signals: list[TradingSignal] = []
        market_slug = market["market_slug"]

        # Get market outcomes (typically Yes/No)
        outcomes = market.get("outcomes", [])
        if len(outcomes) != 2:
            log.debug(f"Skipping {market_slug}: not a binary market")
            return signals

        yes_outcome = outcomes[0]
        no_outcome = outcomes[1]

        # Get current best bid/ask for each outcome
        yes_book = market.get("yes_book", {})
        no_book = market.get("no_book", {})

        yes_bid, yes_ask = best_bid_ask(yes_book)
        no_bid, no_ask = best_bid_ask(no_book)

        # Calculate current spreads
        yes_spread = calc_spread_bps(yes_bid, yes_ask) if yes_bid and yes_ask else None
        no_spread = calc_spread_bps(no_bid, no_ask) if no_bid and no_ask else None

        # Process Yes outcome
        if self._should_make_market(yes_spread, market_slug, "yes"):
            yes_signals = self._generate_quotes(
                market_slug=market_slug,
                token_id=yes_outcome["id"],
                outcome_type="yes",
                current_bid=yes_bid,
                current_ask=yes_ask,
                spread_bps=yes_spread,
            )
            signals.extend(yes_signals)

        # Process No outcome
        if self._should_make_market(no_spread, market_slug, "no"):
            no_signals = self._generate_quotes(
                market_slug=market_slug,
                token_id=no_outcome["id"],
                outcome_type="no",
                current_bid=no_bid,
                current_ask=no_ask,
                spread_bps=no_spread,
            )
            signals.extend(no_signals)

        return signals

    def _should_make_market(
        self, spread_bps: float | None, market_slug: str, outcome: str
    ) -> bool:
        """Determine if we should make market based on current conditions."""
        if spread_bps is None:
            return False

        # Don't make market if spread is too tight (not profitable)
        if spread_bps < self.config.min_spread_bps:
            log.debug(
                f"Spread too tight for {market_slug} {outcome}: {spread_bps:.1f} bps"
            )
            return False

        # Wide spreads are opportunities for market makers
        # Only skip if spread is extremely wide (might indicate stale/broken market)
        if spread_bps > self.config.max_spread_bps:
            log.debug(
                f"Spread too wide for {market_slug} {outcome}: {spread_bps:.1f} bps"
            )
            return False

        return True

    def _generate_quotes(
        self,
        market_slug: str,
        token_id: str,
        outcome_type: str,
        current_bid: float | None,
        current_ask: float | None,
        spread_bps: float | None,
    ) -> list[TradingSignal]:
        """Generate bid and ask quotes for a single outcome."""
        signals: list[TradingSignal] = []

        # Calculate fair value (mid-point)
        if current_bid is None or current_ask is None:
            return signals

        fair_value = (current_bid + current_ask) / 2

        # Apply inventory skew
        position = self.positions.get(token_id, 0.0)
        inventory_skew = self._calculate_inventory_skew(position)

        # Calculate target bid/ask with edge and inventory skew
        half_spread = (self.config.target_spread_bps / 10000) / 2
        edge = self.config.edge_bps / 10000

        target_bid = fair_value - half_spread - edge + inventory_skew
        target_ask = fair_value + half_spread + edge + inventory_skew

        # Ensure quotes are within valid price range [0.01, 0.99]
        target_bid = max(0.01, min(0.99, target_bid))
        target_ask = max(0.01, min(0.99, target_ask))

        # Check position limits before generating signals
        position_value = abs(position)
        if position_value < self.config.max_position_size:
            # Generate bid signal (we want to buy)
            if self._should_place_bid(target_bid, current_bid, position):
                signals.append(
                    TradingSignal(
                        market_slug=market_slug,
                        token_id=token_id,
                        side=SignalAction.BUY.value,
                        price=target_bid,
                        size=self._calculate_quote_size(target_bid),
                        signal_id=str(uuid.uuid4()),
                        outcome_type=outcome_type,
                    )
                )

            # Generate ask signal (we want to sell)
            if self._should_place_ask(target_ask, current_ask, position):
                signals.append(
                    TradingSignal(
                        market_slug=market_slug,
                        token_id=token_id,
                        side=SignalAction.SELL.value,
                        price=target_ask,
                        size=self._calculate_quote_size(target_ask),
                        signal_id=str(uuid.uuid4()),
                        outcome_type=outcome_type,
                    )
                )
        else:
            log.warning(f"Position limit reached for {token_id}: {position_value:.2f}")

        return signals

    def _calculate_inventory_skew(self, position: float) -> float:
        """Calculate price skew based on current inventory position."""
        # Positive position (long) -> skew quotes down to encourage selling
        # Negative position (short) -> skew quotes up to encourage buying
        normalized_position = position / self.config.max_position_size
        return -normalized_position * self.config.inventory_skew_factor

    def _should_place_bid(
        self, target_bid: float, current_bid: float | None, position: float
    ) -> bool:
        """Determine if we should place a bid order."""
        # Don't bid if we're already long and at risk limits
        if position > self.config.max_position_size * 0.8:
            return False

        # Place bid if our target is better than current best bid
        if current_bid is None or target_bid > current_bid:
            return True

        return False

    def _should_place_ask(
        self, target_ask: float, current_ask: float | None, position: float
    ) -> bool:
        """Determine if we should place an ask order."""
        # Don't offer if we're already short and at risk limits
        if position < -self.config.max_position_size * 0.8:
            return False

        # Place ask if our target is better than current best ask
        if current_ask is None or target_ask < current_ask:
            return True

        return False

    def _calculate_quote_size(self, price: float) -> float:
        """Calculate the size of quote in shares based on configured USD amount."""
        if price <= 0:
            return 0.0
        return self.config.quote_size / price

    def update_position(self, token_id: str, trade_value: float) -> None:
        """Update position tracking after a trade."""
        if token_id not in self.positions:
            self.positions[token_id] = 0.0
        self.positions[token_id] += trade_value
        log.info(f"Updated position for {token_id}: {self.positions[token_id]:.2f}")

    def get_position(self, token_id: str) -> float:
        """Get current position for a token."""
        return self.positions.get(token_id, 0.0) or 0.0

    def reset_positions(self) -> None:
        """Reset all position tracking (use with caution)."""
        self.positions.clear()
        log.warning("All positions reset")
