#!/usr/bin/env python3
"""
Demo script showcasing the comprehensive retry logic with circuit breakers,
failure classification, and monitoring capabilities.
"""

import os
import random

# Add project to path
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from inkedup_bot.circuit_breaker import CircuitBreakerConfig
from inkedup_bot.enhanced_retry_client import (
    ResilientClientConfig,
    ResilientRetryClient,
)


class UnreliableAPIClient:
    """Simulates an unreliable API for testing retry logic."""

    def __init__(self):
        self.call_count = 0
        self.failure_rate = 0.7  # 70% failure rate initially

    def unreliable_operation(self) -> str:
        """An operation that fails randomly."""
        self.call_count += 1

        # Simulate different types of failures
        if random.random() < self.failure_rate:
            failure_type = random.choice(
                ["network_error", "rate_limit", "server_error", "timeout"]
            )

            if failure_type == "network_error":
                raise ConnectionError("Connection refused by server")
            elif failure_type == "rate_limit":
                raise Exception("429 Too Many Requests")
            elif failure_type == "server_error":
                raise Exception("503 Service Unavailable - Server overloaded")
            elif failure_type == "timeout":
                raise TimeoutError("Request timed out")

        return f"Success! (call #{self.call_count})"

    def improve_reliability(self):
        """Simulate API reliability improving over time."""
        self.failure_rate = max(0.1, self.failure_rate - 0.1)
        print(f"🔧 API reliability improved. Failure rate now: {self.failure_rate:.1%}")


def main():
    """Demonstrate the comprehensive retry system."""

    print("🚀 Enhanced Retry System Demo")
    print("=" * 50)

    # Configure circuit breaker for aggressive testing
    circuit_config = CircuitBreakerConfig(
        failure_threshold=3,  # Open after 3 failures
        recovery_timeout=5.0,  # Try recovery after 5 seconds
        half_open_max_calls=2,  # Allow 2 calls in half-open state
        success_threshold=2,  # Need 2 successes to close
    )

    # Configure resilient client
    resilient_config = ResilientClientConfig(
        circuit_breaker_enabled=True,
        circuit_breaker_config=circuit_config,
        default_max_attempts=4,
        default_base_delay=1.0,
        default_max_delay=5.0,
    )

    # Create resilient client
    retry_client = ResilientRetryClient(
        client_name="demo_api_client", config=resilient_config
    )

    # Create unreliable API client
    api_client = UnreliableAPIClient()

    print("\n📊 Initial Health Status:")
    health = retry_client.get_health_summary()
    print(f"   Status: {health['status']}")
    print(f"   Operations: {health['operations_count']}")

    print("\n🎯 Testing Enhanced Retry Logic...")
    print("-" * 50)

    # Phase 1: High failure rate - should trigger circuit breaker
    print("\n📍 Phase 1: High Failure Rate (70%)")
    for i in range(8):
        try:
            result = retry_client.call(
                operation_name="api_call",
                func=api_client.unreliable_operation,
                context={"phase": "high_failure"},
            )
            print(f"✅ Call {i+1}: {result}")
        except Exception as e:
            print(f"❌ Call {i+1}: Failed - {e}")

        # Small delay between calls
        time.sleep(0.5)

    # Show circuit breaker status
    cb_metrics = retry_client.circuit_breaker.get_metrics()
    print(f"\n🔌 Circuit Breaker Status: {cb_metrics['state'].upper()}")
    print(f"   Failure Count: {cb_metrics['failure_count']}")
    print(f"   Success Count: {cb_metrics['success_count']}")

    # Show monitoring alerts
    alerts = retry_client.get_monitoring_alerts()
    print(f"\n🚨 Monitoring Alerts: {len(alerts)} active")
    for alert in alerts[:3]:  # Show first 3 alerts
        print(f"   [{alert['severity'].upper()}] {alert['message']}")

    # Phase 2: Improve API reliability
    print("\n📍 Phase 2: Improving API Reliability")
    api_client.improve_reliability()  # Reduce failure rate to 60%
    api_client.improve_reliability()  # Reduce failure rate to 50%
    api_client.improve_reliability()  # Reduce failure rate to 40%

    # Wait for circuit breaker recovery
    if cb_metrics["state"] == "open":
        print("⏳ Waiting for circuit breaker recovery...")
        time.sleep(6)  # Wait longer than recovery timeout

    # Phase 3: Test recovery
    print("\n📍 Phase 3: Testing Recovery")
    for i in range(5):
        try:
            result = retry_client.call(
                operation_name="api_call",
                func=api_client.unreliable_operation,
                context={"phase": "recovery"},
            )
            print(f"✅ Recovery Call {i+1}: {result}")
        except Exception as e:
            print(f"❌ Recovery Call {i+1}: Failed - {e}")

        time.sleep(0.5)

    # Final status
    print("\n📊 Final Status Report:")
    print("=" * 50)

    # Overall health
    health = retry_client.get_health_summary()
    print(f"Overall Health: {health['status'].upper()}")
    print(f"Total Operations: {health['operations_count']}")
    print(f"Success Rate: {health['overall_success_rate']:.1f}%")
    print(f"Unresolved Alerts: {health['unresolved_alerts']}")

    # Operation-specific metrics
    operation_health = retry_client.get_operation_health("api_call")
    print(f"\nAPI Call Operation Health: {operation_health['health_status'].upper()}")
    print(f"   Success Rate: {operation_health.get('local_success_rate', 0):.1f}%")
    print(f"   Total Calls: {operation_health.get('local_total_calls', 0)}")
    print(
        f"   Circuit Breaker Trips: {operation_health.get('local_circuit_breaker_trips', 0)}"
    )

    # Circuit breaker final status
    cb_final = retry_client.circuit_breaker.get_metrics()
    print(f"\nCircuit Breaker Final State: {cb_final['state'].upper()}")
    print(f"   Total Failures: {cb_final['failure_count']}")
    print(f"   Total Successes: {cb_final['success_count']}")

    # Monitoring summary
    monitoring_metrics = retry_client.get_monitoring_metrics()
    if monitoring_metrics:
        api_metrics = monitoring_metrics.get("api_call", {})
        print("\nMonitoring Summary:")
        print(f"   Average Duration: {api_metrics.get('average_duration', 0):.2f}s")
        print(f"   Average Retry Delay: {api_metrics.get('average_delay', 0):.2f}s")
        print(f"   Error Distribution: {api_metrics.get('error_counts', {})}")

    print("\n✨ Demo completed! The enhanced retry system demonstrated:")
    print("   ✓ Exponential backoff with jitter")
    print("   ✓ Circuit breaker pattern (OPEN → HALF_OPEN → CLOSED)")
    print("   ✓ Comprehensive failure classification")
    print("   ✓ Real-time monitoring and alerting")
    print("   ✓ Adaptive retry strategies based on error types")


if __name__ == "__main__":
    main()
