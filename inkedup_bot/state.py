from __future__ import annotations

import asyncio
import logging
from typing import Any

from .database import DatabaseManager

log = logging.getLogger("state")


class StateManager:
    """
    Persistent state tracking using SQLite database with fallback to in-memory.

    This class now uses DatabaseManager for persistent storage while maintaining
    backward compatibility through synchronous wrappers around async operations.
    """

    def __init__(self, db_path: str = "bot_data.db") -> None:
        # Initialize database manager
        self.db = DatabaseManager(db_path)
        self._db_initialized = False

        # Fallback in-memory storage (for backwards compatibility)
        self.open_orders: dict[str, Any] = {}
        self.positions: dict[str, Any] = {}
        self.market_exposures: dict[str, float] = {}
        self.outcome_exposures: dict[str, float] = {}

    def _run_async(self, coro: Any) -> Any:
        """
        Helper to run async operations synchronously, ensuring compatibility
        with both sync and async contexts. Resolves RuntimeWarning in tests.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # No running loop
            return asyncio.run(coro)

        # If a loop is running, schedule the coroutine and wait for the result.
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()

    def _ensure_db_initialized(self) -> None:
        """Ensure database is initialized (sync wrapper)."""
        if not self._db_initialized:
            result = self._run_async(self.db.initialize())
            if result is not None:  # Successfully initialized
                self._db_initialized = True

    async def initialize_async(self) -> None:
        """Async database initialization."""
        await self.db.initialize()
        self._db_initialized = True
        log.info("StateManager database initialized")

    def add_order(self, order: dict[str, Any]) -> None:
        """
        Adds a newly placed order to the state.
        """
        order_id = order.get("id")
        if not order_id:
            return

        log.info(f"Tracking new order {order_id}")

        # Try database first
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                self._run_async(self.db.insert_order(order))
                return
            except Exception as e:
                log.error(f"Failed to insert order to database: {e}")

        # Fallback to in-memory
        self.open_orders[order_id] = order

    async def add_order_async(self, order: dict[str, Any]) -> None:
        """Async version of add_order."""
        order_id = order.get("id")
        if not order_id:
            return

        log.info(f"Tracking new order {order_id}")
        await self.db.insert_order(order)

    def update_order(self, order_id: str, update_data: dict[str, Any]) -> None:
        """
        Updates the status or details of an open order.
        """
        log.info(f"Updating order {order_id}")

        # Try database first
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                self._run_async(self.db.update_order(order_id, update_data))
                return
            except Exception as e:
                log.error(f"Failed to update order in database: {e}")

        # Fallback to in-memory
        if order_id in self.open_orders:
            self.open_orders[order_id].update(update_data)
            # If filled or cancelled, remove from open orders
            if self.open_orders[order_id].get("status") in ("FILLED", "CANCELLED"):
                del self.open_orders[order_id]

    async def update_order_async(
        self, order_id: str, update_data: dict[str, Any]
    ) -> None:
        """Async version of update_order."""
        log.info(f"Updating order {order_id}")
        await self.db.update_order(order_id, update_data)

    def update_position(self, position_data: dict[str, Any]) -> None:
        """
        Updates the size and notional value of a position.
        """
        token_id = position_data.get("token_id")
        if not token_id:
            return

        log.info(f"Updating position for token {token_id}")

        # Try database first
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                self._run_async(self.db.upsert_position(position_data))
                return
            except Exception as e:
                log.error(f"Failed to update position in database: {e}")

        # Fallback to in-memory
        self.positions[token_id] = position_data

    async def update_position_async(self, position_data: dict[str, Any]) -> None:
        """Async version of update_position."""
        token_id = position_data.get("token_id")
        if not token_id:
            return

        log.info(f"Updating position for token {token_id}")
        await self.db.upsert_position(position_data)

    def get_position_notional(self, token_id: str) -> float:
        """
        Calculates the notional value of a single position.
        """
        # Try database first
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                result = self._run_async(self.db.get_position_notional(token_id))
                return float(result) if result is not None else 0.0
            except Exception as e:
                log.error(f"Failed to get position from database: {e}")

        # Fallback to in-memory
        pos = self.positions.get(token_id)
        return pos.get("notional_value", 0) if pos else 0.0

    async def get_position_notional_async(self, token_id: str) -> float:
        """Async version of get_position_notional."""
        return await self.db.get_position_notional(token_id)

    def get_total_exposure(self) -> float:
        """
        Calculates the total notional value of all current positions.
        """
        # Try database first
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                result = self._run_async(self.db.get_total_exposure())
                return float(result) if result is not None else 0.0
            except Exception as e:
                log.error(f"Failed to get total exposure from database: {e}")

        # Fallback to in-memory
        return sum(self.get_position_notional(token_id) for token_id in self.positions)

    async def get_total_exposure_async(self) -> float:
        """Async version of get_total_exposure."""
        return await self.db.get_total_exposure()

    def update_market_exposure(self, market_slug: str, exposure_change: float) -> None:
        """
        Updates the total exposure for a specific market.
        Note: In database mode, this is calculated from positions, not tracked separately.
        """
        if self._db_initialized:
            # In database mode, market exposure is calculated from positions
            # No need to maintain separate tracking
            log.debug(f"Market {market_slug} exposure change: {exposure_change}")
            return

        # Fallback to in-memory tracking
        current = self.market_exposures.get(market_slug, 0.0)
        self.market_exposures[market_slug] = current + exposure_change
        log.debug(
            f"Market {market_slug} exposure updated: {current} -> {self.market_exposures[market_slug]}"
        )

    def update_outcome_exposure(
        self, outcome_type: str, exposure_change: float
    ) -> None:
        """
        Updates the total exposure for a specific outcome type (e.g., 'yes', 'no').
        Note: In database mode, this is calculated from positions, not tracked separately.
        """
        if self._db_initialized:
            # In database mode, outcome exposure is calculated from positions
            # No need to maintain separate tracking
            log.debug(f"Outcome {outcome_type} exposure change: {exposure_change}")
            return

        # Fallback to in-memory tracking
        current = self.outcome_exposures.get(outcome_type, 0.0)
        self.outcome_exposures[outcome_type] = current + exposure_change
        log.debug(
            f"Outcome {outcome_type} exposure updated: {current} -> {self.outcome_exposures[outcome_type]}"
        )

    def get_market_exposure(self, market_slug: str) -> float:
        """
        Returns the total exposure for a specific market.
        """
        # Try database first
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                result = self._run_async(self.db.get_market_exposure(market_slug))
                return float(result) if result is not None else 0.0
            except Exception as e:
                log.error(f"Failed to get market exposure from database: {e}")

        # Fallback to in-memory
        return self.market_exposures.get(market_slug, 0.0)

    async def get_market_exposure_async(self, market_slug: str) -> float:
        """Async version of get_market_exposure."""
        return await self.db.get_market_exposure(market_slug)

    def get_outcome_exposure(self, outcome_type: str) -> float:
        """
        Returns the total exposure for a specific outcome type.
        """
        # Try database first
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                result = self._run_async(self.db.get_outcome_exposure(outcome_type))
                return float(result) if result is not None else 0.0
            except Exception as e:
                log.error(f"Failed to get outcome exposure from database: {e}")

        # Fallback to in-memory
        return self.outcome_exposures.get(outcome_type, 0.0)

    async def get_outcome_exposure_async(self, outcome_type: str) -> float:
        """Async version of get_outcome_exposure."""
        return await self.db.get_outcome_exposure(outcome_type)
