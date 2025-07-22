"""
Example: Strategy Pattern Implementation

This example demonstrates how to implement a new trading strategy
for the InkedUp bot following the established pattern.
"""

from typing import Any

from inkedup_bot.strategies.base import Strategy


class ExampleStrategy(Strategy):
    """
    Example strategy that demonstrates the preferred implementation pattern.

    This strategy serves as a template for creating new trading strategies.
    It shows how to:
    - Inherit from the base Strategy class
    - Implement the required evaluate method
    - Handle market data analysis
    - Return trading actions
    """

    def __init__(self, threshold: float = 0.05):
        """
        Initialize the strategy with configuration parameters.

        Args:
            threshold: Example threshold parameter for decision making
        """
        self.threshold = threshold

    def evaluate(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Evaluate market data and return potential trading actions.

        Args:
            rows: List of market data rows from the scanner

        Returns:
            List of trading actions to execute
        """
        actions = []

        for row in rows:
            # Example analysis logic
            if self._should_trade(row):
                action = self._create_trade_action(row)
                actions.append(action)

        return actions

    def _should_trade(self, row: dict[str, Any]) -> bool:
        """
        Determine if a trade should be executed based on market data.

        Args:
            row: Market data row

        Returns:
            True if trade should be executed, False otherwise
        """
        # Example decision logic
        spread = row.get("spread_bps", 0)
        volume = row.get("volume_24h", 0)

        return bool(spread > self.threshold and volume > 1000)

    def _create_trade_action(self, row: dict[str, Any]) -> dict[str, Any]:
        """
        Create a trading action based on market analysis.

        Args:
            row: Market data row

        Returns:
            Dictionary representing the trading action
        """
        return {
            "action": "place_order",
            "market_id": row.get("market_id"),
            "side": "buy",  # or 'sell'
            "amount": 100,  # Calculate based on strategy
            "price": row.get("best_bid", 0) + 0.01,  # Example pricing logic
        }
