"""
Alert-based trading strategies for the InkedUp Polymarket bot.
"""

from ..signals import SpreadSignal, TradingSignal


class WideSpreadAlertStrategy:
    """Strategy that alerts on wide spreads."""

    def __init__(self, spread_alert_bps: float) -> None:
        self.spread_alert_bps = spread_alert_bps

    def on_spread(self, signal: SpreadSignal) -> TradingSignal | None:
        """Process spread signal and potentially return trading signal."""
        if signal.spread_bps and signal.spread_bps > self.spread_alert_bps:
            # For now, just log - could return actual trading signal later
            return TradingSignal(
                market_slug=signal.market_slug,
                token_id=signal.token_id,
                side="buy",
                price=0.5,
                size=1.0,
            )
        return None
