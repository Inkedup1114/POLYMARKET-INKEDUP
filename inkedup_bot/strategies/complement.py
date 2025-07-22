"""
Complement arbitrage strategies for the InkedUp Polymarket bot.
"""

from ..signals import ComplementSignal, TradingSignal


class ComplementArbStrategy:
    """Strategy that detects complement arbitrage opportunities."""

    def __init__(self) -> None:
        pass

    def on_complement(self, signal: ComplementSignal) -> TradingSignal | None:
        """Process complement signal and potentially return trading signal."""
        # For now, just return a mock signal - implement actual logic later
        return TradingSignal(
            market_slug=signal.market_slug,
            token_id=signal.yes_token_id,
            side="buy",
            price=0.5,
            size=1.0,
        )
