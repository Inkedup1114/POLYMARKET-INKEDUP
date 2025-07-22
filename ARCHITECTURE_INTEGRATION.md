# Integration Architecture Document

## Overview
This document provides the complete integration architecture for implementing the position tracking system and resilient retry logic with the existing codebase.

## 1. Configuration Management System

### Configuration Structure
```python
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class PositionConfig:
    """Configuration for position tracking system."""
    
    # Database settings
    database_path: str = "positions.db"
    enable_persistence: bool = True
    
    # Position calculation settings
    max_position_size: float = 10000.0  # Maximum USD position size
    min_position_size: float = 1.0      # Minimum USD position size
    position_precision: int = 4          # Decimal places for calculations
    
    # Risk settings
    max_drawdown_threshold: float = 0.10  # 10% max drawdown
    risk_score_threshold: float = 0.8     # Risk score threshold
    
    # Integration settings
    sync_interval: int = 30              # Seconds between syncs
    enable_real_time_updates: bool = True

@dataclass
class RetryConfig:
    """Configuration for retry logic system."""
    
    # Exponential backoff
    initial_delay: float = 1.0           # Initial delay in seconds
    max_delay: float = 60.0              # Maximum delay in seconds
    multiplier: float = 2.0            # Backoff multiplier
    jitter: bool = True                  # Add random jitter
    
    # Circuit breaker
    failure_threshold: int = 5           # Failures before opening
    recovery_timeout: int = 60           # Seconds before recovery attempt
    half_open_max_calls: int = 3         # Max calls in half-open state
    
    # Idempotency
    idempotency_ttl_hours: int = 24      # TTL for idempotency keys
    enable_idempotency: bool = True
    
    # Error handling
    max_retries: int = 3                 # Maximum retry attempts
    retryable_errors: list = None         # List of retryable error types

class ConfigManager:
    """Central configuration management."""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file
        self.position_config = PositionConfig()
        self.retry_config = RetryConfig()
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from file or environment variables."""
        # Implementation for loading from file/env
        pass
    
    def get_position_config(self) -> PositionConfig:
        """Get position tracking configuration."""
        return self.position_config
    
    def get_retry_config(self) -> RetryConfig:
        """Get retry logic configuration."""
        return self.retry_config
```

## 2. Integration with Order Client

### Enhanced Order Client
```python
from typing import Optional, Dict, Any
import asyncio
from dataclasses import asdict

class EnhancedOrderClient:
    """Enhanced order client with position tracking and retry logic."""
    
    def __init__(
        self,
        cfg: BotConfig,
        state: StateManager,
        position_manager: Optional[PositionManager] = None,
        retry_manager: Optional[RetryManager] = None
    ):
        self.cfg = cfg
        self.state = state
        self.position_manager = position_manager
        self.retry_manager = retry_manager or RetryManager()
        
        # Initialize components
        self.error_classifier = ErrorClassifier()
        self.idempotency_store = IdempotencyStore()
        
    async def place_limit(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        tif: str = "GTC",
        market_slug: Optional[str] = None,
        outcome_type: Optional[str] = None,
        notional_value: Optional[float] = None,
        risk: Any = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Enhanced order placement with retry logic and position tracking."""
        
        # Generate idempotency key
        idempotency_key = IdempotencyKeyGenerator.generate_for_order(
            token_id, side, price, size
        )
        
        # Check for existing operation
        existing = await self.idempotency_store.get(idempotency_key)
        if existing and existing.status == "completed":
            logger.info(f"Returning cached result for idempotency key: {idempotency_key}")
            return existing.response_data
        
        # Define retryable operation
        async def _place_order():
            return await self._execute_order_placement(
                token_id, side, price, size, tif, market_slug, 
                outcome_type, notional_value, risk, **kwargs
            )
        
        # Execute with retry and circuit breaker
        try:
            result = await self.retry_manager.execute_with_retry(
                _place_order,
                operation_id=idempotency_key,
                context={
                    "token_id": token_id,
                    "side": side,
                    "price": price,
                    "size": size
                }
            )
            
            # Create position from successful order
            if result and result.get("status") == "FILLED":
                await self._create_position_from_order(
                    result, token_id, market_slug, outcome_type, notional_value
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            raise
    
    async def _execute_order_placement(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        tif: str,
        market_slug: Optional[str],
        outcome_type: Optional[str],
        notional_value: Optional[float],
        risk: Any,
        **kwargs
    ) -> Dict[str, Any]:
        """Core order placement logic."""
        
        if not self.ready():
            raise UnavailableClientError("Trading functionality not available")
        
        # Validate parameters
        if price <= 0 or size <= 0:
            raise ValueError("Invalid price/size")
        
        # Create order
        order_args = OrderArgs(
            price=round(price, 4),
            size=round(size, 4),
            side=side.lower(),
            token_id=token_id,
        )
        
        # Execute with timeout
        order = await self._execute_with_timeout(
            lambda: self.client.create_order(order_args),
            timeout=30.0
        )
        
        if order:
            order_dict = asdict(order)
            logger.info(
                f"Placed {side.upper()} size={size} price={price} token={token_id} id={order_dict.get('id')}"
            )
            
            # Update state
            await self.state.add_order_async(order_dict)
            
            # Record trade in risk manager
            if risk and notional_value is not None:
                await self._record_trade_async(
                    token_id, notional_value, market_slug, outcome_type
                )
            
            return order_dict
        
        return None
    
    async def _create_position_from_order(
        self,
        order_data: Dict[str, Any],
        token_id: str,
        market_slug: Optional[str],
        outcome_type: Optional[str],
        notional_value: Optional[float]
    ) -> None:
        """Create position from successful order."""
        
        if not self.position_manager:
            return
            
        position_data = {
            "position_id": f"pos_{order_data['id']}",
            "token_id": token_id,
            "market_slug": market_slug,
            "outcome_type": outcome_type,
            "side": order_data.get("side", "buy"),
            "size": order_data.get("size", 0),
            "notional_value": notional_value or 0,
            "average_price": order_data.get("price", 0),
            "current_price": order_data.get("price", 0),
            "parent_order_id": order_data["id"]
        }
        
        await self.position_manager.create_position(position_data)
```

## 3. Integration with Exposure Tracker

### Position-Exposure Bridge
```python
class PositionExposureBridge:
    """Bridge between position tracking and exposure tracking systems."""
    
    def __init__(
        self,
        position_manager: PositionManager,
        exposure_tracker: RealTimeExposureTracker
    ):
        self.position_manager = position_manager
        self.exposure_tracker = exposure_tracker
        
    async def initialize(self) -> None:
        """Initialize the bridge with event listeners."""
        
        # Listen for position events
        self.position_manager.event_bus.on("position_created", self._on_position_created)
        self.position_manager.event_bus.on("position_updated", self._on_position_updated)
        self.position_manager.event_bus.on("position_closed", self._on_position_closed)
        
    async def sync_all_positions(self) -> None:
        """Synchronize all positions between systems."""
        
        positions = await self.position_manager.get_all_positions()
        
        for position in positions:
            if position.is_open:
                await self._sync_position_to_exposure(position)
    
    async def _sync_position_to_exposure(self, position: Position) -> None:
        """Sync a single position to exposure tracker."""
        
        update = PositionUpdate(
            token_id=position.token_id,
            size=position.size,
            price=position.current_price,
            notional_value=position.notional_value,
            timestamp=datetime.utcnow().timestamp(),
            market_slug=position.market_slug,
            outcome_type=position.outcome_type
        )
        
        await self.exposure_tracker.add_position_update(update)
    
    async def _on_position_created(self, position: Position) -> None:
        """Handle position creation event."""
        await self._sync_position_to_exposure(position)
    
    async def _on_position_updated(self, position: Position) -> None:
        """Handle position update event."""
        await self._sync_position_to_exposure(position)
    
    async def _on_position_closed(self, position: Position) -> None:
        """Handle position closure event."""
        # Send zero-size update to exposure tracker
        update = PositionUpdate(
            token_id=position.token_id,
            size=0.0,
            price=position.current_price,
            not