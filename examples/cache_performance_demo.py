#!/usr/bin/env python3
"""
Cache Performance Monitoring Demo

This demo shows how to use the intelligent caching system with performance monitoring,
analytics, and the dashboard to track cache effectiveness and optimize performance.
"""

import asyncio
import os
import random
import sys
import time
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from inkedup_bot.cache import CacheConfig, IntelligentCache
from inkedup_bot.cache_analytics import get_cache_analytics, initialize_cache_analytics
from inkedup_bot.cache_dashboard import get_cache_dashboard, print_cache_status


async def generate_cache_workload(
    cache: IntelligentCache, workload_name: str, duration_seconds: int = 60
):
    """Generate realistic cache workload for testing performance monitoring."""
    print(f"\nStarting {workload_name} workload for {duration_seconds} seconds...")

    start_time = time.time()
    request_count = 0

    # Define different access patterns
    if "hot_keys" in workload_name.lower():
        # 80/20 pattern - 80% requests to 20% of keys
        hot_keys = [f"hot_key_{i}" for i in range(20)]
        cold_keys = [f"cold_key_{i}" for i in range(200)]
        all_keys = hot_keys + cold_keys

        # Pre-populate some keys
        for key in hot_keys:
            await cache.set(key, f"Hot data for {key}", ttl=300)

    elif "random" in workload_name.lower():
        # Random access pattern
        all_keys = [f"random_key_{i}" for i in range(1000)]

        # Pre-populate 30% of keys
        for i in range(0, 300):
            key = all_keys[i]
            await cache.set(key, f"Random data for {key}", ttl=60)

    elif "sequential" in workload_name.lower():
        # Sequential access pattern
        all_keys = [f"seq_key_{i}" for i in range(500)]

        # Pre-populate first 100 keys
        for i in range(100):
            await cache.set(all_keys[i], f"Sequential data for {all_keys[i]}", ttl=120)

    else:
        # Default mixed pattern
        all_keys = [f"mixed_key_{i}" for i in range(100)]
        for i in range(50):
            await cache.set(all_keys[i], f"Mixed data for {all_keys[i]}", ttl=180)

    # Generate workload
    while time.time() - start_time < duration_seconds:
        try:
            if "hot_keys" in workload_name.lower():
                # 80% chance of accessing hot keys
                if random.random() < 0.8:
                    key = random.choice(hot_keys)
                else:
                    key = random.choice(cold_keys)
            else:
                key = random.choice(all_keys)

            # 70% reads, 30% writes
            if random.random() < 0.7:
                # Read operation
                value = await cache.get(key)
                if value is None and random.random() < 0.5:
                    # Cache miss - populate with new data
                    await cache.set(
                        key,
                        f"New data for {key} at {datetime.now()}",
                        ttl=random.randint(30, 300),
                    )
            else:
                # Write operation
                ttl = random.randint(30, 600)  # TTL between 30 seconds and 10 minutes
                await cache.set(
                    key, f"Updated data for {key} at {datetime.now()}", ttl=ttl
                )

            request_count += 1

            # Small delay to simulate realistic usage
            await asyncio.sleep(random.uniform(0.001, 0.01))

        except Exception as e:
            print(f"Error in workload {workload_name}: {e}")
            # Record error in analytics
            analytics = get_cache_analytics()
            analytics.record_cache_error(
                cache.name, key if "key" in locals() else "unknown", {"error": str(e)}
            )

    elapsed = time.time() - start_time
    rps = request_count / elapsed
    print(
        f"Completed {workload_name}: {request_count} requests in {elapsed:.1f}s ({rps:.1f} RPS)"
    )


async def simulate_cache_errors(cache: IntelligentCache, error_rate: float = 0.05):
    """Simulate cache errors for testing alert system."""
    print(f"\nSimulating cache errors (rate: {error_rate:.1%})...")

    analytics = get_cache_analytics()

    for i in range(20):  # Generate 20 operations with potential errors
        key = f"error_test_key_{i}"

        if random.random() < error_rate:
            # Simulate an error
            error_details = {
                "error_type": "simulated_error",
                "operation": "get" if random.random() < 0.5 else "set",
                "error_code": random.choice(
                    ["TIMEOUT", "CONNECTION_LOST", "INVALID_DATA"]
                ),
            }
            analytics.record_cache_error(cache.name, key, error_details)
        else:
            # Normal operation
            if random.random() < 0.5:
                await cache.set(key, f"Test data {i}", ttl=60)
            else:
                await cache.get(key)

        await asyncio.sleep(0.1)


async def demonstrate_cache_monitoring():
    """Main demo function showing cache monitoring capabilities."""
    print("🚀 Cache Performance Monitoring Demo")
    print("=" * 80)

    # Initialize analytics system
    print("Initializing cache analytics system...")
    await initialize_cache_analytics(
        retention_hours=2,  # Keep data for 2 hours
        alert_thresholds={
            "hit_rate_low": 0.6,  # Alert if hit rate drops below 60%
            "response_time_high_ms": 25.0,  # Alert if avg response time > 25ms
            "error_rate_high": 0.03,  # Alert if error rate > 3%
            "memory_usage_high_mb": 100.0,  # Alert if memory usage > 100MB
            "eviction_rate_high": 0.08,  # Alert if eviction rate > 8%
        },
    )

    # Create different types of caches for testing
    print("\nCreating test caches...")

    # High-performance cache
    high_perf_config = CacheConfig(
        max_size=1000,
        default_ttl=300,
        enable_background_refresh=True,
        enable_analytics=True,
    )
    high_perf_cache = IntelligentCache("high_performance", high_perf_config)

    # Memory-constrained cache
    memory_config = CacheConfig(
        max_size=100,  # Small size to trigger evictions
        default_ttl=60,
        enable_background_refresh=False,
        enable_analytics=True,
    )
    memory_cache = IntelligentCache("memory_constrained", memory_config)

    # Fast-changing data cache
    volatile_config = CacheConfig(
        max_size=500,
        default_ttl=30,  # Short TTL
        enable_background_refresh=True,
        enable_analytics=True,
    )
    volatile_cache = IntelligentCache("volatile_data", volatile_config)

    # Add alert callback to demonstrate alert system
    def alert_callback(alert):
        severity_emoji = {"critical": "🚨", "high": "⚠️", "medium": "💛", "low": "ℹ️"}
        emoji = severity_emoji.get(alert.severity.value, "📢")
        print(
            f"{emoji} ALERT [{alert.severity.value.upper()}] {alert.cache_name}: {alert.message}"
        )

    analytics = get_cache_analytics()
    analytics.add_alert_callback(alert_callback)

    print("✅ Analytics system initialized with alert monitoring")

    # Run concurrent workloads
    print("\n📊 Running concurrent cache workloads...")

    workload_tasks = [
        generate_cache_workload(high_perf_cache, "Hot Keys Pattern", 30),
        generate_cache_workload(memory_cache, "Random Access", 30),
        generate_cache_workload(volatile_cache, "Sequential Access", 30),
    ]

    # Add error simulation
    workload_tasks.append(simulate_cache_errors(high_perf_cache, error_rate=0.02))

    # Run workloads concurrently
    await asyncio.gather(*workload_tasks)

    print("\n⏱️  Allowing time for metrics collection...")
    await asyncio.sleep(5)  # Allow time for metrics to be collected

    # Display performance dashboard
    print("\n📈 Cache Performance Dashboard")
    print("-" * 80)
    await print_cache_status()

    # Get detailed performance analysis
    dashboard = get_cache_dashboard()

    print("\n🔍 Detailed Cache Analysis")
    print("-" * 80)

    for cache_name in ["high_performance", "memory_constrained", "volatile_data"]:
        details = await dashboard.get_cache_details(cache_name, time_window_minutes=30)

        if not details.get("no_data", False):
            print(f"\n📋 {cache_name.upper()} CACHE DETAILS:")
            print(f"├── Hit Rate: {details['rates']['hit_rate']:.2%}")
            print(
                f"├── Average Response: {details['response_times_ms']['average']:.2f}ms"
            )
            print(f"├── P95 Response: {details['response_times_ms']['p95']:.2f}ms")
            print(f"├── Total Requests: {details['requests']['total']:,}")
            print(f"├── Error Rate: {details['rates']['error_rate']:.2%}")
            print(f"└── Health Score: {details.get('health_score', 0):.1f}/100")

            # Show top accessed keys
            top_keys = details.get("top_keys", [])
            if top_keys:
                print("  Top Keys:")
                for i, key_info in enumerate(top_keys[:3], 1):
                    print(
                        f"  {i}. {key_info['key']} ({key_info['access_count']} accesses, {key_info['hit_rate']:.1%} hit rate)"
                    )

    # Show active alerts
    active_alerts = analytics.get_active_alerts()
    if active_alerts:
        print(f"\n🚨 Active Alerts ({len(active_alerts)}):")
        for alert in active_alerts[:5]:  # Show first 5 alerts
            print(
                f"├── [{alert.severity.value.upper()}] {alert.cache_name}: {alert.message}"
            )
    else:
        print("\n✅ No active alerts - all caches performing well!")

    # Generate comprehensive performance report
    print("\n📋 Generating Performance Report...")
    report_file = (
        f"cache_performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    report = analytics.export_performance_report(report_file, time_window_hours=1)

    print(f"📄 Performance report saved to: {report_file}")
    print(f"├── Report contains {report['report_metadata']['total_events']} events")
    print(f"├── Active caches: {len(report['performance_summary']['cache_details'])}")
    print(f"└── Active alerts: {report['alerts_summary']['active_alerts']}")

    # Show optimization recommendations
    recommendations = report["performance_summary"]["recommendations"]
    if recommendations:
        print("\n💡 Optimization Recommendations:")
        for i, rec in enumerate(recommendations[:3], 1):
            print(f"{i}. {rec}")

    # Export dashboard data
    dashboard_file = f"cache_dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    export_result = await dashboard.export_dashboard_data(dashboard_file)

    if export_result["success"]:
        print(f"\n📊 Dashboard data exported to: {dashboard_file}")
        print(f"└── File size: {export_result['file_size_bytes']:,} bytes")

    print("\n🏁 Cache monitoring demo completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(demonstrate_cache_monitoring())
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback

        traceback.print_exc()
