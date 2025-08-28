"""
Tests for Connection Pool Optimization

Comprehensive test suite for the dynamic connection pool optimization system.
Tests cover activity monitoring, scaling decisions, market activity detection,
and integration with existing connection pools.
"""

import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from inkedup_bot.dynamic_connection_optimizer import (
    DynamicConnectionOptimizer,
    MarketActivityLevel,
    MarketMetrics,
    OptimizerConfig,
    PeakHoursDetector,
    PoolSizingDecision,
    ScalingDecision,
    VolatilityDetector,
    create_connection_optimizer,
)
from inkedup_bot.optimized_connection_pool import (
    OptimizedConnectionPoolManager,
    create_optimized_pool_manager,
    get_recommended_pool_sizes,
)


@pytest.fixture
def optimizer_config():
    """Create test configuration for optimizer."""
    return OptimizerConfig(
        base_min_connections=2,
        base_max_connections=10,
        scale_up_utilization=0.7,
        scale_down_utilization=0.3,
        min_scale_interval=30,  # Shorter for testing
        max_daily_scales=5,
        enable_monitoring=False,  # Disable for controlled testing
    )


@pytest.fixture
def optimizer(optimizer_config):
    """Create optimizer instance for testing."""
    return DynamicConnectionOptimizer(optimizer_config)


@pytest.fixture
def mock_pool():
    """Create mock connection pool for testing."""
    pool = Mock()
    pool.min_size = 5
    pool.max_size = 15

    # Mock stats
    stats = Mock()
    stats.current_connections_in_use = 3
    stats.current_idle_connections = 2
    stats.average_response_time_ms = 100.0
    stats.total_failed_connections = 0
    pool.stats = stats

    return pool


class TestDynamicConnectionOptimizer:
    """Test the core optimizer functionality."""

    def test_initialization(self, optimizer_config):
        """Test optimizer initialization."""
        optimizer = DynamicConnectionOptimizer(optimizer_config)

        assert optimizer.config == optimizer_config
        assert len(optimizer._pool_references) == 0
        assert len(optimizer._current_configs) == 0
        assert not optimizer._shutdown

    def test_register_pool(self, optimizer, mock_pool):
        """Test pool registration."""
        pool_id = "test_pool"

        optimizer.register_pool(pool_id, mock_pool, 5, 15)

        assert pool_id in optimizer._pool_references
        assert optimizer._pool_references[pool_id] == mock_pool
        assert optimizer._current_configs[pool_id]["min_size"] == 5
        assert optimizer._current_configs[pool_id]["max_size"] == 15

    def test_update_activity_metrics(self, optimizer):
        """Test activity metrics updates."""
        optimizer.update_activity_metrics(
            signals_count=10,
            orders_count=5,
            websocket_messages_count=100,
            market_data_requests_count=20,
        )

        assert optimizer._activity_counters["signals"] == 10
        assert optimizer._activity_counters["orders"] == 5
        assert optimizer._activity_counters["websocket_messages"] == 100
        assert optimizer._activity_counters["market_data_requests"] == 20

    def test_collect_system_metrics(self, optimizer, mock_pool):
        """Test system metrics collection."""
        pool_id = "test_pool"
        optimizer.register_pool(pool_id, mock_pool, 5, 15)

        # Set up activity
        optimizer.update_activity_metrics(signals_count=60, orders_count=30)

        metrics = optimizer.collect_system_metrics(pool_id)

        assert isinstance(metrics, MarketMetrics)
        assert metrics.signals_per_minute > 0
        assert metrics.orders_per_minute > 0
        assert metrics.connection_pool_utilization == 0.6  # 3 in use / 5 total
        assert metrics.average_response_time_ms == 100.0

    def test_determine_market_activity_level(self, optimizer):
        """Test market activity level determination."""
        # Test dormant activity
        metrics = MarketMetrics(
            signals_per_minute=2.0,
            orders_per_minute=1.0,
            websocket_messages_per_minute=1.0,
            market_data_requests_per_minute=1.0,
        )
        level = optimizer.determine_market_activity_level(metrics)
        assert level == MarketActivityLevel.DORMANT

        # Test critical activity
        metrics = MarketMetrics(
            signals_per_minute=200.0,
            orders_per_minute=150.0,
            websocket_messages_per_minute=500.0,
            market_data_requests_per_minute=300.0,
            news_event_active=True,
        )
        level = optimizer.determine_market_activity_level(metrics)
        assert level == MarketActivityLevel.CRITICAL

        # Test volatile activity
        metrics = MarketMetrics(
            signals_per_minute=300.0,
            orders_per_minute=250.0,
            websocket_messages_per_minute=600.0,
            market_data_requests_per_minute=200.0,
            volatility_index=2.5,  # Below critical threshold of 3.0
        )
        level = optimizer.determine_market_activity_level(metrics)
        assert level == MarketActivityLevel.VOLATILE

    def test_calculate_optimal_pool_size_scale_up(self, optimizer, mock_pool):
        """Test pool sizing calculation for scale up scenario."""
        pool_id = "test_pool"
        optimizer.register_pool(pool_id, mock_pool, 5, 15)

        # High utilization metrics
        metrics = MarketMetrics(
            signals_per_minute=150.0,
            orders_per_minute=100.0,
            connection_pool_utilization=0.85,  # High utilization
            average_response_time_ms=200.0,  # Poor response time
            is_market_hours=True,
        )

        activity_level = MarketActivityLevel.HIGH
        decision = optimizer.calculate_optimal_pool_size(
            pool_id, metrics, activity_level
        )

        assert isinstance(decision, PoolSizingDecision)
        assert decision.decision in [
            ScalingDecision.SCALE_UP,
            ScalingDecision.EMERGENCY_SCALE,
        ]
        assert decision.recommended_min_size > decision.current_min_size
        assert decision.recommended_max_size > decision.current_max_size
        assert decision.priority >= 3

    def test_calculate_optimal_pool_size_scale_down(self, optimizer, mock_pool):
        """Test pool sizing calculation for scale down scenario."""
        pool_id = "test_pool"
        optimizer.register_pool(pool_id, mock_pool, 10, 25)  # Larger current size

        # Low utilization metrics
        metrics = MarketMetrics(
            signals_per_minute=5.0,
            orders_per_minute=2.0,
            connection_pool_utilization=0.2,  # Low utilization
            average_response_time_ms=30.0,  # Good response time
            is_market_hours=False,
            is_weekend=True,
        )

        activity_level = MarketActivityLevel.DORMANT
        decision = optimizer.calculate_optimal_pool_size(
            pool_id, metrics, activity_level
        )

        assert decision.decision == ScalingDecision.SCALE_DOWN
        assert decision.recommended_min_size < decision.current_min_size
        assert decision.recommended_max_size < decision.current_max_size
        assert decision.priority <= 2

    def test_should_apply_scaling_decision_constraints(self, optimizer, mock_pool):
        """Test scaling decision constraints."""
        pool_id = "test_pool"
        optimizer.register_pool(pool_id, mock_pool, 5, 15)

        # Create decision
        decision = PoolSizingDecision(
            current_min_size=5,
            current_max_size=15,
            recommended_min_size=7,
            recommended_max_size=18,
            decision=ScalingDecision.SCALE_UP,
            confidence=0.8,
            rationale="Test scaling",
            priority=3,
        )

        # Should apply initially
        assert optimizer.should_apply_scaling_decision(pool_id, decision)

        # Set recent scaling to block
        optimizer._last_scaling_decision[pool_id] = time.time() - 10  # 10 seconds ago
        assert not optimizer.should_apply_scaling_decision(pool_id, decision)

        # Emergency scaling should override timing constraints
        decision.decision = ScalingDecision.EMERGENCY_SCALE
        assert optimizer.should_apply_scaling_decision(pool_id, decision)

    def test_should_apply_scaling_decision_daily_limits(self, optimizer, mock_pool):
        """Test daily scaling limits."""
        pool_id = "test_pool"
        optimizer.register_pool(pool_id, mock_pool, 5, 15)

        # Hit daily limit
        optimizer._daily_scale_count[pool_id] = optimizer.config.max_daily_scales

        decision = PoolSizingDecision(
            current_min_size=5,
            current_max_size=15,
            recommended_min_size=8,
            recommended_max_size=20,
            decision=ScalingDecision.SCALE_UP,
            confidence=0.9,
            rationale="Test scaling",
            priority=3,
        )

        # Should be blocked by daily limit
        assert not optimizer.should_apply_scaling_decision(pool_id, decision)

        # Emergency scaling should override daily limits
        decision.decision = ScalingDecision.EMERGENCY_SCALE
        assert optimizer.should_apply_scaling_decision(pool_id, decision)

    @pytest.mark.asyncio
    async def test_apply_scaling_decision(self, optimizer, mock_pool):
        """Test applying scaling decisions."""
        pool_id = "test_pool"
        optimizer.register_pool(pool_id, mock_pool, 5, 15)

        decision = PoolSizingDecision(
            current_min_size=5,
            current_max_size=15,
            recommended_min_size=7,
            recommended_max_size=18,
            decision=ScalingDecision.SCALE_UP,
            confidence=0.8,
            rationale="Test scaling",
            priority=3,
        )

        result = await optimizer.apply_scaling_decision(pool_id, decision)

        assert result is True
        assert mock_pool.min_size == 7
        assert mock_pool.max_size == 18
        assert optimizer._current_configs[pool_id]["min_size"] == 7
        assert optimizer._current_configs[pool_id]["max_size"] == 18
        assert pool_id in optimizer._last_scaling_decision
        assert optimizer._daily_scale_count[pool_id] == 1

    @pytest.mark.asyncio
    async def test_optimize_pool_sizes_end_to_end(self, optimizer, mock_pool):
        """Test complete optimization cycle."""
        pool_id = "test_pool"
        optimizer.register_pool(pool_id, mock_pool, 5, 15)

        # Set up high activity
        optimizer.update_activity_metrics(
            signals_count=300, orders_count=150, websocket_messages_count=800
        )

        # Run optimization
        decisions = await optimizer.optimize_pool_sizes()

        assert pool_id in decisions
        decision = decisions[pool_id]
        assert isinstance(decision, PoolSizingDecision)

        # Activity counters should be reset
        assert sum(optimizer._activity_counters.values()) == 0


class TestVolatilityDetector:
    """Test volatility detection functionality."""

    def test_volatility_calculation(self):
        """Test volatility index calculation."""
        detector = VolatilityDetector()

        # Add consistent activity (low volatility)
        for _ in range(10):
            detector.calculate_volatility_index(50.0, 25.0)

        volatility = detector.calculate_volatility_index(52.0, 26.0)
        assert volatility < 2.0  # Low volatility

        # Add spike (high volatility)
        volatility = detector.calculate_volatility_index(200.0, 100.0)
        assert volatility > 2.0  # High volatility (adjusted expectation)


class TestPeakHoursDetector:
    """Test peak hours detection."""

    def test_market_hours_detection(self):
        """Test market hours detection."""
        detector = PeakHoursDetector()

        # Test weekday market hours
        market_time = datetime(2024, 1, 15, 14, 30)  # Monday 2:30 PM UTC
        assert detector.is_market_hours(market_time) is True

        # Test weekday off-hours
        off_hours_time = datetime(2024, 1, 15, 6, 30)  # Monday 6:30 AM UTC
        assert detector.is_market_hours(off_hours_time) is False

        # Test weekend
        weekend_time = datetime(2024, 1, 13, 14, 30)  # Saturday 2:30 PM UTC
        assert detector.is_market_hours(weekend_time) is False


class TestOptimizedConnectionPoolManager:
    """Test the optimized connection pool manager."""

    @pytest.mark.asyncio
    async def test_initialization_with_optimization(self):
        """Test pool manager initialization with optimization enabled."""
        manager = OptimizedConnectionPoolManager(
            database_url="sqlite:///test.db",
            enable_optimization=True,
            aggressive_scaling=False,
        )

        assert manager.enable_optimization is True
        assert manager.optimizer is not None
        assert not manager._optimization_started

    @pytest.mark.asyncio
    async def test_initialization_without_optimization(self):
        """Test pool manager initialization with optimization disabled."""
        manager = OptimizedConnectionPoolManager(
            database_url="sqlite:///test.db", enable_optimization=False
        )

        assert manager.enable_optimization is False
        assert manager.optimizer is None

    def test_update_activity_metrics(self):
        """Test activity metrics updates in pool manager."""
        manager = OptimizedConnectionPoolManager(
            database_url="sqlite:///test.db", enable_optimization=True
        )

        manager.update_activity_metrics(
            signals_count=10, orders_count=5, websocket_messages_count=50
        )

        # Should not raise errors
        assert True

    def test_get_optimization_status_disabled(self):
        """Test optimization status when disabled."""
        manager = OptimizedConnectionPoolManager(
            database_url="sqlite:///test.db", enable_optimization=False
        )

        status = manager.get_optimization_status()

        assert status["optimization_enabled"] is False
        assert status["status"] == "disabled"

    def test_get_optimization_status_enabled(self):
        """Test optimization status when enabled."""
        manager = OptimizedConnectionPoolManager(
            database_url="sqlite:///test.db", enable_optimization=True
        )

        status = manager.get_optimization_status()

        assert status["optimization_enabled"] is True
        assert "optimizer_stats" in status
        assert "pool_status" in status
        assert "last_updated" in status


class TestFactoryFunctions:
    """Test factory functions and utilities."""

    def test_create_connection_optimizer(self):
        """Test optimizer factory function."""
        optimizer = create_connection_optimizer(
            aggressive_scaling=True, enable_monitoring=False
        )

        assert isinstance(optimizer, DynamicConnectionOptimizer)
        assert optimizer.config.aggressive_scaling is True
        assert optimizer.config.enable_monitoring is False

    def test_create_optimized_pool_manager(self):
        """Test pool manager factory function."""
        manager = create_optimized_pool_manager(
            database_url="sqlite:///test.db",
            enable_optimization=True,
            aggressive_scaling=False,
        )

        assert isinstance(manager, OptimizedConnectionPoolManager)
        assert manager.enable_optimization is True

    def test_get_recommended_pool_sizes_sqlite(self):
        """Test recommended pool sizes for SQLite."""
        sizes = get_recommended_pool_sizes("sqlite")

        assert sizes["min_size"] == 2
        assert sizes["max_size"] == 12  # SQLite limit
        assert sizes["pool_size"] == 6
        assert sizes["max_size"] <= 12  # Ensure SQLite concurrency limit

    def test_get_recommended_pool_sizes_postgresql(self):
        """Test recommended pool sizes for PostgreSQL."""
        sizes = get_recommended_pool_sizes("postgresql")

        assert sizes["min_size"] == 3
        assert sizes["max_size"] == 30  # Higher for PostgreSQL
        assert sizes["pool_size"] == 12
        assert sizes["max_size"] > 15  # Should be higher than SQLite


@pytest.mark.asyncio
class TestIntegrationScenarios:
    """Integration tests for real-world scenarios."""

    async def test_high_activity_scaling(self):
        """Test scaling behavior during high activity periods."""
        config = OptimizerConfig(
            base_min_connections=3,
            base_max_connections=12,
            scale_up_utilization=0.6,
            min_scale_interval=1,  # Fast scaling for test
            enable_monitoring=False,
        )

        optimizer = DynamicConnectionOptimizer(config)

        # Mock pool with high utilization
        mock_pool = Mock()
        mock_pool.min_size = 5
        mock_pool.max_size = 15

        stats = Mock()
        stats.current_connections_in_use = 12  # High usage
        stats.current_idle_connections = 3
        stats.average_response_time_ms = 250.0  # Poor response time
        mock_pool.stats = stats

        pool_id = "high_activity_pool"
        optimizer.register_pool(pool_id, mock_pool, 5, 15)

        # Simulate high activity
        optimizer.update_activity_metrics(
            signals_count=600,  # Very high
            orders_count=300,
            websocket_messages_count=1200,
        )

        # Run optimization
        decisions = await optimizer.optimize_pool_sizes()

        assert pool_id in decisions
        decision = decisions[pool_id]

        # Should decide to scale up
        assert decision.decision in [
            ScalingDecision.SCALE_UP,
            ScalingDecision.EMERGENCY_SCALE,
        ]
        assert decision.recommended_max_size > decision.current_max_size
        assert decision.priority >= 3

    async def test_low_activity_scaling_down(self):
        """Test scaling down during low activity periods."""
        config = OptimizerConfig(
            base_min_connections=2,
            base_max_connections=20,
            scale_down_utilization=0.4,
            min_scale_interval=1,
            enable_monitoring=False,
        )

        optimizer = DynamicConnectionOptimizer(config)

        # Mock pool with low utilization
        mock_pool = Mock()
        mock_pool.min_size = 8  # Currently large
        mock_pool.max_size = 25

        stats = Mock()
        stats.current_connections_in_use = 1  # Very low usage
        stats.current_idle_connections = 7
        stats.average_response_time_ms = 20.0  # Excellent response time
        mock_pool.stats = stats

        pool_id = "low_activity_pool"
        optimizer.register_pool(pool_id, mock_pool, 8, 25)

        # Simulate low activity (weekend, off-hours)
        optimizer.update_activity_metrics(
            signals_count=2, orders_count=1, websocket_messages_count=5  # Very low
        )

        # Run optimization
        decisions = await optimizer.optimize_pool_sizes()

        assert pool_id in decisions
        decision = decisions[pool_id]

        # Should decide to scale down
        assert decision.decision == ScalingDecision.SCALE_DOWN
        assert decision.recommended_min_size < decision.current_min_size
        assert decision.recommended_max_size < decision.current_max_size
        assert decision.priority <= 2

    async def test_emergency_scaling_scenario(self):
        """Test emergency scaling during extreme conditions."""
        config = OptimizerConfig(
            emergency_utilization=0.85,
            min_scale_interval=60,  # Normally blocks frequent scaling
            enable_monitoring=False,
        )

        optimizer = DynamicConnectionOptimizer(config)

        # Mock pool at emergency utilization
        mock_pool = Mock()
        mock_pool.min_size = 10
        mock_pool.max_size = 20

        stats = Mock()
        stats.current_connections_in_use = 18  # 90% utilization
        stats.current_idle_connections = 2
        stats.average_response_time_ms = 800.0  # Very poor response
        mock_pool.stats = stats

        pool_id = "emergency_pool"
        optimizer.register_pool(pool_id, mock_pool, 10, 20)

        # Block normal scaling with recent decision
        optimizer._last_scaling_decision[pool_id] = time.time() - 30  # 30 seconds ago

        # Simulate critical activity
        optimizer.update_activity_metrics(
            signals_count=1000,  # Critical
            orders_count=800,
            websocket_messages_count=2000,
        )

        # Run optimization
        decisions = await optimizer.optimize_pool_sizes()

        decision = decisions[pool_id]

        # Should trigger emergency scaling despite recent scaling
        assert decision.decision == ScalingDecision.EMERGENCY_SCALE
        assert decision.priority == 5

        # Should apply despite timing constraints
        should_apply = optimizer.should_apply_scaling_decision(pool_id, decision)
        assert should_apply is True
