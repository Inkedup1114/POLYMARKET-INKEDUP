"""
Book message handler for processing order book updates from Polymarket WebSocket stream.
"""

import logging
from decimal import Decimal
from typing import Any

from ..models.ws_messages import BookMessage, WebSocketMessage
from .base_handler import BaseMessageHandler
from .validation_utils import ValidationLevel

logger = logging.getLogger(__name__)


class BookHandler(BaseMessageHandler):
    """
    Handler for processing order book messages from Polymarket WebSocket stream.

    Processes order book updates and maintains current market depth.
    """

    def __init__(
        self, validation_level: ValidationLevel = ValidationLevel.MODERATE
    ) -> None:
        """Initialize the book handler."""
        super().__init__("BookHandler", validation_level)
        self._order_books: dict[str, dict[str, Any]] = {}
        self._market_depth_cache: dict[str, dict[str, Decimal]] = {}

    async def _handle_message(self, message: WebSocketMessage) -> dict[str, Any]:
        """
        Process a book update message.

        Args:
            message: Book message to process

        Returns:
            Processed book data
        """
        if not isinstance(message, BookMessage):
            raise ValueError(f"Expected BookMessage, got {type(message)}")

        # Process bids
        bids = []
        total_bid_volume = Decimal("0")
        for bid in message.bids:
            bids.append(
                {"price": bid.price, "size": bid.size, "value": bid.price * bid.size}
            )
            total_bid_volume += bid.size

        # Process asks
        asks = []
        total_ask_volume = Decimal("0")
        for ask in message.asks:
            asks.append(
                {"price": ask.price, "size": ask.size, "value": ask.price * ask.size}
            )
            total_ask_volume += ask.size

        book_data = {
            "market": message.market,
            "timestamp": message.timestamp,
            "bids": bids,
            "asks": asks,
            "best_bid": message.get_best_bid(),
            "best_ask": message.get_best_ask(),
            "spread": message.get_spread(),
            "total_bid_volume": total_bid_volume,
            "total_ask_volume": total_ask_volume,
            "mid_price": self._calculate_mid_price(message),
            "bid_ask_ratio": self._calculate_bid_ask_ratio(
                total_bid_volume, total_ask_volume
            ),
        }

        # Store the order book
        self._order_books[message.market] = book_data

        # Cache market depth metrics
        self._market_depth_cache[message.market] = {
            "best_bid": book_data["best_bid"] or Decimal("0"),
            "best_ask": book_data["best_ask"] or Decimal("0"),
            "spread": book_data["spread"] or Decimal("0"),
            "mid_price": book_data["mid_price"] or Decimal("0"),
        }

        # Log summary
        logger.info(
            f"Book update: market={message.market} | "
            f"best_bid={book_data['best_bid']} | "
            f"best_ask={book_data['best_ask']} | "
            f"spread={book_data['spread']} | "
            f"bid_vol={total_bid_volume} | "
            f"ask_vol={total_ask_volume}"
        )

        return book_data

    def supports_message_type(self, message_type: str) -> bool:
        """Check if this handler supports the given message type."""
        return message_type == "book"

    def get_supported_message_types(self) -> list[str]:
        """Get list of supported message types."""
        return ["book"]

    async def _validate_by_type(
        self, message: WebSocketMessage, message_type: str
    ) -> tuple[bool, list[str], dict[str, Any] | None]:
        """Perform book-specific validation."""
        issues = []
        sanitized_data = {}

        if not isinstance(message, BookMessage):
            issues.append("Error: Expected BookMessage")
            return False, issues, None

        # Validate market field
        if not hasattr(message, "market") or not message.market:
            issues.append("Error: Missing market field")
            if self.validation_level == ValidationLevel.STRICT:
                return False, issues, None
        elif hasattr(message, "market"):
            market = message.market
            if not isinstance(market, str) or len(market) < 20:
                issues.append("Warning: Market address appears invalid")

        # Validate bids and asks structure
        has_bids = hasattr(message, "bids") and message.bids
        has_asks = hasattr(message, "asks") and message.asks

        if not has_bids and not has_asks:
            issues.append("Warning: BookMessage has no bids or asks")

        # Validate bid levels
        valid_bids = []
        if has_bids:
            for i, bid in enumerate(message.bids):
                try:
                    if not hasattr(bid, "price") or not hasattr(bid, "size"):
                        issues.append(f"Warning: Bid level {i} missing price or size")
                        continue

                    price = bid.price
                    size = bid.size

                    if price <= 0:
                        issues.append(
                            f"Warning: Bid level {i} has invalid price: {price}"
                        )
                    elif price > 1:
                        issues.append(
                            f"Warning: Bid level {i} price {price} exceeds maximum of 1.0"
                        )

                    if size <= 0:
                        issues.append(
                            f"Warning: Bid level {i} has invalid size: {size}"
                        )

                    valid_bids.append({"price": price, "size": size})
                except Exception as e:
                    issues.append(f"Warning: Error validating bid level {i}: {e}")

        sanitized_data["valid_bids"] = valid_bids

        # Validate ask levels
        valid_asks = []
        if has_asks:
            for i, ask in enumerate(message.asks):
                try:
                    if not hasattr(ask, "price") or not hasattr(ask, "size"):
                        issues.append(f"Warning: Ask level {i} missing price or size")
                        continue

                    price = ask.price
                    size = ask.size

                    if price <= 0:
                        issues.append(
                            f"Warning: Ask level {i} has invalid price: {price}"
                        )
                    elif price > 1:
                        issues.append(
                            f"Warning: Ask level {i} price {price} exceeds maximum of 1.0"
                        )

                    if size <= 0:
                        issues.append(
                            f"Warning: Ask level {i} has invalid size: {size}"
                        )

                    valid_asks.append({"price": price, "size": size})
                except Exception as e:
                    issues.append(f"Warning: Error validating ask level {i}: {e}")

        sanitized_data["valid_asks"] = valid_asks

        # Validate spread consistency
        if valid_bids and valid_asks:
            try:
                best_bid = max(level["price"] for level in valid_bids)
                best_ask = min(level["price"] for level in valid_asks)

                if best_bid >= best_ask:
                    issues.append(
                        f"Warning: Crossed spread detected - best_bid ({best_bid}) >= best_ask ({best_ask})"
                    )
            except Exception as e:
                issues.append(f"Warning: Error validating spread: {e}")

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
        """Validate book message with specific checks for backward compatibility."""
        # First run base validation
        if not super()._validate_message(message):
            return False

        # Check if it's a BookMessage
        if not isinstance(message, BookMessage):
            logger.error(f"Expected BookMessage, got {type(message)}")
            return False

        # Validate market is specified
        if not hasattr(message, "market") or not message.market:
            logger.error("BookMessage missing market field")
            return False

        # Validate we have either bids or asks (or both)
        has_bids = hasattr(message, "bids") and message.bids
        has_asks = hasattr(message, "asks") and message.asks

        if not has_bids and not has_asks:
            logger.warning("BookMessage has no bids or asks")
            # Don't fail on this - empty book might be valid state

        return True

    def _calculate_mid_price(self, message: BookMessage) -> Decimal | None:
        """Calculate the mid price between best bid and ask."""
        best_bid = message.get_best_bid()
        best_ask = message.get_best_ask()

        if best_bid is not None and best_ask is not None:
            return Decimal(str((best_bid + best_ask) / 2))
        return None

    def _calculate_bid_ask_ratio(
        self, bid_volume: Decimal, ask_volume: Decimal
    ) -> Decimal | None:
        """Calculate the bid/ask volume ratio."""
        if ask_volume > 0:
            return bid_volume / ask_volume
        return None

    def get_order_book(self, market: str) -> dict[str, Any] | None:
        """
        Get the current order book for a market.

        Args:
            market: Market contract address

        Returns:
            Order book data if available
        """
        return self._order_books.get(market)

    def get_market_depth(self, market: str) -> dict[str, Decimal] | None:
        """
        Get market depth metrics for a market.

        Args:
            market: Market contract address

        Returns:
            Market depth metrics
        """
        return self._market_depth_cache.get(market)

    def get_top_levels(
        self, market: str, levels: int = 5
    ) -> dict[str, list[dict[str, Decimal]]] | None:
        """
        Get top N bid and ask levels for a market.

        Args:
            market: Market contract address
            levels: Number of levels to return

        Returns:
            Top bid and ask levels
        """
        book = self._order_books.get(market)
        if not book:
            return None

        return {"bids": book["bids"][:levels], "asks": book["asks"][:levels]}

    def get_all_markets(self) -> list[str]:
        """Get list of all markets with cached order books."""
        return list(self._order_books.keys())

    def clear_cache(self) -> None:
        """Clear all cached order books."""
        self._order_books.clear()
        self._market_depth_cache.clear()

    def get_cache_size(self) -> int:
        """Get the current cache size."""
        return len(self._order_books)
