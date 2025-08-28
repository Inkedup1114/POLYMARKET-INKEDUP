"""
Price message handler for processing price updates from Polymarket WebSocket stream.
"""

import logging
from decimal import Decimal
from typing import Any

from ..models.ws_messages import (
    LastTradePriceMessage,
    PriceChangeMessage,
    TickSizeChangeMessage,
    WebSocketMessage,
)
from .base_handler import BaseMessageHandler
from .validation_utils import ValidationLevel

logger = logging.getLogger(__name__)


class PriceHandler(BaseMessageHandler):
    """
    Handler for processing price-related messages from Polymarket WebSocket stream.

    Processes price changes, last trade prices, and tick size updates.
    """

    def __init__(
        self, validation_level: ValidationLevel = ValidationLevel.MODERATE
    ) -> None:
        """Initialize the price handler."""
        super().__init__("PriceHandler", validation_level)
        self._price_cache: dict[str, dict[str, Any]] = {}
        self._tick_sizes: dict[str, Decimal] = {}
        self._price_history: dict[str, list[dict[str, Any]]] = {}

    async def _handle_message(self, message: WebSocketMessage) -> dict[str, Any]:
        """
        Process a price-related message.

        Args:
            message: Price message to process

        Returns:
            Processed price data
        """
        if isinstance(message, PriceChangeMessage):
            return await self._handle_price_change(message)
        elif isinstance(message, LastTradePriceMessage):
            return await self._handle_last_trade_price(message)
        elif isinstance(message, TickSizeChangeMessage):
            return await self._handle_tick_size_change(message)
        else:
            raise ValueError(f"Unsupported message type: {type(message)}")

    async def _handle_price_change(self, message: PriceChangeMessage) -> dict[str, Any]:
        """Handle price change messages."""
        price_data = {
            "type": "price_change",
            "market": message.market,
            "price": message.price,
            "change": message.change,
            "percentage": message.percentage,
            "timestamp": message.timestamp,
        }

        # Update price cache
        if message.market not in self._price_cache:
            self._price_cache[message.market] = {}

        self._price_cache[message.market].update(
            {
                "price": message.price,
                "change": message.change,
                "percentage": message.percentage,
                "last_update": message.timestamp,
            }
        )

        # Add to price history
        if message.market not in self._price_history:
            self._price_history[message.market] = []

        self._price_history[message.market].append(
            {
                "price": message.price,
                "change": message.change,
                "percentage": message.percentage,
                "timestamp": message.timestamp,
            }
        )

        # Keep only last 100 price updates
        if len(self._price_history[message.market]) > 100:
            self._price_history[message.market] = self._price_history[message.market][
                -100:
            ]

        logger.info(
            f"Price change: market={message.market} | "
            f"price={message.price} | "
            f"change={message.change} ({message.percentage}%)"
        )

        return price_data

    async def _handle_last_trade_price(
        self, message: LastTradePriceMessage
    ) -> dict[str, Any]:
        """Handle last trade price messages."""
        price_data = {
            "type": "last_trade_price",
            "market": message.market,
            "price": message.price,
            "timestamp": message.timestamp,
        }

        # Update price cache
        if message.market not in self._price_cache:
            self._price_cache[message.market] = {}

        self._price_cache[message.market].update(
            {"last_trade_price": message.price, "last_trade_time": message.timestamp}
        )

        logger.info(f"Last trade: market={message.market} | " f"price={message.price}")

        return price_data

    async def _handle_tick_size_change(
        self, message: TickSizeChangeMessage
    ) -> dict[str, Any]:
        """Handle tick size change messages."""
        tick_data = {
            "type": "tick_size_change",
            "market": message.market,
            "tick_size": message.tick_size,
            "timestamp": message.timestamp,
        }

        # Update tick size cache
        self._tick_sizes[message.market] = message.tick_size

        logger.info(
            f"Tick size change: market={message.market} | "
            f"tick_size={message.tick_size}"
        )

        return tick_data

    def supports_message_type(self, message_type: str) -> bool:
        """Check if this handler supports the given message type."""
        return message_type in ["price_change", "last_trade_price", "tick_size_change"]

    def get_supported_message_types(self) -> list[str]:
        """Get list of supported message types."""
        return ["price_change", "last_trade_price", "tick_size_change"]

    async def _validate_by_type(
        self, message: WebSocketMessage, message_type: str
    ) -> tuple[bool, list[str], dict[str, Any] | None]:
        """Perform price message type-specific validation."""
        issues = []
        sanitized_data = {}

        if isinstance(message, PriceChangeMessage):
            return await self._validate_price_change_message(message)
        elif isinstance(message, LastTradePriceMessage):
            return await self._validate_last_trade_price_message(message)
        elif isinstance(message, TickSizeChangeMessage):
            return await self._validate_tick_size_change_message(message)
        else:
            issues.append(f"Error: Unsupported message type: {type(message)}")
            return False, issues, None

    async def _validate_price_change_message(
        self, message: PriceChangeMessage
    ) -> tuple[bool, list[str], dict[str, Any] | None]:
        """Validate price change message."""
        issues = []
        sanitized_data = {}

        # Validate required fields
        required_fields = ["market", "price", "change", "percentage"]
        missing_fields = []

        for field in required_fields:
            if not hasattr(message, field) or getattr(message, field) is None:
                missing_fields.append(field)

        if missing_fields:
            issues.append(f"Error: Missing required fields: {missing_fields}")
            if self.validation_level == ValidationLevel.STRICT:
                return False, issues, None

        # Validate price
        if hasattr(message, "price"):
            try:
                price = message.price
                if price <= 0:
                    issues.append(f"Error: Invalid price: {price} (must be positive)")
                elif price > 1:
                    issues.append(f"Warning: Price {price} exceeds maximum of 1.0")

                sanitized_data["validated_price"] = price
            except Exception as e:
                issues.append(f"Error: Invalid price format: {e}")

        # Validate change value
        if hasattr(message, "change"):
            try:
                change = message.change
                sanitized_data["validated_change"] = change
            except Exception as e:
                issues.append(f"Warning: Invalid change format: {e}")

        # Validate percentage
        if hasattr(message, "percentage"):
            try:
                percentage = message.percentage
                if abs(percentage) > 100:
                    issues.append(
                        f"Warning: Percentage change {percentage}% seems extreme"
                    )

                sanitized_data["validated_percentage"] = percentage
            except Exception as e:
                issues.append(f"Warning: Invalid percentage format: {e}")

        # Validate market address
        if hasattr(message, "market") and message.market:
            market = message.market
            if not isinstance(market, str) or len(market) < 20:
                issues.append("Warning: Market address appears invalid")

        # Determine if validation passes
        error_count = len([issue for issue in issues if issue.startswith("Error:")])

        if error_count > 0 and self.validation_level in [
            ValidationLevel.STRICT,
            ValidationLevel.MODERATE,
        ]:
            return False, issues, None
        else:
            return True, issues, sanitized_data

    async def _validate_last_trade_price_message(
        self, message: LastTradePriceMessage
    ) -> tuple[bool, list[str], dict[str, Any] | None]:
        """Validate last trade price message."""
        issues = []
        sanitized_data = {}

        # Validate required fields
        required_fields = ["market", "price"]
        missing_fields = []

        for field in required_fields:
            if not hasattr(message, field) or getattr(message, field) is None:
                missing_fields.append(field)

        if missing_fields:
            issues.append(f"Error: Missing required fields: {missing_fields}")
            if self.validation_level == ValidationLevel.STRICT:
                return False, issues, None

        # Validate price
        if hasattr(message, "price"):
            try:
                price = message.price
                if price <= 0:
                    issues.append(f"Error: Invalid price: {price} (must be positive)")
                elif price > 1:
                    issues.append(f"Warning: Price {price} exceeds maximum of 1.0")

                sanitized_data["validated_price"] = price
            except Exception as e:
                issues.append(f"Error: Invalid price format: {e}")

        # Validate market address
        if hasattr(message, "market") and message.market:
            market = message.market
            if not isinstance(market, str) or len(market) < 20:
                issues.append("Warning: Market address appears invalid")

        # Determine if validation passes
        error_count = len([issue for issue in issues if issue.startswith("Error:")])

        if error_count > 0 and self.validation_level in [
            ValidationLevel.STRICT,
            ValidationLevel.MODERATE,
        ]:
            return False, issues, None
        else:
            return True, issues, sanitized_data

    async def _validate_tick_size_change_message(
        self, message: TickSizeChangeMessage
    ) -> tuple[bool, list[str], dict[str, Any] | None]:
        """Validate tick size change message."""
        issues = []
        sanitized_data = {}

        # Validate required fields
        required_fields = ["market", "tick_size"]
        missing_fields = []

        for field in required_fields:
            if not hasattr(message, field) or getattr(message, field) is None:
                missing_fields.append(field)

        if missing_fields:
            issues.append(f"Error: Missing required fields: {missing_fields}")
            if self.validation_level == ValidationLevel.STRICT:
                return False, issues, None

        # Validate tick size
        if hasattr(message, "tick_size"):
            try:
                tick_size = message.tick_size
                if tick_size <= 0:
                    issues.append(
                        f"Error: Invalid tick size: {tick_size} (must be positive)"
                    )
                elif tick_size > 1:
                    issues.append(
                        f"Warning: Tick size {tick_size} exceeds maximum of 1.0"
                    )

                sanitized_data["validated_tick_size"] = tick_size
            except Exception as e:
                issues.append(f"Error: Invalid tick size format: {e}")

        # Validate market address
        if hasattr(message, "market") and message.market:
            market = message.market
            if not isinstance(market, str) or len(market) < 20:
                issues.append("Warning: Market address appears invalid")

        # Determine if validation passes
        error_count = len([issue for issue in issues if issue.startswith("Error:")])

        if error_count > 0 and self.validation_level in [
            ValidationLevel.STRICT,
            ValidationLevel.MODERATE,
        ]:
            return False, issues, None
        else:
            return True, issues, sanitized_data

    def _validate_message(self, message: WebSocketMessage) -> bool:
        """Validate price message with specific checks for backward compatibility."""
        # First run base validation
        if not super()._validate_message(message):
            return False

        # Check message type and validate accordingly with stricter rules
        if isinstance(message, PriceChangeMessage):
            return self._validate_price_change_message_strict(message)
        elif isinstance(message, LastTradePriceMessage):
            return self._validate_last_trade_price_message_strict(message)
        elif isinstance(message, TickSizeChangeMessage):
            return self._validate_tick_size_change_message_strict(message)
        else:
            logger.error(
                f"PriceHandler received unsupported message type: {type(message)}"
            )
            return False

    def _validate_price_change_message_strict(
        self, message: PriceChangeMessage
    ) -> bool:
        """Strict validation for price change message for backward compatibility."""
        required_fields = ["market", "price", "change", "percentage"]
        for field in required_fields:
            if not hasattr(message, field) or getattr(message, field) is None:
                logger.error(f"PriceChangeMessage missing required field: {field}")
                return False

        # Validate price is positive
        if message.price <= 0:
            logger.error(f"PriceChangeMessage has invalid price: {message.price}")
            return False

        return True

    def _validate_last_trade_price_message_strict(
        self, message: LastTradePriceMessage
    ) -> bool:
        """Strict validation for last trade price message for backward compatibility."""
        required_fields = ["market", "price"]
        for field in required_fields:
            if not hasattr(message, field) or getattr(message, field) is None:
                logger.error(f"LastTradePriceMessage missing required field: {field}")
                return False

        # Validate price is positive
        if message.price <= 0:
            logger.error(f"LastTradePriceMessage has invalid price: {message.price}")
            return False

        return True

    def _validate_tick_size_change_message_strict(
        self, message: TickSizeChangeMessage
    ) -> bool:
        """Strict validation for tick size change message for backward compatibility."""
        required_fields = ["market", "tick_size"]
        for field in required_fields:
            if not hasattr(message, field) or getattr(message, field) is None:
                logger.error(f"TickSizeChangeMessage missing required field: {field}")
                return False

        # Validate tick size is positive
        if message.tick_size <= 0:
            logger.error(
                f"TickSizeChangeMessage has invalid tick_size: {message.tick_size}"
            )
            return False

        return True

    def get_current_price(self, market: str) -> dict[str, Any] | None:
        """
        Get current price data for a market.

        Args:
            market: Market contract address

        Returns:
            Current price data if available
        """
        return self._price_cache.get(market)

    def get_tick_size(self, market: str) -> Decimal | None:
        """
        Get current tick size for a market.

        Args:
            market: Market contract address

        Returns:
            Tick size if available
        """
        return self._tick_sizes.get(market)

    def get_price_history(self, market: str, limit: int = 50) -> list[dict[str, Any]]:
        """
        Get price history for a market.

        Args:
            market: Market contract address
            limit: Maximum number of records to return

        Returns:
            Price history
        """
        history = self._price_history.get(market, [])
        return history[-limit:] if history else []

    def get_all_markets(self) -> list[str]:
        """Get list of all markets with cached price data."""
        return list(self._price_cache.keys())

    def get_price_summary(self) -> dict[str, dict[str, Any]]:
        """
        Get price summary for all markets.

        Returns:
            Dictionary of price data keyed by market
        """
        return self._price_cache.copy()

    def clear_cache(self) -> None:
        """Clear all cached price data."""
        self._price_cache.clear()
        self._tick_sizes.clear()
        self._price_history.clear()

    def get_cache_size(self) -> int:
        """Get the current cache size."""
        return len(self._price_cache)
