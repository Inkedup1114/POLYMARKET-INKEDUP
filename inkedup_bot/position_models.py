"""Position tracking models and data structures."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, Any
import uuid


class PositionStatus(Enum):
    """Enum representing the possible states of a position."""
    
    OPEN = "open"
    CLOSED = "closed"
    PARTIALLY_CLOSED = "partially_closed"
    LIQUIDATED = "liquidated"
    EXPIRED = "expired"
    PENDING = "pending"
    CANCELLED = "cancelled"


@dataclass
class Position:
    """Comprehensive position data structure for tracking all aspects of a trading position."""
    
    position_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    token_id: str = ""
    market_slug: str = ""
    outcome_type: str = ""  # "YES" or "NO"
    size: Decimal = field(default=Decimal('0'))
    notional_value: Decimal = field(default=Decimal('0'))
    average_price: Decimal = field(default=Decimal('0'))
    current_price: Decimal = field(default=Decimal('0'))
    unrealized_pnl: Decimal = field(default=Decimal('0'))
    realized_pnl: Decimal = field(default=Decimal('0'))
    fees: Decimal = field(default=Decimal('0'))
    status: PositionStatus = field(default=PositionStatus.OPEN)
    strategy_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate and normalize position data after initialization."""
        # Ensure decimal types
        self.size = Decimal(str(self.size))
        self.notional_value = Decimal(str(self.notional_value))
        self.average_price = Decimal(str(self.average_price))
        self.current_price = Decimal(str(self.current_price))
        self.unrealized_pnl = Decimal(str(self.unrealized_pnl))
        self.realized_pnl = Decimal(str(self.realized_pnl))
        self.fees = Decimal(str(self.fees))
        
        # Ensure status is enum
        if isinstance(self.status, str):
            self.status = PositionStatus(self.status)
    
    @property
    def is_open(self) -> bool:
        """Check if position is currently open."""
        return self.status in [PositionStatus.OPEN, PositionStatus.PARTIALLY_CLOSED]
    
    @property
    def total_pnl(self) -> Decimal:
        """Calculate total P&L (realized + unrealized)."""
        return self.realized_pnl + self.unrealized_pnl
    
    @property
    def pnl_percentage(self) -> Decimal:
        """Calculate P&L percentage based on notional value."""
        if self.notional_value == 0:
            return Decimal('0')
        return (self.total_pnl / self.notional_value) * 100
    
    def update_current_price(self, new_price: Decimal) -> None:
        """Update current price and recalculate unrealized P&L."""
        self.current_price = new_price
        self.unrealized_pnl = (new_price - self.average_price) * self.size
        self.updated_at = datetime.utcnow()
    
    def add_realized_pnl(self, pnl: Decimal, fees: Decimal = Decimal('0')) -> None:
        """Add realized P&L and fees to the position."""
        self.realized_pnl += pnl
        self.fees += fees
        self.updated_at = datetime.utcnow()
    
    def close_position(self, exit_price: Decimal, exit_size: Optional[Decimal] = None) -> Dict[str, Decimal]:
        """Close position and calculate final P&L."""
        if exit_size is None:
            exit_size = self.size
        
        # Calculate P&L for the closed portion
        pnl = (exit_price - self.average_price) * exit_size
        
        # Update position
        self.size -= exit_size
        self.realized_pnl += pnl
        self.updated_at = datetime.utcnow()
        
        if self.size == 0:
            self.status = PositionStatus.CLOSED
            self.closed_at = datetime.utcnow()
        else:
            self.status = PositionStatus.PARTIALLY_CLOSED
        
        return {
            'realized_pnl': pnl,
            'exit_size': exit_size,
            'remaining_size': self.size
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert position to dictionary for serialization."""
        return {
            'position_id': self.position_id,
            'token_id': self.token_id,
            'market_slug': self.market_slug,
            'outcome_type': self.outcome_type,
            'size': str(self.size),
            'notional_value': str(self.notional_value),
            'average_price': str(self.average_price),
            'current_price': str(self.current_price),
            'unrealized_pnl': str(self.unrealized_pnl),
            'realized_pnl': str(self.realized_pnl),
            'fees': str(self.fees),
            'status': self.status.value,
            'strategy_id': self.strategy_id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        """Create position from dictionary."""
        return cls(
            position_id=data['position_id'],
            token_id=data['token_id'],
            market_slug=data['market_slug'],
            outcome_type=data['outcome_type'],
            size=Decimal(data['size']),
            notional_value=Decimal(data['notional_value']),
            average_price=Decimal(data['average_price']),
            current_price=Decimal(data['current_price']),
            unrealized_pnl=Decimal(data['unrealized_pnl']),
            realized_pnl=Decimal(data['realized_pnl']),
            fees=Decimal(data['fees']),
            status=PositionStatus(data['status']),
            strategy_id=data.get('strategy_id'),
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at']),
            closed_at=datetime.fromisoformat(data['closed_at']) if data.get('closed_at') else None,
            metadata=data.get('metadata', {})
        )