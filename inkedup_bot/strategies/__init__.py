"""
Trading strategies package for the InkedUp Polymarket bot.

This package contains various trading strategy implementations
including market making and spread arbitrage strategies.
"""

from .alerts import WideSpreadAlertStrategy
from .base import Strategy
from .complement import ComplementArbStrategy
from .market_making import MarketMakingConfig, MarketMakingStrategy
from .spread_arbitrage import SpreadArb

__all__ = [
    "Strategy",
    "MarketMakingStrategy",
    "MarketMakingConfig",
    "SpreadArb",
    "WideSpreadAlertStrategy",
    "ComplementArbStrategy",
]
