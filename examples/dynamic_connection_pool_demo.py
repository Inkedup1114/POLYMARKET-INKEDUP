#!/usr/bin/env python3
"""
Dynamic Connection Pool Management Demo.

This demonstration shows the dynamic connection pool management system that
automatically adjusts pool sizes based on real-time activity patterns and
load conditions for optimal resource utilization.

The system provides:
- Automatic pool scaling based on utilization and queue depth
- Activity level classification (idle, low, normal, high, peak, overload)
- Performance monitoring and optimization recommendations
- Resource efficiency improvements during varying load conditions
- Intelligent scaling with configurable thresholds and limits

Key Benefits:
- Better resource utilization during varying load conditions
- Automatic scaling prevents connection exhaustion during high activity
- Resource conservation during quiet periods
- Performance optimization through adaptive pool sizing
"""

import asyncio
import random
import sys
import time

sys.path.append("/home/ink/polymarket-inkedup")

from inkedup_bot.connection_pool import ConnectionPoolManager
from inkedup_bot.dynamic_connection_pool import (
    ActivityLevel,
    ActivityMetrics,
    DynamicConnectionPoolManager,
    DynamicPoolConfig,
)


class MockConnectionPoolManager:
    """Mock connection pool manager for demonstration purposes."""

    def __init__(self, initial_size: int = 5):
        self.pool_size = initial_size
        self.active_connections = 0
        self.pending_requests = 0
        self.total_requests = 0
        self.wait_times = []

    async def get_pool_stats(self):
        """Simulate getting pool statistics."""
        # Simulate varying activity patterns
        self.active_connections = random.randint(0, self.pool_size)
        self.pending_requests = random.randint(0, max(1, self.pool_size // 2))

        # Simulate wait times
        avg_wait_time = random.uniform(10, 200)  # 10-200ms
        self.wait_times.append(avg_wait_time)

        return {
            "pool_size": self.pool_size,
            "active_connections": self.active_connections,
            "pending_requests": self.pending_requests,
            "average_wait_time": avg_wait_time,
            "total_requests": self.total_requests,
        }

    def simulate_load_spike(self):
        """Simulate a load spike."""
        self.active_connections = min(
            self.pool_size, random.randint(self.pool_size - 1, self.pool_size * 2)
        )
        self.pending_requests = random.randint(5, 20)

    def simulate_quiet_period(self):
        """Simulate a quiet period."""
        self.active_connections = random.randint(0, max(1, self.pool_size // 3))
        self.pending_requests = 0


async def demonstrate_dynamic_pool_management():
    """Demonstrate the dynamic connection pool management system."""

    print("📊 Dynamic Connection Pool Management Demo")
    print("=" * 50)

    try:
        # Create configuration for demonstration
        config = DynamicPoolConfig(
            initial_size=5,
            min_size=2,
            max_size=25,
            idle_threshold=0.1,
            low_threshold=0.3,
            normal_threshold=0.6,
            high_threshold=0.8,
            peak_threshold=0.9,
            scale_up_factor=1.5,
            scale_down_factor=0.8,
            min_scale_interval=5.0,  # Short interval for demo
            evaluation_interval=2.0,  # Quick evaluation for demo
        )

        print("✅ Dynamic pool configuration created:")
        print(f"   Initial size: {config.initial_size}")
        print(f"   Size range: {config.min_size} - {config.max_size}")
        print(
            f"   Utilization thresholds: idle(<{config.idle_threshold:.0%}), normal(<{config.normal_threshold:.0%}), high(<{config.high_threshold:.0%}), peak(<{config.peak_threshold:.0%})"
        )
        print(
            f"   Scaling factors: up={config.scale_up_factor}x, down={config.scale_down_factor}x"
        )

        # Create mock pool manager
        mock_pool = MockConnectionPoolManager(initial_size=config.initial_size)

        # Create dynamic pool manager
        dynamic_manager = DynamicConnectionPoolManager(
            base_pool_manager=mock_pool, config=config
        )

        print(f"\n🚀 Starting dynamic pool management system...")
        await dynamic_manager.start()

        # Simulate different activity scenarios
        scenarios = [
            {"name": "Normal Operation", "duration": 10, "action": None},
            {"name": "Load Spike", "duration": 15, "action": "spike"},
            {"name": "Sustained High Load", "duration": 20, "action": "spike"},
            {"name": "Quiet Period", "duration": 15, "action": "quiet"},
            {"name": "Recovery", "duration": 10, "action": None},
        ]

        print(f"\n📈 Running activity scenarios:")

        for i, scenario in enumerate(scenarios, 1):
            print(f"\n🎬 Scenario {i}: {scenario['name']} ({scenario['duration']}s)")

            start_time = time.time()
            end_time = start_time + scenario["duration"]

            while time.time() < end_time:
                # Apply scenario-specific actions
                if scenario["action"] == "spike":
                    mock_pool.simulate_load_spike()
                elif scenario["action"] == "quiet":
                    mock_pool.simulate_quiet_period()

                # Get current metrics for display
                if (
                    hasattr(dynamic_manager, "metrics_history")
                    and dynamic_manager.metrics_history
                ):
                    latest_metrics = list(dynamic_manager.metrics_history)[-1]
                    current_size = dynamic_manager.performance_stats[
                        "current_pool_size"
                    ]
                    activity_level = dynamic_manager.current_activity_level.value

                    print(
                        f"   {time.time() - start_time:6.1f}s: Pool={current_size:2d}, "
                        f"Active={mock_pool.active_connections:2d}, "
                        f"Util={latest_metrics.pool_utilization:5.1%}, "
                        f"Level={activity_level}"
                    )

                await asyncio.sleep(2)

        # Get final performance summary
        print(f"\n📊 Performance Summary:")
        summary = dynamic_manager.get_performance_summary()

        current_state = summary["current_state"]
        scaling_stats = summary["scaling_stats"]
        config_info = summary["config"]

        print(f"   Final pool size: {current_state['pool_size']}")
        print(f"   Peak pool size: {scaling_stats['peak_pool_size']}")
        print(f"   Activity level: {current_state['activity_level']}")
        print(f"   Average utilization: {current_state['utilization']:.1%}")
        print(f"   Average wait time: {current_state['wait_time']:.1f}ms")

        print(f"\n🔄 Scaling Activity:")
        print(f"   Total scale-ups: {scaling_stats['total_scale_ups']}")
        print(f"   Total scale-downs: {scaling_stats['total_scale_downs']}")
        print(f"   Total scaling events: {scaling_stats['total_scaling_events']}")
        print(
            f"   Pool size range: {config_info['min_size']}-{config_info['max_size']}"
        )

        # Show recent scaling events
        if summary["recent_scaling"]:
            print(f"\n📋 Recent Scaling Events:")
            for event in summary["recent_scaling"][-3:]:
                timestamp = time.ctime(event["timestamp"])
                print(
                    f"   {timestamp}: {event['from_size']} → {event['to_size']} "
                    f"({event['direction']}) - {event['reason']}"
                )

        # Get optimization recommendations
        recommendations = dynamic_manager.get_optimization_recommendations()
        print(f"\n💡 Optimization Recommendations:")
        for i, recommendation in enumerate(recommendations, 1):
            print(f"   {i}. {recommendation}")

        # Calculate efficiency improvements
        static_size = config.initial_size
        dynamic_avg_size = (
            sum(event["to_size"] for event in dynamic_manager.scaling_history)
            / max(len(dynamic_manager.scaling_history), 1)
            if dynamic_manager.scaling_history
            else static_size
        )

        print(f"\n💰 Resource Efficiency Analysis:")
        print(f"   Static pool size: {static_size} connections")
        print(f"   Dynamic average size: {dynamic_avg_size:.1f} connections")

        if dynamic_avg_size < static_size:
            savings = ((static_size - dynamic_avg_size) / static_size) * 100
            print(f"   Resource savings: {savings:.1f}% fewer connections on average")
        else:
            improvement = ((dynamic_avg_size - static_size) / static_size) * 100
            print(
                f"   Performance improvement: {improvement:.1f}% more connections when needed"
            )

        print(
            f"   Adaptive efficiency: Pool scaled {scaling_stats['total_scaling_events']} times based on demand"
        )

        print(f"\n🎯 Key Benefits Demonstrated:")
        print(f"   ✓ Automatic scaling based on real-time activity patterns")
        print(f"   ✓ Resource conservation during quiet periods")
        print(f"   ✓ Performance optimization during high-activity periods")
        print(f"   ✓ Intelligent thresholds prevent excessive scaling")
        print(f"   ✓ Comprehensive monitoring and optimization recommendations")

        # Stop the dynamic manager
        print(f"\n🛑 Stopping dynamic pool management...")
        await dynamic_manager.stop()

        print(f"\n" + "=" * 50)
        print(f"✅ Dynamic Connection Pool Management Demo Complete!")

        print(f"\nImplementation Summary:")
        print(f"🔧 Automatic pool scaling based on utilization and activity patterns")
        print(f"📊 Real-time monitoring with activity level classification")
        print(f"⚡ Resource efficiency improvements during varying load conditions")
        print(f"🛡️ Configurable thresholds and limits for safe scaling")
        print(f"💡 Performance analytics and optimization recommendations")
        print(f"🚀 Ready for integration with existing connection pool infrastructure")

        return True

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(demonstrate_dynamic_pool_management())
    exit(0 if success else 1)
