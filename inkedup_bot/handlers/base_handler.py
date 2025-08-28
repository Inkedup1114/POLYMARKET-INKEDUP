"""
Base message handler for Polymarket WebSocket messages.

This module provides the base class for all message handlers.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from ..models.ws_messages import WebSocketMessage
from .validation_utils import (
    FallbackDataProvider,
    MessageValidator,
    ValidationError,
    ValidationLevel,
)

logger = logging.getLogger(__name__)


class BaseMessageHandler(ABC):
    """
    Base class for WebSocket message handlers with comprehensive validation and error handling.

    Provides common functionality for processing and routing WebSocket messages
    with robust validation, error recovery, and data quality assurance.
    """

    def __init__(
        self,
        name: str,
        validation_level: ValidationLevel = ValidationLevel.MODERATE,
        enable_fallbacks: bool = False,
        max_processing_time: float = 5.0,
    ):
        """
        Initialize the message handler.

        Args:
            name: Handler name for logging purposes
            validation_level: Validation strictness level
            enable_fallbacks: Whether to use fallback data for recoverable errors
            max_processing_time: Maximum processing time per message in seconds
        """
        self.name = name
        self.validation_level = validation_level
        self.enable_fallbacks = enable_fallbacks
        self.max_processing_time = max_processing_time

        # Components
        self.validator = MessageValidator(validation_level)
        self.fallback_provider = FallbackDataProvider()

        # Callbacks
        self._callbacks: list[Callable[[Any], Awaitable[None]]] = []

        # Basic metrics
        self._message_count = 0
        self._error_count = 0
        self._warning_count = 0
        self._fallback_count = 0
        self._validation_failures = 0
        self._processing_timeouts = 0
        self._last_message_time: datetime | None = None

        # Performance tracking
        self._total_processing_time = 0.0
        self._min_processing_time = float("inf")
        self._max_processing_time = 0.0

        # Circuit breaker for error handling
        self._consecutive_errors = 0
        self._max_consecutive_errors = 10
        self._circuit_breaker_active = False
        self._circuit_breaker_reset_time: datetime | None = None

    def add_callback(self, callback: Callable[[Any], Awaitable[None]]) -> None:
        """
        Add a callback to be called when a message is processed.

        Args:
            callback: Async callback function that receives the processed message
        """
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[Any], Awaitable[None]]) -> bool:
        """
        Remove a callback.

        Args:
            callback: Callback function to remove

        Returns:
            True if callback was found and removed
        """
        try:
            self._callbacks.remove(callback)
            return True
        except ValueError:
            return False

    async def process_message(self, message: WebSocketMessage) -> bool:
        """
        Process a WebSocket message with comprehensive error handling, validation, and recovery.

        Args:
            message: WebSocket message to process

        Returns:
            True if message was processed successfully, False otherwise
        """
        start_time = time.time()
        processed_data = None

        try:
            self._message_count += 1
            self._last_message_time = datetime.utcnow()

            # Check circuit breaker
            if self._circuit_breaker_active:
                if datetime.utcnow() < self._circuit_breaker_reset_time:
                    logger.warning(
                        f"Circuit breaker active for {self.name}, skipping message"
                    )
                    return False
                else:
                    logger.info(f"Circuit breaker reset for {self.name}")
                    self._circuit_breaker_active = False
                    self._consecutive_errors = 0

            # Enhanced message processing with timeout using asyncio.wait_for
            try:
                core_processing = self._process_message_core(message, start_time)
                result = await asyncio.wait_for(
                    core_processing, timeout=self.max_processing_time
                )
                return result

            except TimeoutError:
                self._processing_timeouts += 1
                logger.warning(
                    f"Message processing timeout in {self.name} after {self.max_processing_time}s"
                )
                return await self._handle_timeout(message)

        except ValidationError as e:
            self._validation_failures += 1
            return await self._handle_validation_error(e, message)
        except NotImplementedError as e:
            logger.critical(f"Handler implementation error in {self.name}: {e}")
            self._error_count += 1
            self._consecutive_errors += 1
            return False
        except Exception as e:
            self._error_count += 1
            self._consecutive_errors += 1
            logger.error(
                f"Unexpected error processing message in {self.name}: {e}",
                exc_info=True,
            )

            # Check if we need to activate circuit breaker
            if self._consecutive_errors >= self._max_consecutive_errors:
                self._activate_circuit_breaker()

            return await self._handle_processing_error(e, message)

    async def get_processed_data(self, message: WebSocketMessage) -> bool:
        """Enhanced method that returns both success and processed data."""
        # This would be the enhanced version that returns data too
        # For now, just return the success status and None for data
        success = await self.process_message(message)
        return success, None

    async def _process_message_core(
        self, message: WebSocketMessage, start_time: float
    ) -> bool:
        """Core message processing logic without timeout wrapper."""
        # Pre-processing validation with comprehensive checks
        validation_success, processed_data = await self._comprehensive_validation(
            message
        )

        if not validation_success:
            # For backward compatibility, validation failures should return False unless fallbacks are explicitly enabled
            if self.enable_fallbacks:
                return await self._handle_validation_failure(message)
            else:
                # Increment error count for validation failures
                self._error_count += 1
                return False

        # Process the message
        if processed_data is not None:
            # Use pre-validated/sanitized data if available
            result = await self._handle_message_with_data(message, processed_data)
        else:
            # Fallback to original processing
            result = await self._handle_message(message)

        processed_data = result

        # Post-processing validation and enhancement
        processed_data = await self._post_process_data(processed_data, message)

        # Notify callbacks with comprehensive error isolation
        await self._notify_callbacks_safe(processed_data)

        # Update success metrics
        self._consecutive_errors = 0
        processing_time = time.time() - start_time
        self._update_performance_metrics(processing_time)

        return True

    async def _comprehensive_validation(
        self, message: WebSocketMessage
    ) -> tuple[bool, dict[str, Any] | None]:
        """Perform comprehensive validation with type-specific checks."""
        try:
            # Handle None message early
            if message is None:
                logger.error(f"Received None message in {self.name}")
                return False, None

            # Base validation
            base_valid, base_issues = self.validator.validate_message_base(message)

            if not base_valid and self.validation_level == ValidationLevel.STRICT:
                logger.error(f"Base validation failed in {self.name}: {base_issues}")
                return False, None

            # Type-specific validation
            message_type = getattr(message, "type", "unknown")
            (
                type_validation_success,
                type_issues,
                sanitized_data,
            ) = await self._validate_by_type(message, message_type)

            # Combine results
            all_issues = base_issues + type_issues
            overall_success = base_valid and type_validation_success

            # Log issues based on severity
            errors = [issue for issue in all_issues if "error" in issue.lower()]
            warnings = [issue for issue in all_issues if "warning" in issue.lower()]

            for error in errors:
                logger.error(f"Validation error in {self.name}: {error}")
            for warning in warnings:
                logger.warning(f"Validation warning in {self.name}: {warning}")
                self._warning_count += 1

            # Determine if we can proceed
            can_proceed = overall_success or (
                self.validation_level == ValidationLevel.LENIENT
                and len(errors) == 0  # No hard errors, only warnings
            )

            return can_proceed, sanitized_data if can_proceed else None

        except Exception as e:
            logger.error(f"Validation error in {self.name}: {e}", exc_info=True)
            return False, None

    async def _validate_by_type(
        self, message: WebSocketMessage, message_type: str
    ) -> tuple[bool, list[str], dict[str, Any] | None]:
        """Perform type-specific validation - override in subclasses."""
        # Default implementation - subclasses should override for specific validation
        return True, [], None

    async def _handle_message_with_data(
        self, message: WebSocketMessage, sanitized_data: dict[str, Any]
    ) -> Any:
        """Handle message with pre-validated data - override in subclasses if needed."""
        # Default: delegate to original handler
        return await self._handle_message(message)

    @abstractmethod
    async def _handle_message(self, message: WebSocketMessage) -> dict[str, Any]:
        """
        Handle the actual message processing.

        This is the core method that subclasses must implement to process specific
        message types. The base class provides common validation and error handling.

        IMPLEMENTATION REQUIREMENTS:
        - Must validate the message type using isinstance() checks
        - Must return a dictionary with processed data
        - Should raise ValueError for invalid/unsupported message types
        - Must handle all expected fields for the message type
        - Should implement appropriate logging for the message type

        EXPECTED RETURN FORMAT:
        The returned dictionary should include at minimum:
        - 'type': str - Message type identifier
        - 'market': str - Market contract address (if applicable)
        - 'timestamp': datetime - Message timestamp
        - Additional fields specific to the message type

        Args:
            message: WebSocket message to process. Type will be validated by subclass.

        Returns:
            Dictionary containing processed message data with type-specific fields

        Raises:
            ValueError: If message type is invalid or unsupported by this handler
            NotImplementedError: If subclass doesn't implement this method (development error)

        Example Implementation:
            ```python
            async def _handle_message(self, message: WebSocketMessage) -> Dict[str, Any]:
                if not isinstance(message, ExpectedMessageType):
                    raise ValueError(f"Expected ExpectedMessageType, got {type(message)}")

                return {
                    'type': 'expected_type',
                    'market': message.market,
                    'timestamp': message.timestamp,
                    # ... other type-specific fields
                }
            ```
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _handle_message() method. "
            f"This method should validate message types using isinstance() and return "
            f"a dictionary with processed message data."
        )

    def _validate_message(self, message: WebSocketMessage) -> bool:
        """
        Validate a WebSocket message before processing.

        Subclasses can override this method to add specific validation logic.

        Args:
            message: WebSocket message to validate

        Returns:
            True if message is valid, False otherwise
        """
        if message is None:
            logger.error("Received None message")
            return False

        # Check if message has required attributes
        if not hasattr(message, "type"):
            logger.error("Message missing 'type' attribute")
            return False

        if not hasattr(message, "timestamp"):
            logger.error("Message missing 'timestamp' attribute")
            return False

        # Validate timestamp is not too old (optional - can be overridden)
        return self._validate_message_timestamp(message)

    def _validate_message_timestamp(self, message: WebSocketMessage) -> bool:
        """
        Validate message timestamp to ensure it's not too old.

        Args:
            message: WebSocket message to validate

        Returns:
            True if timestamp is acceptable, False otherwise
        """
        try:
            # Allow messages up to 1 hour old (configurable)
            max_age_seconds = 3600
            now = datetime.utcnow()

            if hasattr(message, "timestamp") and message.timestamp:
                message_time = message.timestamp
                # Handle both datetime objects and timestamp strings
                if isinstance(message_time, str):
                    try:
                        message_time = datetime.fromisoformat(
                            message_time.replace("Z", "+00:00")
                        )
                    except ValueError:
                        logger.warning(
                            f"Invalid timestamp format in message: {message_time}"
                        )
                        return True  # Don't fail on timestamp format issues

                age_seconds = (now - message_time).total_seconds()
                if age_seconds > max_age_seconds:
                    logger.warning(
                        f"Message is {age_seconds}s old, exceeds max age of {max_age_seconds}s"
                    )
                    return False

        except Exception as e:
            logger.warning(f"Error validating message timestamp: {e}")
            # Don't fail message processing due to timestamp validation errors
            return True

        return True

    async def _handle_validation_failure(self, message: WebSocketMessage) -> bool:
        """Handle validation failure with fallback if enabled."""
        self._validation_failures += 1

        if self.enable_fallbacks:
            try:
                fallback_data = await self._create_fallback_data(message)
                if fallback_data:
                    self._fallback_count += 1
                    logger.info(
                        f"Using fallback data for {self.name} due to validation failure"
                    )
                    await self._notify_callbacks_safe(fallback_data)
                    return True
            except Exception as e:
                logger.error(f"Fallback creation failed in {self.name}: {e}")

        return False

    async def _handle_validation_error(
        self, error: ValidationError, message: WebSocketMessage
    ) -> bool:
        """Handle validation error with recovery if possible."""
        if error.recoverable and self.enable_fallbacks:
            logger.warning(f"Recoverable validation error in {self.name}: {error}")
            return await self._handle_validation_failure(message)
        else:
            logger.error(f"Non-recoverable validation error in {self.name}: {error}")
            return False

    async def _handle_timeout(self, message: WebSocketMessage) -> bool:
        """Handle processing timeout with fallback if enabled."""
        if self.enable_fallbacks:
            try:
                fallback_data = await self._create_fallback_data(message)
                if fallback_data:
                    self._fallback_count += 1
                    logger.info(f"Using fallback data for {self.name} due to timeout")
                    await self._notify_callbacks_safe(fallback_data)
                    return True
            except Exception as e:
                logger.error(f"Timeout fallback failed in {self.name}: {e}")

        return False

    async def _handle_processing_error(
        self, error: Exception, message: WebSocketMessage
    ) -> bool:
        """Handle processing error with fallback if appropriate."""
        if self.enable_fallbacks and not isinstance(
            error, (NotImplementedError, SystemExit)
        ):
            try:
                fallback_data = await self._create_fallback_data(message)
                if fallback_data:
                    self._fallback_count += 1
                    logger.info(
                        f"Using fallback data for {self.name} due to processing error"
                    )
                    await self._notify_callbacks_safe(fallback_data)
                    return True
            except Exception as fallback_error:
                logger.error(f"Error fallback failed in {self.name}: {fallback_error}")

        return False

    async def _post_process_data(
        self, processed_data: Any, original_message: WebSocketMessage
    ) -> Any:
        """Post-process data with quality checks and enhancements."""
        if processed_data is None:
            return processed_data

        try:
            # Only add metadata in enhanced mode, not for backward compatibility
            # This prevents breaking existing callback expectations
            add_metadata = getattr(self, "_enable_enhanced_metadata", False)

            if add_metadata and isinstance(processed_data, dict):
                if "processed_at" not in processed_data:
                    processed_data["processed_at"] = datetime.utcnow()
                if "handler_name" not in processed_data:
                    processed_data["handler_name"] = self.name
                if "validation_level" not in processed_data:
                    processed_data["validation_level"] = self.validation_level.value

            # Perform data quality checks
            quality_score = self._calculate_data_quality(processed_data)
            if quality_score < 0.5:  # Low quality threshold
                logger.warning(
                    f"Low data quality score ({quality_score:.2f}) for {self.name}"
                )

            return processed_data

        except Exception as e:
            logger.warning(f"Post-processing error in {self.name}: {e}")
            return processed_data  # Return original data if post-processing fails

    def _calculate_data_quality(self, data: Any) -> float:
        """Calculate data quality score (0-1)."""
        if data is None:
            return 0.0

        if not isinstance(data, dict):
            return 0.8  # Non-dict data gets moderate score

        score = 1.0

        # Check for required fields
        if "market" not in data or not data["market"]:
            score -= 0.3
        if "timestamp" not in data or not data["timestamp"]:
            score -= 0.2

        # Check for fallback indicators
        if data.get("is_fallback", False):
            score -= 0.3

        # Check for data completeness
        non_none_fields = sum(1 for v in data.values() if v is not None)
        total_fields = len(data)
        if total_fields > 0:
            completeness_ratio = non_none_fields / total_fields
            score *= completeness_ratio

        return max(0.0, min(1.0, score))

    async def _create_fallback_data(
        self, message: WebSocketMessage
    ) -> dict[str, Any] | None:
        """Create fallback data for failed message processing."""
        message_type = getattr(message, "type", "unknown")
        market = getattr(message, "market", "unknown")

        if message_type == "trade":
            return self.fallback_provider.create_fallback_trade_data(market)
        elif message_type == "order":
            return self.fallback_provider.create_fallback_order_data(market)
        elif message_type == "book":
            return self.fallback_provider.create_fallback_book_data(market)
        else:
            # Generic fallback
            return {
                "type": message_type,
                "market": market,
                "timestamp": datetime.utcnow(),
                "is_fallback": True,
                "handler_name": self.name,
            }

    def _activate_circuit_breaker(self):
        """Activate circuit breaker to prevent cascading failures."""
        self._circuit_breaker_active = True
        self._circuit_breaker_reset_time = datetime.utcnow() + timedelta(minutes=5)
        logger.warning(
            f"Circuit breaker activated for {self.name} - too many consecutive errors"
        )

    def _update_performance_metrics(self, processing_time: float):
        """Update performance metrics."""
        self._total_processing_time += processing_time
        self._min_processing_time = min(self._min_processing_time, processing_time)
        self._max_processing_time = max(self._max_processing_time, processing_time)

    async def _notify_callbacks_safe(self, processed_data: Any) -> None:
        """
        Safely notify all registered callbacks with comprehensive error isolation.

        Args:
            processed_data: The processed message data to pass to callbacks
        """
        if not self._callbacks:
            return

        callback_tasks = []
        for i, callback in enumerate(self._callbacks):
            task = asyncio.create_task(
                self._safe_callback_wrapper(callback, processed_data, i)
            )
            callback_tasks.append(task)

        # Wait for all callbacks with timeout
        if callback_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*callback_tasks, return_exceptions=True),
                    timeout=2.0,  # 2 second timeout for all callbacks
                )
            except TimeoutError:
                logger.warning(f"Some callbacks timed out for {self.name}")

    async def _safe_callback_wrapper(
        self, callback: Callable, data: Any, callback_index: int
    ):
        """Safely execute a single callback with individual timeout."""
        try:
            await asyncio.wait_for(callback(data), timeout=1.0)
        except TimeoutError:
            logger.warning(f"Callback {callback_index} timed out for {self.name}")
        except Exception as e:
            logger.error(f"Error in callback {callback_index} for {self.name}: {e}")

    async def _notify_callbacks(self, processed_data: Any) -> None:
        """
        Legacy method for backward compatibility - delegates to safe version.

        Args:
            processed_data: The processed message data to pass to callbacks
        """
        await self._notify_callbacks_safe(processed_data)

    def supports_message_type(self, message_type: str) -> bool:
        """
        Check if this handler supports a specific message type.

        Subclasses should override this method to specify which message types they handle.

        Args:
            message_type: The message type string to check

        Returns:
            True if this handler supports the message type, False otherwise
        """
        # Base implementation returns False - subclasses must override
        return False

    def get_supported_message_types(self) -> list[str]:
        """
        Get list of message types supported by this handler.

        Subclasses should override this method to return their supported types.

        Returns:
            List of supported message type strings
        """
        # Base implementation returns empty list - subclasses should override
        return []

    def get_stats(self) -> dict[str, Any]:
        """
        Get handler statistics.

        Returns:
            Dictionary with handler statistics
        """
        return {
            "name": self.name,
            "message_count": self._message_count,
            "error_count": self._error_count,
            "last_message_time": (
                self._last_message_time.isoformat() if self._last_message_time else None
            ),
            "callback_count": len(self._callbacks),
        }

    def reset_stats(self) -> None:
        """Reset handler statistics."""
        self._message_count = 0
        self._error_count = 0
        self._last_message_time = None

    @property
    def message_count(self) -> int:
        """Get total message count."""
        return self._message_count

    @property
    def error_count(self) -> int:
        """Get total error count."""
        return self._error_count

    @property
    def last_message_time(self) -> datetime | None:
        """Get last message time."""
        return self._last_message_time
