"""Position manager for unified position tracking and management."""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import asyncio

from .position_models import Position, PositionStatus
from .database_complete import DatabaseManager

logger = logging.getLogger(__name__)


class PositionManager:
    """Unified position manager for tracking and managing all trading positions."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize position manager with database connection."""
        self.db = db_manager
        self._positions: Dict[str, Position] = {}
        self._positions_by_market: Dict[str, Dict[str, Position]] = {}
        self.logger = logger
        
    async def initialize(self) -> None:
        """Initialize position manager and load existing positions."""
        try:
            await self._load_positions_from_db()
            self.logger.info(f"PositionManager initialized with {len(self._positions)} positions")
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
        strategy_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
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
                metadata=metadata or {}
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
                        position.updated_at.isoformat()
                    )
                )
        except Exception as e:
            self.logger.error(f"Failed to save position to database: {e}")
            raise
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """Get position by ID."""
        return self._positions.get(position_id)
    
    def get_positions_by_market(
        self,
        market_slug: str,
        outcome_type: Optional[str] = None
    ) -> List[Position]:
        """Get positions for a specific market."""
        positions: List[Position] = []
        if outcome_type:
            market_key = f"{market_slug}:{outcome_type}"
            return list(self._positions_by_market.get(market_key, {}).values())
        else:
            for key, pos_dict in self._positions_by_market.items():
                if key.startswith(f"{market_slug}:"):
                    positions.extend(pos_dict.values())
            return positions
    
    def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        return [p for p in self._positions.values() if p.is_open]
    
    def get_positions_by_strategy(self, strategy_id: str) -> List[Position]:
        """Get positions for a specific strategy."""
        return [p for p in self._positions.values() if p.strategy_id == strategy_id]
    
    async def update_position_price(
        self,
        position_id: str,
        new_price: Decimal
    ) -> Optional[Position]:
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
        self,
        position_id: str,
        exit_price: Decimal,
        exit_size: Optional[Decimal] = None
    ) -> Optional[Dict[str, Decimal]]:
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
        self,
        exchange_positions: List[Dict[str, Any]]
    ) -> Tuple[List[Position], List[Dict[str, Any]]]:
        """Reconcile local positions with exchange positions."""
        try:
            matched_positions = []
            unmatched_exchange: List[Dict[str, Any]] = []
            
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
                    if Decimal(str(exchange_pos['size'])) != position.size:
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
        return sum((p.notional_value for p in self.get_open_positions()), Decimal('0'))
    
    def get_exposure_by_market(self, market_slug: str) -> Decimal:
        """Get total exposure for a specific market."""
        positions = self.get_positions_by_market(market_slug)
        return sum((p.notional_value for p in positions if p.is_open), Decimal('0'))
    
    def get_pnl_summary(self) -> Dict[str, Decimal]:
        """Get P&L summary across all positions."""
        open_positions = self.get_open_positions()
        total_unrealized = sum((p.unrealized_pnl for p in open_positions), Decimal('0'))
        total_realized = sum((p.realized_pnl for p in self._positions.values()), Decimal('0'))
        total_fees = sum((p.fees for p in self._positions.values()), Decimal('0'))
        
        return {
            'total_unrealized_pnl': total_unrealized,
            'total_realized_pnl': total_realized,
            'total_fees': total_fees,
            'total_pnl': total_unrealized + total_realized - total_fees
        }