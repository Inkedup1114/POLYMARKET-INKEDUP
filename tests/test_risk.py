import unittest
from unittest.mock import MagicMock

from inkedup_bot.config import BotConfig
from inkedup_bot.risk import RiskManager
from inkedup_bot.state import StateManager


class TestRiskManager(unittest.TestCase):

    def setUp(self) -> None:
        """Set up a mock environment for each test."""
        self.cfg = BotConfig(
            global_risk_cap=1000.0,
            position_risk_cap=100.0,
            per_market_risk_cap=500.0,
            per_outcome_risk_cap=250.0,
        )
        self.order_client = MagicMock()
        self.state = MagicMock(spec=StateManager)
        self.risk = RiskManager(self.cfg, self.order_client, self.state)

    def test_preflight_invalid_notional(self) -> None:
        """Test that preflight fails if intended_notional is zero or negative."""
        self.order_client.ready.return_value = True

        with self.assertRaisesRegex(ValueError, "Intended notional must be positive"):
            self.risk.preflight("token1", 0)

        with self.assertRaisesRegex(ValueError, "Intended notional must be positive"):
            self.risk.preflight("token1", -100)

    def test_preflight_order_client_not_ready(self) -> None:
        """Test that preflight fails if the order client is not ready."""
        self.order_client.ready.return_value = False
        with self.assertRaisesRegex(RuntimeError, "Order client not ready"):
            self.risk.preflight("token1", 10.0)

    def test_global_risk_cap_exceeded(self) -> None:
        """Test that preflight fails when the global risk cap is exceeded."""
        self.order_client.ready.return_value = True
        self.state.get_total_exposure.return_value = self.cfg.global_risk_cap - 50
        with self.assertRaisesRegex(RuntimeError, "Global cap exceeded"):
            self.risk.preflight("token1", 51)

    def test_position_risk_cap_exceeded(self) -> None:
        """Test that preflight fails when the per-position risk cap is exceeded."""
        self.order_client.ready.return_value = True
        self.state.get_total_exposure.return_value = 0
        self.state.get_position_notional.return_value = self.cfg.position_risk_cap - 50
        with self.assertRaisesRegex(RuntimeError, "Per-position cap exceeded"):
            self.risk.preflight("token1", 51)

    def test_market_risk_cap_exceeded(self) -> None:
        """Test that preflight fails when the per-market risk cap is exceeded."""
        self.order_client.ready.return_value = True
        self.state.get_total_exposure.return_value = 0
        self.state.get_position_notional.return_value = 0
        self.state.get_market_exposure.return_value = self.cfg.per_market_risk_cap - 50
        with self.assertRaisesRegex(RuntimeError, "Per-market cap exceeded"):
            self.risk.preflight("token1", 51, "market1")

    def test_outcome_risk_cap_exceeded(self) -> None:
        """Test that preflight fails when the per-outcome risk cap is exceeded."""
        self.order_client.ready.return_value = True
        self.state.get_total_exposure.return_value = 0
        self.state.get_position_notional.return_value = 0
        self.state.get_market_exposure.return_value = 0
        self.state.get_outcome_exposure.return_value = (
            self.cfg.per_outcome_risk_cap - 50
        )
        with self.assertRaisesRegex(RuntimeError, "Per-outcome cap exceeded"):
            self.risk.preflight("token1", 51, "market1", "outcome1")


if __name__ == "__main__":
    unittest.main()
