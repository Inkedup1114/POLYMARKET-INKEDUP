"""Base strategy classes and interfaces for trading strategy implementation.

This module provides the foundational abstract base classes and interfaces
that all trading strategies in the InkedUp bot must implement. It defines
the standard contract for strategy evaluation and signal generation.

The strategy system provides:
- Abstract base class for consistent strategy interfaces
- Standard evaluation method signatures
- Type safety for strategy implementations
- Integration points with the trading engine
- No-operation strategy for testing and defaults

Key Components:
    - Strategy: Abstract base class defining the strategy interface
    - NoOpStrategy: Default implementation that takes no actions

Architecture:
    All strategies follow a common pattern:
    1. Receive market data (order book rows) from scanner
    2. Evaluate market conditions and identify opportunities
    3. Return list of trading signals or actions
    4. Let the trading engine handle risk management and execution

Examples:
    Implementing a custom strategy:

    >>> from inkedup_bot.strategies.base import Strategy
    >>> from inkedup_bot.signals import TradingSignal
    >>> from typing import Any
    >>>
    >>> class SimpleArbitrageStrategy(Strategy):
    ...     def evaluate(self, rows: list[dict[str, Any]]) -> list[TradingSignal]:
    ...         signals = []
    ...         for row in rows:
    ...             # Check for arbitrage opportunities
    ...             if self._is_arbitrage_opportunity(row):
    ...                 signal = TradingSignal(
    ...                     market_slug=row["market_slug"],
    ...                     token_id=row["token_id"],
    ...                     side="buy",
    ...                     price=row["ask"],
    ...                     size=100.0
    ...                 )
    ...                 signals.append(signal)
    ...         return signals
    >>>
    >>> # Use with trading engine
    >>> strategy = SimpleArbitrageStrategy()
    >>> market_data = scanner.get_market_data()
    >>> signals = strategy.evaluate(market_data)

Design Patterns:
    The strategy system follows the Strategy pattern from Gang of Four
    design patterns, enabling runtime strategy selection and composition.
    This allows for flexible trading system configuration and testing.

Integration:
    Strategies integrate with the broader trading system through:
    - Scanner: Provides market data input
    - TradingEngine: Processes strategy outputs
    - RiskManager: Validates and sizes positions
    - OrderClient: Executes trading decisions

"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Strategy(ABC):
    """Abstract base class for all trading strategies.

    The Strategy class defines the standard interface that all trading strategies
    must implement. It ensures consistent behavior across different strategy
    implementations and provides type safety for the trading system.

    All strategies follow a common evaluation pattern:
    1. Receive current market data from the scanner
    2. Analyze data for trading opportunities
    3. Generate and return trading signals
    4. Let downstream components handle execution

    Examples:
        Implement a simple momentum strategy:

        >>> class MomentumStrategy(Strategy):
        ...     def __init__(self, threshold: float = 0.05):
        ...         self.threshold = threshold
        ...
        ...     def evaluate(self, rows: list[dict[str, Any]]) -> list[TradingSignal]:
        ...         signals = []
        ...         for row in rows:
        ...             if self._detect_momentum(row):
        ...                 signal = self._create_momentum_signal(row)
        ...                 signals.append(signal)
        ...         return signals

        Use with no-operation for testing:

        >>> noop_strategy = NoOpStrategy()
        >>> result = noop_strategy.evaluate(market_data)
        >>> assert result == []  # No signals generated

    Thread Safety:
        Strategy implementations should be thread-safe if they maintain
        internal state. The evaluate method may be called concurrently
        from different market scanning cycles.

    Performance:
        Strategies should be efficient in their evaluate methods as they
        are called frequently during market scanning. Heavy computations
        should be cached or moved to background processes when possible.

    """

    @abstractmethod
    def evaluate(self, rows: list[dict[str, Any]]) -> list[Any]:
        """Evaluate market data and generate trading signals.

        This method is called by the trading system with current market
        data from the scanner. Implementations should analyze the data
        and return appropriate trading signals or actions.

        Args:
            rows: List of market data dictionaries from the scanner.
                  Each row typically contains order book information,
                  market identifiers, prices, and other market state.

        Returns:
            List of trading signals, actions, or other outputs that
            should be processed by the trading engine. Common return
            types include TradingSignal, SpreadSignal, ComplementSignal.

        Examples:
            Basic strategy evaluation:

            >>> def evaluate(self, rows):
            ...     signals = []
            ...     for row in rows:
            ...         if row.get("spread_bps", 0) > 1000:  # > 10%
            ...             signal = SpreadSignal(
            ...                 market_slug=row["market_slug"],
            ...                 token_id=row["token_id"],
            ...                 bid=row["bid"],
            ...                 ask=row["ask"],
            ...                 spread_bps=row["spread_bps"]
            ...             )
            ...             signals.append(signal)
            ...     return signals

        Note:
            This method should not perform any side effects like placing
            orders directly. All trading actions should be communicated
            through the returned signals for proper risk management.

        """
        ...


class NoOpStrategy(Strategy):
    """No-operation strategy that generates no trading signals.

    The NoOpStrategy provides a default implementation that takes no trading
    actions. It's useful for testing, as a safe default, or when temporarily
    disabling trading while keeping the system running.

    This strategy can be used to:
    - Test the trading system without actual trading
    - Provide a safe fallback during system issues
    - Serve as a base template for new strategies
    - Disable trading while maintaining data collection

    Examples:
        Use as a safe default:

        >>> strategy = NoOpStrategy()
        >>> signals = strategy.evaluate(market_data)
        >>> assert len(signals) == 0
        >>>
        >>> # System continues running without trading
        >>> engine.set_strategy(strategy)  # Safe mode

        Testing system components:

        >>> # Test scanner and engine without trading
        >>> test_strategy = NoOpStrategy()
        >>> market_data = scanner.scan_markets()
        >>> result = test_strategy.evaluate(market_data)
        >>> # Verify system processes data correctly

    Thread Safety:
        NoOpStrategy is completely thread-safe as it maintains no state
        and performs no operations beyond returning an empty list.

    """

    def evaluate(self, rows: list[dict[str, Any]]) -> list[Any]:
        """Evaluate market data and return no signals (no-op).

        Args:
            rows: Market data from scanner (ignored)

        Returns:
            Empty list (no trading signals generated)

        """
        return []
