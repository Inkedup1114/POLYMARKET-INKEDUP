"""
State management models for Polymarket trading system.

This module contains state tracking models for orders, positions, and market data
to maintain consistent state across the trading system.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any, Set
from pydantic import BaseModel, Field, validator
from dataclasses import dataclass, field


class OrderLifecycle(str, Enum):
    """Order lifecycle states."""
    PLACEMENT = "placement"
    UPDATE = "update"
    CANCELLATION = "cancellation"
    EXECUTION = "execution"


class PositionSide(str, Enum):
    """Position side enumeration."""
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class OrderState(BaseModel):
    """
    Track order lifecycle state.
    
    Represents the complete state of an order throughout its lifecycle,
    from placement through execution or cancellation.
    
    Example:
        OrderState(
            order_id="order123",
            market="0x123...",
            owner="0xuser1",
            price=Decimal("0.55"),
            size=Decimal("100.0"),
            side="buy",
            status="open",
            order_type="limit",
            lifecycle_stage="placement",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            filled_size=Decimal("0.0"),
            remaining_size=Decimal("100.0"),
            average_fill_price=None,
            transaction_hashes=[]
        )
    """
    order_id: str = Field(..., description="Unique order identifier")
    market: str = Field(..., description="Market contract address")
    owner: str = Field(..., description="Order owner address")
    price: Decimal = Field(..., description="Order price", ge=0, le=1)
    size: Decimal = Field(..., description="Original order size", gt=0)
    side: str = Field(..., description="Order side (buy/sell)")
    status: str = Field(..., description="Current order status")
    order_type: str = Field(..., description="Order type (limit/market)")
    lifecycle_stage: OrderLifecycle = Field(..., description="Current lifecycle stage")
    created_at: datetime = Field(..., description="Order creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    filled_size: Decimal = Field(default=Decimal("0"), description="Total filled size")
    remaining_size: Decimal = Field(..., description="Remaining size to fill")
    average_fill_price: Optional[Decimal] = Field(None, description="Average fill price")
    transaction_hashes: List[str] = Field(default_factory=list, description="Related transaction hashes")
    
    @validator('remaining_size')
    def validate_remaining_size(cls, v: Decimal, values: Dict[str, Any]) -> Decimal:
        """Validate remaining size is not greater than original size."""
        if 'size' in values and v > values['size']:
            raise ValueError("Remaining size cannot be greater than original size")
        return v
    
    @validator('filled_size')
    def validate_filled_size(cls, v: Decimal, values: Dict[str, Any]) -> Decimal:
        """Validate filled size is not greater than original size."""
        if 'size' in values and v > values['size']:
            raise ValueError("Filled size cannot be greater than original size")
        return v
    
    def update_fill(self, fill_size: Decimal, fill_price: Decimal) -> None:
        """
        Update order state with new fill information.
        
        Args:
            fill_size: Size of the new fill
            fill_price: Price of the new fill
        """
        if fill_size <= 0:
            raise ValueError("Fill size must be positive")
        
        new_filled_size = self.filled_size + fill_size
        if new_filled_size > self.size:
            raise ValueError("Total filled size cannot exceed original size")
        
        self.filled_size = new_filled_size
        self.remaining_size = self.size - new_filled_size
        
        # Calculate new average fill price
        if self.average_fill_price is None:
            self.average_fill_price = fill_price
        else:
            total_value = (self.filled_size - fill_size) * self.average_fill_price + fill_size * fill_price
            self.average_fill_price = total_value / self.filled_size
        
        self.updated_at = datetime.utcnow()
        
        # Update status based on fill
        if self.remaining_size == 0:
            self.status = "filled"
        elif self.filled_size > 0:
            self.status = "partially_filled"
    
    def cancel(self) -> None:
        """Mark order as cancelled."""
        self.status = "cancelled"
        self.updated_at = datetime.utcnow()
    
    def is_complete(self) -> bool:
        """Check if order is complete (filled or cancelled)."""
        return self.status in ["filled", "cancelled"]
    
    def is_active(self) -> bool:
        """Check if order is still active."""
        return self.status in ["open", "partially_filled"]
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: str(v)
        }


class PositionState(BaseModel):
    """
    Track position state with size and P&L.
    
    Represents the current state of a position in a specific market,
    including size, entry price, and unrealized P&L.
    
    Example:
        PositionState(
            market="0x123...",
            owner="0xuser1",
            side="long",
            size=Decimal("100.0"),
            entry_price=Decimal("0.55"),
            current_price=Decimal("0.57"),
            unrealized_pnl=Decimal("2.0"),
            realized_pnl=Decimal("0.0"),
            last_update=datetime.utcnow()
        )
    """
    market: str = Field(..., description="Market contract address")
    owner: str = Field(..., description="Position owner address")
    side: PositionSide = Field(..., description="Position side (long/short/flat)")
    size: Decimal = Field(..., description="Current position size", ge=0)
    entry_price: Decimal = Field(..., description="Average entry price", ge=0, le=1)
    current_price: Decimal = Field(..., description="Current market price", ge=0, le=1)
    unrealized_pnl: Decimal = Field(default=Decimal("0"), description="Unrealized P&L")
    realized_pnl: Decimal = Field(default=Decimal("0"), description="Realized P&L")
    last_update: datetime = Field(..., description="Last update timestamp")
    
    @validator('size')
    def validate_size(cls, v: Decimal) -> Decimal:
        """Validate size is non-negative."""
        if v < 0:
            raise ValueError("Position size cannot be negative")
        return v
    
    def update_price(self, new_price: Decimal) -> None:
        """
        Update position with new market price.
        
        Args:
            new_price: New market price
        """
        if new_price < 0 or new_price > 1:
            raise ValueError("Price must be between 0 and 1")
        
        self.current_price = new_price
        self.unrealized_pnl = self.calculate_unrealized_pnl()
        self.last_update = datetime.utcnow()
    
    def calculate_unrealized_pnl(self) -> Decimal:
        """Calculate unrealized P&L based on current price."""
        if self.size == 0:
            return Decimal("0")
        
        price_diff = self.current_price - self.entry_price
        
        if self.side == PositionSide.LONG:
            return price_diff * self.size
        elif self.side == PositionSide.SHORT:
            return -price_diff * self.size
        else:
            return Decimal("0")
    
    def add_fill(self, fill_size: Decimal, fill_price: Decimal, is_buy: bool) -> None:
        """
        Add a fill to the position.
        
        Args:
            fill_size: Size of the fill
            fill_price: Price of the fill
            is_buy: Whether this was a buy (True) or sell (False)
        """
        if fill_size <= 0:
            raise ValueError("Fill size must be positive")
        
        # Determine if this is opening or closing
        current_side = self.side
        new_side = self._calculate_new_side(current_side, fill_size, is_buy)
        
        # Calculate P&L for closing portion
        if (current_side == PositionSide.LONG and not is_buy) or \
           (current_side == PositionSide.SHORT and is_buy):
            # Closing position
            closing_size = min(fill_size, self.size)
            price_diff = fill_price - self.entry_price
            
            if current_side == PositionSide.LONG:
                pnl = price_diff * closing_size
            else:  # SHORT
                pnl = -price_diff * closing_size
            
            self.realized_pnl += pnl
            self.size -= closing_size
            
            if self.size == 0:
                self.side = PositionSide.FLAT
                self.entry_price = Decimal("0")
        
        # Handle opening portion
        if new_side != PositionSide.FLAT and new_side != current_side:
            # Opening new position
            self.side = new_side
            self.entry_price = fill_price
            self.size = fill_size - (self.size if current_side != PositionSide.FLAT else 0)
        
        self.unrealized_pnl = self.calculate_unrealized_pnl()
        self.last_update = datetime.utcnow()
    
    def _calculate_new_side(self, current_side: PositionSide, fill_size: Decimal, is_buy: bool) -> PositionSide:
        """Calculate new position side after fill."""
        if current_side == PositionSide.FLAT:
            return PositionSide.LONG if is_buy else PositionSide.SHORT
        
        if current_side == PositionSide.LONG:
            if is_buy:
                return PositionSide.LONG  # Adding to long
            else:
                if fill_size >= self.size:
                    return PositionSide.FLAT  # Closing long
                else:
                    return PositionSide.LONG  # Reducing long
        
        if current_side == PositionSide.SHORT:
            if not is_buy:
                return PositionSide.SHORT  # Adding to short
            else:
                if fill_size >= self.size:
                    return PositionSide.FLAT  # Closing short
                else:
                    return PositionSide.SHORT  # Reducing short
        
        return current_side
    
    def get_total_pnl(self) -> Decimal:
        """Get total P&L (realized + unrealized)."""
        return self.realized_pnl + self.unrealized_pnl
    
    def get_notional_value(self) -> Decimal:
        """Get current notional value of position."""
        return self.size * self.current_price
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: str(v)
        }


class MarketDataState(BaseModel):
    """
    Cache market data snapshots.
    
    Represents a snapshot of market data at a specific point in time,
    including order book, last trade price, and other market metrics.
    
    Example:
        MarketDataState(
            market="0x123...",
            timestamp=datetime.utcnow(),
            best_bid=Decimal("0.54"),
            best_ask=Decimal("0.56"),
            last_trade_price=Decimal("0.55"),
            bid_depth=Decimal("1000.0"),
            ask_depth=Decimal("800.0"),
            spread=Decimal("0.02"),
            mid_price=Decimal("0.55")
        )
    """
    market: str = Field(..., description="Market contract address")
    timestamp: datetime = Field(..., description="Snapshot timestamp")
    best_bid: Optional[Decimal] = Field(None, description="Best bid price")
    best_ask: Optional[Decimal] = Field(None, description="Best ask price")
    last_trade_price: Optional[Decimal] = Field(None, description="Last trade price")
    bid_depth: Decimal = Field(default=Decimal("0"), description="Total bid depth")
    ask_depth: Decimal = Field(default=Decimal("0"), description="Total ask depth")
    spread: Optional[Decimal] = Field(None, description="Bid-ask spread")
    mid_price: Optional[Decimal] = Field(None, description="Mid-market price")
    
    @validator('best_bid', 'best_ask', 'last_trade_price', 'spread', 'mid_price')
    def validate_price_range(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Validate price is within valid range."""
        if v is not None and (v < 0 or v > 1):
            raise ValueError("Price must be between 0 and 1")
        return v
    
    def update_from_book(self, bids: List[Dict[str, Decimal]], asks: List[Dict[str, Decimal]]) -> None:
        """
        Update market data from order book.
        
        Args:
            bids: List of bid levels with price and size
            asks: List of ask levels with price and size
        """
        if bids:
            self.best_bid = max(level['price'] for level in bids)
            self.bid_depth = Decimal(str(sum(level['size'] for level in bids)))
        else:
            self.best_bid = None
            self.bid_depth = Decimal("0")
        
        if asks:
            self.best_ask = min(level['price'] for level in asks)
            self.ask_depth = Decimal(str(sum(level['size'] for level in asks)))
        else:
            self.best_ask = None
            self.ask_depth = Decimal("0")
        
        if self.best_bid is not None and self.best_ask is not None:
            self.spread = self.best_ask - self.best_bid
            self.mid_price = (self.best_bid + self.best_ask) / 2
        else:
            self.spread = None
            self.mid_price = None
        
        self.timestamp = datetime.utcnow()
    
    def update_last_trade(self, price: Decimal) -> None:
        """
        Update last trade price.
        
        Args:
            price: Last trade price
        """
        self.last_trade_price = price
        self.timestamp = datetime.utcnow()
    
    def get_liquidity_metrics(self) -> Dict[str, Decimal]:
        """Get liquidity metrics for the market."""
        spread = self.spread or Decimal("0")
        mid_price = self.mid_price or Decimal("1")
        return {
            "bid_depth": self.bid_depth,
            "ask_depth": self.ask_depth,
            "total_depth": self.bid_depth + self.ask_depth,
            "spread": spread,
            "spread_bps": (spread / mid_price * 10000) if mid_price > 0 else Decimal("0")
        }
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: str(v)
        }


class TradingState(BaseModel):
    """
    Complete trading state for a user.
    
    Aggregates all state information for a specific user across all markets.
    """
    owner: str = Field(..., description="User address")
    orders: Dict[str, OrderState] = Field(default_factory=dict, description="Order ID to order state mapping")
    positions: Dict[str, PositionState] = Field(default_factory=dict, description="Market to position state mapping")
    market_data: Dict[str, MarketDataState] = Field(default_factory=dict, description="Market to market data mapping")
    last_update: datetime = Field(..., description="Last state update timestamp")
    
    def add_order(self, order: OrderState) -> None:
        """Add or update an order in the state."""
        self.orders[order.order_id] = order
        self.last_update = datetime.utcnow()
    
    def get_order(self, order_id: str) -> Optional[OrderState]:
        """Get order state by ID."""
        return self.orders.get(order_id)
    
    def remove_order(self, order_id: str) -> bool:
        """Remove an order from the state."""
        if order_id in self.orders:
            del self.orders[order_id]
            self.last_update = datetime.utcnow()
            return True
        return False
    
    def get_position(self, market: str) -> Optional[PositionState]:
        """Get position state for a market."""
        return self.positions.get(market)
    
    def add_position(self, position: PositionState) -> None:
        """Add or update a position in the state."""
        self.positions[position.market] = position
        self.last_update = datetime.utcnow()
    
    def get_market_data(self, market: str) -> Optional[MarketDataState]:
        """Get market data for a specific market."""
        return self.market_data.get(market)
    
    def add_market_data(self, market_data: MarketDataState) -> None:
        """Add or update market data in the state."""
        self.market_data[market_data.market] = market_data
        self.last_update = datetime.utcnow()
    
    def get_active_orders(self) -> List[OrderState]:
        """Get all active orders."""
        return [order for order in self.orders.values() if order.is_active()]
    
    def get_open_positions(self) -> List[PositionState]:
        """Get all open positions (non-flat)."""
        return [pos for pos in self.positions.values() if pos.side != PositionSide.FLAT and pos.size > 0]
    
    def get_total_exposure(self) -> Dict[str, Decimal]:
        """Get total exposure across all positions."""
        long_exposure = Decimal("0")
        short_exposure = Decimal("0")
        
        for position in self.positions.values():
            if position.side == PositionSide.LONG:
                long_exposure += position.get_notional_value()
            elif position.side == PositionSide.SHORT:
                short_exposure += position.get_notional_value()
        
        return {
            "long_exposure": long_exposure,
            "short_exposure": short_exposure,
            "net_exposure": long_exposure - short_exposure,
            "gross_exposure": long_exposure + short_exposure
        }
    
    def get_total_pnl(self) -> Decimal:
        """Get total P&L across all positions."""
        total = Decimal("0")
        for pos in self.positions.values():
            total += pos.get_total_pnl()
        return total
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: str(v)
        }


# State management utilities
class StateManager:
    """Utility class for managing trading state."""
    
    @staticmethod
    def create_initial_state(owner: str) -> TradingState:
        """Create initial trading state for a user."""
        return TradingState(
            owner=owner,
            last_update=datetime.utcnow()
        )
    
    @staticmethod
    def merge_states(states: List[TradingState]) -> TradingState:
        """
        Merge multiple trading states into one.
        
        Args:
            states: List of trading states to merge
            
        Returns:
            Merged trading state
        """
        if not states:
            raise ValueError("Cannot merge empty list of states")
        
        # Use the first state's owner
        merged = StateManager.create_initial_state(states[0].owner)
        
        for state in states:
            if state.owner != merged.owner:
                raise ValueError("Cannot merge states for different owners")
            
            # Merge orders (latest wins)
            merged.orders.update(state.orders)
            
            # Merge positions (latest wins)
            merged.positions.update(state.positions)
            
            # Merge market data (latest wins)
            merged.market_data.update(state.market_data)
        
        return merged