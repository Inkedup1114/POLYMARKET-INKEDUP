"""Core trading engine for the InkedUp Polymarket trading bot.

This module provides the main TradingEngine class that orchestrates all trading
operations including signal processing, risk management, and order execution.
The engine handles:

- Signal lifecycle management with timeout controls
- Risk validation and position size management
- Order routing and execution monitoring
- State synchronization across components
- Performance tracking and metrics collection

The TradingEngine acts as the central coordinator between market scanning,
signal generation, risk analysis, and order execution systems.

Example:
    Basic trading engine usage:

    >>> from inkedup_bot.config import BotConfig
    >>> from inkedup_bot.engine import TradingEngine
    >>>
    >>> # Initialize with configuration
    >>> config = BotConfig()
    >>> engine = TradingEngine(config)
    >>>
    >>> # Initialize async components
    >>> await engine.initialize()
    >>>
    >>> # Process a trading signal
    >>> from inkedup_bot.signals import TradingSignal
    >>> signal = TradingSignal(...)
    >>> result = engine.process_signal(signal)
    >>>
    >>> # Clean shutdown
    >>> await engine.cleanup()

Architecture:
    The TradingEngine coordinates several subsystems:
    - SignalManager: Handles signal queuing and deduplication
    - RiskManager: Validates trades against risk limits
    - OrderClient: Executes trades on the exchange
    - StateManager: Maintains portfolio and order state

Performance:
    The engine supports configurable concurrent signal processing with
    timeout management to prevent resource exhaustion and ensure
    responsive trading behavior under varying market conditions.

"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .config import BotConfig
from .order_client import OrderClient
from .risk import RiskManager
from .signal_manager import SignalManager, SignalManagerConfig
from .signals import TradingSignal
from .state import StateManager

log = logging.getLogger("engine")


class TradingEngine:
    """Central trading engine that orchestrates signal processing, risk management, and order execution.

    The TradingEngine is the core component responsible for coordinating all trading
    activities in the InkedUp bot. It manages signal lifecycle, applies risk controls,
    and executes trades while maintaining state consistency across all subsystems.

    Key Features:
        - Signal processing with configurable timeouts
        - Multi-level risk validation and position sizing
        - Order execution with retry logic and error handling
        - Real-time state synchronization and portfolio tracking
        - Performance metrics and monitoring integration
        - Graceful shutdown and resource cleanup

    Attributes:
        cfg (BotConfig): Bot configuration settings
        state (StateManager): Portfolio and order state manager
        order_client (OrderClient): Interface to trading exchange
        risk (RiskManager): Risk validation and limit enforcement
        signal_manager (SignalManager): Signal queuing and processing

    Example:
        Initialize and use the trading engine:

        >>> # Create configuration
        >>> config = BotConfig(
        ...     max_position_size=1000.0,
        ...     signal_max_concurrent=5,
        ...     signal_default_timeout_seconds=30.0
        ... )
        >>>
        >>> # Initialize engine
        >>> engine = TradingEngine(config)
        >>> await engine.initialize()
        >>>
        >>> # Process trading signals
        >>> signal = TradingSignal(
        ...     market_slug="election-2024",
        ...     token_id="0x123...",
        ...     side="buy",
        ...     size=100.0,
        ...     price=0.55
        ... )
        >>>
        >>> result = engine.process_signal(signal)
        >>> print(f"Signal processed: {result}")
        >>>
        >>> # Monitor performance
        >>> metrics = engine.get_signal_metrics()
        >>> print(f"Processed {metrics['total_processed']} signals")
        >>>
        >>> # Cleanup
        >>> await engine.cleanup()

    Signal Processing Flow:
        1. Signal validation and deduplication
        2. Risk assessment and position sizing
        3. Order generation and execution
        4. State update and performance tracking
        5. Timeout management and cleanup

    Thread Safety:
        The TradingEngine is designed for single-threaded async operation.
        All methods should be called from the same event loop to ensure
        thread safety and data consistency.

    """

    def __init__(self, cfg: BotConfig) -> None:
        """Initialize the trading engine with configuration.

        Args:
            cfg: Bot configuration containing trading parameters,
                risk limits, and system settings. See BotConfig
                for all available options.

        Raises:
            ValueError: If configuration is invalid or incomplete

        Note:
            The engine is not ready for use until initialize() is called.
            This separation allows for dependency injection and testing.

        """
        self.cfg = cfg
        self.state = StateManager()
        self.order_client = OrderClient(self.cfg, self.state)
        self.risk = RiskManager(self.cfg, self.order_client, self.state)
        self._initialized = False

        # Initialize signal manager with configuration
        signal_config = SignalManagerConfig(
            default_signal_timeout=getattr(cfg, "signal_default_timeout_seconds", 30.0),
            spread_signal_timeout=getattr(cfg, "signal_spread_timeout_seconds", 15.0),
            complement_signal_timeout=getattr(
                cfg, "signal_complement_timeout_seconds", 45.0
            ),
            market_making_signal_timeout=getattr(
                cfg, "signal_market_making_timeout_seconds", 60.0
            ),
            cleanup_interval=getattr(cfg, "signal_cleanup_interval_seconds", 10.0),
            max_concurrent_signals=getattr(cfg, "signal_max_concurrent", 10),
            enable_deduplication=getattr(cfg, "signal_enable_deduplication", True),
            deduplication_window=getattr(
                cfg, "signal_deduplication_window_seconds", 5.0
            ),
        )
        self.signal_manager = SignalManager(signal_config)
        self.signal_manager.set_signal_processor(self._process_signal_direct)

    async def initialize(self) -> None:
        """Initialize the trading engine and all subsystems.

        This method must be called before the engine can process signals.
        It initializes the database connection, starts the signal manager,
        and prepares all components for trading operations.

        Raises:
            DatabaseError: If database initialization fails
            ConnectionError: If unable to connect to required services
            ValueError: If configuration is invalid

        Example:
            >>> engine = TradingEngine(config)
            >>> await engine.initialize()
            >>> # Engine is now ready for signal processing

        Note:
            This method is idempotent - calling it multiple times has no effect
            after the first successful initialization.

        """
        if self._initialized:
            return

        # Initialize the state manager database
        await self.state.initialize_async()

        # Start signal manager
        await self.signal_manager.start()

        self._initialized = True
        log.info(
            "TradingEngine initialized with database persistence and signal management"
        )

    def _ensure_initialized(self) -> None:
        """Ensure the trading engine is initialized (synchronous fallback).

        This is a synchronous wrapper for the async initialize() method. It should
        only be used during startup when no event loop is running. For async
        applications, use 'await engine.initialize()' instead.

        Raises:
            RuntimeError: If an event loop is already running (use async initialize instead)
            DatabaseError: If database initialization fails
            ConnectionError: If unable to connect to required services

        Warning:
            This method creates a new event loop and should not be used in
            async contexts. It's provided for backward compatibility only.

        """
        if not self._initialized:
            log.info("Engine not initialized. Performing one-time synchronous setup.")
            try:
                # asyncio.run() is a simplified way to run an async function from a
                # sync context. It creates a new event loop and closes it after
                # completion. It will raise a RuntimeError if called when an event
                # loop is already running in the same thread, which prevents
                # unsafe, nested loops.
                asyncio.run(self.initialize())
            except RuntimeError as e:
                log.error(
                    "Failed to initialize engine synchronously, likely because an "
                    f"event loop is already running: {e}. Please use "
                    "'await engine.initialize()' in your async startup code."
                )
                raise  # Re-raise the exception to prevent the engine from running in an uninitialized state.

    async def shutdown(self) -> None:
        """Shutdown the trading engine and cleanup all resources.

        This method gracefully shuts down all subsystems, ensures pending
        operations are completed or cancelled, and releases system resources.
        Should be called before application exit to prevent resource leaks.

        Example:
            >>> # Graceful shutdown
            >>> await engine.shutdown()
            >>> # Engine is now safely shut down

        Note:
            After shutdown, the engine cannot be restarted. Create a new
            instance if needed.

        """
        if self._initialized:
            await self.signal_manager.stop()
            log.info("TradingEngine shutdown complete")

    def process_signal(self, signal: TradingSignal) -> str:
        """Submit a trading signal for processing with timeout and risk management.

        This method queues a signal for asynchronous processing through the
        signal management system. The signal will be validated, risk-checked,
        and executed if all conditions are met.

        Args:
            signal: Trading signal containing market details, position size,
                   price, and execution parameters. Must include:
                   - market_slug: Target market identifier
                   - token_id: Specific token/outcome to trade
                   - side: "buy" or "sell"
                   - size: Position size in USD
                   - price: Execution price (0.0-1.0 for prediction markets)

        Returns:
            str: Unique signal identifier for tracking status and results.
                 Use get_signal_status() to monitor processing progress.

        Raises:
            ValueError: If signal data is invalid or incomplete
            RuntimeError: If engine is not initialized

        Example:
            >>> # Create and submit a trading signal
            >>> signal = TradingSignal(
            ...     market_slug="election-2024",
            ...     token_id="0x123...",
            ...     side="buy",
            ...     size=100.0,
            ...     price=0.65
            ... )
            >>>
            >>> signal_id = engine.process_signal(signal)
            >>> print(f"Signal submitted: {signal_id}")
            >>>
            >>> # Monitor processing
            >>> status = engine.get_signal_status(signal_id)
            >>> print(f"Signal status: {status}")

        Processing Flow:
            1. Signal validation and deduplication
            2. Risk assessment and position sizing
            3. Market liquidity and pricing checks
            4. Order generation and execution
            5. Portfolio state updates

        Note:
            This method returns immediately after queuing the signal.
            Processing occurs asynchronously with configured timeouts.

        """
        # Ensure database is initialized
        self._ensure_initialized()

        # Submit signal to manager for timeout handling and processing
        try:
            signal_id = self.signal_manager.submit_signal(signal)
            log.info(f"Signal {signal_id} submitted for processing")
            return str(signal_id)
        except Exception as e:
            log.error(f"Failed to submit signal: {e}")
            return ""

    def _process_signal_direct(self, signal: TradingSignal) -> None:
        """Process a signal directly (called by signal manager).
        This is the actual signal processing logic extracted from the original process_signal.
        """
        # Ensure database is initialized
        self._ensure_initialized()

        if not self.order_client.ready():
            log.warning("Order client not ready, cannot process signal.")
            return

        # Basic validation
        if signal.price <= 0 or signal.size <= 0:
            log.error(f"Invalid signal price or size: {signal}")
            return

        # Risk pre-flight check
        notional_value = signal.price * signal.size
        try:
            self.risk.preflight(
                signal.token_id, notional_value, signal.market_slug, signal.outcome_type
            )
        except (RuntimeError, ValueError) as e:
            log.error(f"Risk check failed for signal {signal.signal_id}: {e}")
            return

        # Execute trade
        log.info(f"Signal {signal.signal_id} passed risk checks, executing trade.")
        self.order_client.place_limit(
            signal.token_id,
            signal.side,
            signal.price,
            signal.size,
            "GTC",
            signal.market_slug,
            signal.outcome_type,
            notional_value,
            self.risk,
        )

    def get_signal_status(self, signal_id: str) -> str | None:
        """Get the current status of a signal by ID."""
        status = self.signal_manager.get_signal_status(signal_id)
        return status.value if status else None

    def get_signal_metrics(self) -> dict[str, Any]:
        """Get current signal processing metrics."""
        return self.signal_manager.get_metrics()

    def is_signal_manager_running(self) -> bool:
        """Check if the signal manager is running."""
        return bool(self.signal_manager._running)
