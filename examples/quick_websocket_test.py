#!/usr/bin/env python3
"""
Quick WebSocket optimization test to verify functionality.
"""

import asyncio
import json
import sys
import time

sys.path.append("/home/ink/polymarket-inkedup")

from inkedup_bot.optimized_ws_deduplication import (
    create_optimized_deduplication_tracker,
)


async def quick_test():
    print("🧪 Quick WebSocket Optimization Test")
    print("=" * 40)

    # Create tracker
    tracker = create_optimized_deduplication_tracker(
        expected_messages_per_hour=1000,
        false_positive_rate=0.01,
        message_ttl_minutes=1,
        cache_size=100,
    )

    await tracker.start()

    # Test messages
    messages = [
        {"type": "test", "id": 1, "data": "first"},
        {"type": "test", "id": 2, "data": "second"},
        {"type": "test", "id": 1, "data": "first"},  # Duplicate
        {"type": "test", "id": 3, "data": "third"},
        {"type": "test", "id": 2, "data": "second"},  # Duplicate
    ]

    results = []
    for i, msg in enumerate(messages):
        start = time.perf_counter()
        is_dup = await tracker.is_duplicate(msg)
        duration = (time.perf_counter() - start) * 1000

        results.append((i + 1, is_dup, duration))
        print(f"Message {i+1}: duplicate={is_dup}, time={duration:.2f}ms")

    # Get stats
    stats = tracker.get_performance_stats()
    await tracker.stop()

    print(f"\n📊 Results:")
    print(f"Total messages: {stats['message_processing']['total_messages']}")
    print(f"Duplicates detected: {stats['message_processing']['duplicates_detected']}")
    print(f"Average time: {stats['performance']['avg_processing_time_ms']:.2f}ms")
    print(f"Bloom efficiency: {stats['performance']['bloom_efficiency']:.1%}")

    # Verify correctness
    expected_duplicates = [False, False, True, False, True]
    actual_duplicates = [result[1] for result in results]

    if actual_duplicates == expected_duplicates:
        print("✅ Duplicate detection working correctly!")
    else:
        print(f"❌ Expected: {expected_duplicates}")
        print(f"❌ Actual: {actual_duplicates}")

    return True


if __name__ == "__main__":
    asyncio.run(quick_test())
