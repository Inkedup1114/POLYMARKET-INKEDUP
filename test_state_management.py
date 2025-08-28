#!/usr/bin/env python3
"""
Comprehensive test script for WebSocket state management improvements.
Tests state persistence, recovery, message buffering, and data integrity.
"""
import asyncio
import os
import sys
import tempfile
from unittest.mock import AsyncMock

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock external dependencies
sys.modules["websockets"] = AsyncMock()
sys.modules["websockets.exceptions"] = AsyncMock()
sys.modules["py_clob_client"] = AsyncMock()
sys.modules["py_clob_client.client"] = AsyncMock()

from inkedup_bot.ws_manager import (
    StatePersistenceConfig,
    StatePersistenceManager,
    StreamingState,
)


class TestStateManagement:
    """Test suite for WebSocket state management."""

    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_results = []

    def log_test(self, test_name: str, passed: bool, details: str = ""):
        """Log test result."""
        status = "PASS" if passed else "FAIL"
        self.test_results.append((test_name, passed, details))
        print(f"[{status}] {test_name}: {details}")

    async def test_streaming_state_serialization(self):
        """Test StreamingState serialization and deserialization."""
        print("\n=== Testing StreamingState Serialization ===")

        # Create a streaming state with various data
        state = StreamingState()
        state.add_market_subscription("0x123", {"trade", "book"})
        state.add_user_subscription("0xuser1", {"order"}, {"token1", "token2"})
        state.update_message_time()
        state.update_connection_established()
        state.add_message_to_buffer({"type": "trade", "price": "1.50"})
        state.mark_message_processed("test_msg_1")

        try:
            # Test serialization
            serialized = state.to_serializable_dict()
            self.log_test(
                "State serialization",
                isinstance(serialized, dict) and "market_subscriptions" in serialized,
                f"Serialized keys: {list(serialized.keys())}",
            )

            # Test deserialization
            recovered_state = StreamingState.from_serializable_dict(serialized)

            # Verify data integrity
            market_subs_match = (
                recovered_state.market_subscriptions == state.market_subscriptions
            )
            user_subs_match = (
                recovered_state.user_subscriptions == state.user_subscriptions
            )
            buffer_match = len(recovered_state.message_buffer) == len(
                state.message_buffer
            )

            self.log_test(
                "State deserialization integrity",
                market_subs_match and user_subs_match and buffer_match,
                f"Markets: {market_subs_match}, Users: {user_subs_match}, Buffer: {buffer_match}",
            )

            return True

        except Exception as e:
            self.log_test("State serialization", False, f"Error: {e}")
            return False

    async def test_message_buffering(self):
        """Test message buffering and replay functionality."""
        print("\n=== Testing Message Buffering ===")

        state = StreamingState()

        try:
            # Add multiple messages to buffer
            messages = [
                {"type": "trade", "market": "0x123", "price": "1.00"},
                {"type": "trade", "market": "0x456", "price": "2.00"},
                {"type": "book", "market": "0x123", "bids": []},
            ]

            for msg in messages:
                state.add_message_to_buffer(msg, max_buffer_size=100)

            # Test buffer size
            buffer_size_correct = len(state.message_buffer) == 3
            self.log_test(
                "Message buffer size",
                buffer_size_correct,
                f"Expected: 3, Got: {len(state.message_buffer)}",
            )

            # Test sequence numbering
            last_seq = state.last_sequence_number
            sequence_correct = last_seq == 3
            self.log_test(
                "Sequence numbering", sequence_correct, f"Last sequence: {last_seq}"
            )

            # Test buffered message retrieval
            buffered = state.get_buffered_messages()
            retrieval_correct = len(buffered) == 3
            self.log_test(
                "Buffer retrieval",
                retrieval_correct,
                f"Retrieved {len(buffered)} messages",
            )

            # Test filtered retrieval
            filtered = state.get_buffered_messages(since_sequence=1)
            filtered_correct = len(filtered) == 2
            self.log_test(
                "Filtered buffer retrieval",
                filtered_correct,
                f"Retrieved {len(filtered)} messages since seq 1",
            )

            # Test buffer limit enforcement
            for i in range(150):  # Add more than max_buffer_size
                state.add_message_to_buffer(
                    {"type": "test", "id": i}, max_buffer_size=100
                )

            limit_enforced = len(state.message_buffer) <= 100
            self.log_test(
                "Buffer size limit",
                limit_enforced,
                f"Buffer size after overflow: {len(state.message_buffer)}",
            )

            return True

        except Exception as e:
            self.log_test("Message buffering", False, f"Error: {e}")
            return False

    async def test_state_persistence_manager(self):
        """Test StatePersistenceManager functionality."""
        print("\n=== Testing State Persistence Manager ===")

        state_file = os.path.join(self.temp_dir, "test_state.pkl")
        backup_file = os.path.join(self.temp_dir, "test_state_backup.pkl")

        config = StatePersistenceConfig(
            state_file_path=state_file,
            backup_state_file_path=backup_file,
            save_interval_seconds=1.0,
            compress_state=False,  # Disable for simpler testing
        )

        try:
            manager = StatePersistenceManager(config)

            # Create test state
            test_state = StreamingState()
            test_state.add_market_subscription("0x123", {"trade"})
            test_state.update_message_time()
            test_state.message_count = 42

            # Test saving
            save_success = await manager.save_state(test_state, force=True)
            self.log_test(
                "State save", save_success, f"File exists: {os.path.exists(state_file)}"
            )

            # Test loading
            loaded_state = await manager.load_state()
            load_success = loaded_state is not None
            self.log_test(
                "State load", load_success, f"Loaded state type: {type(loaded_state)}"
            )

            if loaded_state:
                # Test data integrity after round-trip
                market_subs_match = (
                    loaded_state.market_subscriptions == test_state.market_subscriptions
                )
                message_count_match = (
                    loaded_state.message_count == test_state.message_count
                )

                self.log_test(
                    "Round-trip data integrity",
                    market_subs_match and message_count_match,
                    f"Markets: {market_subs_match}, Count: {message_count_match}",
                )

            # Test statistics
            stats = manager.get_persistence_statistics()
            stats_valid = isinstance(stats, dict) and "enabled" in stats
            self.log_test(
                "Persistence statistics",
                stats_valid,
                f"Stats keys: {list(stats.keys())}",
            )

            return True

        except Exception as e:
            self.log_test("State persistence manager", False, f"Error: {e}")
            return False

    async def test_connection_quality_scoring(self):
        """Test connection quality scoring system."""
        print("\n=== Testing Connection Quality Scoring ===")

        try:
            state = StreamingState()

            # Test initial score (should be 0 with no messages)
            initial_score = state.get_connection_quality_score()
            initial_correct = initial_score == 0.0
            self.log_test(
                "Initial quality score", initial_correct, f"Score: {initial_score}"
            )

            # Add some successful messages
            for i in range(100):
                state.update_message_time()

            # Set connection time for stability bonus
            state.update_connection_established()

            good_score = state.get_connection_quality_score()
            good_score_valid = 0.8 <= good_score <= 1.0
            self.log_test(
                "Good connection score", good_score_valid, f"Score: {good_score:.3f}"
            )

            # Add errors to degrade score
            for i in range(20):
                state.record_error()

            degraded_score = state.get_connection_quality_score()
            score_degraded = degraded_score < good_score
            self.log_test(
                "Error-degraded score",
                score_degraded,
                f"Good: {good_score:.3f}, Degraded: {degraded_score:.3f}",
            )

            return True

        except Exception as e:
            self.log_test("Connection quality scoring", False, f"Error: {e}")
            return False

    async def test_message_processing_tracking(self):
        """Test message processing tracking to prevent duplicates."""
        print("\n=== Testing Message Processing Tracking ===")

        try:
            state = StreamingState()

            # Test marking messages as processed
            test_msgs = ["msg_1", "msg_2", "msg_3"]

            for msg_id in test_msgs:
                state.mark_message_processed(msg_id)

            # Test detection of processed messages
            all_detected = all(
                state.is_message_processed(msg_id) for msg_id in test_msgs
            )
            self.log_test(
                "Processed message detection",
                all_detected,
                f"Detected all {len(test_msgs)} messages",
            )

            # Test non-processed message
            unprocessed_detected = not state.is_message_processed("msg_new")
            self.log_test(
                "Unprocessed message detection",
                unprocessed_detected,
                "Correctly identified unprocessed message",
            )

            # Test memory management (add many messages)
            for i in range(15000):  # More than the 10000 limit
                state.mark_message_processed(f"msg_{i}")

            size_managed = len(state.processed_message_ids) <= 10000
            self.log_test(
                "Processed messages memory management",
                size_managed,
                f"Final size: {len(state.processed_message_ids)}",
            )

            return True

        except Exception as e:
            self.log_test("Message processing tracking", False, f"Error: {e}")
            return False

    async def test_subscription_state_management(self):
        """Test subscription state management."""
        print("\n=== Testing Subscription State Management ===")

        try:
            state = StreamingState()

            # Test market subscriptions
            state.add_market_subscription("market1", {"trade", "book"})
            state.add_market_subscription("market2", {"trade"})

            market_count = len(state.market_subscriptions)
            market_count_correct = market_count == 2
            self.log_test(
                "Market subscription tracking",
                market_count_correct,
                f"Market count: {market_count}",
            )

            # Test user subscriptions
            state.add_user_subscription("user1", {"order"}, {"token1"})
            state.add_user_subscription("user2", {"order", "position"})

            user_count = len(state.user_subscriptions)
            user_count_correct = user_count == 2
            self.log_test(
                "User subscription tracking",
                user_count_correct,
                f"User count: {user_count}",
            )

            # Test subscription removal
            state.remove_market_subscription("market1", {"book"})
            market1_channels = state.market_subscriptions.get("market1", set())
            partial_removal = market1_channels == {"trade"}
            self.log_test(
                "Partial subscription removal",
                partial_removal,
                f"Remaining channels: {market1_channels}",
            )

            # Test complete removal
            state.remove_market_subscription("market1", {"trade"})
            complete_removal = "market1" not in state.market_subscriptions
            self.log_test(
                "Complete subscription removal",
                complete_removal,
                "Market1 completely removed",
            )

            # Test get_all_subscriptions
            all_subs = state.get_all_subscriptions()
            all_subs_valid = len(all_subs) == 3  # 1 market + 2 users
            self.log_test(
                "All subscriptions retrieval",
                all_subs_valid,
                f"Total subscriptions: {len(all_subs)}",
            )

            return True

        except Exception as e:
            self.log_test("Subscription state management", False, f"Error: {e}")
            return False

    def cleanup(self):
        """Clean up temporary files."""
        try:
            import shutil

            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except:
            pass

    async def run_all_tests(self):
        """Run all state management tests."""
        print("=" * 60)
        print("WEBSOCKET STATE MANAGEMENT COMPREHENSIVE TESTS")
        print("=" * 60)

        tests = [
            self.test_streaming_state_serialization(),
            self.test_message_buffering(),
            self.test_state_persistence_manager(),
            self.test_connection_quality_scoring(),
            self.test_message_processing_tracking(),
            self.test_subscription_state_management(),
        ]

        try:
            await asyncio.gather(*tests)
        except Exception as e:
            print(f"Error running tests: {e}")
        finally:
            self.cleanup()

        # Summary
        print("\n" + "=" * 60)
        print("TEST RESULTS SUMMARY")
        print("=" * 60)

        passed_tests = sum(1 for _, passed, _ in self.test_results if passed)
        total_tests = len(self.test_results)

        for test_name, passed, details in self.test_results:
            status = "PASS" if passed else "FAIL"
            print(f"[{status}] {test_name}")
            if not passed and details:
                print(f"        {details}")

        print(f"\nOverall: {passed_tests}/{total_tests} tests passed")

        if passed_tests == total_tests:
            print("🎉 ALL TESTS PASSED! State management is working correctly.")
            return 0
        else:
            print("❌ Some tests failed. Please review the implementation.")
            return 1


async def main():
    """Run the test suite."""
    tester = TestStateManagement()
    return await tester.run_all_tests()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
