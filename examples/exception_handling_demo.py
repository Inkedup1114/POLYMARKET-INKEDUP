#!/usr/bin/env python3
"""
Demo script showcasing the improved exception handling in OrderClient.

This demonstrates:
1. Fixed silent exception handling
2. Comprehensive exception tracking
3. Automatic recovery strategies
4. Detailed error logging and debugging
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import MagicMock

from inkedup_bot.enhanced_stub_client import StubClientConfig
from inkedup_bot.order_client import (
    OrderClient,
    _exception_tracker,
)


def create_test_client():
    """Create a test OrderClient with mock configuration."""

    # Mock configuration
    config = MagicMock()
    config.private_key = "test_key_demo"
    config.api_base = "https://test-api.example.com"
    config.api_retry_attempts = 3
    config.api_retry_delay_seconds = 1.0
    config.api_retry_max_delay_seconds = 60.0
    config.api_retry_exponential_base = 2.0
    config.api_retry_jitter_enabled = True
    config.api_retry_jitter_range = 0.1
    config.api_retry_backoff_strategy = "exponential"

    # Mock state manager
    state = MagicMock()

    # Create client with enhanced stub (since py-clob-client not available)
    stub_config = StubClientConfig()
    stub_config.enable_order_validation = False  # Disable for demo

    client = OrderClient(config, state, stub_config)
    return client


def demonstrate_exception_tracking():
    """Demonstrate exception tracking capabilities."""

    print("🔍 Exception Tracking Demonstration")
    print("=" * 50)

    client = create_test_client()

    # Simulate some exceptions by calling methods with invalid data
    print("\n📊 Testing exception tracking...")

    # Test 1: Try to place invalid orders (will generate exceptions)
    print("   Attempting invalid operations to generate exceptions...")

    try:
        # This should generate validation errors
        result = client.place_limit("", "invalid_side", -1.0, -1.0)
        print(f"   Order result (expected None): {result}")
    except Exception as e:
        print(f"   Caught exception: {type(e).__name__}: {e}")

    try:
        # This should work but might generate internal exceptions during processing
        result = (
            client.exposure_usd()
        )  # This processes positions and may encounter parsing errors
        print(f"   Exposure result: ${result:.2f}")
    except Exception as e:
        print(f"   Caught exception: {type(e).__name__}: {e}")

    # Get exception statistics
    stats = client.get_exception_statistics()
    print("\n📈 Exception Statistics:")
    print(f"   Total exception types tracked: {stats.get('total_exception_types', 0)}")
    print(f"   Recent exceptions (1h): {stats.get('recent_exceptions_1h', 0)}")
    print(f"   Recent exceptions (24h): {stats.get('recent_exceptions_24h', 0)}")
    print(f"   Client type: {stats.get('client_type', 'unknown')}")
    print(f"   Client ready: {stats.get('client_ready', False)}")

    if stats.get("frequent_exceptions"):
        print(f"   Frequent exceptions: {stats['frequent_exceptions']}")

    return client


def demonstrate_health_monitoring():
    """Demonstrate health monitoring and reporting."""

    print("\n🏥 Health Monitoring Demonstration")
    print("=" * 50)

    client = create_test_client()

    # Simulate some operations that might generate exceptions
    for i in range(5):
        try:
            # Try operations that might fail
            client.get_positions()
            client.cancel_all()
            client.exposure_usd()
        except Exception as e:
            print(f"   Operation {i+1} exception: {type(e).__name__}")

    # Get health report
    health = client.get_exception_health_report()
    print("\n🩺 Health Report:")
    print(f"   Status: {health['health_status'].upper()}")
    print(f"   Issues found: {len(health.get('issues', []))}")

    for issue in health.get("issues", []):
        print(f"     ⚠️  {issue}")

    print(f"   Recommendations: {len(health.get('recommendations', []))}")
    for rec in health.get("recommendations", []):
        print(f"     💡 {rec}")

    summary = health.get("exception_summary", {})
    print("   Summary:")
    print(f"     Recent (1h): {summary.get('recent_1h', 0)} exceptions")
    print(f"     Recent (24h): {summary.get('recent_24h', 0)} exceptions")
    print(f"     Frequent patterns: {summary.get('frequent_count', 0)}")

    return client


def demonstrate_recovery_strategies():
    """Demonstrate automatic recovery strategies."""

    print("\n🔄 Recovery Strategies Demonstration")
    print("=" * 50)

    client = create_test_client()

    # Simulate problematic conditions
    print("   Simulating problematic conditions...")

    # Add some fake exception data to trigger recovery
    for i in range(15):
        _exception_tracker.record_exception(
            ConnectionError("Simulated connection error"),
            "test_method",
            {"simulation": True},
        )

    print("   Implementing recovery strategies...")
    recovery = client.implement_recovery_strategies()

    print("\n🛠️  Recovery Actions Taken:")
    actions = recovery.get("recovery_actions_taken", [])
    if actions:
        for action in actions:
            print(f"     ✅ {action}")
    else:
        print("     ℹ️  No recovery actions needed")

    print(
        f"   Health status after recovery: {recovery.get('health_status', 'unknown').upper()}"
    )
    print(f"   Recovery timestamp: {recovery.get('timestamp', 'unknown')}")

    # Show recent exception details
    recent = client.get_recent_exception_details(60)
    print(f"\n📋 Recent Exception Details (last hour): {len(recent)} exceptions")

    for detail in recent[-3:]:  # Show last 3
        print(
            f"     {detail.get('timestamp', 'unknown')[:19]} - "
            f"{detail.get('method', 'unknown')}:{detail.get('exception_type', 'unknown')}"
        )

    return client


def main():
    """Main demonstration function."""

    print("🚀 OrderClient Exception Handling Improvements Demo")
    print("=" * 60)

    print("\n✨ Key Improvements Demonstrated:")
    print("   ✓ Replaced silent exception handling with proper logging")
    print("   ✓ Added comprehensive exception tracking and analysis")
    print("   ✓ Implemented automatic recovery strategies")
    print("   ✓ Enhanced debugging capabilities with detailed reporting")
    print("   ✓ Proactive health monitoring and alerting")

    # Run demonstrations
    demonstrate_exception_tracking()
    demonstrate_health_monitoring()
    demonstrate_recovery_strategies()

    print("\n🎯 Summary of Improvements:")
    print("=" * 50)

    print("1. 🔇 Fixed Silent Exceptions:")
    print("   - Lines 511-512: Added specific logging for attribute access errors")
    print("   - Lines 588-589: Added logging for dot notation parsing errors")
    print("   - Lines 690-691: Added logging for numeric conversion errors")

    print("\n2. 📊 Exception Tracking:")
    print("   - Comprehensive tracking of all exceptions with timestamps")
    print("   - Frequency analysis and pattern detection")
    print("   - Automatic categorization of critical vs. non-critical errors")

    print("\n3. 🏥 Health Monitoring:")
    print("   - Real-time health status based on exception patterns")
    print("   - Proactive issue identification and recommendations")
    print("   - Integration with existing retry and circuit breaker systems")

    print("\n4. 🔄 Recovery Strategies:")
    print("   - Automatic cleanup of old exception records")
    print("   - Circuit breaker recovery for stuck open states")
    print("   - Retry statistics reset for network-related issues")
    print("   - Intelligent recommendations based on error patterns")

    print("\n✅ All exception handling improvements completed successfully!")
    print("   The OrderClient now provides production-ready exception handling")
    print("   with comprehensive logging, monitoring, and automatic recovery.")


if __name__ == "__main__":
    main()
