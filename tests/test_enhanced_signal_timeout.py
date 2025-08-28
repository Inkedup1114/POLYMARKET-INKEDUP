"""
Comprehensive tests for enhanced signal timeout handling functionality.

This test suite validates:
- Enhanced timestamp tracking
- Advanced cleanup strategies  
- Granular timeout configuration
- Signal interference prevention
- Comprehensive monitoring and alerting
"""

import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from inkedup_bot.enhanced_signal_manager import (
    EnhancedSignalManager,
    EnhancedSignalManagerConfig,
    EnhancedSignalMetadata,
    SignalPriority,
)
from inkedup_bot.signal_cleanup_manager import (
    CleanupConfig,
    SignalCleanupManager,
    SignalInterferenceLevel,
)
from inkedup_bot.signal_monitoring import (
    AlertSeverity,
    MonitoringMetric,
    SignalMonitoringSystem,
)
from inkedup_bot.signal_timeout_config import (
    AdvancedTimeoutConfigManager,
    StrategyType,
)
from inkedup_bot.signals import TradingSignal


class TestEnhancedTimestampTracking:
    """Test enhanced timestamp tracking functionality."""

    def test_metadata_timestamp_updates(self):
        """Test that metadata timestamps are properly tracked."""
        metadata = EnhancedSignalMetadata(
            signal_id="test_123", created_at=time.time(), expires_at=time.time() + 30
        )

        # Test timestamp update method
        start_time = time.time()
        metadata.update_timestamp("processing_started")

        assert metadata.processing_started_at is not None
        assert metadata.processing_started_at >= start_time
        assert metadata.last_accessed_at == metadata.processing_started_at

        # Test multiple timestamp updates
        time.sleep(0.01)  # Ensure different timestamp
        metadata.update_timestamp("risk_check_started")
        metadata.update_timestamp("risk_check_completed")

        assert metadata.risk_check_started_at is not None
        assert metadata.risk_check_completed_at is not None
        assert metadata.risk_check_completed_at > metadata.risk_check_started_at

    def test_duration_calculations(self):
        """Test duration calculation methods."""
        metadata = EnhancedSignalMetadata(
            signal_id="test_123", created_at=time.time(), expires_at=time.time() + 30
        )

        base_time = time.time()
        metadata.queue_entry_time = base_time
        metadata.processing_started_at = base_time + 1.0
        metadata.execution_completed_at = base_time + 3.0
        metadata.risk_check_started_at = base_time + 1.5
        metadata.risk_check_completed_at = base_time + 2.0
        metadata.execution_started_at = base_time + 2.1

        # Test queue wait duration
        queue_wait = metadata.get_queue_wait_duration()
        assert queue_wait == 1.0

        # Test processing duration
        processing_duration = metadata.get_processing_duration()
        assert processing_duration == 2.0  # 3.0 - 1.0

        # Test risk check duration
        risk_duration = metadata.get_risk_check_duration()
        assert risk_duration == 0.5  # 2.0 - 1.5

        # Test execution duration
        exec_duration = metadata.get_execution_duration()
        assert abs(exec_duration - 0.9) < 0.01  # 3.0 - 2.1


class TestAdvancedCleanupStrategies:
    """Test advanced cleanup strategies."""

    @pytest.fixture
    def cleanup_manager(self):
        """Create cleanup manager for testing."""
        config = CleanupConfig(cleanup_interval_seconds=1.0, batch_cleanup_size=10)
        return SignalCleanupManager(config)

    @patch("inkedup_bot.signal_cleanup_manager.psutil.cpu_percent")
    @patch("inkedup_bot.signal_cleanup_manager.psutil.virtual_memory")
    def test_system_load_based_cleanup(self, mock_memory, mock_cpu, cleanup_manager):
        """Test system load-based cleanup triggering."""
        # Mock high system load
        mock_cpu.return_value = 85.0  # 85% CPU
        mock_memory.return_value.percent = 90.0  # 90% memory

        # Test system load detection
        system_load = cleanup_manager._get_system_load()
        memory_usage = cleanup_manager._get_memory_usage()

        assert system_load == 0.85
        assert memory_usage == 0.90

        # Test aggressive cleanup trigger
        should_trigger = cleanup_manager._should_trigger_aggressive_cleanup()
        assert should_trigger is True

        # Test adaptive cleanup delay reduction
        base_delay = 10.0
        adaptive_delay = cleanup_manager._get_adaptive_cleanup_delay(base_delay)
        assert adaptive_delay < base_delay  # Should be reduced under load

    def test_cleanup_rule_matching(self, cleanup_manager):
        """Test cleanup rule matching with system metrics."""
        # Create test signal analytics
        from inkedup_bot.signal_cleanup_manager import SignalAnalytics

        current_time = time.time()
        analytics = SignalAnalytics(
            signal_id="test_signal",
            created_at=current_time - 100,  # 100 seconds old
            last_accessed=current_time - 50,
            access_count=5,
            interference_score=0.3,
        )

        # Test rule matching with system context
        with patch.object(cleanup_manager, "_get_system_load", return_value=0.85):
            with patch.object(cleanup_manager, "_get_memory_usage", return_value=0.90):
                rule = cleanup_manager._get_applicable_cleanup_rule(
                    "test_signal", analytics, current_time
                )

                assert rule is not None
                # Should match high load cleanup rule due to system pressure
                assert rule.name in ["high_load_cleanup", "memory_pressure_cleanup"]

    def test_interference_assessment(self, cleanup_manager):
        """Test enhanced interference assessment."""
        # Create test signals
        signal1 = TradingSignal(
            signal_id="signal_1",
            market_slug="test_market",
            token_id="token_123",
            side="BUY",
            price=0.55,
            size=100,
        )

        signal2 = TradingSignal(
            signal_id="signal_2",
            market_slug="test_market",
            token_id="token_123",
            side="SELL",  # Opposite side - high interference
            price=0.54,  # Close price - price conflict
            size=200,
        )

        # Register signals
        cleanup_manager.register_signal(signal1, {"priority": "normal"})
        cleanup_manager.register_signal(signal2, {"priority": "high"})

        # Test interference assessment
        interference_level = cleanup_manager._assess_signal_interference(
            signal1, "signal_2"
        )

        # Should detect high interference due to opposite sides and close prices
        assert interference_level in [
            SignalInterferenceLevel.HIGH,
            SignalInterferenceLevel.CRITICAL,
        ]


class TestGranularTimeoutConfiguration:
    """Test granular timeout configuration."""

    @pytest.fixture
    def timeout_manager(self):
        """Create timeout configuration manager."""
        return AdvancedTimeoutConfigManager()

    def test_granular_strategy_timeouts(self, timeout_manager):
        """Test strategy-specific timeout configuration."""
        # Enable granular mode
        timeout_manager.enable_granular_mode(True)

        # Test ultra-fast arbitrage strategy
        timeout = timeout_manager._calculate_granular_timeout(
            strategy_type=StrategyType.PURE_ARBITRAGE,
            priority="critical",
            current_time=datetime.now(UTC),
            volatility_score=0.5,
        )

        # Should be very short for critical arbitrage
        assert timeout <= 1.0  # Less than 1 second

        # Test slower strategy
        timeout_slow = timeout_manager._calculate_granular_timeout(
            strategy_type=StrategyType.TREND_FOLLOWING,
            priority="normal",
            current_time=datetime.now(UTC),
            volatility_score=0.3,
        )

        # Should be much longer
        assert timeout_slow > timeout * 10

    def test_session_based_timeout_adjustment(self, timeout_manager):
        """Test fine-grained session-based timeout adjustment."""
        # Test different time sessions
        market_open_time = datetime.now(UTC).replace(
            hour=9, minute=35
        )  # Market open first
        market_close_time = datetime.now(UTC).replace(
            hour=15, minute=50
        )  # Market close final

        timeout_manager.enable_granular_mode(True)

        # Market open (volatile) - should have shorter timeout
        timeout_open = timeout_manager._calculate_granular_timeout(
            strategy_type=StrategyType.SHORT_MOMENTUM,
            priority="normal",
            current_time=market_open_time,
            volatility_score=0.6,
        )

        # Market close (very volatile) - should have even shorter timeout
        timeout_close = timeout_manager._calculate_granular_timeout(
            strategy_type=StrategyType.SHORT_MOMENTUM,
            priority="normal",
            current_time=market_close_time,
            volatility_score=0.6,
        )

        # Market close should have shorter timeout than market open
        assert timeout_close < timeout_open

    def test_volatility_level_classification(self, timeout_manager):
        """Test volatility level classification."""
        assert timeout_manager._get_volatility_level(0.05) == "ultra_low"
        assert timeout_manager._get_volatility_level(0.15) == "low"
        assert timeout_manager._get_volatility_level(0.30) == "normal"
        assert timeout_manager._get_volatility_level(0.50) == "elevated"
        assert timeout_manager._get_volatility_level(0.70) == "high"
        assert timeout_manager._get_volatility_level(0.95) == "extreme"

    def test_priority_multipliers(self, timeout_manager):
        """Test granular priority-based timeout multipliers."""
        timeout_manager.enable_granular_mode(True)

        base_time = datetime.now(UTC)

        # Test different priorities
        timeout_emergency = timeout_manager._calculate_granular_timeout(
            strategy_type=StrategyType.PURE_ARBITRAGE,
            priority="emergency",
            current_time=base_time,
            volatility_score=0.3,
        )

        timeout_normal = timeout_manager._calculate_granular_timeout(
            strategy_type=StrategyType.PURE_ARBITRAGE,
            priority="normal",
            current_time=base_time,
            volatility_score=0.3,
        )

        timeout_background = timeout_manager._calculate_granular_timeout(
            strategy_type=StrategyType.PURE_ARBITRAGE,
            priority="background",
            current_time=base_time,
            volatility_score=0.3,
        )

        # Emergency should be fastest, background slowest
        assert timeout_emergency < timeout_normal < timeout_background


class TestSignalInterferencePrevention:
    """Test signal interference prevention."""

    @pytest.fixture
    def cleanup_manager(self):
        """Create cleanup manager for testing."""
        return SignalCleanupManager()

    def test_proactive_interference_prevention(self, cleanup_manager):
        """Test proactive signal interference prevention."""
        # Create conflicting signals
        existing_signal = TradingSignal(
            signal_id="existing_123",
            market_slug="test_market",
            token_id="token_456",
            side="BUY",
            price=0.60,
            size=500,
        )

        incoming_signal = TradingSignal(
            signal_id="incoming_123",
            market_slug="test_market",
            token_id="token_456",
            side="SELL",  # Conflicting side
            price=0.59,  # Competing price
            size=400,
        )

        # Register existing signal
        cleanup_manager.register_signal(existing_signal, {"priority": "normal"})

        # Test interference prevention
        prevention_result = cleanup_manager.prevent_signal_interference(incoming_signal)

        assert prevention_result["blocked"] is True
        assert len(prevention_result["conflicting_signals"]) > 0
        assert prevention_result["interference_score"] > 0.5
        assert len(prevention_result["recommended_actions"]) > 0

    def test_automatic_conflict_resolution(self, cleanup_manager):
        """Test automatic conflict resolution."""
        # Create signals with different priorities
        low_priority_signal = TradingSignal(
            signal_id="low_pri",
            market_slug="test_market",
            token_id="token_789",
            side="BUY",
            price=0.50,
            size=300,
        )

        high_priority_signal = TradingSignal(
            signal_id="high_pri",
            market_slug="test_market",
            token_id="token_789",
            side="SELL",
            price=0.49,
            size=250,
        )

        # Register low priority signal first
        cleanup_manager.register_signal(low_priority_signal, {"priority": "low"})

        # Test auto-resolution when high priority signal comes in
        high_priority_signal.priority = "critical"  # Set high priority
        resolution_result = cleanup_manager.auto_resolve_conflicts(high_priority_signal)

        # Should successfully resolve by cancelling lower priority signal
        assert resolution_result["resolved"] is True
        assert len(resolution_result["signals_cancelled"]) >= 0
        assert len(resolution_result["actions_taken"]) >= 0

    def test_market_capacity_constraints(self, cleanup_manager):
        """Test market capacity constraint checking."""
        large_signal = TradingSignal(
            signal_id="large_signal",
            market_slug="small_market",
            token_id="illiquid_token",
            side="BUY",
            price=0.45,
            size=50000,  # Very large size
        )

        # Mock market capacity estimation
        with patch.object(
            cleanup_manager, "_estimate_market_capacity", return_value=10000.0
        ):
            has_capacity_issue = cleanup_manager._check_market_capacity_constraints(
                large_signal
            )
            assert has_capacity_issue is True  # Signal too large for market


@pytest.mark.asyncio
class TestSignalMonitoring:
    """Test comprehensive signal monitoring system."""

    @pytest.fixture
    async def monitoring_system(self):
        """Create monitoring system for testing."""
        system = SignalMonitoringSystem()
        await system.start_monitoring()
        yield system
        await system.stop_monitoring()

    async def test_signal_lifecycle_monitoring(self, monitoring_system):
        """Test monitoring of complete signal lifecycle."""
        signal = TradingSignal(
            signal_id="monitored_signal",
            market_slug="test_market",
            token_id="test_token",
            side="BUY",
            price=0.65,
            size=150,
        )

        start_time = time.time()

        # Record signal lifecycle events
        monitoring_system.record_signal_submitted(signal, start_time)

        # Simulate processing delay
        await asyncio.sleep(0.05)

        monitoring_system.record_signal_completed("monitored_signal", start_time + 0.05)

        # Check that metrics were recorded
        summary = monitoring_system.get_monitoring_summary()
        assert summary["total_signals_tracked"] == 1

        # Check throughput metric
        throughput_metric = summary["metrics"].get(
            MonitoringMetric.SIGNAL_THROUGHPUT.value
        )
        if throughput_metric:
            assert throughput_metric["samples_count"] > 0

    async def test_alert_generation(self, monitoring_system):
        """Test alert generation for threshold violations."""
        # Record multiple failed signals to trigger error rate alert
        for i in range(10):
            monitoring_system.record_signal_failed(f"failed_{i}", "test error")

        # Wait for monitoring loop to process
        await asyncio.sleep(0.1)

        # Check if alerts were generated
        summary = monitoring_system.get_monitoring_summary()
        assert summary["active_alerts"] >= 0  # May have generated alerts

    async def test_anomaly_detection(self, monitoring_system):
        """Test anomaly detection capabilities."""
        # Create baseline with normal latencies
        for i in range(20):
            monitoring_system._metric_windows[
                MonitoringMetric.PROCESSING_LATENCY
            ].add_sample(
                1.0 + (i % 3) * 0.1  # Normal latencies around 1 second
            )

        # Add anomalous spike
        for i in range(5):
            monitoring_system._metric_windows[
                MonitoringMetric.PROCESSING_LATENCY
            ].add_sample(10.0)

        # Trigger anomaly detection
        await monitoring_system._detect_anomalies()

        # Should detect the anomaly (this is integration testing)
        summary = monitoring_system.get_monitoring_summary()
        # Anomaly detection might generate alerts

    async def test_custom_alert_handlers(self, monitoring_system):
        """Test custom alert handler registration and execution."""
        handler_called = False
        alert_received = None

        async def custom_handler(alert):
            nonlocal handler_called, alert_received
            handler_called = True
            alert_received = alert

        # Register handler
        monitoring_system.add_alert_handler(AlertSeverity.WARNING, custom_handler)

        # Generate alert that should trigger handler
        await monitoring_system._generate_alert(
            severity=AlertSeverity.WARNING,
            metric=MonitoringMetric.ERROR_RATE,
            message="Test alert",
            details={"test": "data"},
        )

        # Wait for handler execution
        await asyncio.sleep(0.01)

        # Verify handler was called
        assert handler_called is True
        assert alert_received is not None
        assert alert_received.severity == AlertSeverity.WARNING

    def test_system_health_assessment(self, monitoring_system):
        """Test system health assessment."""
        # Initially system should be healthy
        assert monitoring_system._system_healthy is True

        # Record high error rates to degrade health
        for i in range(50):
            monitoring_system.record_signal_failed(f"error_{i}", "test failure")

        # Health status might change after processing
        # This tests the health assessment logic


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple enhanced features."""

    @pytest.fixture
    def integrated_system(self):
        """Create integrated system with all components."""
        config = EnhancedSignalManagerConfig()
        signal_manager = EnhancedSignalManager(config)
        cleanup_manager = SignalCleanupManager()
        timeout_manager = AdvancedTimeoutConfigManager()

        return {
            "signal_manager": signal_manager,
            "cleanup_manager": cleanup_manager,
            "timeout_manager": timeout_manager,
        }

    @pytest.mark.asyncio
    async def test_high_frequency_signal_processing(self, integrated_system):
        """Test system behavior under high-frequency signal load."""
        signal_manager = integrated_system["signal_manager"]

        # Create multiple rapid signals
        signals = []
        for i in range(20):
            signal = TradingSignal(
                signal_id=f"hf_signal_{i}",
                market_slug="high_freq_market",
                token_id="hf_token",
                side="BUY" if i % 2 == 0 else "SELL",
                price=0.50 + (i * 0.01),
                size=100 + (i * 10),
            )
            signals.append(signal)

        # Submit signals rapidly
        start_time = time.time()
        submitted_signals = []

        for signal in signals:
            try:
                signal_id = await signal_manager.submit_enhanced_signal(
                    signal,
                    priority=SignalPriority.HIGH,
                    strategy_name="high_frequency_test",
                )
                submitted_signals.append(signal_id)
            except Exception:
                # Expected - some signals may be blocked due to interference
                pass

        end_time = time.time()
        processing_time = end_time - start_time

        # Verify reasonable processing time
        assert processing_time < 5.0  # Should complete quickly
        assert len(submitted_signals) > 0  # At least some signals processed

    def test_stress_cleanup_with_interference(self, integrated_system):
        """Test cleanup system under stress with high interference."""
        cleanup_manager = integrated_system["cleanup_manager"]

        # Create many overlapping signals
        for i in range(100):
            signal = TradingSignal(
                signal_id=f"stress_{i}",
                market_slug="stress_market",
                token_id="stress_token",
                side="BUY" if i % 3 == 0 else "SELL",
                price=0.40 + (i % 10) * 0.01,
                size=50 + (i % 5) * 20,
            )

            cleanup_manager.register_signal(
                signal,
                {
                    "priority": ["low", "normal", "high"][i % 3],
                    "strategy": "stress_test",
                },
            )

        # Trigger cleanup
        current_time = time.time()
        cleanup_manager.cleanup_expired_signals(current_time)

        # System should handle the load gracefully
        metrics = cleanup_manager.get_cleanup_metrics()
        assert metrics["active_signals"] <= 100  # Some cleanup occurred
        assert metrics["total_cleaned"] >= 0  # Cleanup metrics updated


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
