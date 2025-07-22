"""
Tests for CLI commands.

This module tests the various CLI commands in the InkedUp bot,
following the testing patterns established in the project.
"""

from unittest.mock import AsyncMock, Mock, patch

from typer.testing import CliRunner

from inkedup_bot.cli import app


class TestStatusCommand:
    """Test cases for the enhanced status CLI command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_status_command_healthy_all_systems(self) -> None:
        """Test status command with all systems healthy."""
        with (
            patch("inkedup_bot.cli.BotConfig") as mock_config,
            patch(
                "inkedup_bot.cli._check_database_health", new_callable=AsyncMock
            ) as mock_db_health,
            patch(
                "inkedup_bot.cli._check_scanner_status", new_callable=AsyncMock
            ) as mock_scanner_health,
            patch(
                "inkedup_bot.cli._check_portfolio_health", new_callable=AsyncMock
            ) as mock_portfolio_health,
            patch("inkedup_bot.cli._check_config_validity") as mock_config_validity,
            patch(
                "inkedup_bot.cli._get_recent_activity", new_callable=AsyncMock
            ) as mock_activity,
        ):

            # Mock healthy configuration
            mock_cfg = Mock()
            mock_cfg.api_base = "https://clob.polymarket.com"
            mock_cfg.ws_url = "wss://ws-subscriptions-clob.polymarket.com"
            mock_cfg.private_key = "test_private_key"
            mock_cfg.public_key = "test_public_key"
            mock_cfg.ws_enabled = True
            mock_cfg.mm_enabled = False
            mock_cfg.global_risk_cap = 1000.0
            mock_cfg.position_risk_cap = 100.0
            mock_cfg.market_risk_cap = 500.0
            mock_cfg.per_market_risk_cap = 250.0
            mock_cfg.per_outcome_risk_cap = 125.0
            mock_cfg.mm_target_spread_bps = 50.0
            mock_cfg.mm_max_position_size = 100.0
            mock_cfg.mm_quote_size = 10.0
            mock_cfg.mm_min_spread_bps = 20.0
            mock_cfg.mm_max_spread_bps = 5000.0
            mock_config.return_value = mock_cfg

            # Mock all health checks as healthy
            mock_db_health.return_value = (True, "Connected and operational")
            mock_scanner_health.return_value = (True, "Scanner service available")
            mock_portfolio_health.return_value = (True, "API connection successful")
            mock_config_validity.return_value = (True, [])  # No warnings
            mock_activity.return_value = {
                "open_orders": 0,
                "positions": 2,
                "last_activity": "2024-01-01 12:00:00",
            }

            result = self.runner.invoke(app, ["status"])

            assert result.exit_code == 0
            assert "InkedUp Bot Status" in result.stdout
            assert "✓ Connected" in result.stdout
            assert "✓ Available" in result.stdout
            assert "✓ Valid" in result.stdout
            assert "All systems healthy" in result.stdout

    def test_status_command_warning_conditions(self) -> None:
        """Test status command with warning conditions."""
        with (
            patch("inkedup_bot.cli.BotConfig") as mock_config,
            patch(
                "inkedup_bot.cli._check_database_health", new_callable=AsyncMock
            ) as mock_db_health,
            patch(
                "inkedup_bot.cli._check_scanner_status", new_callable=AsyncMock
            ) as mock_scanner_health,
            patch(
                "inkedup_bot.cli._check_portfolio_health", new_callable=AsyncMock
            ) as mock_portfolio_health,
            patch("inkedup_bot.cli._check_config_validity") as mock_config_validity,
            patch(
                "inkedup_bot.cli._get_recent_activity", new_callable=AsyncMock
            ) as mock_activity,
        ):

            # Mock configuration with warnings
            mock_cfg = Mock()
            mock_cfg.api_base = "https://clob.polymarket.com"
            mock_cfg.ws_url = "wss://ws-subscriptions-clob.polymarket.com"
            mock_cfg.private_key = None  # Missing credentials
            mock_cfg.public_key = None
            mock_cfg.ws_enabled = True
            mock_cfg.mm_enabled = False
            mock_cfg.global_risk_cap = 1000.0
            mock_cfg.position_risk_cap = 100.0
            mock_cfg.market_risk_cap = 500.0
            mock_cfg.per_market_risk_cap = 250.0
            mock_cfg.per_outcome_risk_cap = 125.0
            mock_config.return_value = mock_cfg

            # Mock mixed health checks
            mock_db_health.return_value = (True, "Connected and operational")
            mock_scanner_health.return_value = (
                False,
                "Scanner unavailable: Connection timeout",
            )
            mock_portfolio_health.return_value = (
                False,
                "Credentials not configured",
            )  # Portfolio API fails
            mock_config_validity.return_value = (
                True,
                ["Trading credentials not configured - bot will run in read-only mode"],
            )
            mock_activity.return_value = {"open_orders": 0, "positions": 0}

            result = self.runner.invoke(app, ["status"])

            assert result.exit_code == 2  # Critical error because portfolio fails
            assert "✗ Error" in result.stdout
            assert "Critical issues require attention" in result.stdout

    def test_status_command_critical_error(self) -> None:
        """Test status command with critical error conditions."""
        with (
            patch("inkedup_bot.cli.BotConfig") as mock_config,
            patch(
                "inkedup_bot.cli._check_database_health", new_callable=AsyncMock
            ) as mock_db_health,
            patch(
                "inkedup_bot.cli._check_scanner_status", new_callable=AsyncMock
            ) as mock_scanner_health,
            patch(
                "inkedup_bot.cli._check_portfolio_health", new_callable=AsyncMock
            ) as mock_portfolio_health,
            patch("inkedup_bot.cli._check_config_validity") as mock_config_validity,
            patch(
                "inkedup_bot.cli._get_recent_activity", new_callable=AsyncMock
            ) as mock_activity,
        ):

            # Mock configuration
            mock_cfg = Mock()
            mock_cfg.api_base = ""  # Invalid configuration
            mock_cfg.ws_url = ""
            mock_cfg.private_key = "test_key"
            mock_cfg.public_key = "test_key"
            mock_cfg.ws_enabled = True
            mock_cfg.mm_enabled = False
            mock_config.return_value = mock_cfg

            # Mock critical failures
            mock_db_health.return_value = (
                False,
                "Connection failed: Database not found",
            )
            mock_scanner_health.return_value = (True, "Scanner service available")
            mock_portfolio_health.return_value = (True, "API connection successful")
            mock_config_validity.return_value = (
                False,
                ["API base URL not configured", "WebSocket URL not configured"],
            )
            mock_activity.return_value = {}

            result = self.runner.invoke(app, ["status"])

            assert result.exit_code == 2  # Error exit code
            assert "✗ Error" in result.stdout
            assert "Critical issues require attention" in result.stdout

    def test_status_command_verbose_output(self) -> None:
        """Test status command with verbose flag."""
        with (
            patch("inkedup_bot.cli.BotConfig") as mock_config,
            patch(
                "inkedup_bot.cli._check_database_health", new_callable=AsyncMock
            ) as mock_db_health,
            patch(
                "inkedup_bot.cli._check_scanner_status", new_callable=AsyncMock
            ) as mock_scanner_health,
            patch(
                "inkedup_bot.cli._check_portfolio_health", new_callable=AsyncMock
            ) as mock_portfolio_health,
            patch("inkedup_bot.cli._check_config_validity") as mock_config_validity,
            patch(
                "inkedup_bot.cli._get_recent_activity", new_callable=AsyncMock
            ) as mock_activity,
        ):

            # Mock configuration with market making enabled
            mock_cfg = Mock()
            mock_cfg.api_base = "https://clob.polymarket.com"
            mock_cfg.ws_url = "wss://ws-subscriptions-clob.polymarket.com"
            mock_cfg.private_key = "test_key"
            mock_cfg.public_key = "test_key"
            mock_cfg.ws_enabled = True
            mock_cfg.mm_enabled = True  # Enable MM for verbose output test
            mock_cfg.global_risk_cap = 1000.0
            mock_cfg.position_risk_cap = 100.0
            mock_cfg.market_risk_cap = 500.0
            mock_cfg.per_market_risk_cap = 250.0
            mock_cfg.per_outcome_risk_cap = 125.0
            mock_cfg.mm_target_spread_bps = 50.0
            mock_cfg.mm_max_position_size = 100.0
            mock_cfg.mm_quote_size = 10.0
            mock_cfg.mm_min_spread_bps = 20.0
            mock_cfg.mm_max_spread_bps = 5000.0
            mock_config.return_value = mock_cfg

            # Mock healthy system
            mock_db_health.return_value = (True, "Connected and operational")
            mock_scanner_health.return_value = (True, "Scanner service available")
            mock_portfolio_health.return_value = (True, "API connection successful")
            mock_config_validity.return_value = (True, ["Minor warning about config"])
            mock_activity.return_value = {"open_orders": 1, "positions": 3}

            result = self.runner.invoke(app, ["status", "--verbose"])

            assert result.exit_code == 1  # Warning due to config warning
            assert "Risk Management Configuration" in result.stdout
            assert (
                "Market Making Configuration" in result.stdout
            )  # Should show MM config when enabled
            assert "Global Risk Cap" in result.stdout
            assert "Configuration Warnings" in result.stdout


class TestStatusHelperFunctions:
    """Test cases for status command helper functions."""

    def test_check_config_validity_healthy(self) -> None:
        """Test config validity check with healthy configuration."""
        from inkedup_bot.cli import _check_config_validity

        mock_cfg = Mock()
        mock_cfg.api_base = "https://clob.polymarket.com"
        mock_cfg.ws_url = "wss://ws-subscriptions-clob.polymarket.com"
        mock_cfg.private_key = "test_key"
        mock_cfg.public_key = "test_key"
        mock_cfg.mm_enabled = False
        mock_cfg.global_risk_cap = 1000.0

        is_valid, warnings = _check_config_validity(mock_cfg)

        assert is_valid is True
        assert len(warnings) == 0

    def test_check_config_validity_missing_critical(self) -> None:
        """Test config validity check with missing critical configuration."""
        from inkedup_bot.cli import _check_config_validity

        mock_cfg = Mock()
        mock_cfg.api_base = ""  # Missing critical config
        mock_cfg.ws_url = ""
        mock_cfg.private_key = None
        mock_cfg.public_key = None
        mock_cfg.mm_enabled = False
        mock_cfg.global_risk_cap = 1000.0

        is_valid, warnings = _check_config_validity(mock_cfg)

        assert is_valid is False
        assert "API base URL not configured" in warnings
        assert "WebSocket URL not configured" in warnings

    def test_check_config_validity_warnings(self) -> None:
        """Test config validity check with warning conditions."""
        from inkedup_bot.cli import _check_config_validity

        mock_cfg = Mock()
        mock_cfg.api_base = "https://clob.polymarket.com"
        mock_cfg.ws_url = "wss://ws-subscriptions-clob.polymarket.com"
        mock_cfg.private_key = None  # Missing credentials
        mock_cfg.public_key = None
        mock_cfg.mm_enabled = True  # MM enabled but bad config
        mock_cfg.mm_max_position_size = 0  # Invalid MM config
        mock_cfg.mm_quote_size = -1
        mock_cfg.mm_min_spread_bps = 100
        mock_cfg.mm_max_spread_bps = 50  # Min > Max
        mock_cfg.global_risk_cap = 0

        is_valid, warnings = _check_config_validity(mock_cfg)

        assert is_valid is True  # Non-critical warnings
        assert len(warnings) >= 3
        assert any("Trading credentials not configured" in w for w in warnings)
        assert any(
            "Market making enabled but position/quote sizes" in w for w in warnings
        )
        assert any("min spread >= max spread" in w for w in warnings)

    @patch("inkedup_bot.cli.DatabaseManager")
    async def test_check_database_health_success(self, mock_db_manager: Mock) -> None:
        """Test database health check success."""
        from inkedup_bot.cli import _check_database_health

        # Mock successful database operations
        mock_db = Mock()
        mock_conn = AsyncMock()
        mock_db.initialize = AsyncMock()
        mock_db.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.connection.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock()
        mock_db_manager.return_value = mock_db

        healthy, status = await _check_database_health()

        assert healthy is True
        assert "Connected and operational" in status
        mock_db.initialize.assert_called_once()

    @patch("inkedup_bot.cli.DatabaseManager")
    async def test_check_database_health_failure(self, mock_db_manager: Mock) -> None:
        """Test database health check failure."""
        from inkedup_bot.cli import _check_database_health

        # Mock database failure
        mock_db_manager.side_effect = Exception("Connection timeout")

        healthy, status = await _check_database_health()

        assert healthy is False
        assert "Connection failed" in status
        assert "Connection timeout" in status

    @patch("inkedup_bot.cli.Scanner")
    async def test_check_scanner_status_success(self, mock_scanner_class: Mock) -> None:
        """Test scanner status check success."""
        from inkedup_bot.cli import _check_scanner_status

        # Mock successful scanner initialization
        mock_scanner = Mock()
        mock_scanner.cfg = Mock()  # Has cfg attribute
        mock_scanner_class.return_value = mock_scanner

        mock_cfg = Mock()
        healthy, status = await _check_scanner_status(mock_cfg)

        assert healthy is True
        assert "Scanner service available" in status
        mock_scanner_class.assert_called_once_with(mock_cfg)

    @patch("inkedup_bot.cli.Scanner")
    async def test_check_scanner_status_failure(self, mock_scanner_class: Mock) -> None:
        """Test scanner status check failure."""
        from inkedup_bot.cli import _check_scanner_status

        # Mock scanner initialization failure
        mock_scanner_class.side_effect = Exception("Import error")

        mock_cfg = Mock()
        healthy, status = await _check_scanner_status(mock_cfg)

        assert healthy is False
        assert "Scanner unavailable" in status
        assert "Import error" in status

    @patch("inkedup_bot.cli.StateManager")
    async def test_get_recent_activity_success(self, mock_state_manager: Mock) -> None:
        """Test recent activity retrieval success."""
        from inkedup_bot.cli import _get_recent_activity

        # Mock successful state access
        mock_state = Mock()
        mock_state.open_orders = {"order1": {}, "order2": {}}
        mock_state.positions = {"pos1": {}}
        mock_state_manager.return_value = mock_state

        activity = await _get_recent_activity()

        assert "open_orders" in activity
        assert "positions" in activity
        assert activity["open_orders"] == 2
        assert activity["positions"] == 1

    @patch("inkedup_bot.cli.StateManager")
    async def test_get_recent_activity_failure(self, mock_state_manager: Mock) -> None:
        """Test recent activity retrieval failure."""
        from inkedup_bot.cli import _get_recent_activity

        # Mock state manager failure
        mock_state_manager.side_effect = Exception("Database error")

        activity = await _get_recent_activity()

        assert activity == {}  # Returns empty dict on failure


class TestPortfolioCommand:
    """Test cases for the portfolio CLI command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_portfolio_command_valid_config(self) -> None:
        """Test the portfolio command with a valid configuration."""
        with (
            patch("inkedup_bot.cli.BotConfig") as mock_config,
            patch("inkedup_bot.cli.OrderClient") as mock_order_client,
        ):
            mock_cfg = Mock()
            mock_cfg.private_key = "test-key"
            mock_cfg.public_key = "test-public-key"
            mock_config.return_value = mock_cfg

            mock_oc_instance = mock_order_client.return_value
            mock_oc_instance.ready.return_value = True
            mock_oc_instance.get_positions.return_value = [
                {"symbol": "TEST-YES", "size": 100, "usd_value": 50.0},
                {"symbol": "TEST-NO", "size": -100, "usd_value": -50.0},
            ]

            result = self.runner.invoke(app, ["portfolio"])

            assert result.exit_code == 0
            assert "Portfolio Summary" in result.stdout
            assert "Total Portfolio Value: $0.00" in result.stdout
            assert "Active Positions" in result.stdout
            assert "TEST-YES" in result.stdout

    def test_portfolio_command_no_credentials(self) -> None:
        """Test the portfolio command when credentials are not configured."""
        with patch("inkedup_bot.cli.BotConfig") as mock_config:
            mock_cfg = Mock()
            mock_cfg.private_key = None
            mock_cfg.public_key = None
            mock_config.return_value = mock_cfg

            result = self.runner.invoke(app, ["portfolio"])

            assert result.exit_code == 1
            assert "Trading client not ready" in result.stdout
            assert "Please ensure `PRIVATE_KEY`" in result.stdout

    def test_portfolio_command_api_error(self) -> None:
        """Test the portfolio command when the API call fails."""
        with (
            patch("inkedup_bot.cli.BotConfig") as mock_config,
            patch("inkedup_bot.cli.OrderClient") as mock_order_client,
        ):
            mock_cfg = Mock()
            mock_cfg.private_key = "test-key"
            mock_config.return_value = mock_cfg

            mock_oc_instance = mock_order_client.return_value
            mock_oc_instance.ready.return_value = True
            mock_oc_instance.get_positions.side_effect = Exception("API Unavailable")

            result = self.runner.invoke(app, ["portfolio"])

            assert result.exit_code == 1
            assert "Failed to fetch portfolio" in result.stdout
            assert "API Unavailable" in result.stdout
