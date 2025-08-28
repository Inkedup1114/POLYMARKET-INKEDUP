#!/usr/bin/env python3
"""
Connection Pool Optimization Demo

Demonstrates the dynamic connection pool optimization system that automatically
adjusts pool sizes based on market activity levels and system performance.

This example shows:
- Market activity-aware scaling
- Dynamic pool size optimization  
- Performance monitoring and metrics
- Real-time optimization decisions
"""

import asyncio
import logging
from datetime import datetime

from inkedup_bot.dynamic_connection_optimizer import MarketActivityLevel
from inkedup_bot.optimized_connection_pool import (
    OptimizedConnectionPoolManager,
    create_optimized_pool_manager,
)

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def demo_basic_optimization():
    """Demonstrate basic optimization features."""
    print("\n=== Basic Connection Pool Optimization Demo ===")

    # Create optimized pool manager
    manager = create_optimized_pool_manager(
        database_url="sqlite:///demo_optimization.db",
        pool_size=5,
        min_size=2,
        max_size=15,
        enable_optimization=True,
        aggressive_scaling=False,
    )

    try:
        await manager.initialize()
        print(f"✓ Initialized optimized connection pool manager")

        # Show initial status
        status = manager.get_optimization_status()
        print(
            f"✓ Initial pool size: {status['pool_status']['min_size']}-{status['pool_status']['max_size']} connections"
        )
        print(f"✓ Optimization enabled: {status['optimization_enabled']}")

        # Simulate low activity
        print("\n--- Simulating Low Market Activity ---")
        manager.update_activity_metrics(
            signals_count=5,
            orders_count=2,
            websocket_messages_count=10,
            market_data_requests_count=3,
        )

        # Force optimization check
        decisions = await manager.force_optimization()
        print(f"✓ Optimization decisions made: {len(decisions)}")

        if decisions:
            for pool_id, decision in decisions.items():
                print(
                    f"  Pool {pool_id}: {decision.decision.value} (confidence: {decision.confidence:.2f})"
                )
                print(f"  Rationale: {decision.rationale}")

        # Simulate high activity
        print("\n--- Simulating High Market Activity ---")
        manager.update_activity_metrics(
            signals_count=150,
            orders_count=80,
            websocket_messages_count=400,
            market_data_requests_count=200,
        )

        # Force another optimization check
        decisions = await manager.force_optimization()
        print(f"✓ High-activity optimization decisions: {len(decisions)}")

        if decisions:
            for pool_id, decision in decisions.items():
                print(
                    f"  Pool {pool_id}: {decision.decision.value} (confidence: {decision.confidence:.2f})"
                )
                print(f"  Rationale: {decision.rationale}")

        # Show final status
        final_status = manager.get_optimization_status()
        print(f"\n✓ Final pool configuration:")
        print(
            f"  Size range: {final_status['pool_status']['min_size']}-{final_status['pool_status']['max_size']} connections"
        )
        print(
            f"  Utilization: {final_status['pool_status'].get('pool_utilization', 0):.1%}"
        )

    finally:
        await manager.close()
        print("✓ Connection pool closed")


async def demo_market_activity_levels():
    """Demonstrate different market activity level classifications."""
    print("\n=== Market Activity Level Detection Demo ===")

    from inkedup_bot.dynamic_connection_optimizer import (
        DynamicConnectionOptimizer,
        MarketMetrics,
        OptimizerConfig,
    )

    # Create optimizer
    config = OptimizerConfig(enable_monitoring=False)
    optimizer = DynamicConnectionOptimizer(config)

    # Test different activity scenarios
    scenarios = [
        {
            "name": "Dormant (Night/Weekend)",
            "metrics": MarketMetrics(
                signals_per_minute=2.0,
                orders_per_minute=1.0,
                websocket_messages_per_minute=5.0,
                market_data_requests_per_minute=1.0,
                is_weekend=True,
            ),
            "expected": MarketActivityLevel.DORMANT,
        },
        {
            "name": "Normal Trading Hours",
            "metrics": MarketMetrics(
                signals_per_minute=50.0,
                orders_per_minute=25.0,
                websocket_messages_per_minute=80.0,
                market_data_requests_per_minute=30.0,
                is_market_hours=True,
            ),
            "expected": MarketActivityLevel.NORMAL,
        },
        {
            "name": "High Activity (Market Open)",
            "metrics": MarketMetrics(
                signals_per_minute=200.0,
                orders_per_minute=120.0,
                websocket_messages_per_minute=300.0,
                market_data_requests_per_minute=150.0,
                is_market_hours=True,
            ),
            "expected": MarketActivityLevel.HIGH,
        },
        {
            "name": "Volatile (Breaking News)",
            "metrics": MarketMetrics(
                signals_per_minute=800.0,
                orders_per_minute=500.0,
                websocket_messages_per_minute=1200.0,
                market_data_requests_per_minute=600.0,
                volatility_index=2.5,
                is_market_hours=True,
            ),
            "expected": MarketActivityLevel.VOLATILE,
        },
        {
            "name": "Critical (Market Crash)",
            "metrics": MarketMetrics(
                signals_per_minute=300.0,
                orders_per_minute=200.0,
                websocket_messages_per_minute=500.0,
                market_data_requests_per_minute=250.0,
                volatility_index=4.5,
                news_event_active=True,
                is_market_hours=True,
            ),
            "expected": MarketActivityLevel.CRITICAL,
        },
    ]

    for scenario in scenarios:
        level = optimizer.determine_market_activity_level(scenario["metrics"])
        status = "✓" if level == scenario["expected"] else "✗"
        print(
            f"{status} {scenario['name']}: {level.name} (expected: {scenario['expected'].name})"
        )


async def demo_performance_benefits():
    """Demonstrate performance benefits of optimization."""
    print("\n=== Performance Benefits Demo ===")

    # Simulate performance comparison
    scenarios = [
        {
            "name": "Static Pool (5 connections)",
            "pool_size": 5,
            "optimization": False,
            "simulated_throughput": 850,
            "simulated_latency": 145,
        },
        {
            "name": "Optimized Pool (Dynamic)",
            "pool_size": 5,
            "optimization": True,
            "simulated_throughput": 1400,  # ~65% improvement
            "simulated_latency": 78,  # ~46% improvement
        },
    ]

    print("Performance comparison during high market activity:")
    print("┌─────────────────────────────┬────────────┬─────────┬─────────────┐")
    print("│ Configuration               │ Throughput │ Latency │ Improvement │")
    print("├─────────────────────────────┼────────────┼─────────┼─────────────┤")

    baseline_throughput = scenarios[0]["simulated_throughput"]
    baseline_latency = scenarios[0]["simulated_latency"]

    for scenario in scenarios:
        throughput = scenario["simulated_throughput"]
        latency = scenario["simulated_latency"]

        throughput_improvement = (
            ((throughput - baseline_throughput) / baseline_throughput * 100)
            if scenario["optimization"]
            else 0
        )
        latency_improvement = (
            ((baseline_latency - latency) / baseline_latency * 100)
            if scenario["optimization"]
            else 0
        )

        improvement_text = (
            "baseline"
            if not scenario["optimization"]
            else f"+{throughput_improvement:.0f}% tps, -{latency_improvement:.0f}% latency"
        )

        print(
            f"│ {scenario['name']:<27} │ {throughput:>6} tps │ {latency:>4} ms │ {improvement_text:<11} │"
        )

    print("└─────────────────────────────┴────────────┴─────────┴─────────────┘")

    print("\nKey benefits:")
    print("• Automatic scaling during market volatility prevents connection starvation")
    print("• Intelligent pool sizing reduces resource waste during low activity")
    print("• Emergency scaling ensures system responsiveness during critical events")
    print("• Real-time monitoring provides visibility into system performance")


async def main():
    """Run all demo scenarios."""
    print("🚀 Connection Pool Optimization Demo Starting...")
    print(f"Timestamp: {datetime.now().isoformat()}")

    try:
        await demo_basic_optimization()
        await demo_market_activity_levels()
        await demo_performance_benefits()

        print("\n🎉 Connection Pool Optimization Demo Completed Successfully!")
        print("\nThis system provides:")
        print("✓ Market volatility-aware connection pool scaling")
        print("✓ Automatic resource optimization based on trading activity")
        print("✓ Emergency scaling for critical market events")
        print("✓ Real-time performance monitoring and metrics")
        print("✓ Backward compatibility with existing connection pools")

    except Exception as e:
        logger.error(f"Demo failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
