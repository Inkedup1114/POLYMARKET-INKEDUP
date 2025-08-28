"""
Comprehensive validation utilities for message handlers.

Provides robust validation, sanitization, and data quality checks
for WebSocket message processing with fallback mechanisms.
"""

import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """Validation strictness levels."""

    STRICT = "strict"  # Fail on any validation error
    MODERATE = "moderate"  # Allow minor issues with warnings
    LENIENT = "lenient"  # Best effort with fallbacks


class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(
        self,
        message: str,
        field: str = None,
        value: Any = None,
        recoverable: bool = True,
    ):
        super().__init__(message)
        self.field = field
        self.value = value
        self.recoverable = recoverable


class DataSanitizer:
    """Handles data sanitization and normalization."""

    @staticmethod
    def sanitize_string(
        value: Any, max_length: int = 1000, allow_empty: bool = False
    ) -> str:
        """Sanitize string input with length limits and character filtering."""
        if value is None:
            if allow_empty:
                return ""
            raise ValidationError("String value cannot be None", recoverable=False)

        # Convert to string
        str_value = str(value).strip()

        # Check empty
        if not str_value and not allow_empty:
            raise ValidationError("String value cannot be empty", recoverable=False)

        # Length check
        if len(str_value) > max_length:
            logger.warning(
                f"String truncated from {len(str_value)} to {max_length} characters"
            )
            str_value = str_value[:max_length]

        # Remove potentially dangerous characters (basic sanitization)
        str_value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str_value)

        return str_value

    @staticmethod
    def sanitize_decimal(
        value: Any,
        min_value: Decimal | None = None,
        max_value: Decimal | None = None,
        precision: int = 18,
    ) -> Decimal:
        """Sanitize and validate decimal values."""
        if value is None:
            raise ValidationError("Decimal value cannot be None", recoverable=False)

        try:
            if isinstance(value, str):
                # Clean string representation
                cleaned = re.sub(r"[^\d.-]", "", value)
                if not cleaned:
                    raise ValidationError(
                        f"Invalid decimal string: {value}", recoverable=False
                    )
                decimal_value = Decimal(cleaned)
            else:
                decimal_value = Decimal(str(value))

            # Precision check
            if decimal_value.as_tuple().exponent < -precision:
                # Round to specified precision
                decimal_value = decimal_value.quantize(Decimal("0." + "0" * precision))
                logger.debug(
                    f"Decimal rounded to {precision} precision: {decimal_value}"
                )

            # Range checks
            if min_value is not None and decimal_value < min_value:
                raise ValidationError(
                    f"Decimal value {decimal_value} below minimum {min_value}",
                    value=decimal_value,
                )
            if max_value is not None and decimal_value > max_value:
                raise ValidationError(
                    f"Decimal value {decimal_value} above maximum {max_value}",
                    value=decimal_value,
                )

            return decimal_value

        except (InvalidOperation, ValueError, TypeError) as e:
            raise ValidationError(
                f"Invalid decimal value: {value} ({e})", value=value, recoverable=False
            )

    @staticmethod
    def sanitize_timestamp(value: Any, max_age_hours: int = 24) -> datetime:
        """Sanitize and validate timestamp values."""
        if value is None:
            raise ValidationError("Timestamp cannot be None", recoverable=False)

        try:
            if isinstance(value, datetime):
                timestamp = value
            elif isinstance(value, str):
                # Try common timestamp formats
                formats = [
                    "%Y-%m-%dT%H:%M:%S.%fZ",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S",
                ]

                timestamp = None
                for fmt in formats:
                    try:
                        timestamp = datetime.strptime(value, fmt)
                        break
                    except ValueError:
                        continue

                if timestamp is None:
                    # Try fromisoformat as last resort
                    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))

            elif isinstance(value, (int, float)):
                timestamp = datetime.fromtimestamp(value)
            else:
                raise ValidationError(
                    f"Unsupported timestamp type: {type(value)}",
                    value=value,
                    recoverable=False,
                )

            # Age validation
            if max_age_hours > 0:
                age = datetime.utcnow() - timestamp
                if age > timedelta(hours=max_age_hours):
                    raise ValidationError(
                        f"Timestamp too old: {age.total_seconds()/3600:.1f} hours",
                        value=timestamp,
                    )

            return timestamp

        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            raise ValidationError(
                f"Invalid timestamp: {value} ({e})", value=value, recoverable=False
            )

    @staticmethod
    def sanitize_address(value: Any) -> str:
        """Sanitize Ethereum addresses."""
        if value is None:
            raise ValidationError("Address cannot be None", recoverable=False)

        address = str(value).strip()

        # Basic Ethereum address format check
        if not re.match(r"^0x[a-fA-F0-9]{40}$", address):
            raise ValidationError(
                f"Invalid Ethereum address format: {address}",
                value=address,
                recoverable=False,
            )

        return address.lower()  # Normalize to lowercase


class MessageValidator:
    """Comprehensive message validation with configurable strictness."""

    def __init__(self, validation_level: ValidationLevel = ValidationLevel.MODERATE):
        self.validation_level = validation_level
        self.sanitizer = DataSanitizer()
        self.validation_stats = {
            "total_validations": 0,
            "passed_validations": 0,
            "failed_validations": 0,
            "warnings_issued": 0,
            "recoverable_errors": 0,
            "fatal_errors": 0,
        }

    def validate_message_base(self, message: Any) -> tuple[bool, list[str]]:
        """Validate base message properties."""
        self.validation_stats["total_validations"] += 1
        errors = []
        warnings = []

        try:
            # Check message exists
            if message is None:
                errors.append("Message is None")
                return False, errors

            # Check required base attributes
            required_attrs = ["type", "timestamp"]
            for attr in required_attrs:
                if not hasattr(message, attr):
                    errors.append(f"Missing required attribute: {attr}")
                elif getattr(message, attr) is None:
                    errors.append(f"Required attribute {attr} is None")

            # Validate timestamp if present
            if hasattr(message, "timestamp") and message.timestamp is not None:
                try:
                    self.sanitizer.sanitize_timestamp(message.timestamp)
                except ValidationError as e:
                    if (
                        e.recoverable
                        and self.validation_level == ValidationLevel.LENIENT
                    ):
                        warnings.append(f"Timestamp warning: {e}")
                        self.validation_stats["warnings_issued"] += 1
                    else:
                        errors.append(f"Timestamp error: {e}")

            # Log warnings
            for warning in warnings:
                logger.warning(warning)

            success = len(errors) == 0
            if success:
                self.validation_stats["passed_validations"] += 1
            else:
                self.validation_stats["failed_validations"] += 1

            return success, errors + warnings

        except Exception as e:
            error_msg = f"Unexpected validation error: {e}"
            logger.error(error_msg, exc_info=True)
            self.validation_stats["fatal_errors"] += 1
            return False, [error_msg]

    def validate_trade_message(
        self, message: Any
    ) -> tuple[bool, list[str], dict[str, Any]]:
        """Validate trade message with comprehensive checks and sanitization."""
        issues = []
        sanitized_data = {}

        # Base validation
        base_valid, base_issues = self.validate_message_base(message)
        issues.extend(base_issues)
        if not base_valid and self.validation_level == ValidationLevel.STRICT:
            return False, issues, sanitized_data

        try:
            # Required fields validation
            required_fields = [
                "market",
                "transaction_hash",
                "taker_order_id",
                "maker_orders",
            ]
            for field in required_fields:
                if not hasattr(message, field):
                    issues.append(f"Missing required field: {field}")
                elif getattr(message, field) is None:
                    issues.append(f"Required field {field} is None")

            # Sanitize and validate fields
            if hasattr(message, "market") and message.market is not None:
                try:
                    sanitized_data["market"] = self.sanitizer.sanitize_address(
                        message.market
                    )
                except ValidationError as e:
                    issues.append(f"Market validation error: {e}")

            if (
                hasattr(message, "transaction_hash")
                and message.transaction_hash is not None
            ):
                try:
                    sanitized_data["transaction_hash"] = self.sanitizer.sanitize_string(
                        message.transaction_hash, max_length=66
                    )
                except ValidationError as e:
                    issues.append(f"Transaction hash validation error: {e}")

            if (
                hasattr(message, "taker_order_id")
                and message.taker_order_id is not None
            ):
                try:
                    sanitized_data["taker_order_id"] = self.sanitizer.sanitize_string(
                        message.taker_order_id, max_length=100
                    )
                except ValidationError as e:
                    issues.append(f"Taker order ID validation error: {e}")

            # Validate maker orders
            if hasattr(message, "maker_orders") and message.maker_orders is not None:
                sanitized_orders = []
                if not isinstance(message.maker_orders, list):
                    issues.append("Maker orders must be a list")
                else:
                    for i, order in enumerate(message.maker_orders):
                        try:
                            sanitized_order = self._validate_maker_order(order, i)
                            sanitized_orders.append(sanitized_order)
                        except ValidationError as e:
                            if (
                                e.recoverable
                                and self.validation_level != ValidationLevel.STRICT
                            ):
                                logger.warning(f"Maker order {i} warning: {e}")
                                self.validation_stats["recoverable_errors"] += 1
                            else:
                                issues.append(f"Maker order {i} error: {e}")

                sanitized_data["maker_orders"] = sanitized_orders

            # Overall validation result
            has_errors = any("error" in issue.lower() for issue in issues)
            success = not has_errors or self.validation_level == ValidationLevel.LENIENT

            return success, issues, sanitized_data

        except Exception as e:
            error_msg = f"Trade message validation failed: {e}"
            logger.error(error_msg, exc_info=True)
            self.validation_stats["fatal_errors"] += 1
            return False, [error_msg], sanitized_data

    def _validate_maker_order(self, order: Any, index: int) -> dict[str, Any]:
        """Validate individual maker order."""
        if not isinstance(order, dict):
            raise ValidationError(
                f"Maker order {index} must be a dict", recoverable=False
            )

        sanitized_order = {}
        required_fields = ["orderId", "owner", "price", "size", "side"]

        for field in required_fields:
            if field not in order:
                raise ValidationError(
                    f"Maker order {index} missing field: {field}", recoverable=False
                )

        # Sanitize fields
        sanitized_order["orderId"] = self.sanitizer.sanitize_string(
            order["orderId"], max_length=100
        )
        sanitized_order["owner"] = self.sanitizer.sanitize_address(order["owner"])
        sanitized_order["price"] = self.sanitizer.sanitize_decimal(
            order["price"], min_value=Decimal("0"), max_value=Decimal("1")
        )
        sanitized_order["size"] = self.sanitizer.sanitize_decimal(
            order["size"], min_value=Decimal("0")
        )
        sanitized_order["side"] = self.sanitizer.sanitize_string(order["side"]).lower()

        if sanitized_order["side"] not in ["buy", "sell"]:
            raise ValidationError(
                f"Invalid side: {sanitized_order['side']}", recoverable=True
            )

        return sanitized_order

    def validate_order_message(
        self, message: Any
    ) -> tuple[bool, list[str], dict[str, Any]]:
        """Validate order message."""
        issues = []
        sanitized_data = {}

        # Base validation
        base_valid, base_issues = self.validate_message_base(message)
        issues.extend(base_issues)
        if not base_valid and self.validation_level == ValidationLevel.STRICT:
            return False, issues, sanitized_data

        try:
            # Required fields
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
                    issues.append(f"Missing or null required field: {field}")

            # Sanitize fields if present
            if hasattr(message, "order_id") and message.order_id is not None:
                sanitized_data["order_id"] = self.sanitizer.sanitize_string(
                    message.order_id, max_length=100
                )

            if hasattr(message, "market") and message.market is not None:
                try:
                    sanitized_data["market"] = self.sanitizer.sanitize_address(
                        message.market
                    )
                except ValidationError as e:
                    issues.append(f"Market validation error: {e}")

            if hasattr(message, "owner") and message.owner is not None:
                try:
                    sanitized_data["owner"] = self.sanitizer.sanitize_address(
                        message.owner
                    )
                except ValidationError as e:
                    issues.append(f"Owner validation error: {e}")

            if hasattr(message, "price") and message.price is not None:
                try:
                    sanitized_data["price"] = self.sanitizer.sanitize_decimal(
                        message.price, min_value=Decimal("0"), max_value=Decimal("1")
                    )
                except ValidationError as e:
                    issues.append(f"Price validation error: {e}")

            if hasattr(message, "size") and message.size is not None:
                try:
                    sanitized_data["size"] = self.sanitizer.sanitize_decimal(
                        message.size, min_value=Decimal("0")
                    )
                except ValidationError as e:
                    issues.append(f"Size validation error: {e}")

            if hasattr(message, "side") and message.side is not None:
                side_str = str(message.side).lower()
                if hasattr(message.side, "value"):  # Handle enum
                    side_str = str(message.side.value).lower()
                if side_str in ["buy", "sell"]:
                    sanitized_data["side"] = side_str
                else:
                    issues.append(f"Invalid side value: {side_str}")

            if hasattr(message, "status") and message.status is not None:
                status_str = str(message.status).lower()
                if hasattr(message.status, "value"):  # Handle enum
                    status_str = str(message.status.value).lower()
                valid_statuses = ["pending", "open", "filled", "cancelled", "failed"]
                if status_str in valid_statuses:
                    sanitized_data["status"] = status_str
                else:
                    issues.append(f"Invalid status value: {status_str}")

            has_errors = any("error" in issue.lower() for issue in issues)
            success = not has_errors or self.validation_level == ValidationLevel.LENIENT

            return success, issues, sanitized_data

        except Exception as e:
            error_msg = f"Order message validation failed: {e}"
            logger.error(error_msg, exc_info=True)
            self.validation_stats["fatal_errors"] += 1
            return False, [error_msg], sanitized_data

    def validate_book_message(
        self, message: Any
    ) -> tuple[bool, list[str], dict[str, Any]]:
        """Validate book message."""
        issues = []
        sanitized_data = {}

        # Base validation
        base_valid, base_issues = self.validate_message_base(message)
        issues.extend(base_issues)
        if not base_valid and self.validation_level == ValidationLevel.STRICT:
            return False, issues, sanitized_data

        try:
            # Required fields
            if not hasattr(message, "market") or message.market is None:
                issues.append("Missing or null market field")
            else:
                try:
                    sanitized_data["market"] = self.sanitizer.sanitize_address(
                        message.market
                    )
                except ValidationError as e:
                    issues.append(f"Market validation error: {e}")

            # Validate bids and asks
            sanitized_data["bids"] = []
            sanitized_data["asks"] = []

            if hasattr(message, "bids") and message.bids:
                try:
                    sanitized_data["bids"] = self._validate_book_levels(
                        message.bids, "bids"
                    )
                except ValidationError as e:
                    issues.append(f"Bids validation error: {e}")

            if hasattr(message, "asks") and message.asks:
                try:
                    sanitized_data["asks"] = self._validate_book_levels(
                        message.asks, "asks"
                    )
                except ValidationError as e:
                    issues.append(f"Asks validation error: {e}")

            # Check if we have at least some data
            if not sanitized_data["bids"] and not sanitized_data["asks"]:
                if self.validation_level == ValidationLevel.STRICT:
                    issues.append("Book message has no bids or asks")
                else:
                    logger.warning("Book message has no bids or asks")
                    self.validation_stats["warnings_issued"] += 1

            has_errors = any("error" in issue.lower() for issue in issues)
            success = not has_errors or self.validation_level == ValidationLevel.LENIENT

            return success, issues, sanitized_data

        except Exception as e:
            error_msg = f"Book message validation failed: {e}"
            logger.error(error_msg, exc_info=True)
            self.validation_stats["fatal_errors"] += 1
            return False, [error_msg], sanitized_data

    def _validate_book_levels(
        self, levels: list[Any], level_type: str
    ) -> list[dict[str, Decimal]]:
        """Validate bid/ask levels."""
        sanitized_levels = []

        for i, level in enumerate(levels):
            try:
                if not hasattr(level, "price") or not hasattr(level, "size"):
                    raise ValidationError(
                        f"{level_type} level {i} missing price or size"
                    )

                price = self.sanitizer.sanitize_decimal(
                    level.price, min_value=Decimal("0"), max_value=Decimal("1")
                )
                size = self.sanitizer.sanitize_decimal(
                    level.size, min_value=Decimal("0")
                )

                sanitized_levels.append(
                    {"price": price, "size": size, "value": price * size}
                )

            except ValidationError as e:
                if e.recoverable and self.validation_level != ValidationLevel.STRICT:
                    logger.warning(f"{level_type} level {i} warning: {e}")
                    self.validation_stats["recoverable_errors"] += 1
                else:
                    raise ValidationError(f"{level_type} level {i}: {e}")

        return sanitized_levels

    def get_validation_stats(self) -> dict[str, Any]:
        """Get validation statistics."""
        total = max(self.validation_stats["total_validations"], 1)
        return {
            **self.validation_stats,
            "success_rate": (self.validation_stats["passed_validations"] / total) * 100,
            "error_rate": (self.validation_stats["failed_validations"] / total) * 100,
        }

    def reset_stats(self):
        """Reset validation statistics."""
        for key in self.validation_stats:
            self.validation_stats[key] = 0


class FallbackDataProvider:
    """Provides fallback data for missing or invalid message fields."""

    @staticmethod
    def get_fallback_timestamp() -> datetime:
        """Get current timestamp as fallback."""
        return datetime.utcnow()

    @staticmethod
    def get_fallback_price() -> Decimal:
        """Get fallback price (0.5 as neutral)."""
        return Decimal("0.5")

    @staticmethod
    def get_fallback_size() -> Decimal:
        """Get fallback size (0)."""
        return Decimal("0")

    @staticmethod
    def get_fallback_side() -> str:
        """Get fallback order side."""
        return "buy"

    @staticmethod
    def get_fallback_status() -> str:
        """Get fallback order status."""
        return "unknown"

    @staticmethod
    def create_fallback_trade_data(market: str = "unknown") -> dict[str, Any]:
        """Create minimal fallback trade data."""
        return {
            "market": market,
            "transaction_hash": "unknown",
            "taker_order_id": "unknown",
            "maker_orders": [],
            "total_size": Decimal("0"),
            "weighted_avg_price": Decimal("0.5"),
            "timestamp": datetime.utcnow(),
            "is_fallback": True,
        }

    @staticmethod
    def create_fallback_order_data(market: str = "unknown") -> dict[str, Any]:
        """Create minimal fallback order data."""
        return {
            "order_id": "unknown",
            "market": market,
            "owner": "0x" + "0" * 40,
            "side": "buy",
            "price": Decimal("0.5"),
            "size": Decimal("0"),
            "status": "unknown",
            "timestamp": datetime.utcnow(),
            "is_fallback": True,
        }

    @staticmethod
    def create_fallback_book_data(market: str = "unknown") -> dict[str, Any]:
        """Create minimal fallback book data."""
        return {
            "market": market,
            "bids": [],
            "asks": [],
            "best_bid": None,
            "best_ask": None,
            "spread": None,
            "timestamp": datetime.utcnow(),
            "is_fallback": True,
        }
