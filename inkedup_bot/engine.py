from __future__ import annotations

import asyncio
import logging

from .config import BotConfig
from .order_client import OrderClient
from .risk import RiskManager
from .signals import TradingSignal
from .state import StateManager

log = logging.getLogger("engine")


class TradingEngine:
    """
    Orchestrates trading signals, risk checks, and order execution.
    """

    def __init__(self, cfg: BotConfig):
        self.cfg = cfg
        self.state = StateManager()
        self.order_client = OrderClient(self.cfg, self.state)
        self.risk = RiskManager(self.cfg, self.order_client, self.state)
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the trading engine and database."""
        if self._initialized:
            return

        # Initialize the state manager database
        await self.state.initialize_async()
        self._initialized = True
        log.info("TradingEngine initialized with database persistence")

    def _ensure_initialized(self) -> None:
        """
        Ensure the trading engine is initialized.
        This is a synchronous wrapper for the async `initialize` method. It should
        ideally only be called at startup when no event loop is running. For async
        applications, it's strongly recommended to call `await engine.initialize()`
        instead.
        """
        if not self._initialized:
            log.info("Engine not initialized. Performing one-time synchronous setup.")
            try:
                # asyncio.run() is a simplified way to run an async function from a
                # sync context. It creates a new event loop and closes it after
                # completion. It will raise a RuntimeError if called when an event
                # loop is already running in the same thread, which prevents
                # unsafe, nested loops.
                asyncio.run(self.initialize())
            except RuntimeError as e:
                log.error(
                    "Failed to initialize engine synchronously, likely because an "
                    f"event loop is already running: {e}. Please use "
                    "'await engine.initialize()' in your async startup code."
                )
                raise  # Re-raise the exception to prevent the engine from running in an uninitialized state.

    def process_signal(self, signal: TradingSignal) -> None:
        # Ensure database is initialized
        self._ensure_initialized()

        if not self.order_client.ready():
            log.warning("Order client not ready, cannot process signal.")
            return

        # Basic validation
        if signal.price <= 0 or signal.size <= 0:
            log.error(f"Invalid signal price or size: {signal}")
            return

        # Risk pre-flight check
        notional_value = signal.price * signal.size
        try:
            self.risk.preflight(
                signal.token_id, notional_value, signal.market_slug, signal.outcome_type
            )
        except (RuntimeError, ValueError) as e:
            log.error(f"Risk check failed for signal {signal.signal_id}: {e}")
            return

        # Execute trade
        log.info(f"Signal {signal.signal_id} passed risk checks, executing trade.")
        self.order_client.place_limit(
            signal.token_id,
            signal.side,
            signal.price,
            signal.size,
            "GTC",
            signal.market_slug,
            signal.outcome_type,
            notional_value,
            self.risk,
        )
