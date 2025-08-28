"""
WebSocket message models for Polymarket WSS stream.

This module contains Pydantic models for parsing and validating
Polymarket WebSocket messages according to the official API specification.
"""

import json
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, validator
from pydantic.json import pydantic_encoder


class MessageType(str, Enum):
    """Enumeration of Polymarket WebSocket message types."""

    TRADE = "trade"
    ORDER = "order"
    BOOK = "book"
    PRICE_CHANGE = "price_change"
    TICK_SIZE_CHANGE = "tick_size_change"
    LAST_TRADE_PRICE = "last_trade_price"


class OrderSide(str, Enum):
    """Order side enumeration."""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """Order status enumeration."""

    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class OrderType(str, Enum):
    """Order type enumeration."""

    LIMIT = "limit"
    MARKET = "market"


class TradeMessage(BaseModel):
    """
    Trade event message from Polymarket WSS stream.

    Represents a trade execution event with maker order details.

    Example:
        {
            "type": "trade",
            "market": "0x123...",
            "transactionHash": "0xabc...",
            "takerOrderId": "order123",
            "makerOrders": [
                {
                    "orderId": "maker1",
                    "owner": "0xuser1",
                    "price": "0.55",
                    "size": "100.0",
                    "side": "buy"
                }
            ],
            "timestamp": "2024-01-01T12:00:00Z"
        }
    """

    type: Literal["trade"] = "trade"
    market: str = Field(..., description="Market contract address")
    transaction_hash: str = Field(
        ..., alias="transactionHash", description="Transaction hash"
    )
    taker_order_id: str = Field(..., alias="takerOrderId", description="Taker order ID")
    maker_orders: list[dict[str, Any]] = Field(
        ..., alias="makerOrders", description="Array of maker orders"
    )
    timestamp: datetime = Field(..., description="Trade timestamp")

    @validator("maker_orders")
    @classmethod
    def validate_maker_orders(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate maker orders structure."""
        if not isinstance(v, list):
            raise ValueError("maker_orders must be a list")

        for order in v:
            if not isinstance(order, dict):
                raise ValueError("Each maker order must be a dictionary")
            required_fields = {"orderId", "owner", "price", "size", "side"}
            if not all(field in order for field in required_fields):
                raise ValueError(
                    f"Maker order missing required fields: {required_fields}"
                )

        return v

    class Config:
        allow_population_by_field_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), Decimal: lambda v: str(v)}


class OrderMessage(BaseModel):
    """
    Order event message from Polymarket WSS stream.

    Represents order placement, update, or cancellation events.

    Example:
        {
            "type": "order",
            "orderId": "order123",
            "market": "0x123...",
            "owner": "0xuser1",
            "price": "0.55",
            "size": "100.0",
            "side": "buy",
            "status": "open",
            "orderType": "limit",
            "timestamp": "2024-01-01T12:00:00Z"
        }
    """

    type: Literal["order"] = "order"
    order_id: str = Field(..., alias="orderId", description="Unique order identifier")
    market: str = Field(..., description="Market contract address")
    owner: str = Field(..., description="Order owner address")
    price: Decimal = Field(..., description="Order price", ge=0, le=1)
    size: Decimal = Field(..., description="Order size", gt=0)
    side: OrderSide = Field(..., description="Order side (buy/sell)")
    status: OrderStatus = Field(..., description="Current order status")
    order_type: OrderType = Field(..., alias="orderType", description="Order type")
    timestamp: datetime = Field(..., description="Order timestamp")

    @validator("price", "size", pre=True)
    @classmethod
    def parse_decimal(cls, v: str | Decimal) -> Decimal:
        """Parse string to Decimal."""
        if isinstance(v, str):
            return Decimal(v)
        return v

    class Config:
        allow_population_by_field_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), Decimal: lambda v: str(v)}


class BookLevel(BaseModel):
    """Individual book level (bid/ask)."""

    price: Decimal = Field(..., description="Price level")
    size: Decimal = Field(..., description="Size at price level")

    @validator("price", "size", pre=True)
    @classmethod
    def parse_decimal(cls, v: str | Decimal) -> Decimal:
        """Parse string to Decimal."""
        if isinstance(v, str):
            return Decimal(v)
        return v


class BookMessage(BaseModel):
    """
    Book update message from Polymarket WSS stream.

    Represents order book updates with bids and asks arrays.

    Example:
        {
            "type": "book",
            "market": "0x123...",
            "bids": [
                {"price": "0.54", "size": "100.0"},
                {"price": "0.53", "size": "200.0"}
            ],
            "asks": [
                {"price": "0.56", "size": "150.0"},
                {"price": "0.57", "size": "75.0"}
            ],
            "timestamp": "2024-01-01T12:00:00Z"
        }
    """

    type: Literal["book"] = "book"
    market: str = Field(..., description="Market contract address")
    bids: list[BookLevel] = Field(..., description="Array of bid levels")
    asks: list[BookLevel] = Field(..., description="Array of ask levels")
    timestamp: datetime = Field(..., description="Book timestamp")

    @validator("bids", "asks")
    @classmethod
    def validate_book_levels(cls, v: list[BookLevel]) -> list[BookLevel]:
        """Validate book levels are sorted correctly."""
        if not v:
            return v

        prices = [level.price for level in v]
        if len(prices) != len(set(prices)):
            raise ValueError("Duplicate price levels found")

        return v

    def get_best_bid(self) -> Decimal | None:
        """Get the best bid price."""
        return max(level.price for level in self.bids) if self.bids else None

    def get_best_ask(self) -> Decimal | None:
        """Get the best ask price."""
        return min(level.price for level in self.asks) if self.asks else None

    def get_spread(self) -> Decimal | None:
        """Get the bid-ask spread."""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid is not None and best_ask is not None:
            return best_ask - best_bid
        return None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat(), Decimal: lambda v: str(v)}


class PriceChangeMessage(BaseModel):
    """
    Price level change message from Polymarket WSS stream.

    Represents changes in price levels for a market.

    Example:
        {
            "type": "price_change",
            "market": "0x123...",
            "price": "0.55",
            "change": "0.02",
            "percentage": "3.77",
            "timestamp": "2024-01-01T12:00:00Z"
        }
    """

    type: Literal["price_change"] = "price_change"
    market: str = Field(..., description="Market contract address")
    price: Decimal = Field(..., description="Current price", ge=0, le=1)
    change: Decimal = Field(..., description="Price change amount")
    percentage: Decimal = Field(..., description="Price change percentage")
    timestamp: datetime = Field(..., description="Change timestamp")

    @validator("price", "change", "percentage", pre=True)
    @classmethod
    def parse_decimal(cls, v: str | Decimal) -> Decimal:
        """Parse string to Decimal."""
        if isinstance(v, str):
            return Decimal(v)
        return v

    class Config:
        allow_population_by_field_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), Decimal: lambda v: str(v)}


class TickSizeChangeMessage(BaseModel):
    """
    Tick size change message from Polymarket WSS stream.

    Represents tick size adjustments for a market.

    Example:
        {
            "type": "tick_size_change",
            "market": "0x123...",
            "tickSize": "0.01",
            "timestamp": "2024-01-01T12:00:00Z"
        }
    """

    type: Literal["tick_size_change"] = "tick_size_change"
    market: str = Field(..., description="Market contract address")
    tick_size: Decimal = Field(..., alias="tickSize", description="New tick size")
    timestamp: datetime = Field(..., description="Change timestamp")

    @validator("tick_size", pre=True)
    @classmethod
    def parse_decimal(cls, v: str | Decimal) -> Decimal:
        """Parse string to Decimal."""
        if isinstance(v, str):
            return Decimal(v)
        return v

    class Config:
        allow_population_by_field_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), Decimal: lambda v: str(v)}


class LastTradePriceMessage(BaseModel):
    """
    Last trade price message from Polymarket WSS stream.

    Represents the most recent trade price for a market.

    Example:
        {
            "type": "last_trade_price",
            "market": "0x123...",
            "price": "0.55",
            "timestamp": "2024-01-01T12:00:00Z"
        }
    """

    type: Literal["last_trade_price"] = "last_trade_price"
    market: str = Field(..., description="Market contract address")
    price: Decimal = Field(..., description="Last trade price", ge=0, le=1)
    timestamp: datetime = Field(..., description="Trade timestamp")

    @validator("price", pre=True)
    @classmethod
    def parse_decimal(cls, v: str | Decimal) -> Decimal:
        """Parse string to Decimal."""
        if isinstance(v, str):
            return Decimal(v)
        return v

    class Config:
        allow_population_by_field_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), Decimal: lambda v: str(v)}


# Union type for all WebSocket messages
WebSocketMessage = (
    TradeMessage
    | OrderMessage
    | BookMessage
    | PriceChangeMessage
    | TickSizeChangeMessage
    | LastTradePriceMessage
)


def parse_websocket_message(data: dict[str, Any]) -> WebSocketMessage:
    """
    Parse a WebSocket message into the appropriate model.

    Args:
        data: Raw message data as dictionary

    Returns:
        Parsed WebSocket message model

    Raises:
        ValueError: If message type is unknown or data is invalid
    """
    if not isinstance(data, dict):
        raise ValueError("Message data must be a dictionary")

    message_type = data.get("type")
    if not message_type:
        raise ValueError("Message must have a 'type' field")

    message_map = {
        "trade": TradeMessage,
        "order": OrderMessage,
        "book": BookMessage,
        "price_change": PriceChangeMessage,
        "tick_size_change": TickSizeChangeMessage,
        "last_trade_price": LastTradePriceMessage,
    }

    model_class = message_map.get(message_type)
    if not model_class:
        raise ValueError(f"Unknown message type: {message_type}")

    try:
        return cast(WebSocketMessage, model_class(**data))  # type: ignore
    except Exception as e:
        raise ValueError(f"Failed to parse {message_type} message: {str(e)}") from e


def serialize_message(message: WebSocketMessage) -> str:
    """
    Serialize a WebSocket message to JSON string.

    Args:
        message: WebSocket message model

    Returns:
        JSON string representation
    """
    return json.dumps(message.dict(by_alias=True), default=pydantic_encoder)
