"""
Comprehensive secure logging module for preventing sensitive data exposure.

This module provides robust sanitization of sensitive data in logs, error messages,
and debug output to prevent credential leaks and information disclosure.
"""

import hashlib
import logging
import re
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any


class SensitivityLevel(Enum):
    """Sensitivity levels for data sanitization."""

    MINIMAL = "minimal"  # Only most obvious sensitive data
    STANDARD = "standard"  # Common sensitive data patterns
    STRICT = "strict"  # Aggressive sanitization
    PARANOID = "paranoid"  # Maximum security, minimal information


class SecureLogger:
    """
    Enhanced logger with automatic sensitive data sanitization.

    Features:
    - Configurable sensitivity levels
    - Pattern-based sensitive data detection
    - Nested object sanitization
    - Circular reference handling
    - Performance optimized for production use
    """

    # Comprehensive sensitive data patterns
    SENSITIVE_PATTERNS = {
        SensitivityLevel.MINIMAL: {
            # Most obvious credentials
            "field_patterns": {
                r"private_key",
                r"secret",
                r"password",
                r"token",
                r"api_key",
            },
            "value_patterns": {
                r"^0x[0-9a-fA-F]{64}$",  # Private keys
                r"^[A-Za-z0-9+/]{32,}={0,2}$",  # Base64 tokens
            },
        },
        SensitivityLevel.STANDARD: {
            "field_patterns": {
                r"private_key",
                r"secret",
                r"password",
                r"token",
                r"api_key",
                r"auth",
                r"signature",
                r"hash",
                r"wallet",
                r"address",
                r"key",
                r"credential",
                r"session",
                r"cookie",
                r"bearer",
                r"jwt",
                r"oauth",
                r"nonce",
                r"salt",
            },
            "value_patterns": {
                r"0x[0-9a-fA-F]{40}",  # Ethereum addresses (anywhere in string)
                r"0x[0-9a-fA-F]{64}",  # Private keys/hashes (anywhere in string)
                r"[A-Za-z0-9+/]{20,}={0,2}",  # Base64 tokens
                r"[a-f0-9]{32}",  # MD5 hashes
                r"[a-f0-9]{40}",  # SHA-1 hashes
                r"[a-f0-9]{64}",  # SHA-256 hashes
            },
        },
        SensitivityLevel.STRICT: {
            "field_patterns": {
                r"private_key",
                r"secret",
                r"password",
                r"token",
                r"api_key",
                r"auth",
                r"signature",
                r"hash",
                r"wallet",
                r"address",
                r"key",
                r"credential",
                r"session",
                r"cookie",
                r"bearer",
                r"jwt",
                r"oauth",
                r"nonce",
                r"salt",
                r"seed",
                r"mnemonic",
                r"id",
                r"uuid",
                r"guid",
                r"client_id",
                r"user_id",
                r"account",
                r"email",
                r"phone",
                r"ssn",
                r"tax",
            },
            "value_patterns": {
                r"^0x[0-9a-fA-F]{40}$",  # Ethereum addresses
                r"^0x[0-9a-fA-F]{64}$",  # Private keys/hashes
                r"^[A-Za-z0-9+/]{16,}={0,2}$",  # Base64 strings
                r"^[a-f0-9]{32,}$",  # Hex strings
                r"^[A-Z0-9]{20,}$",  # API keys pattern
                r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email
                r"^\d{3}-?\d{3}-?\d{4}$",  # Phone numbers
                r"^\d{3}-?\d{2}-?\d{4}$",  # SSNs
            },
        },
        SensitivityLevel.PARANOID: {
            "field_patterns": {
                # Include all from STRICT plus more
                r".*key.*",
                r".*secret.*",
                r".*password.*",
                r".*token.*",
                r".*auth.*",
                r".*signature.*",
                r".*hash.*",
                r".*wallet.*",
                r".*address.*",
                r".*credential.*",
                r".*session.*",
                r".*id.*",
                r".*account.*",
                r".*email.*",
                r".*phone.*",
                r".*personal.*",
                r".*private.*",
                r".*confidential.*",
                r".*internal.*",
            },
            "value_patterns": {
                r"^0x[0-9a-fA-F]{8,}$",  # Any hex with 0x prefix
                r"^[A-Za-z0-9+/]{8,}={0,2}$",  # Any Base64-like string
                r"^[a-f0-9]{8,}$",  # Any lowercase hex
                r"^[A-F0-9]{8,}$",  # Any uppercase hex
                r"^\d{8,}$",  # Long numeric strings
                r"^[A-Z0-9]{8,}$",  # Uppercase alphanumeric
            },
        },
    }

    # Additional security patterns
    SECURITY_PATTERNS = {
        # Credit card patterns
        "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
        # Social security numbers
        "ssn": r"\b\d{3}-?\d{2}-?\d{4}\b",
        # IP addresses (sometimes sensitive)
        "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        # URLs with credentials
        "url_with_creds": r"https?://[^:]+:[^@]+@[^/]+",
        # JWT tokens
        "jwt": r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*\b",
    }

    def __init__(
        self,
        logger: logging.Logger | None = None,
        sensitivity_level: SensitivityLevel = SensitivityLevel.STANDARD,
        custom_patterns: dict[str, set[str]] | None = None,
        max_depth: int = 10,
        max_size: int = 1000000,
    ):
        """
        Initialize secure logger.

        Args:
            logger: Base logger instance
            sensitivity_level: How aggressive to be with sanitization
            custom_patterns: Additional sensitive patterns to detect
            max_depth: Maximum recursion depth for nested objects
            max_size: Maximum size of objects to fully sanitize
        """
        self.logger = logger or logging.getLogger(__name__)
        self.sensitivity_level = sensitivity_level
        self.max_depth = max_depth
        self.max_size = max_size

        # Compile patterns for performance
        self._compile_patterns(custom_patterns)

        # Cache for repeated sanitization
        self._sanitization_cache: dict[str, str] = {}

    def _compile_patterns(self, custom_patterns: dict[str, set[str]] | None = None):
        """Compile regex patterns for efficient matching."""
        base_patterns = self.SENSITIVE_PATTERNS[self.sensitivity_level]

        # Compile field patterns
        field_patterns = base_patterns["field_patterns"]
        if custom_patterns and "field_patterns" in custom_patterns:
            field_patterns.update(custom_patterns["field_patterns"])

        self._field_regex = [
            re.compile(pattern, re.IGNORECASE) for pattern in field_patterns
        ]

        # Compile value patterns
        value_patterns = base_patterns["value_patterns"]
        if custom_patterns and "value_patterns" in custom_patterns:
            value_patterns.update(custom_patterns["value_patterns"])

        self._value_regex = [re.compile(pattern) for pattern in value_patterns]

        # Compile security patterns
        self._security_regex = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in self.SECURITY_PATTERNS.items()
        }

    def _is_sensitive_field(self, field_name: str) -> bool:
        """Check if field name indicates sensitive data."""
        field_lower = str(field_name).lower()
        return any(pattern.search(field_lower) for pattern in self._field_regex)

    def _is_sensitive_value(self, value: str) -> bool:
        """Check if value appears to contain sensitive data."""
        if not isinstance(value, str) or len(value) < 8:
            return False

        # Check against value patterns (using search since patterns no longer anchored)
        if any(pattern.search(value) for pattern in self._value_regex):
            return True

        # Check against security patterns
        return any(pattern.search(value) for pattern in self._security_regex.values())

    def _generate_redaction_placeholder(
        self, original_value: Any, field_name: str = ""
    ) -> str:
        """Generate a consistent redaction placeholder."""
        if self.sensitivity_level == SensitivityLevel.PARANOID:
            return "[REDACTED]"

        # Create a short hash for consistency
        combined = f"{field_name}:{str(original_value)}"
        hash_obj = hashlib.sha256(combined.encode())
        short_hash = hash_obj.hexdigest()[:8]

        # Provide some context based on original data type/length
        if isinstance(original_value, str):
            length_hint = f"len={len(original_value)}"
        else:
            length_hint = f"type={type(original_value).__name__}"

        return f"[REDACTED:{short_hash}:{length_hint}]"

    def sanitize_data(
        self, data: Any, _depth: int = 0, _seen: set[int] | None = None
    ) -> Any:
        """
        Recursively sanitize data structure to remove sensitive information.

        Args:
            data: Data structure to sanitize
            _depth: Current recursion depth (internal)
            _seen: Set of object IDs to detect cycles (internal)

        Returns:
            Sanitized copy of the data structure
        """
        # Prevent infinite recursion
        if _depth > self.max_depth:
            return f"[TRUNCATED:max_depth={self.max_depth}]"

        # Handle circular references
        if _seen is None:
            _seen = set()

        obj_id = id(data)
        if obj_id in _seen:
            return f"[CIRCULAR_REFERENCE:{type(data).__name__}]"

        try:
            # Handle None
            if data is None:
                return None

            # Handle primitive types
            if isinstance(data, (bool, int, float)):
                return data

            # Handle strings
            if isinstance(data, str):
                return self._sanitize_string(data)

            # Size check for large objects
            try:
                data_size = len(str(data))
                if data_size > self.max_size:
                    return f"[TRUNCATED:size={data_size}:max={self.max_size}]"
            except Exception:
                # If size check fails, continue with sanitization
                # Note: intentionally not logging this as it could cause recursion
                pass

            # Add to seen set for circular reference detection
            _seen.add(obj_id)

            try:
                # Handle dictionaries
                if isinstance(data, dict):
                    return self._sanitize_dict(data, _depth, _seen)

                # Handle lists and tuples
                if isinstance(data, (list, tuple)):
                    return self._sanitize_sequence(data, _depth, _seen)

                # Handle dataclasses
                if is_dataclass(data):
                    return self._sanitize_dataclass(data, _depth, _seen)

                # Handle objects with __dict__
                if hasattr(data, "__dict__"):
                    return self._sanitize_object(data, _depth, _seen)

                # Handle other types with string representation
                return self._sanitize_string(str(data))

            finally:
                # Remove from seen set when done processing
                _seen.discard(obj_id)

        except Exception as e:
            # If sanitization fails, return safe representation
            return f"[SANITIZATION_ERROR:{type(e).__name__}:{type(data).__name__}]"

    def _sanitize_string(self, value: str) -> str:
        """Sanitize a string value."""
        if self._is_sensitive_value(value):
            return self._generate_redaction_placeholder(value)

        # For PARANOID mode, be more aggressive with long strings
        if (
            self.sensitivity_level == SensitivityLevel.PARANOID
            and len(value) > 50
            and any(char.isdigit() or char.isupper() for char in value)
        ):
            return self._generate_redaction_placeholder(value)

        # Truncate very long strings
        if len(value) > 500:
            return value[:500] + f"...[TRUNCATED:total_len={len(value)}]"

        return value

    def _sanitize_dict(self, data: dict, _depth: int, _seen: set[int]) -> dict:
        """Sanitize a dictionary."""
        sanitized = {}

        for key, value in data.items():
            key_str = str(key)

            # Check if field name indicates sensitive data
            if self._is_sensitive_field(key_str):
                sanitized[key] = self._generate_redaction_placeholder(value, key_str)
            else:
                sanitized[key] = self.sanitize_data(value, _depth + 1, _seen)

        return sanitized

    def _sanitize_sequence(
        self, data: list | tuple, _depth: int, _seen: set[int]
    ) -> list | tuple:
        """Sanitize a list or tuple."""
        # Limit sequence length to prevent memory issues
        max_items = 100 if self.sensitivity_level != SensitivityLevel.PARANOID else 20

        if len(data) > max_items:
            sanitized_items = [
                self.sanitize_data(item, _depth + 1, _seen) for item in data[:max_items]
            ]
            sanitized_items.append(f"[TRUNCATED:{len(data)-max_items}_more_items]")
        else:
            sanitized_items = [
                self.sanitize_data(item, _depth + 1, _seen) for item in data
            ]

        return type(data)(sanitized_items)

    def _sanitize_dataclass(self, data: Any, _depth: int, _seen: set[int]) -> dict:
        """Sanitize a dataclass object."""
        try:
            data_dict = asdict(data)
            sanitized_dict = self._sanitize_dict(data_dict, _depth, _seen)
            sanitized_dict["__type__"] = type(data).__name__
            return sanitized_dict
        except Exception:
            return f"[DATACLASS:{type(data).__name__}:sanitization_failed]"

    def _sanitize_object(self, data: Any, _depth: int, _seen: set[int]) -> dict:
        """Sanitize an object with __dict__."""
        try:
            data_dict = vars(data).copy()
            sanitized_dict = self._sanitize_dict(data_dict, _depth, _seen)
            sanitized_dict["__type__"] = type(data).__name__
            return sanitized_dict
        except Exception:
            return f"[OBJECT:{type(data).__name__}:sanitization_failed]"

    def sanitize_exception(self, exc: Exception) -> str:
        """
        Sanitize exception information to prevent sensitive data leaks.

        Args:
            exc: Exception to sanitize

        Returns:
            Safe string representation of the exception
        """
        try:
            exc_type = type(exc).__name__
            exc_str = str(exc)

            # Sanitize the exception message by checking for sensitive patterns
            sanitized_message = exc_str

            # Check for and redact sensitive value patterns
            for pattern in self._value_regex:
                sanitized_message = pattern.sub(
                    "[REDACTED:sensitive_value]", sanitized_message
                )

            # Check for and redact security patterns
            for name, pattern in self._security_regex.items():
                sanitized_message = pattern.sub(f"[REDACTED:{name}]", sanitized_message)

            # If message is still too long, truncate it
            if len(sanitized_message) > 200:
                sanitized_message = sanitized_message[:200] + "...[TRUNCATED]"

            return f"{exc_type}: {sanitized_message}"

        except Exception:
            return f"[EXCEPTION_SANITIZATION_FAILED:{type(exc).__name__}]"

    # Logging methods with automatic sanitization
    def debug(self, message: str, *args, **kwargs):
        """Log debug message with sanitization."""
        sanitized_args = [self.sanitize_data(arg) for arg in args]
        sanitized_kwargs = self.sanitize_data(kwargs)
        self.logger.debug(message, *sanitized_args, **sanitized_kwargs)

    def info(self, message: str, *args, **kwargs):
        """Log info message with sanitization."""
        sanitized_args = [self.sanitize_data(arg) for arg in args]
        sanitized_kwargs = self.sanitize_data(kwargs)
        self.logger.info(message, *sanitized_args, **sanitized_kwargs)

    def warning(self, message: str, *args, **kwargs):
        """Log warning message with sanitization."""
        sanitized_args = [self.sanitize_data(arg) for arg in args]
        sanitized_kwargs = self.sanitize_data(kwargs)
        self.logger.warning(message, *sanitized_args, **sanitized_kwargs)

    def error(self, message: str, *args, exc_info=None, **kwargs):
        """Log error message with sanitization."""
        sanitized_args = [self.sanitize_data(arg) for arg in args]
        sanitized_kwargs = self.sanitize_data(kwargs)

        # Handle exc_info specially
        if exc_info is True:
            # Let logging handle getting current exception
            self.logger.error(
                message, *sanitized_args, exc_info=True, **sanitized_kwargs
            )
        elif isinstance(exc_info, Exception):
            # Sanitize the exception
            sanitized_exc = self.sanitize_exception(exc_info)
            self.logger.error(
                f"{message} Exception: {sanitized_exc}",
                *sanitized_args,
                **sanitized_kwargs,
            )
        else:
            self.logger.error(message, *sanitized_args, **sanitized_kwargs)

    def critical(self, message: str, *args, **kwargs):
        """Log critical message with sanitization."""
        sanitized_args = [self.sanitize_data(arg) for arg in args]
        sanitized_kwargs = self.sanitize_data(kwargs)
        self.logger.critical(message, *sanitized_args, **sanitized_kwargs)


# Convenience functions for creating secure loggers
def get_secure_logger(
    name: str, sensitivity_level: SensitivityLevel = SensitivityLevel.STANDARD
) -> SecureLogger:
    """
    Get a secure logger instance.

    Args:
        name: Logger name
        sensitivity_level: Sensitivity level for sanitization

    Returns:
        SecureLogger instance
    """
    base_logger = logging.getLogger(name)
    return SecureLogger(base_logger, sensitivity_level)


def sanitize_for_logging(
    data: Any, sensitivity_level: SensitivityLevel = SensitivityLevel.STANDARD
) -> Any:
    """
    Standalone function to sanitize data for logging.

    Args:
        data: Data to sanitize
        sensitivity_level: Sensitivity level

    Returns:
        Sanitized data safe for logging
    """
    sanitizer = SecureLogger(sensitivity_level=sensitivity_level)
    return sanitizer.sanitize_data(data)


def create_safe_error_message(
    base_message: str,
    error_details: Any = None,
    sensitivity_level: SensitivityLevel = SensitivityLevel.STANDARD,
) -> str:
    """
    Create a safe error message with sanitized details.

    Args:
        base_message: Base error message
        error_details: Error details to sanitize
        sensitivity_level: Sensitivity level

    Returns:
        Safe error message
    """
    if error_details is None:
        return base_message

    sanitized_details = sanitize_for_logging(error_details, sensitivity_level)
    return f"{base_message} Details: {sanitized_details}"
