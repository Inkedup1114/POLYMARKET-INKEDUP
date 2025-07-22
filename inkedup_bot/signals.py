from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class SignalAction(str, Enum):
    """Enumeration for trading actions."""

    BUY = "buy"
    SELL = "sell"


class OutcomeType(str, Enum):
    """Enumeration for market outcomes."""

    YES = "yes"
    NO = "no"


@dataclass(slots=True)
class TradingSignal:
    """
    Unified signal for buy/sell actions emitted by strategies.
    Enhanced with market and outcome tracking for risk management.
    """

    market_slug: str
    token_id: str
    side: Literal["buy", "sell"]
    price: float
    size: float
    signal_id: str | None = None  # Optional unique ID for tracking
    outcome_type: str | None = None  # e.g., 'yes', 'no' for risk tracking


@dataclass(slots=True)
class SpreadSignal:
    """Signal emitted when a spread condition is detected."""

    market_slug: str
    token_id: str
    bid: float | None
    ask: float | None
    spread_bps: float | None


@dataclass(slots=True)
class ComplementSignal:
    """Signal emitted when complement deviation is detected."""

    market_slug: str
    yes_token_id: str
    no_token_id: str
    yes_price: float | None
    no_price: float | None
    complement_deviation: float
