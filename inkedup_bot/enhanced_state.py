"""
Enhanced StateManager with comprehensive fallback support.

This module provides a production-ready StateManager that seamlessly
switches between database and in-memory operations when the database
becomes unavailable.
"""

import asyncio
import logging
import time
from typing import Any

from .database import DatabaseManager
from .fallback import FallbackManager, FallbackMode
from .validation import (
    OrderValidation,
    PositionValidation,
    ValidationError,
    validate_model_data,
    validate_state_update,
)

log = logging.getLogger("enhanced_state")


class EnhancedStateManager:
    """
    Enhanced StateManager with comprehensive fallback support.

    Provides seamless operation even when the primary database becomes
    unavailable, with automatic health monitoring, data synchronization,
    and recovery procedures.
    """

    def __init__(
        self,
        db_path: str = "bot_data.db",
        enable_fallback: bool = True,
        sync_interval: float = 300.0,  # 5 minutes
        health_check_interval: float = 30.0,  # 30 seconds
        enable_auto_recovery: bool = True,
    ) -> None:
        # Initialize database manager
        self.db = DatabaseManager(db_path)

        # Initialize fallback manager if enabled
        self.enable_fallback = enable_fallback
        if enable_fallback:
            self.fallback_manager = FallbackManager(
                database_manager=self.db,
                sync_interval=sync_interval,
                enable_auto_recovery=enable_auto_recovery,
            )
        else:
            self.fallback_manager = None

        # State tracking
        self._initialized = False
        self._risk_manager: Any | None = None

        # Legacy in-memory storage for backward compatibility
        self.open_orders: dict[str, Any] = {}
        self.positions: dict[str, Any] = {}
        self.market_exposures: dict[str, float] = {}
        self.outcome_exposures: dict[str, float] = {}

    async def initialize(self) -> None:
        """Initialize the enhanced state manager."""
        if self._initialized:
            return

        if self.fallback_manager:
            await self.fallback_manager.start()
            log.info("Enhanced state manager initialized with fallback support")
        else:
            await self.db.initialize()
            log.info("Enhanced state manager initialized without fallback")

        self._initialized = True

    async def shutdown(self) -> None:
        """Shutdown the state manager gracefully."""
        if self.fallback_manager:
            await self.fallback_manager.stop()
        await self.db.close()
        log.info("Enhanced state manager shutdown complete")

    def set_risk_manager(self, risk_manager: Any) -> None:
        """Set reference to risk manager."""
        self._risk_manager = risk_manager

    def _notify_risk_manager_of_position_update(
        self, token_id: str, position_data: dict[str, Any]
    ) -> None:
        """Notify risk manager of position updates."""
        if self._risk_manager is not None:
            try:
                self._risk_manager.update_fallback_cache_position(
                    token_id, position_data
                )
            except Exception as e:
                log.warning(f"Failed to update risk manager fallback cache: {e}")

    # Order Management Methods
    @validate_state_update
    async def add_order(self, order: dict[str, Any]) -> None:
        """Add a newly placed order with fallback support."""
        # Validate order data
        try:
            validated_order = validate_model_data(OrderValidation, order)
            order_data = validated_order.model_dump()
        except ValidationError as e:
            log.error(f"Order validation failed: {e}")
            raise

        order_id = order_data.get("id")
        if not order_id:
            raise ValidationError("Order must have an ID")

        log.info(f"Adding order {order_id}")

        if not self.fallback_manager:
            # Direct database operation without fallback
            await self.db.insert_order(order_data)
            return

        # Use fallback manager for resilient operation
        async with self.fallback_manager.operation_context("add_order") as mode:
            if mode == "primary":
                await self.db.insert_order(order_data)
            else:  # fallback mode
                self.fallback_manager.memory_store.insert_order(order_data)
                # Update legacy storage for backward compatibility
                self.open_orders[order_id] = order_data

    @validate_state_update
    async def update_order(self, order_id: str, update_data: dict[str, Any]) -> None:
        """Update an existing order with fallback support."""
        if not update_data:
            return

        log.info(f"Updating order {order_id}")

        if not self.fallback_manager:
            # Direct database operation without fallback
            await self.db.update_order(order_id, update_data)
            return

        # Use fallback manager for resilient operation
        async with self.fallback_manager.operation_context("update_order") as mode:
            if mode == "primary":
                await self.db.update_order(order_id, update_data)
            else:  # fallback mode
                self.fallback_manager.memory_store.update_order(order_id, update_data)
                # Update legacy storage
                if order_id in self.open_orders:
                    self.open_orders[order_id].update(update_data)
                    # Remove from open orders if completed
                    status = update_data.get("status", "")
                    if status in ["FILLED", "CANCELLED"]:
                        self.open_orders.pop(order_id, None)

    async def get_order(self, order_id: str) -> dict[str, Any] | None:
        """Get order by ID with fallback support."""
        if not self.fallback_manager:
            # Direct database operation
            try:
                async with self.db.connection() as conn:
                    async with conn.execute(
                        "SELECT * FROM orders WHERE id = ?", (order_id,)
                    ) as cursor:
                        row = await cursor.fetchone()
                        return dict(row) if row else None
            except Exception as e:
                log.error(f"Failed to get order from database: {e}")
                return self.open_orders.get(order_id)

        # Use fallback manager
        async with self.fallback_manager.operation_context("get_order") as mode:
            if mode == "primary":
                async with self.db.connection() as conn:
                    async with conn.execute(
                        "SELECT * FROM orders WHERE id = ?", (order_id,)
                    ) as cursor:
                        row = await cursor.fetchone()
                        return dict(row) if row else None
            else:  # fallback mode
                return self.fallback_manager.memory_store.get_order(order_id)

    # Position Management Methods
    @validate_state_update
    async def update_position(self, position_data: dict[str, Any]) -> None:
        """Update position with fallback support."""
        # Validate position data
        try:
            validated_position = validate_model_data(PositionValidation, position_data)
            pos_data = validated_position.model_dump()
        except ValidationError as e:
            log.error(f"Position validation failed: {e}")
            raise

        token_id = pos_data.get("token_id")
        if not token_id:
            raise ValidationError("Position must have a token_id")

        log.info(f"Updating position for token {token_id}")

        if not self.fallback_manager:
            # Direct database operation without fallback
            await self.db.upsert_position(pos_data)
            self._notify_risk_manager_of_position_update(token_id, pos_data)
            return

        # Use fallback manager for resilient operation
        async with self.fallback_manager.operation_context("update_position") as mode:
            if mode == "primary":
                await self.db.upsert_position(pos_data)
            else:  # fallback mode
                self.fallback_manager.memory_store.upsert_position(pos_data)
                # Update legacy storage
                self.positions[token_id] = pos_data

            # Always notify risk manager
            self._notify_risk_manager_of_position_update(token_id, pos_data)

    async def get_position(self, token_id: str) -> dict[str, Any] | None:
        """Get position by token ID with fallback support."""
        if not self.fallback_manager:
            # Direct database operation
            try:
                async with self.db.connection() as conn:
                    async with conn.execute(
                        "SELECT * FROM positions WHERE token_id = ?", (token_id,)
                    ) as cursor:
                        row = await cursor.fetchone()
                        return dict(row) if row else None
            except Exception as e:
                log.error(f"Failed to get position from database: {e}")
                return self.positions.get(token_id)

        # Use fallback manager
        async with self.fallback_manager.operation_context("get_position") as mode:
            if mode == "primary":
                async with self.db.connection() as conn:
                    async with conn.execute(
                        "SELECT * FROM positions WHERE token_id = ?", (token_id,)
                    ) as cursor:
                        row = await cursor.fetchone()
                        return dict(row) if row else None
            else:  # fallback mode
                return self.fallback_manager.memory_store.get_position(token_id)

    async def get_all_positions(self) -> list[dict[str, Any]]:
        """Get all positions with fallback support."""
        if not self.fallback_manager:
            # Direct database operation
            try:
                return await self.db.get_all_positions()
            except Exception as e:
                log.error(f"Failed to get positions from database: {e}")
                return list(self.positions.values())

        # Use fallback manager
        async with self.fallback_manager.operation_context("get_all_positions") as mode:
            if mode == "primary":
                return await self.db.get_all_positions()
            else:  # fallback mode
                return self.fallback_manager.memory_store.get_all_positions()

    async def get_positions_by_market(self, market_slug: str) -> list[dict[str, Any]]:
        """Get positions by market with fallback support."""
        if not self.fallback_manager:
            # Direct database operation
            try:
                return await self.db.get_positions_by_market(market_slug)
            except Exception as e:
                log.error(f"Failed to get market positions from database: {e}")
                return [
                    pos
                    for pos in self.positions.values()
                    if pos.get("market_slug") == market_slug
                ]

        # Use fallback manager
        async with self.fallback_manager.operation_context(
            "get_positions_by_market"
        ) as mode:
            if mode == "primary":
                return await self.db.get_positions_by_market(market_slug)
            else:  # fallback mode
                return self.fallback_manager.memory_store.get_positions_by_market(
                    market_slug
                )

    # Trade Management Methods
    async def record_trade_impact(
        self,
        token_id: str,
        trade_size: float,
        trade_price: float,
        side: str,
        market_slug: str,
        outcome_type: str,
    ) -> dict[str, Any]:
        """Record trade impact with fallback support."""
        log.info(f"Recording trade impact for {token_id}")

        if not self.fallback_manager:
            # Direct database operation
            try:
                return await self.db.record_trade_impact(
                    token_id, trade_size, trade_price, side, market_slug, outcome_type
                )
            except Exception as e:
                log.error(f"Failed to record trade impact in database: {e}")
                # Fallback calculation
                return self._calculate_trade_impact_fallback(
                    token_id, trade_size, trade_price, side, market_slug, outcome_type
                )

        # Use fallback manager
        async with self.fallback_manager.operation_context(
            "record_trade_impact"
        ) as mode:
            if mode == "primary":
                return await self.db.record_trade_impact(
                    token_id, trade_size, trade_price, side, market_slug, outcome_type
                )
            else:  # fallback mode
                # Record in memory and calculate impact
                trade_data = {
                    "order_id": f"trade_{token_id}_{int(time.time())}",
                    "token_id": token_id,
                    "market_slug": market_slug,
                    "side": side,
                    "price": trade_price,
                    "size": trade_size,
                    "notional_value": abs(trade_size * trade_price),
                    "outcome_type": outcome_type,
                }

                self.fallback_manager.memory_store.record_trade(trade_data)
                return self._calculate_trade_impact_fallback(
                    token_id, trade_size, trade_price, side, market_slug, outcome_type
                )

    def _calculate_trade_impact_fallback(
        self,
        token_id: str,
        trade_size: float,
        trade_price: float,
        side: str,
        market_slug: str,
        outcome_type: str,
    ) -> dict[str, Any]:
        """Calculate trade impact using fallback logic."""
        notional_value = abs(trade_size * trade_price)
        signed_size = trade_size if side.upper() == "BUY" else -trade_size
        signed_notional = notional_value if side.upper() == "BUY" else -notional_value

        # Update legacy exposure tracking
        current_market = self.market_exposures.get(market_slug, 0.0)
        self.market_exposures[market_slug] = current_market + signed_notional

        current_outcome = self.outcome_exposures.get(outcome_type, 0.0)
        self.outcome_exposures[outcome_type] = current_outcome + signed_notional

        return {
            "token_id": token_id,
            "market_slug": market_slug,
            "outcome_type": outcome_type,
            "size_delta": signed_size,
            "notional_delta": signed_notional,
            "trade_notional": notional_value,
            "side": side,
            "price": trade_price,
        }

    # Exposure Tracking Methods
    async def get_market_exposure(self, market_slug: str) -> float:
        """Get market exposure with fallback support."""
        if not self.fallback_manager:
            # Direct database operation
            try:
                return await self.db.get_market_exposure(market_slug)
            except Exception as e:
                log.error(f"Failed to get market exposure from database: {e}")
                return self.market_exposures.get(market_slug, 0.0)

        # Use fallback manager
        async with self.fallback_manager.operation_context(
            "get_market_exposure"
        ) as mode:
            if mode == "primary":
                return await self.db.get_market_exposure(market_slug)
            else:  # fallback mode
                # Calculate from positions in memory
                positions = self.fallback_manager.memory_store.get_positions_by_market(
                    market_slug
                )
                return sum(pos.get("notional_value", 0.0) for pos in positions)

    async def get_outcome_exposure(self, outcome_type: str) -> float:
        """Get outcome exposure with fallback support."""
        if not self.fallback_manager:
            # Direct database operation
            try:
                return await self.db.get_outcome_exposure(outcome_type)
            except Exception as e:
                log.error(f"Failed to get outcome exposure from database: {e}")
                return self.outcome_exposures.get(outcome_type, 0.0)

        # Use fallback manager
        async with self.fallback_manager.operation_context(
            "get_outcome_exposure"
        ) as mode:
            if mode == "primary":
                return await self.db.get_outcome_exposure(outcome_type)
            else:  # fallback mode
                # Calculate from positions in memory
                all_positions = self.fallback_manager.memory_store.get_all_positions()
                return sum(
                    pos.get("notional_value", 0.0)
                    for pos in all_positions
                    if pos.get("outcome_type") == outcome_type
                )

    async def get_total_exposure(self) -> float:
        """Get total exposure with fallback support."""
        if not self.fallback_manager:
            # Direct database operation
            try:
                return await self.db.get_total_exposure()
            except Exception as e:
                log.error(f"Failed to get total exposure from database: {e}")
                return sum(abs(exp) for exp in self.market_exposures.values())

        # Use fallback manager
        async with self.fallback_manager.operation_context(
            "get_total_exposure"
        ) as mode:
            if mode == "primary":
                return await self.db.get_total_exposure()
            else:  # fallback mode
                # Calculate from all positions in memory
                all_positions = self.fallback_manager.memory_store.get_all_positions()
                return sum(abs(pos.get("notional_value", 0.0)) for pos in all_positions)

    # Portfolio Methods
    async def get_portfolio_summary(self) -> dict[str, Any]:
        """Get portfolio summary with fallback support."""
        if not self.fallback_manager:
            # Direct database operation
            try:
                return await self.db.get_portfolio_summary()
            except Exception as e:
                log.error(f"Failed to get portfolio summary from database: {e}")
                return self._calculate_portfolio_summary_fallback()

        # Use fallback manager
        async with self.fallback_manager.operation_context(
            "get_portfolio_summary"
        ) as mode:
            if mode == "primary":
                return await self.db.get_portfolio_summary()
            else:  # fallback mode
                return self._calculate_portfolio_summary_fallback()

    def _calculate_portfolio_summary_fallback(self) -> dict[str, Any]:
        """Calculate portfolio summary from fallback data."""
        if self.fallback_manager:
            positions = self.fallback_manager.memory_store.get_all_positions()
        else:
            positions = list(self.positions.values())

        total_positions = len(positions)
        total_notional = sum(abs(pos.get("notional_value", 0.0)) for pos in positions)
        net_notional = sum(pos.get("notional_value", 0.0) for pos in positions)

        markets = set(
            pos.get("market_slug") for pos in positions if pos.get("market_slug")
        )
        outcomes = set(
            pos.get("outcome_type") for pos in positions if pos.get("outcome_type")
        )

        return {
            "total_positions": total_positions,
            "total_markets": len(markets),
            "total_outcomes": len(outcomes),
            "gross_notional": total_notional,
            "net_notional": net_notional,
            "largest_position": max(
                (abs(pos.get("notional_value", 0.0)) for pos in positions), default=0.0
            ),
            "positions_by_market": {
                market: len([p for p in positions if p.get("market_slug") == market])
                for market in markets
            },
            "calculated_at": time.time(),
        }

    # Status and Health Methods
    def get_fallback_status(self) -> dict[str, Any]:
        """Get comprehensive fallback status."""
        if not self.fallback_manager:
            return {"fallback_enabled": False, "mode": "direct_database"}

        return self.fallback_manager.get_status()

    def get_health_metrics(self) -> dict[str, Any]:
        """Get health metrics."""
        if not self.fallback_manager:
            return {"health_monitoring": False}

        metrics = self.fallback_manager.get_metrics()
        return {
            "health_monitoring": True,
            "is_healthy": metrics.is_healthy,
            "current_mode": metrics.mode.value,
            "health_status": metrics.health_status.value,
            "primary_success_rate": metrics.primary_success_rate,
            "recovery_attempts": metrics.recovery_attempts,
            "data_loss_events": metrics.data_loss_events,
        }

    async def force_fallback_mode(self, reason: str = "Manual override") -> None:
        """Force switch to fallback mode (for testing/emergency)."""
        if self.fallback_manager:
            await self.fallback_manager.switch_to_fallback(reason)
            log.warning(f"Manually forced fallback mode: {reason}")

    async def force_recovery_attempt(self) -> bool:
        """Force recovery attempt (for testing/manual recovery)."""
        if (
            self.fallback_manager
            and self.fallback_manager.current_mode == FallbackMode.FALLBACK
        ):
            await self.fallback_manager.attempt_recovery()
            return self.fallback_manager.current_mode == FallbackMode.PRIMARY
        return False

    # Legacy compatibility methods (delegating to fallback-aware versions)
    def add_order_sync(self, order: dict[str, Any]) -> None:
        """Synchronous wrapper for add_order (legacy compatibility)."""
        return self._run_async(self.add_order(order))

    def update_position_sync(self, position_data: dict[str, Any]) -> None:
        """Synchronous wrapper for update_position (legacy compatibility)."""
        return self._run_async(self.update_position(position_data))

    def get_position_notional(self, token_id: str) -> float:
        """Get position notional value (legacy compatibility)."""
        position = self._run_async(self.get_position(token_id))
        return position.get("notional_value", 0.0) if position else 0.0

    def _run_async(self, coro):
        """Helper to run async operations synchronously."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()
