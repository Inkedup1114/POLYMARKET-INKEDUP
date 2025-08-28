#!/usr/bin/env python3
"""
Example demonstrating the risk management fallback system.

This script shows how the risk system gracefully handles database failures
by switching between NORMAL, DEGRADED, and EMERGENCY_HALT modes.
"""

from unittest.mock import Mock, patch

from inkedup_bot.config import BotConfig
from inkedup_bot.order_client import OrderClient
from inkedup_bot.risk.manager import RiskManager, RiskSystemMode
from inkedup_bot.state import StateManager


def create_mock_config():
    """Create a mock configuration for demonstration."""
    config = Mock(spec=BotConfig)
    # Set up proper attributes
    config.global_risk_cap = 10000.0
    config.position_risk_cap = 1000.0
    config.market_risk_cap = 2000.0
    config.per_market_risk_cap = 2000.0
    config.per_outcome_risk_cap = 1500.0
    config.max_position_size = 500.0
    config.max_order_size = 100.0
    config.slippage_tolerance_bps = 50
    config.order_timeout_seconds = 30
    config.price_precision = 4
    config.size_precision = 4
    config.default_order_type = "GTC"
    config.complement_arb_min_deviation = 0.01
    config.complement_arb_max_deviation = 0.20
    config.complement_arb_base_size = 10.0
    config.complement_arb_max_size = 100.0
    config.complement_arb_size_scaling = 50.0
    config.risk_validation_enabled = True
    config.risk_strict_mode = False
    return config


def demonstrate_normal_mode():
    """Demonstrate normal operation mode."""
    print("=== DEMONSTRATING NORMAL MODE ===")

    # Set up components
    config = create_mock_config()
    order_client = Mock(spec=OrderClient)
    order_client.ready.return_value = True
    state_manager = StateManager(":memory:")  # In-memory database

    # Initialize risk manager
    risk_manager = RiskManager(config, order_client, state_manager)
    state_manager.set_risk_manager(risk_manager)

    print(f"Risk system mode: {risk_manager.mode.value}")
    print(f"Database failure count: {risk_manager.database_failure_count}")

    # Perform some normal operations
    try:
        result = risk_manager.preflight("TEST_TOKEN", 100.0, "test_market", "yes")
        print(f"Preflight check passed: {result}")
    except Exception as e:
        print(f"Preflight check failed: {e}")

    # Get system status
    status = risk_manager.get_risk_system_status()
    print(
        f"System status: mode={status['mode']}, failures={status['database_failure_count']}"
    )
    print()


def demonstrate_degraded_mode():
    """Demonstrate degraded mode with database issues."""
    print("=== DEMONSTRATING DEGRADED MODE ===")

    # Set up components
    config = create_mock_config()
    order_client = Mock(spec=OrderClient)
    order_client.ready.return_value = True
    state_manager = StateManager(":memory:")
    risk_manager = RiskManager(config, order_client, state_manager)
    state_manager.set_risk_manager(risk_manager)

    # Set up some position data in fallback cache
    risk_manager.fallback_cache.update_position(
        "EXISTING_TOKEN",
        {
            "token_id": "EXISTING_TOKEN",
            "notional_value": 500.0,
            "market_slug": "test_market",
            "outcome_type": "yes",
        },
    )

    # Simulate database failures to trigger degraded mode
    print("Simulating database failures...")
    for i in range(risk_manager.max_failure_threshold):
        risk_manager._handle_database_failure(
            "test_operation", Exception(f"Simulated error {i+1}")
        )

    print(f"Risk system mode: {risk_manager.mode.value}")
    print(f"Database failure count: {risk_manager.database_failure_count}")

    # Test operations in degraded mode
    with patch.object(
        state_manager, "get_total_exposure", side_effect=Exception("Database error")
    ):
        try:
            result = risk_manager.preflight("NEW_TOKEN", 100.0, "test_market", "no")
            print(f"Preflight check in degraded mode passed: {result}")
        except Exception as e:
            print(f"Preflight check failed: {e}")

    # Show cache statistics
    cache_stats = risk_manager.fallback_cache.get_cache_stats()
    print(f"Cache stats: {cache_stats}")
    print()


def demonstrate_emergency_halt():
    """Demonstrate emergency halt mode."""
    print("=== DEMONSTRATING EMERGENCY HALT MODE ===")

    # Set up components
    config = create_mock_config()
    order_client = Mock(spec=OrderClient)
    order_client.ready.return_value = True
    state_manager = StateManager(":memory:")
    risk_manager = RiskManager(config, order_client, state_manager)

    # Force emergency halt
    print("Triggering emergency halt...")
    risk_manager.set_emergency_halt("Demonstration of emergency halt")

    print(f"Risk system mode: {risk_manager.mode.value}")

    # Test that trading is blocked
    try:
        result = risk_manager.preflight("ANY_TOKEN", 100.0)
        print(f"Unexpected: preflight passed in emergency halt: {result}")
    except RuntimeError as e:
        print(f"Expected: trading blocked - {e}")

    # Show system status
    status = risk_manager.get_risk_system_status()
    print(f"System status: mode={status['mode']}")
    print()


def demonstrate_recovery():
    """Demonstrate recovery from degraded mode."""
    print("=== DEMONSTRATING RECOVERY ===")

    # Set up components
    config = create_mock_config()
    order_client = Mock(spec=OrderClient)
    order_client.ready.return_value = True
    state_manager = StateManager(":memory:")
    risk_manager = RiskManager(config, order_client, state_manager)

    # Put system in degraded mode
    risk_manager.mode = RiskSystemMode.DEGRADED
    risk_manager.database_failure_count = 5
    print(f"Starting mode: {risk_manager.mode.value}")
    print(f"Starting failure count: {risk_manager.database_failure_count}")

    # Simulate database recovery
    print("Simulating database recovery...")
    with patch.object(risk_manager, "_check_database_health", return_value=True):
        recovery_success = risk_manager.force_database_check()
        print(f"Recovery successful: {recovery_success}")
        print(f"New mode: {risk_manager.mode.value}")
        print(f"New failure count: {risk_manager.database_failure_count}")
    print()


def demonstrate_manual_operations():
    """Demonstrate manual operations and monitoring."""
    print("=== DEMONSTRATING MANUAL OPERATIONS ===")

    config = create_mock_config()
    order_client = Mock(spec=OrderClient)
    order_client.ready.return_value = True
    state_manager = StateManager(":memory:")
    risk_manager = RiskManager(config, order_client, state_manager)

    # Show initial status
    status = risk_manager.get_risk_system_status()
    print("Initial system status:")
    print(f"  Mode: {status['mode']}")
    print(f"  Trading enabled: {status['trading_enabled']}")
    print(f"  Failure count: {status['database_failure_count']}")

    # Manual operations
    print("\nManual operations:")

    # Add some database failures
    risk_manager.database_failure_count = 3
    print(f"  Set failure count to: {risk_manager.database_failure_count}")

    # Reset failure count
    risk_manager.reset_database_failure_count()
    print(f"  Reset failure count to: {risk_manager.database_failure_count}")

    # Force emergency halt
    risk_manager.set_emergency_halt("Manual test")
    print(f"  Forced emergency halt: {risk_manager.mode.value}")

    # Clear emergency halt (simulate healthy database)
    with patch.object(risk_manager, "_check_database_health", return_value=True):
        cleared = risk_manager.clear_emergency_halt()
        print(f"  Cleared emergency halt: {cleared}, mode: {risk_manager.mode.value}")

    print()


def main():
    """Run all demonstrations."""
    print("Risk Management Fallback System Demonstration")
    print("=" * 50)
    print()

    demonstrate_normal_mode()
    demonstrate_degraded_mode()
    demonstrate_emergency_halt()
    demonstrate_recovery()
    demonstrate_manual_operations()

    print("Demonstration complete!")
    print()
    print("Key takeaways:")
    print("1. System automatically detects database failures")
    print("2. Graceful degradation to in-memory cache")
    print("3. Emergency halt protects against complete failures")
    print("4. Automatic recovery when database is restored")
    print("5. Manual operations available for operational control")


if __name__ == "__main__":
    main()
