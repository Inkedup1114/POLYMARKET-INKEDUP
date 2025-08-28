"""
Tests for Signal Pipeline Optimization

Comprehensive test suite for the optimized parallel signal processing system.
Tests cover priority queuing, batch processing, circuit breaker, and performance
monitoring functionality.
"""

import asyncio
import time
from typing import List
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from inkedup_bot.signal_pipeline_optimizer import (
    OptimizedSignalWrapper,
    PipelineConfig,
    PipelineMetrics,
    SignalPipelineOptimizer,
    SignalPriority,
    create_optimized_pipeline,
)
from inkedup_bot.signals import TradingSignal


@pytest.fixture
def mock_signal():
    """Create a mock trading signal for testing."""
    signal = Mock(spec=TradingSignal)
    signal.signal_id = "test_signal_123"
    signal.strategy = "arbitrage_spread"
    signal.expected_profit = 0.015
    signal.confidence = 0.8
    signal.market_slug = "test-market"
    signal.timestamp = time.time()
    signal.market_volatility = 0.6
    signal.liquidity_score = 0.7
    signal.risk_score = 0.3
    return signal


@pytest.fixture
def test_config():
    """Create a test configuration with smaller values for faster testing."""
    return PipelineConfig(
        critical_workers=2,
        high_workers=3,
        normal_workers=4,
        low_workers=2,
        max_critical_queue=20,
        max_high_queue=30,
        max_normal_queue=40,
        max_low_queue=20,
        enable_batch_processing=True,
        enable_monitoring=False,  # Disable for faster tests
        failure_threshold=5,
        circuit_reset_timeout=10.0,
    )


@pytest.fixture
def optimizer(test_config):
    """Create a signal pipeline optimizer for testing."""
    return SignalPipelineOptimizer(test_config)


class TestSignalPipelineOptimizer:
    """Test the main optimizer functionality."""

    def test_initialization(self, test_config):
        """Test optimizer initialization."""
        optimizer = SignalPipelineOptimizer(test_config)

        assert optimizer.config == test_config
        assert len(optimizer._priority_queues) == 4
        assert len(optimizer._worker_executors) == 4
        assert not optimizer._shutdown
        assert not optimizer._circuit_breaker_open

        # Check worker executor initialization
        for priority in SignalPriority:
            assert priority in optimizer._worker_executors
            executor = optimizer._worker_executors[priority]
            assert executor._max_workers > 0

    def test_analyze_signal_priority(self, optimizer, mock_signal):
        """Test signal priority analysis."""
        # Test critical priority (high profit arbitrage)
        mock_signal.strategy = "arbitrage_spread"
        mock_signal.expected_profit = 0.025  # 2.5% profit
        priority = optimizer.analyze_signal_priority(mock_signal)
        assert priority == SignalPriority.CRITICAL

        # Test high priority (volatile market)
        mock_signal.expected_profit = 0.005  # Lower profit
        mock_signal.market_slug = "breaking-news-market"
        priority = optimizer.analyze_signal_priority(mock_signal)
        assert priority == SignalPriority.HIGH

        # Test low priority (aged signal)
        mock_signal.market_slug = "normal-market"
        mock_signal.timestamp = time.time() - 700  # 11+ minutes old
        priority = optimizer.analyze_signal_priority(mock_signal)
        assert priority == SignalPriority.LOW

        # Test normal priority (default)
        mock_signal.timestamp = time.time()  # Fresh signal
        priority = optimizer.analyze_signal_priority(mock_signal)
        assert priority == SignalPriority.NORMAL

    def test_calculate_priority_score(self, optimizer, mock_signal):
        """Test priority score calculation."""
        # Test high score signal
        mock_signal.expected_profit = 0.02  # 2% profit
        mock_signal.confidence = 0.9
        mock_signal.market_volatility = 0.8
        mock_signal.timestamp = time.time()  # Fresh

        score = optimizer.calculate_priority_score(mock_signal, SignalPriority.HIGH)
        assert score > 15.0  # Should be high score

        # Test low score signal
        mock_signal.expected_profit = 0.001  # 0.1% profit
        mock_signal.confidence = 0.5
        mock_signal.market_volatility = 0.2
        mock_signal.timestamp = time.time() - 300  # 5 minutes old

        score = optimizer.calculate_priority_score(mock_signal, SignalPriority.LOW)
        assert score < 5.0  # Should be low score

    def test_calculate_complexity_score(self, optimizer, mock_signal):
        """Test signal complexity scoring."""
        # Test market making (simple)
        mock_signal.strategy = "market_making"
        complexity = optimizer.calculate_complexity_score(mock_signal)
        assert complexity == 0.5

        # Test arbitrage (complex)
        mock_signal.strategy = "arbitrage_spread"
        complexity = optimizer.calculate_complexity_score(mock_signal)
        assert complexity == 1.5

        # Test default
        mock_signal.strategy = "unknown_strategy"
        complexity = optimizer.calculate_complexity_score(mock_signal)
        assert complexity == 1.0

    @pytest.mark.asyncio
    async def test_submit_signal(self, optimizer, mock_signal):
        """Test signal submission."""
        # Test successful submission
        signal_id = await optimizer.submit_signal(mock_signal)
        assert signal_id == mock_signal.signal_id
        assert signal_id in optimizer._active_signals

        # Check signal was queued
        wrapper = optimizer._active_signals[signal_id]
        assert wrapper.signal == mock_signal
        assert isinstance(wrapper.priority, SignalPriority)
        assert wrapper.priority_score >= 0.0

    @pytest.mark.asyncio
    async def test_submit_signal_when_shutdown(self, optimizer, mock_signal):
        """Test signal submission when optimizer is shutting down."""
        optimizer._shutdown = True

        with pytest.raises(RuntimeError, match="Pipeline is shutting down"):
            await optimizer.submit_signal(mock_signal)

    @pytest.mark.asyncio
    async def test_circuit_breaker(self, optimizer, mock_signal):
        """Test circuit breaker functionality."""
        # Trigger circuit breaker
        optimizer._circuit_breaker_open = True
        optimizer._circuit_reset_time = time.time() + 60  # 1 minute in future

        with pytest.raises(RuntimeError, match="Circuit breaker is open"):
            await optimizer.submit_signal(mock_signal)

        # Test circuit breaker reset
        optimizer._circuit_reset_time = time.time() - 1  # In the past
        signal_id = await optimizer.submit_signal(mock_signal)  # Should work now
        assert signal_id == mock_signal.signal_id
        assert not optimizer._circuit_breaker_open

    @pytest.mark.asyncio
    async def test_check_circuit_breaker_trigger(self, optimizer):
        """Test circuit breaker triggering on failures."""
        # Simulate failures to trigger circuit breaker
        for _ in range(optimizer.config.failure_threshold):
            optimizer._circuit_failure_counts[SignalPriority.NORMAL] += 1

        await optimizer._check_circuit_breaker()

        assert optimizer._circuit_breaker_open
        assert optimizer.metrics.circuit_breaker_open
        assert optimizer.metrics.circuit_breaker_trips == 1

    def test_set_signal_processor(self, optimizer):
        """Test setting signal processors."""

        def test_processor(signal):
            return {"processed": signal.signal_id}

        # Test default processor
        optimizer.set_signal_processor(test_processor)
        assert optimizer._default_processor == test_processor

        # Test priority-specific processor
        optimizer.set_signal_processor(test_processor, SignalPriority.CRITICAL)
        assert optimizer._signal_processors[SignalPriority.CRITICAL] == test_processor

    @pytest.mark.asyncio
    async def test_start_processing(self, optimizer):
        """Test starting the processing system."""
        await optimizer.start_processing()

        # Check workers were started
        expected_workers = (
            optimizer.config.critical_workers
            + optimizer.config.high_workers
            + optimizer.config.normal_workers
            + optimizer.config.low_workers
        )
        assert len(optimizer._worker_tasks) == expected_workers

        # Check all tasks are running
        for task in optimizer._worker_tasks:
            assert not task.done()

    @pytest.mark.asyncio
    async def test_worker_loop_no_processor(self, optimizer):
        """Test worker behavior when no processor is set."""
        # Start processing without setting a processor
        await optimizer.start_processing()

        # Submit a signal
        mock_signal = Mock(spec=TradingSignal)
        mock_signal.signal_id = "no_processor_test"
        mock_signal.strategy = "test"
        mock_signal.expected_profit = 0.01
        mock_signal.confidence = 0.7
        mock_signal.market_slug = "test"
        mock_signal.timestamp = time.time()

        await optimizer.submit_signal(mock_signal)

        # Wait a bit for processing attempt
        await asyncio.sleep(0.5)

        # Signal should be marked as failed due to no processor
        assert mock_signal.signal_id not in optimizer._active_signals

    @pytest.mark.asyncio
    async def test_end_to_end_processing(self, optimizer):
        """Test end-to-end signal processing."""
        # Set up processor
        processed_signals = []

        def test_processor(signal):
            processed_signals.append(signal.signal_id)
            return {"status": "processed", "signal_id": signal.signal_id}

        optimizer.set_signal_processor(test_processor)
        await optimizer.start_processing()

        # Create test signals
        test_signals = []
        for i in range(5):
            signal = Mock(spec=TradingSignal)
            signal.signal_id = f"test_signal_{i}"
            signal.strategy = "test_strategy"
            signal.expected_profit = 0.01
            signal.confidence = 0.7
            signal.market_slug = "test-market"
            signal.timestamp = time.time()
            test_signals.append(signal)

        # Submit signals
        for signal in test_signals:
            await optimizer.submit_signal(signal)

        # Wait for processing
        max_wait = 10.0  # 10 seconds max wait
        start_wait = time.time()
        while (
            optimizer.get_status()["active_signals"] > 0
            and time.time() - start_wait < max_wait
        ):
            await asyncio.sleep(0.1)

        # Check all signals were processed
        assert len(processed_signals) == len(test_signals)
        for signal in test_signals:
            assert signal.signal_id in processed_signals

    def test_get_performance_stats(self, optimizer):
        """Test performance statistics collection."""
        # Set some test metrics
        optimizer.metrics.processed_by_priority["CRITICAL"] = 10
        optimizer.metrics.processed_by_priority["HIGH"] = 20
        optimizer.metrics.queue_sizes["CRITICAL"] = 5
        optimizer.metrics.signals_per_second = 15.5

        stats = optimizer.get_performance_stats()

        assert "summary" in stats
        assert "by_priority" in stats
        assert "circuit_breaker" in stats

        # Check summary
        summary = stats["summary"]
        assert summary["total_processed"] == 30
        assert summary["signals_per_second"] == 15.5
        assert "active_signals" in summary

        # Check priority breakdown
        priority_stats = stats["by_priority"]
        assert "CRITICAL" in priority_stats
        assert priority_stats["CRITICAL"]["processed"] == 10
        assert priority_stats["CRITICAL"]["queue_size"] == 5

    def test_get_status(self, optimizer):
        """Test status reporting."""
        # Add some test data
        optimizer._active_signals["test1"] = Mock()
        optimizer._completed_signals.append(Mock())

        status = optimizer.get_status()

        assert "active_signals" in status
        assert "completed_signals" in status
        assert "worker_tasks" in status
        assert "circuit_breaker_open" in status
        assert "metrics" in status
        assert "uptime_seconds" in status

        assert status["active_signals"] == 1
        assert status["completed_signals"] == 1
        assert status["circuit_breaker_open"] == False


class TestPipelineConfig:
    """Test pipeline configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = PipelineConfig()

        # Check default worker counts
        assert config.critical_workers == 6
        assert config.high_workers == 10
        assert config.normal_workers == 16
        assert config.low_workers == 6

        # Check queue limits
        assert config.max_critical_queue == 100
        assert config.max_normal_queue == 500

        # Check timeouts
        assert config.critical_timeout == 5.0
        assert config.low_timeout == 60.0

        # Check batch processing
        assert config.enable_batch_processing == True
        assert config.critical_batch_size == 1
        assert config.normal_batch_size == 8

    def test_custom_config(self):
        """Test custom configuration values."""
        config = PipelineConfig(
            critical_workers=4,
            normal_workers=8,
            enable_batch_processing=False,
            failure_threshold=20,
        )

        assert config.critical_workers == 4
        assert config.normal_workers == 8
        assert config.enable_batch_processing == False
        assert config.failure_threshold == 20


class TestOptimizedSignalWrapper:
    """Test the optimized signal wrapper."""

    def test_wrapper_creation(self, mock_signal):
        """Test wrapper creation and properties."""
        from inkedup_bot.signal_manager import SignalMetadata, SignalStatus

        metadata = SignalMetadata(
            signal_id="test_123",
            created_at=time.time(),
            expires_at=time.time() + 30,
            status=SignalStatus.PENDING,
        )

        wrapper = OptimizedSignalWrapper(
            signal=mock_signal,
            metadata=metadata,
            priority=SignalPriority.HIGH,
            priority_score=15.5,
            complexity_score=1.2,
        )

        assert wrapper.signal == mock_signal
        assert wrapper.metadata == metadata
        assert wrapper.priority == SignalPriority.HIGH
        assert wrapper.priority_score == 15.5
        assert wrapper.complexity_score == 1.2
        assert wrapper.processing_started_at is None

    def test_wrapper_comparison(self, mock_signal):
        """Test wrapper priority comparison."""
        from inkedup_bot.signal_manager import SignalMetadata, SignalStatus

        metadata = SignalMetadata(
            signal_id="test_123",
            created_at=time.time(),
            expires_at=time.time() + 30,
            status=SignalStatus.PENDING,
        )

        # Create wrappers with different priorities
        high_wrapper = OptimizedSignalWrapper(
            signal=mock_signal,
            metadata=metadata,
            priority=SignalPriority.HIGH,
            priority_score=10.0,
        )

        critical_wrapper = OptimizedSignalWrapper(
            signal=mock_signal,
            metadata=metadata,
            priority=SignalPriority.CRITICAL,
            priority_score=5.0,
        )

        # Critical should be "less than" high (higher priority)
        assert critical_wrapper < high_wrapper

        # Same priority, higher score should be "less than"
        high_wrapper2 = OptimizedSignalWrapper(
            signal=mock_signal,
            metadata=metadata,
            priority=SignalPriority.HIGH,
            priority_score=15.0,
        )

        assert high_wrapper2 < high_wrapper


class TestFactoryFunctions:
    """Test factory functions."""

    def test_create_optimized_pipeline(self):
        """Test pipeline factory function."""
        pipeline = create_optimized_pipeline()

        assert isinstance(pipeline, SignalPipelineOptimizer)
        assert pipeline.config is not None
        assert len(pipeline._priority_queues) == 4

    def test_create_optimized_pipeline_with_config(self):
        """Test pipeline factory with custom config."""
        config = PipelineConfig(critical_workers=8)
        pipeline = create_optimized_pipeline(config)

        assert isinstance(pipeline, SignalPipelineOptimizer)
        assert pipeline.config == config
        assert pipeline.config.critical_workers == 8


@pytest.mark.asyncio
class TestPerformanceIntegration:
    """Integration tests for performance optimization."""

    async def test_priority_ordering(self):
        """Test that signals are processed in priority order."""
        config = PipelineConfig(
            critical_workers=1,  # Single worker to test ordering
            high_workers=1,
            normal_workers=1,
            low_workers=1,
            enable_batch_processing=False,  # Disable batching for order testing
        )

        optimizer = SignalPipelineOptimizer(config)
        processed_order = []

        def test_processor(signal):
            processed_order.append(signal.signal_id)
            return {"processed": signal.signal_id}

        optimizer.set_signal_processor(test_processor)

        try:
            await optimizer.start_processing()

            # Create signals with different priorities
            signals = []

            # Low priority (should process last)
            low_signal = Mock(spec=TradingSignal)
            low_signal.signal_id = "low_priority"
            low_signal.strategy = "market_making"
            low_signal.expected_profit = 0.002
            low_signal.confidence = 0.6
            low_signal.market_slug = "stable-market"
            low_signal.timestamp = time.time() - 800  # Very old
            signals.append(low_signal)

            # Normal priority
            normal_signal = Mock(spec=TradingSignal)
            normal_signal.signal_id = "normal_priority"
            normal_signal.strategy = "mean_reversion"
            normal_signal.expected_profit = 0.005
            normal_signal.confidence = 0.7
            normal_signal.market_slug = "regular-market"
            normal_signal.timestamp = time.time()
            signals.append(normal_signal)

            # High priority (should process second)
            high_signal = Mock(spec=TradingSignal)
            high_signal.signal_id = "high_priority"
            high_signal.strategy = "news_reaction"
            high_signal.expected_profit = 0.01
            high_signal.confidence = 0.8
            high_signal.market_slug = "volatile-market"
            high_signal.timestamp = time.time()
            signals.append(high_signal)

            # Critical priority (should process first)
            critical_signal = Mock(spec=TradingSignal)
            critical_signal.signal_id = "critical_priority"
            critical_signal.strategy = "arbitrage_spread"
            critical_signal.expected_profit = 0.025  # 2.5% profit
            critical_signal.confidence = 0.9
            critical_signal.market_slug = "arbitrage-market"
            critical_signal.timestamp = time.time()
            signals.append(critical_signal)

            # Submit in reverse priority order
            for signal in signals:
                await optimizer.submit_signal(signal)

            # Wait for processing
            max_wait = 10.0
            start_wait = time.time()
            while (
                len(processed_order) < len(signals)
                and time.time() - start_wait < max_wait
            ):
                await asyncio.sleep(0.1)

            # Check processing order
            assert len(processed_order) == len(signals)

            # Critical should be first, low should be last
            assert processed_order[0] == "critical_priority"
            assert processed_order[-1] == "low_priority"

        finally:
            await optimizer.shutdown()

    async def test_concurrent_processing(self):
        """Test that multiple signals can be processed concurrently."""
        config = PipelineConfig(
            normal_workers=4,  # Multiple workers for concurrency
            enable_batch_processing=False,
        )

        optimizer = SignalPipelineOptimizer(config)
        processing_times = {}
        processing_lock = asyncio.Lock()

        def test_processor(signal):
            start_time = time.time()
            time.sleep(0.2)  # Simulate 200ms processing time
            end_time = time.time()

            # Record processing time in thread-safe way
            processing_times[signal.signal_id] = {
                "start": start_time,
                "end": end_time,
                "duration": end_time - start_time,
            }
            return {"processed": signal.signal_id}

        optimizer.set_signal_processor(test_processor)

        try:
            await optimizer.start_processing()

            # Create multiple signals
            signals = []
            for i in range(8):  # More signals than workers
                signal = Mock(spec=TradingSignal)
                signal.signal_id = f"concurrent_signal_{i}"
                signal.strategy = "test_strategy"
                signal.expected_profit = 0.01
                signal.confidence = 0.7
                signal.market_slug = "test-market"
                signal.timestamp = time.time()
                signals.append(signal)

            # Submit all signals quickly
            submit_start = time.time()
            for signal in signals:
                await optimizer.submit_signal(signal)
            submit_end = time.time()

            # Wait for all processing to complete
            max_wait = 15.0
            start_wait = time.time()
            while (
                len(processing_times) < len(signals)
                and time.time() - start_wait < max_wait
            ):
                await asyncio.sleep(0.1)

            # Verify concurrent processing
            assert len(processing_times) == len(signals)

            # Calculate total processing time if sequential
            total_sequential_time = sum(
                times["duration"] for times in processing_times.values()
            )

            # Calculate actual wall clock time
            earliest_start = min(times["start"] for times in processing_times.values())
            latest_end = max(times["end"] for times in processing_times.values())
            actual_wall_time = latest_end - earliest_start

            # Concurrent processing should be significantly faster than sequential
            concurrency_ratio = total_sequential_time / actual_wall_time
            assert concurrency_ratio > 2.0  # At least 2x speedup from concurrency

        finally:
            await optimizer.shutdown()
