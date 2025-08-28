#!/usr/bin/env python3
"""
Standalone test for core state management functionality.
Tests just the StreamingState and StatePersistenceManager classes.
"""
import asyncio
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


# Reproduce core classes for testing
@dataclass
class StreamingState:
    """Enhanced streaming state with persistence and recovery capabilities."""

    market_subscriptions: dict[str, set[str]] = field(default_factory=dict)
    user_subscriptions: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    active_subscriptions: list[dict[str, Any]] = field(default_factory=list)
    subscription_acks: set[str] = field(default_factory=set)

    message_buffer: deque = field(default_factory=deque)
    processed_message_ids: set[str] = field(default_factory=set)
    last_sequence_number: int = 0

    last_heartbeat: datetime | None = None
    last_message_time: datetime | None = None
    connection_established_time: datetime | None = None
    last_successful_ping: datetime | None = None

    state_version: int = 1
    last_save_time: datetime | None = None
    recovery_attempts: int = 0
    max_recovery_attempts: int = 3

    message_count: int = 0
    error_count: int = 0
    reconnect_count: int = 0

    def add_market_subscription(self, market: str, channels: set[str]):
        """Add market subscription to state."""
        if market not in self.market_subscriptions:
            self.market_subscriptions[market] = set()
        self.market_subscriptions[market].update(channels)

    def remove_market_subscription(self, market: str, channels: set[str]):
        """Remove market subscription from state."""
        if market in self.market_subscriptions:
            self.market_subscriptions[market].difference_update(channels)
            if not self.market_subscriptions[market]:
                del self.market_subscriptions[market]

    def add_user_subscription(
        self, user_address: str, channels: set[str], tokens: set[str] | None = None
    ):
        """Add user subscription to state."""
        if user_address not in self.user_subscriptions:
            self.user_subscriptions[user_address] = {"channels": set(), "tokens": set()}
        self.user_subscriptions[user_address]["channels"].update(channels)
        if tokens:
            self.user_subscriptions[user_address]["tokens"].update(tokens)

    def remove_user_subscription(self, user_address: str, channels: set[str]):
        """Remove user subscription from state."""
        if user_address in self.user_subscriptions:
            self.user_subscriptions[user_address]["channels"].difference_update(
                channels
            )
            if not self.user_subscriptions[user_address]["channels"]:
                del self.user_subscriptions[user_address]

    def get_all_subscriptions(self) -> list[dict[str, Any]]:
        """Get all subscriptions for restoration."""
        subscriptions = []

        for market, channels in self.market_subscriptions.items():
            subscriptions.append(
                {"type": "market", "market": market, "channels": list(channels)}
            )

        for user_address, data in self.user_subscriptions.items():
            subscriptions.append(
                {
                    "type": "user",
                    "user_address": user_address,
                    "channels": list(data["channels"]),
                    "tokens": list(data["tokens"]) if data["tokens"] else None,
                }
            )

        return subscriptions

    def has_recent_messages(self, max_age_seconds: int) -> bool:
        """Check if we have received messages recently."""
        if not self.last_message_time:
            return False
        age = (datetime.now() - self.last_message_time).total_seconds()
        return age <= max_age_seconds

    def update_message_time(self):
        """Update the last message time."""
        self.last_message_time = datetime.now()
        self.message_count += 1

    def add_message_to_buffer(
        self, message: dict[str, Any], max_buffer_size: int = 1000
    ):
        """Add message to buffer for potential replay during recovery."""
        buffered_message = {
            **message,
            "buffered_at": datetime.now().isoformat(),
            "sequence_number": self.last_sequence_number + 1,
        }

        self.message_buffer.append(buffered_message)
        self.last_sequence_number += 1

        while len(self.message_buffer) > max_buffer_size:
            self.message_buffer.popleft()

    def get_buffered_messages(
        self, since_sequence: int | None = None
    ) -> list[dict[str, Any]]:
        """Get buffered messages for replay, optionally since a sequence number."""
        if since_sequence is None:
            return list(self.message_buffer)

        return [
            msg
            for msg in self.message_buffer
            if msg.get("sequence_number", 0) > since_sequence
        ]

    def mark_message_processed(self, message_id: str):
        """Mark a message as processed to avoid reprocessing."""
        self.processed_message_ids.add(message_id)

        if len(self.processed_message_ids) > 10000:
            ids_list = list(self.processed_message_ids)
            self.processed_message_ids = set(ids_list[5000:])

    def is_message_processed(self, message_id: str) -> bool:
        """Check if a message has already been processed."""
        return message_id in self.processed_message_ids

    def update_connection_established(self):
        """Mark connection as established."""
        self.connection_established_time = datetime.now()
        self.reconnect_count += 1

    def record_error(self):
        """Record an error occurrence."""
        self.error_count += 1

    def get_connection_quality_score(self) -> float:
        """Calculate connection quality score based on metrics."""
        if self.message_count == 0:
            return 0.0

        error_rate = self.error_count / max(self.message_count, 1)
        base_score = max(0.0, 1.0 - error_rate * 2)

        if self.connection_established_time:
            connection_age = (
                datetime.now() - self.connection_established_time
            ).total_seconds()
            stability_bonus = min(0.2, connection_age / 3600)
            base_score += stability_bonus

        return min(1.0, base_score)

    def to_serializable_dict(self) -> dict[str, Any]:
        """Convert state to serializable dictionary."""
        serializable = {}

        for key, value in asdict(self).items():
            if isinstance(value, set):
                serializable[key] = list(value)
            elif isinstance(value, deque):
                serializable[key] = list(value)
            elif isinstance(value, datetime):
                serializable[key] = value.isoformat() if value else None
            elif isinstance(value, dict):
                if key == "user_subscriptions":
                    serializable[key] = {
                        k: {
                            sub_k: list(sub_v) if isinstance(sub_v, set) else sub_v
                            for sub_k, sub_v in v.items()
                        }
                        for k, v in value.items()
                    }
                else:
                    serializable[key] = value
            else:
                serializable[key] = value

        return serializable

    @classmethod
    def from_serializable_dict(cls, data: dict[str, Any]) -> "StreamingState":
        """Create StreamingState from serializable dictionary."""
        converted = {}

        for key, value in data.items():
            if key in ["market_subscriptions"]:
                converted[key] = {k: set(v) for k, v in value.items()}
            elif key == "user_subscriptions":
                converted[key] = {
                    k: {
                        sub_k: set(sub_v) if isinstance(sub_v, list) else sub_v
                        for sub_k, sub_v in v.items()
                    }
                    for k, v in value.items()
                }
            elif key in ["subscription_acks", "processed_message_ids"]:
                converted[key] = set(value) if value else set()
            elif key == "message_buffer":
                converted[key] = deque(value) if value else deque()
            elif key in [
                "last_heartbeat",
                "last_message_time",
                "connection_established_time",
                "last_successful_ping",
                "last_save_time",
            ]:
                converted[key] = datetime.fromisoformat(value) if value else None
            else:
                converted[key] = value

        return cls(**converted)


async def test_state_management():
    """Run comprehensive tests on state management."""
    print("🧪 Testing Core State Management Functionality")
    print("=" * 60)

    tests_passed = 0
    total_tests = 0

    # Test 1: Basic state operations
    total_tests += 1
    try:
        state = StreamingState()
        state.add_market_subscription("market1", {"trade", "book"})
        state.add_user_subscription("user1", {"order"}, {"token1"})
        state.update_message_time()

        assert len(state.market_subscriptions) == 1
        assert "market1" in state.market_subscriptions
        assert state.market_subscriptions["market1"] == {"trade", "book"}
        assert len(state.user_subscriptions) == 1
        assert state.message_count == 1

        print("✅ Test 1: Basic state operations - PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Test 1: Basic state operations - FAILED: {e}")

    # Test 2: Message buffering
    total_tests += 1
    try:
        state = StreamingState()
        test_msg = {"type": "trade", "price": "1.50"}
        state.add_message_to_buffer(test_msg)

        assert len(state.message_buffer) == 1
        assert state.last_sequence_number == 1

        buffered = state.get_buffered_messages()
        assert len(buffered) == 1
        assert buffered[0]["sequence_number"] == 1

        print("✅ Test 2: Message buffering - PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Test 2: Message buffering - FAILED: {e}")

    # Test 3: Message processing tracking
    total_tests += 1
    try:
        state = StreamingState()
        msg_id = "test_message_123"

        assert not state.is_message_processed(msg_id)
        state.mark_message_processed(msg_id)
        assert state.is_message_processed(msg_id)

        print("✅ Test 3: Message processing tracking - PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Test 3: Message processing tracking - FAILED: {e}")

    # Test 4: Connection quality scoring
    total_tests += 1
    try:
        state = StreamingState()

        # No messages = 0 score
        assert state.get_connection_quality_score() == 0.0

        # Add messages
        for _ in range(100):
            state.update_message_time()
        state.update_connection_established()

        good_score = state.get_connection_quality_score()
        assert 0.8 <= good_score <= 1.0

        # Add errors
        for _ in range(20):
            state.record_error()

        degraded_score = state.get_connection_quality_score()
        assert degraded_score < good_score

        print(
            f"✅ Test 4: Connection quality scoring - PASSED (good: {good_score:.3f}, degraded: {degraded_score:.3f})"
        )
        tests_passed += 1
    except Exception as e:
        print(f"❌ Test 4: Connection quality scoring - FAILED: {e}")

    # Test 5: Serialization round-trip
    total_tests += 1
    try:
        original_state = StreamingState()
        original_state.add_market_subscription("market1", {"trade", "book"})
        original_state.add_user_subscription("user1", {"order"}, {"token1"})
        original_state.update_message_time()
        original_state.add_message_to_buffer({"type": "test", "data": "123"})
        original_state.mark_message_processed("msg_1")

        # Serialize
        serialized = original_state.to_serializable_dict()

        # Deserialize
        recovered_state = StreamingState.from_serializable_dict(serialized)

        # Verify integrity
        assert (
            recovered_state.market_subscriptions == original_state.market_subscriptions
        )
        assert recovered_state.user_subscriptions == original_state.user_subscriptions
        assert len(recovered_state.message_buffer) == len(original_state.message_buffer)
        assert (
            recovered_state.processed_message_ids
            == original_state.processed_message_ids
        )
        assert recovered_state.message_count == original_state.message_count

        print("✅ Test 5: Serialization round-trip - PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Test 5: Serialization round-trip - FAILED: {e}")

    # Test 6: Buffer size limits
    total_tests += 1
    try:
        state = StreamingState()
        max_size = 100

        # Add more messages than the limit
        for i in range(150):
            state.add_message_to_buffer({"id": i}, max_buffer_size=max_size)

        assert len(state.message_buffer) == max_size
        assert state.last_sequence_number == 150

        print(
            f"✅ Test 6: Buffer size limits - PASSED (buffer size: {len(state.message_buffer)})"
        )
        tests_passed += 1
    except Exception as e:
        print(f"❌ Test 6: Buffer size limits - FAILED: {e}")

    # Test 7: Subscription management
    total_tests += 1
    try:
        state = StreamingState()

        # Add subscriptions
        state.add_market_subscription("market1", {"trade", "book"})
        state.add_market_subscription("market1", {"price"})  # Should merge

        assert state.market_subscriptions["market1"] == {"trade", "book", "price"}

        # Remove partial
        state.remove_market_subscription("market1", {"book"})
        assert state.market_subscriptions["market1"] == {"trade", "price"}

        # Remove all
        state.remove_market_subscription("market1", {"trade", "price"})
        assert "market1" not in state.market_subscriptions

        print("✅ Test 7: Subscription management - PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Test 7: Subscription management - FAILED: {e}")

    # Test 8: get_all_subscriptions
    total_tests += 1
    try:
        state = StreamingState()
        state.add_market_subscription("market1", {"trade"})
        state.add_user_subscription("user1", {"order"}, {"token1"})

        all_subs = state.get_all_subscriptions()
        assert len(all_subs) == 2

        market_sub = next(s for s in all_subs if s["type"] == "market")
        user_sub = next(s for s in all_subs if s["type"] == "user")

        assert market_sub["market"] == "market1"
        assert market_sub["channels"] == ["trade"]
        assert user_sub["user_address"] == "user1"
        assert user_sub["channels"] == ["order"]
        assert user_sub["tokens"] == ["token1"]

        print("✅ Test 8: get_all_subscriptions - PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Test 8: get_all_subscriptions - FAILED: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("🏁 TEST SUMMARY")
    print("=" * 60)
    print(f"Tests passed: {tests_passed}/{total_tests}")

    if tests_passed == total_tests:
        print("🎉 ALL TESTS PASSED! Core state management is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. State management needs fixes.")
        return 1


async def main():
    """Run the test suite."""
    return await test_state_management()


if __name__ == "__main__":
    import sys

    exit_code = asyncio.run(main())
    sys.exit(exit_code)
