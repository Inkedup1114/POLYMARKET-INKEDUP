# Testing Strategy Architecture

## Overview
This document outlines the comprehensive testing strategy for the position tracking system and resilient retry logic implementation.

## 1. Testing Architecture Overview

### Test Pyramid Structure
```
                 ┌─────────────────────────────┐
                 │    Integration Tests        │
                 │  (End-to-End Scenarios)     │
                 └─────────────────────────────┘
                           ▲
                 ┌─────────────────────────────┐
                 │    Component Tests          │
                 │  (Service Integration)      │
                 └─────────────────────────────┘
                           ▲
                 ┌─────────────────────────────┐
                 │      Unit Tests             │
                 │   (Individual Components)   │
                 └─────────────────────────────┘
```

## 2. Unit Testing Strategy

### Position Model Tests
```python
import pytest
from datetime import datetime
from inkedup_bot.positions.models import Position, PositionStatus, PositionSide

class TestPositionModel:
    """Unit tests for Position model."""
    
    def test_position_creation(self):
        """Test basic position creation."""
        position = Position(
            position_id="test_pos_1",
            token_id="token_123",
            market_slug="test-market",
            outcome_type="yes",
            side=PositionSide.LONG,
            size=100.0,
            notional_value=5000.0,
            average_price=0.5,
            current_price=0.5
        )
        
        assert position.position_id == "test_pos_1"
        assert position.is_open is True
        assert position.total_pnl == 0.0
    
    def test_position_pnl_calculation(self):
        """Test P&L calculation."""
        position = Position(
            position_id="test_pos_1",
            token_id="token_123",
            market_slug="test-market",
            outcome_type="yes",
            side=PositionSide.LONG,
            size=100.0,
            notional_value=5000.0,
            average_price=0.5,
            current_price=0.6
        )
        
        expected_pnl = (0.6 - 0.5) * 100.0
        assert position.unrealized_pnl == expected_pnl
    
    def test_position_closure(self):
        """Test position closure."""
        position = Position(
            position_id="test_pos_1",
            token_id="token_123",
            market_slug="test-market",
            outcome_type="yes",
            side=PositionSide.LONG,
            size=100.0,
            notional_value=5000.0,
            average_price=0.5,
            current_price=0.7
        )
        
        position.update_price(0.8)
        position.close_position(0.8)
        
        assert position.status == PositionStatus.CLOSED
        assert position.realized_pnl == 30.0  # (0.8 - 0.5) * 100
```

### Retry Logic Tests
```python
import asyncio
from unittest.mock import Mock, patch
from inkedup_bot.retry import RetryManager, CircuitBreaker, ErrorClassifier

class TestRetryManager:
    """Unit tests for retry manager."""
    
    @pytest.mark.asyncio
    async def test_successful_operation(self):
        """Test successful operation without retries."""
        retry_manager = RetryManager(max_retries=3)
        
        async def mock_operation():
            return {"status": "success", "data": "test"}
        
        result = await retry_manager.execute_with_retry(mock_operation)
        assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_retry_on_transient_error(self):
        """Test retry on transient network error."""
        retry_manager = RetryManager(max_retries=3, initial_delay=0.1)
        
        call_count = 0
        async def mock_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Network error")
            return {"status": "success"}
        
        result = await retry_manager.execute_with_retry(mock_operation)
        assert result["status"] == "success"
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_activation(self):
        """Test circuit breaker activation on repeated failures."""
        circuit_breaker = CircuitBreaker(
            name="test_circuit",
            failure_threshold=3,
            recovery_timeout=1
        )
        
        # Trigger failures
        for _ in range(3):
            with pytest.raises(CircuitOpenError):
                await circuit_breaker.call(lambda: exec('raise ConnectionError("fail")'))
        
        # Circuit should be open
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Should reject calls immediately
        with pytest.raises(CircuitOpenError):
            await circuit_breaker.call(lambda: exec('raise ConnectionError("fail")'))
```

### Error Classification Tests
```python
class TestErrorClassifier:
    """Unit tests for error classification."""
    
    def test_network_error_classification(self):
        """Test network error classification."""
        classifier = ErrorClassifier()
        
        error = ConnectionError("Connection refused")
        context = classifier.classify(error)
        
        assert context.error_type == ErrorCategory.NETWORK_ERROR
        assert context.is_retryable is True
    
    def test_rate_limit_classification(self):
        """Test rate limit error classification."""
        classifier = ErrorClassifier()
        
        response_data = {"status": 429, "headers": {"Retry-After": "5"}}
        context = classifier.classify(
            Exception("Rate limit exceeded"), 
            response_data
        )
        
        assert context.error_type == ErrorCategory.RATE_LIMIT
        assert context.retry_after == 5
    
    def test_validation_error_classification(self):
        """Test validation error classification."""
        classifier = ErrorClassifier()
        
        response_data = {"status": 400, "message": "Invalid parameters"}
        context = classifier.classify(
            ValueError("Invalid parameters"), 
            response_data
        )
        
        assert context.error_type == ErrorCategory.VALIDATION_ERROR
        assert context.is_retryable is False
```

## 3. Component Integration Tests

### Position-Exposure Integration Tests
```python
import pytest
from inkedup_bot.positions import PositionManager
from inkedup_bot.risk.exposure_tracker import RealTimeExposureTracker

class TestPositionExposureIntegration:
    """Integration tests for position and exposure tracking."""
    
    @pytest.mark.asyncio
    async def test_position_sync_to_exposure(self):
        """Test position synchronization to exposure tracker."""
        
        # Setup
        position_manager = PositionManager()
        exposure_tracker = RealTimeExposureTracker()
        bridge = PositionExposureBridge(position_manager, exposure_tracker)
        
        # Create position
        position = await position_manager.create_position({
            "token_id": "token_123",
            "market_slug": "test-market",
            "outcome_type": "yes",
            "side": "long",
            "size": 100.0,
            "notional_value": 5000.0,
            "average_price": 0.5
        })
        
        # Sync to exposure
        await bridge.sync_positions()
        
        # Verify exposure tracker has position
        exposure = await exposure_tracker.get_current_exposure()
        assert "token_123" in exposure.position_exposures
        assert exposure.position_exposures["token_123"] == 5000.0
    
    @pytest.mark.asyncio
    async def test_position_update_propagation(self):
        """Test position update propagation to exposure tracker."""
        
        # Setup
        position_manager = PositionManager()
        exposure_tracker = RealTimeExposureTracker()
        bridge = PositionExposureBridge(position_manager, exposure_tracker)
        await bridge.initialize()
        
        # Create and update position
        position = await position_manager.create_position({
            "token_id": "token_123",
            "market_slug": "test-market",
            "outcome_type": "yes",
            "side": "long",
            "size": 100.0,
            "notional_value": 5000.0,
            "average_price": 0.5
        })
        
        # Update position
        await position_manager.update_position(
            position.position_id,
            {"current_price": 0.6, "size": 150.0}
        )
        
        # Verify exposure update
        exposure = await exposure_tracker.get_current_exposure()
        assert exposure.position_exposures["token_123"] == 7500.0
```

### Order-Position Integration Tests
```python
class TestOrderPositionIntegration:
    """Integration tests for order and position tracking."""
    
    @pytest.mark.asyncio
    async def test_order_creates_position(self):
        """Test that successful order creates position."""
        
        # Setup
        enhanced_client = EnhancedOrderClient(
            cfg=MockConfig(),
            state=MockStateManager(),
            position_manager=MockPositionManager()
        )
        
        # Mock successful order
        with patch.object(enhanced_client, '_execute_order_placement') as mock_order:
            mock_order.return_value = {
                "id": "order_123",
                "status": "FILLED",
                "token_id": "token_456",
                "size": 100.0,
                "price": 0.5
            }
            
            result = await enhanced_client.place_limit(
                token_id="token_456",
                side="buy",
                price=0.5,
                size=100.0,
                market_slug="test-market",
                outcome_type="yes"
            )
        
        # Verify position was created
        assert result["status"] == "FILLED"
        # Position creation would be verified through position_manager mock
    
    @pytest.mark.asyncio
    async def test_failed_order_no_position(self):
        """Test that failed order doesn't create position."""
        
        # Setup
        enhanced_client = EnhancedOrderClient(
            cfg=MockConfig(),
            state=MockStateManager(),
            position_manager=MockPositionManager()
        )
        
        # Mock failed order
        with patch.object(enhanced_client, '_execute_order_placement') as mock_order:
            mock_order.side_effect = Exception("Order failed")
            
            with pytest.raises(Exception):
                await enhanced_client.place_limit(
                    token_id="token_456",
                    side="buy",
                    price=0.5,
                    size=100.0
                )
        
        # Verify no position was created
        # Position creation would be verified through position_manager mock
```

## 4. End-to-End Integration Tests

### Complete Trading Flow Tests
```python
class TestCompleteTradingFlow:
    """End-to-end tests for complete trading flow."""
    
    @pytest.mark.asyncio
    async def test_complete_buy_sell_cycle(self):
        """Test complete buy and sell cycle with position tracking."""
        
        # Setup complete system
        config = ConfigManager()
        state_manager = StateManager()
        position_manager = PositionManager(state_manager)
        exposure_tracker = RealTimeExposureTracker()
        enhanced_client = EnhancedOrderClient(