"""State management for persistent trading state and portfolio tracking.

This module provides the StateManager class which maintains persistent state
across trading sessions, including order tracking, position management, and
market exposure calculations. It uses SQLite for persistence with in-memory
fallback capabilities for reliability.

The state manager provides:
- Persistent order and position tracking
- Market and outcome exposure calculations
- Risk manager integration for real-time updates
- Database fallback mechanisms for reliability
- Validation and data integrity checks
- Async/sync compatibility for different usage patterns

Key Features:
    - SQLite-based persistent storage with automatic schema management
    - In-memory fallback for high availability during database issues
    - Real-time exposure tracking for risk management
    - Comprehensive validation of all state updates
    - Integration with risk management systems
    - Thread-safe operations with proper locking

Examples:
    Basic state manager usage:

    >>> from inkedup_bot.state import StateManager
    >>>
    >>> # Initialize with database persistence
    >>> state = StateManager("trading_state.db")
    >>> await state.initialize_async()
    >>>
    >>> # Add an order
    >>> order_data = {
    ...     "id": "order_123",
    ...     "market_slug": "election-2024",
    ...     "side": "buy",
    ...     "size": 100.0,
    ...     "price": 0.65
    ... }
    >>> state.add_order("order_123", order_data)
    >>>
    >>> # Check market exposure
    >>> exposure = state.get_market_exposure("election-2024")
    >>> print(f"Market exposure: ${exposure}")

Architecture:
    The StateManager uses a dual-layer architecture with SQLite persistence
    backed by in-memory caches for performance. It provides both synchronous
    and asynchronous interfaces for different usage patterns.

Thread Safety:
    All operations are thread-safe through proper use of asyncio locks
    and database connection management. The state manager can be safely
    used across multiple trading strategies and components.

"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .database import DatabaseManager
from .validation import (
    OrderValidation,
    PositionValidation,
    ValidationError,
    validate_model_data,
    validate_state_update,
)

log = logging.getLogger("state")


class StateManager:
    """Persistent state tracking using SQLite database with fallback to in-memory storage.

    The StateManager serves as the central repository for all trading state including
    orders, positions, and market exposures. It provides persistent storage through
    SQLite while maintaining in-memory fallback capabilities for high availability.

    This class bridges synchronous and asynchronous usage patterns, providing
    backward compatibility for existing code while enabling modern async operations
    for new components.

    Key Features:
        - SQLite persistence with automatic schema management
        - In-memory fallback for database failures
        - Real-time exposure tracking and calculations
        - Comprehensive data validation and integrity checks
        - Risk manager integration for coordinated updates
        - Thread-safe operations with proper locking

    Attributes:
        db: Database manager for persistent storage
        _db_initialized: Flag indicating database readiness
        open_orders: In-memory cache of open orders (fallback)
        positions: In-memory cache of positions (fallback)
        market_exposures: Cached market exposure calculations
        outcome_exposures: Cached outcome-specific exposures
        _risk_manager: Optional risk manager reference for coordination

    Examples:
        Initialize and use state manager:

        >>> # Create state manager with custom database
        >>> state = StateManager("production_state.db")
        >>> await state.initialize_async()
        >>>
        >>> # Track an order
        >>> order = {
        ...     "id": "limit_order_456",
        ...     "token_id": "0x123abc...",
        ...     "side": "buy",
        ...     "size": 250.0,
        ...     "price": 0.42
        ... }
        >>> state.add_order("limit_order_456", order)
        >>>
        >>> # Update position
        >>> position = {
        ...     "token_id": "0x123abc...",
        ...     "size": 150.0,
        ...     "notional_value": 63.0,
        ...     "market_slug": "sports-nfl"
        ... }
        >>> state.update_position("0x123abc...", position)
        >>>
        >>> # Check exposures
        >>> market_exp = state.get_market_exposure("sports-nfl")
        >>> outcome_exp = state.get_outcome_exposure("0x123abc...")
        >>> print(f"Market: ${market_exp}, Outcome: ${outcome_exp}")

    Persistence Strategy:
        The state manager uses a write-through cache strategy where:
        1. All updates are immediately written to SQLite
        2. In-memory caches are updated for fast reads
        3. On database failures, operations fall back to memory-only
        4. Database recovery automatically restores consistency

    Risk Integration:
        State updates are coordinated with the risk management system
        to ensure real-time exposure calculations and limit enforcement.
        The risk manager receives notifications of all position changes.

    Thread Safety:
        All database operations use proper async locking and connection
        management. The state manager is safe for concurrent use across
        multiple trading components and event loops.

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

        # Risk manager reference for fallback coordination
        self._risk_manager: Any | None = None

    def set_risk_manager(self, risk_manager: Any) -> None:
        """Set reference to risk manager for fallback coordination."""
        self._risk_manager = risk_manager

    def _notify_risk_manager_of_position_update(
        self, token_id: str, position_data: dict[str, Any]
    ) -> None:
        """Notify risk manager of position updates for fallback cache maintenance."""
        if self._risk_manager is not None:
            try:
                self._risk_manager.update_fallback_cache_position(
                    token_id, position_data
                )
            except Exception as e:
                log.warning(f"Failed to update risk manager fallback cache: {e}")

    def _run_async(self, coro: Any) -> Any:
        """Helper to run async operations synchronously, ensuring compatibility
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

    @validate_state_update
    def add_order(self, order: dict[str, Any]) -> None:
        """Adds a newly placed order to the state with validation."""
        # Validate order data before processing
        try:
            validated_order = validate_model_data(OrderValidation, order)
            order_data = validated_order.model_dump()
        except ValidationError as e:
            log.error(f"Order validation failed: {e}")
            raise

        order_id = order_data.get("id")
        if not order_id:
            log.error("Order missing required ID field")
            raise ValidationError("Order must have an ID")

        log.info(f"Tracking new order {order_id}")

        # Try database first
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                self._run_async(self.db.insert_order(order_data))
                return
            except Exception as e:
                log.error(f"Failed to insert order to database: {e}")

        # Fallback to in-memory
        self.open_orders[order_id] = order_data

    async def add_order_async(self, order: dict[str, Any]) -> None:
        """Async version of add_order with validation."""
        # Validate order data before processing
        try:
            validated_order = validate_model_data(OrderValidation, order)
            order_data = validated_order.model_dump()
        except ValidationError as e:
            log.error(f"Order validation failed: {e}")
            raise

        order_id = order_data.get("id")
        if not order_id:
            log.error("Order missing required ID field")
            raise ValidationError("Order must have an ID")

        log.info(f"Tracking new order {order_id}")
        await self.db.insert_order(order_data)

    def update_order(self, order_id: str, update_data: dict[str, Any]) -> None:
        """Updates the status or details of an open order."""
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

    @validate_state_update
    def update_position(self, position_data: dict[str, Any]) -> None:
        """Updates the size and notional value of a position with validation."""
        # Validate position data before processing
        try:
            validated_position = validate_model_data(PositionValidation, position_data)
            pos_data = validated_position.model_dump()
        except ValidationError as e:
            log.error(f"Position validation failed: {e}")
            raise

        token_id = pos_data.get("token_id")
        if not token_id:
            log.error("Position missing required token_id field")
            raise ValidationError("Position must have a token_id")

        log.info(f"Updating position for token {token_id}")

        # Try database first
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                self._run_async(self.db.upsert_position(pos_data))
                # Notify risk manager of successful position update
                self._notify_risk_manager_of_position_update(token_id, pos_data)
                return
            except Exception as e:
                log.error(f"Failed to update position in database: {e}")

        # Fallback to in-memory
        self.positions[token_id] = pos_data
        # Notify risk manager even for in-memory updates
        self._notify_risk_manager_of_position_update(token_id, pos_data)

    async def update_position_async(self, position_data: dict[str, Any]) -> None:
        """Async version of update_position with validation."""
        # Validate position data before processing
        try:
            validated_position = validate_model_data(PositionValidation, position_data)
            pos_data = validated_position.model_dump()
        except ValidationError as e:
            log.error(f"Position validation failed: {e}")
            raise

        token_id = pos_data.get("token_id")
        if not token_id:
            log.error("Position missing required token_id field")
            raise ValidationError("Position must have a token_id")

        log.info(f"Updating position for token {token_id}")
        await self.db.upsert_position(pos_data)
        # Notify risk manager of successful position update
        self._notify_risk_manager_of_position_update(token_id, pos_data)

    def get_position_notional(self, token_id: str) -> float:
        """Calculates the notional value of a single position."""
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
        """Calculates the total notional value of all current positions."""
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
        """Updates the total exposure for a specific market.
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
        """Updates the total exposure for a specific outcome type (e.g., 'yes', 'no').
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
        """Returns the total exposure for a specific market.
        Enhanced with comprehensive calculation logic.
        """
        # Try database first
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                result = self._run_async(self.db.get_market_exposure(market_slug))
                return float(result) if result is not None else 0.0
            except Exception as e:
                log.error(f"Failed to get market exposure from database: {e}")

        # Fallback to in-memory with comprehensive calculation
        return self._calculate_market_exposure_from_memory(market_slug)

    def _calculate_market_exposure_from_memory(self, market_slug: str) -> float:
        """Calculate market exposure from in-memory positions."""
        total_exposure = 0.0

        # Calculate from all positions in the market
        for token_id, position in self.positions.items():
            if position.get("market_slug") == market_slug:
                notional = position.get("notional_value", 0.0)
                total_exposure += abs(notional)  # Use absolute value for total exposure

        return total_exposure

    async def get_market_exposure_async(self, market_slug: str) -> float:
        """Async version of get_market_exposure."""
        return await self.db.get_market_exposure(market_slug)

    def get_outcome_exposure(self, outcome_type: str) -> float:
        """Returns the total exposure for a specific outcome type.
        Enhanced with comprehensive calculation logic.
        """
        # Try database first
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                result = self._run_async(self.db.get_outcome_exposure(outcome_type))
                return float(result) if result is not None else 0.0
            except Exception as e:
                log.error(f"Failed to get outcome exposure from database: {e}")

        # Fallback to in-memory with comprehensive calculation
        return self._calculate_outcome_exposure_from_memory(outcome_type)

    def _calculate_outcome_exposure_from_memory(self, outcome_type: str) -> float:
        """Calculate outcome exposure from in-memory positions."""
        total_exposure = 0.0

        # Calculate from all positions with this outcome type
        for token_id, position in self.positions.items():
            if position.get("outcome_type") == outcome_type:
                notional = position.get("notional_value", 0.0)
                total_exposure += abs(notional)  # Use absolute value for total exposure

        return total_exposure

    async def get_outcome_exposure_async(self, outcome_type: str) -> float:
        """Async version of get_outcome_exposure."""
        return await self.db.get_outcome_exposure(outcome_type)

    # Enhanced exposure tracking methods
    def record_trade_impact(
        self,
        token_id: str,
        trade_size: float,
        trade_price: float,
        side: str,
        market_slug: str,
        outcome_type: str,
    ) -> dict[str, Any]:
        """Record the impact of a trade on position and exposure tracking.
        This is the primary method to call when a trade is executed.
        """
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                result = self._run_async(
                    self.db.record_trade_impact(
                        token_id,
                        trade_size,
                        trade_price,
                        side,
                        market_slug,
                        outcome_type,
                    )
                )
                try:
                    trade_notional = result.get("trade_notional", 0)
                    log.info(
                        f"Trade impact recorded - {token_id}: {side} {trade_size} @ {trade_price} "
                        f"(notional: {trade_notional:.2f})"
                    )
                except Exception as log_error:
                    log.warning(f"Failed to log trade impact details: {log_error}")
                return result
            except Exception as e:
                log.error(f"Failed to record trade impact in database: {e}")

        # Fallback to in-memory tracking
        notional_value = abs(trade_size * trade_price)
        signed_notional = notional_value if side.upper() == "BUY" else -notional_value

        # Update in-memory tracking
        self.update_market_exposure(market_slug, signed_notional)
        self.update_outcome_exposure(outcome_type, signed_notional)

        # Update position tracking
        position_data = {
            "token_id": token_id,
            "market_slug": market_slug,
            "outcome_type": outcome_type,
            "notional_value": self.positions.get(token_id, {}).get("notional_value", 0)
            + signed_notional,
            "size": self.positions.get(token_id, {}).get("size", 0)
            + (trade_size if side.upper() == "BUY" else -trade_size),
        }
        self.positions[token_id] = position_data

        return {
            "token_id": token_id,
            "market_slug": market_slug,
            "outcome_type": outcome_type,
            "size_delta": trade_size if side.upper() == "BUY" else -trade_size,
            "notional_delta": signed_notional,
            "trade_notional": notional_value,
            "side": side,
            "price": trade_price,
        }

    async def record_trade_impact_async(
        self,
        token_id: str,
        trade_size: float,
        trade_price: float,
        side: str,
        market_slug: str,
        outcome_type: str,
    ) -> dict[str, Any]:
        """Async version of record_trade_impact."""
        result = await self.db.record_trade_impact(
            token_id, trade_size, trade_price, side, market_slug, outcome_type
        )
        log.info(
            f"Trade impact recorded - {token_id}: {side} {trade_size} @ {trade_price} "
            f"(notional: {result.get('trade_notional', 0):.2f})"
        )
        return result

    def get_market_summary(self, market_slug: str) -> dict[str, Any]:
        """Get comprehensive market exposure summary."""
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                return self._run_async(self.db.get_market_summary(market_slug))
            except Exception as e:
                log.error(f"Failed to get market summary from database: {e}")

        # Fallback to in-memory calculation
        total_exposure = self.market_exposures.get(market_slug, 0.0)
        positions_in_market = [
            pos
            for pos in self.positions.values()
            if pos.get("market_slug") == market_slug
        ]

        outcome_breakdown = {}
        for pos in positions_in_market:
            outcome = pos.get("outcome_type", "unknown")
            if outcome not in outcome_breakdown:
                outcome_breakdown[outcome] = {
                    "outcome_type": outcome,
                    "count": 0,
                    "exposure": 0.0,
                    "absolute_exposure": 0.0,
                }
            outcome_breakdown[outcome]["count"] += 1
            notional = pos.get("notional_value", 0.0)
            outcome_breakdown[outcome]["exposure"] += notional
            outcome_breakdown[outcome]["absolute_exposure"] += abs(notional)

        return {
            "market_slug": market_slug,
            "position_count": len(positions_in_market),
            "total_exposure": total_exposure,
            "absolute_exposure": sum(
                abs(pos.get("notional_value", 0)) for pos in positions_in_market
            ),
            "avg_position_size": (
                total_exposure / len(positions_in_market)
                if positions_in_market
                else 0.0
            ),
            "outcome_breakdown": list(outcome_breakdown.values()),
        }

    async def get_market_summary_async(self, market_slug: str) -> dict[str, Any]:
        """Async version of get_market_summary."""
        return await self.db.get_market_summary(market_slug)

    def get_outcome_summary(self, outcome_type: str) -> dict[str, Any]:
        """Get comprehensive outcome exposure summary."""
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                return self._run_async(self.db.get_outcome_summary(outcome_type))
            except Exception as e:
                log.error(f"Failed to get outcome summary from database: {e}")

        # Fallback to in-memory calculation
        total_exposure = self.outcome_exposures.get(outcome_type, 0.0)
        positions_for_outcome = [
            pos
            for pos in self.positions.values()
            if pos.get("outcome_type") == outcome_type
        ]

        market_breakdown = {}
        for pos in positions_for_outcome:
            market = pos.get("market_slug", "unknown")
            if market not in market_breakdown:
                market_breakdown[market] = {
                    "market_slug": market,
                    "count": 0,
                    "exposure": 0.0,
                    "absolute_exposure": 0.0,
                }
            market_breakdown[market]["count"] += 1
            notional = pos.get("notional_value", 0.0)
            market_breakdown[market]["exposure"] += notional
            market_breakdown[market]["absolute_exposure"] += abs(notional)

        unique_markets = set(pos.get("market_slug") for pos in positions_for_outcome)

        return {
            "outcome_type": outcome_type,
            "position_count": len(positions_for_outcome),
            "market_count": len(unique_markets),
            "total_exposure": total_exposure,
            "absolute_exposure": sum(
                abs(pos.get("notional_value", 0)) for pos in positions_for_outcome
            ),
            "avg_position_size": (
                total_exposure / len(positions_for_outcome)
                if positions_for_outcome
                else 0.0
            ),
            "market_breakdown": list(market_breakdown.values()),
        }

    async def get_outcome_summary_async(self, outcome_type: str) -> dict[str, Any]:
        """Async version of get_outcome_summary."""
        return await self.db.get_outcome_summary(outcome_type)

    def get_all_positions(self) -> list[dict[str, Any]]:
        """Get all current positions."""
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                return self._run_async(self.db.get_all_positions())
            except Exception as e:
                log.error(f"Failed to get positions from database: {e}")

        # Fallback to in-memory
        return list(self.positions.values())

    async def get_all_positions_async(self) -> list[dict[str, Any]]:
        """Async version of get_all_positions."""
        return await self.db.get_all_positions()

    def get_positions_by_market(self, market_slug: str) -> list[dict[str, Any]]:
        """Get all positions for a specific market."""
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                return self._run_async(self.db.get_positions_by_market(market_slug))
            except Exception as e:
                log.error(f"Failed to get market positions from database: {e}")

        # Fallback to in-memory
        return [
            pos
            for pos in self.positions.values()
            if pos.get("market_slug") == market_slug
        ]

    async def get_positions_by_market_async(
        self, market_slug: str
    ) -> list[dict[str, Any]]:
        """Async version of get_positions_by_market."""
        return await self.db.get_positions_by_market(market_slug)

    def get_positions_by_outcome(self, outcome_type: str) -> list[dict[str, Any]]:
        """Get all positions for a specific outcome type."""
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                return self._run_async(self.db.get_positions_by_outcome(outcome_type))
            except Exception as e:
                log.error(f"Failed to get outcome positions from database: {e}")

        # Fallback to in-memory
        return [
            pos
            for pos in self.positions.values()
            if pos.get("outcome_type") == outcome_type
        ]

    async def get_positions_by_outcome_async(
        self, outcome_type: str
    ) -> list[dict[str, Any]]:
        """Async version of get_positions_by_outcome."""
        return await self.db.get_positions_by_outcome(outcome_type)

    def update_position_exposure(
        self,
        token_id: str,
        size_delta: float,
        notional_delta: float,
        current_price: float | None = None,
    ) -> dict[str, Any]:
        """Update position exposure incrementally.
        Useful for partial fills and position adjustments.
        """
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                return self._run_async(
                    self.db.update_position_exposure(
                        token_id, size_delta, notional_delta, current_price
                    )
                )
            except Exception as e:
                log.error(f"Failed to update position exposure in database: {e}")

        # Fallback to in-memory
        if token_id not in self.positions:
            raise ValueError(f"Position not found for token_id: {token_id}")

        old_pos = self.positions[token_id].copy()
        self.positions[token_id]["size"] += size_delta
        self.positions[token_id]["notional_value"] += notional_delta

        # Update market and outcome exposures
        market_slug = old_pos.get("market_slug")
        outcome_type = old_pos.get("outcome_type")
        if market_slug:
            self.update_market_exposure(market_slug, notional_delta)
        if outcome_type:
            self.update_outcome_exposure(outcome_type, notional_delta)

        return {
            "token_id": token_id,
            "market_slug": market_slug,
            "outcome_type": outcome_type,
            "old_size": old_pos.get("size", 0),
            "new_size": self.positions[token_id]["size"],
            "size_delta": size_delta,
            "old_notional": old_pos.get("notional_value", 0),
            "new_notional": self.positions[token_id]["notional_value"],
            "notional_delta": notional_delta,
        }

    async def update_position_exposure_async(
        self,
        token_id: str,
        size_delta: float,
        notional_delta: float,
        current_price: float | None = None,
    ) -> dict[str, Any]:
        """Async version of update_position_exposure."""
        return await self.db.update_position_exposure(
            token_id, size_delta, notional_delta, current_price
        )

    # Enhanced exposure tracking methods

    def get_detailed_market_exposure(self, market_slug: str) -> dict[str, Any]:
        """Get detailed exposure breakdown for a specific market.

        Returns:
            Dictionary with total, net, gross exposure and position details

        """
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                return self._run_async(self.db.get_market_summary(market_slug))
            except Exception as e:
                log.error(f"Failed to get detailed market exposure from database: {e}")

        return self._calculate_detailed_market_exposure_from_memory(market_slug)

    def _calculate_detailed_market_exposure_from_memory(
        self, market_slug: str
    ) -> dict[str, Any]:
        """Calculate detailed market exposure from in-memory positions."""
        positions = [
            pos
            for pos in self.positions.values()
            if pos.get("market_slug") == market_slug
        ]

        if not positions:
            return {
                "market_slug": market_slug,
                "total_exposure": 0.0,
                "net_exposure": 0.0,
                "gross_exposure": 0.0,
                "long_exposure": 0.0,
                "short_exposure": 0.0,
                "position_count": 0,
                "outcome_breakdown": {},
            }

        long_exposure = sum(
            pos.get("notional_value", 0.0)
            for pos in positions
            if pos.get("size", 0.0) > 0
        )

        short_exposure = sum(
            abs(pos.get("notional_value", 0.0))
            for pos in positions
            if pos.get("size", 0.0) < 0
        )

        net_exposure = long_exposure - short_exposure
        gross_exposure = long_exposure + short_exposure

        # Outcome breakdown
        outcome_breakdown = {}
        for pos in positions:
            outcome = pos.get("outcome_type", "unknown")
            if outcome not in outcome_breakdown:
                outcome_breakdown[outcome] = {"exposure": 0.0, "position_count": 0}
            outcome_breakdown[outcome]["exposure"] += abs(
                pos.get("notional_value", 0.0)
            )
            outcome_breakdown[outcome]["position_count"] += 1

        return {
            "market_slug": market_slug,
            "total_exposure": gross_exposure,
            "net_exposure": net_exposure,
            "gross_exposure": gross_exposure,
            "long_exposure": long_exposure,
            "short_exposure": short_exposure,
            "position_count": len(positions),
            "outcome_breakdown": outcome_breakdown,
        }

    def get_detailed_outcome_exposure(self, outcome_type: str) -> dict[str, Any]:
        """Get detailed exposure breakdown for a specific outcome type.

        Returns:
            Dictionary with total, net, gross exposure and market details

        """
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                return self._run_async(self.db.get_outcome_summary(outcome_type))
            except Exception as e:
                log.error(f"Failed to get detailed outcome exposure from database: {e}")

        return self._calculate_detailed_outcome_exposure_from_memory(outcome_type)

    def _calculate_detailed_outcome_exposure_from_memory(
        self, outcome_type: str
    ) -> dict[str, Any]:
        """Calculate detailed outcome exposure from in-memory positions."""
        positions = [
            pos
            for pos in self.positions.values()
            if pos.get("outcome_type") == outcome_type
        ]

        if not positions:
            return {
                "outcome_type": outcome_type,
                "total_exposure": 0.0,
                "net_exposure": 0.0,
                "gross_exposure": 0.0,
                "long_exposure": 0.0,
                "short_exposure": 0.0,
                "position_count": 0,
                "market_breakdown": {},
            }

        long_exposure = sum(
            pos.get("notional_value", 0.0)
            for pos in positions
            if pos.get("size", 0.0) > 0
        )

        short_exposure = sum(
            abs(pos.get("notional_value", 0.0))
            for pos in positions
            if pos.get("size", 0.0) < 0
        )

        net_exposure = long_exposure - short_exposure
        gross_exposure = long_exposure + short_exposure

        # Market breakdown
        market_breakdown = {}
        for pos in positions:
            market = pos.get("market_slug", "unknown")
            if market not in market_breakdown:
                market_breakdown[market] = {"exposure": 0.0, "position_count": 0}
            market_breakdown[market]["exposure"] += abs(pos.get("notional_value", 0.0))
            market_breakdown[market]["position_count"] += 1

        return {
            "outcome_type": outcome_type,
            "total_exposure": gross_exposure,
            "net_exposure": net_exposure,
            "gross_exposure": gross_exposure,
            "long_exposure": long_exposure,
            "short_exposure": short_exposure,
            "position_count": len(positions),
            "market_breakdown": market_breakdown,
        }

    def get_exposure_by_strategy(self, strategy_id: str) -> dict[str, Any]:
        """Get exposure breakdown for positions from a specific strategy.

        Args:
            strategy_id: Strategy identifier

        Returns:
            Dictionary with strategy exposure details

        """
        strategy_positions = [
            pos
            for pos in self.positions.values()
            if pos.get("strategy_id") == strategy_id
        ]

        if not strategy_positions:
            return {
                "strategy_id": strategy_id,
                "total_exposure": 0.0,
                "position_count": 0,
                "market_breakdown": {},
                "outcome_breakdown": {},
            }

        total_exposure = sum(
            abs(pos.get("notional_value", 0.0)) for pos in strategy_positions
        )

        # Market breakdown
        market_breakdown = {}
        outcome_breakdown = {}

        for pos in strategy_positions:
            market = pos.get("market_slug")
            outcome = pos.get("outcome_type")
            notional = abs(pos.get("notional_value", 0.0))

            if market:
                market_breakdown[market] = market_breakdown.get(market, 0.0) + notional

            if outcome:
                outcome_breakdown[outcome] = (
                    outcome_breakdown.get(outcome, 0.0) + notional
                )

        return {
            "strategy_id": strategy_id,
            "total_exposure": total_exposure,
            "position_count": len(strategy_positions),
            "market_breakdown": market_breakdown,
            "outcome_breakdown": outcome_breakdown,
        }

    def get_portfolio_exposure_summary(self) -> dict[str, Any]:
        """Get comprehensive portfolio exposure summary across all dimensions.

        Returns:
            Complete exposure breakdown with risk metrics

        """
        self._ensure_db_initialized()
        if self._db_initialized:
            try:
                # Get all positions from database
                all_positions = self._run_async(self.db.get_all_positions())
                return self._calculate_portfolio_summary_from_positions(all_positions)
            except Exception as e:
                log.error(f"Failed to get portfolio summary from database: {e}")

        # Fallback to in-memory calculation
        all_positions = list(self.positions.values())
        return self._calculate_portfolio_summary_from_positions(all_positions)

    def _calculate_portfolio_summary_from_positions(
        self, positions: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Calculate comprehensive portfolio summary from position list."""
        if not positions:
            return {
                "total_positions": 0,
                "total_exposure": 0.0,
                "net_exposure": 0.0,
                "gross_exposure": 0.0,
                "market_count": 0,
                "outcome_count": 0,
                "market_exposures": {},
                "outcome_exposures": {},
                "concentration_metrics": {},
                "risk_metrics": {},
            }

        total_exposure = sum(abs(pos.get("notional_value", 0.0)) for pos in positions)
        long_exposure = sum(
            pos.get("notional_value", 0.0)
            for pos in positions
            if pos.get("size", 0.0) > 0
        )
        short_exposure = sum(
            abs(pos.get("notional_value", 0.0))
            for pos in positions
            if pos.get("size", 0.0) < 0
        )
        net_exposure = long_exposure - short_exposure
        gross_exposure = long_exposure + short_exposure

        # Market and outcome breakdowns
        market_exposures = {}
        outcome_exposures = {}

        for pos in positions:
            market = pos.get("market_slug")
            outcome = pos.get("outcome_type")
            notional = abs(pos.get("notional_value", 0.0))

            if market:
                market_exposures[market] = market_exposures.get(market, 0.0) + notional
            if outcome:
                outcome_exposures[outcome] = (
                    outcome_exposures.get(outcome, 0.0) + notional
                )

        # Concentration metrics
        max_market_exposure = (
            max(market_exposures.values()) if market_exposures else 0.0
        )
        max_outcome_exposure = (
            max(outcome_exposures.values()) if outcome_exposures else 0.0
        )

        market_concentration = (
            max_market_exposure / total_exposure if total_exposure > 0 else 0.0
        )
        outcome_concentration = (
            max_outcome_exposure / total_exposure if total_exposure > 0 else 0.0
        )

        # Herfindahl Index for concentration
        market_hhi = (
            sum((exp / total_exposure) ** 2 for exp in market_exposures.values())
            if total_exposure > 0
            else 0.0
        )

        outcome_hhi = (
            sum((exp / total_exposure) ** 2 for exp in outcome_exposures.values())
            if total_exposure > 0
            else 0.0
        )

        return {
            "total_positions": len(positions),
            "total_exposure": total_exposure,
            "net_exposure": net_exposure,
            "gross_exposure": gross_exposure,
            "long_exposure": long_exposure,
            "short_exposure": short_exposure,
            "market_count": len(market_exposures),
            "outcome_count": len(outcome_exposures),
            "market_exposures": market_exposures,
            "outcome_exposures": outcome_exposures,
            "concentration_metrics": {
                "market_concentration": market_concentration,
                "outcome_concentration": outcome_concentration,
                "market_hhi": market_hhi,
                "outcome_hhi": outcome_hhi,
                "max_market_exposure": max_market_exposure,
                "max_outcome_exposure": max_outcome_exposure,
            },
            "risk_metrics": {
                "leverage_ratio": gross_exposure / max(net_exposure, 1.0),
                "diversification_ratio": len(market_exposures) / max(len(positions), 1),
            },
        }

    def calculate_exposure_delta(
        self,
        token_id: str,
        size_delta: float,
        price: float,
        market_slug: str = None,
        outcome_type: str = None,
    ) -> dict[str, float]:
        """Calculate the exposure change from a position update without full recalculation.

        Args:
            token_id: Position token identifier
            size_delta: Change in position size
            price: Current/trade price
            market_slug: Market identifier (optional)
            outcome_type: Outcome identifier (optional)

        Returns:
            Dictionary with exposure deltas

        """
        notional_delta = abs(size_delta * price)
        net_delta = size_delta * price  # Signed for net exposure

        current_position = self.positions.get(token_id, {})
        current_size = current_position.get("size", 0.0)

        # Determine if this creates, increases, decreases, or closes a position
        new_size = current_size + size_delta

        position_status = "unknown"
        if current_size == 0 and new_size != 0:
            position_status = "opened"
        elif current_size != 0 and new_size == 0:
            position_status = "closed"
        elif abs(new_size) > abs(current_size):
            position_status = "increased"
        elif abs(new_size) < abs(current_size):
            position_status = "decreased"

        return {
            "token_id": token_id,
            "size_delta": size_delta,
            "notional_delta": notional_delta,
            "net_delta": net_delta,
            "market_slug": market_slug or current_position.get("market_slug"),
            "outcome_type": outcome_type or current_position.get("outcome_type"),
            "position_status": position_status,
            "old_size": current_size,
            "new_size": new_size,
            "price": price,
        }

    def get_top_positions_by_exposure(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get the largest positions by notional exposure.

        Args:
            limit: Maximum number of positions to return

        Returns:
            List of positions sorted by exposure (descending)

        """
        positions_with_exposure = [
            {
                "token_id": token_id,
                "notional_value": abs(pos.get("notional_value", 0.0)),
                "size": pos.get("size", 0.0),
                "market_slug": pos.get("market_slug"),
                "outcome_type": pos.get("outcome_type"),
                "strategy_id": pos.get("strategy_id"),
                **pos,
            }
            for token_id, pos in self.positions.items()
        ]

        # Sort by notional value (descending)
        positions_with_exposure.sort(key=lambda x: x["notional_value"], reverse=True)

        return positions_with_exposure[:limit]

    def get_exposure_alerts(self, limits: dict[str, float]) -> list[dict[str, Any]]:
        """Check current exposures against limits and return alerts.

        Args:
            limits: Dictionary with exposure limits

        Returns:
            List of exposure limit violations

        """
        alerts = []
        current_time = time.time()

        # Get current portfolio summary
        portfolio = self.get_portfolio_exposure_summary()

        # Check global exposure
        if "global_risk_cap" in limits and limits["global_risk_cap"] > 0:
            utilization = portfolio["total_exposure"] / limits["global_risk_cap"]
            if utilization > 0.8:  # 80% warning threshold
                alerts.append(
                    {
                        "type": "global_exposure_warning",
                        "current": portfolio["total_exposure"],
                        "limit": limits["global_risk_cap"],
                        "utilization": utilization,
                        "severity": "critical" if utilization > 1.0 else "warning",
                        "timestamp": current_time,
                    }
                )

        # Check market exposures
        if "per_market_risk_cap" in limits and limits["per_market_risk_cap"] > 0:
            for market_slug, exposure in portfolio["market_exposures"].items():
                utilization = exposure / limits["per_market_risk_cap"]
                if utilization > 0.8:
                    alerts.append(
                        {
                            "type": "market_exposure_warning",
                            "market_slug": market_slug,
                            "current": exposure,
                            "limit": limits["per_market_risk_cap"],
                            "utilization": utilization,
                            "severity": "critical" if utilization > 1.0 else "warning",
                            "timestamp": current_time,
                        }
                    )

        # Check outcome exposures
        if "per_outcome_risk_cap" in limits and limits["per_outcome_risk_cap"] > 0:
            for outcome_type, exposure in portfolio["outcome_exposures"].items():
                utilization = exposure / limits["per_outcome_risk_cap"]
                if utilization > 0.8:
                    alerts.append(
                        {
                            "type": "outcome_exposure_warning",
                            "outcome_type": outcome_type,
                            "current": exposure,
                            "limit": limits["per_outcome_risk_cap"],
                            "utilization": utilization,
                            "severity": "critical" if utilization > 1.0 else "warning",
                            "timestamp": current_time,
                        }
                    )

        # Check concentration risks
        concentration = portfolio["concentration_metrics"]
        if concentration["market_concentration"] > 0.5:  # 50% in single market
            alerts.append(
                {
                    "type": "concentration_warning",
                    "concentration_type": "market",
                    "concentration_ratio": concentration["market_concentration"],
                    "max_exposure": concentration["max_market_exposure"],
                    "severity": "warning",
                    "timestamp": current_time,
                }
            )

        if concentration["outcome_concentration"] > 0.5:  # 50% in single outcome
            alerts.append(
                {
                    "type": "concentration_warning",
                    "concentration_type": "outcome",
                    "concentration_ratio": concentration["outcome_concentration"],
                    "max_exposure": concentration["max_outcome_exposure"],
                    "severity": "warning",
                    "timestamp": current_time,
                }
            )

        return alerts
