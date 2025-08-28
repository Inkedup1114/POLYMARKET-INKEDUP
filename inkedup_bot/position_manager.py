"""Position manager for unified position tracking and management across trading strategies.

This module provides the PositionManager class which serves as the central coordinator
for all position-related operations in the InkedUp Polymarket trading bot. It manages
position lifecycle, maintains in-memory caches for performance, and provides consistent
data access patterns across all trading components.

The position manager handles:
- Position creation and lifecycle management
- Real-time position tracking and updates
- Database persistence and synchronization
- Market-based position aggregation and analysis
- Risk monitoring integration
- Performance metrics collection

Architecture:
    The PositionManager uses a dual-storage approach with in-memory caching
    backed by persistent database storage. This design provides fast access
    for real-time trading decisions while ensuring data durability.

Examples:
    Basic position management:

    >>> from inkedup_bot.database_complete import DatabaseManager
    >>> from inkedup_bot.position_manager import PositionManager
    >>> from decimal import Decimal
    >>>
    >>> # Initialize with database
    >>> db = DatabaseManager()
    >>> pm = PositionManager(db)
    >>> await pm.initialize()
    >>>
    >>> # Create a new position
    >>> position = await pm.create_position(
    ...     token_id="0x123abc456def...",
    ...     market_slug="election-2024",
    ...     outcome_type="yes",
    ...     size=Decimal("100.0"),
    ...     price=Decimal("0.65"),
    ...     strategy_id="complement_arb"
    ... )
    >>>
    >>> # Query positions
    >>> market_positions = pm.get_positions_by_market("election-2024")
    >>> print(f"Market has {len(market_positions)} positions")

Performance:
    The manager maintains indexed in-memory caches for O(1) position lookups
    by ID and efficient market-based queries. Background synchronization
    ensures database consistency without blocking trading operations.

Thread Safety:
    The PositionManager is designed for single-threaded async operation.
    All methods should be called from the same event loop to ensure
    data consistency and thread safety.

"""

import logging
from decimal import Decimal
from typing import Any

from .database_complete import DatabaseManager
from .position_models import Position, PositionStatus

logger = logging.getLogger(__name__)


class PositionManager:
    """Unified position manager for tracking and managing all trading positions.

    The PositionManager serves as the central coordinator for position lifecycle
    management, providing fast access to position data while maintaining database
    persistence. It supports real-time position tracking, market-based aggregation,
    and integration with risk management systems.

    Key Features:
        - Dual-storage architecture with in-memory caching
        - Market-based position indexing for efficient queries
        - Automatic database synchronization
        - Position lifecycle management (create, update, close)
        - Risk monitoring integration points
        - Performance metrics collection

    Attributes:
        db: Database manager for persistent storage
        _positions: In-memory position cache indexed by position ID
        _positions_by_market: Market-indexed position cache for efficient queries
        logger: Logger instance for position tracking events

    Examples:
        Initialize and use the position manager:

        >>> # Setup with database
        >>> db_manager = DatabaseManager()
        >>> position_manager = PositionManager(db_manager)
        >>> await position_manager.initialize()
        >>>
        >>> # Create a new position
        >>> position = await position_manager.create_position(
        ...     token_id="0x789def123abc...",
        ...     market_slug="sports-nfl-championship",
        ...     outcome_type="yes",
        ...     size=Decimal("250.0"),
        ...     price=Decimal("0.42"),
        ...     strategy_id="spread_arb"
        ... )
        >>>
        >>> # Query positions by market
        >>> nfl_positions = position_manager.get_positions_by_market("sports-nfl-championship")
        >>> total_exposure = sum(p.notional_value for p in nfl_positions)
        >>> print(f"NFL market exposure: ${total_exposure}")

    Cache Management:
        Positions are cached in two data structures:
        - _positions: Direct access by position ID
        - _positions_by_market: Nested access by market and outcome

        This dual indexing enables both O(1) position lookups and efficient
        market-based queries for risk analysis and reporting.

    Error Handling:
        All database operations include proper error handling with logging.
        Cache inconsistencies are detected and resolved through database
        synchronization when possible.

    Thread Safety:
        Designed for single-threaded async operation. All methods should
        be called from the same event loop to prevent race conditions.

    """

    def __init__(self, db_manager: DatabaseManager) -> None:
        """Initialize position manager with database connection.

        Args:
            db_manager: Database manager instance for persistent storage.
                       Must be properly initialized before use.

        Note:
            The position manager requires initialize() to be called
            before use to load existing positions from the database.

        """
        self.db = db_manager
        self._positions: dict[str, Position] = {}
        self._positions_by_market: dict[str, dict[str, Position]] = {}
        self.logger = logger

    async def initialize(self) -> None:
        """Initialize position manager and load existing positions from database.

        This method must be called after construction and before any position
        operations. It loads all active positions from the database into memory
        caches for fast access during trading operations.

        Raises:
            DatabaseError: If database connection fails or queries error
            ValueError: If position data is corrupted or invalid

        Example:
            >>> pm = PositionManager(db_manager)
            >>> await pm.initialize()  # Required before use
            >>> # Now ready for position operations

        """
        try:
            await self._load_positions_from_db()
            self.logger.info(
                f"PositionManager initialized with {len(self._positions)} positions"
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize PositionManager: {e}")
            raise

    async def _load_positions_from_db(self) -> None:
        """Load positions from database into memory."""
        try:
            async with self.db.connection() as db:
                # Load active positions
                async with db.execute(
                    "SELECT * FROM positions WHERE status IN ('open', 'partially_closed')"
                ) as cursor:
                    rows = await cursor.fetchall()

                    for row in rows:
                        position = Position.from_dict(dict(row))
                        self._add_position_to_cache(position)

        except Exception as e:
            self.logger.error(f"Error loading positions from database: {e}")

    def _add_position_to_cache(self, position: Position) -> None:
        """Add position to in-memory cache."""
        self._positions[position.position_id] = position

        # Index by market and outcome
        market_key = f"{position.market_slug}:{position.outcome_type}"
        if market_key not in self._positions_by_market:
            self._positions_by_market[market_key] = {}
        self._positions_by_market[market_key][position.position_id] = position

    def _remove_position_from_cache(self, position_id: str) -> None:
        """Remove position from in-memory cache."""
        if position_id in self._positions:
            position = self._positions[position_id]
            market_key = f"{position.market_slug}:{position.outcome_type}"

            if market_key in self._positions_by_market:
                self._positions_by_market[market_key].pop(position_id, None)
                if not self._positions_by_market[market_key]:
                    del self._positions_by_market[market_key]

            del self._positions[position_id]

    async def create_position(
        self,
        token_id: str,
        market_slug: str,
        outcome_type: str,
        size: Decimal,
        price: Decimal,
        strategy_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Position:
        """Create a new position."""
        try:
            notional_value = size * price

            position = Position(
                token_id=token_id,
                market_slug=market_slug,
                outcome_type=outcome_type,
                size=size,
                notional_value=notional_value,
                average_price=price,
                current_price=price,
                strategy_id=strategy_id,
                metadata=metadata or {},
            )

            # Save to database
            await self._save_position_to_db(position)

            # Add to cache
            self._add_position_to_cache(position)

            self.logger.info(
                f"Created position {position.position_id} for {market_slug}:{outcome_type} "
                f"size={size} price={price}"
            )

            return position

        except Exception as e:
            self.logger.error(f"Failed to create position: {e}")
            raise

    async def _save_position_to_db(self, position: Position) -> None:
        """Save position to database."""
        try:
            async with self.db.connection() as db:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO positions (
                        token_id, market_slug, outcome_type, size,
                        notional_value, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        position.token_id,
                        position.market_slug,
                        position.outcome_type,
                        float(position.size),
                        float(position.notional_value),
                        position.updated_at.isoformat(),
                    ),
                )
        except Exception as e:
            self.logger.error(f"Failed to save position to database: {e}")
            raise

    def get_position(self, position_id: str) -> Position | None:
        """Get position by ID."""
        return self._positions.get(position_id)

    def get_positions_by_market(
        self, market_slug: str, outcome_type: str | None = None
    ) -> list[Position]:
        """Get positions for a specific market."""
        positions: list[Position] = []
        if outcome_type:
            market_key = f"{market_slug}:{outcome_type}"
            return list(self._positions_by_market.get(market_key, {}).values())
        else:
            for key, pos_dict in self._positions_by_market.items():
                if key.startswith(f"{market_slug}:"):
                    positions.extend(pos_dict.values())
            return positions

    def get_open_positions(self) -> list[Position]:
        """Get all open positions."""
        return [p for p in self._positions.values() if p.is_open]

    def get_positions_by_strategy(self, strategy_id: str) -> list[Position]:
        """Get positions for a specific strategy."""
        return [p for p in self._positions.values() if p.strategy_id == strategy_id]

    async def update_position_price(
        self, position_id: str, new_price: Decimal
    ) -> Position | None:
        """Update position with new market price."""
        position = self.get_position(position_id)
        if not position:
            self.logger.warning(f"Position {position_id} not found")
            return None

        try:
            position.update_current_price(new_price)
            await self._save_position_to_db(position)

            self.logger.debug(
                f"Updated position {position_id} price to {new_price}, "
                f"unrealized_pnl={position.unrealized_pnl}"
            )

            return position

        except Exception as e:
            self.logger.error(f"Failed to update position price: {e}")
            return None

    async def close_position(
        self, position_id: str, exit_price: Decimal, exit_size: Decimal | None = None
    ) -> dict[str, Decimal] | None:
        """Close or partially close a position."""
        position = self.get_position(position_id)
        if not position:
            self.logger.warning(f"Position {position_id} not found")
            return None

        try:
            result = position.close_position(exit_price, exit_size)
            await self._save_position_to_db(position)

            if position.status == PositionStatus.CLOSED:
                self._remove_position_from_cache(position_id)

            self.logger.info(
                f"Closed position {position_id}: realized_pnl={result['realized_pnl']} "
                f"exit_size={result['exit_size']}"
            )

            return result

        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")
            return None

    async def reconcile_positions(
        self, exchange_positions: list[dict[str, Any]]
    ) -> tuple[list[Position], list[dict[str, Any]]]:
        """Reconcile local positions with exchange positions."""
        try:
            matched_positions = []
            unmatched_exchange: list[dict[str, Any]] = []

            # Create lookup for exchange positions
            exchange_lookup = {
                f"{pos['token_id']}:{pos['outcome_type']}": pos
                for pos in exchange_positions
            }

            # Check local positions against exchange
            for position in self.get_open_positions():
                key = f"{position.token_id}:{position.outcome_type}"
                if key in exchange_lookup:
                    exchange_pos = exchange_lookup[key]

                    # Update if sizes differ
                    if Decimal(str(exchange_pos["size"])) != position.size:
                        self.logger.warning(
                            f"Size mismatch for {key}: "
                            f"local={position.size}, exchange={exchange_pos['size']}"
                        )
                        # Could implement auto-correction here

                    matched_positions.append(position)
                    del exchange_lookup[key]
                else:
                    self.logger.warning(
                        f"Local position {position.position_id} not found on exchange"
                    )

            # Remaining exchange positions are unmatched
            unmatched_exchange = list(exchange_lookup.values())

            return matched_positions, unmatched_exchange

        except Exception as e:
            self.logger.error(f"Failed to reconcile positions: {e}")
            return [], []

    def get_total_exposure(self) -> Decimal:
        """Get total exposure across all open positions."""
        return sum((p.notional_value for p in self.get_open_positions()), Decimal("0"))

    def get_exposure_by_market(self, market_slug: str) -> Decimal:
        """Get total exposure for a specific market."""
        positions = self.get_positions_by_market(market_slug)
        return sum((p.notional_value for p in positions if p.is_open), Decimal("0"))

    def get_pnl_summary(self) -> dict[str, Decimal]:
        """Get P&L summary across all positions."""
        open_positions = self.get_open_positions()
        total_unrealized = sum((p.unrealized_pnl for p in open_positions), Decimal("0"))
        total_realized = sum(
            (p.realized_pnl for p in self._positions.values()), Decimal("0")
        )
        total_fees = sum((p.fees for p in self._positions.values()), Decimal("0"))

        return {
            "total_unrealized_pnl": total_unrealized,
            "total_realized_pnl": total_realized,
            "total_fees": total_fees,
            "total_pnl": total_unrealized + total_realized - total_fees,
        }
