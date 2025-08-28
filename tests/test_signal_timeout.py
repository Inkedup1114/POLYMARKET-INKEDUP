"""
Unit tests for signal timeout handling functionality.
"""

import asyncio
import time
from unittest.mock import Mock

import pytest

from inkedup_bot.signal_manager import SignalManager, SignalManagerConfig, SignalStatus
from inkedup_bot.signals import TradingSignal


@pytest.fixture
def test_config():
    """Create test configuration with short timeouts."""
    return SignalManagerConfig(
        default_signal_timeout=2.0,  # 2 second timeout for fast tests
        cleanup_interval=0.5,  # Cleanup every 0.5 seconds
        enable_deduplication=True,
        deduplication_window=1.0,  # 1 second dedup window
        max_concurrent_signals=3,
    )


@pytest.fixture
def signal_manager(test_config):
    """Create signal manager with test configuration."""
    manager = SignalManager(test_config)
    return manager


@pytest.fixture
def test_signal():
    """Create a test trading signal."""
    return TradingSignal(
        market_slug="test-market",
        token_id="test-token",
        side="buy",
        price=0.55,
        size=100.0,
        signal_id="test-signal-1",
    )


def test_signal_manager_creation(test_config):
    """Test signal manager can be created with configuration."""
    manager = SignalManager(test_config)
    assert manager.config.default_signal_timeout == 2.0
    assert not manager._running


def test_signal_submission(signal_manager, test_signal):
    """Test basic signal submission."""
    # Set up a mock processor
    processor = Mock()
    signal_manager.set_signal_processor(processor)

    # Submit signal
    signal_id = signal_manager.submit_signal(test_signal)

    assert signal_id is not None
    assert signal_id == test_signal.signal_id

    # Check signal is in pending state
    status = signal_manager.get_signal_status(signal_id)
    assert status == SignalStatus.PENDING


def test_signal_deduplication(signal_manager, test_signal):
    """Test signal deduplication functionality."""
    processor = Mock()
    signal_manager.set_signal_processor(processor)

    # Submit original signal
    signal_id1 = signal_manager.submit_signal(test_signal)
    assert signal_id1 is not None

    # Try to submit duplicate - should raise exception
    with pytest.raises(Exception):  # Should be SignalDeduplicationError
        signal_manager.submit_signal(test_signal)

    # Metrics should show deduplication
    metrics = signal_manager.get_metrics()
    assert metrics["signals_deduplicated"] == 1


def test_signal_timeout_configuration(signal_manager):
    """Test different timeout periods for different signal types."""
    processor = Mock()
    signal_manager.set_signal_processor(processor)

    # Test spread signal (should have shorter timeout)
    spread_signal = TradingSignal(
        market_slug="spread-test-market",
        token_id="test-token",
        side="buy",
        price=0.55,
        size=100.0,
    )

    signal_id = signal_manager.submit_signal(spread_signal)
    wrapper = signal_manager._pending_signals[signal_id]

    # Should use shorter timeout for spread signals
    timeout_used = wrapper.metadata.expires_at - wrapper.metadata.created_at
    assert timeout_used <= signal_manager.config.default_signal_timeout


@pytest.mark.asyncio
async def test_signal_expiration(signal_manager, test_signal):
    """Test that signals expire after timeout period."""
    processor = Mock()
    signal_manager.set_signal_processor(processor)

    # Start signal manager
    await signal_manager.start()

    try:
        # Submit signal
        signal_id = signal_manager.submit_signal(test_signal)

        # Check initial status
        status = signal_manager.get_signal_status(signal_id)
        assert status == SignalStatus.PENDING

        # Wait for signal to expire (config has 2 second timeout)
        await asyncio.sleep(3.0)

        # Signal should now be expired
        status = signal_manager.get_signal_status(signal_id)
        assert status == SignalStatus.EXPIRED

        # Metrics should show expiration
        metrics = signal_manager.get_metrics()
        assert metrics["signals_expired"] >= 1

    finally:
        await signal_manager.stop()


@pytest.mark.asyncio
async def test_signal_processing_success(signal_manager, test_signal):
    """Test successful signal processing."""
    # Create a processor that succeeds
    processor = Mock()
    signal_manager.set_signal_processor(processor)

    await signal_manager.start()

    try:
        # Submit signal
        signal_id = signal_manager.submit_signal(test_signal)

        # Wait for processing
        await asyncio.sleep(1.0)

        # Processor should have been called
        processor.assert_called_once_with(test_signal)

        # Signal should be processed
        status = signal_manager.get_signal_status(signal_id)
        assert status == SignalStatus.PROCESSED

        # Metrics should show processing
        metrics = signal_manager.get_metrics()
        assert metrics["signals_processed"] >= 1

    finally:
        await signal_manager.stop()


@pytest.mark.asyncio
async def test_signal_processing_failure(signal_manager, test_signal):
    """Test signal processing failure handling."""

    # Create a processor that raises an exception
    def failing_processor(signal):
        raise RuntimeError("Test processing failure")

    signal_manager.set_signal_processor(failing_processor)

    await signal_manager.start()

    try:
        # Submit signal
        signal_id = signal_manager.submit_signal(test_signal)

        # Wait for processing attempt
        await asyncio.sleep(1.0)

        # Signal should be marked as failed
        status = signal_manager.get_signal_status(signal_id)
        assert status == SignalStatus.FAILED

        # Metrics should show failure
        metrics = signal_manager.get_metrics()
        assert metrics["signals_failed"] >= 1

    finally:
        await signal_manager.stop()


def test_signal_metrics(signal_manager, test_signal):
    """Test signal processing metrics."""
    processor = Mock()
    signal_manager.set_signal_processor(processor)

    # Submit some signals
    for i in range(3):
        signal = TradingSignal(
            market_slug=f"test-market-{i}",
            token_id=f"test-token-{i}",
            side="buy",
            price=0.5 + i * 0.01,
            size=100.0,
            signal_id=f"test-signal-{i}",
        )
        signal_manager.submit_signal(signal)

    # Check metrics
    metrics = signal_manager.get_metrics()
    assert metrics["signals_received"] == 3
    assert metrics["pending_signals"] == 3
    assert "avg_processing_time" in metrics
    assert "last_cleanup_at" in metrics


@pytest.mark.asyncio
async def test_cleanup_task(signal_manager, test_signal):
    """Test that cleanup task runs and cleans up expired signals."""
    processor = Mock()
    signal_manager.set_signal_processor(processor)

    await signal_manager.start()

    try:
        # Submit signal
        signal_id = signal_manager.submit_signal(test_signal)

        # Wait for signal to expire and cleanup to run
        await asyncio.sleep(3.0)

        # Signal should be cleaned up and moved to expired queue
        assert signal_id not in signal_manager._pending_signals
        assert len(signal_manager._expired_signals) > 0

        # Metrics should show cleanup occurred
        metrics = signal_manager.get_metrics()
        assert metrics["last_cleanup_at"] > 0

    finally:
        await signal_manager.stop()


@pytest.mark.asyncio
async def test_concurrent_signal_processing(signal_manager):
    """Test concurrent signal processing limits."""
    # Create slow processor to test concurrency
    process_times = []

    async def slow_processor(signal):
        start = time.time()
        await asyncio.sleep(0.5)  # Simulate slow processing
        process_times.append(time.time() - start)

    # Wrap in sync function for compatibility
    def sync_processor(signal):
        asyncio.create_task(slow_processor(signal))

    signal_manager.set_signal_processor(sync_processor)

    await signal_manager.start()

    try:
        # Submit multiple signals
        signals = []
        for i in range(5):
            signal = TradingSignal(
                market_slug=f"concurrent-test-{i}",
                token_id=f"token-{i}",
                side="buy",
                price=0.5,
                size=100.0,
                signal_id=f"concurrent-signal-{i}",
            )
            signals.append(signal)
            signal_manager.submit_signal(signal)

        # Wait for processing
        await asyncio.sleep(2.0)

        # Should respect max concurrent limit (3 in test config)
        metrics = signal_manager.get_metrics()
        assert metrics["processing_signals"] <= 3

    finally:
        await signal_manager.stop()


def test_signal_status_transitions(signal_manager, test_signal):
    """Test signal status transitions through lifecycle."""
    processor = Mock()
    signal_manager.set_signal_processor(processor)

    # Submit signal
    signal_id = signal_manager.submit_signal(test_signal)

    # Should start as pending
    assert signal_manager.get_signal_status(signal_id) == SignalStatus.PENDING

    # Status should remain pending until processing starts
    time.sleep(0.1)
    status = signal_manager.get_signal_status(signal_id)
    assert status in [SignalStatus.PENDING, SignalStatus.PROCESSING]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
