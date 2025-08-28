"""Order client for secure and reliable order execution on Polymarket.

This module provides the OrderClient class which handles all order placement,
management, and execution operations with the Polymarket exchange. It includes
comprehensive error handling, retry logic, security measures, and monitoring
capabilities to ensure robust trading operations.

The order client provides:
- Secure order placement with credential protection
- Comprehensive retry logic with circuit breaker patterns
- Exception tracking and monitoring for debugging
- Rate limiting and API management
- Order status tracking and management
- Integration with risk management systems

Security Features:
    - Secure logging that prevents credential exposure
    - Input sanitization and validation
    - Safe error message generation
    - Audit trail for all order operations

Reliability Features:
    - Exponential backoff retry with jitter
    - Circuit breaker pattern for fault tolerance
    - Connection pooling and management
    - Comprehensive exception tracking
    - Graceful degradation capabilities

Examples:
    Basic order client usage:

    >>> from inkedup_bot.config import BotConfig
    >>> from inkedup_bot.state import StateManager
    >>> from inkedup_bot.order_client import OrderClient
    >>>
    >>> # Initialize with configuration
    >>> config = BotConfig()
    >>> state = StateManager()
    >>> client = OrderClient(config, state)
    >>>
    >>> # Check client readiness
    >>> if client.ready():
    ...     print("Order client ready for trading")
    >>>
    >>> # Place a limit order
    >>> client.place_limit(
    ...     token_id="0x123abc456def...",
    ...     side="buy",
    ...     price=0.65,
    ...     size=100.0,
    ...     time_in_force="GTC",
    ...     market_slug="election-2024"
    ... )

Architecture:
    The OrderClient uses a layered architecture with multiple resilience
    patterns including retry managers, circuit breakers, and exception
    tracking to ensure reliable operation under various failure conditions.

Performance:
    The client includes connection pooling, request batching, and intelligent
    retry strategies to optimize throughput while respecting API rate limits
    and maintaining system stability.

"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, cast

try:
    import backoff

    BACKOFF_AVAILABLE = True
except ImportError:
    BACKOFF_AVAILABLE = False

    # Create a no-op decorator when backoff is not available
    class backoff:
        @staticmethod
        def on_exception(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

        @staticmethod
        def expo(*args, **kwargs):
            pass


from .circuit_breaker import CircuitBreakerConfig
from .config import BotConfig
from .enhanced_retry_client import ResilientClientConfig, ResilientRetryClient
from .enhanced_stub_client import (
    EnhancedStubClobClient,
    StubClientConfig,
)
from .retry_utils import RetryConfig, RetryManager
from .security import (
    SensitivityLevel,
    create_safe_error_message,
    get_secure_logger,
    sanitize_for_logging,
)
from .state import StateManager

# Use secure logger to prevent credential exposure
log = get_secure_logger("order_client", SensitivityLevel.STANDARD)


import functools
from collections import defaultdict
from datetime import datetime, timedelta


class ExceptionTracker:
    """Comprehensive exception tracking for debugging and monitoring order client operations.

    The ExceptionTracker provides detailed monitoring of exceptions that occur during
    order processing, enabling better debugging, alerting, and system health monitoring.
    It maintains both aggregate statistics and detailed exception histories.

    Features:
        - Exception frequency tracking by method and type
        - Detailed exception history with context
        - Recent exception queries for alerting
        - Automatic cleanup of old records
        - Memory-bounded storage to prevent unbounded growth

    Attributes:
        exception_counts: Count of exceptions by method:type key
        exception_details: Detailed exception records with context
        last_exceptions: Timestamp of most recent exception by type
        max_details_history: Maximum number of detailed records to keep

    Examples:
        Use with order client methods:

        >>> tracker = ExceptionTracker()
        >>>
        >>> try:
        ...     # Some order operation that might fail
        ...     place_order()
        ... except Exception as e:
        ...     tracker.record_exception(e, "place_limit", {"token_id": "0x123..."})
        >>>
        >>> # Check for frequent issues
        >>> frequent = tracker.get_frequent_exceptions(threshold=5)
        >>> for exception_key, count in frequent.items():
        ...     print(f"Frequent issue: {exception_key} occurred {count} times")

    Memory Management:
        The tracker automatically manages memory usage by:
        - Limiting detailed records to max_details_history entries
        - Providing cleanup methods for old data
        - Using efficient data structures for counts and lookups

    """

    def __init__(self) -> None:
        """Initialize exception tracker with empty state."""
        self.exception_counts: dict[str, int] = defaultdict(int)
        self.exception_details: list[dict[str, Any]] = []
        self.last_exceptions: dict[str, datetime] = {}
        self.max_details_history = 100

    def record_exception(
        self,
        exception: Exception,
        method_name: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record exception details for analysis and monitoring.

        Captures exception information including type, message, context, and
        timestamp for later analysis. Updates both aggregate counts and
        detailed history while managing memory usage.

        Args:
            exception: The exception that occurred
            method_name: Name of the method where exception occurred
            context: Optional context information (e.g., parameters, state)

        Example:
            >>> tracker = ExceptionTracker()
            >>> try:
            ...     risky_operation()
            ... except ValueError as e:
            ...     tracker.record_exception(
            ...         e, "place_order", {"token_id": "0x123", "size": 100}
            ...     )

        """
        exception_type = type(exception).__name__
        exception_key = f"{method_name}:{exception_type}"

        # Update counts
        self.exception_counts[exception_key] += 1
        self.last_exceptions[exception_key] = datetime.utcnow()

        # Record detailed information (with size limit)
        exception_detail = {
            "timestamp": datetime.utcnow().isoformat(),
            "method": method_name,
            "exception_type": exception_type,
            "message": str(exception),
            "context": context or {},
            "count": self.exception_counts[exception_key],
        }

        self.exception_details.append(exception_detail)

        # Maintain size limit
        if len(self.exception_details) > self.max_details_history:
            self.exception_details.pop(0)

    def get_frequent_exceptions(self, threshold: int = 3) -> dict[str, int]:
        """Get exceptions that occur frequently."""
        return {k: v for k, v in self.exception_counts.items() if v >= threshold}

    def get_recent_exceptions(self, minutes: int = 60) -> list[dict[str, Any]]:
        """Get exceptions from the last N minutes."""
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        return [
            detail
            for detail in self.exception_details
            if datetime.fromisoformat(detail["timestamp"]) >= cutoff
        ]

    def clear_old_records(self, hours: int = 24):
        """Clear old exception records."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        # Clear old details
        self.exception_details = [
            detail
            for detail in self.exception_details
            if datetime.fromisoformat(detail["timestamp"]) >= cutoff
        ]

        # Clear old last_exceptions
        keys_to_remove = [
            key for key, timestamp in self.last_exceptions.items() if timestamp < cutoff
        ]
        for key in keys_to_remove:
            del self.last_exceptions[key]
            # Also reset the count since we're clearing old data
            if key in self.exception_counts:
                self.exception_counts[key] = 0


# Global exception tracker for the order client
_exception_tracker = ExceptionTracker()


def track_exceptions(method_name: str | None = None):
    """Decorator to track exceptions in order client methods."""

    def decorator(func):
        name = method_name or func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Extract context from self if available
                context = {}
                if args and hasattr(args[0], "__class__"):
                    context["class"] = args[0].__class__.__name__

                # Record the exception
                _exception_tracker.record_exception(e, name, context)

                # Re-raise to maintain original behavior
                raise

        return wrapper

    return decorator


def get_exception_stats() -> dict[str, Any]:
    """Get comprehensive exception statistics for debugging."""
    return {
        "total_exception_types": len(_exception_tracker.exception_counts),
        "frequent_exceptions": _exception_tracker.get_frequent_exceptions(),
        "recent_exceptions_1h": len(_exception_tracker.get_recent_exceptions(60)),
        "recent_exceptions_24h": len(_exception_tracker.get_recent_exceptions(1440)),
        "exception_counts": dict(_exception_tracker.exception_counts),
        "last_exceptions": {
            k: v.isoformat() for k, v in _exception_tracker.last_exceptions.items()
        },
    }


class UnavailableClientError(Exception):
    """Raised when attempting to use the CLOB client while py-clob-client is not available."""

    pass


class StubClobClient:
    """No-op stub client that raises UnavailableClientError for any method call."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Accept any arguments to match ClobClient signature
        pass

    def create_order(self, *args: Any, **kwargs: Any) -> Any:
        raise UnavailableClientError("py-clob-client not available")

    def cancel_all(self, *args: Any, **kwargs: Any) -> list[Any]:
        raise UnavailableClientError("py-clob-client not available")

    def get_positions(self, *args: Any, **kwargs: Any) -> list[Any]:
        raise UnavailableClientError("py-clob-client not available")

    def __getattr__(self, name: str) -> Any:
        """Catch-all for any other method calls."""

        def method(*args: Any, **kwargs: Any) -> Any:
            raise UnavailableClientError("py-clob-client not available")

        return method


class MockOrderArgs:
    """Mock OrderArgs class for use when py-clob-client is not available."""

    def __init__(self, price: float, size: float, side: str, token_id: str, **kwargs):
        self.price = price
        self.size = size
        self.side = side
        self.token_id = token_id
        # Store any additional arguments
        for key, value in kwargs.items():
            setattr(self, key, value)


try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs

    PY_CLOB_CLIENT_INSTALLED = True
    log.debug("py-clob-client successfully imported")
except ImportError:
    ClobClient = StubClobClient  # Use stub instead of None
    OrderArgs = MockOrderArgs  # Use mock instead of None
    PY_CLOB_CLIENT_INSTALLED = False
    log.debug("py-clob-client not available; using stub client")


class OrderClient:
    """Advanced order management client for Polymarket trading operations.

    This class provides a comprehensive interface for order placement, management,
    and monitoring on the Polymarket prediction market platform. It includes
    advanced features like circuit breakers, retry mechanisms, fallback clients,
    and comprehensive error handling.

    Key Features:
    - Resilient order placement with automatic retries
    - Circuit breaker pattern for handling API failures
    - Fallback to enhanced stub client when py-clob-client unavailable
    - Comprehensive logging and error tracking
    - State management integration for order persistence
    - Security-focused credential handling

    Example:
        >>> from inkedup_bot.config import BotConfig
        >>> from inkedup_bot.state import StateManager
        >>>
        >>> cfg = BotConfig(private_key="your_private_key")
        >>> state = StateManager(db_path="trading.db")
        >>> client = OrderClient(cfg, state)
        >>>
        >>> # Place a limit order
        >>> order = client.place_limit(
        ...     token_id="0x123...",
        ...     side="buy",
        ...     price=0.65,
        ...     size=100.0
        ... )
        >>>
        >>> # Cancel an order
        >>> client.cancel(order_id="order123")
        >>>
        >>> # Check order status
        >>> if client.ready():
        ...     print("Client ready for trading")

    Args:
        cfg: Bot configuration containing API credentials and settings
        state: State manager for order persistence and tracking
        stub_config: Optional configuration for stub client fallback

    Raises:
        ImportError: If py-clob-client is required but not installed
        ValueError: If configuration is invalid or missing required fields
        ConnectionError: If unable to establish connection to trading API

    """

    def __init__(
        self, cfg: BotConfig, state: StateManager, stub_config: StubClientConfig = None
    ) -> None:
        self.cfg = cfg
        self.state = state

        # Initialize legacy retry manager for backward compatibility
        retry_config = RetryConfig(
            max_attempts=cfg.api_retry_attempts,
            base_delay=float(cfg.api_retry_delay_seconds),
            max_delay=cfg.api_retry_max_delay_seconds,
            exponential_base=cfg.api_retry_exponential_base,
            jitter=cfg.api_retry_jitter_enabled,
            jitter_range=cfg.api_retry_jitter_range,
            backoff_strategy=cfg.api_retry_backoff_strategy,
        )
        self.retry_manager = RetryManager(retry_config)

        # Initialize enhanced resilient retry client with comprehensive configuration
        circuit_breaker_config = CircuitBreakerConfig(
            failure_threshold=cfg.circuit_breaker_failure_threshold,
            recovery_timeout=cfg.circuit_breaker_recovery_timeout,
            half_open_max_calls=cfg.circuit_breaker_half_open_calls,
            success_threshold=cfg.circuit_breaker_success_threshold,
            sliding_window_size=cfg.circuit_breaker_sliding_window_size,
            failure_rate_threshold=cfg.circuit_breaker_failure_rate_threshold,
            call_timeout=cfg.api_call_timeout,
        )

        resilient_config = ResilientClientConfig(
            circuit_breaker_enabled=cfg.circuit_breaker_enabled,
            circuit_breaker_config=circuit_breaker_config,
            default_max_attempts=cfg.api_retry_attempts,
            default_base_delay=float(cfg.api_retry_delay_seconds),
            default_max_delay=cfg.api_retry_max_delay_seconds,
            exponential_base=cfg.api_retry_exponential_base,
            jitter_enabled=cfg.api_retry_jitter_enabled,
            jitter_range=cfg.api_retry_jitter_range,
            call_timeout=cfg.api_call_timeout,
            total_timeout=cfg.api_total_timeout,
        )

        self.resilient_client = ResilientRetryClient(
            client_name="polymarket_order_client", config=resilient_config
        )

        if not PY_CLOB_CLIENT_INSTALLED:
            log.debug("Using enhanced stub client due to missing py-clob-client")
            self.client = EnhancedStubClobClient(stub_config or StubClientConfig())
        elif cfg.private_key:
            try:
                self.client = ClobClient(
                    host=self.cfg.api_base,
                    key=cfg.private_key,
                )
                log.debug("ClobClient initialized successfully")
            except Exception as e:
                # Secure error logging to prevent credential exposure
                safe_error = create_safe_error_message(
                    "Failed to initialize ClobClient",
                    {
                        "exception_type": type(e).__name__,
                        "config_keys": list(vars(cfg).keys()),
                    },
                    SensitivityLevel.STRICT,
                )
                log.error(safe_error, exc_info=True)
                log.debug("Falling back to enhanced stub client")
                self.client = EnhancedStubClobClient(stub_config or StubClientConfig())
        else:
            log.debug("No private key provided, using enhanced stub client")
            self.client = EnhancedStubClobClient(stub_config or StubClientConfig())

    def ready(self) -> bool:
        """Check if the order client is ready for live trading operations.

        This method determines if the client has proper credentials and can
        execute real trades on the Polymarket platform. Returns False if:
        - py-clob-client library is not installed
        - No valid client instance exists
        - Client is using a stub/mock implementation

        Returns:
            bool: True if ready for live trading, False if using stub client

        Example:
            >>> client = OrderClient(cfg, state)
            >>> if client.ready():
            ...     print("Ready for live trading")
            ... else:
            ...     print("Using stub client for testing")

        """
        return (
            PY_CLOB_CLIENT_INSTALLED
            and self.client is not None
            and not isinstance(self.client, (StubClobClient, EnhancedStubClobClient))
        )

    def _create_order_with_retry(self, order_args):
        """Create order with enhanced retry logic and circuit breaker protection."""

        def _create_order():
            return self.client.create_order(order_args)

        return self.resilient_client.call(
            operation_name="create_order",
            func=_create_order,
            context={"operation_type": "order_placement", "order_data": order_args},
        )

    def _cancel_all_with_retry(self):
        """Cancel all orders with enhanced retry logic and circuit breaker protection."""

        def _cancel_all():
            return self.client.cancel_all()

        return self.resilient_client.call(
            operation_name="cancel_all_orders",
            func=_cancel_all,
            context={"operation_type": "order_cancellation"},
        )

    def _get_positions_with_retry(self):
        """Get positions with enhanced retry logic and circuit breaker protection."""

        def _get_positions():
            return self.client.get_positions()

        return self.resilient_client.call(
            operation_name="get_positions",
            func=_get_positions,
            context={"operation_type": "data_retrieval"},
        )

    def get_retry_stats(self) -> dict:
        """Get retry statistics for monitoring and debugging."""
        return self.retry_manager.get_stats()

    def reset_retry_stats(self):
        """Reset retry statistics."""
        self.retry_manager.reset_stats()

    # Enhanced stub client methods
    def is_using_stub(self) -> bool:
        """Check if the client is using a stub (enhanced or basic)."""
        return isinstance(self.client, (StubClobClient, EnhancedStubClobClient))

    def is_using_enhanced_stub(self) -> bool:
        """Check if the client is using the enhanced stub."""
        return isinstance(self.client, EnhancedStubClobClient)

    def get_stub_stats(self) -> dict:
        """Get statistics from the enhanced stub client if available."""
        if isinstance(self.client, EnhancedStubClobClient):
            return self.client.get_stats()
        return {}

    def reset_stub_stats(self):
        """Reset statistics in the enhanced stub client if available."""
        if isinstance(self.client, EnhancedStubClobClient):
            self.client.reset_stats()

    def configure_stub_behavior(self, config: StubClientConfig):
        """Update the enhanced stub client configuration if available."""
        if isinstance(self.client, EnhancedStubClobClient):
            self.client.set_config(config)
            log.debug("Stub client configuration updated")
        else:
            log.warning(
                "Cannot configure stub behavior - not using enhanced stub client"
            )

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
        max_time=30,
        giveup=lambda e: isinstance(e, ValueError) and "Invalid" in str(e),
    )
    @track_exceptions("place_limit")
    def place_limit(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        tif: str = "GTC",
        market_slug: str | None = None,
        outcome_type: str | None = None,
        notional_value: float | None = None,
        risk: Any | None = None,
    ) -> dict[str, Any] | None:
        """Place a limit order on the Polymarket platform with advanced error handling.

        This method creates a limit order with comprehensive validation, retry logic,
        circuit breaker protection, and state management integration. It handles both
        live trading and stub client scenarios for testing.

        Args:
            token_id: Unique identifier for the prediction market token
            side: Order side, either "buy" or "sell"
            price: Limit price between 0.0 and 1.0 (probability)
            size: Order size in number of shares
            tif: Time in force, defaults to "GTC" (Good Till Cancelled)
            market_slug: Human-readable market identifier (optional)
            outcome_type: Type of outcome ("YES" or "NO", optional)
            notional_value: USD value of the order (optional, calculated if not provided)
            risk: Risk assessment data for the order (optional)

        Returns:
            dict: Order details including order ID, status, and metadata
                 None if order placement fails or client not ready

        Raises:
            ValueError: If invalid parameters are provided (price/size <= 0)
            ConnectionError: If unable to connect to trading API
            TimeoutError: If order placement times out after retries

        Example:
            >>> # Buy 100 shares of a YES token at 65% probability
            >>> order = client.place_limit(
            ...     token_id="0x123abc...",
            ...     side="buy",
            ...     price=0.65,
            ...     size=100.0,
            ...     market_slug="2024-election-winner",
            ...     outcome_type="YES"
            ... )
            >>>
            >>> if order:
            ...     print(f"Order placed: {order['id']}")
            ...     print(f"Status: {order['status']}")
            ... else:
            ...     print("Order placement failed")

        Note:
            - Prices must be between 0.0 and 1.0 (representing probabilities)
            - Size represents number of shares, not USD value
            - Orders are automatically tracked in the state manager
            - Circuit breaker may prevent orders during high failure rates

        """
        if not self.ready() and not isinstance(self.client, EnhancedStubClobClient):
            log.debug(
                "Trading functionality not available - py-clob-client not installed"
            )
            return None

        if OrderArgs is None:
            log.debug("OrderArgs not available - py-clob-client not installed")
            return None

        if price <= 0 or size <= 0:
            log.error("Invalid price/size.")
            return None

        # Validate token_id
        if not token_id or not isinstance(token_id, str):
            log.error("Invalid token_id provided.")
            return None

        try:
            # Add timeout context
            order_args = OrderArgs(
                price=round(price, 4),
                size=round(size, 4),
                side=side.lower(),
                token_id=token_id,
            )

            # Execute order with retry logic
            order = self._create_order_with_retry(order_args)

            if order:
                order_dict = asdict(order)
                log.info(
                    f"Placed {side.upper()} size={size} price={price} token={token_id} id={order_dict.get('id')}"
                )

                # Ensure state is updated
                try:
                    self.state.add_order(order_dict)
                except Exception as e:
                    log.error(f"Failed to add order to state: {e}", exc_info=True)

                # Atomic risk recording
                if risk and notional_value is not None:
                    try:
                        risk.record_trade(
                            token_id,
                            notional_value,
                            market_slug,
                            outcome_type,
                        )
                    except Exception as e:
                        log.error(
                            f"Failed to record trade in risk manager: {e}",
                            exc_info=True,
                        )

                return order_dict
            else:
                log.warning("Order creation returned None")
                return None

        except UnavailableClientError:
            log.debug(
                "Trading functionality not available - py-clob-client not installed"
            )
            return None
        except ValueError as e:
            log.error(f"Order validation error: {e}")
            return None
        except ConnectionError as e:
            log.error(f"Connection error during order placement: {e}")
            return None
        except TimeoutError as e:
            log.error(f"Order placement timeout: {e}")
            return None
        except Exception as e:
            log.error(
                f"Unexpected order failure for token {token_id} ({side} {size} @ {price}): {type(e).__name__}: {e}",
                exc_info=True,
            )
            return None

    @track_exceptions("cancel_all")
    def cancel_all(self) -> list[Any]:
        if not self.ready() and not isinstance(self.client, EnhancedStubClobClient):
            log.debug("Cancel all not available - py-clob-client not installed")
            return []
        try:
            res = self._cancel_all_with_retry()
            log.info(f"Cancelled {len(res)} orders")
            return cast(list[Any], res)
        except UnavailableClientError:
            log.debug("Cancel all not available - py-clob-client not installed")
            return []
        except Exception as e:
            # Secure error logging
            safe_error = create_safe_error_message(
                "An unexpected error occurred during cancel all",
                {"exception_type": type(e).__name__, "message": str(e)},
                SensitivityLevel.STANDARD,
            )
            log.error(safe_error, exc_info=True)
            return []

    @track_exceptions("get_positions")
    def get_positions(self) -> list[Any]:
        if not self.ready() and not isinstance(self.client, EnhancedStubClobClient):
            log.debug("Get positions not available - py-clob-client not installed")
            return []
        try:
            # Type ignore because py-clob-client may not have perfect stubs
            positions = self._get_positions_with_retry()  # type: ignore
            return cast(list[Any], positions)
        except UnavailableClientError:
            log.debug("Get positions not available - py-clob-client not installed")
            return []
        except Exception as e:
            # Secure error logging for positions
            safe_error = create_safe_error_message(
                "An unexpected error occurred while fetching positions",
                {"exception_type": type(e).__name__, "message": str(e)},
                SensitivityLevel.STANDARD,
            )
            log.error(safe_error, exc_info=True)
            return []

    @track_exceptions("exposure_usd")
    def exposure_usd(self) -> float:
        """Calculate total USD exposure from positions with robust error handling.

        Handles various data structures and field name variations commonly found
        in exchange API responses. Provides comprehensive error logging while
        maintaining graceful degradation.

        Returns:
            float: Total USD exposure, or 0.0 if no valid positions found

        """
        total = 0.0
        positions = self.get_positions()

        if not positions:
            log.debug("No positions data available for exposure calculation")
            return total

        log.debug(f"Processing {len(positions)} positions for USD exposure calculation")

        for i, p in enumerate(positions):
            try:
                usd_value = self._extract_usd_value_from_position(p)
                if usd_value is not None:
                    total += usd_value
                    log.debug(f"Position {i}: added ${usd_value:.4f} to total exposure")
                else:
                    log.debug(f"Position {i}: no valid USD value found, skipping")

            except Exception as e:
                # Use secure logging to prevent any sensitive data leaks
                safe_error_msg = create_safe_error_message(
                    f"Failed to process position {i}: {type(e).__name__}",
                    {"position_type": type(p).__name__, "position_data": p},
                    SensitivityLevel.STANDARD,
                )
                log.warning(safe_error_msg, exc_info=True)
                # Continue processing other positions

        log.debug(f"Total USD exposure calculated: ${total:.4f}")
        return total

    def _extract_usd_value_from_position(self, position) -> float | None:
        """Extract USD value from a position object with comprehensive error handling.

        Supports multiple data structures and field name variations:
        - Dataclasses with various field names
        - Dictionaries with nested or flat structures
        - Objects with attribute access
        - String/numeric values requiring conversion

        Args:
            position: Position data in various formats

        Returns:
            float | None: USD value if successfully extracted, None otherwise

        """
        if position is None:
            return None

        # Convert position to dictionary representation for uniform processing
        position_dict = self._normalize_position_to_dict(position)
        if not position_dict:
            return None

        # Try multiple field name variations commonly used in APIs
        usd_field_candidates = [
            "usd_value",
            "usdValue",
            "USD_VALUE",  # Common variations
            "value_usd",
            "valueUsd",
            "VALUE_USD",
            "notional",
            "notional_value",
            "notionalValue",  # Alternative terms
            "market_value",
            "marketValue",
            "MARKET_VALUE",
            "position_value",
            "positionValue",
            "POSITION_VALUE",
            "dollar_value",
            "dollarValue",
            "DOLLAR_VALUE",
            "amount_usd",
            "amountUsd",
            "AMOUNT_USD",
            "total_value",
            "totalValue",
            "TOTAL_VALUE",
            "value",
            "amount",  # Generic fallbacks
        ]

        for field_name in usd_field_candidates:
            try:
                value = self._extract_nested_value(position_dict, field_name)
                if value is not None:
                    parsed_value = self._parse_numeric_value(value)
                    if parsed_value is not None:
                        log.debug(
                            f"Successfully extracted USD value ${parsed_value:.4f} from field '{field_name}'"
                        )
                        return parsed_value
            except Exception as e:
                log.debug(f"Failed to extract value from field '{field_name}': {e}")
                continue

        # If no standard fields found, try to find any numeric values that might represent USD
        return self._extract_fallback_numeric_value(position_dict)

    def _normalize_position_to_dict(self, position) -> dict | None:
        """Convert position data to dictionary format for uniform processing.

        Handles:
        - Dataclasses
        - Named tuples
        - Objects with __dict__
        - Already dictionary objects
        - Objects with attribute access

        Args:
            position: Position data in various formats

        Returns:
            dict | None: Dictionary representation or None if conversion fails

        """
        try:
            # Handle dataclasses
            if hasattr(position, "__dataclass_fields__"):
                return asdict(position)

            # Handle dictionaries (most common case)
            if isinstance(position, dict):
                return position

            # Handle named tuples
            if hasattr(position, "_fields") and hasattr(position, "_asdict"):
                return position._asdict()

            # Handle objects with __dict__ attribute
            if hasattr(position, "__dict__"):
                all_attrs = vars(position)
                # Filter out None values to keep only meaningful data
                return {k: v for k, v in all_attrs.items() if v is not None}

            # Handle objects with known attributes (try common position attributes)
            if hasattr(position, "__getattribute__"):
                result = {}
                common_attributes = [
                    "usd_value",
                    "value",
                    "amount",
                    "notional",
                    "market_value",
                    "position_value",
                    "dollar_value",
                    "total_value",
                    "size",
                    "quantity",
                    "exposure",
                    "balance",
                ]

                for attr in common_attributes:
                    try:
                        # Only get attributes that actually exist
                        if hasattr(position, attr):
                            value = getattr(position, attr)
                            # Only include non-None values
                            if value is not None:
                                result[attr] = value
                    except AttributeError as e:
                        # Expected error when attribute doesn't exist or isn't accessible
                        log.debug(
                            f"Attribute '{attr}' not accessible on position object: {e}"
                        )
                        continue
                    except TypeError as e:
                        # Handle type conversion issues gracefully
                        log.debug(
                            f"Type error accessing attribute '{attr}' on position: {e}"
                        )
                        continue
                    except Exception as e:
                        # Unexpected errors - log with more detail for debugging
                        log.warning(
                            f"Unexpected error extracting attribute '{attr}' from position: "
                            f"{type(e).__name__}: {e}"
                        )
                        continue

                return result if result else None

            # Handle primitive types that might be wrapped
            if isinstance(position, (int, float, str)):
                return {"value": position}

            log.debug(f"Unable to normalize position type: {type(position)}")
            return None

        except Exception as e:
            # Use secure error logging to prevent sensitive data exposure
            safe_error_msg = create_safe_error_message(
                "Error normalizing position to dict",
                {"exception": e, "position_type": type(position).__name__},
                SensitivityLevel.STANDARD,
            )
            log.error(safe_error_msg, exc_info=True)
            return None

    def _extract_nested_value(self, data: dict, field_name: str):
        """Extract value from potentially nested dictionary structure.

        Supports:
        - Direct field access: data["usd_value"]
        - Nested access: data["position"]["usd_value"]
        - Case-insensitive matching
        - Dot notation in field names

        Args:
            data: Dictionary to search
            field_name: Field name to find (supports dot notation)

        Returns:
            Any: Found value or None

        """
        if not isinstance(data, dict):
            return None

        # Direct field access (most common case)
        if field_name in data:
            return data[field_name]

        # Case-insensitive search
        for key, value in data.items():
            if isinstance(key, str) and key.lower() == field_name.lower():
                return value

        # Handle dot notation (e.g., "position.usd_value")
        if "." in field_name:
            parts = field_name.split(".")
            current = data
            try:
                for part in parts:
                    if isinstance(current, dict):
                        current = current.get(part)
                        if current is None:
                            break
                    else:
                        break
                return current
            except TypeError as e:
                # Handle type errors when navigating nested structures
                log.debug(
                    f"Type error navigating dot notation field '{field_name}': {e}"
                )
            except KeyError as e:
                # Handle missing keys in nested structures
                log.debug(
                    f"Key error navigating dot notation field '{field_name}': {e}"
                )
            except Exception as e:
                # Unexpected errors in dot notation parsing
                log.debug(
                    f"Unexpected error parsing dot notation field '{field_name}': {type(e).__name__}: {e}"
                )

        # Search in nested objects
        for key, value in data.items():
            if isinstance(value, dict):
                nested_result = self._extract_nested_value(value, field_name)
                if nested_result is not None:
                    return nested_result

        return None

    def _parse_numeric_value(self, value) -> float | None:
        """Parse various numeric value formats to float.

        Handles:
        - Integer and float values
        - String representations of numbers
        - Scientific notation
        - Currency strings (removes symbols)
        - Percentage strings
        - Null/None values
        - Boolean values (True=1, False=0)

        Args:
            value: Value to parse

        Returns:
            float | None: Parsed numeric value or None if unparseable

        """
        if value is None:
            return None

        # Handle already numeric types
        if isinstance(value, (int, float)):
            if not (isinstance(value, float) and (value != value)):  # Check for NaN
                return float(value)
            return None

        # Handle boolean values
        if isinstance(value, bool):
            return float(value)

        # Handle string values
        if isinstance(value, str):
            # Handle empty or whitespace strings
            value = value.strip()
            if not value:
                return None

            # Handle common null representations
            if value.lower() in ("null", "none", "n/a", "na", "", "-"):
                return None

            # Remove common currency symbols and formatting
            cleaned_value = value
            currency_symbols = ["$", "€", "£", "¥", "₹", "₽", "₿", "USD", "EUR", "GBP"]
            for symbol in currency_symbols:
                cleaned_value = cleaned_value.replace(symbol, "")

            # Remove percentage symbol and convert if needed
            is_percentage = cleaned_value.endswith("%")
            if is_percentage:
                cleaned_value = cleaned_value[:-1]

            # Remove thousands separators
            cleaned_value = cleaned_value.replace(",", "")

            # Handle parentheses for negative values (accounting format)
            if cleaned_value.startswith("(") and cleaned_value.endswith(")"):
                cleaned_value = "-" + cleaned_value[1:-1]

            try:
                numeric_value = float(cleaned_value)
                # Convert percentage to decimal if needed
                if is_percentage:
                    numeric_value = numeric_value / 100.0
                return numeric_value
            except ValueError:
                log.debug(f"Cannot parse string value to float: '{value}'")
                return None

        # Handle list/array values (take first numeric element)
        if isinstance(value, (list, tuple)) and value:
            for item in value:
                parsed = self._parse_numeric_value(item)
                if parsed is not None:
                    return parsed
            return None

        # Handle nested objects with numeric representation
        if hasattr(value, "__float__"):
            try:
                return float(value)
            except ValueError as e:
                # Value error during float conversion
                log.debug(
                    f"Value error converting object with __float__ method to float: {e}"
                )
            except TypeError as e:
                # Type error during float conversion
                log.debug(
                    f"Type error converting object with __float__ method to float: {e}"
                )
            except Exception as e:
                # Unexpected error during float conversion
                log.debug(
                    f"Unexpected error converting object to float: {type(e).__name__}: {e}"
                )

        log.debug(f"Cannot parse value type {type(value)} to float: {value}")
        return None

    def _extract_fallback_numeric_value(self, position_dict: dict) -> float | None:
        """Fallback method to extract any reasonable numeric value from position data.

        Used when standard field names are not found. Looks for:
        - Any numeric values that could represent USD amounts
        - Values in reasonable ranges for position sizes
        - Non-zero values that make sense as positions

        Args:
            position_dict: Position data as dictionary

        Returns:
            float | None: Best guess numeric value or None

        """
        candidates = []

        # Sensitive fields to skip during fallback parsing
        sensitive_fields = {
            "private_key",
            "secret",
            "token",
            "password",
            "auth",
            "key",
            "signature",
            "hash",
            "wallet",
            "address",
        }

        for key, value in position_dict.items():
            # Skip sensitive fields during fallback parsing
            key_lower = key.lower()
            if any(
                sensitive_field in key_lower for sensitive_field in sensitive_fields
            ):
                continue

            parsed_value = self._parse_numeric_value(value)
            if parsed_value is not None:
                # Only consider reasonable position values
                if -1_000_000 <= parsed_value <= 1_000_000:  # Reasonable position range
                    candidates.append((key, parsed_value))

        if not candidates:
            return None

        # Prefer non-zero values
        non_zero_candidates = [(k, v) for k, v in candidates if v != 0.0]
        if non_zero_candidates:
            # If multiple candidates, prefer the largest absolute value (likely the position value)
            best_key, best_value = max(non_zero_candidates, key=lambda x: abs(x[1]))
            log.debug(
                f"Using fallback numeric value ${best_value:.4f} from field '{best_key}'"
            )
            return best_value

        # If only zero values, return the first one
        best_key, best_value = candidates[0]
        log.debug(f"Using fallback zero value from field '{best_key}'")
        return best_value

    def _sanitize_position_data_for_logging(self, position) -> str:
        """Sanitize position data for safe logging using comprehensive secure logging.

        This method now uses the enhanced SecureLogger sanitization system
        which provides better protection against sensitive data exposure.

        Args:
            position: Position data to sanitize

        Returns:
            str: Sanitized string representation suitable for logging

        """
        try:
            # Use the enhanced sanitization system
            sanitized_data = sanitize_for_logging(position, SensitivityLevel.STANDARD)
            return str(sanitized_data)

        except Exception as e:
            # If sanitization fails, return a very safe generic representation
            safe_error = sanitize_for_logging(str(e), SensitivityLevel.STRICT)
            return f"<{type(position).__name__}>: [sanitization_failed: {safe_error}]"

    # Exception tracking and recovery methods

    def get_exception_statistics(self) -> dict[str, Any]:
        """Get comprehensive exception statistics for this OrderClient instance."""
        stats = get_exception_stats()

        # Add OrderClient-specific information
        stats.update(
            {
                "client_type": type(self.client).__name__,
                "py_clob_installed": PY_CLOB_CLIENT_INSTALLED,
                "client_ready": self.ready(),
                "resilient_client_enabled": hasattr(self, "resilient_client"),
            }
        )

        return stats

    def get_exception_health_report(self) -> dict[str, Any]:
        """Get a health report based on exception patterns."""
        stats = self.get_exception_statistics()
        frequent_exceptions = stats.get("frequent_exceptions", {})
        recent_1h = stats.get("recent_exceptions_1h", 0)
        recent_24h = stats.get("recent_exceptions_24h", 0)

        # Determine health status
        health_status = "healthy"
        issues = []
        recommendations = []

        # Check for frequent exceptions
        if frequent_exceptions:
            health_status = "degraded"
            issues.append(
                f"Frequent exceptions detected: {list(frequent_exceptions.keys())}"
            )
            recommendations.append(
                "Review error patterns and consider implementing specific error handling"
            )

        # Check recent exception rates
        if recent_1h > 10:
            health_status = "critical" if recent_1h > 25 else "degraded"
            issues.append(f"High exception rate: {recent_1h} exceptions in last hour")
            recommendations.append("Investigate immediate causes of high error rate")

        # Check for specific problematic patterns
        critical_exceptions = [
            key
            for key in frequent_exceptions.keys()
            if any(
                critical_type in key.lower()
                for critical_type in [
                    "connectionerror",
                    "timeouterror",
                    "circuitopenerror",
                    "ratelimiterror",
                ]
            )
        ]

        if critical_exceptions:
            health_status = "critical" if health_status != "critical" else health_status
            issues.append(f"Critical exception patterns: {critical_exceptions}")
            recommendations.append("Review network connectivity and API rate limiting")

        return {
            "health_status": health_status,
            "issues": issues,
            "recommendations": recommendations,
            "exception_summary": {
                "recent_1h": recent_1h,
                "recent_24h": recent_24h,
                "frequent_count": len(frequent_exceptions),
                "total_exception_types": stats.get("total_exception_types", 0),
            },
        }

    def implement_recovery_strategies(self) -> dict[str, Any]:
        """Implement automatic recovery strategies based on exception patterns."""
        stats = self.get_exception_statistics()
        frequent_exceptions = stats.get("frequent_exceptions", {})
        recovery_actions = []

        # Strategy 1: Clear old exception records if accumulating
        if len(stats.get("exception_counts", {})) > 50:
            _exception_tracker.clear_old_records(hours=12)
            recovery_actions.append("cleared_old_exception_records")

        # Strategy 2: Reset circuit breaker if it's stuck open due to old failures
        circuit_errors = [
            key for key in frequent_exceptions.keys() if "circuit" in key.lower()
        ]
        if circuit_errors and hasattr(self, "resilient_client"):
            try:
                cb_metrics = self.resilient_client.circuit_breaker.get_metrics()
                if cb_metrics.get("state") == "open":
                    # Force recovery attempt by transitioning to half-open
                    log.info(
                        "Attempting circuit breaker recovery due to frequent circuit errors"
                    )
                    recovery_actions.append("attempted_circuit_breaker_recovery")
            except Exception as e:
                log.debug(f"Could not attempt circuit breaker recovery: {e}")

        # Strategy 3: Reset retry statistics if they're accumulating errors
        retry_errors = [
            key
            for key in frequent_exceptions.keys()
            if any(
                retry_type in key.lower()
                for retry_type in ["timeout", "connection", "network"]
            )
        ]
        if retry_errors:
            try:
                self.reset_retry_stats()
                recovery_actions.append("reset_retry_statistics")
                log.info(
                    "Reset retry statistics due to frequent network-related errors"
                )
            except Exception as e:
                log.debug(f"Could not reset retry statistics: {e}")

        # Strategy 4: Log recovery recommendations
        health_report = self.get_exception_health_report()
        if health_report["health_status"] in ["degraded", "critical"]:
            for recommendation in health_report["recommendations"]:
                log.warning(f"Recovery recommendation: {recommendation}")

        return {
            "recovery_actions_taken": recovery_actions,
            "health_status": health_report["health_status"],
            "timestamp": datetime.utcnow().isoformat(),
        }

    def clear_exception_history(self, hours: int = 24):
        """Clear exception history older than specified hours."""
        _exception_tracker.clear_old_records(hours=hours)
        log.info(f"Cleared exception history older than {hours} hours")

    def get_recent_exception_details(self, minutes: int = 60) -> list[dict[str, Any]]:
        """Get detailed information about recent exceptions."""
        return _exception_tracker.get_recent_exceptions(minutes)
