"""
Trade message handler for processing trade events from Polymarket WebSocket stream.
"""

import logging
from decimal import Decimal
from typing import Any

from ..models.ws_messages import TradeMessage, WebSocketMessage
from .base_handler import BaseMessageHandler
from .validation_utils import ValidationLevel

logger = logging.getLogger(__name__)


class TradeHandler(BaseMessageHandler):
    """
    Handler for processing trade messages from Polymarket WebSocket stream.

    Processes trade execution events and extracts relevant market data.
    """

    def __init__(
        self, validation_level: ValidationLevel = ValidationLevel.MODERATE
    ) -> None:
        """Initialize the trade handler."""
        super().__init__("TradeHandler", validation_level)
        self._trade_cache: dict[str, dict[str, Any]] = {}

    async def _handle_message(self, message: WebSocketMessage) -> dict[str, Any]:
        """
        Process a trade message.

        Args:
            message: Trade message to process

        Returns:
            Processed trade data
        """
        if not isinstance(message, TradeMessage):
            raise ValueError(f"Expected TradeMessage, got {type(message)}")

        trade_data = {
            "market": message.market,
            "transaction_hash": message.transaction_hash,
            "taker_order_id": message.taker_order_id,
            "timestamp": message.timestamp,
            "maker_orders": [],
            "total_size": Decimal("0"),
            "weighted_avg_price": Decimal("0"),
            "trade_count": len(message.maker_orders),
        }

        # Process maker orders
        total_value = Decimal("0")
        for order in message.maker_orders:
            try:
                price = Decimal(str(order.get("price", "0")))
                size = Decimal(str(order.get("size", "0")))
                value = price * size

                maker_order = {
                    "order_id": str(order.get("orderId", "")),
                    "owner": str(order.get("owner", "")),
                    "price": price,
                    "size": size,
                    "side": str(order.get("side", "")),
                    "value": value,
                }

                trade_data["maker_orders"].append(maker_order)
                trade_data["total_size"] += size
                total_value += value

            except (ValueError, TypeError) as e:
                logger.warning(f"Error processing maker order: {e}")
                continue

        # Calculate weighted average price
        if trade_data["total_size"] > 0:
            trade_data["weighted_avg_price"] = total_value / trade_data["total_size"]

        # Cache the trade
        cache_key = f"{message.market}:{message.transaction_hash}"
        self._trade_cache[cache_key] = trade_data

        # Log summary
        logger.info(
            f"Trade processed: market={message.market}, "
            f"size={trade_data['total_size']}, "
            f"avg_price={trade_data['weighted_avg_price']}, "
            f"maker_orders={trade_data['trade_count']}"
        )

        return trade_data

    def supports_message_type(self, message_type: str) -> bool:
        """Check if this handler supports the given message type."""
        return message_type == "trade"

    def get_supported_message_types(self) -> list[str]:
        """Get list of supported message types."""
        return ["trade"]

    async def _validate_by_type(
        self, message: WebSocketMessage, message_type: str
    ) -> tuple[bool, list[str], dict[str, Any] | None]:
        """Perform trade-specific validation."""
        issues = []
        sanitized_data = {}

        if not isinstance(message, TradeMessage):
            issues.append("Error: Expected TradeMessage")
            return False, issues, None

        # Validate required fields
        required_fields = [
            "market",
            "transaction_hash",
            "taker_order_id",
            "maker_orders",
        ]
        missing_fields = []

        for field in required_fields:
            if not hasattr(message, field) or getattr(message, field) is None:
                missing_fields.append(field)

        if missing_fields:
            issues.append(f"Error: Missing required fields: {missing_fields}")
            if self.validation_level == ValidationLevel.STRICT:
                return False, issues, None

        # Validate maker orders structure
        maker_orders_valid = True
        if hasattr(message, "maker_orders"):
            if not isinstance(message.maker_orders, list):
                issues.append("Error: maker_orders must be a list")
                maker_orders_valid = False
            elif len(message.maker_orders) == 0:
                issues.append("Warning: Trade has no maker orders")
            else:
                # Validate individual maker orders
                valid_orders = []
                for i, order in enumerate(message.maker_orders):
                    if not isinstance(order, dict):
                        issues.append(f"Warning: Maker order {i} is not a dictionary")
                        continue

                    required_order_fields = [
                        "orderId",
                        "owner",
                        "price",
                        "size",
                        "side",
                    ]
                    missing_order_fields = [
                        f for f in required_order_fields if f not in order
                    ]

                    if missing_order_fields:
                        issues.append(
                            f"Warning: Maker order {i} missing fields: {missing_order_fields}"
                        )
                        if self.validation_level == ValidationLevel.STRICT:
                            continue

                    # Validate price and size
                    try:
                        price = Decimal(str(order.get("price", "0")))
                        size = Decimal(str(order.get("size", "0")))

                        if price <= 0:
                            issues.append(
                                f"Warning: Maker order {i} has invalid price: {price}"
                            )
                        if size <= 0:
                            issues.append(
                                f"Warning: Maker order {i} has invalid size: {size}"
                            )

                        valid_orders.append(order)
                    except (ValueError, TypeError) as e:
                        issues.append(
                            f"Warning: Maker order {i} has invalid numeric values: {e}"
                        )

                sanitized_data["valid_maker_orders"] = valid_orders

        # Validate transaction hash format (basic check)
        if hasattr(message, "transaction_hash") and message.transaction_hash:
            tx_hash = message.transaction_hash
            if not isinstance(tx_hash, str) or len(tx_hash) < 20:
                issues.append("Warning: Transaction hash appears invalid")

        # Validate market address format
        if hasattr(message, "market") and message.market:
            market = message.market
            if not isinstance(market, str) or len(market) < 20:
                issues.append("Warning: Market address appears invalid")

        # Determine if validation passes
        error_count = len([issue for issue in issues if issue.startswith("Error:")])

        if error_count > 0 and self.validation_level == ValidationLevel.STRICT:
            return False, issues, None
        elif error_count > 0 and self.validation_level == ValidationLevel.MODERATE:
            return False, issues, None
        else:
            return True, issues, sanitized_data

    def _validate_message(self, message: WebSocketMessage) -> bool:
        """Legacy validation method for backward compatibility."""
        # This method is now handled by the enhanced validation in the base class
        return super()._validate_message(message)

    def get_cached_trade(
        self, market: str, transaction_hash: str
    ) -> dict[str, Any] | None:
        """
        Get a cached trade by market and transaction hash.

        Args:
            market: Market contract address
            transaction_hash: Transaction hash

        Returns:
            Cached trade data if found
        """
        cache_key = f"{market}:{transaction_hash}"
        return self._trade_cache.get(cache_key)

    def get_trades_for_market(self, market: str) -> dict[str, dict[str, Any]]:
        """
        Get all cached trades for a specific market.

        Args:
            market: Market contract address

        Returns:
            Dictionary of trades keyed by transaction hash
        """
        return {
            key.split(":", 1)[1]: trade
            for key, trade in self._trade_cache.items()
            if key.startswith(f"{market}:")
        }

    def clear_cache(self) -> None:
        """Clear the trade cache."""
        self._trade_cache.clear()

    def get_cache_size(self) -> int:
        """Get the current cache size."""
        return len(self._trade_cache)
