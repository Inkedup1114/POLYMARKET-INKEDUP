"""
JSON Schema validation for Polymarket WebSocket messages.

This module provides JSON schema definitions and validation utilities
for all Polymarket WebSocket message types according to the official API specification.
"""

from decimal import Decimal
from typing import Any

from jsonschema import Draft7Validator, ValidationError

# Base schema for all messages
BASE_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": [
                "trade",
                "order",
                "book",
                "price_change",
                "tick_size_change",
                "last_trade_price",
            ],
        }
    },
    "required": ["type"],
}


# Trade message schema
TRADE_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "const": "trade"},
        "market": {"type": "string", "pattern": "^0x[a-fA-F0-9]{40}$"},
        "transactionHash": {"type": "string", "pattern": "^0x[a-fA-F0-9]{64}$"},
        "takerOrderId": {"type": "string"},
        "makerOrders": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "orderId": {"type": "string"},
                    "owner": {"type": "string", "pattern": "^0x[a-fA-F0-9]{40}$"},
                    "price": {"type": "string", "pattern": "^\\d+(?:\\.\\d+)?$"},
                    "size": {"type": "string", "pattern": "^\\d+(?:\\.\\d+)?$"},
                    "side": {"type": "string", "enum": ["buy", "sell"]},
                },
                "required": ["orderId", "owner", "price", "size", "side"],
            },
            "minItems": 1,
        },
        "timestamp": {"type": "string", "format": "date-time"},
    },
    "required": [
        "type",
        "market",
        "transactionHash",
        "takerOrderId",
        "makerOrders",
        "timestamp",
    ],
    "additionalProperties": False,
}


# Order message schema
ORDER_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "const": "order"},
        "orderId": {"type": "string"},
        "market": {"type": "string", "pattern": "^0x[a-fA-F0-9]{40}$"},
        "owner": {"type": "string", "pattern": "^0x[a-fA-F0-9]{40}$"},
        "price": {"type": "string", "pattern": "^(?:0(?:\\.\\d+)?|1(?:\\.0+)?)$"},
        "size": {"type": "string", "pattern": "^\\d+(?:\\.\\d+)?$"},
        "side": {"type": "string", "enum": ["buy", "sell"]},
        "status": {
            "type": "string",
            "enum": ["pending", "open", "filled", "cancelled", "failed"],
        },
        "orderType": {"type": "string", "enum": ["limit", "market"]},
        "timestamp": {"type": "string", "format": "date-time"},
    },
    "required": [
        "type",
        "orderId",
        "market",
        "owner",
        "price",
        "size",
        "side",
        "status",
        "orderType",
        "timestamp",
    ],
    "additionalProperties": False,
}


# Book level schema
BOOK_LEVEL_SCHEMA = {
    "type": "object",
    "properties": {
        "price": {"type": "string", "pattern": "^(?:0(?:\\.\\d+)?|1(?:\\.0+)?)$"},
        "size": {"type": "string", "pattern": "^\\d+(?:\\.\\d+)?$"},
    },
    "required": ["price", "size"],
    "additionalProperties": False,
}


# Book message schema
BOOK_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "const": "book"},
        "market": {"type": "string", "pattern": "^0x[a-fA-F0-9]{40}$"},
        "bids": {"type": "array", "items": BOOK_LEVEL_SCHEMA, "uniqueItems": True},
        "asks": {"type": "array", "items": BOOK_LEVEL_SCHEMA, "uniqueItems": True},
        "timestamp": {"type": "string", "format": "date-time"},
    },
    "required": ["type", "market", "bids", "asks", "timestamp"],
    "additionalProperties": False,
}


# Price change message schema
PRICE_CHANGE_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "const": "price_change"},
        "market": {"type": "string", "pattern": "^0x[a-fA-F0-9]{40}$"},
        "price": {"type": "string", "pattern": "^(?:0(?:\\.\\d+)?|1(?:\\.0+)?)$"},
        "change": {"type": "string", "pattern": "^-?\\d+(?:\\.\\d+)?$"},
        "percentage": {"type": "string", "pattern": "^-?\\d+(?:\\.\\d+)?$"},
        "timestamp": {"type": "string", "format": "date-time"},
    },
    "required": ["type", "market", "price", "change", "percentage", "timestamp"],
    "additionalProperties": False,
}


# Tick size change message schema
TICK_SIZE_CHANGE_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "const": "tick_size_change"},
        "market": {"type": "string", "pattern": "^0x[a-fA-F0-9]{40}$"},
        "tickSize": {"type": "string", "pattern": "^\\d+(?:\\.\\d+)?$"},
        "timestamp": {"type": "string", "format": "date-time"},
    },
    "required": ["type", "market", "tickSize", "timestamp"],
    "additionalProperties": False,
}


# Last trade price message schema
LAST_TRADE_PRICE_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "const": "last_trade_price"},
        "market": {"type": "string", "pattern": "^0x[a-fA-F0-9]{40}$"},
        "price": {"type": "string", "pattern": "^(?:0(?:\\.\\d+)?|1(?:\\.0+)?)$"},
        "timestamp": {"type": "string", "format": "date-time"},
    },
    "required": ["type", "market", "price", "timestamp"],
    "additionalProperties": False,
}


# Schema mapping
SCHEMA_MAP = {
    "trade": TRADE_MESSAGE_SCHEMA,
    "order": ORDER_MESSAGE_SCHEMA,
    "book": BOOK_MESSAGE_SCHEMA,
    "price_change": PRICE_CHANGE_MESSAGE_SCHEMA,
    "tick_size_change": TICK_SIZE_CHANGE_MESSAGE_SCHEMA,
    "last_trade_price": LAST_TRADE_PRICE_MESSAGE_SCHEMA,
}


class MessageValidator:
    """
    Validator for Polymarket WebSocket messages.

    Provides methods for validating message structure and data integrity
    according to the official Polymarket API specification.
    """

    def __init__(self) -> None:
        """Initialize the validator with compiled schemas."""
        self.validators = {
            message_type: Draft7Validator(schema)
            for message_type, schema in SCHEMA_MAP.items()
        }

    def validate_message(self, message: dict[str, Any], message_type: str) -> bool:
        """
        Validate a message against its schema.

        Args:
            message: The message to validate
            message_type: The type of message (trade, order, book, etc.)

        Returns:
            True if valid, False otherwise

        Raises:
            ValidationError: If the message is invalid
        """
        if message_type not in self.validators:
            raise ValueError(f"Unknown message type: {message_type}")

        validator = self.validators[message_type]
        validator.validate(message)
        return True

    def validate_message_silent(
        self, message: dict[str, Any], message_type: str
    ) -> tuple[bool, str | None]:
        """
        Validate a message silently without raising exceptions.

        Args:
            message: The message to validate
            message_type: The type of message

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            self.validate_message(message, message_type)
            return True, None
        except ValidationError as e:
            return False, str(e)

    def get_validation_errors(
        self, message: dict[str, Any], message_type: str
    ) -> list[str]:
        """
        Get all validation errors for a message.

        Args:
            message: The message to validate
            message_type: The type of message

        Returns:
            List of validation error messages
        """
        if message_type not in self.validators:
            return [f"Unknown message type: {message_type}"]

        validator = self.validators[message_type]
        errors = list(validator.iter_errors(message))
        return [str(error) for error in errors]

    def validate_field_types(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        Validate and convert field types for a message.

        Args:
            message: The message to validate

        Returns:
            Message with converted field types
        """
        converted = message.copy()

        # Handle decimal conversion for price/size fields
        decimal_fields = ["price", "size", "change", "percentage", "tickSize"]

        for field in decimal_fields:
            if field in converted and isinstance(converted[field], str):
                try:
                    converted[field] = Decimal(converted[field])
                except (ValueError, ArithmeticError) as e:
                    raise ValueError(
                        f"Invalid decimal value for {field}: {converted[field]}"
                    ) from e

        # Handle timestamp conversion
        if "timestamp" in converted and isinstance(converted["timestamp"], str):
            from datetime import datetime

            try:
                converted["timestamp"] = datetime.fromisoformat(
                    converted["timestamp"].replace("Z", "+00:00")
                )
            except ValueError as e:
                raise ValueError(
                    f"Invalid timestamp format: {converted['timestamp']}"
                ) from e

        return converted

    def is_valid_market_address(self, address: str) -> bool:
        """
        Validate if a string is a valid Ethereum market address.

        Args:
            address: The address to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(address, str):
            return False

        # Check if it's a valid Ethereum address format
        return bool(
            address.startswith("0x")
            and len(address) == 42
            and all(c in "0123456789abcdefABCDEF" for c in address[2:])
        )

    def is_valid_price(self, price: str) -> bool:
        """
        Validate if a string represents a valid price (0-1).

        Args:
            price: The price string to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            price_decimal = Decimal(price)
            return 0 <= price_decimal <= 1
        except (ValueError, ArithmeticError):
            return False

    def is_valid_size(self, size: str) -> bool:
        """
        Validate if a string represents a valid size (> 0).

        Args:
            size: The size string to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            size_decimal = Decimal(size)
            return size_decimal > 0
        except (ValueError, ArithmeticError):
            return False


# Global validator instance
message_validator = MessageValidator()


def validate_trade_message(message: dict[str, Any]) -> bool:
    """
    Validate a trade message.

    Args:
        message: The trade message to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If the message is invalid
    """
    return message_validator.validate_message(message, "trade")


def validate_order_message(message: dict[str, Any]) -> bool:
    """
    Validate an order message.

    Args:
        message: The order message to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If the message is invalid
    """
    return message_validator.validate_message(message, "order")


def validate_book_message(message: dict[str, Any]) -> bool:
    """
    Validate a book message.

    Args:
        message: The book message to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If the message is invalid
    """
    return message_validator.validate_message(message, "book")


def validate_price_change_message(message: dict[str, Any]) -> bool:
    """
    Validate a price change message.

    Args:
        message: The price change message to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If the message is invalid
    """
    return message_validator.validate_message(message, "price_change")


def validate_tick_size_change_message(message: dict[str, Any]) -> bool:
    """
    Validate a tick size change message.

    Args:
        message: The tick size change message to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If the message is invalid
    """
    return message_validator.validate_message(message, "tick_size_change")


def validate_last_trade_price_message(message: dict[str, Any]) -> bool:
    """
    Validate a last trade price message.

    Args:
        message: The last trade price message to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If the message is invalid
    """
    return message_validator.validate_message(message, "last_trade_price")


def get_schema(message_type: str) -> dict[str, Any]:
    """
    Get the JSON schema for a specific message type.

    Args:
        message_type: The type of message

    Returns:
        The JSON schema as a dictionary

    Raises:
        ValueError: If message type is unknown
    """
    if message_type not in SCHEMA_MAP:
        raise ValueError(f"Unknown message type: {message_type}")

    return SCHEMA_MAP[message_type]


def get_all_schemas() -> dict[str, dict[str, Any]]:
    """
    Get all JSON schemas.

    Returns:
        Dictionary mapping message types to their schemas
    """
    return SCHEMA_MAP.copy()
