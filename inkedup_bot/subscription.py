"""
Subscription manager for Polymarket WebSocket connections.

This module handles dynamic subscription management for both market and user channels,
including token filtering and subscription state tracking.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ChannelType(str, Enum):
    """WebSocket channel types."""

    MARKET = "market"
    USER = "user"


class SubscriptionStatus(str, Enum):
    """Subscription status enumeration."""

    PENDING = "pending"
    ACTIVE = "active"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubscriptionConfig:
    """Configuration for a subscription."""

    channel: ChannelType
    tokens: set[str] = field(default_factory=set)
    user_address: str | None = None
    initial_dump: bool = True
    include_trades: bool = True
    include_orders: bool = True
    include_book: bool = True
    include_price_changes: bool = True


@dataclass
class SubscriptionState:
    """State tracking for a subscription."""

    config: SubscriptionConfig
    status: SubscriptionStatus = SubscriptionStatus.PENDING
    subscribed_at: datetime | None = None
    last_heartbeat: datetime | None = None
    error_message: str | None = None
    message_count: int = 0


class SubscriptionManager:
    """
    Manages WebSocket subscriptions for market and user channels.

    Handles dynamic subscription updates, token filtering, and state tracking.
    """

    def __init__(self) -> None:
        """Initialize the subscription manager."""
        self._subscriptions: dict[str, SubscriptionState] = {}
        self._lock = asyncio.Lock()
        self._callbacks: dict[str, list[Callable[..., Awaitable[None]]]] = {
            "subscription_added": [],
            "subscription_removed": [],
            "subscription_updated": [],
            "subscription_failed": [],
        }

    def add_callback(
        self, event: str, callback: Callable[..., Awaitable[None]]
    ) -> None:
        """
        Add a callback for subscription events.

        Args:
            event: Event name ('subscription_added', 'subscription_removed', etc.)
            callback: Callback function to call
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)
        else:
            logger.warning(f"Unknown event type: {event}")

    async def add_subscription(
        self, subscription_id: str, config: SubscriptionConfig
    ) -> bool:
        """
        Add a new subscription.

        Args:
            subscription_id: Unique identifier for the subscription
            config: Subscription configuration

        Returns:
            True if subscription was added successfully
        """
        async with self._lock:
            if subscription_id in self._subscriptions:
                logger.warning(f"Subscription {subscription_id} already exists")
                return False

            state = SubscriptionState(config=config, status=SubscriptionStatus.PENDING)

            self._subscriptions[subscription_id] = state

            # Notify callbacks
            for callback in self._callbacks["subscription_added"]:
                try:
                    await callback(subscription_id, config)
                except Exception as e:
                    logger.error(f"Error in subscription_added callback: {e}")

            logger.info(
                f"Added subscription {subscription_id} for channel {config.channel}"
            )
            return True

    async def remove_subscription(self, subscription_id: str) -> bool:
        """
        Remove a subscription.

        Args:
            subscription_id: Subscription identifier to remove

        Returns:
            True if subscription was removed successfully
        """
        async with self._lock:
            if subscription_id not in self._subscriptions:
                logger.warning(f"Subscription {subscription_id} not found")
                return False

            config = self._subscriptions[subscription_id].config
            del self._subscriptions[subscription_id]

            # Notify callbacks
            for callback in self._callbacks["subscription_removed"]:
                try:
                    await callback(subscription_id, config)
                except Exception as e:
                    logger.error(f"Error in subscription_removed callback: {e}")

            logger.info(f"Removed subscription {subscription_id}")
            return True

    async def update_subscription(
        self, subscription_id: str, new_config: SubscriptionConfig
    ) -> bool:
        """
        Update an existing subscription.

        Args:
            subscription_id: Subscription identifier to update
            new_config: New subscription configuration

        Returns:
            True if subscription was updated successfully
        """
        async with self._lock:
            if subscription_id not in self._subscriptions:
                logger.warning(f"Subscription {subscription_id} not found")
                return False

            old_config = self._subscriptions[subscription_id].config
            self._subscriptions[subscription_id].config = new_config

            # Notify callbacks
            for callback in self._callbacks["subscription_updated"]:
                try:
                    await callback(subscription_id, old_config, new_config)
                except Exception as e:
                    logger.error(f"Error in subscription_updated callback: {e}")

            logger.info(f"Updated subscription {subscription_id}")
            return True

    async def get_subscription(self, subscription_id: str) -> SubscriptionState | None:
        """
        Get subscription state by ID.

        Args:
            subscription_id: Subscription identifier

        Returns:
            Subscription state if found, None otherwise
        """
        async with self._lock:
            return self._subscriptions.get(subscription_id)

    async def get_subscriptions_by_channel(
        self, channel: ChannelType
    ) -> dict[str, SubscriptionState]:
        """
        Get all subscriptions for a specific channel.

        Args:
            channel: Channel type to filter by

        Returns:
            Dictionary of subscription ID to state
        """
        async with self._lock:
            return {
                sid: state
                for sid, state in self._subscriptions.items()
                if state.config.channel == channel
            }

    async def get_subscriptions_by_token(
        self, token: str
    ) -> dict[str, SubscriptionState]:
        """
        Get all subscriptions that include a specific token.

        Args:
            token: Token address to filter by

        Returns:
            Dictionary of subscription ID to state
        """
        async with self._lock:
            return {
                sid: state
                for sid, state in self._subscriptions.items()
                if token in state.config.tokens
            }

    async def get_all_subscriptions(self) -> dict[str, SubscriptionState]:
        """
        Get all subscriptions.

        Returns:
            Dictionary of all subscription states
        """
        async with self._lock:
            return dict(self._subscriptions)

    async def update_status(
        self,
        subscription_id: str,
        status: SubscriptionStatus,
        error_message: str | None = None,
    ) -> bool:
        """
        Update subscription status.

        Args:
            subscription_id: Subscription identifier
            status: New status
            error_message: Optional error message for failed status

        Returns:
            True if status was updated
        """
        async with self._lock:
            if subscription_id not in self._subscriptions:
                return False

            state = self._subscriptions[subscription_id]
            state.status = status
            state.error_message = error_message

            if status == SubscriptionStatus.ACTIVE:
                state.subscribed_at = datetime.utcnow()

            if status == SubscriptionStatus.FAILED and error_message:
                logger.error(f"Subscription {subscription_id} failed: {error_message}")
                for callback in self._callbacks["subscription_failed"]:
                    try:
                        await callback(subscription_id, error_message)
                    except Exception as e:
                        logger.error(f"Error in subscription_failed callback: {e}")

            return True

    async def increment_message_count(self, subscription_id: str) -> bool:
        """
        Increment message count for a subscription.

        Args:
            subscription_id: Subscription identifier

        Returns:
            True if count was incremented
        """
        async with self._lock:
            if subscription_id not in self._subscriptions:
                return False

            self._subscriptions[subscription_id].message_count += 1
            self._subscriptions[subscription_id].last_heartbeat = datetime.utcnow()
            return True

    async def update_heartbeat(self, subscription_id: str) -> bool:
        """
        Update last heartbeat time for a subscription.

        Args:
            subscription_id: Subscription identifier

        Returns:
            True if heartbeat was updated
        """
        async with self._lock:
            if subscription_id not in self._subscriptions:
                return False

            self._subscriptions[subscription_id].last_heartbeat = datetime.utcnow()
            return True

    async def get_subscription_message(
        self, subscription_id: str
    ) -> dict[str, Any] | None:
        """
        Get the WebSocket subscription message for a subscription.

        Args:
            subscription_id: Subscription identifier

        Returns:
            Subscription message dictionary or None if subscription not found
        """
        state = await self.get_subscription(subscription_id)
        if not state:
            return None

        config = state.config

        if config.channel == ChannelType.MARKET:
            message = {
                "type": "subscribe",
                "channel": "market",
                "tokens": list(config.tokens),
                "initial_dump": config.initial_dump,
            }

            # Add message type filters
            if not config.include_trades:
                message["trades"] = False
            if not config.include_orders:
                message["orders"] = False
            if not config.include_book:
                message["book"] = False
            if not config.include_price_changes:
                message["price_changes"] = False

        elif config.channel == ChannelType.USER:
            if not config.user_address:
                logger.error(
                    f"User address required for user channel subscription {subscription_id}"
                )
                return None

            message = {
                "type": "subscribe",
                "channel": "user",
                "user": config.user_address,
            }

        else:
            logger.error(f"Unknown channel type: {config.channel}")
            return None

        return message

    async def get_all_subscription_messages(self) -> dict[str, dict[str, Any]]:
        """
        Get all subscription messages.

        Returns:
            Dictionary mapping subscription ID to subscription message
        """
        messages = {}
        for subscription_id in self._subscriptions:
            message = await self.get_subscription_message(subscription_id)
            if message:
                messages[subscription_id] = message

        return messages

    async def cleanup(self) -> None:
        """Clean up resources."""
        async with self._lock:
            self._subscriptions.clear()
            self._callbacks.clear()
