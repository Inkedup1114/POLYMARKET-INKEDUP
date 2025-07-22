from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger("strategies")


@dataclass(slots=True)
class SpreadSignal:
    market_slug: str
    token_id: str
    bid: float | None
    ask: float | None
    spread_bps: float | None


@dataclass(slots=True)
class ComplementSignal:
    market_slug: str
    yes_token: str
    no_token: str
    yes_price: float | None
    no_price: float | None
    deviation: float | None


class BaseStrategy:
    name: str = "base"


class WideSpreadAlertStrategy(BaseStrategy):
    name = "spread_alert"

    def __init__(self, threshold_bps: float):
        self.threshold = threshold_bps

    def on_spread(self, signal: SpreadSignal):
        if signal.spread_bps is not None and signal.spread_bps >= self.threshold:
            log.info(
                f"[SPREAD ALERT] {signal.market_slug} {signal.spread_bps:.1f} bps >= {self.threshold}"
            )
            return {
                "type": "spread",
                "slug": signal.market_slug,
                "bps": signal.spread_bps,
            }


class ComplementArbStrategy(BaseStrategy):
    name = "complement_arb"

    def __init__(self, max_dev: float = 0.01):
        self.max_dev = max_dev

    def on_complement(self, signal: ComplementSignal):
        if signal.deviation is None:
            return None
        if signal.deviation > self.max_dev:
            log.info(
                f"[COMP DEV] {signal.market_slug} deviation={signal.deviation:.4f} > {self.max_dev}"
            )
            return {
                "type": "complement_dev",
                "slug": signal.market_slug,
                "dev": signal.deviation,
            }
