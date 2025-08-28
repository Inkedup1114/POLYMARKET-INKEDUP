#!/usr/bin/env python3
"""
Test script for signal timeout handling functionality.

This script demonstrates:
1. Signal timeout handling
2. Automatic cleanup of stale signals
3. Signal deduplication
4. Metrics and monitoring
"""

import asyncio
import time
from dataclasses import dataclass

from inkedup_bot.config import BotConfig
from inkedup_bot.engine import TradingEngine
from inkedup_bot.signals import TradingSignal


@dataclass
class TestConfig:
    """Test configuration for signal timeout testing."""

    test_duration: float = 60.0  # Total test duration in seconds
    signal_generation_interval: float = 2.0  # Generate signal every N seconds


async def create_test_signal(index: int, market_type: str = "spread") -> TradingSignal:
    """Create a test trading signal."""
    return TradingSignal(
        market_slug=f"test-market-{market_type}-{index}",
        token_id=f"token_{index}",
        side="buy" if index % 2 == 0 else "sell",
        price=0.5 + (index % 10) * 0.01,  # Price between 0.5 and 0.59
        size=10.0 + (index % 5),  # Size between 10 and 14
        signal_id=f"test_signal_{index}",
        outcome_type="yes" if index % 2 == 0 else "no",
    )


async def test_signal_timeout_handling():
    """Test signal timeout handling functionality."""
    print("🚀 Starting Signal Timeout Handling Test")
    print("=" * 60)

    # Create a test configuration with shorter timeouts for testing
    config = BotConfig()

    # Override signal timeout configurations for testing
    config.signal_default_timeout_seconds = 10.0
    config.signal_spread_timeout_seconds = 5.0
    config.signal_complement_timeout_seconds = 15.0
    config.signal_market_making_timeout_seconds = 20.0
    config.signal_cleanup_interval_seconds = 3.0
    config.signal_max_concurrent = 5
    config.signal_enable_deduplication = True
    config.signal_deduplication_window_seconds = 2.0

    # Create trading engine (note: this will fail auth, but signal manager will work)
    engine = TradingEngine(config)

    try:
        # Initialize engine (this might fail due to auth, but signal manager should work)
        try:
            await engine.initialize()
        except Exception as e:
            print(f"⚠️  Engine initialization failed (expected): {e}")
            print("📝 Signal manager should still work for testing timeouts")

        test_config = TestConfig()
        start_time = time.time()
        signal_counter = 0
        submitted_signals = []

        print("📊 Test Configuration:")
        print(f"   - Test duration: {test_config.test_duration}s")
        print(
            f"   - Signal generation interval: {test_config.signal_generation_interval}s"
        )
        print(f"   - Default signal timeout: {config.signal_default_timeout_seconds}s")
        print(f"   - Spread signal timeout: {config.signal_spread_timeout_seconds}s")
        print(f"   - Cleanup interval: {config.signal_cleanup_interval_seconds}s")
        print(f"   - Max concurrent signals: {config.signal_max_concurrent}")
        print()

        # Main test loop
        while time.time() - start_time < test_config.test_duration:
            current_time = time.time() - start_time

            # Generate signals periodically
            if (
                signal_counter == 0
                or (
                    current_time
                    - signal_counter * test_config.signal_generation_interval
                )
                >= test_config.signal_generation_interval
            ):
                signal_counter += 1

                # Create different types of signals to test different timeouts
                market_types = ["spread", "complement", "market-making", "default"]
                market_type = market_types[signal_counter % len(market_types)]

                signal = await create_test_signal(signal_counter, market_type)

                try:
                    signal_id = engine.process_signal(signal)
                    submitted_signals.append(
                        {
                            "id": signal_id,
                            "type": market_type,
                            "submitted_at": current_time,
                            "signal": signal,
                        }
                    )
                    print(
                        f"✅ Signal {signal_counter} ({market_type}) submitted: {signal_id}"
                    )
                except Exception as e:
                    print(f"❌ Failed to submit signal {signal_counter}: {e}")

            # Test duplicate signal submission
            if signal_counter > 0 and signal_counter % 5 == 0:
                # Try to submit a duplicate signal
                try:
                    last_signal = submitted_signals[-1]["signal"]
                    duplicate_id = engine.process_signal(last_signal)
                    print(
                        f"⚠️  Duplicate signal should have been rejected but got ID: {duplicate_id}"
                    )
                except Exception as e:
                    print(f"✅ Duplicate signal correctly rejected: {e}")

            # Check signal statuses
            if signal_counter > 0 and signal_counter % 3 == 0:
                print(f"\n📈 Signal Status Check (at {current_time:.1f}s):")
                for sig_info in submitted_signals[-5:]:  # Check last 5 signals
                    status = engine.get_signal_status(sig_info["id"])
                    age = current_time - sig_info["submitted_at"]
                    print(
                        f"   Signal {sig_info['id'][:12]}... ({sig_info['type']}) - Status: {status}, Age: {age:.1f}s"
                    )

            # Display metrics periodically
            if signal_counter > 0 and signal_counter % 10 == 0:
                print(f"\n📊 Signal Metrics (at {current_time:.1f}s):")
                metrics = engine.get_signal_metrics()
                for key, value in metrics.items():
                    if isinstance(value, float):
                        print(f"   {key}: {value:.2f}")
                    else:
                        print(f"   {key}: {value}")
                print()

            # Wait a bit before next iteration
            await asyncio.sleep(0.5)

        # Final metrics and status
        print("\n" + "=" * 60)
        print("🏁 Test Complete - Final Results")
        print("=" * 60)

        print("\n📊 Final Metrics:")
        final_metrics = engine.get_signal_metrics()
        for key, value in final_metrics.items():
            if isinstance(value, float):
                print(f"   {key}: {value:.2f}")
            else:
                print(f"   {key}: {value}")

        print("\n📈 Signal Status Summary:")
        status_counts = {}
        for sig_info in submitted_signals:
            status = engine.get_signal_status(sig_info["id"])
            status_counts[status] = status_counts.get(status, 0) + 1

        for status, count in status_counts.items():
            print(f"   {status}: {count} signals")

        print("\n✅ Test completed successfully!")
        print(f"   - Total signals submitted: {len(submitted_signals)}")
        print(f"   - Test duration: {time.time() - start_time:.1f}s")
        print(f"   - Signal manager running: {engine.is_signal_manager_running()}")

    finally:
        # Cleanup
        try:
            await engine.shutdown()
            print("🧹 Engine shutdown complete")
        except Exception as e:
            print(f"⚠️  Shutdown error: {e}")


async def test_signal_expiration():
    """Test that signals properly expire after their timeout."""
    print("\n🕒 Testing Signal Expiration")
    print("-" * 40)

    config = BotConfig()
    config.signal_default_timeout_seconds = 3.0  # Very short timeout for testing
    config.signal_cleanup_interval_seconds = 1.0  # Frequent cleanup

    engine = TradingEngine(config)

    try:
        # Submit a signal
        signal = await create_test_signal(1, "test")
        signal_id = engine.process_signal(signal)
        print(f"📨 Submitted signal: {signal_id}")

        # Check status immediately
        status = engine.get_signal_status(signal_id)
        print(f"   Initial status: {status}")

        # Wait for timeout
        print("⏳ Waiting for signal to expire...")
        await asyncio.sleep(4.0)

        # Check status after timeout
        status = engine.get_signal_status(signal_id)
        print(f"   Status after timeout: {status}")

        if status == "expired":
            print("✅ Signal correctly expired!")
        else:
            print(f"❌ Signal should have expired but status is: {status}")

    finally:
        await engine.shutdown()


async def test_signal_deduplication():
    """Test signal deduplication functionality."""
    print("\n🔄 Testing Signal Deduplication")
    print("-" * 40)

    config = BotConfig()
    config.signal_enable_deduplication = True
    config.signal_deduplication_window_seconds = 3.0

    engine = TradingEngine(config)

    try:
        # Submit original signal
        signal = await create_test_signal(1, "dedup-test")
        signal_id1 = engine.process_signal(signal)
        print(f"📨 First signal submitted: {signal_id1}")

        # Try to submit duplicate immediately
        try:
            signal_id2 = engine.process_signal(signal)
            print(f"❌ Duplicate should have been rejected but got: {signal_id2}")
        except Exception as e:
            print(f"✅ Duplicate correctly rejected: {type(e).__name__}")

        # Wait for deduplication window to expire
        print("⏳ Waiting for deduplication window to expire...")
        await asyncio.sleep(4.0)

        # Try to submit again - should work now
        signal_id3 = engine.process_signal(signal)
        print(f"📨 Signal after window expiry: {signal_id3}")

        if signal_id3 and signal_id3 != signal_id1:
            print("✅ Signal correctly accepted after deduplication window!")
        else:
            print("❌ Signal should have been accepted after window expiry")

    finally:
        await engine.shutdown()


if __name__ == "__main__":

    async def main():
        print("🧪 Signal Timeout Handling Test Suite")
        print("=" * 60)

        # Run main timeout test
        await test_signal_timeout_handling()

        # Run expiration test
        await test_signal_expiration()

        # Run deduplication test
        await test_signal_deduplication()

        print("\n🎉 All tests completed!")

    asyncio.run(main())
