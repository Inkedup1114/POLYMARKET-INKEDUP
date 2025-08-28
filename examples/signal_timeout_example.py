"""
Simple example demonstrating signal timeout handling.

This example shows how the signal manager automatically handles:
1. Signal timeout tracking
2. Automatic cleanup of expired signals
3. Signal deduplication
4. Processing metrics
"""

from inkedup_bot.signal_manager import SignalManager, SignalManagerConfig
from inkedup_bot.signals import TradingSignal


def simple_signal_processor(signal: TradingSignal) -> None:
    """Simple signal processor that just logs the signal."""
    print(
        f"🔄 Processing signal: {signal.signal_id} - {signal.market_slug} {signal.side} {signal.price}"
    )


def main():
    """Demonstrate basic signal timeout functionality."""
    print("📊 Signal Timeout Handling Example")
    print("=" * 50)

    # Create signal manager with short timeouts for demo
    config = SignalManagerConfig(
        default_signal_timeout=5.0,  # 5 second timeout
        cleanup_interval=2.0,  # Check every 2 seconds
        enable_deduplication=True,
        deduplication_window=3.0,  # 3 second dedup window
    )

    signal_manager = SignalManager(config)
    signal_manager.set_signal_processor(simple_signal_processor)

    # Create some test signals
    signals = [
        TradingSignal(
            market_slug="test-market-1",
            token_id="token-123",
            side="buy",
            price=0.55,
            size=100.0,
            signal_id="signal-1",
        ),
        TradingSignal(
            market_slug="test-market-2",
            token_id="token-456",
            side="sell",
            price=0.45,
            size=50.0,
            signal_id="signal-2",
        ),
    ]

    print("\n📨 Submitting signals:")
    for signal in signals:
        try:
            signal_id = signal_manager.submit_signal(signal)
            print(f"✅ Submitted: {signal_id}")
        except Exception as e:
            print(f"❌ Failed: {e}")

    # Try to submit duplicate
    print("\n🔄 Testing deduplication:")
    try:
        duplicate_id = signal_manager.submit_signal(signals[0])  # Same signal
        print(f"❌ Duplicate should have been rejected: {duplicate_id}")
    except Exception as e:
        print(f"✅ Duplicate correctly rejected: {type(e).__name__}")

    # Show metrics
    print("\n📊 Current metrics:")
    metrics = signal_manager.get_metrics()
    for key, value in metrics.items():
        print(f"   {key}: {value}")

    print("\n✅ Example complete!")
    print("\nNote: In a real application, you would:")
    print("1. Start the signal manager with await signal_manager.start()")
    print("2. Submit signals from your strategies")
    print("3. The manager automatically handles timeouts and cleanup")
    print("4. Stop with await signal_manager.stop()")


if __name__ == "__main__":
    main()
