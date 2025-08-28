"""
Validation decorators and utilities for state management.

This module provides decorators and utilities to automatically validate
data before database operations and state updates.
"""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from .models import (
    ExposureAlertValidation,
    MarketSnapshotValidation,
    OrderValidation,
    OutcomeCorrelationValidation,
    OutcomeExposureValidation,
    PositionValidation,
    RiskEventValidation,
    TradeValidation,
    ValidationError,
)

log = logging.getLogger("validation")

F = TypeVar("F", bound=Callable[..., Any])


class ValidationContext:
    """Context for validation operations with configuration."""

    def __init__(
        self,
        strict_mode: bool = True,
        log_validation_errors: bool = True,
        raise_on_validation_error: bool = True,
        validation_timeout: float = 5.0,
    ):
        self.strict_mode = strict_mode
        self.log_validation_errors = log_validation_errors
        self.raise_on_validation_error = raise_on_validation_error
        self.validation_timeout = validation_timeout


# Global validation context
default_validation_context = ValidationContext()


def validate_input(model_class: type[BaseModel], input_param: str = None):
    """
    Decorator to validate input parameters against a Pydantic model.

    Args:
        model_class: Pydantic model class to validate against
        input_param: Name of parameter to validate (if None, validates all dict parameters)
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                # Handle both positional and keyword arguments
                if input_param:
                    # Validate specific parameter
                    if input_param in kwargs:
                        value = kwargs[input_param]
                        if isinstance(value, dict):
                            validated = model_class(**value)
                            kwargs[input_param] = validated.model_dump()
                    else:
                        # Check positional arguments by function signature
                        import inspect

                        sig = inspect.signature(func)
                        param_names = list(sig.parameters.keys())
                        for i, arg in enumerate(args):
                            if i < len(param_names) and param_names[i] == input_param:
                                if isinstance(arg, dict):
                                    validated = model_class(**arg)
                                    args = list(args)
                                    args[i] = validated.model_dump()
                                    args = tuple(args)
                                break
                else:
                    # Validate all dict parameters
                    for key, value in kwargs.items():
                        if isinstance(value, dict):
                            try:
                                validated = model_class(**value)
                                kwargs[key] = validated.model_dump()
                            except PydanticValidationError:
                                # Skip if validation fails for this parameter
                                continue

                return func(*args, **kwargs)

            except PydanticValidationError as e:
                error_msg = f"Validation failed in {func.__name__}: {str(e)}"
                if default_validation_context.log_validation_errors:
                    log.error(error_msg)
                if default_validation_context.raise_on_validation_error:
                    raise ValidationError(error_msg)
                return None
            except Exception as e:
                log.error(
                    f"Unexpected error in validation decorator for {func.__name__}: {e}"
                )
                if default_validation_context.strict_mode:
                    raise
                return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_order_data(func: F) -> F:
    """Decorator specifically for order data validation."""
    return validate_input(OrderValidation, "order")(func)


def validate_position_data(func: F) -> F:
    """Decorator specifically for position data validation."""
    return validate_input(PositionValidation, "position_data")(func)


def validate_trade_data(func: F) -> F:
    """Decorator specifically for trade data validation."""
    return validate_input(TradeValidation)(func)


def validate_output(model_class: type[BaseModel]):
    """
    Decorator to validate function output against a Pydantic model.

    Args:
        model_class: Pydantic model class to validate against
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            if result is None:
                return result

            try:
                if isinstance(result, dict):
                    # Validate single dict result
                    validated = model_class(**result)
                    return validated.model_dump()
                elif isinstance(result, list) and all(
                    isinstance(item, dict) for item in result
                ):
                    # Validate list of dict results
                    validated_list = []
                    for item in result:
                        validated = model_class(**item)
                        validated_list.append(validated.model_dump())
                    return validated_list
                else:
                    # Return as-is if not a dict or list of dicts
                    return result

            except PydanticValidationError as e:
                error_msg = f"Output validation failed in {func.__name__}: {str(e)}"
                if default_validation_context.log_validation_errors:
                    log.warning(error_msg)
                if default_validation_context.strict_mode:
                    raise ValidationError(error_msg)
                # Return original result if validation fails in non-strict mode
                return result

        return wrapper

    return decorator


def validate_database_write(operation_type: str):
    """
    Decorator for database write operations with operation-specific validation.

    Args:
        operation_type: Type of database operation (insert, update, delete)
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Log the operation for audit trail
            if default_validation_context.log_validation_errors:
                log.debug(f"Database {operation_type} operation: {func.__name__}")

            # Pre-operation validation based on function name
            function_name = func.__name__.lower()

            try:
                if "order" in function_name:
                    # Apply order validation
                    return validate_input(OrderValidation)(func)(*args, **kwargs)
                elif "position" in function_name:
                    # Apply position validation
                    return validate_input(PositionValidation)(func)(*args, **kwargs)
                elif "trade" in function_name:
                    # Apply trade validation
                    return validate_input(TradeValidation)(func)(*args, **kwargs)
                elif "market_snapshot" in function_name or "snapshot" in function_name:
                    # Apply market snapshot validation
                    return validate_input(MarketSnapshotValidation)(func)(
                        *args, **kwargs
                    )
                elif "risk_event" in function_name:
                    # Apply risk event validation
                    return validate_input(RiskEventValidation)(func)(*args, **kwargs)
                elif "outcome_exposure" in function_name:
                    # Apply outcome exposure validation
                    return validate_input(OutcomeExposureValidation)(func)(
                        *args, **kwargs
                    )
                elif "outcome_correlation" in function_name:
                    # Apply correlation validation
                    return validate_input(OutcomeCorrelationValidation)(func)(
                        *args, **kwargs
                    )
                elif "exposure_alert" in function_name or "alert" in function_name:
                    # Apply alert validation
                    return validate_input(ExposureAlertValidation)(func)(
                        *args, **kwargs
                    )
                else:
                    # Generic validation for any dict parameters
                    return func(*args, **kwargs)

            except ValidationError:
                # Re-raise validation errors
                raise
            except Exception as e:
                log.error(f"Database operation {func.__name__} failed: {e}")
                if default_validation_context.strict_mode:
                    raise ValidationError(f"Database operation failed: {str(e)}")
                raise

        return wrapper

    return decorator


def safe_database_operation(func: F) -> F:
    """
    Decorator to make database operations safe with automatic validation and error handling.
    """

    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        """Async wrapper for database operations."""
        try:
            # Determine operation type from function name
            operation_type = "read"
            if any(op in func.__name__.lower() for op in ["insert", "create", "add"]):
                operation_type = "insert"
            elif any(
                op in func.__name__.lower() for op in ["update", "upsert", "modify"]
            ):
                operation_type = "update"
            elif any(op in func.__name__.lower() for op in ["delete", "remove"]):
                operation_type = "delete"

            # Apply appropriate validation
            validated_func = validate_database_write(operation_type)(func)
            return await validated_func(*args, **kwargs)

        except ValidationError:
            # Re-raise validation errors
            raise
        except Exception as e:
            log.error(f"Safe database operation {func.__name__} failed: {e}")
            if default_validation_context.raise_on_validation_error:
                raise ValidationError(f"Database operation failed: {str(e)}")
            return None

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        """Sync wrapper for database operations."""
        try:
            # Determine operation type from function name
            operation_type = "read"
            if any(op in func.__name__.lower() for op in ["insert", "create", "add"]):
                operation_type = "insert"
            elif any(
                op in func.__name__.lower() for op in ["update", "upsert", "modify"]
            ):
                operation_type = "update"
            elif any(op in func.__name__.lower() for op in ["delete", "remove"]):
                operation_type = "delete"

            # Apply appropriate validation
            validated_func = validate_database_write(operation_type)(func)
            return validated_func(*args, **kwargs)

        except ValidationError:
            # Re-raise validation errors
            raise
        except Exception as e:
            log.error(f"Safe database operation {func.__name__} failed: {e}")
            if default_validation_context.raise_on_validation_error:
                raise ValidationError(f"Database operation failed: {str(e)}")
            return None

    # Determine if function is async
    import inspect

    if inspect.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


def validate_state_update(func: F) -> F:
    """
    Decorator for state update operations with comprehensive validation.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Log state update for audit trail
        log.debug(f"State update operation: {func.__name__}")

        try:
            # Apply validation based on function context
            function_name = func.__name__.lower()

            if "order" in function_name:
                return validate_order_data(func)(*args, **kwargs)
            elif "position" in function_name:
                return validate_position_data(func)(*args, **kwargs)
            elif "trade" in function_name:
                return validate_trade_data(func)(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        except ValidationError as e:
            log.error(f"State update validation failed for {func.__name__}: {e}")
            if default_validation_context.raise_on_validation_error:
                raise
            return None
        except Exception as e:
            log.error(f"State update {func.__name__} failed: {e}")
            if default_validation_context.strict_mode:
                raise ValidationError(f"State update failed: {str(e)}")
            raise

    return wrapper


class ValidationBatch:
    """Utility class for batch validation operations."""

    def __init__(self, model_class: type[BaseModel]):
        self.model_class = model_class
        self.errors: list[dict[str, Any]] = []
        self.valid_items: list[dict[str, Any]] = []

    def validate_item(self, item: dict[str, Any], item_id: str = None) -> bool:
        """
        Validate a single item and add to appropriate list.

        Args:
            item: Item to validate
            item_id: Optional identifier for the item

        Returns:
            True if validation passed, False otherwise
        """
        try:
            validated = self.model_class(**item)
            self.valid_items.append(validated.model_dump())
            return True
        except PydanticValidationError as e:
            self.errors.append(
                {
                    "item_id": item_id,
                    "item": item,
                    "error": str(e),
                    "validation_errors": e.errors(),
                }
            )
            return False

    def validate_batch(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Validate a batch of items.

        Args:
            items: List of items to validate

        Returns:
            Dictionary with validation results
        """
        self.errors.clear()
        self.valid_items.clear()

        for i, item in enumerate(items):
            self.validate_item(item, str(i))

        return {
            "total_items": len(items),
            "valid_items": len(self.valid_items),
            "error_count": len(self.errors),
            "success_rate": len(self.valid_items) / len(items) if items else 0,
            "errors": self.errors,
            "valid_data": self.valid_items,
        }

    def get_summary(self) -> str:
        """Get validation summary as a string."""
        total = len(self.valid_items) + len(self.errors)
        if total == 0:
            return "No items validated"

        success_rate = len(self.valid_items) / total * 100
        return (
            f"Validated {total} items: {len(self.valid_items)} valid "
            f"({success_rate:.1f}%), {len(self.errors)} errors"
        )


def batch_validate(model_class: type[BaseModel]):
    """
    Decorator for batch validation operations.

    Args:
        model_class: Pydantic model class to validate against
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Look for list parameters to validate
            for key, value in kwargs.items():
                if isinstance(value, list) and all(
                    isinstance(item, dict) for item in value
                ):
                    batch_validator = ValidationBatch(model_class)
                    results = batch_validator.validate_batch(value)

                    if (
                        default_validation_context.log_validation_errors
                        and results["error_count"] > 0
                    ):
                        log.warning(
                            f"Batch validation in {func.__name__}: {batch_validator.get_summary()}"
                        )

                    # Replace with validated data
                    kwargs[key] = results["valid_data"]

                    # Store validation results for access
                    kwargs[f"{key}_validation_results"] = results

            return func(*args, **kwargs)

        return wrapper

    return decorator


# Configuration functions
def set_validation_context(
    strict_mode: bool = None,
    log_validation_errors: bool = None,
    raise_on_validation_error: bool = None,
    validation_timeout: float = None,
):
    """Update global validation context settings."""
    global default_validation_context

    if strict_mode is not None:
        default_validation_context.strict_mode = strict_mode
    if log_validation_errors is not None:
        default_validation_context.log_validation_errors = log_validation_errors
    if raise_on_validation_error is not None:
        default_validation_context.raise_on_validation_error = raise_on_validation_error
    if validation_timeout is not None:
        default_validation_context.validation_timeout = validation_timeout


def get_validation_context() -> ValidationContext:
    """Get current validation context."""
    return default_validation_context


# Export decorators and utilities
__all__ = [
    "validate_input",
    "validate_output",
    "validate_order_data",
    "validate_position_data",
    "validate_trade_data",
    "validate_database_write",
    "safe_database_operation",
    "validate_state_update",
    "batch_validate",
    "ValidationBatch",
    "ValidationContext",
    "set_validation_context",
    "get_validation_context",
    "default_validation_context",
]
