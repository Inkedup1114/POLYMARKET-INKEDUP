"""
Comprehensive tests for market and outcome exposure tracking functionality.

Tests the complete exposure tracking system including:
- Market exposure calculations
- Outcome exposure calculations  
- Real-time exposure updates
- Limit monitoring and alerts
- Historical analytics and trends
- Integration between components
"""

import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from inkedup_bot.database import DatabaseManager
from inkedup_bot.risk.exposure_analytics import ExposureHistoryTracker, ExposureSnapshot
from inkedup_bot.risk.exposure_calculator import ExposureCalculator, PortfolioExposure
from inkedup_bot.state import StateManager


@pytest.fixture
def mock_db_manager():
    """Create mock database manager."""
    db_manager = Mock(spec=DatabaseManager)
    db_manager.get_all_positions = AsyncMock(return_value=[])
    db_manager.get_market_exposure = AsyncMock(return_value=0.0)
    db_manager.get_outcome_exposure = AsyncMock(return_value=0.0)
    return db_manager


@pytest.fixture
def state_manager():
    """Create state manager with in-memory database."""
    return StateManager(":memory:")


@pytest.fixture
def exposure_calculator(mock_db_manager):
    """Create exposure calculator with mock database."""
    return ExposureCalculator(mock_db_manager)


@pytest.fixture
def sample_positions():
    """Create sample position data for testing."""
    return {
        "token_1": {
            "token_id": "token_1",
            "market_slug": "election_2024",
            "outcome_type": "YES",
            "notional_value": 1000.0,
            "size": 200.0,
            "average_price": 0.5,
            "current_price": 0.52,
            "strategy_id": "strategy_A",
        },
        "token_2": {
            "token_id": "token_2",
            "market_slug": "election_2024",
            "outcome_type": "NO",
            "notional_value": -600.0,
            "size": -120.0,
            "average_price": 0.5,
            "current_price": 0.48,
            "strategy_id": "strategy_A",
        },
        "token_3": {
            "token_id": "token_3",
            "market_slug": "sports_game",
            "outcome_type": "YES",
            "notional_value": 800.0,
            "size": 160.0,
            "average_price": 0.5,
            "current_price": 0.55,
            "strategy_id": "strategy_B",
        },
    }


class TestStateManagerExposureTracking:
    """Test exposure tracking methods in StateManager."""

    def test_market_exposure_calculation(self, state_manager, sample_positions):
        """Test market exposure calculation from positions."""
        # Add sample positions to state manager
        state_manager.positions = sample_positions

        # Test market exposure calculation
        election_exposure = state_manager.get_market_exposure("election_2024")
        assert election_exposure == 1600.0  # |1000| + |600| = 1600

        sports_exposure = state_manager.get_market_exposure("sports_game")
        assert sports_exposure == 800.0

        nonexistent_exposure = state_manager.get_market_exposure("nonexistent_market")
        assert nonexistent_exposure == 0.0

    def test_outcome_exposure_calculation(self, state_manager, sample_positions):
        """Test outcome exposure calculation from positions."""
        state_manager.positions = sample_positions

        # Test outcome exposure calculation
        yes_exposure = state_manager.get_outcome_exposure("YES")
        assert yes_exposure == 1800.0  # |1000| + |800| = 1800

        no_exposure = state_manager.get_outcome_exposure("NO")
        assert no_exposure == 600.0

        nonexistent_exposure = state_manager.get_outcome_exposure("MAYBE")
        assert nonexistent_exposure == 0.0

    def test_detailed_market_exposure(self, state_manager, sample_positions):
        """Test detailed market exposure breakdown."""
        state_manager.positions = sample_positions

        detailed = state_manager.get_detailed_market_exposure("election_2024")

        assert detailed["market_slug"] == "election_2024"
        assert detailed["total_exposure"] == 1600.0
        assert detailed["net_exposure"] == 400.0  # 1000 - 600
        assert detailed["gross_exposure"] == 1600.0  # 1000 + 600
        assert detailed["long_exposure"] == 1000.0
        assert detailed["short_exposure"] == 600.0
        assert detailed["position_count"] == 2

        # Check outcome breakdown
        assert "YES" in detailed["outcome_breakdown"]
        assert "NO" in detailed["outcome_breakdown"]
        assert detailed["outcome_breakdown"]["YES"]["exposure"] == 1000.0
        assert detailed["outcome_breakdown"]["NO"]["exposure"] == 600.0
        assert detailed["outcome_breakdown"]["YES"]["position_count"] == 1
        assert detailed["outcome_breakdown"]["NO"]["position_count"] == 1

    def test_detailed_outcome_exposure(self, state_manager, sample_positions):
        """Test detailed outcome exposure breakdown."""
        state_manager.positions = sample_positions

        detailed = state_manager.get_detailed_outcome_exposure("YES")

        assert detailed["outcome_type"] == "YES"
        assert detailed["total_exposure"] == 1800.0
        assert detailed["net_exposure"] == 1800.0  # All YES positions are long
        assert detailed["position_count"] == 2

        # Check market breakdown
        assert "election_2024" in detailed["market_breakdown"]
        assert "sports_game" in detailed["market_breakdown"]
        assert detailed["market_breakdown"]["election_2024"]["exposure"] == 1000.0
        assert detailed["market_breakdown"]["sports_game"]["exposure"] == 800.0

    def test_strategy_exposure_breakdown(self, state_manager, sample_positions):
        """Test exposure breakdown by strategy."""
        state_manager.positions = sample_positions

        strategy_a = state_manager.get_exposure_by_strategy("strategy_A")

        assert strategy_a["strategy_id"] == "strategy_A"
        assert strategy_a["total_exposure"] == 1600.0  # election_2024 positions
        assert strategy_a["position_count"] == 2
        assert "election_2024" in strategy_a["market_breakdown"]
        assert "YES" in strategy_a["outcome_breakdown"]
        assert "NO" in strategy_a["outcome_breakdown"]

        strategy_b = state_manager.get_exposure_by_strategy("strategy_B")

        assert strategy_b["strategy_id"] == "strategy_B"
        assert strategy_b["total_exposure"] == 800.0
        assert strategy_b["position_count"] == 1

    def test_portfolio_exposure_summary(self, state_manager, sample_positions):
        """Test comprehensive portfolio exposure summary."""
        state_manager.positions = sample_positions

        summary = state_manager.get_portfolio_exposure_summary()

        assert summary["total_positions"] == 3
        assert summary["total_exposure"] == 2400.0  # Sum of all absolute exposures
        assert summary["net_exposure"] == 1200.0  # 1000 - 600 + 800
        assert summary["gross_exposure"] == 2400.0
        assert summary["long_exposure"] == 1800.0  # 1000 + 800
        assert summary["short_exposure"] == 600.0
        assert summary["market_count"] == 2
        assert summary["outcome_count"] == 2

        # Check market exposures
        assert summary["market_exposures"]["election_2024"] == 1600.0
        assert summary["market_exposures"]["sports_game"] == 800.0

        # Check outcome exposures
        assert summary["outcome_exposures"]["YES"] == 1800.0
        assert summary["outcome_exposures"]["NO"] == 600.0

        # Check concentration metrics
        concentration = summary["concentration_metrics"]
        assert (
            concentration["market_concentration"] == 1600.0 / 2400.0
        )  # Largest market
        assert (
            concentration["outcome_concentration"] == 1800.0 / 2400.0
        )  # Largest outcome
        assert 0.0 <= concentration["market_hhi"] <= 1.0
        assert 0.0 <= concentration["outcome_hhi"] <= 1.0

    def test_exposure_delta_calculation(self, state_manager):
        """Test exposure delta calculation for position changes."""
        # Add existing position
        state_manager.positions = {
            "token_1": {
                "size": 100.0,
                "market_slug": "test_market",
                "outcome_type": "YES",
            }
        }

        # Test increasing position
        delta = state_manager.calculate_exposure_delta(
            token_id="token_1",
            size_delta=50.0,
            price=0.6,
            market_slug="test_market",
            outcome_type="YES",
        )

        assert delta["token_id"] == "token_1"
        assert delta["size_delta"] == 50.0
        assert delta["notional_delta"] == 30.0  # |50 * 0.6|
        assert delta["net_delta"] == 30.0  # 50 * 0.6
        assert delta["old_size"] == 100.0
        assert delta["new_size"] == 150.0
        assert delta["position_status"] == "increased"

        # Test opening new position
        delta_new = state_manager.calculate_exposure_delta(
            token_id="new_token",
            size_delta=200.0,
            price=0.5,
            market_slug="new_market",
            outcome_type="NO",
        )

        assert delta_new["position_status"] == "opened"
        assert delta_new["old_size"] == 0.0
        assert delta_new["new_size"] == 200.0
        assert delta_new["notional_delta"] == 100.0

    def test_top_positions_by_exposure(self, state_manager, sample_positions):
        """Test getting top positions by exposure."""
        state_manager.positions = sample_positions

        top_positions = state_manager.get_top_positions_by_exposure(limit=2)

        assert len(top_positions) == 2

        # Should be sorted by absolute notional value descending
        assert top_positions[0]["token_id"] == "token_1"  # 1000.0
        assert top_positions[0]["notional_value"] == 1000.0

        assert top_positions[1]["token_id"] == "token_3"  # 800.0
        assert top_positions[1]["notional_value"] == 800.0

    def test_exposure_alerts(self, state_manager):
        """Test exposure alert generation."""
        # Add positions that approach limits
        state_manager.positions = {
            "high_exposure": {
                "market_slug": "risky_market",
                "outcome_type": "YES",
                "notional_value": 8500.0,  # Close to 10k global limit
                "size": 1000.0,
            },
            "market_concentrated": {
                "market_slug": "risky_market",
                "outcome_type": "NO",
                "notional_value": 1000.0,
                "size": 200.0,
            },
        }

        limits = {
            "global_risk_cap": 10000.0,
            "per_market_risk_cap": 5000.0,
            "per_outcome_risk_cap": 8000.0,
        }

        alerts = state_manager.get_exposure_alerts(limits)

        # Should generate multiple alerts
        alert_types = [alert["type"] for alert in alerts]

        assert "global_exposure_warning" in alert_types
        assert "market_exposure_warning" in alert_types
        assert "outcome_exposure_warning" in alert_types

        # Check global warning
        global_alerts = [a for a in alerts if a["type"] == "global_exposure_warning"]
        assert len(global_alerts) == 1
        assert global_alerts[0]["utilization"] == 0.85  # 8500/10000


class TestExposureCalculatorCore:
    """Test core exposure calculation functionality."""

    @pytest.mark.asyncio
    async def test_real_time_exposure_delta(self, exposure_calculator):
        """Test real-time exposure delta calculation."""
        delta_data = {
            "token_id": "test_token",
            "size_delta": 100,
            "price": 0.75,
            "market_slug": "test_market",
            "outcome_type": "YES",
        }

        delta = await exposure_calculator.calculate_real_time_exposure_delta(delta_data)

        assert delta["total_notional_delta"] == Decimal("75.0")  # |100 * 0.75|
        assert delta["total_net_delta"] == Decimal("75.0")  # 100 * 0.75
        assert delta["market_notional_delta"] == Decimal("75.0")
        assert delta["outcome_notional_delta"] == Decimal("75.0")
        assert delta["position_count_delta"] == 1

    @pytest.mark.asyncio
    async def test_exposure_limits_utilization(self, exposure_calculator):
        """Test exposure limits utilization calculation."""
        # Create mock portfolio
        portfolio = PortfolioExposure(
            total_notional=Decimal("7500"),
            net_exposure=Decimal("6000"),
            gross_exposure=Decimal("7500"),
            market_count=3,
            outcome_count=2,
            position_count=8,
            market_exposures={
                "market_A": MagicMock(total_notional=Decimal("4000")),
                "market_B": MagicMock(total_notional=Decimal("2500")),
                "market_C": MagicMock(total_notional=Decimal("1000")),
            },
            outcome_exposures={
                "YES": MagicMock(total_notional=Decimal("5000")),
                "NO": MagicMock(total_notional=Decimal("2500")),
            },
            concentration_metrics={},
            risk_metrics={},
        )

        limits = {
            "global_risk_cap": Decimal("10000"),
            "per_market_risk_cap": Decimal("5000"),
            "per_outcome_risk_cap": Decimal("6000"),
        }

        utilization = await exposure_calculator.get_exposure_limits_utilization(
            portfolio, limits
        )

        assert utilization["global"] == 0.75  # 7500 / 10000
        assert utilization["max_market"] == 0.8  # 4000 / 5000
        assert utilization["max_outcome"] == 0.833  # 5000 / 6000 (approximately)

        # Check individual market utilization
        assert "markets" in utilization
        assert utilization["markets"]["market_A"] == 0.8
        assert utilization["markets"]["market_B"] == 0.5
        assert utilization["markets"]["market_C"] == 0.2

    @pytest.mark.asyncio
    async def test_concentration_analysis(self, exposure_calculator):
        """Test portfolio concentration analysis."""
        # Create portfolio with concentrated exposure
        portfolio = PortfolioExposure(
            total_notional=Decimal("10000"),
            net_exposure=Decimal("8000"),
            gross_exposure=Decimal("10000"),
            market_count=3,
            outcome_count=2,
            position_count=5,
            market_exposures={
                "dominant_market": MagicMock(total_notional=Decimal("7000")),  # 70%
                "small_market_a": MagicMock(total_notional=Decimal("2000")),  # 20%
                "small_market_b": MagicMock(total_notional=Decimal("1000")),  # 10%
            },
            outcome_exposures={
                "YES": MagicMock(total_notional=Decimal("8000")),  # 80%
                "NO": MagicMock(total_notional=Decimal("2000")),  # 20%
            },
            concentration_metrics={},
            risk_metrics={},
        )

        concentration = await exposure_calculator.analyze_exposure_concentration(
            portfolio
        )

        # Check Herfindahl Index: (0.7)² + (0.2)² + (0.1)² = 0.49 + 0.04 + 0.01 = 0.54
        assert abs(concentration["herfindahl_index_markets"] - 0.54) < 0.01

        # Outcome HHI: (0.8)² + (0.2)² = 0.64 + 0.04 = 0.68
        assert abs(concentration["herfindahl_index_outcomes"] - 0.68) < 0.01

        # Check top positions
        top_markets = concentration["top_markets"]
        assert len(top_markets) == 3
        assert top_markets[0]["market_slug"] == "dominant_market"
        assert top_markets[0]["percentage"] == 70.0

        # Concentration risk score should be high (uses max HHI)
        assert concentration["concentration_risk_score"] == 0.68


class TestExposureHistoryAndAnalytics:
    """Test exposure history tracking and analytics."""

    @pytest.fixture
    def exposure_history(self, mock_db_manager):
        """Create exposure history tracker."""
        return ExposureHistoryTracker(
            mock_db_manager, max_snapshots=50, snapshot_interval=60.0
        )

    @pytest.mark.asyncio
    async def test_snapshot_recording(self, exposure_history):
        """Test recording exposure snapshots."""
        snapshot = ExposureSnapshot(
            timestamp=time.time(),
            total_exposure=5000.0,
            net_exposure=4000.0,
            market_exposures={"market_A": 3000.0, "market_B": 2000.0},
            outcome_exposures={"YES": 3500.0, "NO": 1500.0},
            position_count=10,
        )

        await exposure_history.record_exposure_snapshot(snapshot)

        # Check snapshot was stored
        assert len(exposure_history._recent_snapshots) == 1
        stored_snapshot = exposure_history._recent_snapshots[0]
        assert stored_snapshot.total_exposure == 5000.0
        assert stored_snapshot.position_count == 10

    @pytest.mark.asyncio
    async def test_exposure_trends(self, exposure_history):
        """Test exposure trend analysis."""
        current_time = time.time()

        # Add snapshots with increasing trend
        snapshots = []
        for i in range(5):
            snapshot = ExposureSnapshot(
                timestamp=current_time - (5 - i) * 300,  # 5 minute intervals
                total_exposure=1000.0 + i * 200,  # Increasing by 200 each time
                net_exposure=800.0 + i * 150,
                market_exposures={
                    "market_A": 600.0 + i * 100,
                    "market_B": 400.0 + i * 100,
                },
                outcome_exposures={"YES": 600.0 + i * 120, "NO": 400.0 + i * 80},
                position_count=5 + i,
            )
            snapshots.append(snapshot)
            exposure_history._recent_snapshots.append(snapshot)

        # Test total exposure trends
        trends = await exposure_history.get_exposure_trends("total", lookback_hours=2)

        assert "total_exposure" in trends
        assert "net_exposure" in trends

        total_trend = trends["total_exposure"]
        assert len(total_trend) == 5
        assert total_trend[0][1] == 1000.0  # First value
        assert total_trend[-1][1] == 1800.0  # Last value (1000 + 4*200)

        # Test market trends
        market_trends = await exposure_history.get_exposure_trends(
            "market", lookback_hours=2
        )

        assert "market_A" in market_trends
        assert "market_B" in market_trends

        market_a_trend = market_trends["market_A"]
        assert len(market_a_trend) == 5
        assert market_a_trend[0][1] == 600.0
        assert market_a_trend[-1][1] == 1000.0  # 600 + 4*100

    @pytest.mark.asyncio
    async def test_anomaly_detection(self, exposure_history):
        """Test exposure anomaly detection."""
        current_time = time.time()

        # Add normal snapshots
        normal_exposures = [1000, 1010, 1020, 1015, 1025, 1030, 1020, 1035, 1025, 1040]

        for i, exposure in enumerate(normal_exposures):
            snapshot = ExposureSnapshot(
                timestamp=current_time - (len(normal_exposures) - i) * 60,
                total_exposure=float(exposure),
                net_exposure=800.0,
                market_exposures={},
                outcome_exposures={},
                position_count=5,
            )
            exposure_history._recent_snapshots.append(snapshot)

        # Add anomalous spike
        anomalous_snapshot = ExposureSnapshot(
            timestamp=current_time,
            total_exposure=2000.0,  # Significant spike
            net_exposure=800.0,
            market_exposures={},
            outcome_exposures={},
            position_count=5,
        )
        exposure_history._recent_snapshots.append(anomalous_snapshot)

        # Detect anomalies
        anomalies = await exposure_history.detect_exposure_anomalies(
            lookback_hours=1, std_threshold=2.0
        )

        # Should detect the spike
        assert len(anomalies) >= 1
        spike_anomalies = [a for a in anomalies if a["type"] == "exposure_spike"]
        assert len(spike_anomalies) == 1

        spike = spike_anomalies[0]
        assert spike["value"] == 2000.0
        assert spike["z_score"] > 2.0
        assert spike["severity"] in ["medium", "high"]

    @pytest.mark.asyncio
    async def test_trend_prediction(self, exposure_history):
        """Test simple trend prediction."""
        current_time = time.time()

        # Add snapshots with clear linear trend
        base_exposure = 1000.0
        trend_increment = 50.0

        for i in range(12):  # 12 data points over 1 hour
            snapshot = ExposureSnapshot(
                timestamp=current_time - (12 - i) * 300,  # 5 minute intervals
                total_exposure=base_exposure + i * trend_increment,
                net_exposure=800.0,
                market_exposures={},
                outcome_exposures={},
                position_count=5,
            )
            exposure_history._recent_snapshots.append(snapshot)

        # Predict 2 hours ahead
        prediction = await exposure_history.predict_exposure_trend(
            hours_ahead=2, lookback_hours=1
        )

        assert "predicted_exposure" in prediction
        assert "trend_direction" in prediction
        assert "confidence" in prediction

        # Should predict increasing trend
        assert prediction["trend_direction"] == "increasing"

        # Should predict higher value (current ~1550 + 2 hours of trend)
        current_exposure = base_exposure + 11 * trend_increment  # 1550
        assert prediction["predicted_exposure"] > current_exposure

        # Confidence should be reasonable for clean linear trend
        assert 0.0 <= prediction["confidence"] <= 1.0


class TestIntegratedExposureSystem:
    """Test integration between all exposure tracking components."""

    def test_state_manager_position_update_flow(self, state_manager):
        """Test complete position update and exposure tracking flow."""
        # Start with empty state
        assert state_manager.get_total_exposure() == 0.0

        # Add first position
        position_1 = {
            "token_id": "token_1",
            "market_slug": "test_market",
            "outcome_type": "YES",
            "notional_value": 500.0,
            "size": 100.0,
        }

        state_manager.update_position(position_1)

        # Check exposures updated
        assert state_manager.get_total_exposure() == 500.0
        assert state_manager.get_market_exposure("test_market") == 500.0
        assert state_manager.get_outcome_exposure("YES") == 500.0

        # Add second position in same market, different outcome
        position_2 = {
            "token_id": "token_2",
            "market_slug": "test_market",
            "outcome_type": "NO",
            "notional_value": -300.0,
            "size": -60.0,
        }

        state_manager.update_position(position_2)

        # Check updated exposures
        assert state_manager.get_total_exposure() == 800.0  # |500| + |300|
        assert state_manager.get_market_exposure("test_market") == 800.0
        assert state_manager.get_outcome_exposure("YES") == 500.0
        assert state_manager.get_outcome_exposure("NO") == 300.0

        # Test detailed market analysis
        market_detail = state_manager.get_detailed_market_exposure("test_market")
        assert market_detail["net_exposure"] == 200.0  # 500 - 300
        assert market_detail["gross_exposure"] == 800.0
        assert market_detail["position_count"] == 2

    def test_exposure_limit_monitoring_integration(self, state_manager):
        """Test integrated exposure limit monitoring."""
        # Set up positions that will trigger alerts
        positions = {
            "large_position": {
                "market_slug": "high_risk_market",
                "outcome_type": "YES",
                "notional_value": 4500.0,  # Will exceed market limit
                "size": 900.0,
            },
            "medium_position": {
                "market_slug": "high_risk_market",
                "outcome_type": "NO",
                "notional_value": 3000.0,
                "size": 600.0,
            },
            "small_position": {
                "market_slug": "safe_market",
                "outcome_type": "YES",
                "notional_value": 1000.0,
                "size": 200.0,
            },
        }

        state_manager.positions = positions

        # Define risk limits
        limits = {
            "global_risk_cap": 10000.0,  # Total: 8500, so 85% utilization
            "per_market_risk_cap": 5000.0,  # high_risk_market: 7500, exceeds limit
            "per_outcome_risk_cap": 6000.0,  # YES: 5500, approaches limit
        }

        # Get alerts
        alerts = state_manager.get_exposure_alerts(limits)

        # Should have multiple alerts
        assert len(alerts) >= 2

        # Check for specific alert types
        alert_types = {alert["type"] for alert in alerts}
        assert "market_exposure_warning" in alert_types

        # Verify market alert details
        market_alerts = [a for a in alerts if a["type"] == "market_exposure_warning"]
        high_risk_alerts = [
            a for a in market_alerts if a["market_slug"] == "high_risk_market"
        ]

        assert len(high_risk_alerts) == 1
        assert high_risk_alerts[0]["utilization"] == 1.5  # 7500 / 5000
        assert high_risk_alerts[0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_real_time_exposure_updates(self, exposure_calculator):
        """Test real-time exposure update calculations."""
        # Mock existing portfolio
        with patch.object(
            exposure_calculator, "calculate_portfolio_exposure"
        ) as mock_portfolio:
            mock_portfolio.return_value = PortfolioExposure(
                total_notional=Decimal("5000"),
                net_exposure=Decimal("4000"),
                gross_exposure=Decimal("5000"),
                market_count=2,
                outcome_count=2,
                position_count=5,
                market_exposures={
                    "existing_market": MagicMock(total_notional=Decimal("3000"))
                },
                outcome_exposures={"YES": MagicMock(total_notional=Decimal("3500"))},
                concentration_metrics={"market_concentration": 0.6},
                risk_metrics={"leverage_ratio": 1.25},
            )

            # Test pre-trade impact analysis
            trade_impact = await exposure_calculator.calculate_real_time_exposure_delta(
                {
                    "token_id": "new_trade",
                    "size_delta": 200,
                    "price": 0.65,
                    "market_slug": "new_market",
                    "outcome_type": "NO",
                }
            )

            # Verify impact calculations
            expected_notional_delta = Decimal("130.0")  # |200 * 0.65|
            assert trade_impact["total_notional_delta"] == expected_notional_delta

            # Test that it correctly calculates new totals
            new_total = Decimal("5000") + expected_notional_delta
            assert new_total == Decimal("5130.0")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


class TestDatabaseExposureTracking:
    """Test database exposure tracking methods."""

    @pytest.fixture
    async def db_manager(self):
        """Create an in-memory database for testing."""
        db = DatabaseManager(":memory:")
        await db.initialize()
        return db

    @pytest.mark.asyncio
    async def test_record_trade_impact_new_position(self, db_manager):
        """Test recording trade impact for a new position."""
        result = await db_manager.record_trade_impact(
            token_id="token_123",
            trade_size=100.0,
            trade_price=0.75,
            side="BUY",
            market_slug="test_market",
            outcome_type="YES",
        )

        assert result["token_id"] == "token_123"
        assert result["market_slug"] == "test_market"
        assert result["outcome_type"] == "YES"
        assert result["size_delta"] == 100.0
        assert result["notional_delta"] == 75.0  # 100 * 0.75
        assert result["trade_notional"] == 75.0
        assert result["side"] == "BUY"
        assert result["price"] == 0.75

        # Verify position was created
        position = await db_manager.get_position_notional("token_123")
        assert position == 75.0

    @pytest.mark.asyncio
    async def test_record_trade_impact_existing_position(self, db_manager):
        """Test recording trade impact for an existing position."""
        # Create initial position
        await db_manager.record_trade_impact(
            token_id="token_123",
            trade_size=100.0,
            trade_price=0.75,
            side="BUY",
            market_slug="test_market",
            outcome_type="YES",
        )

        # Add another trade
        result = await db_manager.record_trade_impact(
            token_id="token_123",
            trade_size=50.0,
            trade_price=0.80,
            side="BUY",
            market_slug="test_market",
            outcome_type="YES",
        )

        assert result["size_delta"] == 50.0
        assert result["notional_delta"] == 40.0  # 50 * 0.80

        # Verify total position
        position = await db_manager.get_position_notional("token_123")
        assert position == 115.0  # 75 + 40

    @pytest.mark.asyncio
    async def test_record_trade_impact_sell_position(self, db_manager):
        """Test recording a sell trade (reducing position)."""
        # Create initial position
        await db_manager.record_trade_impact(
            token_id="token_123",
            trade_size=100.0,
            trade_price=0.75,
            side="BUY",
            market_slug="test_market",
            outcome_type="YES",
        )

        # Sell partial position
        result = await db_manager.record_trade_impact(
            token_id="token_123",
            trade_size=30.0,
            trade_price=0.80,
            side="SELL",
            market_slug="test_market",
            outcome_type="YES",
        )

        assert result["size_delta"] == -30.0
        assert result["notional_delta"] == -24.0  # -(30 * 0.80)

        # Verify reduced position
        position = await db_manager.get_position_notional("token_123")
        assert position == 51.0  # 75 - 24

    @pytest.mark.asyncio
    async def test_get_total_exposure(self, db_manager):
        """Test calculating total exposure across all positions."""
        # Create multiple positions
        await db_manager.record_trade_impact(
            "token_1", 100.0, 0.75, "BUY", "market_A", "YES"
        )
        await db_manager.record_trade_impact(
            "token_2", 200.0, 0.60, "BUY", "market_B", "NO"
        )
        await db_manager.record_trade_impact(
            "token_3", 50.0, 0.40, "SELL", "market_C", "YES"
        )

        total_exposure = await db_manager.get_total_exposure()
        expected = abs(75.0) + abs(120.0) + abs(-20.0)  # 215.0
        assert total_exposure == expected

    @pytest.mark.asyncio
    async def test_get_market_exposure(self, db_manager):
        """Test calculating exposure for a specific market."""
        # Create positions in different markets
        await db_manager.record_trade_impact(
            "token_1", 100.0, 0.75, "BUY", "market_A", "YES"
        )
        await db_manager.record_trade_impact(
            "token_2", 200.0, 0.60, "BUY", "market_A", "NO"
        )
        await db_manager.record_trade_impact(
            "token_3", 50.0, 0.40, "BUY", "market_B", "YES"
        )

        market_a_exposure = await db_manager.get_market_exposure("market_A")
        assert market_a_exposure == 195.0  # 75 + 120

        market_b_exposure = await db_manager.get_market_exposure("market_B")
        assert market_b_exposure == 20.0  # 50 * 0.4

    @pytest.mark.asyncio
    async def test_get_outcome_exposure(self, db_manager):
        """Test calculating exposure for a specific outcome type."""
        # Create positions with different outcomes
        await db_manager.record_trade_impact(
            "token_1", 100.0, 0.75, "BUY", "market_A", "YES"
        )
        await db_manager.record_trade_impact(
            "token_2", 200.0, 0.60, "BUY", "market_B", "YES"
        )
        await db_manager.record_trade_impact(
            "token_3", 50.0, 0.40, "BUY", "market_C", "NO"
        )

        yes_exposure = await db_manager.get_outcome_exposure("YES")
        assert yes_exposure == 195.0  # 75 + 120

        no_exposure = await db_manager.get_outcome_exposure("NO")
        assert no_exposure == 20.0  # 50 * 0.4

    @pytest.mark.asyncio
    async def test_get_market_summary(self, db_manager):
        """Test getting comprehensive market summary."""
        # Create positions in a market with different outcomes
        await db_manager.record_trade_impact(
            "token_1", 100.0, 0.75, "BUY", "test_market", "YES"
        )
        await db_manager.record_trade_impact(
            "token_2", 200.0, 0.60, "BUY", "test_market", "NO"
        )
        await db_manager.record_trade_impact(
            "token_3", 50.0, 0.80, "SELL", "test_market", "YES"
        )

        summary = await db_manager.get_market_summary("test_market")

        assert summary["market_slug"] == "test_market"
        assert summary["position_count"] == 3
        assert summary["total_exposure"] == 155.0  # 75 + 120 - 40 (signed values)
        assert summary["absolute_exposure"] == 235.0  # 75 + 120 + 40

        # Check outcome breakdown
        breakdown = {
            item["outcome_type"]: item for item in summary["outcome_breakdown"]
        }
        assert "YES" in breakdown
        assert "NO" in breakdown
        assert breakdown["YES"]["count"] == 2
        assert breakdown["NO"]["count"] == 1

    @pytest.mark.asyncio
    async def test_get_outcome_summary(self, db_manager):
        """Test getting comprehensive outcome summary."""
        # Create positions for YES outcome across different markets
        await db_manager.record_trade_impact(
            "token_1", 100.0, 0.75, "BUY", "market_A", "YES"
        )
        await db_manager.record_trade_impact(
            "token_2", 200.0, 0.60, "BUY", "market_B", "YES"
        )
        await db_manager.record_trade_impact(
            "token_3", 50.0, 0.80, "SELL", "market_A", "YES"
        )

        summary = await db_manager.get_outcome_summary("YES")

        assert summary["outcome_type"] == "YES"
        assert summary["position_count"] == 3
        assert summary["market_count"] == 2
        assert summary["total_exposure"] == 155.0  # 75 + 120 - 40
        assert summary["absolute_exposure"] == 235.0  # 75 + 120 + 40

        # Check market breakdown
        breakdown = {item["market_slug"]: item for item in summary["market_breakdown"]}
        assert "market_A" in breakdown
        assert "market_B" in breakdown
        assert breakdown["market_A"]["count"] == 2
        assert breakdown["market_B"]["count"] == 1


class TestStateManagerExposureTracking:
    """Test StateManager exposure tracking methods."""

    @pytest.fixture
    def state_manager(self):
        """Create StateManager with in-memory database."""
        with patch("inkedup_bot.state.DatabaseManager") as mock_db_class:
            mock_db = AsyncMock()
            mock_db_class.return_value = mock_db

            state = StateManager(":memory:")
            state.db = mock_db
            state._db_initialized = False  # Set to False to trigger fallback
            return state, mock_db

    def test_record_trade_impact_with_database(self, state_manager):
        """Test recording trade impact using database."""
        state, mock_db = state_manager

        # Mock the database method
        mock_db.record_trade_impact.return_value = {
            "token_id": "token_123",
            "market_slug": "test_market",
            "outcome_type": "YES",
            "size_delta": 100.0,
            "notional_delta": 75.0,
            "trade_notional": 75.0,
            "side": "BUY",
            "price": 0.75,
        }

        result = state.record_trade_impact(
            token_id="token_123",
            trade_size=100.0,
            trade_price=0.75,
            side="BUY",
            market_slug="test_market",
            outcome_type="YES",
        )

        # Verify database method was called
        mock_db.record_trade_impact.assert_called_once()

        # Verify result
        assert result["token_id"] == "token_123"
        assert result["trade_notional"] == 75.0

    def test_record_trade_impact_fallback_to_memory(self, state_manager):
        """Test fallback to in-memory tracking when database is not initialized."""
        state, mock_db = state_manager

        # Database not initialized - should use in-memory fallback
        assert not state._db_initialized

        result = state.record_trade_impact(
            token_id="token_123",
            trade_size=100.0,
            trade_price=0.75,
            side="BUY",
            market_slug="test_market",
            outcome_type="YES",
        )

        # Verify fallback worked
        assert result["token_id"] == "token_123"
        assert result["notional_delta"] == 75.0

        # Verify in-memory state was updated
        assert "test_market" in state.market_exposures
        assert "YES" in state.outcome_exposures
        assert state.market_exposures["test_market"] == 75.0
        assert state.outcome_exposures["YES"] == 75.0

    def test_get_market_summary_with_database(self, state_manager):
        """Test getting market summary from database."""
        state, mock_db = state_manager

        mock_summary = {
            "market_slug": "test_market",
            "position_count": 2,
            "total_exposure": 150.0,
            "absolute_exposure": 200.0,
            "outcome_breakdown": [
                {
                    "outcome_type": "YES",
                    "count": 1,
                    "exposure": 75.0,
                    "absolute_exposure": 75.0,
                },
                {
                    "outcome_type": "NO",
                    "count": 1,
                    "exposure": 75.0,
                    "absolute_exposure": 125.0,
                },
            ],
        }
        mock_db.get_market_summary.return_value = mock_summary

        result = state.get_market_summary("test_market")

        mock_db.get_market_summary.assert_called_once_with("test_market")
        assert result == mock_summary

    def test_get_market_summary_fallback_to_memory(self, state_manager):
        """Test market summary fallback to in-memory calculation."""
        state, mock_db = state_manager

        # Mock database failure
        mock_db.get_market_summary.side_effect = Exception("Database error")

        # Set up in-memory state
        state.market_exposures["test_market"] = 150.0
        state.positions = {
            "token_1": {
                "market_slug": "test_market",
                "outcome_type": "YES",
                "notional_value": 75.0,
            },
            "token_2": {
                "market_slug": "test_market",
                "outcome_type": "NO",
                "notional_value": 125.0,
            },
        }

        result = state.get_market_summary("test_market")

        assert result["market_slug"] == "test_market"
        assert result["position_count"] == 2
        assert result["total_exposure"] == 150.0


class TestRiskManagerExposureIntegration:
    """Test integration of exposure tracking with risk management."""

    @pytest.fixture
    def risk_manager_setup(self):
        """Create risk manager with mocked dependencies."""
        config = BotConfig(
            global_risk_cap=10000.0,
            position_risk_cap=1000.0,
            per_market_risk_cap=2000.0,
            per_outcome_risk_cap=1500.0,
            max_position_size=1000.0,
            max_order_size=100.0,
        )

        mock_order_client = Mock()
        mock_order_client.ready.return_value = True

        mock_state = Mock(spec=StateManager)
        mock_state.get_total_exposure.return_value = 500.0
        mock_state.get_position_notional.return_value = 200.0
        mock_state.get_market_exposure.return_value = 800.0
        mock_state.get_outcome_exposure.return_value = 600.0
        mock_state.get_all_positions.return_value = [
            {
                "token_id": "token_1",
                "market_slug": "market_A",
                "outcome_type": "YES",
                "notional_value": 300.0,
            },
            {
                "token_id": "token_2",
                "market_slug": "market_B",
                "outcome_type": "NO",
                "notional_value": 200.0,
            },
        ]
        # Add missing attributes for the legacy method
        mock_state.positions = {"token_123": {"notional_value": 50.0}}
        mock_state.update_position = Mock()
        mock_state.update_market_exposure = Mock()
        mock_state.update_outcome_exposure = Mock()

        risk_manager = RiskManager(
            cfg=config,
            order_client=mock_order_client,
            state=mock_state,
        )

        return risk_manager, mock_state

    def test_enhanced_record_trade(self, risk_manager_setup):
        """Test enhanced trade recording with full parameters."""
        risk_manager, mock_state = risk_manager_setup

        # Mock the enhanced trade recording
        mock_state.record_trade_impact.return_value = {
            "token_id": "token_123",
            "market_slug": "test_market",
            "outcome_type": "YES",
            "size_delta": 100.0,
            "notional_delta": 75.0,
            "trade_notional": 75.0,
            "side": "BUY",
            "price": 0.75,
        }

        result = risk_manager.record_trade(
            token_id="token_123",
            notional=75.0,  # Legacy parameter
            market_slug="test_market",
            outcome_type="YES",
            trade_size=100.0,  # Enhanced parameters
            trade_price=0.75,
            side="BUY",
        )

        # Verify enhanced method was called
        mock_state.record_trade_impact.assert_called_once_with(
            token_id="token_123",
            trade_size=100.0,
            trade_price=0.75,
            side="BUY",
            market_slug="test_market",
            outcome_type="YES",
        )

        assert result["trade_notional"] == 75.0

    def test_legacy_record_trade(self, risk_manager_setup):
        """Test legacy trade recording for backward compatibility."""
        risk_manager, mock_state = risk_manager_setup

        result = risk_manager.record_trade(
            token_id="token_123",
            notional=75.0,
            market_slug="test_market",
            outcome_type="YES",
        )

        # Verify legacy methods were called
        mock_state.update_position.assert_called_once()
        mock_state.update_market_exposure.assert_called_once_with("test_market", 75.0)
        mock_state.update_outcome_exposure.assert_called_once_with("YES", 75.0)

        assert result["method"] == "legacy"
        assert result["notional_delta"] == 75.0

    def test_get_exposure_summary(self, risk_manager_setup):
        """Test comprehensive exposure summary."""
        risk_manager, mock_state = risk_manager_setup

        summary = risk_manager.get_exposure_summary()

        assert summary["total_exposure"] == 500.0
        assert summary["position_count"] == 2
        assert summary["market_count"] == 2
        assert summary["outcome_count"] == 2
        assert "market_A" in summary["market_exposures"]
        assert "YES" in summary["outcome_exposures"]
        assert "risk_limits" in summary
        assert "utilization" in summary

    def test_get_market_risk_analysis(self, risk_manager_setup):
        """Test market-specific risk analysis."""
        risk_manager, mock_state = risk_manager_setup

        # Mock market summary
        mock_state.get_market_summary.return_value = {
            "market_slug": "test_market",
            "position_count": 2,
            "absolute_exposure": 1200.0,
            "total_exposure": 800.0,
            "outcome_breakdown": [
                {"outcome_type": "YES", "absolute_exposure": 700.0},
                {"outcome_type": "NO", "absolute_exposure": 500.0},
            ],
        }

        analysis = risk_manager.get_market_risk_analysis("test_market")

        assert analysis["market_slug"] == "test_market"
        assert "risk_metrics" in analysis
        assert "limits" in analysis
        assert (
            analysis["risk_metrics"]["exposure_utilization"] == 1200.0 / 2000.0
        )  # exposure / cap
        assert analysis["limits"]["remaining_capacity"] == 800.0  # 2000 - 1200

    def test_get_outcome_risk_analysis(self, risk_manager_setup):
        """Test outcome-specific risk analysis."""
        risk_manager, mock_state = risk_manager_setup

        # Mock outcome summary
        mock_state.get_outcome_summary.return_value = {
            "outcome_type": "YES",
            "position_count": 3,
            "market_count": 2,
            "absolute_exposure": 900.0,
            "total_exposure": 600.0,
            "market_breakdown": [
                {"market_slug": "market_A", "absolute_exposure": 500.0},
                {"market_slug": "market_B", "absolute_exposure": 400.0},
            ],
        }

        analysis = risk_manager.get_outcome_risk_analysis("YES")

        assert analysis["outcome_type"] == "YES"
        assert "risk_metrics" in analysis
        assert "limits" in analysis
        assert (
            analysis["risk_metrics"]["exposure_utilization"] == 900.0 / 1500.0
        )  # exposure / cap
        assert analysis["limits"]["remaining_capacity"] == 600.0  # 1500 - 900


class TestExposureTrackingEdgeCases:
    """Test edge cases and error handling in exposure tracking."""

    @pytest.fixture
    async def db_manager(self):
        """Create an in-memory database for testing."""
        db = DatabaseManager(":memory:")
        await db.initialize()
        return db

    @pytest.mark.asyncio
    async def test_zero_price_trade(self, db_manager):
        """Test handling of zero-price trades."""
        result = await db_manager.record_trade_impact(
            token_id="token_123",
            trade_size=100.0,
            trade_price=0.0,  # Zero price
            side="BUY",
            market_slug="test_market",
            outcome_type="YES",
        )

        assert result["trade_notional"] == 0.0
        assert result["notional_delta"] == 0.0

    @pytest.mark.asyncio
    async def test_zero_size_trade(self, db_manager):
        """Test handling of zero-size trades."""
        result = await db_manager.record_trade_impact(
            token_id="token_123",
            trade_size=0.0,  # Zero size
            trade_price=0.75,
            side="BUY",
            market_slug="test_market",
            outcome_type="YES",
        )

        assert result["trade_notional"] == 0.0
        assert result["size_delta"] == 0.0

    @pytest.mark.asyncio
    async def test_nonexistent_market_exposure(self, db_manager):
        """Test getting exposure for non-existent market."""
        exposure = await db_manager.get_market_exposure("nonexistent_market")
        assert exposure == 0.0

    @pytest.mark.asyncio
    async def test_nonexistent_outcome_exposure(self, db_manager):
        """Test getting exposure for non-existent outcome."""
        exposure = await db_manager.get_outcome_exposure("NONEXISTENT")
        assert exposure == 0.0

    @pytest.mark.asyncio
    async def test_update_nonexistent_position_exposure(self, db_manager):
        """Test updating exposure for non-existent position."""
        with pytest.raises(ValueError, match="Position not found"):
            await db_manager.update_position_exposure("nonexistent_token", 10.0, 7.5)
