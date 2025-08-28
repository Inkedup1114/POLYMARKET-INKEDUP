"""
Unified WebSocket manager for Polymarket streaming data.

This module provides a comprehensive WebSocket client that manages authentication,
subscriptions, and message handling for Polymarket's WebSocket API.
"""

import asyncio
import hashlib
import json
import logging
import os
import pickle
import random
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from .auth import AuthManager
from .handlers import BookHandler, OrderHandler, PriceHandler, TradeHandler
from .models.ws_messages import parse_websocket_message
from .subscription import SubscriptionManager

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """WebSocket connection states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    CLOSING = "closing"
    CLOSED = "closed"


class DisconnectReason(Enum):
    """Reasons for WebSocket disconnection."""

    USER_REQUESTED = "user_requested"
    CONNECTION_LOST = "connection_lost"
    AUTH_FAILED = "auth_failed"
    SERVER_ERROR = "server_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    PROTOCOL_ERROR = "protocol_error"
    UNKNOWN = "unknown"


@dataclass
class ConnectionMetrics:
    """Comprehensive connection metrics."""

    total_connections: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    total_reconnections: int = 0
    successful_reconnections: int = 0
    failed_reconnections: int = 0
    total_disconnections: int = 0
    connection_duration_total: float = 0.0
    longest_connection_duration: float = 0.0
    average_connection_duration: float = 0.0
    messages_received: int = 0
    messages_sent: int = 0
    errors: int = 0
    auth_failures: int = 0
    network_errors: int = 0
    server_errors: int = 0
    timeouts: int = 0

    # Enhanced metrics for improved monitoring
    heartbeats_sent: int = 0
    heartbeat_failures: int = 0
    health_checks_performed: int = 0
    health_check_failures: int = 0
    subscriptions_made: int = 0
    subscriptions_restored: int = 0
    restoration_failures: int = 0
    processing_errors: int = 0
    processing_timeouts: int = 0
    callback_errors: int = 0
    callback_timeouts: int = 0
    json_decode_errors: int = 0
    unhandled_messages: int = 0
    unexpected_errors: int = 0

    # Deduplication metrics
    duplicate_messages_detected: int = 0
    duplicate_messages_dropped: int = 0
    deduplication_cache_hits: int = 0
    deduplication_cache_misses: int = 0
    deduplication_cleanup_operations: int = 0

    def update_connection_duration(self, duration: float):
        """Update connection duration metrics."""
        self.connection_duration_total += duration
        self.longest_connection_duration = max(
            self.longest_connection_duration, duration
        )
        self.average_connection_duration = self.connection_duration_total / max(
            self.total_connections, 1
        )


@dataclass
class StatePersistenceConfig:
    """Configuration for state persistence and recovery."""

    enabled: bool = True
    state_file_path: str = "ws_state.pkl"
    backup_state_file_path: str = "ws_state_backup.pkl"
    save_interval_seconds: float = 30.0
    max_message_buffer_size: int = 1000
    max_state_history: int = 10
    compress_state: bool = True
    encryption_enabled: bool = False
    recovery_timeout_seconds: float = 10.0
    auto_cleanup_old_states: bool = True


@dataclass
class DeduplicationConfig:
    """Configuration for message deduplication."""

    enabled: bool = True
    max_tracked_messages: int = 10000
    message_ttl_seconds: float = 300.0  # 5 minutes
    cleanup_interval_seconds: float = 60.0  # 1 minute
    hash_algorithm: str = "sha256"
    include_timestamp_in_hash: bool = False
    duplicate_metrics_enabled: bool = True


@dataclass
class ReconnectionConfig:
    """Configuration for reconnection behavior."""

    max_attempts: int = 10
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter_range: float = 0.1
    connection_timeout: float = 30.0
    health_check_interval: float = 30.0
    max_message_queue_size: int = 1000

    def calculate_delay(
        self, attempt: int, failure_type: DisconnectReason | None = None
    ) -> float:
        """Calculate reconnection delay with exponential backoff and jitter."""
        # Base exponential backoff
        delay = self.base_delay * (self.exponential_base**attempt)

        # Apply failure-type specific multipliers
        if failure_type == DisconnectReason.AUTH_FAILED:
            delay *= 2.0  # Longer delay for auth failures
        elif failure_type == DisconnectReason.SERVER_ERROR:
            delay *= 1.5  # Moderate delay for server errors
        elif failure_type == DisconnectReason.NETWORK_ERROR:
            delay *= 1.2  # Slight delay increase for network issues

        # Apply maximum delay limit
        delay = min(delay, self.max_delay)

        # Add jitter to prevent thundering herd
        if self.jitter_range > 0:
            jitter = random.uniform(-self.jitter_range, self.jitter_range)
            delay = delay * (1 + jitter)

        return max(0.1, delay)  # Minimum 100ms delay


@dataclass
class StreamingState:
    """Enhanced streaming state with persistence and recovery capabilities."""

    # Core subscription state
    market_subscriptions: dict[str, set[str]] = field(default_factory=dict)
    user_subscriptions: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    active_subscriptions: list[dict[str, Any]] = field(default_factory=list)
    subscription_acks: set[str] = field(default_factory=set)

    # Message buffering for recovery
    message_buffer: deque = field(default_factory=deque)
    processed_message_ids: set[str] = field(default_factory=set)
    last_sequence_number: int = 0

    # Connection state tracking
    last_heartbeat: datetime | None = None
    last_message_time: datetime | None = None
    connection_established_time: datetime | None = None
    last_successful_ping: datetime | None = None

    # Recovery metadata
    state_version: int = 1
    last_save_time: datetime | None = None
    recovery_attempts: int = 0
    max_recovery_attempts: int = 3

    # Connection quality metrics
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

        # Add market subscriptions
        for market, channels in self.market_subscriptions.items():
            subscriptions.append(
                {"type": "market", "market": market, "channels": list(channels)}
            )

        # Add user subscriptions
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
        # Add timestamp and sequence number
        buffered_message = {
            **message,
            "buffered_at": datetime.now().isoformat(),
            "sequence_number": self.last_sequence_number + 1,
        }

        self.message_buffer.append(buffered_message)
        self.last_sequence_number += 1

        # Maintain buffer size limit
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

        # Limit the size of processed message tracking
        if len(self.processed_message_ids) > 10000:
            # Remove oldest half
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
        base_score = max(0.0, 1.0 - error_rate * 2)  # Penalty for errors

        # Bonus for stable connection
        if self.connection_established_time:
            connection_age = (
                datetime.now() - self.connection_established_time
            ).total_seconds()
            stability_bonus = min(
                0.2, connection_age / 3600
            )  # Up to 0.2 bonus for hour-long connections
            base_score += stability_bonus

        return min(1.0, base_score)

    def to_serializable_dict(self) -> dict[str, Any]:
        """Convert state to serializable dictionary."""
        # Convert sets to lists and handle datetime objects
        serializable = {}

        for key, value in asdict(self).items():
            if isinstance(value, set):
                serializable[key] = list(value)
            elif isinstance(value, deque):
                serializable[key] = list(value)
            elif isinstance(value, datetime):
                serializable[key] = value.isoformat() if value else None
            elif isinstance(value, dict):
                # Handle nested dictionaries with sets
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
        # Convert lists back to sets and handle datetime objects
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

    def clear(self):
        """Clear all streaming state."""
        self.market_subscriptions.clear()
        self.user_subscriptions.clear()
        self.active_subscriptions.clear()
        self.subscription_acks.clear()
        self.message_buffer.clear()
        self.processed_message_ids.clear()
        self.last_heartbeat = None
        self.last_message_time = None
        self.connection_established_time = None
        self.last_successful_ping = None
        self.last_save_time = None
        self.recovery_attempts = 0
        self.message_count = 0
        self.error_count = 0
        self.reconnect_count = 0


class MessageDeduplicationTracker:
    """
    Tracks message IDs to prevent processing duplicate messages.

    Uses configurable hashing and time-based cleanup to maintain
    data integrity during high-frequency message processing.
    """

    def __init__(self, config: DeduplicationConfig):
        self.config = config

        # Message hash -> timestamp mapping
        self.message_hashes: dict[str, datetime] = {}

        # Time-ordered queue for efficient cleanup
        self.cleanup_queue: deque = deque()

        # Statistics
        self.total_messages_processed = 0
        self.duplicate_count = 0
        self.cleanup_operations = 0

        # Cleanup task
        self.cleanup_task: asyncio.Task | None = None

        # Lock for thread safety during high-frequency processing
        self._lock = asyncio.Lock()

    async def start_cleanup_task(self):
        """Start the periodic cleanup task."""
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def stop_cleanup_task(self):
        """Stop the periodic cleanup task."""
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

    def _generate_message_hash(self, message_data: dict[str, Any]) -> str:
        """
        Generate a unique hash for a message based on its content.

        Args:
            message_data: The parsed message data

        Returns:
            Hex string hash of the message
        """
        # Create a copy to avoid modifying original
        hash_data = message_data.copy()

        # Remove timestamp from hash if configured
        if not self.config.include_timestamp_in_hash:
            hash_data.pop("timestamp", None)
            hash_data.pop("created_at", None)
            hash_data.pop("updated_at", None)

        # Convert to deterministic JSON string
        json_str = json.dumps(hash_data, sort_keys=True, separators=(",", ":"))

        # Generate hash
        if self.config.hash_algorithm == "sha256":
            return hashlib.sha256(json_str.encode()).hexdigest()
        elif self.config.hash_algorithm == "md5":
            return hashlib.md5(json_str.encode()).hexdigest()
        else:
            # Default to SHA256
            return hashlib.sha256(json_str.encode()).hexdigest()

    async def is_duplicate(self, message_data: dict[str, Any]) -> bool:
        """
        Check if a message is a duplicate and track it.

        Thread-safe implementation with optimistic locking for high-frequency processing.

        Args:
            message_data: The parsed message data

        Returns:
            True if the message is a duplicate, False otherwise
        """
        if not self.config.enabled:
            return False

        # Pre-generate hash outside of lock for better performance
        try:
            message_hash = self._generate_message_hash(message_data)
        except Exception as e:
            # If we can't generate hash, treat as non-duplicate for safety
            logger.warning(f"Failed to generate message hash: {e}")
            return False

        current_time = datetime.now()

        async with self._lock:
            self.total_messages_processed += 1

            # Check if message already exists
            if message_hash in self.message_hashes:
                self.duplicate_count += 1
                return True

            # Add to tracking with validation
            try:
                self.message_hashes[message_hash] = current_time
                self.cleanup_queue.append((message_hash, current_time))

                # Proactive cleanup to prevent memory issues during high frequency
                if len(self.message_hashes) > self.config.max_tracked_messages:
                    # More aggressive cleanup during high frequency
                    cleanup_count = max(
                        100, int(self.config.max_tracked_messages * 0.1)
                    )
                    await self._cleanup_old_messages(force_count=cleanup_count)

                return False

            except Exception as e:
                # If tracking fails, remove from hash table and treat as non-duplicate
                self.message_hashes.pop(message_hash, None)
                logger.error(f"Error tracking message hash: {e}")
                return False

    async def _cleanup_old_messages(self, force_count: int | None = None):
        """
        Clean up old message hashes based on TTL.

        Args:
            force_count: If specified, remove this many oldest messages regardless of TTL
        """
        current_time = datetime.now()
        ttl_threshold = timedelta(seconds=self.config.message_ttl_seconds)
        removed_count = 0

        if force_count:
            # Force removal of oldest messages
            for _ in range(min(force_count, len(self.cleanup_queue))):
                if self.cleanup_queue:
                    message_hash, _ = self.cleanup_queue.popleft()
                    self.message_hashes.pop(message_hash, None)
                    removed_count += 1
        else:
            # TTL-based cleanup
            while self.cleanup_queue:
                message_hash, timestamp = self.cleanup_queue[0]

                if current_time - timestamp > ttl_threshold:
                    self.cleanup_queue.popleft()
                    self.message_hashes.pop(message_hash, None)
                    removed_count += 1
                else:
                    break  # Queue is ordered, so we can stop here

        if removed_count > 0:
            self.cleanup_operations += 1

    async def _periodic_cleanup(self):
        """Periodic cleanup task to remove expired message hashes."""
        while True:
            try:
                await asyncio.sleep(self.config.cleanup_interval_seconds)

                async with self._lock:
                    await self._cleanup_old_messages()

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error but don't stop cleanup
                logger.error(f"Error in deduplication cleanup: {e}")

    def get_statistics(self) -> dict[str, Any]:
        """Get deduplication statistics."""
        return {
            "enabled": self.config.enabled,
            "total_messages_processed": self.total_messages_processed,
            "duplicate_count": self.duplicate_count,
            "duplicate_rate": (
                self.duplicate_count / max(self.total_messages_processed, 1)
            )
            * 100,
            "tracked_messages": len(self.message_hashes),
            "max_tracked_messages": self.config.max_tracked_messages,
            "cleanup_operations": self.cleanup_operations,
            "memory_usage": {
                "message_hashes_size": len(self.message_hashes),
                "cleanup_queue_size": len(self.cleanup_queue),
            },
        }

    async def clear_all(self):
        """Clear all tracked messages."""
        async with self._lock:
            self.message_hashes.clear()
            self.cleanup_queue.clear()
            self.total_messages_processed = 0
            self.duplicate_count = 0


class StatePersistenceManager:
    """
    Manages state persistence and recovery for WebSocket connections.

    Provides robust state serialization, backup management, and recovery
    mechanisms to ensure no data loss during connection failures.
    """

    def __init__(self, config: StatePersistenceConfig):
        self.config = config
        self.state_lock = asyncio.Lock()
        self.save_task: asyncio.Task | None = None
        self.last_successful_save: datetime | None = None

        # Ensure state directory exists
        state_path = Path(self.config.state_file_path)
        state_path.parent.mkdir(parents=True, exist_ok=True)

        backup_path = Path(self.config.backup_state_file_path)
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"State persistence initialized: {self.config.state_file_path}")

    async def start_periodic_save(self, get_state_func):
        """Start periodic state saving task."""
        if self.config.enabled and (self.save_task is None or self.save_task.done()):
            self.save_task = asyncio.create_task(
                self._periodic_save_worker(get_state_func)
            )

    async def stop_periodic_save(self):
        """Stop periodic state saving task."""
        if self.save_task and not self.save_task.done():
            self.save_task.cancel()
            try:
                await self.save_task
            except asyncio.CancelledError:
                pass

    async def save_state(self, state: StreamingState, force: bool = False) -> bool:
        """
        Save streaming state to persistent storage.

        Args:
            state: The streaming state to save
            force: Force save even if not much time has passed

        Returns:
            True if save was successful
        """
        if not self.config.enabled:
            return False

        # Check if enough time has passed since last save
        if not force and self.last_successful_save:
            time_since_save = (
                datetime.now() - self.last_successful_save
            ).total_seconds()
            if time_since_save < self.config.save_interval_seconds:
                return True  # Skip save, too recent

        async with self.state_lock:
            try:
                # Create backup of current state if it exists
                await self._create_backup()

                # Prepare state data
                state_data = {
                    "version": 1,
                    "timestamp": datetime.now().isoformat(),
                    "streaming_state": state.to_serializable_dict(),
                }

                # Save to temporary file first
                temp_path = f"{self.config.state_file_path}.tmp"

                if self.config.compress_state:
                    import gzip

                    with gzip.open(temp_path, "wb") as f:
                        pickle.dump(state_data, f, protocol=pickle.HIGHEST_PROTOCOL)
                else:
                    with open(temp_path, "wb") as f:
                        pickle.dump(state_data, f, protocol=pickle.HIGHEST_PROTOCOL)

                # Atomic move to final location
                os.rename(temp_path, self.config.state_file_path)

                self.last_successful_save = datetime.now()
                state.last_save_time = self.last_successful_save

                logger.debug(
                    f"State saved successfully to {self.config.state_file_path}"
                )
                return True

            except Exception as e:
                logger.error(f"Failed to save state: {e}")
                # Clean up temporary file if it exists
                temp_path = f"{self.config.state_file_path}.tmp"
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError as e:
                        logger.warning(
                            f"Failed to remove temporary state file {temp_path}: {e}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Unexpected error removing temporary state file {temp_path}: {e}",
                            exc_info=True,
                        )
                return False

    async def load_state(self) -> StreamingState | None:
        """
        Load streaming state from persistent storage.

        Returns:
            Loaded StreamingState or None if loading failed
        """
        if not self.config.enabled:
            return None

        async with self.state_lock:
            # Try to load from primary state file
            state = await self._load_from_file(self.config.state_file_path)

            # If primary failed, try backup
            if state is None and os.path.exists(self.config.backup_state_file_path):
                logger.warning("Primary state file failed, trying backup")
                state = await self._load_from_file(self.config.backup_state_file_path)

            if state:
                logger.info(
                    f"State loaded successfully, version: {state.state_version}"
                )
                return state
            else:
                logger.warning("No valid state file found, starting fresh")
                return None

    async def _load_from_file(self, file_path: str) -> StreamingState | None:
        """Load state from a specific file."""
        try:
            if not os.path.exists(file_path):
                return None

            # Check if file is compressed
            if self.config.compress_state:
                import gzip

                with gzip.open(file_path, "rb") as f:
                    state_data = pickle.load(f)
            else:
                with open(file_path, "rb") as f:
                    state_data = pickle.load(f)

            # Validate state data structure
            if not isinstance(state_data, dict) or "streaming_state" not in state_data:
                logger.warning(f"Invalid state data structure in {file_path}")
                return None

            # Check version compatibility
            version = state_data.get("version", 0)
            if version > 1:
                logger.warning(
                    f"State version {version} is newer than supported, skipping"
                )
                return None

            # Create StreamingState from data
            streaming_state = StreamingState.from_serializable_dict(
                state_data["streaming_state"]
            )

            return streaming_state

        except Exception as e:
            logger.error(f"Error loading state from {file_path}: {e}")
            return None

    async def _create_backup(self):
        """Create backup of current state file."""
        try:
            if os.path.exists(self.config.state_file_path):
                # Copy current state to backup location
                import shutil

                shutil.copy2(
                    self.config.state_file_path, self.config.backup_state_file_path
                )
                logger.debug("State backup created")
        except Exception as e:
            logger.warning(f"Failed to create state backup: {e}")

    async def _periodic_save_worker(self, get_state_func):
        """Periodic worker that saves state at regular intervals."""
        while True:
            try:
                await asyncio.sleep(self.config.save_interval_seconds)

                # Get current state
                current_state = get_state_func()
                if current_state:
                    await self.save_state(current_state)

            except asyncio.CancelledError:
                logger.debug("Periodic save worker cancelled")
                break
            except Exception as e:
                logger.error(f"Error in periodic save worker: {e}")
                # Continue running despite errors

    async def cleanup_old_states(self):
        """Clean up old state files if configured."""
        if not self.config.auto_cleanup_old_states:
            return

        try:
            # This could be extended to manage multiple state file versions
            # For now, we just ensure backup exists and is recent
            pass
        except Exception as e:
            logger.error(f"Error cleaning up old states: {e}")

    def get_persistence_statistics(self) -> dict[str, Any]:
        """Get persistence-related statistics."""
        stats = {
            "enabled": self.config.enabled,
            "state_file_path": self.config.state_file_path,
            "backup_file_path": self.config.backup_state_file_path,
            "last_successful_save": (
                self.last_successful_save.isoformat()
                if self.last_successful_save
                else None
            ),
            "state_file_exists": os.path.exists(self.config.state_file_path),
            "backup_file_exists": os.path.exists(self.config.backup_state_file_path),
        }

        # Add file sizes if files exist
        try:
            if os.path.exists(self.config.state_file_path):
                stats["state_file_size_bytes"] = os.path.getsize(
                    self.config.state_file_path
                )
            if os.path.exists(self.config.backup_state_file_path):
                stats["backup_file_size_bytes"] = os.path.getsize(
                    self.config.backup_state_file_path
                )
        except OSError as e:
            logger.warning(f"Failed to get file statistics for state files: {e}")
        except Exception as e:
            logger.error(
                f"Unexpected error getting state file statistics: {e}", exc_info=True
            )

        return stats


class WebSocketManager:
    """
    Enhanced WebSocket manager for Polymarket streaming data.

    This class provides a complete solution for connecting to Polymarket's
    WebSocket API with advanced reconnection logic, state preservation,
    and comprehensive monitoring.

    Features:
    - Enhanced exponential backoff with jitter
    - Intelligent connection state management
    - Streaming state preservation during reconnections
    - Comprehensive error handling and recovery
    - Health monitoring and metrics collection
    - Automatic subscription restoration
    - Message queuing during reconnection
    """

    def __init__(
        self,
        auth_manager: AuthManager,
        ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws",
        reconnection_config: ReconnectionConfig | None = None,
        heartbeat_interval: float = 30.0,
        deduplication_config: DeduplicationConfig | None = None,
        persistence_config: StatePersistenceConfig | None = None,
    ):
        """
        Initialize the WebSocket manager.

        Args:
            auth_manager: Authentication manager for API credentials
            ws_url: WebSocket endpoint URL
            reconnection_config: Configuration for reconnection behavior
            heartbeat_interval: Heartbeat interval (seconds)
            deduplication_config: Configuration for message deduplication
            persistence_config: Configuration for state persistence
        """
        self.auth_manager = auth_manager
        self.ws_url = ws_url
        self.reconnection_config = reconnection_config or ReconnectionConfig()
        self.heartbeat_interval = heartbeat_interval
        self.deduplication_config = deduplication_config or DeduplicationConfig()
        self.persistence_config = persistence_config or StatePersistenceConfig()

        # Initialize components
        self.subscription_manager = SubscriptionManager()
        self.trade_handler = TradeHandler()
        self.order_handler = OrderHandler()
        self.book_handler = BookHandler()
        self.price_handler = PriceHandler()

        # Enhanced WebSocket state
        self.websocket = None
        self.connection_state = ConnectionState.DISCONNECTED
        self.is_running = False
        self.reconnect_attempts = 0
        self.last_disconnect_reason = DisconnectReason.UNKNOWN
        self.connection_start_time = None
        self.last_successful_connection = None

        # State preservation
        self.streaming_state = StreamingState()

        # Message deduplication
        self.deduplication_tracker = MessageDeduplicationTracker(
            self.deduplication_config
        )

        # State persistence
        self.state_persistence = StatePersistenceManager(self.persistence_config)

        # Comprehensive metrics
        self.metrics = ConnectionMetrics()

        # Message routing
        self.message_handlers = {
            "trade": self.trade_handler,
            "order": self.order_handler,
            "book": self.book_handler,
            "price_change": self.price_handler,
            "last_trade_price": self.price_handler,
            "tick_size_change": self.price_handler,
        }

        # Enhanced callbacks
        self.on_connect_callbacks: list[Callable[[], None]] = []
        self.on_disconnect_callbacks: list[Callable[[DisconnectReason], None]] = []
        self.on_error_callbacks: list[Callable[[Exception], None]] = []
        self.on_message_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self.on_state_change_callbacks: list[
            Callable[[ConnectionState, ConnectionState], None]
        ] = []

        # Health monitoring
        self.health_check_task = None
        self.heartbeat_task = None
        self.start_time = None

    def _set_connection_state(self, new_state: ConnectionState):
        """Set connection state and trigger callbacks."""
        old_state = self.connection_state
        self.connection_state = new_state

        logger.debug(f"Connection state changed: {old_state.value} → {new_state.value}")

        # Trigger state change callbacks
        for callback in self.on_state_change_callbacks:
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")

    def _classify_disconnect_reason(self, exception: Exception) -> DisconnectReason:
        """Classify the reason for disconnection based on exception type."""
        if isinstance(exception, ConnectionClosed):
            if exception.code == 1000:  # Normal closure
                return DisconnectReason.USER_REQUESTED
            elif exception.code in [1001, 1006]:  # Going away or abnormal closure
                return DisconnectReason.CONNECTION_LOST
            elif exception.code in [1007, 1002]:  # Invalid data or protocol error
                return DisconnectReason.PROTOCOL_ERROR
            else:
                return DisconnectReason.SERVER_ERROR
        elif isinstance(exception, (OSError, ConnectionError)):
            return DisconnectReason.NETWORK_ERROR
        elif isinstance(exception, asyncio.TimeoutError):
            return DisconnectReason.TIMEOUT
        elif "auth" in str(exception).lower():
            return DisconnectReason.AUTH_FAILED
        else:
            return DisconnectReason.UNKNOWN

    async def start(self) -> None:
        """Start the WebSocket manager with enhanced monitoring."""
        if self.is_running:
            logger.warning("WebSocket manager is already running")
            return

        self.is_running = True
        self.start_time = datetime.now()
        logger.info("Starting enhanced WebSocket manager with state recovery")

        # Attempt to recover previous state
        await self._recover_previous_state()

        # Start health monitoring
        self.health_check_task = asyncio.create_task(self._health_monitor())

        # Start deduplication cleanup task
        if self.deduplication_config.enabled:
            await self.deduplication_tracker.start_cleanup_task()

        # Start state persistence
        if self.persistence_config.enabled:
            await self.state_persistence.start_periodic_save(
                lambda: self.streaming_state
            )

        await self._connect_with_retry()

    async def stop(self) -> None:
        """Stop the WebSocket manager with proper cleanup."""
        if not self.is_running:
            return

        self.is_running = False
        logger.info("Stopping enhanced WebSocket manager")

        self._set_connection_state(ConnectionState.CLOSING)

        # Save final state before shutdown
        if self.persistence_config.enabled:
            await self.state_persistence.save_state(self.streaming_state, force=True)
            await self.state_persistence.stop_periodic_save()

        # Stop deduplication cleanup task
        await self.deduplication_tracker.stop_cleanup_task()

        # Cancel health monitoring tasks
        if self.health_check_task and not self.health_check_task.done():
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass

        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket connection
        if self.websocket:
            try:
                await asyncio.wait_for(self.websocket.close(), timeout=5.0)
            except TimeoutError:
                logger.warning("WebSocket close timeout - forcing closure")
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")

        # Update connection duration metrics
        if self.connection_start_time:
            duration = (datetime.now() - self.connection_start_time).total_seconds()
            self.metrics.update_connection_duration(duration)

        self._set_connection_state(ConnectionState.CLOSED)

        # Clear streaming state
        self.streaming_state.clear()

        logger.info("WebSocket manager stopped")

    async def _connect_with_retry(self) -> None:
        """Enhanced connection logic with proper retry and state management."""
        while (
            self.is_running
            and self.reconnect_attempts < self.reconnection_config.max_attempts
        ):
            try:
                await self._establish_connection()
                break  # Success - exit retry loop

            except Exception as e:
                self.last_disconnect_reason = self._classify_disconnect_reason(e)
                self.metrics.failed_connections += 1

                # Update error-specific metrics
                if self.last_disconnect_reason == DisconnectReason.AUTH_FAILED:
                    self.metrics.auth_failures += 1
                elif self.last_disconnect_reason == DisconnectReason.NETWORK_ERROR:
                    self.metrics.network_errors += 1
                elif self.last_disconnect_reason == DisconnectReason.SERVER_ERROR:
                    self.metrics.server_errors += 1
                elif self.last_disconnect_reason == DisconnectReason.TIMEOUT:
                    self.metrics.timeouts += 1

                self.reconnect_attempts += 1

                logger.error(
                    f"WebSocket connection failed (attempt {self.reconnect_attempts}/"
                    f"{self.reconnection_config.max_attempts}): {e} "
                    f"(reason: {self.last_disconnect_reason.value})"
                )

                # Trigger error callbacks
                for callback in self.on_error_callbacks:
                    try:
                        callback(e)
                    except Exception as cb_error:
                        logger.error(f"Error in error callback: {cb_error}")

                if self.reconnect_attempts < self.reconnection_config.max_attempts:
                    # Calculate intelligent backoff delay
                    delay = self.reconnection_config.calculate_delay(
                        self.reconnect_attempts - 1, self.last_disconnect_reason
                    )

                    logger.info(
                        f"Reconnecting in {delay:.2f} seconds... "
                        f"(reason: {self.last_disconnect_reason.value})"
                    )

                    self._set_connection_state(ConnectionState.RECONNECTING)
                    await asyncio.sleep(delay)
                else:
                    logger.error("Max reconnection attempts reached")
                    self._set_connection_state(ConnectionState.FAILED)
                    break

    async def _establish_connection(self) -> None:
        """Establish a single WebSocket connection attempt with proper cleanup."""
        self._set_connection_state(ConnectionState.CONNECTING)
        self.metrics.total_connections += 1

        logger.info(f"Connecting to WebSocket: {self.ws_url}")

        # Cleanup any existing connection resources
        await self._cleanup_connection_resources()

        try:
            # Get authentication headers
            headers = await self.auth_manager.get_auth_headers()

            # Establish connection with timeout
            self.websocket = await asyncio.wait_for(
                websockets.connect(
                    self.ws_url,
                    extra_headers=headers,
                    ping_interval=self.heartbeat_interval,
                    ping_timeout=10.0,
                    close_timeout=10.0,
                ),
                timeout=self.reconnection_config.connection_timeout,
            )

            # Connection successful
            self.connection_start_time = datetime.now()
            self.last_successful_connection = self.connection_start_time
            was_reconnection = self.reconnect_attempts > 0
            self.reconnect_attempts = 0
            self.metrics.successful_connections += 1

            if was_reconnection:
                self.metrics.successful_reconnections += 1
                self.metrics.total_reconnections += 1

            # Update streaming state for connection
            self.streaming_state.update_connection_established()

            self._set_connection_state(ConnectionState.CONNECTED)
            logger.info("WebSocket connected successfully")

            # Trigger connect callbacks
            for callback in self.on_connect_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in connect callback: {e}")

            # Restore subscriptions and state if reconnecting
            if self.streaming_state.get_all_subscriptions():
                await self._restore_subscriptions_with_recovery()

            # Start heartbeat monitoring
            self.heartbeat_task = asyncio.create_task(self._heartbeat_monitor())

            # Start message processing
            await self._process_messages_enhanced()

        except TimeoutError:
            await self._cleanup_connection_resources()
            raise TimeoutError(
                f"Connection timeout after {self.reconnection_config.connection_timeout}s"
            )
        except Exception:
            await self._cleanup_connection_resources()
            self._set_connection_state(ConnectionState.DISCONNECTED)
            raise

    async def _process_messages_enhanced(self) -> None:
        """Enhanced message processing with comprehensive error handling and monitoring."""
        last_heartbeat = datetime.now()
        consecutive_errors = 0
        max_consecutive_errors = 10

        try:
            async for raw_message in self.websocket:
                if not self.is_running:
                    break

                self.metrics.messages_received += 1
                last_heartbeat = datetime.now()
                consecutive_errors = 0  # Reset on successful message

                try:
                    # Parse message with timeout and validation
                    try:
                        message_data = await asyncio.wait_for(
                            asyncio.to_thread(json.loads, raw_message), timeout=1.0
                        )

                        # Validate message structure for integrity
                        if not isinstance(message_data, dict):
                            logger.warning("Received non-dict message, skipping")
                            self.metrics.processing_errors += 1
                            continue

                    except (TimeoutError, json.JSONDecodeError, ValueError) as e:
                        consecutive_errors += 1
                        logger.warning(f"Message parsing error: {e}")
                        self.metrics.json_decode_errors += 1
                        continue

                    # Check for duplicate message with high-frequency safety
                    try:
                        is_duplicate = await asyncio.wait_for(
                            self.deduplication_tracker.is_duplicate(message_data),
                            timeout=0.1,  # Very short timeout to avoid blocking
                        )
                        if is_duplicate:
                            self.metrics.duplicate_messages_detected += 1
                            self.metrics.duplicate_messages_dropped += 1
                            logger.debug(
                                f"Duplicate message detected and dropped: {message_data.get('type', 'unknown')}"
                            )
                            continue  # Skip processing duplicate message
                    except TimeoutError:
                        logger.warning(
                            "Deduplication check timeout, processing message anyway"
                        )
                        # Continue processing to maintain data flow integrity
                    except Exception as e:
                        logger.warning(
                            f"Deduplication error: {e}, processing message anyway"
                        )
                        # Continue processing to maintain data flow integrity

                    # Parse and validate message structure
                    try:
                        message = parse_websocket_message(message_data)
                    except Exception as e:
                        logger.error(f"Failed to parse websocket message: {e}")
                        self.metrics.processing_errors += 1
                        self.streaming_state.record_error()
                        continue

                    # Generate message ID for tracking
                    message_id = self._generate_message_id(message_data)

                    # Check if already processed (for replay scenarios)
                    if self.streaming_state.is_message_processed(message_id):
                        logger.debug(
                            f"Skipping already processed message: {message_id}"
                        )
                        continue

                    # Buffer message for potential replay
                    self.streaming_state.add_message_to_buffer(
                        message_data, self.persistence_config.max_message_buffer_size
                    )

                    # Update message time for health monitoring
                    self.streaming_state.update_message_time()

                    # Route to appropriate handler with error isolation
                    handler = self.message_handlers.get(message.type)
                    if handler:
                        try:
                            processed_data = await asyncio.wait_for(
                                handler.handle_message(message),
                                timeout=2.0,  # Reasonable timeout for handler processing
                            )

                            # Trigger message callbacks with comprehensive error isolation
                            for callback in self.on_message_callbacks:
                                try:
                                    await asyncio.wait_for(
                                        asyncio.to_thread(callback, processed_data),
                                        timeout=0.5,
                                    )
                                except TimeoutError:
                                    logger.warning(
                                        f"Message callback timeout for {callback.__name__}"
                                    )
                                    self.metrics.callback_timeouts += 1
                                except Exception as e:
                                    logger.error(
                                        f"Error in message callback {callback.__name__}: {e}"
                                    )
                                    self.metrics.callback_errors += 1
                        except TimeoutError:
                            logger.warning(
                                f"Handler timeout for message type: {message.type}"
                            )
                            self.metrics.processing_timeouts += 1
                        except Exception as e:
                            logger.error(
                                f"Handler error for message type {message.type}: {e}"
                            )
                            self.metrics.processing_errors += 1
                            self.streaming_state.record_error()
                    else:
                        logger.debug(f"No handler for message type: {message.type}")
                        self.metrics.unhandled_messages += 1

                    # Mark message as successfully processed
                    self.streaming_state.mark_message_processed(message_id)

                except Exception as e:
                    consecutive_errors += 1
                    logger.error(f"Unexpected error processing message: {e}")
                    self.metrics.unexpected_errors += 1
                    self.streaming_state.record_error()

                # Check for too many consecutive errors
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(
                        f"Too many consecutive errors ({consecutive_errors}), triggering reconnection"
                    )
                    self.last_disconnect_reason = DisconnectReason.PROTOCOL_ERROR
                    raise ConnectionError("Excessive message processing errors")

        except (ConnectionClosed, ConnectionError) as e:
            logger.info(f"WebSocket connection closed: {e}")
            self.last_disconnect_reason = self._classify_disconnect_reason(e)

            # Trigger disconnect callbacks
            for callback in self.on_disconnect_callbacks:
                try:
                    callback(self.last_disconnect_reason)
                except Exception as cb_error:
                    logger.error(f"Error in disconnect callback: {cb_error}")

            # Attempt reconnection if still running
            if self.is_running:
                logger.info("Attempting to reconnect...")
                await self._connect_with_retry()

        except Exception as e:
            logger.error(f"Unexpected error in message processing: {e}")
            self.last_disconnect_reason = self._classify_disconnect_reason(e)
            self.metrics.unexpected_errors += 1

            # Only reconnect if the error seems recoverable
            if self.is_running and not isinstance(e, (SystemExit, KeyboardInterrupt)):
                await asyncio.sleep(1.0)  # Brief pause before retry
                await self._connect_with_retry()
            else:
                raise

    async def _cleanup_connection_resources(self) -> None:
        """Clean up connection resources during reconnection."""
        # Cancel existing tasks
        tasks_to_cancel = []

        if self.heartbeat_task and not self.heartbeat_task.done():
            tasks_to_cancel.append(self.heartbeat_task)

        if tasks_to_cancel:
            for task in tasks_to_cancel:
                task.cancel()

            # Wait for tasks to be cancelled
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks_to_cancel, return_exceptions=True),
                    timeout=2.0,
                )
            except TimeoutError:
                logger.warning("Timeout waiting for tasks to cancel during cleanup")

        # Close existing WebSocket if any
        if self.websocket and not self.websocket.closed:
            try:
                await asyncio.wait_for(self.websocket.close(), timeout=2.0)
            except TimeoutError:
                logger.warning("Timeout closing WebSocket during cleanup")
            except Exception as e:
                logger.debug(f"Error closing WebSocket during cleanup: {e}")

        self.websocket = None
        self.heartbeat_task = None

    async def _restore_subscriptions(self) -> None:
        """Restore streaming state after reconnection."""
        subscriptions = self.streaming_state.get_all_subscriptions()

        if not subscriptions:
            logger.debug("No subscriptions to restore")
            return

        logger.info(f"Restoring {len(subscriptions)} subscriptions")

        try:
            # Build subscription message
            message = self.subscription_manager.build_subscription_message(
                subscriptions
            )

            # Send subscription message
            await asyncio.wait_for(
                self.websocket.send(json.dumps(message)), timeout=5.0
            )

            logger.info("Subscriptions restored successfully")
            self.metrics.subscriptions_restored += len(subscriptions)

            # Update streaming state
            self.streaming_state.mark_subscriptions_restored()

        except TimeoutError:
            logger.error("Timeout restoring subscriptions")
            self.metrics.restoration_failures += 1
        except Exception as e:
            logger.error(f"Error restoring subscriptions: {e}")
            self.metrics.restoration_failures += 1

    async def _health_monitor(self) -> None:
        """Monitor connection health and trigger recovery if needed."""
        health_check_interval = 30.0
        max_missed_heartbeats = 3
        missed_heartbeats = 0

        while self.is_running:
            try:
                await asyncio.sleep(health_check_interval)

                if not self.is_running:
                    break

                # Check connection state
                if self.connection_state != ConnectionState.CONNECTED:
                    continue

                # Check for stale connections (no recent messages)
                now = datetime.now()
                if self.last_successful_connection:
                    time_since_last_success = (
                        now - self.last_successful_connection
                    ).total_seconds()
                    if time_since_last_success > 300:  # 5 minutes without success
                        logger.warning(
                            f"Connection appears stale ({time_since_last_success:.0f}s since last success)"
                        )
                        self.metrics.health_check_failures += 1

                # Check message flow
                if not self.streaming_state.has_recent_messages(
                    60
                ):  # No messages in last minute
                    missed_heartbeats += 1
                    logger.warning(
                        f"No recent messages ({missed_heartbeats}/{max_missed_heartbeats})"
                    )

                    if missed_heartbeats >= max_missed_heartbeats:
                        logger.error(
                            "Connection health check failed - triggering reconnection"
                        )
                        self.last_disconnect_reason = DisconnectReason.TIMEOUT
                        if self.websocket and not self.websocket.closed:
                            await self.websocket.close()
                        missed_heartbeats = 0
                else:
                    missed_heartbeats = 0

                # Update health metrics
                self.metrics.health_checks_performed += 1

            except asyncio.CancelledError:
                logger.debug("Health monitor cancelled")
                break
            except Exception as e:
                logger.error(f"Error in health monitor: {e}")
                self.metrics.health_check_failures += 1

    async def _heartbeat_monitor(self) -> None:
        """Monitor WebSocket heartbeat and connection status."""
        heartbeat_timeout = self.heartbeat_interval * 2

        while self.is_running and self.connection_state == ConnectionState.CONNECTED:
            try:
                # Wait for heartbeat interval
                await asyncio.sleep(self.heartbeat_interval)

                if (
                    not self.is_running
                    or self.connection_state != ConnectionState.CONNECTED
                ):
                    break

                # Check if WebSocket is still alive
                if self.websocket and not self.websocket.closed:
                    # Send ping and wait for pong
                    try:
                        pong_waiter = await asyncio.wait_for(
                            self.websocket.ping(), timeout=10.0
                        )
                        await asyncio.wait_for(pong_waiter, timeout=10.0)

                        self.metrics.heartbeats_sent += 1
                        logger.debug("Heartbeat successful")

                    except TimeoutError:
                        logger.warning("Heartbeat timeout")
                        self.metrics.heartbeat_failures += 1
                        self.last_disconnect_reason = DisconnectReason.TIMEOUT
                        break

                    except Exception as e:
                        logger.warning(f"Heartbeat failed: {e}")
                        self.metrics.heartbeat_failures += 1
                        break
                else:
                    logger.debug("WebSocket closed during heartbeat check")
                    break

            except asyncio.CancelledError:
                logger.debug("Heartbeat monitor cancelled")
                break
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
                break

    def get_connection_metrics(self) -> dict[str, Any]:
        """Get comprehensive connection metrics."""
        now = datetime.now()
        uptime = (now - self.start_time).total_seconds() if self.start_time else 0

        connection_duration = 0
        if (
            self.connection_start_time
            and self.connection_state == ConnectionState.CONNECTED
        ):
            connection_duration = (now - self.connection_start_time).total_seconds()

        return {
            "connection_state": self.connection_state.value,
            "is_running": self.is_running,
            "uptime_seconds": uptime,
            "current_connection_duration": connection_duration,
            "reconnect_attempts": self.reconnect_attempts,
            "last_disconnect_reason": self.last_disconnect_reason.value,
            "metrics": {
                "total_connections": self.metrics.total_connections,
                "successful_connections": self.metrics.successful_connections,
                "failed_connections": self.metrics.failed_connections,
                "successful_reconnections": self.metrics.successful_reconnections,
                "total_reconnections": self.metrics.total_reconnections,
                "messages_received": self.metrics.messages_received,
                "heartbeats_sent": self.metrics.heartbeats_sent,
                "heartbeat_failures": self.metrics.heartbeat_failures,
                "health_checks_performed": self.metrics.health_checks_performed,
                "health_check_failures": self.metrics.health_check_failures,
                "subscriptions_restored": self.metrics.subscriptions_restored,
                "restoration_failures": self.metrics.restoration_failures,
                "processing_errors": self.metrics.processing_errors,
                "processing_timeouts": self.metrics.processing_timeouts,
                "callback_errors": self.metrics.callback_errors,
                "callback_timeouts": self.metrics.callback_timeouts,
                "json_decode_errors": self.metrics.json_decode_errors,
                "unhandled_messages": self.metrics.unhandled_messages,
                "unexpected_errors": self.metrics.unexpected_errors,
                "subscriptions_made": self.metrics.subscriptions_made,
                "auth_failures": self.metrics.auth_failures,
                "network_errors": self.metrics.network_errors,
                "server_errors": self.metrics.server_errors,
                "timeouts": self.metrics.timeouts,
            },
            "streaming_state": {
                "total_subscriptions": len(
                    self.streaming_state.get_all_subscriptions()
                ),
                "has_recent_messages": self.streaming_state.has_recent_messages(60),
                "connection_quality_score": self.streaming_state.get_connection_quality_score(),
                "message_buffer_size": len(self.streaming_state.message_buffer),
                "processed_messages": len(self.streaming_state.processed_message_ids),
                "recovery_attempts": self.streaming_state.recovery_attempts,
                "last_sequence_number": self.streaming_state.last_sequence_number,
            },
            "deduplication_stats": self.deduplication_tracker.get_statistics(),
            "persistence_stats": self.state_persistence.get_persistence_statistics(),
        }

    def add_connect_callback(self, callback: Callable[[], None]) -> None:
        """Add callback for connection events."""
        self.on_connect_callbacks.append(callback)

    def add_disconnect_callback(
        self, callback: Callable[[DisconnectReason], None]
    ) -> None:
        """Add callback for disconnection events."""
        self.on_disconnect_callbacks.append(callback)

    def add_error_callback(self, callback: Callable[[Exception], None]) -> None:
        """Add callback for error events."""
        self.on_error_callbacks.append(callback)

    def add_message_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Add callback for message events."""
        self.on_message_callbacks.append(callback)

    def add_state_change_callback(
        self, callback: Callable[[ConnectionState, ConnectionState], None]
    ) -> None:
        """Add callback for state change events."""
        self.on_state_change_callbacks.append(callback)

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self.websocket is not None and not self.websocket.closed

    async def subscribe_market(self, market: str, channels: list[str]) -> None:
        """
        Subscribe to market channels with streaming state preservation.

        Args:
            market: Market contract address
            channels: List of channels to subscribe (trade, order, book, etc.)
        """
        if not self.is_connected:
            raise RuntimeError("WebSocket not connected")

        subscription = self.subscription_manager.create_market_subscription(
            market, channels
        )
        message = self.subscription_manager.build_subscription_message([subscription])

        try:
            await asyncio.wait_for(
                self.websocket.send(json.dumps(message)), timeout=5.0
            )

            # Store subscription in streaming state for recovery
            self.streaming_state.add_market_subscription(market, set(channels))

            logger.info(f"Subscribed to {channels} for market {market}")
            self.metrics.subscriptions_made += 1

        except TimeoutError:
            logger.error(f"Timeout subscribing to {channels} for market {market}")
            raise
        except Exception as e:
            logger.error(f"Error subscribing to {channels} for market {market}: {e}")
            raise

    async def subscribe_user(
        self, user_address: str, channels: list[str], tokens: list[str] | None = None
    ) -> None:
        """
        Subscribe to user channels with streaming state preservation.

        Args:
            user_address: User's wallet address
            channels: List of channels to subscribe (order, etc.)
            tokens: Optional list of tokens to filter
        """
        if not self.is_connected:
            raise RuntimeError("WebSocket not connected")

        subscription = self.subscription_manager.create_user_subscription(
            user_address, channels, tokens
        )
        message = self.subscription_manager.build_subscription_message([subscription])

        try:
            await asyncio.wait_for(
                self.websocket.send(json.dumps(message)), timeout=5.0
            )

            # Store subscription in streaming state for recovery
            token_set = set(tokens) if tokens else None
            self.streaming_state.add_user_subscription(
                user_address, set(channels), token_set
            )

            logger.info(f"Subscribed to {channels} for user {user_address}")
            self.metrics.subscriptions_made += 1

        except TimeoutError:
            logger.error(f"Timeout subscribing to {channels} for user {user_address}")
            raise
        except Exception as e:
            logger.error(
                f"Error subscribing to {channels} for user {user_address}: {e}"
            )
            raise

    async def unsubscribe_market(self, market: str, channels: list[str]) -> None:
        """
        Unsubscribe from market channels.

        Args:
            market: Market contract address
            channels: List of channels to unsubscribe
        """
        if not self.is_connected:
            return

        subscription = self.subscription_manager.create_market_subscription(
            market, channels
        )
        message = self.subscription_manager.build_unsubscription_message([subscription])

        await self.websocket.send(json.dumps(message))

        # Remove from streaming state
        self.streaming_state.remove_market_subscription(market, set(channels))

        logger.info(f"Unsubscribed from {channels} for market {market}")

    async def unsubscribe_user(self, user_address: str, channels: list[str]) -> None:
        """
        Unsubscribe from user channels.

        Args:
            user_address: User's wallet address
            channels: List of channels to unsubscribe
        """
        if not self.is_connected:
            return

        subscription = self.subscription_manager.create_user_subscription(
            user_address, channels
        )
        message = self.subscription_manager.build_unsubscription_message([subscription])

        await self.websocket.send(json.dumps(message))

        # Remove from streaming state
        self.streaming_state.remove_user_subscription(user_address, set(channels))

        logger.info(f"Unsubscribed from {channels} for user {user_address}")

    async def _recover_previous_state(self) -> None:
        """Attempt to recover previous streaming state."""
        if not self.persistence_config.enabled:
            logger.debug("State persistence disabled, skipping recovery")
            return

        try:
            logger.info("Attempting to recover previous streaming state...")
            recovered_state = await self.state_persistence.load_state()

            if recovered_state:
                # Validate recovered state
                if self._validate_recovered_state(recovered_state):
                    self.streaming_state = recovered_state
                    logger.info(
                        f"Successfully recovered state with {len(recovered_state.get_all_subscriptions())} subscriptions"
                    )
                    logger.info(
                        f"State quality score: {recovered_state.get_connection_quality_score():.2f}"
                    )
                else:
                    logger.warning("Recovered state validation failed, starting fresh")
            else:
                logger.info("No previous state found, starting fresh")

        except Exception as e:
            logger.error(f"Error during state recovery: {e}")
            # Continue with fresh state

    def _validate_recovered_state(self, state: StreamingState) -> bool:
        """Validate that recovered state is usable."""
        try:
            # Basic validation checks
            if not isinstance(state.market_subscriptions, dict):
                return False
            if not isinstance(state.user_subscriptions, dict):
                return False

            # Check if state is too old
            if state.last_save_time:
                age = (datetime.now() - state.last_save_time).total_seconds()
                max_age = 3600  # 1 hour
                if age > max_age:
                    logger.warning(
                        f"Recovered state is too old ({age:.0f}s), discarding"
                    )
                    return False

            # Check connection quality
            quality_score = state.get_connection_quality_score()
            if quality_score < 0.3:  # Poor quality threshold
                logger.warning(
                    f"Recovered state has poor quality score ({quality_score:.2f}), discarding"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating recovered state: {e}")
            return False

    def _generate_message_id(self, message_data: dict[str, Any]) -> str:
        """Generate unique ID for message tracking."""
        # Create ID based on message content and timestamp
        id_parts = [
            str(message_data.get("type", "")),
            str(message_data.get("market", "")),
            str(message_data.get("timestamp", "")),
            str(message_data.get("id", "")),
        ]

        # Use first 12 chars of hash for reasonable ID length
        import hashlib

        combined = "|".join(id_parts)
        return hashlib.md5(combined.encode()).hexdigest()[:12]

    async def _restore_subscriptions_with_recovery(self) -> None:
        """Enhanced subscription restoration with recovery mechanisms."""
        subscriptions = self.streaming_state.get_all_subscriptions()

        if not subscriptions:
            logger.debug("No subscriptions to restore")
            return

        logger.info(f"Restoring {len(subscriptions)} subscriptions with recovery")

        try:
            # Reset recovery attempts if max reached
            if (
                self.streaming_state.recovery_attempts
                >= self.streaming_state.max_recovery_attempts
            ):
                logger.warning("Max recovery attempts reached, resetting counter")
                self.streaming_state.recovery_attempts = 0

            self.streaming_state.recovery_attempts += 1

            # Build subscription message
            message = self.subscription_manager.build_subscription_message(
                subscriptions
            )

            # Send subscription message with retry
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await asyncio.wait_for(
                        self.websocket.send(json.dumps(message)),
                        timeout=10.0,  # Longer timeout for recovery
                    )
                    break
                except TimeoutError:
                    if attempt == max_retries - 1:
                        raise
                    logger.warning(
                        f"Subscription restore timeout, attempt {attempt + 1}/{max_retries}"
                    )
                    await asyncio.sleep(2**attempt)  # Exponential backoff

            logger.info("Subscriptions restored successfully")
            self.metrics.subscriptions_restored += len(subscriptions)

            # Reset recovery attempts on success
            self.streaming_state.recovery_attempts = 0

        except Exception as e:
            logger.error(f"Error restoring subscriptions: {e}")
            self.metrics.restoration_failures += 1

            # If we've failed too many times, clear subscriptions to avoid infinite loops
            if (
                self.streaming_state.recovery_attempts
                >= self.streaming_state.max_recovery_attempts
            ):
                logger.warning("Too many recovery failures, clearing subscriptions")
                self.streaming_state.clear()

    async def replay_buffered_messages(self, since_sequence: int | None = None) -> int:
        """
        Replay buffered messages for recovery.

        Args:
            since_sequence: Replay messages since this sequence number

        Returns:
            Number of messages replayed
        """
        if not self.persistence_config.enabled:
            return 0

        buffered_messages = self.streaming_state.get_buffered_messages(since_sequence)

        if not buffered_messages:
            logger.debug("No buffered messages to replay")
            return 0

        logger.info(f"Replaying {len(buffered_messages)} buffered messages")

        replayed_count = 0
        for buffered_msg in buffered_messages:
            try:
                # Extract original message data
                original_data = {
                    k: v
                    for k, v in buffered_msg.items()
                    if k not in ["buffered_at", "sequence_number"]
                }

                # Process as if it's a new message (but skip buffering again)
                message = parse_websocket_message(original_data)
                message_id = self._generate_message_id(original_data)

                # Skip if already processed
                if self.streaming_state.is_message_processed(message_id):
                    continue

                # Route to handler
                handler = self.message_handlers.get(message.type)
                if handler:
                    processed_data = await handler.handle_message(message)

                    # Trigger callbacks (with shorter timeout for replay)
                    for callback in self.on_message_callbacks:
                        try:
                            await asyncio.wait_for(
                                asyncio.to_thread(callback, processed_data), timeout=0.2
                            )
                        except TimeoutError:
                            logger.debug(
                                f"Callback timeout during replay for {callback.__name__}"
                            )
                        except Exception as e:
                            logger.warning(f"Error in callback during replay: {e}")

                    # Mark as processed
                    self.streaming_state.mark_message_processed(message_id)
                    replayed_count += 1

            except Exception as e:
                logger.error(f"Error replaying message: {e}")

        logger.info(f"Successfully replayed {replayed_count} messages")
        return replayed_count

    def add_connect_callback(self, callback: Callable[[], None]) -> None:
        """Add callback to be called on connection."""
        self.on_connect_callbacks.append(callback)

    def add_disconnect_callback(self, callback: Callable[[], None]) -> None:
        """Add callback to be called on disconnection."""
        self.on_disconnect_callbacks.append(callback)

    def add_error_callback(self, callback: Callable[[Exception], None]) -> None:
        """Add callback to be called on errors."""
        self.on_error_callbacks.append(callback)

    def add_message_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Add callback to be called on message processing."""
        self.on_message_callbacks.append(callback)

    def get_status(self) -> dict[str, Any]:
        """
        Get current status and metrics.

        Returns:
            Status dictionary with connection info and metrics
        """
        uptime = 0
        if self.start_time:
            uptime = (datetime.now() - self.start_time).total_seconds()

        return {
            "is_connected": self.is_connected,
            "is_running": self.is_running,
            "reconnect_attempts": self.reconnect_attempts,
            "uptime": uptime,
            "metrics": self.metrics,
            "deduplication": self.deduplication_tracker.get_statistics(),
            "persistence": self.state_persistence.get_persistence_statistics(),
            "streaming_state": {
                "quality_score": self.streaming_state.get_connection_quality_score(),
                "message_buffer_size": len(self.streaming_state.message_buffer),
                "processed_messages": len(self.streaming_state.processed_message_ids),
                "recovery_attempts": self.streaming_state.recovery_attempts,
                "message_count": self.streaming_state.message_count,
                "error_count": self.streaming_state.error_count,
            },
            "subscriptions": self.subscription_manager.get_active_subscriptions(),
            "cache_sizes": {
                "trades": self.trade_handler.get_cache_size(),
                "orders": self.order_handler.get_cache_size(),
                "books": self.book_handler.get_cache_size(),
                "prices": self.price_handler.get_cache_size(),
            },
        }

    def get_market_data(self, market: str) -> dict[str, Any]:
        """
        Get comprehensive market data for a specific market.

        Args:
            market: Market contract address

        Returns:
            Dictionary with all available market data
        """
        return {
            "order_book": self.book_handler.get_order_book(market),
            "trades": self.trade_handler.get_trades_for_market(market),
            "orders": self.order_handler.get_market_orders(market),
            "price": self.price_handler.get_current_price(market),
            "tick_size": self.price_handler.get_tick_size(market),
        }

    async def send_heartbeat(self) -> None:
        """Send heartbeat message to keep connection alive."""
        if self.is_connected:
            try:
                await self.websocket.ping()
                self.last_heartbeat = datetime.now()
            except Exception as e:
                logger.error(f"Error sending heartbeat: {e}")

    async def health_check(self) -> dict[str, Any]:
        """
        Perform health check on the WebSocket connection.

        Returns:
            Health check results
        """
        status = self.get_status()

        # Check if we need to reconnect
        needs_reconnect = (
            not self.is_connected
            and self.is_running
            and self.reconnect_attempts < self.max_reconnect_attempts
        )

        return {
            "healthy": self.is_connected,
            "needs_reconnect": needs_reconnect,
            "status": status,
        }


# Convenience function for quick setup
async def create_ws_manager(
    private_key: str,
    signature_type: str = "EOA",
    enable_deduplication: bool = True,
    deduplication_config: DeduplicationConfig | None = None,
    enable_persistence: bool = True,
    persistence_config: StatePersistenceConfig | None = None,
    **kwargs,
) -> WebSocketManager:
    """
    Create a WebSocket manager with authentication, deduplication, and persistence.

    Args:
        private_key: Private key for authentication
        signature_type: Signature type (EOA, POLY_GNOSIS_SAFE, POLY_PROXY)
        enable_deduplication: Whether to enable message deduplication
        deduplication_config: Custom deduplication configuration
        enable_persistence: Whether to enable state persistence
        persistence_config: Custom persistence configuration
        **kwargs: Additional arguments for WebSocketManager

    Returns:
        Configured WebSocketManager instance
    """
    auth_manager = AuthManager(private_key, signature_type)
    await auth_manager.initialize()

    # Setup deduplication configuration
    if deduplication_config is None:
        deduplication_config = DeduplicationConfig(enabled=enable_deduplication)

    # Setup persistence configuration
    if persistence_config is None:
        persistence_config = StatePersistenceConfig(enabled=enable_persistence)

    return WebSocketManager(
        auth_manager,
        deduplication_config=deduplication_config,
        persistence_config=persistence_config,
        **kwargs,
    )
