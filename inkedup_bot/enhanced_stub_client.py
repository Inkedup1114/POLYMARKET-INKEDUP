"""
Enhanced stub client for comprehensive testing of system resilience.

This module provides a sophisticated stub implementation that can simulate
realistic API behavior, error conditions, and response patterns for testing
the OrderClient's error handling and retry mechanisms.
"""

import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4

log = logging.getLogger(__name__)


class ErrorScenario(Enum):
    """Predefined error scenarios for testing."""

    NONE = "none"
    NETWORK_ERROR = "network_error"
    SERVER_ERROR = "server_error"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    INTERMITTENT = "intermittent"
    AUTHENTICATION_ERROR = "authentication_error"
    VALIDATION_ERROR = "validation_error"
    PARTIAL_FAILURE = "partial_failure"
    CASCADING_FAILURE = "cascading_failure"
    MAINTENANCE_MODE = "maintenance_mode"
    CIRCUIT_BREAKER = "circuit_breaker"
    DEGRADED_PERFORMANCE = "degraded_performance"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    MARKET_CLOSED = "market_closed"
    STALE_PRICES = "stale_prices"
    ORDER_REJECTED = "order_rejected"
    DUPLICATE_ORDER = "duplicate_order"


class MarketCondition(Enum):
    """Market condition simulation."""

    NORMAL = "normal"
    HIGH_VOLATILITY = "high_volatility"
    LOW_LIQUIDITY = "low_liquidity"
    MARKET_CLOSED = "market_closed"
    HALTED = "halted"


@dataclass
class MockOrder:
    """Mock order object that mimics real order structure."""

    id: str
    token_id: str
    side: str
    price: float
    size: float
    status: str = "open"
    filled_size: float = 0.0
    timestamp: float = field(default_factory=time.time)
    fee: float = 0.0
    fee_rate: float = 0.002  # 0.2% default fee
    tif: str = "GTC"  # Time in force
    order_type: str = "limit"
    avg_fill_price: float | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for compatibility."""
        return {
            "id": self.id,
            "token_id": self.token_id,
            "side": self.side,
            "price": self.price,
            "size": self.size,
            "status": self.status,
            "filled_size": self.filled_size,
            "timestamp": self.timestamp,
            "fee": self.fee,
            "fee_rate": self.fee_rate,
            "tif": self.tif,
            "order_type": self.order_type,
            "avg_fill_price": self.avg_fill_price,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def __dataclass_fields__(self):
        """Make this compatible with dataclasses.asdict()."""
        return {
            "id": self.id,
            "token_id": self.token_id,
            "side": self.side,
            "price": self.price,
            "size": self.size,
            "status": self.status,
            "filled_size": self.filled_size,
            "timestamp": self.timestamp,
            "fee": self.fee,
            "fee_rate": self.fee_rate,
            "tif": self.tif,
            "order_type": self.order_type,
            "avg_fill_price": self.avg_fill_price,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class MockPosition:
    """Mock position object that mimics real position structure."""

    token_id: str
    market_slug: str
    outcome_type: str
    size: float
    usd_value: float
    avg_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    timestamp: float = field(default_factory=time.time)
    market_price: float | None = None
    last_trade_price: float | None = None
    last_updated: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for compatibility."""
        return {
            "token_id": self.token_id,
            "market_slug": self.market_slug,
            "outcome_type": self.outcome_type,
            "size": self.size,
            "usd_value": self.usd_value,
            "avg_price": self.avg_price,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "timestamp": self.timestamp,
            "market_price": self.market_price,
            "last_trade_price": self.last_trade_price,
            "last_updated": self.last_updated,
        }


@dataclass
class StubClientConfig:
    """Configuration for enhanced stub client behavior."""

    # Error simulation
    error_scenario: ErrorScenario = ErrorScenario.NONE
    error_probability: float = 0.0  # 0.0 to 1.0
    consecutive_errors: int = 0  # Number of consecutive errors to simulate

    # Timing simulation
    min_response_delay: float = 0.01  # Minimum API response delay
    max_response_delay: float = 0.1  # Maximum API response delay

    # Order behavior
    order_fill_probability: float = 1.0  # Probability orders get filled
    order_fill_delay: float = 0.0  # Delay before orders are filled
    partial_fill_probability: float = 0.1  # Probability of partial fills

    # Position simulation
    starting_positions_count: int = 0  # Number of positions to start with
    position_volatility: float = 0.1  # How much positions change between calls

    # Rate limiting
    rate_limit_threshold: int = 100  # Requests per minute before rate limiting
    rate_limit_window: int = 60  # Rate limit window in seconds

    # Market conditions
    market_condition: MarketCondition = MarketCondition.NORMAL
    liquidity_impact: float = 0.0  # Price impact from large orders

    # Business logic validation
    enable_order_validation: bool = True
    min_order_size: float = 1.0
    max_order_size: float = 10000.0
    min_price: float = 0.01
    max_price: float = 0.99

    # Response structure variations
    response_format_variation: float = 0.0  # Probability of format variations
    include_metadata: bool = True

    # State persistence
    persist_state: bool = True  # Whether to maintain state between calls

    # Real client behavior simulation
    simulate_balance_checks: bool = True
    simulate_order_book_depth: bool = False
    simulate_websocket_disconnects: bool = False
    simulate_price_impact: bool = True
    simulate_slippage: bool = True
    simulate_gas_fees: bool = False

    # Enhanced error patterns
    error_clustering: bool = False  # Whether errors come in clusters
    error_recovery_time: float = 0.0  # Time to recover from error states
    geographic_latency: bool = False  # Simulate geographic latency variations

    # Data consistency simulation
    eventual_consistency_delay: float = 0.0  # Delay for eventual consistency
    stale_data_probability: float = 0.0  # Probability of returning stale data

    # Load-based behavior
    simulate_load_shedding: bool = False
    peak_hours_degradation: bool = False

    # Enhanced validation
    strict_parameter_validation: bool = False
    case_sensitive_validation: bool = False

    # Custom error injection
    custom_error_callback: Callable | None = None

    # Response modification
    response_modifier: Callable | None = None

    # Circuit breaker
    circuit_breaker_threshold: int = 10  # Consecutive failures before tripping
    circuit_breaker_timeout: int = 60  # Seconds before attempting reset


class EnhancedStubClobClient:
    """
    Enhanced stub client that simulates realistic API behavior.

    This client provides configurable error scenarios, realistic response timing,
    and sophisticated data simulation for comprehensive testing of system resilience.
    """

    def __init__(self, config: StubClientConfig = None, *args: Any, **kwargs: Any):
        """Initialize the enhanced stub client."""
        self.config = config or StubClientConfig()
        self.orders: dict[str, MockOrder] = {}
        self.positions: list[MockPosition] = []
        self.request_count = 0
        self.error_count = 0
        self.last_request_time = time.time()
        self.consecutive_error_count = 0
        self.request_timestamps = []

        # Circuit breaker state
        self.circuit_breaker_tripped = False
        self.circuit_breaker_trip_time = 0.0
        self.circuit_breaker_failure_count = 0

        # Thread safety
        self._lock = threading.RLock()

        # Market data simulation
        self._market_prices: dict[str, float] = {}
        self._last_market_update = time.time()
        self._order_book_depth: dict[str, dict] = {}

        # Balance simulation
        self._balance = 10000.0  # Starting balance
        self._reserved_balance = 0.0

        # Error clustering state
        self._error_cluster_active = False
        self._error_cluster_start_time = 0.0

        # Geographic and load simulation
        self._peak_hours = [(9, 16), (20, 24)]  # UTC peak trading hours
        self._last_load_check = time.time()

        # Websocket connection simulation
        self._websocket_connected = True
        self._last_websocket_reconnect = time.time()

        # Initialize with starting positions if configured
        self._initialize_positions()

        log.debug(f"Enhanced stub client initialized with config: {self.config}")

    def _initialize_positions(self):
        """Initialize mock positions based on configuration."""
        for i in range(self.config.starting_positions_count):
            token_id = f"token_{i}"
            market_price = random.uniform(0.3, 0.7)

            position = MockPosition(
                token_id=token_id,
                market_slug=f"test_market_{i}",
                outcome_type="YES" if i % 2 == 0 else "NO",
                size=random.uniform(10, 100),
                usd_value=random.uniform(50, 500),
                avg_price=random.uniform(0.3, 0.7),
                market_price=market_price,
                last_trade_price=market_price * random.uniform(0.95, 1.05),
            )
            self.positions.append(position)
            self._market_prices[token_id] = market_price

    def _should_simulate_error(self, method_name: str) -> Exception | None:
        """Determine if an error should be simulated for this request."""
        with self._lock:
            self.request_count += 1

            # Check for load shedding during peak hours
            if self._should_apply_load_shedding(method_name):
                self._record_failure()
                return Exception("503 Service Unavailable - Load shedding active")

            # Check websocket disconnects for streaming methods
            if self._should_simulate_websocket_disconnect(method_name):
                return Exception("Connection lost - WebSocket disconnected")

            # Handle error clustering
            if self._is_in_error_cluster():
                self._record_failure()
                return Exception("503 Service Unavailable - System under load")

            # Check circuit breaker
            if self._is_circuit_breaker_tripped():
                return Exception("503 Service Unavailable - Circuit breaker tripped")

            # Check market conditions
            if self.config.market_condition == MarketCondition.MARKET_CLOSED:
                if method_name in ["create_order", "cancel_order"]:
                    return Exception("400 Bad Request - Market is closed")

            if self.config.market_condition == MarketCondition.HALTED:
                return Exception("503 Service Unavailable - Trading halted")

            # Check consecutive error limit
            if (
                self.config.consecutive_errors > 0
                and self.consecutive_error_count >= self.config.consecutive_errors
            ):
                self.consecutive_error_count = 0
                return None

            # Custom error callback
            if self.config.custom_error_callback:
                error = self.config.custom_error_callback(
                    method_name, self.request_count
                )
                if error:
                    self._record_failure()
                    return error

            # Rate limiting check
            if self._is_rate_limited():
                self._record_failure()
                return Exception("429 Too Many Requests - Rate limit exceeded")

            # Check if should generate error based on scenario and probability
            should_error = False

            if self.config.error_scenario != ErrorScenario.NONE:
                if self.config.error_scenario == ErrorScenario.INTERMITTENT:
                    # For intermittent, use both probability and random chance
                    should_error = (
                        self.config.error_probability > 0
                        and random.random() < self.config.error_probability
                    )
                else:
                    # For specific scenarios, always trigger unless probability is 0
                    should_error = self.config.error_probability != 0.0 and (
                        self.config.error_probability >= 1.0
                        or random.random() < self.config.error_probability
                    )
            elif self.config.error_probability > 0:
                # Pure probabilistic errors without specific scenario
                should_error = random.random() < self.config.error_probability

            if should_error:
                self._record_failure()
                return self._generate_error_for_scenario()

            # Reset consecutive error count on success
            self.consecutive_error_count = 0
            self.circuit_breaker_failure_count = 0
            return None

    def _is_rate_limited(self) -> bool:
        """Check if the client is being rate limited."""
        current_time = time.time()

        # Clean old timestamps
        cutoff_time = current_time - self.config.rate_limit_window
        self.request_timestamps = [
            ts for ts in self.request_timestamps if ts > cutoff_time
        ]

        # Add current request
        self.request_timestamps.append(current_time)

        # Check if over threshold (>= threshold triggers rate limiting)
        return len(self.request_timestamps) >= self.config.rate_limit_threshold

    def _generate_error_for_scenario(self) -> Exception:
        """Generate an appropriate error for the configured scenario."""
        scenario = self.config.error_scenario

        if scenario == ErrorScenario.NETWORK_ERROR:
            errors = [
                OSError("Network unreachable"),
                OSError("No route to host"),
                Exception("DNSError: Name resolution failed"),
            ]
            return random.choice(errors)

        elif scenario == ErrorScenario.SERVER_ERROR:
            errors = [
                Exception("500 Internal Server Error"),
                Exception("502 Bad Gateway"),
                Exception("503 Service Unavailable"),
            ]
            return random.choice(errors)

        elif scenario == ErrorScenario.RATE_LIMIT:
            return Exception("429 Too Many Requests")

        elif scenario == ErrorScenario.TIMEOUT:
            errors = [
                Exception("ReadTimeout: Request timed out"),
                Exception("ConnectTimeout: Connection timed out"),
                Exception("504 Gateway Timeout"),
            ]
            return random.choice(errors)

        elif scenario == ErrorScenario.CONNECTION_ERROR:
            errors = [
                OSError("Connection refused"),
                OSError("Connection reset by peer"),
                Exception("ConnectionError: Connection aborted"),
            ]
            return random.choice(errors)

        elif scenario == ErrorScenario.AUTHENTICATION_ERROR:
            return Exception("401 Unauthorized - Invalid API key")

        elif scenario == ErrorScenario.VALIDATION_ERROR:
            return ValueError("Invalid order parameters")

        elif scenario == ErrorScenario.INTERMITTENT:
            # Return a random error type for intermittent scenarios
            all_errors = [
                Exception("503 Service Unavailable"),
                OSError("Network unreachable"),
                Exception("ReadTimeout: Request timed out"),
                Exception("502 Bad Gateway"),
            ]
            return random.choice(all_errors)

        elif scenario == ErrorScenario.PARTIAL_FAILURE:
            return Exception("206 Partial Content - Request partially succeeded")

        elif scenario == ErrorScenario.CASCADING_FAILURE:
            cascade_errors = [
                Exception("503 Service Unavailable - Database connection lost"),
                Exception("503 Service Unavailable - Cache service down"),
                Exception("502 Bad Gateway - Upstream service unavailable"),
            ]
            return random.choice(cascade_errors)

        elif scenario == ErrorScenario.MAINTENANCE_MODE:
            return Exception(
                "503 Service Unavailable - Scheduled maintenance in progress"
            )

        elif scenario == ErrorScenario.CIRCUIT_BREAKER:
            return Exception("503 Service Unavailable - Circuit breaker open")

        elif scenario == ErrorScenario.DEGRADED_PERFORMANCE:
            errors = [
                Exception("503 Service Unavailable - Degraded performance mode"),
                Exception("502 Bad Gateway - Service degraded"),
                Exception("RequestException: Slow response times detected"),
            ]
            return random.choice(errors)

        elif scenario == ErrorScenario.INSUFFICIENT_BALANCE:
            return Exception("400 Bad Request - Insufficient balance")

        elif scenario == ErrorScenario.MARKET_CLOSED:
            return Exception("400 Bad Request - Market is closed for trading")

        elif scenario == ErrorScenario.STALE_PRICES:
            return Exception("409 Conflict - Stale price data detected")

        elif scenario == ErrorScenario.ORDER_REJECTED:
            return Exception("422 Unprocessable Entity - Order rejected by exchange")

        elif scenario == ErrorScenario.DUPLICATE_ORDER:
            return Exception("409 Conflict - Duplicate order detected")

        else:
            return Exception("Unexpected error")

    def _simulate_network_delay(self):
        """Simulate realistic network delay with market condition effects."""
        base_delay = random.uniform(
            self.config.min_response_delay, self.config.max_response_delay
        )

        # Adjust delay based on market conditions
        if self.config.market_condition == MarketCondition.HIGH_VOLATILITY:
            base_delay *= 1.5  # Higher load during volatile periods
        elif self.config.market_condition == MarketCondition.LOW_LIQUIDITY:
            base_delay *= 1.2  # Slightly slower during low liquidity

        if base_delay > 0:
            time.sleep(base_delay)

    def _modify_response(self, response: Any, method_name: str) -> Any:
        """Apply response modifications if configured."""
        # Apply custom response modifier first
        if self.config.response_modifier:
            response = self.config.response_modifier(response, method_name)

        # Apply format variations
        if (
            self.config.response_format_variation > 0
            and random.random() < self.config.response_format_variation
        ):
            response = self._apply_format_variation(response, method_name)

        # Add metadata if configured
        if self.config.include_metadata and isinstance(response, (dict, list)):
            if isinstance(response, dict):
                response["_metadata"] = {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "request_id": f"req_{uuid4().hex[:8]}",
                    "server_id": "stub-server-01",
                }
            elif isinstance(response, list) and response:
                # Add metadata to the container
                return {
                    "data": response,
                    "_metadata": {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "request_id": f"req_{uuid4().hex[:8]}",
                        "server_id": "stub-server-01",
                        "count": len(response),
                    },
                }

        return response

    def _should_apply_load_shedding(self, method_name: str) -> bool:
        """Check if load shedding should be applied."""
        if not self.config.simulate_load_shedding:
            return False

        # Check if in peak hours
        if self.config.peak_hours_degradation:
            current_hour = datetime.now(UTC).hour
            in_peak = any(
                start <= current_hour < end for start, end in self._peak_hours
            )
            if in_peak and random.random() < 0.1:  # 10% chance during peak
                return True

        return False

    def _should_simulate_websocket_disconnect(self, method_name: str) -> bool:
        """Check if websocket disconnect should be simulated."""
        if not self.config.simulate_websocket_disconnects:
            return False

        # Simulate periodic disconnects
        time_since_reconnect = time.time() - self._last_websocket_reconnect
        if (
            time_since_reconnect > 300 and random.random() < 0.05
        ):  # 5% chance after 5 minutes
            self._last_websocket_reconnect = time.time()
            self._websocket_connected = False
            return True

        return False

    def _is_in_error_cluster(self) -> bool:
        """Check if currently in an error cluster."""
        if not self.config.error_clustering:
            return False

        current_time = time.time()

        # Start new cluster
        if (
            not self._error_cluster_active and random.random() < 0.02
        ):  # 2% chance to start cluster
            self._error_cluster_active = True
            self._error_cluster_start_time = current_time
            return True

        # Continue existing cluster
        if self._error_cluster_active:
            cluster_duration = current_time - self._error_cluster_start_time
            if cluster_duration < 30.0:  # 30 second clusters
                return True
            else:
                self._error_cluster_active = False

        return False

    def _check_balance_sufficiency(self, order_value: float) -> bool:
        """Check if there's sufficient balance for the order."""
        if not self.config.simulate_balance_checks:
            return True

        available_balance = self._balance - self._reserved_balance
        return available_balance >= order_value

    def _simulate_slippage(self, price: float, size: float) -> float:
        """Simulate price slippage for large orders."""
        if not self.config.simulate_slippage:
            return price

        # Larger orders have more slippage
        slippage_factor = min(size / 10000.0, 0.05)  # Max 5% slippage
        slippage = price * slippage_factor * random.uniform(0.5, 1.5)

        # Slippage is always unfavorable to the trader
        return price + slippage if random.random() > 0.5 else price - slippage

    def _apply_eventual_consistency_delay(self):
        """Apply eventual consistency delay if configured."""
        if self.config.eventual_consistency_delay > 0:
            delay = random.uniform(0, self.config.eventual_consistency_delay)
            time.sleep(delay)

    def create_order(self, order_args, *args: Any, **kwargs: Any) -> MockOrder:
        """Create a mock order with realistic behavior simulation."""
        error = self._should_simulate_error("create_order")
        if error:
            raise error

        self._simulate_network_delay()

        # Extract order parameters
        if hasattr(order_args, "token_id"):
            token_id = order_args.token_id
            side = order_args.side
            price = order_args.price
            size = order_args.size
            tif = getattr(order_args, "tif", "GTC")
        else:
            # Fallback for dict-like args
            token_id = str(order_args.get("token_id", f"token_{uuid4().hex[:8]}"))
            side = str(order_args.get("side", "buy"))
            price = float(order_args.get("price", 0.5))
            size = float(order_args.get("size", 100))
            tif = str(order_args.get("tif", "GTC"))

        # Enhanced parameter validation
        if self.config.enable_order_validation:
            self._validate_order_params(token_id, side, price, size)

        # Check balance sufficiency
        order_value = size * price
        if not self._check_balance_sufficiency(order_value):
            raise Exception("400 Bad Request - Insufficient balance")

        # Apply gas fee simulation
        gas_fee = 0.0
        if self.config.simulate_gas_fees:
            gas_fee = random.uniform(0.001, 0.01)  # $0.001 to $0.01 gas fee
            if not self._check_balance_sufficiency(order_value + gas_fee):
                raise Exception("400 Bad Request - Insufficient balance for gas fees")

        # Simulate stale price detection
        if (
            self.config.stale_data_probability > 0
            and random.random() < self.config.stale_data_probability
        ):
            raise Exception("409 Conflict - Price data is stale, please refresh")

        # Apply liquidity impact and slippage to price
        effective_price = self._apply_liquidity_impact(price, size)
        if self.config.simulate_slippage:
            effective_price = self._simulate_slippage(effective_price, size)

        # Create mock order
        order = MockOrder(
            id=f"order_{uuid4().hex[:12]}",
            token_id=token_id,
            side=side.lower(),
            price=effective_price,
            size=size,
            status="open",
            tif=tif,
            fee=size * effective_price * 0.002,  # 0.2% fee
        )

        with self._lock:
            # Reserve balance for the order
            if self.config.simulate_balance_checks:
                self._reserved_balance += order_value + gas_fee

            # Store order first, then potentially fill it
            self.orders[order.id] = order

            # Update market price simulation
            self._update_market_price(token_id, effective_price, size)

            # Simulate order book depth updates
            if self.config.simulate_order_book_depth:
                self._update_order_book_depth(token_id, side, effective_price, size)

        # Simulate order fill based on probability and market conditions
        fill_probability = self._calculate_fill_probability(order)

        if random.random() < fill_probability:
            if self.config.order_fill_delay > 0:
                time.sleep(self.config.order_fill_delay)

            # Determine if partial or full fill
            if random.random() < self.config.partial_fill_probability:
                # Partial fill
                fill_ratio = random.uniform(0.1, 0.8)
                order.filled_size = order.size * fill_ratio
                order.status = "partial"
                # Only release partial reserved balance
                if self.config.simulate_balance_checks:
                    filled_value = order.filled_size * effective_price
                    self._reserved_balance -= filled_value
                    self._balance -= filled_value  # Deduct from actual balance
            else:
                # Full fill
                order.status = "filled"
                order.filled_size = order.size
                # Release reserved balance and deduct from actual balance
                if self.config.simulate_balance_checks:
                    self._reserved_balance -= order_value
                    self._balance -= order_value

            order.avg_fill_price = effective_price
            order.updated_at = datetime.now(UTC).isoformat()

        # Apply eventual consistency delay
        self._apply_eventual_consistency_delay()

        response = self._modify_response(order, "create_order")
        log.debug(
            f"Stub client created order: {order.id} ({order.status}), balance: {self._balance:.2f}"
        )
        return response

    def cancel_all(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """Cancel all orders with realistic behavior simulation."""
        error = self._should_simulate_error("cancel_all")
        if error:
            raise error

        self._simulate_network_delay()

        # Get all open orders
        cancelled_orders = []
        total_released_value = 0.0

        with self._lock:
            for order in self.orders.values():
                if order.status in ["open", "partial"]:
                    # Calculate unfilled value to release from reserves
                    unfilled_size = order.size - order.filled_size
                    unfilled_value = unfilled_size * order.price
                    total_released_value += unfilled_value

                    order.status = "cancelled"
                    order.updated_at = datetime.now(UTC).isoformat()
                    cancelled_orders.append(order.to_dict())

            # Release reserved balance for cancelled orders
            if self.config.simulate_balance_checks and total_released_value > 0:
                self._reserved_balance = max(
                    0, self._reserved_balance - total_released_value
                )

        # Apply eventual consistency delay
        self._apply_eventual_consistency_delay()

        response = self._modify_response(cancelled_orders, "cancel_all")
        log.debug(
            f"Stub client cancelled {len(cancelled_orders)} orders, released {total_released_value:.2f}"
        )
        return response

    def get_positions(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """Get positions with realistic behavior simulation and data variation."""
        error = self._should_simulate_error("get_positions")
        if error:
            raise error

        self._simulate_network_delay()

        with self._lock:
            # Update market prices periodically
            self._update_market_data()

            # Apply volatility to positions to simulate market movements
            if self.config.position_volatility > 0 and self.positions:
                for position in self.positions:
                    # Update market price with volatility
                    if position.token_id in self._market_prices:
                        market_price = self._market_prices[position.token_id]
                        volatility_factor = 1 + random.uniform(
                            -self.config.position_volatility,
                            self.config.position_volatility,
                        )
                        new_market_price = max(
                            0.01, min(0.99, market_price * volatility_factor)
                        )
                        self._market_prices[position.token_id] = new_market_price

                        # Update position values based on new market price
                        position.market_price = new_market_price
                        position.usd_value = position.size * new_market_price
                        position.unrealized_pnl = position.size * (
                            new_market_price - position.avg_price
                        )
                        position.last_updated = datetime.now(UTC).isoformat()

            # Simulate stale data
            if (
                self.config.stale_data_probability > 0
                and random.random() < self.config.stale_data_probability
            ):
                # Return positions from 5-30 seconds ago by not updating timestamps
                stale_positions = []
                for pos in self.positions:
                    stale_pos = pos.to_dict().copy()
                    # Make timestamp appear older
                    old_time = datetime.now(UTC) - timedelta(
                        seconds=random.randint(5, 30)
                    )
                    stale_pos["last_updated"] = old_time.isoformat()
                    stale_positions.append(stale_pos)
                position_dicts = stale_positions
            else:
                # Convert to dictionaries
                position_dicts = [pos.to_dict() for pos in self.positions]

        # Apply eventual consistency delay
        self._apply_eventual_consistency_delay()

        response = self._modify_response(position_dicts, "get_positions")
        log.debug(f"Stub client returned {len(position_dicts)} positions")
        return response

    def get_orders(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """Get orders with realistic behavior simulation."""
        error = self._should_simulate_error("get_orders")
        if error:
            raise error

        self._simulate_network_delay()

        orders = [order.to_dict() for order in self.orders.values()]
        response = self._modify_response(orders, "get_orders")
        log.debug(f"Stub client returned {len(orders)} orders")
        return response

    def cancel_order(self, order_id: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Cancel a specific order."""
        error = self._should_simulate_error("cancel_order")
        if error:
            raise error

        self._simulate_network_delay()

        if order_id in self.orders:
            order = self.orders[order_id]

            # Release reserved balance if order was open/partial
            if (
                order.status in ["open", "partial"]
                and self.config.simulate_balance_checks
            ):
                unfilled_size = order.size - order.filled_size
                unfilled_value = unfilled_size * order.price
                self._reserved_balance = max(0, self._reserved_balance - unfilled_value)

            order.status = "cancelled"
            order.updated_at = datetime.now(UTC).isoformat()
            response = self._modify_response(order.to_dict(), "cancel_order")
            log.debug(f"Stub client cancelled order: {order_id}")
            return response
        else:
            raise ValueError(f"Order not found: {order_id}")

    def get_order(self, order_id: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Get a specific order."""
        error = self._should_simulate_error("get_order")
        if error:
            raise error

        self._simulate_network_delay()

        if order_id in self.orders:
            order = self.orders[order_id]
            response = self._modify_response(order.to_dict(), "get_order")
            log.debug(f"Stub client returned order: {order_id}")
            return response
        else:
            raise ValueError(f"Order not found: {order_id}")

    def get_balance(self, *args: Any, **kwargs: Any) -> dict[str, float]:
        """Get account balance with realistic simulation."""
        error = self._should_simulate_error("get_balance")
        if error:
            raise error

        self._simulate_network_delay()

        with self._lock:
            if self.config.simulate_balance_checks:
                # Use tracked balance
                balance = {
                    "balance": self._balance,
                    "available": self._balance - self._reserved_balance,
                    "reserved": self._reserved_balance,
                }
            else:
                # Simulate realistic balance
                balance = {
                    "balance": random.uniform(1000, 10000),
                    "available": random.uniform(500, 8000),
                    "reserved": random.uniform(0, 500),
                }

        # Apply eventual consistency delay
        self._apply_eventual_consistency_delay()

        response = self._modify_response(balance, "get_balance")
        log.debug(f"Stub client returned balance: {balance['balance']:.2f}")
        return response

    def __getattr__(self, name: str) -> Any:
        """Handle any other method calls with configurable behavior."""

        def method(*args: Any, **kwargs: Any) -> Any:
            error = self._should_simulate_error(name)
            if error:
                raise error

            self._simulate_network_delay()

            # Return reasonable defaults for unknown methods
            if name.startswith("get_"):
                return {}
            elif name.startswith("cancel_"):
                return {"cancelled": True}
            elif name.startswith("create_") or name.startswith("post_"):
                return {"id": f"mock_{uuid4().hex[:8]}", "status": "success"}
            else:
                return {"status": "ok"}

        return method

    # Statistics and monitoring methods
    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive statistics about stub client behavior."""
        with self._lock:
            filled_orders = sum(
                1 for order in self.orders.values() if order.status == "filled"
            )
            partial_orders = sum(
                1 for order in self.orders.values() if order.status == "partial"
            )
            open_orders = sum(
                1 for order in self.orders.values() if order.status == "open"
            )
            cancelled_orders = sum(
                1 for order in self.orders.values() if order.status == "cancelled"
            )

            # Calculate total order value
            total_order_value = sum(
                order.size * order.price for order in self.orders.values()
            )
            filled_value = sum(
                order.filled_size * order.avg_fill_price
                for order in self.orders.values()
                if order.avg_fill_price is not None
            )

            return {
                # Request statistics
                "total_requests": self.request_count,
                "total_errors": self.error_count,
                "error_rate": self.error_count / max(1, self.request_count),
                "consecutive_errors": self.consecutive_error_count,
                # Order statistics
                "orders_created": len(self.orders),
                "orders_filled": filled_orders,
                "orders_partial": partial_orders,
                "orders_open": open_orders,
                "orders_cancelled": cancelled_orders,
                "total_order_value": total_order_value,
                "filled_value": filled_value,
                "fill_rate": filled_orders / max(1, len(self.orders)),
                # Position statistics
                "positions": len(self.positions),
                "total_position_value": sum(pos.usd_value for pos in self.positions),
                "total_unrealized_pnl": sum(
                    pos.unrealized_pnl for pos in self.positions
                ),
                # Balance statistics
                "current_balance": self._balance,
                "reserved_balance": self._reserved_balance,
                "available_balance": self._balance - self._reserved_balance,
                # Circuit breaker statistics
                "circuit_breaker_tripped": self.circuit_breaker_tripped,
                "circuit_breaker_failures": self.circuit_breaker_failure_count,
                # Error clustering statistics
                "error_cluster_active": self._error_cluster_active,
                "error_cluster_start_time": self._error_cluster_start_time,
                # WebSocket statistics
                "websocket_connected": self._websocket_connected,
                "last_websocket_reconnect": self._last_websocket_reconnect,
                # Market data
                "market_prices": dict(self._market_prices),
                "order_book_tokens": list(self._order_book_depth.keys()),
                # Rate limiting
                "recent_requests": len(self.request_timestamps),
                # Configuration
                "config": self.config.__dict__,
            }

    def reset_stats(self):
        """Reset statistics counters."""
        with self._lock:
            self.request_count = 0
            self.error_count = 0
            self.consecutive_error_count = 0
            self.request_timestamps = []
            self.circuit_breaker_tripped = False
            self.circuit_breaker_failure_count = 0

    def add_position(self, position: MockPosition):
        """Add a mock position for testing."""
        with self._lock:
            self.positions.append(position)
            if position.token_id not in self._market_prices:
                self._market_prices[position.token_id] = (
                    position.market_price or position.avg_price
                )

    def clear_positions(self):
        """Clear all mock positions."""
        with self._lock:
            self.positions.clear()

    def clear_orders(self):
        """Clear all mock orders and reset related state."""
        with self._lock:
            self.orders.clear()
            # Reset reserved balance when clearing orders
            if self.config.simulate_balance_checks:
                self._reserved_balance = 0.0

    def set_config(self, config: StubClientConfig):
        """Update the stub client configuration."""
        self.config = config
        log.debug(f"Stub client configuration updated: {config}")

    def set_balance(self, balance: float):
        """Set the current balance for testing."""
        with self._lock:
            self._balance = balance
            log.debug(f"Stub client balance set to: {balance}")

    def add_reserved_balance(self, amount: float):
        """Add to reserved balance for testing."""
        with self._lock:
            self._reserved_balance += amount
            log.debug(
                f"Added {amount} to reserved balance, total: {self._reserved_balance}"
            )

    def simulate_websocket_reconnect(self):
        """Simulate a websocket reconnection."""
        self._websocket_connected = True
        self._last_websocket_reconnect = time.time()
        log.debug("Simulated websocket reconnection")

    def trigger_circuit_breaker(self):
        """Manually trigger circuit breaker for testing."""
        self.circuit_breaker_tripped = True
        self.circuit_breaker_trip_time = time.time()
        self.circuit_breaker_failure_count = self.config.circuit_breaker_threshold
        log.debug("Circuit breaker manually triggered")

    def get_order_book_depth(self, token_id: str) -> dict[str, Any]:
        """Get simulated order book depth for a token."""
        with self._lock:
            return self._order_book_depth.get(
                token_id, {"bids": [], "asks": [], "last_updated": time.time()}
            )

    # New helper methods for enhanced simulation
    def _record_failure(self):
        """Record a failure for circuit breaker tracking."""
        self.consecutive_error_count += 1
        self.error_count += 1
        self.circuit_breaker_failure_count += 1

        if self.circuit_breaker_failure_count >= self.config.circuit_breaker_threshold:
            self.circuit_breaker_tripped = True
            self.circuit_breaker_trip_time = time.time()
            log.warning(
                f"Circuit breaker tripped after {self.circuit_breaker_failure_count} failures"
            )

    def _is_circuit_breaker_tripped(self) -> bool:
        """Check if circuit breaker is currently tripped."""
        if not self.circuit_breaker_tripped:
            return False

        # Check if timeout has passed
        if (
            time.time() - self.circuit_breaker_trip_time
            > self.config.circuit_breaker_timeout
        ):
            self.circuit_breaker_tripped = False
            self.circuit_breaker_failure_count = 0
            log.info("Circuit breaker reset - attempting normal operation")
            return False

        return True

    def _validate_order_params(
        self, token_id: str, side: str, price: float, size: float
    ):
        """Validate order parameters against business rules with enhanced validation."""
        if not token_id or not isinstance(token_id, str):
            raise ValueError("Invalid token_id")

        # Enhanced token ID validation
        if self.config.strict_parameter_validation:
            if (
                len(token_id) < 3
                or not token_id.replace("_", "").replace("-", "").isalnum()
            ):
                raise ValueError(f"Token ID format invalid: {token_id}")

        # Case-sensitive side validation
        valid_sides = (
            ["buy", "sell"]
            if not self.config.case_sensitive_validation
            else ["BUY", "SELL"]
        )
        if side not in valid_sides and side.lower() not in [
            s.lower() for s in valid_sides
        ]:
            raise ValueError(f"Invalid side: {side}. Must be one of {valid_sides}")

        if price <= 0:
            raise ValueError("Price must be positive")

        if price < self.config.min_price or price > self.config.max_price:
            raise ValueError(
                f"Price {price} outside valid range [{self.config.min_price}, {self.config.max_price}]"
            )

        if size <= 0:
            raise ValueError("Size must be positive")

        if size < self.config.min_order_size or size > self.config.max_order_size:
            raise ValueError(
                f"Size {size} outside valid range [{self.config.min_order_size}, {self.config.max_order_size}]"
            )

        # Additional validations
        if self.config.strict_parameter_validation:
            # Check for reasonable precision
            if len(str(price).split(".")[-1]) > 8:
                raise ValueError("Price precision too high (max 8 decimal places)")

            if len(str(size).split(".")[-1]) > 6:
                raise ValueError("Size precision too high (max 6 decimal places)")

    def _apply_liquidity_impact(self, price: float, size: float) -> float:
        """Apply liquidity impact to order price."""
        if self.config.liquidity_impact <= 0:
            return price

        # Larger orders have more price impact
        impact_factor = min(
            size / 1000.0 * self.config.liquidity_impact, 0.1
        )  # Max 10% impact

        # Random impact direction (slippage can be positive or negative)
        impact_direction = 1 if random.random() > 0.5 else -1
        impact = price * impact_factor * impact_direction

        # Ensure price stays within valid bounds
        return max(0.01, min(0.99, price + impact))

    def _update_market_price(self, token_id: str, price: float, size: float):
        """Update market price based on order activity."""
        if token_id not in self._market_prices:
            self._market_prices[token_id] = price
        else:
            # Weighted average with small weight for new orders
            current_price = self._market_prices[token_id]
            weight = min(size / 1000.0, 0.1)  # Max 10% weight
            self._market_prices[token_id] = (
                current_price * (1 - weight) + price * weight
            )

    def _calculate_fill_probability(self, order: MockOrder) -> float:
        """Calculate order fill probability based on market conditions."""
        base_probability = self.config.order_fill_probability

        # Adjust based on market conditions
        if self.config.market_condition == MarketCondition.LOW_LIQUIDITY:
            base_probability *= 0.7  # Lower fill rate in low liquidity
        elif self.config.market_condition == MarketCondition.HIGH_VOLATILITY:
            base_probability *= 0.8  # Slightly lower fill rate in high volatility

        # Adjust based on order size (larger orders fill less frequently)
        if order.size > 500:
            base_probability *= 0.9
        elif order.size > 1000:
            base_probability *= 0.8

        return min(1.0, max(0.0, base_probability))

    def _update_market_data(self):
        """Update market data periodically."""
        current_time = time.time()
        if current_time - self._last_market_update < 5.0:  # Update every 5 seconds
            return

        self._last_market_update = current_time

        # Update market prices with small random movements
        for token_id in self._market_prices:
            current_price = self._market_prices[token_id]

            # Apply market condition effects
            if self.config.market_condition == MarketCondition.HIGH_VOLATILITY:
                change = random.uniform(-0.05, 0.05)  # ±5% moves
            elif self.config.market_condition == MarketCondition.LOW_LIQUIDITY:
                change = random.uniform(-0.01, 0.01)  # ±1% moves
            else:
                change = random.uniform(-0.02, 0.02)  # ±2% normal moves

            new_price = max(0.01, min(0.99, current_price * (1 + change)))
            self._market_prices[token_id] = new_price

    def _update_order_book_depth(
        self, token_id: str, side: str, price: float, size: float
    ):
        """Update simulated order book depth."""
        if token_id not in self._order_book_depth:
            self._order_book_depth[token_id] = {
                "bids": [],
                "asks": [],
                "last_updated": time.time(),
            }

        book = self._order_book_depth[token_id]

        # Add order to appropriate side
        order_entry = [price, size, time.time()]
        if side.lower() == "buy":
            book["bids"].append(order_entry)
            book["bids"].sort(key=lambda x: x[0], reverse=True)  # Sort by price desc
        else:
            book["asks"].append(order_entry)
            book["asks"].sort(key=lambda x: x[0])  # Sort by price asc

        # Keep only top 10 levels
        book["bids"] = book["bids"][:10]
        book["asks"] = book["asks"][:10]
        book["last_updated"] = time.time()

    def _apply_format_variation(self, response: Any, method_name: str) -> Any:
        """Apply random format variations to responses."""
        if not isinstance(response, (dict, list)):
            return response

        # Sometimes return data wrapped in different structures
        variation_type = random.choice(
            ["camelCase", "nested", "extra_fields", "api_versioning"]
        )

        if variation_type == "camelCase" and isinstance(response, dict):
            # Convert snake_case to camelCase
            converted = {}
            for key, value in response.items():
                if "_" in key:
                    camel_key = "".join(
                        word.capitalize() if i > 0 else word
                        for i, word in enumerate(key.split("_"))
                    )
                    converted[camel_key] = value
                else:
                    converted[key] = value
            return converted

        elif variation_type == "nested" and isinstance(response, (dict, list)):
            # Wrap response in nested structure
            return {
                "result": response,
                "status": "success",
                "version": "v2.1",
                "server_time": datetime.now(UTC).isoformat(),
            }

        elif variation_type == "extra_fields" and isinstance(response, dict):
            # Add extra fields
            response["_extra_field_1"] = "some_value"
            response["_debug_info"] = {
                "processing_time_ms": random.randint(10, 100),
                "server_load": random.uniform(0.1, 0.9),
            }
            return response

        elif variation_type == "api_versioning" and isinstance(response, (dict, list)):
            # Simulate different API versions
            return {
                "data": response,
                "meta": {
                    "api_version": random.choice(["v1.0", "v1.1", "v2.0"]),
                    "deprecation_warning": "This endpoint will be deprecated in v3.0",
                },
            }

        return response


class ConfigurableStubClobClient:
    """
    Backwards-compatible wrapper that can be configured to behave like
    the old stub (raising errors) or the new enhanced stub.
    """

    def __init__(
        self,
        use_enhanced: bool = False,
        config: StubClientConfig = None,
        *args: Any,
        **kwargs: Any,
    ):
        """Initialize configurable stub client."""
        self.use_enhanced = use_enhanced
        if use_enhanced:
            self.client = EnhancedStubClobClient(config, *args, **kwargs)
        else:
            # Use original behavior for backwards compatibility
            self.client = None

    def __getattr__(self, name: str):
        """Delegate to enhanced client or raise error."""
        if self.use_enhanced and self.client:
            return getattr(self.client, name)
        else:
            # Original stub behavior - raise UnavailableClientError
            def method(*args: Any, **kwargs: Any) -> Any:
                from inkedup_bot.order_client import UnavailableClientError

                raise UnavailableClientError("py-clob-client not available")

            return method


# Convenience functions for common test scenarios
def create_network_error_client() -> EnhancedStubClobClient:
    """Create a stub client that simulates network errors."""
    config = StubClientConfig(error_scenario=ErrorScenario.NETWORK_ERROR)
    return EnhancedStubClobClient(config)


def create_rate_limited_client() -> EnhancedStubClobClient:
    """Create a stub client that simulates rate limiting."""
    config = StubClientConfig(
        error_scenario=ErrorScenario.NONE,  # Use actual rate limiting, not error scenario
        rate_limit_threshold=6,  # Allow 5 requests, then rate limit on 6th
        rate_limit_window=10,
    )
    return EnhancedStubClobClient(config)


def create_intermittent_error_client() -> EnhancedStubClobClient:
    """Create a stub client with intermittent errors."""
    config = StubClientConfig(
        error_scenario=ErrorScenario.INTERMITTENT,
        error_probability=0.3,  # 30% error rate
    )
    return EnhancedStubClobClient(config)


def create_slow_response_client() -> EnhancedStubClobClient:
    """Create a stub client with slow responses for timeout testing."""
    config = StubClientConfig(min_response_delay=0.5, max_response_delay=2.0)
    return EnhancedStubClobClient(config)


def create_realistic_trading_client() -> EnhancedStubClobClient:
    """Create a stub client with realistic trading behavior."""
    config = StubClientConfig(
        starting_positions_count=3,
        position_volatility=0.05,  # 5% volatility
        order_fill_probability=0.9,  # 90% fill rate
        partial_fill_probability=0.1,  # 10% partial fills
        min_response_delay=0.01,
        max_response_delay=0.1,
    )
    return EnhancedStubClobClient(config)


def create_circuit_breaker_client() -> EnhancedStubClobClient:
    """Create a stub client that simulates circuit breaker behavior."""
    config = StubClientConfig(
        error_scenario=ErrorScenario.SERVER_ERROR,
        error_probability=1.0,  # Always error initially
        circuit_breaker_threshold=3,  # Trip after 3 failures
        circuit_breaker_timeout=5,  # 5 second timeout
    )
    return EnhancedStubClobClient(config)


def create_market_condition_client(
    condition: MarketCondition,
) -> EnhancedStubClobClient:
    """Create a stub client with specific market conditions."""
    config = StubClientConfig(
        market_condition=condition,
        starting_positions_count=2,
        position_volatility=(
            0.1 if condition == MarketCondition.HIGH_VOLATILITY else 0.02
        ),
    )
    return EnhancedStubClobClient(config)


def create_validation_heavy_client() -> EnhancedStubClobClient:
    """Create a stub client with strict validation rules."""
    config = StubClientConfig(
        enable_order_validation=True,
        min_order_size=10.0,
        max_order_size=1000.0,
        min_price=0.05,
        max_price=0.95,
        liquidity_impact=0.02,  # 2% price impact
    )
    return EnhancedStubClobClient(config)


def create_partial_failure_client() -> EnhancedStubClobClient:
    """Create a stub client that simulates partial failures."""
    config = StubClientConfig(
        error_scenario=ErrorScenario.PARTIAL_FAILURE,
        error_probability=0.3,
        partial_fill_probability=0.4,  # High partial fill rate
        response_format_variation=0.2,  # 20% format variations
    )
    return EnhancedStubClobClient(config)


def create_enhanced_realistic_client() -> EnhancedStubClobClient:
    """Create a stub client with all enhanced realistic features enabled."""
    config = StubClientConfig(
        starting_positions_count=5,
        position_volatility=0.03,  # 3% volatility
        order_fill_probability=0.95,  # 95% fill rate
        partial_fill_probability=0.15,  # 15% partial fills
        min_response_delay=0.02,
        max_response_delay=0.15,
        error_probability=0.05,  # 5% general error rate
        error_scenario=ErrorScenario.INTERMITTENT,
        # Enable enhanced features
        simulate_balance_checks=True,
        simulate_price_impact=True,
        simulate_slippage=True,
        error_clustering=True,
        eventual_consistency_delay=0.1,
        stale_data_probability=0.02,
        simulate_load_shedding=True,
        peak_hours_degradation=True,
        # Enhanced validation
        strict_parameter_validation=True,
        enable_order_validation=True,
        # Response variations
        response_format_variation=0.1,
        include_metadata=True,
    )
    return EnhancedStubClobClient(config)


def create_stress_test_client() -> EnhancedStubClobClient:
    """Create a stub client for stress testing with various failure modes."""
    config = StubClientConfig(
        error_scenario=ErrorScenario.CASCADING_FAILURE,
        error_probability=0.2,  # 20% error rate
        error_clustering=True,
        # Aggressive rate limiting
        rate_limit_threshold=20,
        rate_limit_window=60,
        # Circuit breaker
        circuit_breaker_threshold=5,
        circuit_breaker_timeout=30,
        # Load simulation
        simulate_load_shedding=True,
        peak_hours_degradation=True,
        # Data consistency issues
        stale_data_probability=0.1,
        eventual_consistency_delay=0.5,
        # Network issues
        min_response_delay=0.1,
        max_response_delay=2.0,
    )
    return EnhancedStubClobClient(config)


def create_balance_constraint_client(
    starting_balance: float = 1000.0,
) -> EnhancedStubClobClient:
    """Create a stub client with balance constraints for testing insufficient funds scenarios."""
    config = StubClientConfig(
        simulate_balance_checks=True,
        enable_order_validation=True,
        min_order_size=10.0,
        max_order_size=500.0,  # Constrain max order size
        order_fill_probability=0.9,
    )
    client = EnhancedStubClobClient(config)
    client._balance = starting_balance
    return client
