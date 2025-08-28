"""
Order message handler for processing order events from Polymarket WebSocket stream.
"""

import logging
from typing import Any

from ..models.ws_messages import OrderMessage, WebSocketMessage
from .base_handler import BaseMessageHandler
from .validation_utils import ValidationLevel

logger = logging.getLogger(__name__)


class OrderHandler(BaseMessageHandler):
    """
    Handler for processing order messages from Polymarket WebSocket stream.

    Processes order creation, updates, and cancellation events.
    """

    def __init__(
        self, validation_level: ValidationLevel = ValidationLevel.MODERATE
    ) -> None:
        """Initialize the order handler."""
        super().__init__("OrderHandler", validation_level)
        self._orders: dict[str, dict[str, Any]] = {}
        self._user_orders: dict[str, list[str]] = {}

    async def _handle_message(self, message: WebSocketMessage) -> dict[str, Any]:
        """
        Process an order message.

        Args:
            message: Order message to process

        Returns:
            Processed order data
        """
        if not isinstance(message, OrderMessage):
            raise ValueError(f"Expected OrderMessage, got {type(message)}")

        order_data = {
            "order_id": message.order_id,
            "market": message.market,
            "owner": message.owner,
            "side": message.side.value,
            "price": message.price,
            "size": message.size,
            "status": message.status.value,
            "order_type": message.order_type.value,
            "timestamp": message.timestamp,
            "raw_data": message.dict(),
        }

        # Store order
        self._orders[message.order_id] = order_data

        # Track user's orders
        if message.owner not in self._user_orders:
            self._user_orders[message.owner] = []

        if message.order_id not in self._user_orders[message.owner]:
            self._user_orders[message.owner].append(message.order_id)

        # Log based on status
        if message.status.value == "open":
            logger.info(
                f"New order: {message.order_id} | "
                f"market={message.market} | "
                f"side={message.side.value} | "
                f"price={message.price} | "
                f"size={message.size}"
            )
        elif message.status.value == "filled":
            logger.info(
                f"Order filled: {message.order_id} | "
                f"market={message.market} | "
                f"filled_size={message.size}"
            )
        elif message.status.value == "cancelled":
            logger.info(
                f"Order cancelled: {message.order_id} | " f"market={message.market}"
            )
        else:
            logger.debug(
                f"Order update: {message.order_id} | "
                f"status={message.status.value} | "
                f"size={message.size}"
            )

        return order_data

    def supports_message_type(self, message_type: str) -> bool:
        """Check if this handler supports the given message type."""
        return message_type == "order"

    def get_supported_message_types(self) -> list[str]:
        """Get list of supported message types."""
        return ["order"]

    async def _validate_by_type(
        self, message: WebSocketMessage, message_type: str
    ) -> tuple[bool, list[str], dict[str, Any] | None]:
        """Perform order-specific validation."""
        issues = []
        sanitized_data = {}

        if not isinstance(message, OrderMessage):
            issues.append("Error: Expected OrderMessage")
            return False, issues, None

        # Validate required fields
        required_fields = [
            "order_id",
            "market",
            "owner",
            "side",
            "price",
            "size",
            "status",
        ]
        missing_fields = []

        for field in required_fields:
            if not hasattr(message, field) or getattr(message, field) is None:
                missing_fields.append(field)

        if missing_fields:
            issues.append(f"Error: Missing required fields: {missing_fields}")
            if self.validation_level == ValidationLevel.STRICT:
                return False, issues, None

        # Validate price and size
        if hasattr(message, "price"):
            try:
                price = message.price
                if price <= 0:
                    issues.append(f"Error: Invalid price: {price} (must be positive)")
                elif price > 1:
                    issues.append(f"Warning: Price {price} exceeds maximum of 1.0")

                sanitized_data["validated_price"] = price
            except (TypeError, ValueError) as e:
                issues.append(f"Error: Invalid price format: {e}")

        if hasattr(message, "size"):
            try:
                size = message.size
                if size <= 0:
                    issues.append(f"Error: Invalid size: {size} (must be positive)")

                sanitized_data["validated_size"] = size
            except (TypeError, ValueError) as e:
                issues.append(f"Error: Invalid size format: {e}")

        # Validate order ID format
        if hasattr(message, "order_id") and message.order_id:
            order_id = message.order_id
            if not isinstance(order_id, str) or len(order_id) < 1:
                issues.append("Warning: Order ID appears invalid")

        # Validate market address format
        if hasattr(message, "market") and message.market:
            market = message.market
            if not isinstance(market, str) or len(market) < 20:
                issues.append("Warning: Market address appears invalid")

        # Validate owner address format
        if hasattr(message, "owner") and message.owner:
            owner = message.owner
            if not isinstance(owner, str) or len(owner) < 20:
                issues.append("Warning: Owner address appears invalid")

        # Validate side enum
        if hasattr(message, "side"):
            try:
                side = (
                    message.side.value
                    if hasattr(message.side, "value")
                    else str(message.side)
                )
                if side not in ["buy", "sell"]:
                    issues.append(f"Warning: Invalid order side: {side}")
            except Exception as e:
                issues.append(f"Warning: Invalid order side format: {e}")

        # Validate status enum
        if hasattr(message, "status"):
            try:
                status = (
                    message.status.value
                    if hasattr(message.status, "value")
                    else str(message.status)
                )
                valid_statuses = ["pending", "open", "filled", "cancelled", "failed"]
                if status not in valid_statuses:
                    issues.append(f"Warning: Invalid order status: {status}")
            except Exception as e:
                issues.append(f"Warning: Invalid order status format: {e}")

        # Determine if validation passes
        error_count = len([issue for issue in issues if issue.startswith("Error:")])

        if error_count > 0 and self.validation_level == ValidationLevel.STRICT:
            return False, issues, None
        elif error_count > 0 and self.validation_level == ValidationLevel.MODERATE:
            return False, issues, None
        else:
            return True, issues, sanitized_data

    def _validate_message(self, message: WebSocketMessage) -> bool:
        """Validate order message with specific checks for backward compatibility."""
        # First run base validation
        if not super()._validate_message(message):
            return False

        # Check if it's an OrderMessage
        if not isinstance(message, OrderMessage):
            logger.error(f"Expected OrderMessage, got {type(message)}")
            return False

        # Validate required fields
        required_fields = [
            "order_id",
            "market",
            "owner",
            "side",
            "price",
            "size",
            "status",
        ]
        for field in required_fields:
            if not hasattr(message, field) or getattr(message, field) is None:
                logger.error(f"OrderMessage missing required field: {field}")
                return False

        # Validate price and size are positive
        try:
            if message.price <= 0:
                logger.error(f"OrderMessage has invalid price: {message.price}")
                return False

            if message.size <= 0:
                logger.error(f"OrderMessage has invalid size: {message.size}")
                return False
        except (TypeError, ValueError) as e:
            logger.error(f"OrderMessage has invalid numeric values: {e}")
            return False

        return True

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        """
        Get order by ID.

        Args:
            order_id: Order ID

        Returns:
            Order data if found
        """
        return self._orders.get(order_id)

    def get_user_orders(self, user_address: str) -> list[dict[str, Any]]:
        """
        Get all orders for a user.

        Args:
            user_address: User's wallet address

        Returns:
            List of order data
        """
        order_ids = self._user_orders.get(user_address, [])
        return [self._orders[oid] for oid in order_ids if oid in self._orders]

    def get_open_orders(self, market: str | None = None) -> list[dict[str, Any]]:
        """
        Get open orders, optionally filtered by market.

        Args:
            market: Market contract address (optional)

        Returns:
            List of open order data
        """
        orders = []
        for order_data in self._orders.values():
            if order_data["status"] == "open":
                if market is None or order_data["market"] == market:
                    orders.append(order_data)
        return orders

    def get_market_orders(self, market: str) -> list[dict[str, Any]]:
        """
        Get all orders for a specific market.

        Args:
            market: Market contract address

        Returns:
            List of order data
        """
        return [order for order in self._orders.values() if order["market"] == market]

    def clear_cache(self) -> None:
        """Clear all cached orders."""
        self._orders.clear()
        self._user_orders.clear()

    def get_cache_size(self) -> int:
        """Get the current cache size."""
        return len(self._orders)
