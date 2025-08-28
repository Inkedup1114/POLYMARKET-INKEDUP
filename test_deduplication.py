#!/usr/bin/env python3
"""
Simple test script to validate message deduplication logic.
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock websockets to avoid import error
sys.modules["websockets"] = AsyncMock()
sys.modules["websockets.exceptions"] = AsyncMock()

from inkedup_bot.ws_manager import DeduplicationConfig, MessageDeduplicationTracker


async def test_deduplication_basic():
    """Test basic deduplication functionality."""
    print("Testing basic deduplication functionality...")

    config = DeduplicationConfig(
        enabled=True, max_tracked_messages=100, message_ttl_seconds=60.0
    )
    tracker = MessageDeduplicationTracker(config)

    # Test message 1
    message1 = {"type": "trade", "market": "0x123", "price": "1.50", "size": "100"}
    is_duplicate1 = await tracker.is_duplicate(message1)
    print(f"Message 1 duplicate check: {is_duplicate1} (should be False)")

    # Test same message again (should be duplicate)
    is_duplicate2 = await tracker.is_duplicate(message1)
    print(f"Message 1 again duplicate check: {is_duplicate2} (should be True)")

    # Test different message
    message2 = {"type": "trade", "market": "0x456", "price": "2.00", "size": "200"}
    is_duplicate3 = await tracker.is_duplicate(message2)
    print(f"Message 2 duplicate check: {is_duplicate3} (should be False)")

    # Get statistics
    stats = tracker.get_statistics()
    print(f"Statistics: {stats}")

    return is_duplicate1 == False and is_duplicate2 == True and is_duplicate3 == False


async def test_deduplication_with_timestamps():
    """Test deduplication with timestamp handling."""
    print("\nTesting deduplication with timestamp handling...")

    # Test with timestamps included
    config1 = DeduplicationConfig(enabled=True, include_timestamp_in_hash=True)
    tracker1 = MessageDeduplicationTracker(config1)

    message_base = {"type": "trade", "market": "0x123", "price": "1.50"}
    message_ts1 = {**message_base, "timestamp": "2023-01-01T10:00:00Z"}
    message_ts2 = {**message_base, "timestamp": "2023-01-01T10:00:01Z"}

    dup1 = await tracker1.is_duplicate(message_ts1)
    dup2 = await tracker1.is_duplicate(message_ts2)
    print(
        f"With timestamps - Message 1: {dup1}, Message 2: {dup2} (should be False, False)"
    )

    # Test without timestamps in hash
    config2 = DeduplicationConfig(enabled=True, include_timestamp_in_hash=False)
    tracker2 = MessageDeduplicationTracker(config2)

    dup3 = await tracker2.is_duplicate(message_ts1)
    dup4 = await tracker2.is_duplicate(message_ts2)
    print(
        f"Without timestamps - Message 1: {dup3}, Message 2: {dup4} (should be False, True)"
    )

    return dup1 == False and dup2 == False and dup3 == False and dup4 == True


async def test_deduplication_disabled():
    """Test behavior when deduplication is disabled."""
    print("\nTesting deduplication disabled...")

    config = DeduplicationConfig(enabled=False)
    tracker = MessageDeduplicationTracker(config)

    message = {"type": "trade", "market": "0x123", "price": "1.50"}

    dup1 = await tracker.is_duplicate(message)
    dup2 = await tracker.is_duplicate(message)
    print(f"Disabled - Message 1: {dup1}, Message 2: {dup2} (should be False, False)")

    return dup1 == False and dup2 == False


async def test_high_frequency_simulation():
    """Test high frequency message processing simulation."""
    print("\nTesting high-frequency message processing simulation...")

    config = DeduplicationConfig(
        enabled=True,
        max_tracked_messages=50,  # Small limit for testing
        cleanup_interval_seconds=1.0,
    )
    tracker = MessageDeduplicationTracker(config)

    # Simulate high frequency messages
    duplicates_found = 0
    total_messages = 100

    for i in range(total_messages):
        # Create some duplicate messages
        if i % 10 == 0 and i > 0:
            # Repeat a previous message
            message = {
                "type": "trade",
                "market": "0x123",
                "price": f"1.{i-10}",
                "id": i - 10,
            }
        else:
            # New message
            message = {"type": "trade", "market": "0x123", "price": f"1.{i}", "id": i}

        is_dup = await tracker.is_duplicate(message)
        if is_dup:
            duplicates_found += 1

    stats = tracker.get_statistics()
    print(f"Processed {total_messages} messages, found {duplicates_found} duplicates")
    print(f"Tracker stats: {stats}")

    # Should have found some duplicates
    return duplicates_found > 0 and stats["total_messages_processed"] == total_messages


async def main():
    """Run all tests."""
    print("=" * 50)
    print("MESSAGE DEDUPLICATION TESTS")
    print("=" * 50)

    tests = [
        test_deduplication_basic(),
        test_deduplication_with_timestamps(),
        test_deduplication_disabled(),
        test_high_frequency_simulation(),
    ]

    results = await asyncio.gather(*tests)

    print("\n" + "=" * 50)
    print("TEST RESULTS")
    print("=" * 50)

    all_passed = True
    for i, result in enumerate(results, 1):
        status = "PASS" if result else "FAIL"
        print(f"Test {i}: {status}")
        if not result:
            all_passed = False

    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
